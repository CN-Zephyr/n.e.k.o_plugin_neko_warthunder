"""Ground vehicle facts stay usable, source-aged, and separate from output policy."""

from __future__ import annotations

import asyncio
import copy
import json
import sys

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from test_status_reporting import _plugin_for_action_tests
from wt_processor import TelemetryProcessor
from wt_telemetry import Indicators, VehicleState


def _plugin(monkeypatch, **patch):
    plugin = _plugin_for_action_tests()
    payload = {
        "state": "in_battle", "in_battle": True, "domain": "ground", "timestamp": 1000,
        "vehicle": {"valid": True}, "indicators": {"valid": True},
        "meta": {"fast": {"age_sec": 0.2}, "vehicle": {"age_sec": 0.8}},
        "processed": {"crew_current": 2, "crew_total": 4, "ammo_first_stage": 0,
                      "gun_stabilizer": False, "gear_position": -2,
                      "gunner_state": 2, "driver_state": 3},
        "chat": [{"sender": "private-sentinel", "msg": "private-sentinel"}],
    }
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
        "status": "ready", "sample_age_seconds": 0.8,
        "crew_current": 2, "crew_total": 4, "ammo_first_stage": 0,
        "gun_stabilizer": False, "gear_position": -2, "gunner_state": 2, "driver_state": 3,
        "laser_warning_state": None,
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
    ({"state": "offline"}, "offline"),
    ({"vehicle": {"valid": False}}, "unavailable"),
    ({"meta": {"vehicle": {"age_sec": 7.0}}}, "stale"),
])
def test_ground_facts_are_withheld_when_they_cannot_be_current(monkeypatch, patch, status):
    plugin, _ = _plugin(monkeypatch, **patch)

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == status
    assert all(ground[key] is None for key in ground if key not in {"status", "sample_age_seconds"})


def test_cached_plugin_state_ages_even_when_the_payload_has_not_changed(monkeypatch):
    plugin, moment = _plugin(monkeypatch)
    before = copy.deepcopy(plugin.state.raw)
    moment[0] += 8

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == "stale"
    assert ground["sample_age_seconds"] == 8.8
    assert ground["crew_current"] is None
    assert plugin.state.raw == before


def test_vehicle_age_is_not_replaced_by_a_fresh_fast_poll(monkeypatch):
    plugin, _ = _plugin(monkeypatch, meta={"fast": {"age_sec": 0}, "vehicle": {"age_sec": 6}})

    assert asyncio.run(plugin.dashboard_context())["ground_status"]["status"] == "stale"


def test_missing_and_invalid_facts_remain_unknown_instead_of_zero(monkeypatch):
    plugin, _ = _plugin(monkeypatch, processed={"ammo_first_stage": -1, "crew_current": 5,
                                               "crew_total": 4, "gunner_state": float("nan")})

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == "ready"
    for key in ("ammo_first_stage", "crew_current", "crew_total", "gun_stabilizer", "gunner_state"):
        assert ground[key] is None
    json.dumps(ground, allow_nan=False)


def test_older_payload_without_sample_metadata_keeps_age_unknown(monkeypatch):
    plugin, _ = _plugin(monkeypatch, meta={})

    ground = asyncio.run(plugin.dashboard_context())["ground_status"]

    assert ground["status"] == "ready"
    assert ground["sample_age_seconds"] is None
    assert ground["ammo_first_stage"] == 0


@pytest.mark.parametrize(("raw", "expected"), [(None, None), (0, False), (1, True)])
def test_unavailable_stabilizer_is_not_reported_as_switched_off(raw, expected):
    result = TelemetryProcessor().process(VehicleState(valid=True),
        Indicators(valid=True, army="tank", stabilizer=raw), 1000)

    assert result.gun_stabilizer is expected
