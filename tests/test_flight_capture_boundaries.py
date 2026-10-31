"""Capture-derived readiness, explicit state oil source, and burn estimate regressions."""
from __future__ import annotations

import asyncio
import copy
import json
import sys

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.contracts import SPAWNING, BattleState
from neko_warthunder.core.scenario import ScenarioResolver
from neko_warthunder.detectors.discrete.lifecycle import SpawnDetector
from test_data_layer_proximity import _indicators, _vehicle
from test_status_reporting import _plugin_for_action_tests
from wt_processor import TelemetryProcessor


def _payload(model="unlisted-real-model", now=1000, **updates):
    data = {"state": "in_battle", "in_battle": True, "domain": "air", "timestamp": now,
            "battle_id": "synthetic-battle", "life_index": 1,
            "vehicle": {"valid": True, "engines": [{"index": 1, "oil_temp_c": 0},
                                                     {"index": 2, "oil_temp_c": 96}],
                        "raw": {"oil temp 1, C": 0, "oil temp 2, C": 96, "private": "secret-sentinel"}},
            "indicators": {"valid": True, "army": "air", "vehicle_type": model},
            "meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": 0.1}},
            "processed": {"fuel_fraction": 0.4, "oil_temp_c": 150, "profile_matched": False}}
    data.update(updates)
    return data


def _plugin(monkeypatch):
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = True
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=100)
    plugin.dispatcher = NekoDispatcher(plugin, timeline=plugin.timeline)
    moment = [1000.0]
    monkeypatch.setattr(sys.modules[type(plugin).__module__].time, "time", lambda: moment[0])
    return plugin, moment


def test_placeholder_unknown_then_real_flows_through_full_evaluator_and_dispatch(monkeypatch):
    plugin, moment = _plugin(monkeypatch)
    previous = parse_telemetry(_payload(now=999, in_battle=False, state="not_in_battle"))
    for now, model, domain, valid in [(1000, "dummy_plane", "air", True),
                                      (1008, "dummy_plane", "air", True),
                                      (1009, None, "unknown", False),
                                      (1010, "unlisted-real-model", "air", True)]:
        moment[0] = now
        raw = _payload(model, now, domain=domain)
        raw["vehicle"]["valid"] = valid
        current = parse_telemetry(raw)
        plugin._evaluate(previous, current)
        assert current.scenario == SPAWNING
        previous = current
    assert plugin.resolver.seconds_since_spawn(1010) == 0
    candidates = [r for r in plugin.timeline.snapshot()["recent_timeline"]
                  if r.get("stage") == "detector_candidate" and r.get("event_id") == "spawn"]
    assert len(candidates) == 1
    delivered = [r for r in plugin.timeline.snapshot()["recent_timeline"]
                 if r.get("stage") == "dispatcher_dry_run"]
    assert delivered[-1]["event_id"] == "spawn"
    assert plugin.pushed_messages == []
    # Same-life HTTP outage and repeated placeholder cannot reannounce birth.
    for current in [BattleState(), parse_telemetry(_payload(now=1011)),
                    parse_telemetry(_payload("dummy_plane", 1012)), parse_telemetry(_payload(now=1013))]:
        moment[0] = current.timestamp or 1011
        plugin._evaluate(previous, current)
        previous = current
    assert len([e for e in plugin.timeline.snapshot()["recent_timeline"]
                if e.get("stage") == "detector_candidate" and e.get("event_id") == "spawn"]) == 1


def test_confirmed_respawn_survives_placeholder_and_unknown():
    detector = SpawnDetector()
    first = parse_telemetry(_payload())
    detector.feed(first, first)
    dead = parse_telemetry(_payload(dead=True))
    dummy = parse_telemetry(_payload("dummy_plane", life_index=2))
    unknown = parse_telemetry(_payload(None, domain="unknown", life_index=2))
    alive = parse_telemetry(_payload(life_index=2))
    assert detector.feed(dead, dummy) is None
    assert detector.feed(dummy, unknown) is None
    event = detector.feed(unknown, alive)
    assert event is not None and event.payload["respawn"] is True
    assert detector.feed(alive, alive) is None


def test_cancelled_placeholder_does_not_consume_next_entry():
    detector = SpawnDetector()
    waiting = parse_telemetry(_payload(in_battle=False))
    dummy = parse_telemetry(_payload("dummy_plane"))
    assert detector.feed(waiting, dummy) is None
    assert detector.feed(dummy, waiting) is None
    assert detector.feed(waiting, parse_telemetry(_payload())).event_id == "spawn"


def _fuel(processor, mass, now):
    return processor.process(_vehicle(fuel_kg=mass, fuel_full_kg=500),
                             _indicators(vehicle_type="unlisted-fuel-model"), now)


def test_integer_kg_updates_remain_valid_then_hold_expires_without_losing_low_fuel():
    processor = TelemetryProcessor()
    processor.profiles["_default"].update(fuel_low_fraction=0.3, fuel_critical_fraction=0.1)
    _fuel(processor, 100, 1000)
    ready = _fuel(processor, 99, 1014)
    assert ready.fuel_estimate_status == "ready"
    assert ready.fuel_estimate_max_age_sec == 56
    normal = _fuel(processor, 99, 1028)
    assert normal.fuel_remaining_sec is not None
    stale = _fuel(processor, 99, 1088)
    assert stale.fuel_estimate_status == "stale"
    assert stale.fuel_remaining_sec is stale.fuel_burn_rate_kgs is None
    assert stale.fuel_fraction == 0.198 and stale.flags["fuel_low"]
    assert "秒" not in next(a.message for a in stale.alerts if a.code == "fuel_low")
    # Resume must not average across a pause; the following change rewarms it.
    assert _fuel(processor, 98, 1089).fuel_estimate_status == "waiting"
    assert _fuel(processor, 97, 1103).fuel_estimate_status == "ready"


@pytest.mark.parametrize("invalid", [None, True, "98", float("nan"), float("inf"), -1])
def test_invalid_fuel_clears_estimate_history(invalid):
    processor = TelemetryProcessor()
    _fuel(processor, 100, 1000)
    _fuel(processor, 99, 1014)
    assert _fuel(processor, invalid, 1015).fuel_estimate_status == "unavailable"
    assert _fuel(processor, 98, 1016).fuel_estimate_status == "waiting"


def test_refuel_reset_and_clock_rollback_do_not_reuse_old_burn():
    processor = TelemetryProcessor()
    _fuel(processor, 100, 1000)
    _fuel(processor, 99, 1014)
    assert _fuel(processor, 200, 1015).fuel_estimate_status == "waiting"
    assert _fuel(processor, 199, 1029).fuel_estimate_status == "ready"
    assert _fuel(processor, 199, 900).fuel_estimate_status == "waiting"
    processor.reset()
    assert _fuel(processor, 198, 1100).fuel_estimate_status == "waiting"
    assert _fuel(processor, 197, 1300).fuel_estimate_status == "waiting"
    assert _fuel(processor, 196, 1314).fuel_estimate_status == "ready"


def test_oil_source_is_separate_from_alert_input_and_summary_and_reads_are_pure(monkeypatch):
    plugin, _ = _plugin(monkeypatch)
    plugin.state = parse_telemetry(_payload())
    original = copy.deepcopy(plugin.state.raw)
    first = asyncio.run(plugin.dashboard_context())
    second = asyncio.run(plugin.dashboard_context())
    oil = first["flight_diagnostics"]["oil"]
    assert oil["max_c"] == 96 and oil["observed_channels"] == 2
    assert oil["source"] == "state_oil_temp_C" and oil["life_binding"] == "unverified"
    assert first["flight_diagnostics"] == second["flight_diagnostics"]
    assert first["trusted_facts"] == second["trusted_facts"]
    assert plugin.state.oil_temp_c == 150 and plugin.state.raw == original
    assert "secret-sentinel" not in json.dumps(first["flight_diagnostics"])
    assert len(json.dumps(first["flight_diagnostics"], separators=(",", ":")).encode()) <= 512
    assert plugin.pushed_messages == []
    assert plugin.timeline.snapshot()["recent_timeline"] == []


@pytest.mark.parametrize("bad", [True, "96", float("nan"), float("inf"), -273.15])
def test_oil_channel_rejects_coercion_and_placeholder(monkeypatch, bad):
    plugin, _ = _plugin(monkeypatch)
    raw = _payload()
    raw["vehicle"]["engines"][1]["oil_temp_c"] = bad
    raw["vehicle"]["raw"]["oil temp 2, C"] = bad
    plugin.state = parse_telemetry(raw)
    oil = asyncio.run(plugin.dashboard_context())["flight_diagnostics"]["oil"]
    assert oil["status"] == "partial" and oil["max_c"] == 0
    assert oil["observed_channels"] == oil["unavailable_channels"] == 1


@pytest.mark.parametrize("case", ["duplicate", "conflict", "missing_raw", "no_engines", "too_many"])
def test_ambiguous_or_missing_channels_are_not_filled_from_processed(monkeypatch, case):
    plugin, _ = _plugin(monkeypatch)
    raw = _payload()
    vehicle = raw["vehicle"]
    if case == "duplicate":
        vehicle["engines"] = [vehicle["engines"][1]] * 2
    elif case == "conflict":
        vehicle["raw"]["oil temp 1, C"] = 12
        vehicle["raw"]["oil temp 2, C"] = 12
    elif case == "missing_raw":
        vehicle.pop("raw")
    elif case == "no_engines":
        vehicle["engines"] = []
    else:
        vehicle["engines"] *= 5
    plugin.state = parse_telemetry(raw)
    oil = asyncio.run(plugin.dashboard_context())["flight_diagnostics"]["oil"]
    assert oil["max_c"] is None and oil["status"] == "unavailable"


@pytest.mark.parametrize("patch", [{"dead": True}, {"replay": True}, {"in_battle": False},
                                   {"state": "offline"}, {"meta": {}},
                                   {"meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": 7}}},
                                   {"timestamp": 1001}])
def test_inactive_stale_unknown_or_future_sources_hide_oil(monkeypatch, patch):
    plugin, _ = _plugin(monkeypatch)
    plugin.state = parse_telemetry(_payload(**patch))
    result = asyncio.run(plugin.dashboard_context())["flight_diagnostics"]
    assert result["oil"]["max_c"] is None
    assert result["fuel_estimate"]["remaining_sec"] is None


@pytest.mark.parametrize("domain", ["ground", "heli", "naval", "unknown", "menu"])
def test_flight_diagnostics_do_not_leak_to_other_domains(monkeypatch, domain):
    plugin, _ = _plugin(monkeypatch)
    plugin.state = parse_telemetry(_payload(domain=domain))
    assert asyncio.run(plugin.dashboard_context())["flight_diagnostics"] is None


def test_cached_fuel_estimate_expires_independently_of_vehicle_age(monkeypatch):
    plugin, moment = _plugin(monkeypatch)
    raw = _payload()
    raw["processed"].update(fuel_estimate_status="ready", fuel_estimate_age_sec=44,
                            fuel_estimate_max_age_sec=45, fuel_burn_rate_kgs=1, fuel_remaining_sec=100)
    plugin.state = parse_telemetry(raw)
    assert asyncio.run(plugin.dashboard_context())["flight_diagnostics"]["fuel_estimate"]["remaining_sec"] == 100
    moment[0] += 2
    estimate = asyncio.run(plugin.dashboard_context())["flight_diagnostics"]["fuel_estimate"]
    assert estimate["status"] == "stale" and estimate["remaining_sec"] is None
