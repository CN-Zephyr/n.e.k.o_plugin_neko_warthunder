"""Trusted summaries traverse the actual dashboard seam without advancing the runtime."""
from __future__ import annotations

import asyncio
import copy
import json

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from test_ground_dashboard import _plugin as ground_plugin
from test_helicopter_dashboard import _plugin as heli_plugin
from test_naval_dashboard import _plugin as naval_plugin


def summary(plugin):
    return asyncio.run(plugin.dashboard_context())["trusted_facts"]


def make_plugin(monkeypatch, domain):
    if domain == "naval":
        return naval_plugin(monkeypatch)
    if domain == "heli":
        return heli_plugin(monkeypatch)
    if domain == "ground":
        return ground_plugin(monkeypatch)
    return ground_plugin(monkeypatch, domain="air", processed={"ias_kmh": 200, "altitude_m": 1200,
                         "radio_altitude_m": 50, "fuel_fraction": 0.5}, vehicle={"valid": True, "mach": 0.2})


@pytest.mark.parametrize("domain", ["air", "ground", "heli", "naval"])
def test_real_dashboard_reuses_domain_facts_without_mutation(monkeypatch, domain):
    plugin, _ = make_plugin(monkeypatch, domain)
    before = copy.deepcopy(plugin.state)
    timeline = copy.deepcopy(plugin.timeline.snapshot())
    config = copy.deepcopy(plugin.cfg.to_dict())
    card = summary(plugin)
    assert card["domain"] == domain and card["readonly"] is True
    assert card["version"] == 1
    assert 1 <= len(card["facts"]) <= 5 and len(card["sources"]) == 1
    assert any(f["status"] == "available" for f in card["facts"])
    assert card["sources"][0]["life_binding"] == ("sample" if domain == "naval" else "unverified")
    assert card["output"] == {"mode": "dry_run", "ground_status_enabled": False, "v2_enabled": False,
                              "heli_vrs_enabled": False, "naval_contacts_enabled": False}
    for _ in range(4):
        assert summary(plugin) == card
    assert plugin.state == before
    assert plugin.timeline.snapshot() == timeline
    assert plugin.cfg.to_dict() == config
    assert plugin.pushed_messages == plugin.config_updates == []
    assert not plugin._runtime_state_path.exists()


@pytest.mark.parametrize("domain", ["air", "ground", "heli", "naval"])
@pytest.mark.parametrize("state,expected", [("offline", "offline"), ("replay", "replay"),
                                            ("dead", "dead"), ("waiting", "waiting")])
def test_inactive_context_hides_all_values_even_with_fresh_sources(monkeypatch, domain, state, expected):
    plugin, _ = make_plugin(monkeypatch, domain)
    if state == "offline":
        plugin.state.conn_state = "offline"
    elif state == "waiting":
        plugin.state.in_battle = False
    else:
        setattr(plugin.state, state, True)
    card = summary(plugin)
    assert card["status"] == expected
    assert all(f["value"] is None for f in card["facts"])


@pytest.mark.parametrize("domain", ["air", "ground", "heli", "naval"])
def test_cached_sources_age_without_being_refreshed_by_dashboard_reads(monkeypatch, domain):
    plugin, now = make_plugin(monkeypatch, domain)
    first = summary(plugin)
    now[0] += 6
    stale = summary(plugin)
    assert stale["status"] == "unavailable"
    assert stale["sources"][0]["status"] == "stale"
    assert stale["sources"][0]["age_seconds"] > first["sources"][0]["age_seconds"]
    assert all(f["value"] is None for f in stale["facts"])
    assert plugin.pushed_messages == []


@pytest.mark.parametrize("age", [None, -1, True, "bad", float("nan"), float("inf")])
def test_missing_or_invalid_independent_vehicle_age_is_not_replaced_by_fast_age(monkeypatch, age):
    plugin, _ = ground_plugin(monkeypatch, meta={"fast": {"age_sec": 0.2}, "vehicle": {"age_sec": age}})
    card = summary(plugin)
    assert card["sources"][0]["status"] == "unknown_age"
    assert all(f["value"] is None for f in card["facts"])
    json.dumps(card, allow_nan=False)


@pytest.mark.parametrize("kind", ["future", "missing_fast", "negative_fast", "invalid_timestamp"])
def test_response_clock_must_be_known_and_not_in_the_future(monkeypatch, kind):
    plugin, now = ground_plugin(monkeypatch)
    if kind == "future":
        now[0] = 999
    elif kind == "invalid_timestamp":
        plugin.state.timestamp = float("nan")
    else:
        plugin.state.age_seconds = None if kind == "missing_fast" else -1
    card = summary(plugin)
    assert card["sources"][0]["status"] == ("invalid_clock" if kind == "future" else "unknown_age")
    assert all(f["value"] is None for f in card["facts"])
    json.dumps(card, allow_nan=False)


def test_valid_zero_false_and_negative_values_keep_their_meaning(monkeypatch):
    plugin, _ = ground_plugin(monkeypatch, processed={"crew_current": 2, "crew_total": 4,
        "ammo_first_stage": 0, "gun_stabilizer": False, "gear_position": -2, "laser_warning_state": -1})
    rows = {f["id"]: f for f in summary(plugin)["facts"]}
    assert rows["ammo_first_stage"]["value"] == 0
    assert rows["gun_stabilizer"]["value"] is False
    assert rows["gear_position"]["value"] == -2
    assert rows["laser_warning_state"]["value"] == -1
    assert rows["crew_current"]["total"] == 4


def test_partial_data_never_claims_all_sources_or_facts_are_known(monkeypatch):
    plugin, _ = ground_plugin(monkeypatch, processed={"ammo_first_stage": 0})
    card = summary(plugin)
    assert card["status"] == "partial"
    assert sum(f["status"] == "available" for f in card["facts"]) == 1
    assert next(f for f in card["facts"] if f["id"] == "crew_current")["value"] is None


@pytest.mark.parametrize("key,value", [("ias_kmh", float("nan")), ("radio_altitude_m", -1),
                                       ("fuel_fraction", 1.01), ("mach", True)])
def test_air_summary_rejects_nonfinite_or_out_of_contract_values(monkeypatch, key, value):
    plugin, _ = make_plugin(monkeypatch, "air")
    setattr(plugin.state, key, value)
    fact = next(f for f in summary(plugin)["facts"] if f["id"] == key)
    assert fact["status"] == "unknown" and fact["value"] is None
    json.dumps(summary(plugin), allow_nan=False)


def test_naval_and_unknown_never_borrow_foreign_instruments_or_static_values(monkeypatch):
    plugin, _ = naval_plugin(monkeypatch)
    plugin.state.ias_kmh = plugin.state.rotor_rpm = plugin.state.crew_current = 987654
    plugin.state.raw["combat"] = {"player_name": "private-sentinel"}
    plugin.state.raw["indicators"]["raw"] = {"speed": 987654, "type": "private-sentinel"}
    card = summary(plugin)
    assert "987654" not in json.dumps(card) and "private-sentinel" not in json.dumps(card)
    assert {f["source"] for f in card["facts"]} == {"map"}
    plugin.state.domain = "unknown"
    card = summary(plugin)
    assert card["domain"] == "unknown" and card["capabilities"] == ["generic_map"]
    assert "domain_unconfirmed" in card["limits"]
    assert "987654" not in json.dumps(card)


def test_source_independence_keeps_map_when_naval_instruments_fail(monkeypatch):
    plugin, _ = naval_plugin(monkeypatch)
    plugin.state.raw["meta"]["naval_indicators"] = {"status": "probe_failed"}
    assert summary(plugin)["sources"][0]["status"] == "ready"
    assert any(f["status"] == "available" for f in summary(plugin)["facts"])


def test_new_life_and_domain_switch_discard_old_summary_values(monkeypatch):
    plugin, _ = naval_plugin(monkeypatch)
    assert any(f["status"] == "available" for f in summary(plugin)["facts"])
    plugin.state.life_index = 2
    assert all(f["value"] is None for f in summary(plugin)["facts"])
    plugin.state = parse_telemetry({"domain": "heli", "state": "in_battle", "in_battle": True,
        "timestamp": 1000, "vehicle": {"valid": True}, "meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": 0}}})
    card = summary(plugin)
    assert card["domain"] == "heli" and all(f["value"] is None for f in card["facts"])
    assert "enemy_count" not in {f["id"] for f in card["facts"]}


@pytest.mark.parametrize("mode", ["live", "paused", "disabled"])
def test_summary_reflects_existing_policy_without_toggling_it(monkeypatch, mode):
    plugin, _ = make_plugin(monkeypatch, "ground")
    plugin.cfg.dry_run = False
    plugin.cfg.ground_status_real_output_enabled = True
    plugin.cfg.v2_live_verified_real_output_enabled = True
    if mode == "paused":
        plugin.safety.pause()
    elif mode == "disabled":
        plugin.cfg.enabled = False
    before = copy.deepcopy(plugin.cfg.to_dict())
    card = summary(plugin)
    assert card["output"]["mode"] == {"live": "existing_policy", "paused": "paused", "disabled": "disabled"}[mode]
    assert card["output"]["ground_status_enabled"] is card["output"]["v2_enabled"] is True
    assert card["output"]["heli_vrs_enabled"] is card["output"]["naval_contacts_enabled"] is False
    assert plugin.cfg.to_dict() == before and plugin.pushed_messages == []


def test_reading_confirming_naval_pipeline_cannot_feed_or_reset_detectors(monkeypatch):
    from test_helicopter_vrs import _evaluate, _runtime
    from test_naval_events import _state

    plugin, now = _runtime(monkeypatch)
    _evaluate(plugin, now, _state())
    before = copy.deepcopy([det.__dict__ for det in plugin.engine.detectors])
    timeline = copy.deepcopy(plugin.timeline.snapshot())
    for _ in range(20):
        summary(plugin)
    assert [det.__dict__ for det in plugin.engine.detectors] == before
    assert plugin.timeline.snapshot() == timeline and plugin.pushed_messages == []
