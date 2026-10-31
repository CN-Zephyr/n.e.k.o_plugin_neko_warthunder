"""VRS flags through the real decision pipeline, with hard real-output denial."""

from __future__ import annotations

import sys

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core import contracts as C
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.scenario import ScenarioResolver
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from test_status_reporting import _plugin_for_action_tests
from wt_processor import TelemetryProcessor
from wt_telemetry import Indicators, VehicleState


def _state(vario=-6, now=1000, **patch):
    processed = TelemetryProcessor().process(
        VehicleState(valid=True),
        Indicators(valid=True, army="air", is_helicopter=True, speed=2,
                   prop_rpm=396, radio_altitude=30, vario_ms=vario), now,
    ).to_dict()
    payload = {
        "state": "in_battle", "in_battle": True, "domain": "heli", "timestamp": now,
        "battle_id": "synthetic-heli-battle", "life_index": 1,
        "vehicle": {"valid": True}, "indicators": {"valid": True}, "processed": processed,
        "meta": {"fast": {"age_sec": 0.1}, "vehicle": {"age_sec": 0.2}},
        "chat": [{"sender": "private-sentinel", "msg": "private-sentinel"}],
    }
    payload.update(patch)
    return parse_telemetry(payload)


def _engine():
    return DetectorEngine(build_condition_detectors())


def _runtime(monkeypatch, dry_run=True):
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = dry_run
    plugin.cfg.spawn_grace_seconds = 0
    plugin.cfg.global_rate_limit_seconds = 0
    plugin.cfg.output_backpressure_seconds = 0
    plugin.cfg.dialogue_intrusion_mode = "allow_interrupt"
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=200)
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    moment = [1000.0]
    plugin.dispatcher = NekoDispatcher(plugin, timeline=plugin.timeline, clock=lambda: moment[0])
    monkeypatch.setattr(sys.modules[type(plugin).__module__].time, "time", lambda: moment[0])
    return plugin, moment


def _evaluate(plugin, moment, current):
    moment[0] = current.timestamp
    previous = plugin.state
    plugin.state = current
    plugin._evaluate(previous, current)


def _vrs_records(plugin):
    return [item for item in plugin.timeline.snapshot()["recent_timeline"] if item.get("event_id") == "heli_vrs_risk"]


def test_processor_to_detector_debounces_upgrades_and_rearms_without_recovery():
    engine = _engine()
    previous = C.BattleState()
    events = []
    # A one-frame exit must not rearm; two exits do. No recovery event is added.
    for now, vario in enumerate([-6, 0, -6, -6, -6, -12, 0, -12, 0, 0, -6, -6], start=1000):
        current = _state(vario, now)
        events.extend(engine.feed(previous, current))
        previous = current
    assert [(e.event_id, e.level, e.edge, e.ts, e.payload) for e in events] == [
        ("heli_vrs_risk", "warning", "enter", 1003, {"domain": "heli"}),
        ("heli_vrs_risk", "critical", "enter", 1005, {"domain": "heli"}),
        ("heli_vrs_risk", "warning", "enter", 1011, {"domain": "heli"}),
    ]
    assert not events[1].preempt_eligible
    assert events[1].category == C.CAT_SAFETY_IMPORTANT


@pytest.mark.parametrize("patch", [
    {"domain": "air"}, {"domain": "ground"}, {"domain": "naval"}, {"domain": "unknown"},
    {"domain": ""}, {"dead": True}, {"replay": True}, {"in_battle": False},
    {"state": "offline"}, {"vehicle": {"valid": False}},
    {"meta": {}}, {"meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": 6}}},
    {"meta": {"fast": {"age_sec": 6}, "vehicle": {"age_sec": 0}}},
    {"meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": -1}}},
    {"meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": float("nan")}}},
])
def test_nonheli_inactive_or_unconfirmed_samples_never_produce_vrs(patch):
    current, engine = _state(**patch), _engine()
    assert engine.feed(current, current) + engine.feed(current, current) == []


def test_instrument_values_do_not_recompute_a_vrs_flag():
    current = _state(-12)
    current.flags = {}
    engine = _engine()
    assert engine.feed(current, current) + engine.feed(current, current) == []


@pytest.mark.parametrize("dry_run", [True, False])
def test_full_plugin_pipeline_records_candidates_but_never_pushes_vrs(monkeypatch, dry_run):
    plugin, moment = _runtime(monkeypatch, dry_run=dry_run)
    plugin.state = _state(0, 999)
    for now in (1000, 1001, 1002):
        _evaluate(plugin, moment, _state(-6, now))
    records = _vrs_records(plugin)
    assert any(item["stage"] == "detector_candidate" for item in records)
    reason = "dry_run_enabled" if dry_run else "heli_vrs_dry_run_only"
    assert any(item.get("reason") == reason for item in records)
    assert plugin.pushed_messages == []
    assert all("private-sentinel" not in str(item) for item in records)


def test_direct_dispatcher_denies_vrs_before_prompt_or_llm_even_with_all_switches_enabled(monkeypatch):
    plugin, _ = _runtime(monkeypatch, dry_run=False)
    plugin.cfg.ground_status_real_output_enabled = True
    plugin.cfg.v2_live_verified_real_output_enabled = True
    plugin.cfg.plugin_owned_battle_output_enabled = True
    plugin.cfg.plugin_owned_urgent_output_enabled = True
    plugin.dispatcher.build_prompt = lambda *_: pytest.fail("VRS must not build an output prompt")
    result = plugin.dispatcher.push_event(C.BattleEvent("heli_vrs_risk", level="critical", ts=1000), dry_run=False)
    assert "reason=heli_vrs_dry_run_only" in result
    assert plugin.pushed_messages == []


def test_real_mode_vrs_cannot_occupy_the_slot_or_displace_other_events(monkeypatch):
    plugin, _ = _runtime(monkeypatch, dry_run=False)
    vrs = C.BattleEvent("heli_vrs_risk", ts=1000)
    nearby = C.BattleEvent("enemy_nearby", ts=1000, payload={"domain": "heli"})
    chosen, chain = plugin.arbiter.decide([vrs, nearby], C.IN_FLIGHT, 1000, current_state=_state())
    assert chosen is nearby
    assert any(item.get("reason") == "heli_vrs_dry_run_only" for item in chain)
    assert "heli_vrs_risk" not in plugin.arbiter._last_fired


@pytest.mark.parametrize("change", ["clear", "stale", "dead", "domain", "downgrade"])
def test_buffered_vrs_is_revoked_when_the_condition_or_sample_no_longer_confirms_it(monkeypatch, change):
    plugin, _ = _runtime(monkeypatch)
    plugin.cfg.global_rate_limit_seconds = 2
    plugin.safety.mark_output(critical=False, now=999.5)
    event = C.BattleEvent("heli_vrs_risk", level="critical", ts=1000)
    chosen, _ = plugin.arbiter.decide([event], C.IN_FLIGHT, 1000, current_state=_state(-12))
    assert chosen is None and plugin.arbiter._window_best is event
    current = _state(-12, 1001)
    now = 1001
    if change == "clear":
        current.flags = {}
    elif change == "stale":
        now = 1010
    elif change == "dead":
        current.dead = True
    elif change == "domain":
        current.domain = "air"
    else:
        current.flags = {"vrs_warning": True}
    chosen, chain = plugin.arbiter.decide([], C.IN_FLIGHT, now, current_state=current)
    assert chosen is None and plugin.arbiter._window_best is None
    assert any(item.get("reason") == "heli_vrs_condition_cleared" for item in chain)


def test_switching_to_real_mode_discards_a_dry_run_buffer(monkeypatch):
    plugin, _ = _runtime(monkeypatch)
    plugin.cfg.global_rate_limit_seconds = 2
    plugin.safety.mark_output(critical=False, now=999.5)
    plugin.arbiter.decide([C.BattleEvent("heli_vrs_risk", ts=1000)], C.IN_FLIGHT, 1000, current_state=_state())
    assert plugin.arbiter._window_best is not None
    plugin.cfg.dry_run = False
    chosen, chain = plugin.arbiter.decide([], C.IN_FLIGHT, 1001, current_state=_state(now=1001))
    assert chosen is None and plugin.arbiter._window_best is None
    assert any(item.get("reason") == "heli_vrs_dry_run_only" for item in chain)


@pytest.mark.parametrize(("age", "emits"), [(5.0, True), (5.001, False), (None, False)])
def test_independent_source_age_boundary_is_not_replaced_by_a_fresh_fast_poll(age, emits):
    state = _state(meta={"fast": {"age_sec": 0}, "vehicle": {"age_sec": age}})
    engine = _engine()
    events = engine.feed(state, state) + engine.feed(state, state)
    assert bool(events) is emits


@pytest.mark.parametrize("change", ["clear", "cached_stale"])
def test_plugin_retry_path_cannot_record_an_invalid_old_vrs_event(monkeypatch, change):
    plugin, moment = _runtime(monkeypatch)
    plugin.state = _state(-12, 1000)
    plugin._pending_dispatch_event = C.BattleEvent("heli_vrs_risk", level="critical", ts=1000,
                                                 payload={"domain": "heli"})
    current = _state(0 if change == "clear" else -12, 1001)
    moment[0] = 1001 if change == "clear" else 1010
    previous = plugin.state
    plugin.state = current
    plugin._evaluate(previous, current)
    assert plugin._pending_dispatch_event is None
    records = _vrs_records(plugin)
    assert any(item.get("reason") == "heli_vrs_condition_cleared" for item in records)
    assert all(item.get("stage") != "dispatcher_dry_run" for item in records)
    assert plugin.pushed_messages == []


def test_death_and_same_vehicle_respawn_require_a_new_two_frame_confirmation(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    for now in (1000, 1001):
        _evaluate(plugin, moment, _state(-6, now))
    _evaluate(plugin, moment, _state(-6, 1002, dead=True))
    _evaluate(plugin, moment, _state(-6, 1003, life_index=2))
    assert len([r for r in _vrs_records(plugin) if r.get("stage") == "detector_candidate"]) == 1
    _evaluate(plugin, moment, _state(-6, 1004, life_index=2))
    assert len([r for r in _vrs_records(plugin) if r.get("stage") == "detector_candidate"]) == 2
    assert plugin.pushed_messages == []
