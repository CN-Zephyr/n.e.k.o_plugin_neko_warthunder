"""Map-success freshness and naval read-only facts across the actual service/UI seam."""
from __future__ import annotations

import asyncio
import copy
import importlib
import json
import sys

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from test_status_reporting import _plugin_for_action_tests
from wt_telemetry import MapObject


def _service(monkeypatch):
    server = importlib.import_module("neko_warthunder.data_layer.data_process.wt_server")
    moment = [1000.0]

    class Client:
        ok = True
        objects = [MapObject(type="ground_model", icon="Player", x=0.5, y=0.5),
                   MapObject(type="ground_model", faction="enemy", x=0.6, y=0.5),
                   MapObject(type="aircraft", faction="enemy", x=0.5, y=0.7),
                   MapObject(type="ground_model", faction="ally", x=0.4, y=0.5),
                   MapObject(type="bombing_point", faction="enemy", x=0.5, y=0.51)]

        def get_map_objects_with_status(self):
            return self.ok, self.objects

    client = Client()
    service = server.TelemetryService(client)
    service._state = server.ConnectionState.IN_BATTLE
    service._indicators = server.Indicators(valid=True, army="ship")
    service._fast_ts = 1000
    service._meta["fast"]["last"] = 1000
    service._battle_id = "synthetic-battle"
    service._life_index = 1
    service._map_info = server.MapInfo(valid=True, map_min=(0, 0), map_max=(10000, 10000))
    monkeypatch.setattr(server.time, "time", lambda: moment[0])
    return service, client, moment


def _plugin(monkeypatch, **patch):
    service, _, moment = _service(monkeypatch)
    service._poll_map(service._battle_generation)
    payload = service.get_snapshot()
    payload["chat"] = [{"msg": "private-sentinel"}]
    payload.update(patch)
    plugin = _plugin_for_action_tests()
    plugin.state = parse_telemetry(payload)
    monkeypatch.setattr(sys.modules[type(plugin).__module__].time, "time", lambda: moment[0])
    return plugin, moment


def _facts(plugin):
    return asyncio.run(plugin.dashboard_context())["naval_status"]


def test_actual_service_to_dashboard_works_without_state_instruments(monkeypatch):
    plugin, _ = _plugin(monkeypatch)
    before = copy.deepcopy(plugin.state.raw)
    assert plugin.state.vehicle_valid is False
    assert _facts(plugin) == {
        "status": "ready", "sample_age_seconds": 0,
        "enemy_count": 2, "ally_count": 1, "air_contact_count": 1,
        "nearest_type": "ground_model", "nearest_distance_m": 1000, "nearest_bearing_deg": 90,
    }
    for _ in range(4):
        dashboard = asyncio.run(plugin.dashboard_context())
        assert dashboard["ground_status"] is dashboard["helicopter_status"] is None
        assert dashboard["dry_run"] is True
        assert "private-sentinel" not in json.dumps(dashboard["naval_status"])
    assert plugin.state.raw == before
    assert plugin.pushed_messages == plugin.config_updates == []
    assert not plugin._runtime_state_path.exists()


@pytest.mark.parametrize("domain", ["air", "heli", "ground", "menu", "unknown"])
def test_other_domains_do_not_show_naval_card(monkeypatch, domain):
    plugin, _ = _plugin(monkeypatch, domain=domain)
    assert _facts(plugin) is None


@pytest.mark.parametrize(("patch", "status"), [
    ({"dead": True}, "dead"), ({"replay": True}, "replay"),
    ({"in_battle": False}, "waiting"), ({"state": "offline"}, "offline"),
    ({"meta": {}}, "unavailable"),
    ({"life_index": 2}, "unavailable"),
    ({"situation": {"has_player": False}}, "no_player"),
    ({"situation": {"has_player": True, "player": {"x": True, "y": 0.5}}}, "no_player"),
])
def test_invalid_context_hides_facts(monkeypatch, patch, status):
    plugin, _ = _plugin(monkeypatch, **patch)
    facts = _facts(plugin)
    assert facts.pop("status") == status
    facts.pop("sample_age_seconds")
    assert all(value is None for value in facts.values())


@pytest.mark.parametrize("age", [None, -1, True, "bad", float("nan"), float("inf")])
def test_map_age_must_be_known_and_finite(monkeypatch, age):
    plugin, _ = _plugin(monkeypatch, meta={"fast": {"age_sec": 0},
                                         "map_objects": {"age_sec": age, "life_index": 1}})
    facts = _facts(plugin)
    assert facts["status"] == "unavailable"
    assert facts["enemy_count"] is None
    json.dumps(facts, allow_nan=False)


def test_cached_sample_ages_and_refresh_recovers(monkeypatch):
    plugin, moment = _plugin(monkeypatch)
    moment[0] += 5
    assert _facts(plugin)["status"] == "ready"
    moment[0] += 0.001
    assert _facts(plugin)["status"] == "stale"
    assert _facts(plugin)["nearest_distance_m"] is None
    payload = copy.deepcopy(plugin.state.raw)
    payload["timestamp"] = moment[0]
    plugin.state = parse_telemetry(payload)
    assert _facts(plugin)["status"] == "ready"


@pytest.mark.parametrize("value", [None, -1, True, 1.5, "bad", float("nan"), float("inf")])
def test_bad_counts_are_unknown(monkeypatch, value):
    plugin, _ = _plugin(monkeypatch)
    plugin.state.situation.update(enemy_count=value, ally_count=value, air_threat_count=value)
    facts = _facts(plugin)
    assert facts["status"] == "ready"
    assert [facts[k] for k in ("enemy_count", "ally_count", "air_contact_count", "nearest_type")] == [None] * 4
    json.dumps(facts, allow_nan=False)


@pytest.mark.parametrize("map_info", [{}, {"valid": True, "grid_size": [4000, 4000]},
                                     {"valid": True, "map_min": [0, 0], "map_max": [0, 100]},
                                     {"valid": True, "map_min": [0, 0], "map_max": [float("nan"), 100]}])
def test_unknown_map_scale_hides_nearest_order_and_distance(monkeypatch, map_info):
    plugin, _ = _plugin(monkeypatch, map_info=map_info)
    facts = _facts(plugin)
    assert facts["enemy_count"] == 2
    assert facts["nearest_type"] is facts["nearest_distance_m"] is facts["nearest_bearing_deg"] is None


def test_empty_success_is_zero_not_unknown(monkeypatch):
    service, client, _ = _service(monkeypatch)
    client.objects = client.objects[:1]
    service._poll_map(service._battle_generation)
    plugin = _plugin_for_action_tests()
    plugin.state = parse_telemetry(service.get_snapshot())
    facts = _facts(plugin)
    assert facts["status"] == "ready"
    assert [facts[k] for k in ("enemy_count", "ally_count", "air_contact_count")] == [0] * 3
    assert facts["nearest_type"] is None


def test_failed_map_polls_never_refresh_success_age_or_erase_counts(monkeypatch):
    service, client, moment = _service(monkeypatch)
    service._poll_map(0)
    plugin = _plugin_for_action_tests()
    client.ok = False
    for now in (1001, 1006):
        moment[0] = now
        service._fast_ts = now
        service._meta["fast"]["last"] = now
        service._poll_map(0)
        # The old worker-attempt counter remains independent from successful samples.
        service._meta["map"].update(last=now, count=100)
        snapshot = service.get_snapshot()
        assert snapshot["meta"]["map_objects"]["count"] == 1
        assert snapshot["situation"]["enemy_count"] == 2
        plugin.state = parse_telemetry(snapshot)
    assert _facts(plugin)["status"] == "stale"
    assert _facts(plugin)["enemy_count"] is None
    client.ok = True
    client.objects = client.objects[:1]
    service._poll_map(0)
    plugin.state = parse_telemetry(service.get_snapshot())
    assert _facts(plugin)["enemy_count"] == 0


def test_respawn_needs_new_map_and_late_old_life_result_is_rejected(monkeypatch):
    service, client, _ = _service(monkeypatch)
    service._poll_map(0)
    service._dead = True
    service._poll_map(0)  # spectator map belongs to the old life
    service._dead = False
    service._life_index = 2
    plugin = _plugin_for_action_tests()
    plugin.state = parse_telemetry(service.get_snapshot())
    assert _facts(plugin)["status"] == "unavailable"
    service._poll_map(0)
    plugin.state = parse_telemetry(service.get_snapshot())
    assert _facts(plugin)["status"] == "ready"
    before = copy.deepcopy(service._situation)

    def late_result():
        service._life_index = 3
        return True, []

    client.get_map_objects_with_status = late_result
    service._poll_map(0)
    assert service._situation == before
    assert service._meta_locked()["map_objects"]["life_index"] == 2
    plugin.state = parse_telemetry(service.get_snapshot())
    assert _facts(plugin)["status"] == "unavailable"


def test_old_battle_result_and_reset_cannot_reuse_old_map(monkeypatch):
    service, _, _ = _service(monkeypatch)
    service._poll_map(0)
    service._battle_generation += 1
    service._poll_map(0)
    assert service._meta_locked()["map_objects"]["count"] == 1
    service._reset_battle_cache_locked()
    sample = service._meta_locked()["map_objects"]
    assert sample["age_sec"] is sample["life_index"] is None
    assert sample["count"] == 0


@pytest.mark.parametrize("patch", [
    {"distance_m": None}, {"distance_m": -1}, {"distance_m": float("inf")},
    {"type": "private-sentinel"},
])
def test_unorderable_or_unrecognized_contact_is_not_claimed_nearest(monkeypatch, patch):
    plugin, _ = _plugin(monkeypatch)
    plugin.state.situation["nearest_enemy"].update(patch)
    facts = _facts(plugin)
    assert facts["enemy_count"] == 2
    assert facts["nearest_type"] is facts["nearest_distance_m"] is facts["nearest_bearing_deg"] is None
    assert "private-sentinel" not in json.dumps(facts)


def test_stale_fast_snapshot_and_nonfinite_bearing_are_not_presented_as_current(monkeypatch):
    plugin, _ = _plugin(monkeypatch)
    plugin.state.situation["nearest_enemy"]["bearing_deg"] = float("nan")
    assert _facts(plugin)["nearest_distance_m"] == 1000
    assert _facts(plugin)["nearest_bearing_deg"] is None
    plugin.state.age_seconds = 6
    assert _facts(plugin)["status"] == "stale"
    assert _facts(plugin)["enemy_count"] is None


def test_new_life_change_during_map_analysis_is_rejected(monkeypatch):
    service, _, _ = _service(monkeypatch)
    server = sys.modules[type(service).__module__]
    original = server.analyze_situation

    def analyze(*args):
        result = original(*args)
        service._life_index += 1
        return result

    monkeypatch.setattr(server, "analyze_situation", analyze)
    service._poll_map(0)
    assert service._situation is None
    assert service._meta_locked()["map_objects"]["age_sec"] is None
