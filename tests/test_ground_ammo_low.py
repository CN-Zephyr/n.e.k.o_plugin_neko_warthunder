"""Ready-rack ammo through processor, parser, detector, arbitration and delivery."""
from __future__ import annotations

import asyncio
import importlib
import sys

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core import contracts as C
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.safety_guard import SafetyGuard
from neko_warthunder.core.scenario import ScenarioResolver
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from test_status_reporting import _plugin_for_action_tests
from wt_processor import TelemetryProcessor
from wt_telemetry import Indicators, VehicleState


def _state(processor, ammo, now=1000, **patch):
    processed = processor.process(VehicleState(valid=True), Indicators(
        valid=True, army="tank", vehicle_type="synthetic-tank", first_stage_ammo=ammo,
        crew_current=4, crew_total=4,
    ), now).to_dict()
    payload = {"state": "in_battle", "in_battle": True, "domain": "ground", "timestamp": now,
               "battle_id": "synthetic-battle", "life_index": 1,
               "vehicle": {"valid": True}, "indicators": {"valid": True}, "processed": processed}
    payload.update(patch)
    return parse_telemetry(payload)


def _engine():
    return DetectorEngine(list(build_condition_detectors()))


def _runtime(monkeypatch, *, enabled=True, dry_run=False):
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = dry_run
    plugin.cfg.ground_status_real_output_enabled = enabled
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


def _evaluate(plugin, moment, processor, ammo, now, **patch):
    moment[0] = now
    current = _state(processor, ammo, now, **patch)
    previous = plugin.state
    plugin.state = current
    plugin._evaluate(previous, current)
    return current


def _ammo_outputs(plugin):
    return [item for item in plugin.pushed_messages if item["metadata"]["event_id"].startswith("ground_ammo_")]


def test_low_requires_two_frames_emits_once_and_rearms_after_resupply():
    processor, engine = TelemetryProcessor(), _engine()
    previous = _state(processor, 12)
    events = []
    for now, ammo in [(1001, 3), (1002, 12), (1003, 12), (1004, 3), (1005, 3),
                      (1006, 3), (1007, 12), (1008, 12), (1009, 2), (1010, 2)]:
        current = _state(processor, ammo, now)
        events.extend(engine.feed(previous, current))
        previous = current
    assert [(item.event_id, item.ts, item.payload) for item in events] == [
        ("ground_ammo_low", 1005, {"domain": "ground", "ammo_first_stage": 3}),
        ("ground_ammo_low", 1010, {"domain": "ground", "ammo_first_stage": 2}),
    ]


@pytest.mark.parametrize("sequence", [
    [0, 0, 0], [-1, 0, 0], [None, 0, 0], [3, 1, 1], [12, -1, 2, 2],
    [12, None, 2, 2], [12, 4, 4],
])
def test_no_low_without_usable_baseline_or_data_layer_threshold(sequence):
    processor, engine = TelemetryProcessor(), _engine()
    previous = C.BattleState()
    events = []
    for now, ammo in enumerate(sequence, start=1000):
        current = _state(processor, ammo, now)
        events.extend(engine.feed(previous, current))
        previous = current
    assert "ground_ammo_low" not in [item.event_id for item in events]


@pytest.mark.parametrize("patch", [
    {"domain": "air"}, {"domain": "heli"}, {"domain": "naval"}, {"domain": ""},
    {"dead": True}, {"replay": True}, {"in_battle": False}, {"state": "offline"},
])
def test_low_stays_out_of_other_modes_and_inactive_lives(patch):
    processor, engine = TelemetryProcessor(), _engine()
    previous = _state(processor, 12)
    events = []
    for now in (1001, 1002, 1003):
        current = _state(processor, 3, now, **patch)
        events.extend(engine.feed(previous, current))
        previous = current
    assert events == []


@pytest.mark.parametrize("count", [None, -1, 0])
def test_malformed_low_flag_without_positive_count_is_not_a_candidate(count):
    current = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="ground",
                           ammo_first_stage=count, flags={"ammo_low": True})
    engine = _engine()
    assert engine.feed(current, current) + engine.feed(current, current) == []


@pytest.mark.parametrize(("dry_run", "enabled"), [(False, False), (True, False), (False, True)])
def test_full_pipeline_ground_gate_and_output_contract(monkeypatch, dry_run, enabled):
    plugin, moment = _runtime(monkeypatch, enabled=enabled, dry_run=dry_run)
    processor = TelemetryProcessor()
    for now, ammo in [(1000, 12), (1001, 3), (1002, 3), (1003, 3)]:
        _evaluate(plugin, moment, processor, ammo, now)
    candidates = [item for item in plugin.timeline.snapshot()["recent_timeline"]
                  if item.get("stage") == "detector_candidate" and item.get("event_id") == "ground_ammo_low"]
    assert len(candidates) == 1
    outputs = _ammo_outputs(plugin)
    assert len(outputs) == int(enabled and not dry_run)
    if outputs:
        output = outputs[0]
        assert output["metadata"]["event_id"] == "ground_ammo_low"
        assert "陆战" in output["metadata"]["domain_prompt_contract"]
        assert "一级待发弹偏少" in output["parts"][0]["text"]
        assert "不推断全车余弹" in output["parts"][0]["text"]
        assert output["metadata"]["interrupt_policy"] == "drop"
    else:
        assert "ground_ammo_low" not in plugin.arbiter._last_fired
    assert "ground_ammo_low" in asyncio.run(plugin.dashboard_context())["output_policy"]["ground_status_gated_events"]


def test_full_pipeline_empty_escalation_and_low_cooldown(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    processor = TelemetryProcessor()
    sequence = [(1000, 12), (1001, 3), (1002, 3), (1003, 0), (1004, 0),
                (1005, 12), (1006, 12), (1007, 3), (1008, 3),
                (1050, 12), (1051, 12), (1052, 3), (1053, 3)]
    for now, ammo in sequence:
        _evaluate(plugin, moment, processor, ammo, now)
    assert [item["metadata"]["event_id"] for item in _ammo_outputs(plugin)] == [
        "ground_ammo_low", "ground_ammo_empty", "ground_ammo_low",
    ]


@pytest.mark.parametrize(("initial", "current_ammo", "current_flag"), [
    ("ground_ammo_low", 12, ""), ("ground_ammo_low", 0, "ammo_empty"),
    ("ground_ammo_empty", 3, "ammo_low"),
])
def test_cleared_ammo_buffer_cannot_displace_new_live_contact(initial, current_ammo, current_flag):
    safety = SafetyGuard(C.WtConfig(dry_run=False, ground_status_real_output_enabled=True,
                                   global_rate_limit_seconds=2))
    arbiter = Arbiter(safety)
    safety.mark_output(critical=False, now=100)
    initial_flag = "ammo_empty" if initial == "ground_ammo_empty" else "ammo_low"
    low = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True,
                       domain="ground", ammo_first_stage=0 if initial_flag == "ammo_empty" else 3,
                       flags={initial_flag: True})
    chosen, _ = arbiter.decide([C.BattleEvent(initial, ts=100)], C.IN_FLIGHT, 100, current_state=low)
    assert chosen is None and arbiter._window_best is not None
    current = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True,
                           domain="ground", ammo_first_stage=current_ammo,
                           flags={current_flag: True} if current_flag else {})
    chosen, chain = arbiter.decide([C.BattleEvent("enemy_nearby", ts=102)], C.IN_FLIGHT, 102, current_state=current)
    assert chosen is not None and chosen.event_id == "enemy_nearby"
    assert any(item["reason"] == "ground_ammo_condition_cleared" for item in chain)
    assert initial not in arbiter._last_fired


def test_failed_delivery_retry_is_cancelled_after_resupply(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    processor = TelemetryProcessor()
    push = plugin.push_message

    def fail_low(**kwargs):
        if kwargs["metadata"]["event_id"] == "ground_ammo_low":
            raise RuntimeError("synthetic failure")
        return push(**kwargs)

    plugin.push_message = fail_low
    for now, ammo in [(1000, 12), (1001, 3), (1002, 3)]:
        _evaluate(plugin, moment, processor, ammo, now)
    assert plugin._pending_dispatch_event.event_id == "ground_ammo_low"
    plugin.push_message = push
    _evaluate(plugin, moment, processor, 12, 1003)
    assert plugin._pending_dispatch_event is None
    assert _ammo_outputs(plugin) == []
    assert "ground_ammo_low" not in plugin.arbiter._last_fired


def test_full_pipeline_cancels_buffer_after_resupply(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    plugin.cfg.global_rate_limit_seconds = 2
    processor = TelemetryProcessor()
    _evaluate(plugin, moment, processor, 12, 1000)
    _evaluate(plugin, moment, processor, 3, 1001)
    plugin.safety.mark_output(critical=False, now=1001)
    _evaluate(plugin, moment, processor, 3, 1002)
    assert plugin.arbiter._window_best.event_id == "ground_ammo_low"
    _evaluate(plugin, moment, processor, 12, 1003)
    assert plugin.arbiter._window_best is None
    assert _ammo_outputs(plugin) == []


def test_service_outage_and_same_vehicle_respawn_cannot_reuse_old_ammo_baseline(monkeypatch):
    server = importlib.import_module("wt_server")
    plugin, moment = _runtime(monkeypatch)

    class Client:
        ammo = 12
        crew = 4
        state_ok = True

        def get_indicators_with_status(self):
            return (True, server.ConnectionState.IN_BATTLE,
                    server.Indicators(valid=True, army="tank", vehicle_type="synthetic-tank",
                                      first_stage_ammo=self.ammo, crew_current=self.crew, crew_total=4,
                                      speed=0 if self.crew <= 1 else 8), server.MapInfo(valid=True))

        def get_state_with_status(self):
            return self.state_ok, server.VehicleState(valid=self.state_ok)

    client = Client()
    service = server.TelemetryService(client)
    service._state = server.ConnectionState.IN_BATTLE
    service._battle_entry_ts = service._life_entry_ts = 100
    service._battle_id = "synthetic-battle"
    service._life_index = 1

    def tick(now, ammo, *, crew=4, healthy=True):
        moment[0] = now
        client.ammo, client.crew, client.state_ok = ammo, crew, healthy
        service._poll_fast()
        previous, current = plugin.state, parse_telemetry(service.get_snapshot())
        plugin.state = current
        plugin._evaluate(previous, current)
        return current

    tick(1000, 12)
    tick(1001, 3)
    outage = tick(1002, 3, healthy=False)
    assert not outage.flag("ammo_low")
    tick(1003, 3)
    assert _ammo_outputs(plugin) == []
    tick(1004, 3)
    assert len(_ammo_outputs(plugin)) == 1
    assert tick(1005, 3, crew=1).dead is True
    respawn = tick(1006, 1)
    assert respawn.life_index == 2 and respawn.dead is False
    assert tick(1007, 1).flag("ammo_low") is False
    assert tick(1008, 1).flag("ammo_low") is False
    tick(1050, 12)
    tick(1051, 3)
    tick(1052, 3)
    assert [item["metadata"]["event_id"] for item in _ammo_outputs(plugin)] == [
        "ground_ammo_low", "ground_ammo_low",
    ]
