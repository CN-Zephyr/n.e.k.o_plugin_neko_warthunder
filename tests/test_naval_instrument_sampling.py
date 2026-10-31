"""Actual probe -> service -> HTTP consumer boundaries for naval instrument samples."""
from __future__ import annotations

import copy
import importlib
import json

import pytest
from neko_warthunder.adapters.naval_instrument_fields import snapshot_naval_instrument_fields
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from test_naval_events import _state


def _polling_service(monkeypatch):
    server = importlib.import_module("neko_warthunder.data_layer.data_process.wt_server")
    moment = [1000.0]

    class Client:
        probe_ok, state_ok = True, False
        in_battle = True
        during_request = None
        raw = {"valid": True, "army": "ship", "speed": 7.25, "compass": 90, "rpm": 900, "throttle": 0.6}

        def get_indicators_with_status(self):
            if self.during_request:
                self.during_request()
            return (self.probe_ok,
                    server.ConnectionState.IN_BATTLE if self.in_battle else server.ConnectionState.NOT_IN_BATTLE,
                    server.WarThunderClient()._parse_indicators(self.raw), server.MapInfo(valid=self.in_battle))

        def get_state_with_status(self):
            return self.state_ok, server.VehicleState(valid=self.state_ok)

    client = Client()
    service = server.TelemetryService(client)
    monkeypatch.setattr(server.time, "time", lambda: moment[0])
    return service, client, moment


def _read(service, moment):
    payload = service.get_snapshot()
    # _poll_loop normally updates this attempt metadata; these tests drive only _poll_fast.
    payload["meta"]["fast"]["age_sec"] = max(0, moment[0] - payload["timestamp"])
    return snapshot_naval_instrument_fields(parse_telemetry(payload), moment[0])


def _ready(monkeypatch):
    service, client, moment = _polling_service(monkeypatch)
    service._poll_fast()  # Entry probe does not bind a request begun outside this battle.
    assert _read(service, moment)["sampling_status"] == "context_changed"
    moment[0] += 0.1
    service._poll_fast()
    return service, client, moment


def test_success_is_independent_of_state_map_and_snapshot_reads(monkeypatch):
    service, _, moment = _ready(monkeypatch)
    actual = _read(service, moment)
    assert actual["sampling_status"] == "ready" and actual["sample_life_bound"] is True
    assert actual["sample_count"] == 1 and actual["sample_age_seconds"] == 0
    assert {row["status"] for row in actual["fields"]} == {"observed_numeric"}
    assert service.get_snapshot()["meta"]["vehicle"]["count"] == 0
    assert service.get_snapshot()["meta"]["map_objects"]["count"] == 0
    before = copy.deepcopy(service._naval_indicators_sample)
    for _ in range(8):
        assert _read(service, moment) == actual
    assert service._naval_indicators_sample == before
    moment[0] += 0.1
    service._poll_fast()
    assert _read(service, moment)["sample_count"] == 2
    encoded = json.dumps(actual, allow_nan=False)
    assert all(word not in encoded for word in ("7.25", "900", service._battle_id))
    assert actual["instrument_values_enabled"] is actual["real_output_enabled"] is False


def test_failure_immediately_invalidates_cached_instruments_without_counting_attempts(monkeypatch):
    service, client, moment = _ready(monkeypatch)
    client.probe_ok = False
    moment[0] += 0.1
    service._poll_fast()
    # The existing connection grace keeps the battle alive, but cannot freshen this sample.
    assert service.get_snapshot()["in_battle"] is True
    failed = _read(service, moment)
    assert failed["sampling_status"] == "probe_failed" and failed["sample_life_bound"] is False
    assert {r["status"] for r in failed["fields"]} == {"unavailable"}
    assert service.get_snapshot()["meta"]["naval_indicators"]["count"] == 1
    client.probe_ok = True
    moment[0] += 0.1
    service._poll_fast()
    assert _read(service, moment)["sample_count"] == 2


@pytest.mark.parametrize("raw", [
    {"valid": False, "army": "ship"}, {"valid": 1, "army": "ship"},
    {"valid": "true", "army": "ship"}, {"valid": True, "army": "tank"},
    {"valid": True, "army": "air"}, {"valid": True, "army": "SHIP"},
])
def test_invalid_and_foreign_indicators_do_not_advance_naval_success(monkeypatch, raw):
    service, client, moment = _ready(monkeypatch)
    client.raw = raw
    moment[0] += 0.1
    service._poll_fast()
    meta = service.get_snapshot()["meta"]["naval_indicators"]
    assert meta["status"] != "ready" and meta["count"] == 1
    assert "sample_timestamp" not in meta and "life_index" not in meta


@pytest.mark.parametrize("boundary", ["life", "battle", "generation"])
def test_context_change_while_request_is_in_flight_drops_sample(monkeypatch, boundary):
    service, client, moment = _ready(monkeypatch)
    def change():
        if boundary == "life":
            service._life_index += 1
        elif boundary == "battle":
            service._battle_id = "next-battle"
        else:
            service._battle_generation += 1
    client.during_request = change
    moment[0] += 0.1
    service._poll_fast()
    assert _read(service, moment)["sampling_status"] == "context_changed"
    client.during_request = None
    moment[0] += 0.1
    service._poll_fast()
    assert _read(service, moment)["sample_life_bound"] is True
    assert _read(service, moment)["sample_count"] == 2


@pytest.mark.parametrize("boundary", ["dead", "replay", "exit", "clock"])
def test_lifecycle_or_clock_boundary_withholds_independent_evidence(monkeypatch, boundary):
    service, client, moment = _ready(monkeypatch)
    moment[0] += 0.1
    if boundary == "dead":
        service._combat = {"my": {"deaths": 1}}
    elif boundary == "replay":
        service._replay = True
    elif boundary == "exit":
        client.in_battle = False
    else:
        moment[0] -= 1
    service._poll_fast()
    meta = service.get_snapshot()["meta"]["naval_indicators"]
    assert meta["status"] != "ready" and "sample_timestamp" not in meta
    assert meta["count"] == (0 if boundary == "exit" else 1)
    if boundary == "exit":
        client.in_battle = True
        moment[0] += 1
        service._poll_fast()
        moment[0] += 0.1
        service._poll_fast()
        assert _read(service, moment)["sample_count"] == 1


def _sample_state():
    current = _state()
    current.raw["indicators"].update(speed=1, raw={"valid": True, "army": "ship", "speed": 1})
    current.raw["meta"]["naval_indicators"] = {
        "status": "ready", "count": 5, "sample_timestamp": 999.5, "age_sec": 0.5,
        "battle_id": current.battle_id, "life_index": 1, "army": "ship",
    }
    return current


@pytest.mark.parametrize("key,value,expected", [
    ("count", True, "unbound_sample"), ("count", 0, "unbound_sample"),
    ("count", 1.5, "unbound_sample"), ("count", "1", "unbound_sample"),
    ("life_index", True, "unbound_sample"), ("life_index", 2, "unbound_sample"),
    ("battle_id", "other", "unbound_sample"), ("army", "fleet", "unbound_sample"),
    ("sample_timestamp", 1001, "unknown_sample_age"), ("sample_timestamp", True, "unknown_sample_age"),
    ("sample_timestamp", float("nan"), "unknown_sample_age"),
    ("sample_timestamp", 994.9, "stale_sample"),
    ("age_sec", True, "unknown_sample_age"), ("age_sec", None, "unknown_sample_age"),
    ("age_sec", -1, "unknown_sample_age"), ("age_sec", float("inf"), "unknown_sample_age"),
    ("age_sec", 5.001, "stale_sample"), ("status", "private-sentinel", "invalid_sample"),
    ("status", [], "invalid_sample"), ("status", "probe_failed", "probe_failed"),
])
def test_bad_or_unbound_metadata_cannot_promote_cached_fields(key, value, expected):
    current = _sample_state()
    current.raw["meta"]["naval_indicators"][key] = value
    result = snapshot_naval_instrument_fields(current, 1000)
    assert result["sampling_status"] == expected and result["sample_life_bound"] is False
    assert {r["status"] for r in result["fields"]} == {"unavailable"}
    assert "private-sentinel" not in json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("sample", [None, [], True, "bad", {}])
def test_explicit_malformed_metadata_never_falls_back_to_legacy(sample):
    current = _sample_state()
    current.raw["meta"]["naval_indicators"] = sample
    assert snapshot_naval_instrument_fields(current, 1000)["sampling_status"] == "invalid_sample"


def test_fresh_response_or_other_groups_cannot_freshen_an_old_independent_sample():
    current = _sample_state()
    assert snapshot_naval_instrument_fields(current, 1004.5)["sampling_status"] == "ready"
    assert snapshot_naval_instrument_fields(current, 1004.501)["sampling_status"] == "stale_sample"
    current.timestamp = 1006
    assert snapshot_naval_instrument_fields(current, 1006)["sampling_status"] == "stale_sample"
    current.life_index = 2
    assert snapshot_naval_instrument_fields(current, 1006)["sampling_status"] == "unbound_sample"


@pytest.mark.parametrize("life", [True, 1.5, "1"])
def test_normalized_life_cannot_hide_invalid_raw_identity(life):
    current = _sample_state()
    current.raw["life_index"] = life
    assert snapshot_naval_instrument_fields(current, 1000)["sample_life_bound"] is False


@pytest.mark.parametrize("original", [{}, {"army": "ship"}, {"valid": True}])
def test_new_contract_requires_original_source_identity_as_well_as_metadata(original):
    current = _sample_state()
    current.raw["indicators"]["raw"] = original
    result = snapshot_naval_instrument_fields(current, 1000)
    assert result["sampling_status"] == "invalid_sample" and result["sample_life_bound"] is False


def test_actual_client_probes_advance_indicators_when_state_and_map_objects_fail(monkeypatch):
    server = importlib.import_module("neko_warthunder.data_layer.data_process.wt_server")
    client = server.WarThunderClient()
    requested, moment = [], [1000.0]
    fail_map_info = [False]
    def fetch(endpoint):
        requested.append(endpoint)
        if endpoint == "/indicators":
            return True, {"valid": True, "army": "fleet", "speed": 0}
        if endpoint == "/map_info.json":
            return not fail_map_info[0], {"valid": True}
        return False, None
    monkeypatch.setattr(client, "_fetch", fetch)
    monkeypatch.setattr(server.time, "time", lambda: moment[0])
    service = server.TelemetryService(client)
    for _ in range(2):
        service._poll_fast()
        moment[0] += 0.1
    assert _read(service, moment)["sample_count"] == 1
    assert requested == ["/indicators", "/map_info.json", "/state"] * 2
    fail_map_info[0] = True
    service._poll_fast()
    assert _read(service, moment)["sampling_status"] == "probe_failed"
    assert requested[-2:] == ["/indicators", "/map_info.json"]


def test_confirmed_respawn_frame_cannot_be_assigned_to_the_new_life(monkeypatch):
    service, _, moment = _ready(monkeypatch)
    def respawn(*_):
        service._life_index += 1
        return True
    monkeypatch.setattr(service, "_update_dead_state_locked", respawn)
    moment[0] += 0.1
    service._poll_fast()
    assert _read(service, moment)["sampling_status"] == "context_changed"


def test_slow_probe_cannot_make_earlier_indicator_data_look_fresh(monkeypatch):
    service, client, moment = _ready(monkeypatch)
    request_started = moment[0]
    client.during_request = lambda: moment.__setitem__(0, moment[0] + 6)
    service._poll_fast()
    meta = service.get_snapshot()["meta"]["naval_indicators"]
    assert meta["sample_timestamp"] == request_started and meta["age_sec"] == 6
    assert _read(service, moment)["sampling_status"] == "stale_sample"
    assert _read(service, moment)["sample_life_bound"] is False
