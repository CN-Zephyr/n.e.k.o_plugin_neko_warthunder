"""LWS device states, freshness, and cancellation through the delivery pipeline."""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core import contracts as C
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.safety_guard import SafetyGuard
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from test_ground_ammo_low import _runtime
from test_ground_dashboard import _plugin
from wt_processor import TelemetryProcessor
from wt_telemetry import Indicators, VehicleState


def _state(processor, lws, now=1000, **patch):
    processed = processor.process(VehicleState(valid=True), Indicators(
        valid=True, army="tank", vehicle_type="synthetic-tank", lws=lws,
        crew_current=4, crew_total=4, first_stage_ammo=12,
    ), now).to_dict()
    payload = {"state": "in_battle", "in_battle": True, "domain": "ground", "timestamp": now,
               "battle_id": "synthetic-battle", "life_index": 1,
               "vehicle": {"valid": True}, "indicators": {"valid": True}, "processed": processed,
               "meta": {"vehicle": {"age_sec": 0}, "fast": {"age_sec": 0}}}
    payload.update(patch)
    return parse_telemetry(payload)


def _tick(plugin, moment, processor, lws, now, **patch):
    moment[0] = now
    previous, current = plugin.state, _state(processor, lws, now, **patch)
    plugin.state = current
    plugin._evaluate(previous, current)
    return current


def _laser_outputs(plugin):
    return [item for item in plugin.pushed_messages if item["metadata"]["event_id"] == "ground_laser_warning"]


@pytest.mark.parametrize("lws", [-1, 0, 1, 2, 3, -2, None])
def test_processor_parser_and_dashboard_preserve_device_states(monkeypatch, lws):
    processor = TelemetryProcessor()
    current = _state(processor, lws)
    plugin, moment = _runtime(monkeypatch)
    plugin.state = current
    assert current.laser_warning_state == lws
    assert current.flag("laser_warning") is (lws == 1)
    result = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert result["laser_warning_state"] == lws
    assert plugin.pushed_messages == []


@pytest.mark.parametrize("value", [True, "private-sentinel", 0.5, float("nan"), float("inf")])
def test_invalid_lws_values_do_not_become_device_states_or_leak_text(monkeypatch, value):
    plugin, _ = _plugin(monkeypatch, processed={"laser_warning_state": value})
    result = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert result["laser_warning_state"] is None
    assert "private-sentinel" not in json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(("patch", "status"), [
    ({"dead": True}, "dead"), ({"replay": True}, "replay"),
    ({"in_battle": False}, "waiting"), ({"state": "offline"}, "offline"),
    ({"vehicle": {"valid": False}}, "unavailable"),
    ({"meta": {"vehicle": {"age_sec": 6}}}, "stale"),
])
def test_unsafe_or_old_lws_samples_are_hidden(monkeypatch, patch, status):
    plugin, _ = _plugin(monkeypatch, processed={"laser_warning_state": 1}, **patch)
    result = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert result["status"] == status
    assert result["laser_warning_state"] is None


def test_cached_laser_warning_ages_out_without_another_poll(monkeypatch):
    plugin, moment = _plugin(monkeypatch, processed={"laser_warning_state": 1})
    moment[0] += 6
    result = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert result["status"] == "stale" and result["laser_warning_state"] is None


def test_laser_only_emits_for_state_one_and_rearms_after_two_clear_frames():
    engine = DetectorEngine(list(build_condition_detectors()))
    processor = TelemetryProcessor()
    previous = _state(processor, -1)
    events = []
    for now, value in enumerate([0, 2, 3, 1, 1, 0, 0, 1], 1001):
        current = _state(processor, value, now)
        events.extend(engine.feed(previous, current))
        previous = current
    assert [(item.event_id, item.level, item.ts) for item in events] == [
        ("ground_laser_warning", "critical", 1004), ("ground_laser_warning", "critical", 1008),
    ]


@pytest.mark.parametrize("dry_run", [False, True])
def test_existing_laser_delivery_policy_and_ground_contract_are_preserved(monkeypatch, dry_run):
    plugin, moment = _runtime(monkeypatch, enabled=False, dry_run=dry_run)
    processor = TelemetryProcessor()
    _tick(plugin, moment, processor, 0, 1000)
    _tick(plugin, moment, processor, 1, 1001)
    _tick(plugin, moment, processor, 1, 1002)
    outputs = _laser_outputs(plugin)
    assert len(outputs) == int(not dry_run)
    if outputs:
        assert "陆战" in outputs[0]["metadata"]["domain_prompt_contract"]
        assert "可能被测距或锁定" in outputs[0]["parts"][0]["text"]
        assert outputs[0]["metadata"]["interrupt_policy"] == "drop"
    assert plugin.cfg.ground_status_real_output_enabled is False


@pytest.mark.parametrize("cleared", [-1, 0, 2, 3, None])
def test_cleared_laser_buffer_does_not_displace_live_contact(monkeypatch, cleared):
    plugin, moment = _runtime(monkeypatch, enabled=False)
    processor = TelemetryProcessor()
    _tick(plugin, moment, processor, 0, 1000)
    plugin.cfg.global_rate_limit_seconds = 2
    plugin.safety.mark_output(critical=False, now=1000)
    _tick(plugin, moment, processor, 1, 1001)
    assert plugin.arbiter._window_best.event_id == "ground_laser_warning"
    _tick(plugin, moment, processor, cleared, 1002,
          proximity={"events": [{"id": 1, "kind": "enter", "category": "enemy_ground", "distance_m": 300}]})
    assert _laser_outputs(plugin) == []
    assert plugin.pushed_messages[-1]["metadata"]["event_id"] == "enemy_nearby"
    assert "ground_laser_warning" not in plugin.arbiter._last_fired
    assert any(row.get("reason") == "ground_laser_condition_cleared"
               for row in plugin.timeline.snapshot()["recent_activity"])


def test_failed_laser_delivery_is_not_retried_after_clear(monkeypatch):
    plugin, moment = _runtime(monkeypatch, enabled=False)
    processor = TelemetryProcessor()
    _tick(plugin, moment, processor, 0, 1000)
    push = plugin.push_message

    def fail(**kwargs):
        raise RuntimeError("synthetic delivery failure")

    plugin.push_message = fail
    _tick(plugin, moment, processor, 1, 1001)
    assert plugin._pending_dispatch_event.event_id == "ground_laser_warning"
    plugin.push_message = push
    _tick(plugin, moment, processor, 0, 1002)
    assert plugin._pending_dispatch_event is None
    assert _laser_outputs(plugin) == []


@pytest.mark.parametrize("lws", [-1, 0, 2, 3])
def test_explicit_non_alarm_enum_overrules_contradictory_flag(lws):
    state = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, domain="ground",
                          vehicle_valid=True, flags={"laser_warning": True}, laser_warning_state=lws)
    chosen, _ = Arbiter(SafetyGuard(C.WtConfig())).decide(
        [C.BattleEvent("ground_laser_warning")], C.IN_FLIGHT, 100, current_state=state)
    assert chosen is None


def test_older_flag_only_data_layer_remains_compatible():
    state = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, domain="ground",
                          vehicle_valid=True, flags={"laser_warning": True})
    chosen, _ = Arbiter(SafetyGuard(C.WtConfig())).decide(
        [C.BattleEvent("ground_laser_warning")], C.IN_FLIGHT, 100, current_state=state)
    assert chosen is not None and chosen.event_id == "ground_laser_warning"


def test_service_outage_clears_pending_laser_and_recovery_cannot_replay_it(monkeypatch):
    server = importlib.import_module("wt_server")
    plugin, moment = _runtime(monkeypatch, enabled=False)

    class Client:
        lws = 0
        healthy = True

        def get_indicators_with_status(self):
            return (True, server.ConnectionState.IN_BATTLE,
                    server.Indicators(valid=True, army="tank", vehicle_type="synthetic-tank", lws=self.lws,
                                      crew_current=4, crew_total=4), server.MapInfo(valid=True))

        def get_state_with_status(self):
            return self.healthy, server.VehicleState(valid=self.healthy)

    client = Client()
    service = server.TelemetryService(client)
    service._state = server.ConnectionState.IN_BATTLE
    service._battle_entry_ts = service._life_entry_ts = 100
    service._battle_id, service._life_index = "synthetic-battle", 1
    for now, lws, healthy in [(1000, 0, True), (1001, 1, True), (1002, 1, False), (1003, 0, True)]:
        moment[0] = now
        client.lws, client.healthy = lws, healthy
        if now == 1001:
            plugin.cfg.global_rate_limit_seconds = 2
            plugin.safety.mark_output(critical=False, now=1000)
        service._poll_fast()
        previous, current = plugin.state, parse_telemetry(service.get_snapshot())
        plugin.state = current
        plugin._evaluate(previous, current)
        if now == 1001:
            assert plugin.arbiter._window_best.event_id == "ground_laser_warning"
        if now == 1002:
            assert not current.flag("laser_warning")
            assert plugin.arbiter._window_best is None
    assert _laser_outputs(plugin) == []
