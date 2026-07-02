"""Output backpressure contracts for real push_message calls."""

from __future__ import annotations

from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.core.contracts import BattleEvent, WtConfig


class FakePlugin:
    def __init__(self) -> None:
        self.cfg = WtConfig(output_backpressure_seconds=20.0)
        self.calls: list[dict] = []

    def push_message(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _clock(values: list[float]):
    def tick() -> float:
        return values.pop(0)

    return tick


def test_real_output_backpressure_suppresses_same_or_lower_priority_pushes():
    plugin = FakePlugin()
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0, 105.0]))

    first = dispatcher.push_event(BattleEvent("you_killed"), dry_run=False)
    second = dispatcher.push_event(BattleEvent("spawn"), dry_run=False)

    assert first.startswith("pushed(")
    assert second == "suppressed(event=spawn/enter, reason=output_backpressure)"
    assert len(plugin.calls) == 1
    snapshot = timeline.snapshot()
    assert snapshot["last_output_status"]["stage"] == "dispatcher_suppressed"
    assert snapshot["last_output_status"]["reason"] == "output_backpressure"


def test_real_output_backpressure_allows_higher_priority_event_to_preempt_queue_guard():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    dispatcher.push_event(BattleEvent("you_killed"), dry_run=False)
    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="critical"), dry_run=False)

    assert result.startswith("pushed(event=low_alt_danger/enter)")
    assert len(plugin.calls) == 2
    assert plugin.calls[-1]["metadata"]["event_id"] == "low_alt_danger"


def test_real_output_backpressure_never_blocks_death_event():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    dispatcher.push_event(BattleEvent("you_died", level="critical"), dry_run=False)
    result = dispatcher.push_event(BattleEvent("you_died", level="critical"), dry_run=False)

    assert result.startswith("pushed(event=you_died/enter)")
    assert len(plugin.calls) == 2
    assert plugin.calls[-1]["metadata"]["interrupt_battle_event"] is True


def test_real_event_pushes_use_battle_coalesce_key_to_replace_stale_host_queue():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    dispatcher.push_event(BattleEvent("low_alt_danger", level="warning"), dry_run=False)
    dispatcher.push_event(BattleEvent("you_died", level="critical"), dry_run=False)

    assert len(plugin.calls) == 2
    assert plugin.calls[0]["metadata"]["event_id"] == "low_alt_danger"
    assert plugin.calls[1]["metadata"]["event_id"] == "you_died"
    assert plugin.calls[0]["coalesce_key"] == "neko_warthunder:battle_event"
    assert plugin.calls[1]["coalesce_key"] == "neko_warthunder:battle_event"
    assert plugin.calls[0]["metadata"]["replace_pending"] is True
    assert plugin.calls[1]["metadata"]["replace_pending"] is True
    assert plugin.calls[1]["metadata"]["interrupt_battle_event"] is True


def test_real_output_drops_expired_battle_event_before_push():
    plugin = FakePlugin()
    plugin.cfg.output_event_max_age_seconds = 5.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="warning", ts=90.0), dry_run=False)

    assert result == "suppressed(event=low_alt_danger/enter, reason=event_expired)"
    assert plugin.calls == []
    status = timeline.snapshot()["last_output_status"]
    assert status["stage"] == "dispatcher_suppressed"
    assert status["reason"] == "event_expired"
    assert status["event_age_seconds"] == 10.0
    assert status["event_max_age_seconds"] == 4.0


def test_tactical_awareness_events_expire_faster_than_global_default():
    plugin = FakePlugin()
    plugin.cfg.output_event_max_age_seconds = 8.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("air_threat_nearby", level="warning", ts=96.5), dry_run=False)

    assert result == "suppressed(event=air_threat_nearby/enter, reason=event_expired)"
    assert plugin.calls == []
    status = timeline.snapshot()["last_output_status"]
    assert status["event_age_seconds"] == 3.5
    assert status["event_max_age_seconds"] == 3.0


def test_kill_events_keep_short_but_less_aggressive_freshness_window():
    plugin = FakePlugin()
    plugin.cfg.output_event_max_age_seconds = 8.0
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("you_killed", level="warning", ts=94.5), dry_run=False)

    assert result.startswith("pushed(")
    metadata = plugin.calls[0]["metadata"]
    assert metadata["event_age_seconds"] == 5.5
    assert metadata["event_max_age_seconds"] == 6.0


def test_real_event_push_metadata_carries_event_age_and_expiry_for_host_queue():
    plugin = FakePlugin()
    plugin.cfg.output_event_max_age_seconds = 8.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="warning", ts=97.0), dry_run=False)

    assert result.startswith("pushed(")
    metadata = plugin.calls[0]["metadata"]
    assert metadata["event_id"] == "low_alt_danger"
    assert metadata["event_age_seconds"] == 3.0
    assert metadata["event_max_age_seconds"] == 4.0
    assert metadata["event_expires_at"] == 101.0
    status = timeline.snapshot()["last_output_status"]
    assert status["event_age_seconds"] == 3.0
    assert status["event_max_age_seconds"] == 4.0


def test_real_event_push_metadata_requests_short_tts_output_contract():
    plugin = FakePlugin()
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="critical", ts=99.0), dry_run=False)

    assert result.startswith("pushed(")
    metadata = plugin.calls[0]["metadata"]
    assert metadata["battle_reply_contract"] == "short_tts_line"
    assert metadata["live_reply_contract"] == "short_tts_line"
    assert metadata["max_reply_chars"] == 28
    assert metadata["response_module_hint"] == "war_thunder_battle_event"
    assert metadata["reply_style_contract"].startswith("Style: one short Chinese line")
    status = timeline.snapshot()["last_output_status"]
    assert status["battle_reply_contract"] == "short_tts_line"
    assert status["live_reply_contract"] == "short_tts_line"
    assert status["max_reply_chars"] == 28
    assert status["response_module_hint"] == "war_thunder_battle_event"
    assert status["reply_style_contract"].startswith("Style: one short Chinese line")


def test_real_event_push_metadata_reserves_generic_host_callback_contract():
    plugin = FakePlugin()
    plugin.cfg.target_lanlan = "Lanlan"
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="critical", ts=99.0), dry_run=False)

    assert result.startswith("pushed(")
    metadata = plugin.calls[0]["metadata"]
    contract = metadata["host_callback_contract"]
    assert metadata["host_callback_contract_version"] == "neko.callback.v1"
    assert metadata["interrupt_pending"] is True
    assert metadata["reply_contract"] == "short_tts_line"
    assert metadata["reply_max_chars"] == 28
    assert metadata["quiet_window_policy"] == "suppress_non_urgent_during_user_input"
    assert contract["version"] == "neko.callback.v1"
    assert contract["kind"] == "realtime_cue"
    assert contract["delivery"] == {
        "coalesce_key": "neko_warthunder:battle_event",
        "replace_pending": True,
        "interrupt_pending": True,
        "priority": 9,
        "expires_at": 103.0,
        "max_age_seconds": 4.0,
    }
    assert contract["reply"]["mode"] == "short_tts_line"
    assert contract["reply"]["style"] == "short_line"
    assert contract["reply"]["max_chars"] == 28
    assert contract["reply"]["single_turn"] is True
    assert contract["reply"]["drop_followup_chunks"] is True
    assert contract["quiet_window"] == {
        "policy": "suppress_non_urgent_during_user_input",
        "bypass": True,
    }
    assert contract["freshness"]["event_age_seconds"] == 1.0
    assert contract["target"] == {"lanlan": "Lanlan"}
    status = timeline.snapshot()["last_output_status"]
    assert status["host_callback_contract_version"] == "neko.callback.v1"
    assert status["interrupt_pending"] is True


def test_kill_prompt_requests_one_shot_non_repetitive_praise():
    prompt = NekoDispatcher(None).build_prompt(BattleEvent("you_killed", payload={"kill_count": 2}))

    assert "multi-kill once" in prompt
    assert "no repeated praise" in prompt


def test_real_event_push_uses_configured_target_lanlan():
    plugin = FakePlugin()
    plugin.cfg.target_lanlan = "Lanlan"
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("you_killed", ts=99.0), dry_run=False)

    assert result.startswith("pushed(")
    call = plugin.calls[0]
    assert call["target_lanlan"] == "Lanlan"
    assert call["metadata"]["target_lanlan"] == "Lanlan"


def test_context_push_uses_configured_target_lanlan():
    plugin = FakePlugin()
    plugin.cfg.target_lanlan = "Lanlan"
    dispatcher = NekoDispatcher(plugin)

    dispatcher.push_context("context")

    assert plugin.calls[0]["target_lanlan"] == "Lanlan"
    assert plugin.calls[0]["metadata"]["target_lanlan"] == "Lanlan"


def test_output_backpressure_does_not_affect_dry_run_decisions():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    first = dispatcher.push_event(BattleEvent("you_killed"), dry_run=True)
    second = dispatcher.push_event(BattleEvent("spawn"), dry_run=True)

    assert first.startswith("dry_run(")
    assert second.startswith("dry_run(")
    assert plugin.calls == []
