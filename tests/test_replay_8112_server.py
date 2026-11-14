"""Fake :8112 replay server tests."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path


def _frame(timestamp: float = 10.0) -> dict:
    return {
        "state": "in_battle",
        "timestamp": timestamp,
        "in_battle": True,
        "vehicle": {"valid": True, "ias_kmh": 300.0},
        "indicators": {"valid": True, "vehicle_type": "ki_61_1a_otsu_china", "army": "air"},
        "processed": {"flags": {}, "level": "info", "ias_kmh": 300.0},
        "combat": {"player_name": "auto", "feed": []},
        "meta": {"fast": {"age_sec": 1.25}},
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_load_frames_discovers_processed_8112_under_sample_root(tmp_path):
    from neko_warthunder.tools import replay_8112_server as replay_server

    capture = tmp_path / "captures" / "run" / "processed_8112.jsonl"
    _write_jsonl(capture, [{"ts": 1.0, "status": 200, "data": _frame(10.0)}])

    assert replay_server.discover_capture_file(tmp_path) == capture.resolve()
    assert replay_server.load_frames(tmp_path)[0]["timestamp"] == 10.0


def test_ground_capture_rounding_keeps_first_sample_available(tmp_path):
    from neko_warthunder.tools import replay_8112_server as replay_server

    path = tmp_path / "processed_8112.jsonl"
    ground = {**_frame(10.0004), "domain": "ground"}
    ground["meta"]["ground_indicators"] = {"status": "ready", "sample_timestamp": 10.0003, "age_sec": 0.0}
    _write_jsonl(path, [{"ts": 10.0, "data": ground}])
    state = replay_server.ReplayState(replay_server.load_frames(path), clock=lambda: 100.0)

    payload = state.current_payload()
    assert payload["timestamp"] == 100.0
    assert payload["meta"]["fast"]["age_sec"] == 0.0
    assert 99.999 < payload["meta"]["ground_indicators"]["sample_timestamp"] <= 100.0
    assert "observed_at" not in payload


def test_ground_replay_observes_last_frame_before_end_offline():
    from neko_warthunder.tools import replay_8112_server as replay_server

    first = {**_frame(10.0), "domain": "ground", "life_index": 1}
    last = {**_frame(11.0), "domain": "ground", "life_index": 2}
    now = iter([1000.0, 1000.0, 1000.8, 1001.6])
    state = replay_server.ReplayState([first, last], speed=2.0, end_mode="offline", clock=lambda: next(now))

    assert state.current_payload()["life_index"] == 1
    assert state.current_payload()["life_index"] == 2
    assert state.health()["ended"] is False
    assert state.current_payload()["state"] == "offline"
    assert state.health()["ended"] is True


def test_single_ground_frame_can_end_offline():
    from neko_warthunder.tools import replay_8112_server as replay_server

    frame = {**_frame(10.0), "domain": "ground"}
    now = iter([1000.0, 1000.8, 1001.2])
    state = replay_server.ReplayState([frame], end_mode="offline", clock=lambda: next(now))

    assert state.current_payload()["state"] == "in_battle"
    assert state.current_payload()["state"] == "offline"


def test_ground_replay_estimates_leading_untimestamped_observations():
    from neko_warthunder.tools import replay_8112_server as replay_server

    offline = {"state": "offline", "in_battle": False, "timestamp": 0}
    first = {**_frame(1_780_000_000.0), "domain": "ground", "life_index": 1}
    last = {**_frame(1_780_000_000.5), "domain": "ground", "life_index": 2}
    now = iter([1000.0, 1000.0, 1000.25, 1000.625, 1001.125])
    state = replay_server.ReplayState([offline, first, last], clock=lambda: next(now))

    assert state.health()["duration"] == 1.0
    assert state.current_payload()["state"] == "offline"
    assert state.current_payload()["state"] == "offline"
    assert state.current_payload()["life_index"] == 1
    assert state.current_payload()["life_index"] == 2


def test_ground_replay_preserves_original_clocks_when_requested():
    from neko_warthunder.tools import replay_8112_server as replay_server

    ground = {**_frame(10.0), "domain": "ground"}
    ground["meta"]["ground_indicators"] = {"status": "held", "sample_timestamp": 9.75, "age_sec": 1.5}
    now = iter([100.0, 101.0, 102.0])
    state = replay_server.ReplayState([ground], refresh_timestamps=False, clock=lambda: next(now))

    assert state.current_payload() == state.current_payload() == ground


def test_air_frame_with_unavailable_ground_metadata_keeps_air_replay_timing():
    from neko_warthunder.tools import replay_8112_server as replay_server

    ground = {**_frame(10.0), "domain": "ground", "battle_id": "test-battle"}
    air = {**_frame(12.0), "domain": "air", "battle_id": "test-battle"}
    air["meta"]["ground_indicators"] = {"status": "unavailable", "count": 1, "age_sec": None}
    now = iter([100.0, 102.25, 104.0, 106.25])
    state = replay_server.ReplayState([ground, air], loop=True, clock=lambda: next(now))

    payload = state.current_payload()
    assert payload["domain"] == "air" and payload["timestamp"] == 102.25
    assert payload["meta"]["fast"]["age_sec"] == 0.0
    assert payload["battle_id"] == "test-battle"
    next_ground, next_air = state.current_payload(), state.current_payload()
    assert next_ground["domain"] == "ground" and next_air["domain"] == "air"
    assert next_ground["battle_id"] == next_air["battle_id"] != "test-battle"


def test_replay_state_refreshes_timestamp_and_injects_manual_identity():
    from neko_warthunder.tools import replay_8112_server as replay_server

    now = iter([100.0, 101.0, 101.0])
    state = replay_server.ReplayState(
        [_frame(10.0)],
        refresh_timestamps=True,
        player_name="CN-Zephyr",
        clock=lambda: next(now),
    )

    payload = state.current_payload()

    assert payload["timestamp"] == 101.0
    assert payload["meta"]["fast"]["age_sec"] == 0.0
    assert payload["combat"]["player_name"] == "CN-Zephyr"
    assert payload["combat"]["self"]["source"] == "manual"


def test_replay_state_can_infer_legacy_combat_feed_ownership_from_manual_identity():
    from neko_warthunder.tools import replay_8112_server as replay_server

    frame = _frame(10.0)
    frame["combat"]["feed"] = [
        {"id": 1, "is_kill": True, "killer": "tl0sr2", "victim": "I-153"},
        {"id": 2, "is_kill": True, "killer": "Other", "victim": "tl0sr2 (crashed)"},
        {"id": 3, "is_kill": True, "killer": "Other", "victim": "I-153"},
    ]
    state = replay_server.ReplayState(
        [frame],
        player_name="tl0sr2",
        infer_ownership_from_player_name=True,
        clock=lambda: 100.0,
    )

    feed = state.current_payload()["combat"]["feed"]

    assert feed[0]["is_my_kill"] is True
    assert feed[0]["is_my_death"] is False
    assert feed[0]["involves_me"] is True
    assert feed[1]["is_my_kill"] is False
    assert feed[1]["is_my_death"] is True
    assert feed[1]["involves_me"] is True
    assert feed[2]["is_my_kill"] is False
    assert feed[2]["is_my_death"] is False


def test_replay_state_does_not_infer_ownership_by_default():
    from neko_warthunder.tools import replay_8112_server as replay_server

    frame = _frame(10.0)
    frame["combat"]["feed"] = [{"id": 1, "is_kill": True, "killer": "tl0sr2", "victim": "I-153"}]
    state = replay_server.ReplayState([frame], player_name="tl0sr2", clock=lambda: 100.0)

    item = state.current_payload()["combat"]["feed"][0]

    assert "is_my_kill" not in item
    assert "is_my_death" not in item


def test_replay_state_does_not_inject_interference_by_default():
    from neko_warthunder.tools import replay_8112_server as replay_server

    calls = iter([100.0, 104.0, 104.0])
    state = replay_server.ReplayState([_frame(10.0)], clock=lambda: next(calls))

    payload = state.current_payload()

    assert "hudmsg" not in payload
    assert "awards" not in payload
    assert "gamechat" not in payload
    assert state.health()["interference"] is False


def test_replay_state_can_overlay_interference_without_replacing_combat_feed():
    from neko_warthunder.tools import replay_8112_server as replay_server

    frame = _frame(10.0)
    frame["combat"]["feed"] = [{"id": 1, "is_kill": True, "killer": "tl0sr2", "victim": "I-153"}]
    calls = iter([100.0, 109.0, 109.0])
    state = replay_server.ReplayState([frame], inject_interference=True, clock=lambda: next(calls))

    payload = state.current_payload()

    assert state.health()["interference"] is True
    assert payload["awards"]["feed"]
    assert payload["combat"]["feed"][0]["killer"] == "tl0sr2"
    assert payload["combat"]["feed"][-1]["is_my_kill"] is False
    assert payload["combat"]["feed"][-1]["involves_me"] is False


def test_replay_state_applies_scenario_patch_by_elapsed_time():
    from neko_warthunder.tools import replay_8112_server as replay_server

    calls = iter([100.0, 105.0, 105.0])
    state = replay_server.ReplayState(
        [_frame(10.0)],
        scenario={
            "patches": [
                {
                    "at": 3.0,
                    "duration": 5.0,
                    "patch": {"replay": True, "processed": {"flags": {"overspeed_critical": True}, "level": "critical"}},
                }
            ]
        },
        clock=lambda: next(calls),
    )

    payload = state.current_payload()

    assert payload["replay"] is True
    assert payload["processed"]["flags"]["overspeed_critical"] is True
    assert payload["processed"]["level"] == "critical"


def test_replay_state_holds_last_frame_by_default_after_duration():
    from neko_warthunder.tools import replay_8112_server as replay_server

    first = _frame(10.0)
    last = _frame(12.0)
    last["combat"]["feed"] = [{"id": 1, "is_kill": True, "killer": "tl0sr2", "victim": "I-153"}]
    calls = iter([100.0, 103.0, 103.0])
    state = replay_server.ReplayState([first, last], clock=lambda: next(calls))

    payload = state.current_payload()

    assert payload["timestamp"] == 103.0
    assert payload["combat"]["feed"][0]["killer"] == "tl0sr2"
    assert state.health()["end_mode"] == "hold"
    assert state.health()["ended"] is True


def test_replay_state_end_offline_returns_safe_idle_payload_after_duration():
    from neko_warthunder.tools import replay_8112_server as replay_server

    first = _frame(10.0)
    last = _frame(12.0)
    last["combat"]["feed"] = [{"id": 1, "is_kill": True, "killer": "tl0sr2", "victim": "I-153"}]
    calls = iter([100.0, 103.0, 103.0])
    state = replay_server.ReplayState(
        [first, last],
        player_name="tl0sr2",
        end_mode="offline",
        clock=lambda: next(calls),
    )

    payload = state.current_payload()
    health = state.health()

    assert payload["state"] == "offline"
    assert payload["in_battle"] is False
    assert payload["vehicle"]["valid"] is False
    assert payload["indicators"]["valid"] is False
    assert payload["combat"]["feed"] == []
    assert payload["combat"]["self"]["name"] == "tl0sr2"
    assert payload["meta"]["fast"]["age_sec"] == 0.0
    assert health["end_mode"] == "offline"
    assert health["ended"] is True


def test_http_server_serves_health_telemetry_and_identity():
    from neko_warthunder.tools import replay_8112_server as replay_server

    now = iter([100.0, 100.0, 100.0, 101.0, 101.0])
    state = replay_server.ReplayState([_frame(10.0)], clock=lambda: next(now))
    server = replay_server.build_server("127.0.0.1", 0, state)
    host, port = server.server_address
    base = f"http://{host}:{port}"

    try:
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        health = _fetch_json(f"{base}/health")
        identity = _fetch_json(f"{base}/api/identity?name=CN-Zephyr")
        telemetry = _fetch_json(f"{base}/api/telemetry")
    finally:
        server.shutdown()
        server.server_close()

    assert health["ok"] is True
    assert health["mode"] == "replay_8112"
    assert identity["source"] == "manual"
    assert telemetry["combat"]["self"]["name"] == "CN-Zephyr"
