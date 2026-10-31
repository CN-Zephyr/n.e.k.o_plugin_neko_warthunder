"""Confirmed domains and unsupported naval fields across service, parser and evaluator."""
from __future__ import annotations

import asyncio
import copy
import sys

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.contracts import BattleState
from neko_warthunder.core.scenario import ScenarioResolver
from test_naval_dashboard import _plugin, _service
from test_status_reporting import _plugin_for_action_tests
from wt_processor import TelemetryProcessor
from wt_telemetry import ConnectionState, Indicators, MapObject, Telemetry, VehicleState, resolve_domain


@pytest.mark.parametrize(("army", "helicopter", "expected"), [
    ("air", False, "air"), ("air", True, "heli"), ("tank", False, "ground"),
    ("ship", False, "naval"), ("fleet", False, "naval"),
    ("ship", True, "naval"), ("tank", True, "ground"),
    ("unsupported", True, "unknown"), (None, True, "unknown"),
])
def test_processor_and_top_level_share_explicit_army_whitelist(army, helicopter, expected):
    indicators = Indicators(valid=True, army=army, is_helicopter=helicopter)
    processed = TelemetryProcessor().process(VehicleState(valid=True), indicators, 1000)
    snapshot = Telemetry(ConnectionState.IN_BATTLE, 1000, in_battle=True, indicators=indicators).to_dict()
    assert snapshot["domain"] == processed.vehicle_class == expected
    if expected != "unknown":
        assert snapshot["domain_source"] == "indicators_army"


@pytest.mark.parametrize("army", [None, "", "unsupported", "SHIP", "naval", " ship ", 7, ["ship"]])
def test_unrecognized_army_never_becomes_ground_or_naval(army):
    assert resolve_domain(Indicators(valid=True, army=army), True)["domain"] == "unknown"


@pytest.mark.parametrize(("kind", "source"), [
    ("ground_model", "map_ground_ambiguous"), ("aircraft", "map_aircraft_ambiguous"),
    ("ship", "unavailable"), ("none", "unavailable"),
])
def test_map_player_icon_does_not_confirm_vehicle_domain(kind, source):
    result = resolve_domain(Indicators(valid=False, army="ship"), True, [MapObject(type=kind, icon="Player")])
    assert result == {"domain": "unknown", "domain_label": "未知", "domain_source": source}


@pytest.mark.parametrize("valid", [False, None, 1, "true"])
def test_invalid_indicators_cannot_activate_residual_ground_or_helicopter_fields(valid):
    indicators = Indicators(valid=valid, army="tank", is_helicopter=True,
                            crew_current=1, crew_total=5, prop_rpm=30, radio_altitude=1, vario_ms=-12)
    result = TelemetryProcessor().process(VehicleState(valid=True), indicators, 1000)
    assert result.vehicle_class == "unknown"
    assert result.crew_current is result.rotor_rpm is None
    assert result.flags == {} and result.alerts == []


@pytest.mark.parametrize("army", ["air", "tank", "ship", "fleet", None])
def test_menu_takes_precedence_over_hangar_instruments(army):
    assert resolve_domain(Indicators(valid=True, army=army), False) == {
        "domain": "menu", "domain_label": "主界面/机库", "domain_source": "not_in_battle"}


@pytest.mark.parametrize("domain", ["naval", "unknown", "ground", "air", "heli"])
def test_naval_residual_fields_are_withheld_before_parsing_or_detection(monkeypatch, domain):
    plugin, _ = _plugin(monkeypatch)
    payload = copy.deepcopy(plugin.state.raw)
    payload["domain"] = domain
    payload["vehicle"].update(ias_kmh=1000, altitude_m=4, aoa_deg=40, load_factor=20, climb_ms=-50)
    payload["indicators"].update(radio_altitude=4)
    payload["processed"] = {
        "ias_kmh": 1000, "rotor_rpm": 20, "vario_ms": -12, "water_temp_c": 200,
        "fuel_fraction": 0.01, "crew_current": 1, "ammo_first_stage": 0,
        "gear_position": float("inf"), "gunner_state": 3, "laser_warning_state": 1,
        "flags": {"crew_critical": True, "stall_critical": True, "vrs_critical": True, "engine_overheat": True},
        "profile_family": "private-sentinel", "level": "critical",
    }
    original = copy.deepcopy(payload)
    parsed = parse_telemetry(payload)
    assert parsed.domain == ("naval" if domain == "naval" else "unknown")
    for key in ("ias_kmh", "altitude_m", "radio_altitude_m", "g_now", "climb_ms", "aoa_deg",
                "rotor_rpm", "vario_ms", "water_temp_c", "fuel_fraction", "crew_current",
                "ammo_first_stage", "gear_position", "gunner_state", "laser_warning_state", "profile_family"):
        assert getattr(parsed, key) is None, key
    assert parsed.flags == {} and parsed.level == "info"
    assert payload == original and parsed.raw is payload
    plugin.state = parsed
    assert not any(plugin._build_engine().feed(BattleState(), parsed))


@pytest.mark.parametrize("indicators", [{}, {"valid": False, "army": "ship"},
                                       {"valid": True, "army": "tank"}, {"valid": 1, "army": "fleet"}])
def test_legacy_or_contradictory_naval_claim_is_unknown_with_generic_map(monkeypatch, indicators):
    plugin, _ = _plugin(monkeypatch, indicators=indicators)
    result = asyncio.run(plugin.dashboard_context())
    assert result["domain"] == "unknown" and result["domain_source"] == "unconfirmed_naval"
    assert result["naval_status"] is None
    assert result["map_status"]["enemy_count"] == 2
    assert result["ground_status"] is result["helicopter_status"] is None


def test_data_layer_unknown_map_stays_read_only_and_provenance_is_not_raw(monkeypatch):
    service, _, _ = _service(monkeypatch)
    service._indicators = type(service._indicators)(valid=False)
    service._poll_map(0)
    snapshot = service.get_snapshot()
    assert snapshot["domain"] == "unknown"
    assert snapshot["domain_source"] == "map_ground_ambiguous"
    assert snapshot["proximity"]["events"] == []
    plugin = _plugin_for_action_tests()
    plugin.state = parse_telemetry(snapshot)
    dashboard = asyncio.run(plugin.dashboard_context())
    assert dashboard["naval_status"] is None
    assert dashboard["map_status"]["status"] == "ready"
    snapshot["domain_source"] = "private-sentinel"
    assert parse_telemetry(snapshot).domain_source == "unavailable"
    assert plugin.pushed_messages == plugin.config_updates == []


@pytest.mark.parametrize("indicators", [Indicators(valid=True, army="ship", speed=30),
                                       Indicators(valid=False, army="tank", speed=30, crew_current=1, crew_total=5)])
def test_unsupported_instruments_cannot_kill_or_respawn_a_vehicle(monkeypatch, indicators):
    service, _, _ = _service(monkeypatch)
    assert service._update_dead_state_locked(indicators, {"ias_kmh": 500}, 1000) is False
    assert service._dead is False
    service._dead = service._dead_inert_seen = True
    assert service._update_dead_state_locked(indicators, {"ias_kmh": 500}, 1001) is False
    assert service._dead is True and service._life_index == 1


def test_unknown_snapshot_withholds_cached_foreign_processed_and_proximity(monkeypatch):
    service, _, _ = _service(monkeypatch)
    service._indicators = type(service._indicators)(valid=False, army="tank")
    service._processed = {"vehicle_class": "ground", "crew_current": 1, "flags": {"crew_critical": True}}
    service._proximity_events.append({"kind": "enter", "type": "ground_model", "distance_m": 500})
    snapshot = service.get_snapshot()
    assert snapshot["domain"] == "unknown"
    assert snapshot["processed"] is None
    assert snapshot["proximity"]["events"] == []
    parsed = parse_telemetry({**snapshot, "proximity": {"events": [{"kind": "enter"}]}})
    assert parsed.proximity_events == []


def test_naval_does_not_claim_an_unrelated_aircraft_profile():
    result = TelemetryProcessor().process(VehicleState(valid=True),
                                         Indicators(valid=True, army="ship", vehicle_type="bf_109_f4"), 1000)
    assert result.vehicle_class == "naval"
    assert result.profile_matched is False and result.profile_family is None


def test_missing_motion_is_not_a_stationary_wreck_observation(monkeypatch):
    service, _, _ = _service(monkeypatch)
    server = sys.modules[type(service).__module__]
    service._dead = True
    assert not service._dead_inert_seen
    for ind in (server.Indicators(valid=False, army="tank", speed=0),
                server.Indicators(valid=True, army="ship", speed=0)):
        assert not service._update_dead_state_locked(ind, None, 1000)
        assert not service._dead_inert_seen
    assert not service._update_dead_state_locked(server.Indicators(valid=True, army="tank", speed=30), None, 1001)
    assert service._dead and service._life_index == 1


@pytest.mark.parametrize("army", ["tank", "ship"])
def test_indicator_loss_recovery_and_new_life_through_full_evaluator(monkeypatch, army):
    service, client, moment = _service(monkeypatch)
    server = sys.modules[type(service).__module__]
    valid = [True]
    client.get_indicators_with_status = lambda: (
        True, server.ConnectionState.IN_BATTLE,
        server.Indicators(valid=valid[0], army=army, vehicle_type="synthetic-vehicle"), service._map_info)
    client.get_state_with_status = lambda: (True, server.VehicleState(valid=False))
    service._battle_entry_ts = service._life_entry_ts = 100
    plugin = _plugin_for_action_tests()
    plugin.cfg.spawn_grace_seconds = 0
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=100)
    plugin.dispatcher = NekoDispatcher(plugin, timeline=plugin.timeline)
    monkeypatch.setattr(sys.modules[type(plugin).__module__].time, "time", lambda: moment[0])
    previous = BattleState()
    for now, available in [(1000, True), (1001, False), (1007, False), (1008, True)]:
        moment[0], valid[0] = now, available
        service._poll_fast()
        service._poll_map(0)
        current = parse_telemetry(service.get_snapshot())
        assert current.domain == (("ground" if army == "tank" else "naval") if available else "unknown")
        assert current.life_key == ("synthetic-battle", 1)
        plugin._evaluate(previous, current)
        previous = current
    candidates = [row["event_id"] for row in plugin.timeline.snapshot()["recent_timeline"]
                  if row.get("stage") == "detector_candidate"]
    assert "spawn" not in candidates and "you_died" not in candidates
    service._life_index = 2
    moment[0] = 1010
    service._poll_fast()
    current = parse_telemetry(service.get_snapshot())
    plugin._evaluate(previous, current)
    candidates = [row["event_id"] for row in plugin.timeline.snapshot()["recent_timeline"]
                  if row.get("stage") == "detector_candidate"]
    assert candidates.count("spawn") == 1
    assert plugin.pushed_messages == []
