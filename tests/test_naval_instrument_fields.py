"""Naval field presence is transport evidence, never a validated instrument reading."""
from __future__ import annotations

import asyncio
import copy
import json

import pytest
from neko_warthunder.adapters.naval_instrument_fields import snapshot_naval_instrument_fields
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from test_helicopter_vrs import _evaluate, _runtime
from test_naval_dashboard import _service
from test_naval_events import _state
from wt_telemetry import WarThunderClient

_KEYS = [("speed", "speed", "speed"), ("heading", "heading_deg", "compass"),
         ("rpm", "rpm", "rpm"), ("throttle", "throttle", "throttle")]


def _inventory(state=None, now=1000):
    return snapshot_naval_instrument_fields(state or _state(), now)


def _statuses(inventory):
    return {field["id"]: field["status"] for field in inventory["fields"]}


@pytest.mark.parametrize("name,normalized_key,raw_key", _KEYS)
@pytest.mark.parametrize("expected,normalized,raw,raw_present", [
    ("observed_numeric", 0, 0, True), ("normalized_only", 2, None, False),
    ("raw_only", None, 2, True), ("missing", None, None, False),
    ("invalid", True, True, True), ("conflicting", 2, 1, True), ("conflicting", 2, None, True),
])
def test_each_candidate_field_distinguishes_transport_evidence(name, normalized_key, raw_key,
                                                              expected, normalized, raw, raw_present):
    current = _state()
    current.raw["indicators"].update({normalized_key: normalized, "raw": {raw_key: raw} if raw_present else {}})
    inventory = _inventory(current)
    assert inventory["source_status"] == "response_only"
    assert _statuses(inventory)[name] == expected
    assert inventory["instrument_values_enabled"] is inventory["real_output_enabled"] is False
    assert inventory["sample_life_bound"] is inventory["naval_semantics_verified"] is False
    assert set(inventory["fields"][0]) == {"id", "status"}
    json.dumps(inventory, allow_nan=False)


@pytest.mark.parametrize("value", [True, "2", {}, [], float("nan"), float("inf"), 10 ** 500])
@pytest.mark.parametrize("side", ["normalized", "raw"])
def test_unsafe_or_coerced_numeric_values_are_never_accepted_as_numeric_presence(value, side):
    current = _state()
    current.raw["indicators"].update(speed=value if side == "normalized" else 2,
                                     raw={"speed": value if side == "raw" else 2})
    assert _statuses(_inventory(current))["speed"] == "invalid"


@pytest.mark.parametrize("value", [0, -0.5, 1.25, 1e12])
def test_finite_presence_does_not_guess_naval_units_sign_range_or_capacity(value):
    current = _state()
    current.raw["indicators"].update(speed=value, raw={"speed": value})
    inventory = _inventory(current)
    assert _statuses(inventory)["speed"] == "observed_numeric"
    assert "value" not in inventory["fields"][0] and "unit" not in inventory["fields"][0]


@pytest.mark.parametrize("change,reason", [
    ("offline", "offline"), ("replay", "replay"), ("dead", "dead"), ("waiting", "waiting"),
    ("unknown", "unconfirmed_naval"), ("invalid_indicators", "unconfirmed_naval"),
    ("battle", "unknown_life"), ("life", "unknown_life"), ("life_bool", "unknown_life"),
    ("raw_shape", "invalid_source"), ("raw_army", "invalid_source"), ("raw_valid", "invalid_source"),
    ("unknown_age", "unknown_age"), ("negative_age", "unknown_age"), ("future", "unknown_age"),
    ("stale", "stale"), ("attempt_age_fresh", "stale"),
])
def test_invalid_source_withholds_field_status_instead_of_showing_cached_presence(change, reason):
    current, now = _state(), 1000
    current.raw["indicators"].update(speed=1, raw={"speed": 1})
    if change == "offline":
        current.connected = False
    elif change in {"replay", "dead"}:
        setattr(current, change, True)
    elif change == "waiting":
        current.in_battle = False
    elif change == "unknown":
        current.domain = "unknown"
    elif change == "invalid_indicators":
        current.raw["indicators"]["valid"] = 1
    elif change == "battle":
        current.battle_id = None
    elif change.startswith("life"):
        current.life_index = True if change == "life_bool" else None
    elif change == "raw_shape":
        current.raw["indicators"]["raw"] = []
    elif change == "raw_army":
        current.raw["indicators"]["raw"]["army"] = "tank"
    elif change == "raw_valid":
        current.raw["indicators"]["raw"]["valid"] = "true"
    elif change == "unknown_age":
        current.age_seconds = None
    elif change == "negative_age":
        current.age_seconds = -1
    elif change == "future":
        current.timestamp += 1
    elif change == "stale":
        current.age_seconds = 6
    else:
        now = 1006  # Fresh attempt age cannot make an old indicators timestamp fresh.
    inventory = _inventory(current, now)
    assert inventory["source_status"] == reason
    assert set(_statuses(inventory).values()) == {"unavailable"}
    json.dumps(inventory, allow_nan=False)


@pytest.mark.parametrize("domain", ["air", "heli", "ground", "menu"])
def test_other_domains_never_receive_a_naval_instrument_inventory(domain):
    current = _state()
    current.domain = domain
    assert _inventory(current) is None


def test_actual_service_and_parser_preserve_candidate_paths_without_foreign_processed_values(monkeypatch):
    service, _, moment = _service(monkeypatch)
    raw = {"valid": True, "army": "fleet", "speed": 7.25, "compass": 180, "rpm": 750, "throttle": 0.4,
           "crew_current": 99, "first_stage_ammo": 88, "prop_rpm": 999, "water_temperature": 120,
           "private_text": "private-sentinel"}
    service._indicators = WarThunderClient()._parse_indicators(raw)
    payload = service.get_snapshot()
    payload["meta"].pop("naval_indicators")  # Legacy transport, not a successful poll.
    current = parse_telemetry(payload)
    inventory = _inventory(current, moment[0])
    assert current.domain == "naval" and current.vehicle_valid is False
    assert set(_statuses(inventory).values()) == {"observed_numeric"}
    assert current.crew_current is current.ammo_first_stage is current.rotor_rpm is current.water_temp_c is None
    assert current.flags == {}
    assert "private-sentinel" not in json.dumps(inventory)


@pytest.mark.parametrize("raw_speed", [True, "7.25"])
def test_inventory_does_not_trust_generic_parser_numeric_coercion(monkeypatch, raw_speed):
    service, _, moment = _service(monkeypatch)
    service._indicators = WarThunderClient()._parse_indicators({"valid": True, "army": "ship", "speed": raw_speed})
    payload = service.get_snapshot()
    payload["meta"].pop("naval_indicators")  # Exercise legacy coercion evidence.
    current = parse_telemetry(payload)
    assert isinstance(current.raw["indicators"]["speed"], float)
    assert _statuses(_inventory(current, moment[0]))["speed"] == "invalid"


def test_map_or_vehicle_metadata_cannot_promote_instruments_or_fake_life_binding():
    current = _state()
    current.situation = {}
    current.raw["meta"]["map_objects"] = {"age_sec": 100, "life_index": 99, "count": 400}
    current.raw["meta"]["vehicle"] = {"age_sec": 0, "life_index": 1, "count": 500}
    current.raw["indicators"].update(speed=1, raw={"speed": 1})
    before = _inventory(current)
    assert before["source_status"] == "response_only" and before["sample_life_bound"] is False
    current.life_index = 2
    after = _inventory(current)
    assert before == after  # Response presence never claims the sample belongs to this new life.
    assert after["instrument_values_enabled"] is False
    assert _inventory(current, 1005)["source_status"] == "response_only"
    assert _inventory(current, 1005.001)["source_status"] == "stale"


def test_repeated_dashboard_reads_leave_detectors_timeline_config_and_raw_state_unchanged(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    _evaluate(plugin, moment, _state())
    plugin.state.raw["indicators"].update(speed=7.25, heading_deg=180, rpm=750, throttle=0.4,
                                         raw={"speed": 7.25, "compass": 180, "rpm": 750, "throttle": 0.4,
                                              "name": "private-sentinel", "flooding": 77})
    state_before = copy.deepcopy(plugin.state)
    detectors = copy.deepcopy([det.__dict__ for det in plugin.engine.detectors])
    timeline, cfg = plugin.timeline.snapshot(), plugin.cfg.to_dict()
    for _ in range(8):
        inventory = asyncio.run(plugin.dashboard_context())["naval_instrument_fields"]
        encoded = json.dumps(inventory, allow_nan=False)
        assert "private-sentinel" not in encoded and "7.25" not in encoded and "750" not in encoded
        assert set(_statuses(inventory).values()) == {"observed_numeric"}
    assert plugin.state == state_before and [det.__dict__ for det in plugin.engine.detectors] == detectors
    assert plugin.timeline.snapshot() == timeline and plugin.cfg.to_dict() == cfg
    assert plugin.pushed_messages == plugin.config_updates == []


def test_real_mode_and_enabled_output_switches_cannot_enable_instrument_values_or_naval_speech(monkeypatch):
    plugin, moment = _runtime(monkeypatch, dry_run=False)
    plugin.cfg.ground_status_real_output_enabled = plugin.cfg.v2_live_verified_real_output_enabled = True
    plugin.cfg.plugin_owned_battle_output_enabled = plugin.cfg.plugin_owned_urgent_output_enabled = True
    for count in (1, 2):
        _evaluate(plugin, moment, _state(count))
    inventory = asyncio.run(plugin.dashboard_context())["naval_instrument_fields"]
    assert inventory["instrument_values_enabled"] is inventory["real_output_enabled"] is False
    assert plugin.pushed_messages == []
