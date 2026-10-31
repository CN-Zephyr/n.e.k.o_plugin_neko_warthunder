"""An observation's real decision path, without inference from event names or output mode."""
from __future__ import annotations

import copy
import json

import pytest
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.core import contracts as C
from test_helicopter_vrs import _evaluate, _runtime
from test_naval_diagnostics import _card
from test_naval_events import _state


def _result(plugin, event_id="naval_map_contact"):
    return next(row["result"] for row in _card(plugin)["detectors"] if row["event_id"] == event_id)


def _confirm(plugin, moment, *, air=False, now=1000):
    for count in (1, 2):
        _evaluate(plugin, moment, _state(count, now, surface=not air, air=air))


@pytest.mark.parametrize("event_id", sorted(C.NAVAL_DRY_RUN_ONLY_EVENTS))
@pytest.mark.parametrize("debug", [False, True])
def test_real_pipeline_links_candidate_decision_and_dry_run_even_without_debug(monkeypatch, event_id, debug):
    plugin, moment = _runtime(monkeypatch)
    plugin.timeline.configure(observability_enabled=debug, max_events=1, include_prompt_preview=False)
    _confirm(plugin, moment, air=event_id == "naval_air_contact")
    result = _result(plugin, event_id)
    assert [result[k]["stage"] for k in ("candidate", "decision", "output")] == [
        "detector_candidate", "arbiter_allowed", "dispatcher_dry_run"]
    assert len({row["trace_id"] for row in result.values()}) == 1
    assert result["candidate"]["map_sample_count"] == 2
    assert result["output"]["reason"] == "dry_run_enabled"
    for _ in range(25):
        plugin.timeline.record_stage(stage="dispatcher_dry_run", outcome="dry_run", reason="dry_run_enabled", event_id="spawn")
    assert not any(row.get("event_id") == event_id for row in plugin.timeline.snapshot()["recent_activity"])
    assert _result(plugin, event_id) == result
    assert plugin.pushed_messages == []


def test_simultaneous_classes_have_separate_results_and_one_output(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    for count in (1, 2):
        _evaluate(plugin, moment, _state(count))
    results = [_result(plugin, event_id) for event_id in sorted(C.NAVAL_DRY_RUN_ONLY_EVENTS)]
    assert len({r["candidate"]["trace_id"] for r in results}) == 2
    assert sum(r["output"] is not None for r in results) == 1
    assert {r["decision"]["reason"] for r in results} == {"selected", "lost_in_window"}
    assert plugin.pushed_messages == []


@pytest.mark.parametrize("mode,reason", [("real", "naval_dry_run_only"), ("category", "broadcast_category_disabled"),
                                        ("cooldown", "cooldown_active"), ("paused", "paused"),
                                        ("tripped", "tripped"), ("scenario", "scenario_gated"),
                                        ("expiry", "expired_before_flush")])
def test_actual_arbiter_reasons_are_not_misreported_as_successful_dry_run(monkeypatch, mode, reason):
    plugin, moment = _runtime(monkeypatch, dry_run=mode != "real")
    _evaluate(plugin, moment, _state(1, surface=True, air=False))
    if mode == "category":
        plugin.cfg.broadcast_categories["awareness"] = False
    elif mode == "cooldown":
        plugin.arbiter._last_fired["naval_map_contact"] = (999.8, "info")
    elif mode == "paused":
        plugin.safety.manual_paused = True
    elif mode == "tripped":
        plugin.safety.auto_paused = True
    elif mode == "scenario":
        plugin.resolver.resolve = lambda *_: C.CRITICAL_RISK
    elif mode == "expiry":
        plugin.cfg.global_rate_limit_seconds = 10
        plugin.safety.mark_output(critical=False, now=999.5)
    _evaluate(plugin, moment, _state(2, surface=True, air=False))
    result = _result(plugin)
    assert result["candidate"] is not None
    assert result["decision"]["reason"] == reason
    assert result["output"] is None
    assert _card(plugin)["real_output_enabled"] is False and plugin.pushed_messages == []


@pytest.mark.parametrize("ending", ["flush", "clear"])
def test_buffer_keeps_the_original_observation_through_wait_flush_or_revocation(monkeypatch, ending):
    plugin, moment = _runtime(monkeypatch)
    plugin.cfg.global_rate_limit_seconds = 2
    plugin.safety.mark_output(critical=False, now=999.5)
    _confirm(plugin, moment)
    before = _result(plugin)
    assert before["decision"]["reason"] == "rate_limited" and before["output"] is None
    now = {"flush": 1002, "clear": 1001}[ending]
    _evaluate(plugin, moment, _state(3, now, surface=ending != "clear", air=False))
    after = _result(plugin)
    assert after["candidate"] == before["candidate"]
    assert after["decision"]["reason"] == {"flush": "selected", "clear": "naval_contact_cleared"}[ending]
    assert (after["output"] is not None) == (ending == "flush")
    assert plugin.pushed_messages == []


def test_new_confirmation_does_not_reuse_old_outcomes_or_accept_late_old_results(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    _confirm(plugin, moment)
    old = _result(plugin)
    for count in (3, 4):
        _evaluate(plugin, moment, _state(count, 1001, surface=False, air=False))
    assert _result(plugin) is None
    plugin.safety.manual_paused = True
    _evaluate(plugin, moment, _state(5, 1002, air=False))
    assert _result(plugin) is None
    _evaluate(plugin, moment, _state(6, 1003, air=False))
    current = _result(plugin)
    assert current["candidate"]["trace_id"] != old["candidate"]["trace_id"]
    assert current["decision"]["reason"] == "paused" and current["output"] is None
    plugin.timeline.record_stage(stage="dispatcher_dry_run", outcome="dry_run", reason="dry_run_enabled",
                                 event_id="naval_map_contact", trace_id=old["candidate"]["trace_id"])
    assert _result(plugin) == current


@pytest.mark.parametrize("change", ["life", "battle", "rewind", "stale", "replay", "unknown", "disabled"])
def test_changed_or_invalid_context_never_borrows_a_previous_result(monkeypatch, change):
    plugin, moment = _runtime(monkeypatch)
    _confirm(plugin, moment)
    if change == "life":
        plugin.state.life_index = plugin.state.raw["meta"]["map_objects"]["life_index"] = 2
    elif change == "battle":
        plugin.state.battle_id = "private-new-battle"
    elif change == "rewind":
        plugin.state.raw["meta"]["map_objects"]["count"] = 1
    elif change == "stale":
        moment[0] += 6
    elif change == "replay":
        plugin.state.replay = True
    elif change == "unknown":
        plugin.state.domain = "unknown"
    else:
        plugin.cfg.enabled = False
    assert _result(plugin) is None


def test_reads_return_detached_results_and_do_not_mutate_any_pipeline_state(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    _confirm(plugin, moment)
    before = _result(plugin)
    state = copy.deepcopy(plugin.state)
    progress = [copy.deepcopy(det.__dict__) for det in plugin.engine.detectors]
    arbiter = copy.deepcopy(plugin.arbiter.__dict__ | {"safety": None})
    timeline = copy.deepcopy(plugin.timeline.snapshot())
    for _ in range(8):
        result = _result(plugin)
        result["output"]["reason"] = "private-sentinel"
        assert _result(plugin) == before
    assert plugin.state == state
    assert [det.__dict__ for det in plugin.engine.detectors] == progress
    assert plugin.arbiter.__dict__ | {"safety": None} == arbiter
    assert plugin.timeline.snapshot() == timeline and plugin.pushed_messages == []


@pytest.mark.parametrize("trace_id", [None, "private-sentinel", "g" * 32, True])
def test_missing_or_invalid_trace_cannot_be_guessed_from_event_id(trace_id):
    timeline = RuntimeTimeline()
    event = C.BattleEvent("naval_map_contact", trace_id=trace_id)
    assert event.naval_trace_id is None
    timeline.record_stage(stage="detector_candidate", outcome="candidate", reason="detected",
                          event_id=event.event_id, trace_id=trace_id)
    assert timeline.naval_result(event.event_id, trace_id) is None
    assert "trace_id" not in event.to_dict() and "private-sentinel" not in repr(event)


def test_result_cache_is_bounded_and_whitelists_metadata_and_reason_text():
    timeline = RuntimeTimeline(observability_enabled=False)
    for number in range(50):
        trace = f"{number:032x}"
        timeline.record_stage(stage="detector_candidate", outcome="candidate", reason="detected",
                              event_id="naval_map_contact", trace_id=trace, map_sample_count=2,
                              payload={"name": "private-sentinel"})
        timeline.record_stage(stage="arbiter_dropped", outcome="dropped", reason="private-sentinel",
                              event_id="naval_map_contact", trace_id=trace, safe_summary="private-sentinel")
    assert len(timeline._naval_results) == 1
    result = timeline.naval_result("naval_map_contact", trace)
    assert result["decision"]["reason"] == "unknown"
    assert "private-sentinel" not in json.dumps(result)
    timeline.record_stage(stage="dispatcher_dry_run", outcome="dry_run", reason="dry_run_enabled",
                          event_id="naval_air_contact", trace_id=trace)
    assert timeline.naval_result("naval_air_contact", trace) is None
    assert timeline.naval_result("naval_map_contact", "0" * 32) is None


def test_direct_dispatch_and_unrelated_event_traces_do_not_manufacture_candidates(monkeypatch):
    plugin, _ = _runtime(monkeypatch, dry_run=False)
    trace = "a" * 32
    event = C.BattleEvent("naval_map_contact", trace_id=trace)
    assert "naval_dry_run_only" in plugin.dispatcher.push_event(event, dry_run=False)
    assert plugin.timeline.naval_result(event.event_id, trace) is None
    assert C.BattleEvent("spawn", trace_id=trace).naval_trace_id is None
    assert plugin.pushed_messages == []


def test_retry_registration_retains_previous_stage_results_for_the_same_observation(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    _confirm(plugin, moment)
    before = _result(plugin)
    plugin.timeline.record_stage(stage="detector_candidate", outcome="candidate", reason="detected",
                                 event_id="naval_map_contact", trace_id=before["candidate"]["trace_id"])
    assert _result(plugin) == before
