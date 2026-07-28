"""Output backpressure contracts for real push_message calls."""

from __future__ import annotations

from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher, URGENT_REPLACE_EVENTS
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.core.contracts import CRITICAL_EVENT_IDS, BattleEvent, WtConfig


class FakePlugin:
    def __init__(self) -> None:
        self.cfg = WtConfig(
            output_backpressure_seconds=20.0,
            user_chat_quiet_window_seconds=0.0,
            battle_output_quiet_window_seconds=0.0,
        )
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


def test_suppressed_dispatch_trace_keeps_common_event_context():
    plugin = FakePlugin()
    plugin.cfg.output_backpressure_seconds = 0.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))
    event = BattleEvent(
        "air_threat_nearby",
        edge="enter",
        payload={"domain": "air"},
        ts=90.0,
        level="warning",
    )

    result = dispatcher.push_event(event, dry_run=False)

    assert result == "suppressed(event=air_threat_nearby/enter, reason=event_expired)"
    assert plugin.calls == []
    assert timeline.snapshot()["last_output_status"] == {
        "stage": "dispatcher_suppressed",
        "outcome": "dropped",
        "reason": "event_expired",
        "kind": "event",
        "ai_behavior": "respond",
        "pushed": False,
        "event_id": "air_threat_nearby",
        "edge": "enter",
        "level": "warning",
        "priority": event.priority,
        "dry_run": False,
        "event_ts": 90.0,
        "event_age_seconds": 10.0,
        "event_max_age_seconds": 3.0,
        "event_expires_at": 93.0,
    }


def test_active_frequency_shortens_noncritical_output_backpressure():
    plugin = FakePlugin()
    plugin.cfg.broadcast_frequency = "active"
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 114.0]))

    dispatcher.push_event(BattleEvent("you_killed"), dry_run=False)
    result = dispatcher.push_event(BattleEvent("spawn"), dry_run=False)

    assert result.startswith("pushed(event=spawn/enter)")
    assert len(plugin.calls) == 2


def test_quiet_frequency_extends_noncritical_output_backpressure():
    plugin = FakePlugin()
    plugin.cfg.broadcast_frequency = "quiet"
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 125.0]))

    dispatcher.push_event(BattleEvent("you_killed"), dry_run=False)
    result = dispatcher.push_event(BattleEvent("spawn"), dry_run=False)

    assert result == "suppressed(event=spawn/enter, reason=output_backpressure)"
    assert len(plugin.calls) == 1


def test_real_output_backpressure_allows_higher_priority_event_to_preempt_queue_guard():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    dispatcher.push_event(BattleEvent("you_killed"), dry_run=False)
    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="critical"), dry_run=False)

    assert result.startswith("pushed(event=low_alt_danger/enter)")
    assert len(plugin.calls) == 2
    assert plugin.calls[-1]["metadata"]["event_id"] == "low_alt_danger"


def test_real_output_backpressure_does_not_drop_confirmed_kill_praise():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 112.0]))

    dispatcher.push_event(BattleEvent("over_g", level="critical", ts=99.9), dry_run=False)
    result = dispatcher.push_event(BattleEvent("you_killed", ts=108.5), dry_run=False)

    assert result.startswith("pushed(event=you_killed/enter)")
    assert len(plugin.calls) == 2
    assert plugin.calls[-1]["metadata"]["event_id"] == "you_killed"
    assert "建议台词：" not in plugin.calls[-1]["parts"][0]["text"]
    assert "不套固定话" in plugin.calls[-1]["parts"][0]["text"]
    assert plugin.calls[-1]["metadata"]["plugin_recommended_reply"] == ""


def test_real_output_backpressure_never_blocks_death_event():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    dispatcher.push_event(BattleEvent("you_died", level="critical"), dry_run=False)
    result = dispatcher.push_event(BattleEvent("you_died", level="critical"), dry_run=False)

    assert result.startswith("pushed(event=you_died/enter)")
    assert len(plugin.calls) == 2
    assert plugin.calls[-1]["metadata"]["interrupt_battle_event"] is True


def test_confirmed_battle_outcomes_bypass_backpressure_without_interrupting():
    cases = [
        ("win, K2/D1", "victory", "自然庆祝或夸奖"),
        ("defeat, K0/D2", "defeat", "自然安慰或鼓励"),
    ]

    for result_text, result_kind, expected_intent in cases:
        plugin = FakePlugin()
        dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))
        dispatcher.push_event(BattleEvent("over_g", level="critical", ts=99.9), dry_run=False)

        result = dispatcher.push_event(
            BattleEvent(
                "battle_end",
                payload={"result": result_text, "result_kind": result_kind, "domain": "air"},
                ts=104.9,
            ),
            dry_run=False,
        )

        assert result.startswith("pushed(event=battle_end/enter)")
        assert len(plugin.calls) == 2
        call = plugin.calls[-1]
        assert expected_intent in call["parts"][0]["text"]
        assert call["metadata"]["replace_pending"] is True
        assert call["metadata"]["interrupt_battle_event"] is False
        assert call["metadata"]["interrupt_pending"] is False


def test_neutral_battle_end_remains_subject_to_output_backpressure():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))
    dispatcher.push_event(BattleEvent("over_g", level="critical", ts=99.9), dry_run=False)

    result = dispatcher.push_event(
        BattleEvent(
            "battle_end",
            payload={"result": "left", "result_kind": "neutral", "domain": "air"},
            ts=104.9,
        ),
        dry_run=False,
    )

    assert result == "suppressed(event=battle_end/enter, reason=output_backpressure)"
    assert len(plugin.calls) == 1


def test_repeated_urgent_safety_cue_collapses_inside_short_window():
    plugin = FakePlugin()
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0, 112.0, 131.0]))

    first = dispatcher.push_event(BattleEvent("over_g", level="critical", ts=99.9), dry_run=False)
    second = dispatcher.push_event(BattleEvent("over_g", level="critical", ts=111.9), dry_run=False)
    third = dispatcher.push_event(BattleEvent("over_g", level="critical", ts=130.9), dry_run=False)

    assert first.startswith("pushed(event=over_g/enter)")
    assert second == "suppressed(event=over_g/enter, reason=repeated_event_collapsed)"
    assert third.startswith("pushed(event=over_g/enter)")
    assert len(plugin.calls) == 2
    assert timeline.snapshot()["last_output_status"]["stage"] == "dispatcher_pushed"

    fact_plugin = FakePlugin()
    fact_plugin.cfg.output_backpressure_seconds = 0.0
    fact_dispatcher = NekoDispatcher(fact_plugin, clock=_clock([200.0, 201.0]))
    first_fact = fact_dispatcher.push_event(
        BattleEvent("enemy_nearby", payload={"target_type": "tank", "distance_m": 500}),
        dry_run=False,
    )
    changed_fact = fact_dispatcher.push_event(
        BattleEvent("enemy_nearby", payload={"target_type": "tank", "distance_m": 300}),
        dry_run=False,
    )
    assert first_fact.startswith("pushed(")
    assert changed_fact.startswith("pushed(")
    assert len(fact_plugin.calls) == 2


def test_critical_upgrade_is_not_collapsed_after_warning():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    first = dispatcher.push_event(BattleEvent("over_g", level="warning", ts=99.9), dry_run=False)
    second = dispatcher.push_event(BattleEvent("over_g", level="critical", ts=104.9), dry_run=False)

    assert first.startswith("pushed(event=over_g/enter)")
    assert second.startswith("pushed(event=over_g/enter)")
    assert len(plugin.calls) == 2
    assert plugin.calls[0]["metadata"]["level"] == "warning"
    assert plugin.calls[1]["metadata"]["level"] == "critical"


def test_real_output_backpressure_never_blocks_critical_safety_event():
    plugin = FakePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    dispatcher.push_event(BattleEvent("you_died", level="critical"), dry_run=False)
    result = dispatcher.push_event(BattleEvent("overspeed", level="critical", ts=104.0), dry_run=False)

    assert result.startswith("pushed(event=overspeed/enter)")
    assert len(plugin.calls) == 2
    assert plugin.calls[-1]["metadata"]["event_id"] == "overspeed"
    assert plugin.calls[-1]["metadata"]["interrupt_battle_event"] is True


def test_each_critical_safety_event_bypasses_backpressure_and_interrupts_pending():
    for event_id in sorted(CRITICAL_EVENT_IDS):
        plugin = FakePlugin()
        dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

        dispatcher.push_event(BattleEvent("you_died", level="critical", ts=99.0), dry_run=False)
        result = dispatcher.push_event(BattleEvent(event_id, level="critical", ts=104.0), dry_run=False)

        assert result.startswith(f"pushed(event={event_id}/enter)")
        assert len(plugin.calls) == 2
        metadata = plugin.calls[-1]["metadata"]
        assert metadata["event_id"] == event_id
        assert metadata["replace_pending"] is True
        assert metadata["interrupt_battle_event"] is True
        assert metadata["interrupt_pending"] is True
        assert metadata["dialogue_policy_owner"] == "plugin"
        assert metadata["plugin_dialogue_policy"]["owner"] == "plugin"


def test_dispatcher_urgent_replace_events_cover_all_critical_safety_events():
    assert CRITICAL_EVENT_IDS <= URGENT_REPLACE_EVENTS


def test_user_chat_quiet_window_suppresses_nonurgent_battle_cue():
    plugin = FakePlugin()
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin._last_user_chat_at = 100.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([105.0]))

    result = dispatcher.push_event(BattleEvent("you_killed", ts=104.0), dry_run=False)

    assert result == "suppressed(event=you_killed/enter, reason=user_chat_quiet_window)"
    assert plugin.calls == []
    status = timeline.snapshot()["last_output_status"]
    assert status["reason"] == "user_chat_quiet_window"
    assert status["quiet_window_remaining_seconds"] == 15.0


def test_confirmed_kill_during_text_chat_becomes_passive_context():
    plugin = FakePlugin()
    plugin.cfg.target_lanlan = "Lanlan"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin._last_user_chat_at = 100.0
    plugin._last_user_chat_mode = "text"
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([105.0]))

    result = dispatcher.push_event(BattleEvent("you_killed", ts=104.0), dry_run=False)

    assert result.startswith("pushed(event=you_killed/enter)")
    assert len(plugin.calls) == 1
    call = plugin.calls[0]
    assert call["ai_behavior"] == "read"
    assert call["visibility"] == []
    assert call["target_lanlan"] == "Lanlan"
    assert call["metadata"]["delivery_strategy"] == "passive_context"
    assert call["metadata"]["passive_from_user_chat_quiet_window"] is True
    assert call["metadata"]["quiet_window_remaining_seconds"] == 15.0
    assert "只供之后自然发生的用户轮次参考" in call["parts"][0]["text"]
    assert "不要求在回复中提及" in call["parts"][0]["text"]
    # 规范入口是 ai_behavior=read；metadata 只补充通用的被动上下文意图。
    assert call["metadata"]["delivery_intent"] == "passive_context"
    assert "candidate_ttl_seconds" not in call["metadata"]
    assert "consume_hint" not in call["metadata"]
    assert "deferred_from_user_chat_quiet_window" not in call["metadata"]
    status = timeline.snapshot()["last_output_status"]
    assert status["ai_behavior"] == "read"
    assert status["delivery_strategy"] == "passive_context"
    assert status["delivery_intent"] == "passive_context"
    assert status["passive_from_user_chat_quiet_window"] is True


def test_confirmed_kill_during_voice_chat_keeps_noninterrupting_suppression():
    plugin = FakePlugin()
    plugin.cfg.target_lanlan = "Lanlan"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin._last_user_chat_at = 100.0
    plugin._last_user_chat_mode = "voice"
    dispatcher = NekoDispatcher(plugin, clock=_clock([105.0]))

    result = dispatcher.push_event(BattleEvent("you_killed", ts=104.0), dry_run=False)

    assert result == "suppressed(event=you_killed/enter, reason=user_chat_quiet_window)"
    assert plugin.calls == []


def test_text_chat_does_not_convert_nonkill_cues_to_passive_followups():
    plugin = FakePlugin()
    plugin.cfg.target_lanlan = "Lanlan"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin._last_user_chat_at = 100.0
    plugin._last_user_chat_mode = "text"
    dispatcher = NekoDispatcher(plugin, clock=_clock([105.0]))

    result = dispatcher.push_event(BattleEvent("spawn", ts=104.0), dry_run=False)

    assert result == "suppressed(event=spawn/enter, reason=user_chat_quiet_window)"
    assert plugin.calls == []


def test_user_chat_quiet_window_allows_critical_safety_cue():
    plugin = FakePlugin()
    plugin.cfg.dialogue_intrusion_mode = "critical_only"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin._last_user_chat_at = 100.0
    dispatcher = NekoDispatcher(plugin, clock=_clock([105.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="critical", ts=104.0), dry_run=False)

    assert result.startswith("pushed(event=low_alt_danger/enter)")
    assert len(plugin.calls) == 1
    assert plugin.calls[0]["metadata"]["interrupt_battle_event"] is True


def test_no_interrupt_mode_suppresses_critical_safety_cue_during_user_chat():
    plugin = FakePlugin()
    plugin.cfg.dialogue_intrusion_mode = "no_interrupt"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin._last_user_chat_at = 100.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([105.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="critical", ts=104.0), dry_run=False)

    assert result == "suppressed(event=low_alt_danger/enter, reason=user_chat_quiet_window)"
    assert plugin.calls == []
    assert timeline.snapshot()["last_output_status"]["reason"] == "user_chat_quiet_window"


def test_allow_interrupt_mode_bypasses_user_chat_quiet_window_for_ordinary_cues():
    plugin = FakePlugin()
    plugin.cfg.dialogue_intrusion_mode = "allow_interrupt"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin._last_user_chat_at = 100.0
    dispatcher = NekoDispatcher(plugin, clock=_clock([105.0]))

    result = dispatcher.push_event(BattleEvent("you_killed", ts=104.0), dry_run=False)

    assert result.startswith("pushed(event=you_killed/enter)")
    assert len(plugin.calls) == 1


def test_battle_output_quiet_window_suppresses_ordinary_followup():
    plugin = FakePlugin()
    plugin.cfg.battle_output_quiet_window_seconds = 20.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0, 108.0]))

    first = dispatcher.push_event(BattleEvent("you_killed", ts=99.0), dry_run=False)
    second = dispatcher.push_event(BattleEvent("spawn", ts=107.0), dry_run=False)

    assert first.startswith("pushed(event=you_killed/enter)")
    assert second == "suppressed(event=spawn/enter, reason=battle_output_quiet_window)"
    assert len(plugin.calls) == 1
    status = timeline.snapshot()["last_output_status"]
    assert status["reason"] == "battle_output_quiet_window"
    assert status["quiet_window_remaining_seconds"] == 12.0


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
    assert metadata["event_max_age_seconds"] == 30.0


def test_delayed_kill_praise_keeps_wider_freshness_window_after_combat_stress():
    plugin = FakePlugin()
    plugin.cfg.output_event_max_age_seconds = 8.0
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 100.0]))

    fresh = dispatcher.push_event(BattleEvent("you_killed", level="warning", ts=71.0), dry_run=False)
    expired = dispatcher.push_event(BattleEvent("you_killed", level="warning", ts=69.0), dry_run=False)

    assert fresh.startswith("pushed(")
    assert expired == "suppressed(event=you_killed/enter, reason=event_expired)"


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
    assert plugin.calls[0]["visibility"] == []
    assert plugin.calls[0]["ai_behavior"] == "respond"
    assert "{MASTER_NAME}" in plugin.calls[0]["parts"][0]["text"]
    assert "建议台词：拉起来，要撞地了！" in plugin.calls[0]["parts"][0]["text"]
    assert metadata["plugin_owned_output"] is False
    assert metadata["plugin_recommended_reply"] == "拉起来，要撞地了！"
    assert metadata["reply_style_contract"].startswith("Boundary: exactly one short Chinese line")
    assert "character owns the emotion and wording" in metadata["reply_style_contract"]
    assert metadata["dialogue_policy_owner"] == "plugin"
    assert metadata["plugin_dialogue_policy"] == {
        "owner": "plugin",
        "mode": "short_tts_line",
        "max_chars": 28,
        "single_line": True,
        "no_followup": True,
        "prompt_owned": True,
        "style": "short_line",
        "style_hint": metadata["reply_style_contract"],
    }
    status = timeline.snapshot()["last_output_status"]
    assert status["battle_reply_contract"] == "short_tts_line"
    assert status["live_reply_contract"] == "short_tts_line"
    assert status["max_reply_chars"] == 28
    assert status["response_module_hint"] == "war_thunder_battle_event"
    assert status["ai_behavior"] == "respond"
    assert status["visibility"] == []
    assert status["plugin_owned_output"] is False
    assert status["plugin_recommended_reply"] == "拉起来，要撞地了！"
    assert status["reply_style_contract"].startswith("Boundary: exactly one short Chinese line")
    assert status["dialogue_policy_owner"] == "plugin"
    assert status["plugin_dialogue_policy"]["owner"] == "plugin"


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
    assert metadata["dialogue_policy_owner"] == "plugin"
    assert metadata["plugin_quiet_window_policy"] == "suppress_non_urgent_during_user_input"
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
    assert "reply" not in contract
    assert "quiet_window" not in contract
    assert metadata["plugin_dialogue_policy"]["owner"] == "plugin"
    assert metadata["plugin_dialogue_policy"]["mode"] == "short_tts_line"
    assert metadata["plugin_dialogue_policy"]["max_chars"] == 28
    assert metadata["plugin_dialogue_policy"]["single_line"] is True
    assert contract["freshness"]["event_age_seconds"] == 1.0
    assert contract["target"] == {"lanlan": "Lanlan"}
    status = timeline.snapshot()["last_output_status"]
    assert status["host_callback_contract_version"] == "neko.callback.v1"
    assert status["interrupt_pending"] is True


def test_kill_prompt_requests_one_response_without_prescribing_style():
    prompt = NekoDispatcher(None).build_prompt(BattleEvent("you_killed", payload={"kill_count": 2}))

    assert "合并后的可信战果" in prompt
    assert "只回应一次" in prompt
    assert "不逐条念" in prompt
    assert "插件不指定情绪或措辞" in prompt
    assert "轻夸" not in prompt
    assert "坏笑" not in prompt


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

    result = dispatcher.push_context("context")

    assert result is True
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
