"""Helicopter instruments remain source-aged, read-only facts across the UI seam."""

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
        "state": "in_battle", "in_battle": True, "domain": "heli", "timestamp": 1000,
        "vehicle": {"valid": True}, "indicators": {"valid": True},
        "meta": {"fast": {"age_sec": 0.2}, "vehicle": {"age_sec": 0.8}},
        "processed": {"rotor_rpm": 396.25, "radio_altitude_m": 42.5, "vario_ms": -2.5},
        "chat": [{"sender": "private-sentinel", "msg": "private-sentinel"}],
    }
    payload.update(patch)
    plugin.state = parse_telemetry(payload)
    module = sys.modules[type(plugin).__module__]
    moment = [1000.2]
    monkeypatch.setattr(module.time, "time", lambda: moment[0])
    return plugin, moment


def test_data_layer_to_dashboard_preserves_instruments_without_side_effects(monkeypatch):
    processed = TelemetryProcessor().process(
        VehicleState(valid=True),
        Indicators(valid=True, army="air", is_helicopter=True, prop_rpm=396.25,
                   radio_altitude=42.5, vario_ms=-2.5), 1000,
    ).to_dict()
    plugin, _ = _plugin(monkeypatch, processed=processed)
    before = copy.deepcopy(plugin.state.raw)

    result = asyncio.run(plugin.dashboard_context())

    assert result["helicopter_status"] == {
        "status": "ready", "sample_age_seconds": 0.8,
        "rotor_rpm": 396.25, "radio_altitude_m": 42.5, "vario_ms": -2.5,
    }
    assert result["ground_status"] is None
    assert "private-sentinel" not in json.dumps(result["helicopter_status"])
    assert plugin.state.raw == before
    assert plugin.pushed_messages == plugin.config_updates == []
    assert not plugin._runtime_state_path.exists()


@pytest.mark.parametrize("domain", ["air", "ground", "naval", "unknown", "menu"])
def test_helicopter_card_does_not_leak_into_other_domains(monkeypatch, domain):
    plugin, _ = _plugin(monkeypatch, domain=domain)

    assert asyncio.run(plugin.dashboard_context())["helicopter_status"] is None


@pytest.mark.parametrize(("patch", "status"), [
    ({"dead": True}, "dead"),
    ({"replay": True}, "replay"),
    ({"in_battle": False}, "waiting"),
    ({"state": "offline"}, "offline"),
    ({"vehicle": {"valid": False}}, "unavailable"),
    ({"meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": 5.001}}}, "stale"),
    ({"meta": {"fast": {"age_sec": 6}, "vehicle": {"age_sec": 0}}}, "stale"),
])
def test_unavailable_helicopter_data_is_withheld(monkeypatch, patch, status):
    plugin, _ = _plugin(monkeypatch, **patch)

    facts = asyncio.run(plugin.dashboard_context())["helicopter_status"]

    assert facts["status"] == status
    assert [facts[key] for key in ("rotor_rpm", "radio_altitude_m", "vario_ms")] == [None] * 3


def test_cached_context_continues_aging_and_new_sample_recovers(monkeypatch):
    plugin, moment = _plugin(monkeypatch)
    before = copy.deepcopy(plugin.state.raw)
    moment[0] += 8
    stale = asyncio.run(plugin.dashboard_context())["helicopter_status"]
    assert stale["status"] == "stale"
    assert stale["sample_age_seconds"] == 8.8
    assert stale["rotor_rpm"] is None
    assert plugin.state.raw == before

    refreshed = copy.deepcopy(before)
    refreshed["timestamp"] = moment[0]
    refreshed["meta"]["vehicle"]["age_sec"] = 0.1
    refreshed["processed"]["rotor_rpm"] = 400
    plugin.state = parse_telemetry(refreshed)
    facts = asyncio.run(plugin.dashboard_context())["helicopter_status"]
    assert facts["status"] == "ready"
    assert facts["rotor_rpm"] == 400


@pytest.mark.parametrize("value", [None, True, "invalid", float("nan"), float("inf")])
def test_missing_or_nonfinite_instruments_remain_unknown(monkeypatch, value):
    plugin, _ = _plugin(monkeypatch, processed={
        "rotor_rpm": value, "radio_altitude_m": value, "vario_ms": value,
    })

    facts = asyncio.run(plugin.dashboard_context())["helicopter_status"]

    assert facts["status"] == "ready"
    assert [facts[key] for key in ("rotor_rpm", "radio_altitude_m", "vario_ms")] == [None] * 3
    json.dumps(facts, allow_nan=False)


@pytest.mark.parametrize("vario", [-3.25, 0, 2.5])
def test_negative_rpm_agl_are_unknown_but_vario_keeps_its_sign(monkeypatch, vario):
    plugin, _ = _plugin(monkeypatch, processed={
        "rotor_rpm": -1, "radio_altitude_m": -1, "vario_ms": vario,
    })

    facts = asyncio.run(plugin.dashboard_context())["helicopter_status"]

    assert facts["rotor_rpm"] is None
    assert facts["radio_altitude_m"] is None
    assert facts["vario_ms"] == vario


def test_zero_instruments_and_legacy_unknown_age_are_preserved(monkeypatch):
    plugin, _ = _plugin(monkeypatch, meta={}, processed={
        "rotor_rpm": 0, "radio_altitude_m": 0, "vario_ms": 0,
    })

    assert asyncio.run(plugin.dashboard_context())["helicopter_status"] == {
        "status": "ready", "sample_age_seconds": None,
        "rotor_rpm": 0, "radio_altitude_m": 0, "vario_ms": 0,
    }


def test_instrument_reads_do_not_create_events_or_change_output_policy(monkeypatch):
    plugin, _ = _plugin(monkeypatch, processed={
        "rotor_rpm": 50, "radio_altitude_m": 2, "vario_ms": -12,
        "flags": {"vrs_warning": True, "vrs_critical": True},
    })
    for _ in range(4):
        result = asyncio.run(plugin.dashboard_context())
        assert result["helicopter_status"]["rotor_rpm"] == 50
    assert plugin.cfg.dry_run is True
    assert plugin.pushed_messages == plugin.config_updates == []
