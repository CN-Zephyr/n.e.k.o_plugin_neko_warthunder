"""Ground vehicle facts stay usable, source-aged, and separate from output policy."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from dataclasses import asdict

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from test_status_reporting import _plugin_for_action_tests
from wt_processor import TelemetryProcessor
from wt_telemetry import Indicators, VehicleState, WarThunderClient


def _tank_indicators(processed):
    processed = processed if isinstance(processed, dict) else {}
    gear = processed.get("gear_position")
    stabilizer = processed.get("gun_stabilizer")
    return {"valid": True, "army": "tank", "crew_current": processed.get("crew_current"),
            "crew_total": processed.get("crew_total"), "first_stage_ammo": processed.get("ammo_first_stage"),
            "stabilizer": int(stabilizer) if isinstance(stabilizer, bool) else stabilizer,
            "gear": gear, "gear_neutral": 0 if gear is not None else None,
            "gunner_state": processed.get("gunner_state"), "driver_state": processed.get("driver_state"),
            "lws": processed.get("laser_warning_state")}


def _plugin(monkeypatch, **patch):
    plugin = _plugin_for_action_tests()
    payload = {
        "state": "in_battle", "in_battle": True, "domain": "ground", "timestamp": 1000,
        "vehicle": {"valid": True},
        "meta": {"fast": {"age_sec": 0.2}, "vehicle": {"age_sec": 0.8}},
        "processed": {"crew_current": 2, "crew_total": 4, "ammo_first_stage": 0,
                      "gun_stabilizer": False, "gear_position": -2,
                      "gunner_state": 2, "driver_state": 3},
        "chat": [{"sender": "private-sentinel", "msg": "private-sentinel"}],
    }
    payload["indicators"] = _tank_indicators(patch.get("processed", payload["processed"]))
    payload.update(patch)
    plugin.state = parse_telemetry(payload)
    module = sys.modules[type(plugin).__module__]
    moment = [1000.2]
    monkeypatch.setattr(module.time, "time", lambda: moment[0])
    return plugin, moment


def test_dashboard_exposes_numeric_ground_facts_without_raw_text(monkeypatch):
    plugin, _ = _plugin(monkeypatch)

    result = asyncio.run(plugin.dashboard_context())

    assert result["ground_status"] == {
        "status": "ready", "sample_age_seconds": 0.2, "sample_timestamp": 1000,
        "crew_current": 2, "crew_total": 4, "ammo_first_stage": 0,
        "gun_stabilizer": False, "gear_position": -2, "gunner_state": 2, "driver_state": 3,
        "laser_warning_state": None, "track_broken": None, "h_drive_dead": None,
        "breach_dead": None, "barrel_dead": None, "speed_kmh": None, "engine_rpm": None,
    }
    assert "private-sentinel" not in json.dumps(result["ground_status"])
    assert plugin.pushed_messages == []
    assert plugin.cfg.dry_run is True
    assert plugin.cfg.ground_status_real_output_enabled is False


@pytest.mark.parametrize("domain", ["air", "heli", "naval", "unknown", "menu"])
def test_ground_facts_are_not_projected_into_other_domains(monkeypatch, domain):
    plugin, _ = _plugin(monkeypatch, domain=domain)

    assert asyncio.run(plugin.dashboard_context())["ground_status"] is None


@pytest.mark.parametrize(("patch", "status"), [
    ({"dead": True}, "dead"),
    ({"replay": True}, "replay"),
    ({"in_battle": False}, "waiting"),
    ({"state": "not_in_battle"}, "waiting"),
    ({"state": "offline"}, "offline"),
    ({"indicators": {"army": "tank", "valid": False, "raw": {"track_broken": 1}}}, "unavailable"),
    ({"indicators": {"army": "tank", "valid": 1, "raw": {"track_broken": 1}}}, "unavailable"),
    ({"indicators": {"army": "air", "valid": True, "raw": {"track_broken": 1}}}, "unavailable"),
    ({"meta": {"fast": {"age_sec": 7.0}}}, "stale"),
    ({"timestamp": 1001}, "unavailable"),
    ({"timestamp": 0}, "unavailable"),
])
def test_ground_facts_are_withheld_when_they_cannot_be_current(monkeypatch, patch, status):
    args = {"indicators": {"army": "tank", "valid": True, "raw": {"track_broken": 1}}, **patch}
    plugin, _ = _plugin(monkeypatch, **args)

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == status
    assert all(ground[key] is None for key in ground if key not in {"status", "sample_age_seconds", "sample_timestamp"})


def test_cached_plugin_state_ages_even_when_the_payload_has_not_changed(monkeypatch):
    plugin, moment = _plugin(monkeypatch)
    before = copy.deepcopy(plugin.state.raw)
    moment[0] += 8

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == "stale"
    assert ground["sample_age_seconds"] == 8.2
    assert ground["crew_current"] is None
    assert plugin.state.raw == before


def test_valid_ground_indicators_win_over_invalid_state_and_cached_processed(monkeypatch):
    indicators = WarThunderClient()._parse_indicators({
        "valid": True, "army": "tank", "type": "tankModels/ussr_bmpt_72", "crew_current": 3,
        "crew_total": 3, "first_stage_ammo": -1, "stabilizer": 1, "gear": 2, "gear_neutral": 1, "lws": 0,
        "track_broken": 1, "h_drive_dead": 1.0, "breach_dead": 1, "barrel_dead": 1,
    })
    plugin, _ = _plugin(monkeypatch, vehicle={"valid": False}, indicators=asdict(indicators),
                        meta={"fast": {"age_sec": 0.2}, "vehicle": {"age_sec": 6}})
    result = asyncio.run(plugin.dashboard_context())
    ground = result["ground_status"]
    assert ground["status"] == "ready" and ground["sample_age_seconds"] == 0.2
    assert ground["crew_current"] == ground["crew_total"] == 3
    assert ground["gear_position"] == 1 and ground["gun_stabilizer"] is True
    assert ground["ammo_first_stage"] is None and ground["laser_warning_state"] == 0
    damage_keys = {"track_broken", "h_drive_dead", "breach_dead", "barrel_dead"}
    assert all(ground[key] is True for key in damage_keys)
    assert damage_keys.isdisjoint(fact["id"] for fact in result["trusted_facts"]["facts"])
    assert damage_keys.isdisjoint(plugin.state.flags)
    assert result["ground_ammo_explanation"] == {"status": "count_unknown"}
    assert plugin.pushed_messages == []


def test_sparse_or_unrecognized_module_values_do_not_latch_damage(monkeypatch):
    indicators = {"valid": True, "army": "tank", "raw": {"track_broken": 1}}
    plugin, _ = _plugin(monkeypatch, indicators=indicators)
    assert asyncio.run(plugin.dashboard_context())["ground_status"]["track_broken"] is True

    payload = {**plugin.state.raw, "life_index": 2, "indicators": {**indicators, "raw": {
        "h_drive_dead": 0, "breach_dead": "1", "barrel_dead": True, "engine_dead": 1,
    }}}
    plugin.state = parse_telemetry(payload)
    ground = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert ground["track_broken"] is None and ground["h_drive_dead"] is False
    assert ground["breach_dead"] is None and ground["barrel_dead"] is None
    assert "engine_dead" not in ground


def test_ground_speed_and_rpm_are_panel_only_and_follow_source_age(monkeypatch):
    sample = {"status": "ready", "count": 1, "sample_timestamp": 1000, "age_sec": 0.2,
              "battle_id": "synthetic", "life_index": 1}
    plugin, clock = _plugin(
        monkeypatch, vehicle={"valid": False}, battle_id="synthetic", life_index=1,
        indicators={"army": "tank", "valid": True, "speed": -8.5, "rpm": 1200},
        meta={"fast": {"age_sec": 0.2}, "ground_indicators": sample},
    )
    payload = asyncio.run(plugin.dashboard_context())
    ground = payload["ground_status"]
    assert ground["status"] == "ready" and ground["sample_timestamp"] == 1000
    assert ground["speed_kmh"] == -8.5 and ground["engine_rpm"] == 1200
    assert {"speed_kmh", "engine_rpm"}.isdisjoint(fact["id"] for fact in payload["trusted_facts"]["facts"])

    sample["status"] = "held"
    clock[0] = 1001
    payload = asyncio.run(plugin.dashboard_context())
    assert payload["ground_status"]["status"] == "held"
    assert payload["ground_status"]["speed_kmh"] == -8.5
    assert payload["trusted_facts"]["sources"][0]["status"] == "held"

    clock[0] = 1005
    ground = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert ground["status"] == "stale" and ground["sample_age_seconds"] == 5
    assert ground["speed_kmh"] is ground["engine_rpm"] is None
    assert plugin.pushed_messages == []


@pytest.mark.parametrize(("speed", "rpm", "shown_speed", "shown_rpm"), [
    (0, 0, 0, 0), ("8", -1, None, None), (float("inf"), True, None, None),
])
def test_ground_motion_facts_preserve_zero_and_reject_invalid_readings(monkeypatch, speed, rpm, shown_speed, shown_rpm):
    plugin, _ = _plugin(monkeypatch, indicators={"army": "tank", "valid": True, "speed": speed, "rpm": rpm})
    ground = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert ground["speed_kmh"] == shown_speed and ground["engine_rpm"] == shown_rpm
    json.dumps(ground, allow_nan=False)


def test_missing_and_invalid_facts_remain_unknown_instead_of_zero(monkeypatch):
    plugin, _ = _plugin(monkeypatch, processed={"ammo_first_stage": -1, "crew_current": 5,
                                               "crew_total": 4, "gunner_state": float("nan")})

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == "ready"
    for key in ("ammo_first_stage", "crew_current", "crew_total", "gun_stabilizer", "gunner_state"):
        assert ground[key] is None
    json.dumps(ground, allow_nan=False)


def test_older_payload_without_fast_metadata_uses_tank_snapshot_time(monkeypatch):
    plugin, _ = _plugin(monkeypatch, meta={})

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == "ready"
    assert ground["sample_age_seconds"] == 0.2
    assert ground["ammo_first_stage"] == 0


@pytest.mark.parametrize(("raw", "expected"), [(None, None), (0, False), (1, True)])
def test_unavailable_stabilizer_is_not_reported_as_switched_off(raw, expected):
    result = TelemetryProcessor().process(VehicleState(valid=True),
        Indicators(valid=True, army="tank", stabilizer=raw), 1000)

    assert result.gun_stabilizer is expected
