"""Ground recordings through the replay clock, adapter, detectors and dashboard."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core.contracts import BattleState
from neko_warthunder.core.telemetry_freshness import ground_indicator_source
from neko_warthunder.data_layer.data_process import wt_recorder, wt_server
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from neko_warthunder.detectors.discrete.lifecycle import SpawnDetector
from neko_warthunder.tools.replay_8112_server import ReplayState, load_frames
from test_ground_ammo_low import _runtime
from test_ground_dashboard import _plugin
from warthunder_test_clock import patch_module_clock


def _legacy_frame(timestamp, ammo):
    return {
        "state": "in_battle", "in_battle": True, "domain": "ground", "timestamp": timestamp,
        "vehicle": {"valid": False},
        "indicators": {"valid": True, "army": "tank", "vehicle_type": "test-tank", "first_stage_ammo": ammo},
        "processed": {"ammo_first_stage": ammo, "flags": {"ammo_low": ammo == 3}},
        "meta": {"fast": {"age_sec": 0.0}},
    }


def _evaluate_replay_frame(plugin, payload):
    previous, plugin.state = plugin.state, parse_telemetry(payload)
    plugin._evaluate(previous, plugin.state)


def _modern_frame(timestamp, count, flag=None):
    frame = _legacy_frame(timestamp, 3 if flag == "ammo_low" else 12)
    frame.update(battle_id="test-battle", life_index=1)
    frame["meta"]["ground_indicators"] = {
        "status": "ready", "count": count, "sample_timestamp": timestamp, "age_sec": 0,
        "battle_id": "test-battle", "life_index": 1,
    }
    if flag == "crew_loss":
        frame["processed"].update(crew_current=2, crew_total=4, flags={"crew_loss": True})
    return frame


def _modern_outage(status, flag, previous_count=1, timestamp=10):
    if status == "held":
        frame = _modern_frame(timestamp, previous_count, flag)
        frame["meta"]["fast"]["age_sec"] = 0.5
        frame["meta"]["ground_indicators"].update(status="held", age_sec=0.5)
    else:
        frame = _modern_frame(timestamp + 0.5, previous_count)
        frame["domain"] = "unknown"
        frame["indicators"]["valid"] = False
        frame["meta"]["ground_indicators"] = {"status": "unavailable"}
    return frame


def test_modern_recorder_probe_log_splits_confirmation_without_an_outage_frame(tmp_path, monkeypatch):
    plugin, clock = _runtime(monkeypatch)
    plugin.cfg.broadcast_categories = {"lifecycle": False}
    patch_module_clock(monkeypatch, wt_server, time=lambda: clock[0])
    patch_module_clock(monkeypatch, wt_recorder, time=lambda: clock[0])

    class GroundClient:
        probe_ok = True
        ammo = 12
        crew = 4

        def get_indicators_with_status(self):
            clock[0] += 0.125
            if not self.probe_ok:
                return False, wt_server.ConnectionState.OFFLINE, wt_server.Indicators(), wt_server.MapInfo()
            return (True, wt_server.ConnectionState.IN_BATTLE,
                    wt_server.Indicators(valid=True, army="tank", vehicle_type="test-tank",
                                         first_stage_ammo=self.ammo, crew_current=self.crew, crew_total=4),
                    wt_server.MapInfo(valid=True))

        def get_state_with_status(self):
            return True, wt_server.VehicleState(valid=False)

    client = GroundClient()
    recorder = wt_server.SessionRecorder(root_dir=str(tmp_path), interval=0.25)
    service = wt_server.TelemetryService(client, recorder=recorder)
    service._state = wt_server.ConnectionState.IN_BATTLE
    service._battle_entry_ts = service._life_entry_ts = 100.0
    service._battle_id, service._life_index = "test-battle", 1
    session = Path(recorder.start()["session_dir"])
    try:
        for timestamp, client.ammo, client.crew, client.probe_ok in (
            (1000, 12, 4, True), (1001, 3, 2, True), (1001.5, 3, 2, False),
            (1002, 3, 2, True), (1003, 3, 2, True),
        ):
            clock[0] = timestamp
            service._poll_fast()
    finally:
        recorder.stop()

    with gzip.open(session / "events.jsonl.gz", "rt", encoding="utf-8") as stream:
        probe_events = [event for line in stream if (event := json.loads(line))["_event"].startswith("probe_")]
    assert [(event["_event"], event["ts"]) for event in probe_events] == [
        ("probe_failure_started", 1001.625), ("probe_recovered", 1002.125),
    ]
    frames = load_frames(session / "frames.000.jsonl.gz")
    assert [frame["meta"]["ground_indicators"]["status"] for frame in frames] == ["ready"] * 4
    assert frames[2]["meta"]["ground_indicators"]["sample_timestamp"] < probe_events[1]["ts"]

    clock[0] = 2000
    replay = ReplayState(frames, speed=2, clock=lambda: clock[0])
    engine = DetectorEngine(build_condition_detectors())
    previous = BattleState()
    for elapsed, count in ((0, 1), (0.5, 2), (0.875, 2), (1, 3), (1.25, 3), (1.5, 4)):
        clock[0] = 2000 + elapsed
        current = parse_telemetry(replay.current_payload())
        assert current.life_key == ("test-battle", 1)
        assert ground_indicator_source(current).key == ("test-battle", 1, count)
        events = {event.event_id for event in engine.feed(previous, current)}
        assert events == ({"ground_ammo_low", "ground_crew_loss"} if elapsed == 1.5 else set())
        previous = current


def test_modern_replay_reads_probe_marks_from_the_same_session_across_recording_chunks(tmp_path):
    session = tmp_path / "recording"
    session.mkdir()
    first = session / "frames.000.jsonl.gz"
    with gzip.open(first, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(_modern_frame(10, 1, "ammo_low")) + "\n")
    second = session / "frames.001.jsonl"
    second.write_text(
        "".join(json.dumps(_modern_frame(timestamp, count, "ammo_low")) + "\n"
                for count, timestamp in ((2, 11), (3, 12))),
        encoding="utf-8",
    )
    (tmp_path / "events.jsonl").write_text(
        '{"_event":"probe_failure_started","ts":11.5}\n', encoding="utf-8",
    )
    (session / "events.jsonl").write_text(
        '{"_event":"probe_failure_started","ts":true}\n'
        '{"_event":"probe_failure_started","ts":10.5}\n'
        '{"_event":"vehicle_state_poll_failed","ts":11.5}\n'
        '{"_event":',
        encoding="utf-8",
    )
    assert len(load_frames(second)) == 2
    frames = load_frames(session)
    assert [frame["timestamp"] for frame in frames] == [10, 11, 12]
    clock = [1000.0]
    replay = ReplayState(frames, speed=2, clock=lambda: clock[0])
    engine = DetectorEngine(build_condition_detectors())
    previous = BattleState()
    for elapsed in (0, 0.5, 1):
        clock[0] = 1000 + elapsed
        payload = replay.current_payload()
        assert "_event" not in payload
        current = parse_telemetry(payload)
        assert [event.event_id for event in engine.feed(previous, current)] == (
            ["ground_ammo_low"] if elapsed == 1 else []
        )
        previous = current


@pytest.mark.parametrize(("event_id", "flag"), [
    ("ground_ammo_low", "ammo_low"),
    ("ground_crew_loss", "crew_loss"),
])
@pytest.mark.parametrize("outage", ["held", "unavailable", None])
def test_modern_fast_replay_does_not_confirm_across_a_skipped_outage(monkeypatch, event_id, flag, outage):
    plugin, clock = _runtime(monkeypatch)
    plugin.cfg.broadcast_categories = {"lifecycle": False}
    frames = [_modern_frame(timestamp, count, flag) for count, timestamp in enumerate((10, 11, 12), 1)]
    if outage:
        frames.insert(1, _modern_outage(outage, flag))
    replay = ReplayState(frames, speed=2, clock=lambda: clock[0])
    count_on_first_return = int(outage is None)

    for elapsed, sample, expected_count in ((0, 1, 0), (0.125, 1, 0), (0.5, 2, count_on_first_return),
                                            (0.625, 2, count_on_first_return), (1, 3, 1)):
        clock[0] = 1000 + elapsed
        _evaluate_replay_frame(plugin, replay.current_payload())
        assert plugin.state.life_key == ("test-battle", 1) and plugin.state.flag(flag)
        source = ground_indicator_source(plugin.state)
        assert source.status == "ready" and source.key == ("test-battle", 1, sample)
        assert [message["metadata"]["event_id"] for message in plugin.pushed_messages] == [event_id] * expected_count


@pytest.mark.parametrize(("outage", "expected_event_times"), [("held", [0.25]), ("unavailable", [0.25, 1])])
def test_modern_fast_replay_matches_outage_semantics_for_a_confirmed_condition(outage, expected_event_times):
    frames = [_modern_frame(9.5, 1, "ammo_low"), _modern_frame(10, 2, "ammo_low"),
              _modern_outage(outage, "ammo_low", previous_count=2),
              _modern_frame(11, 3, "ammo_low"), _modern_frame(11.5, 4, "ammo_low")]
    clock = [1000.0]
    replay = ReplayState(frames, speed=2, clock=lambda: clock[0])
    engine = DetectorEngine(build_condition_detectors())
    previous = BattleState()
    observed = []
    for elapsed in (0, 0.25, 0.75, 1):
        clock[0] = 1000 + elapsed
        current = parse_telemetry(replay.current_payload())
        assert ground_indicator_source(current).status == "ready"
        observed.extend(elapsed for event in engine.feed(previous, current) if event.event_id == "ground_ammo_low")
        previous = current
    assert observed == expected_event_times


@pytest.mark.parametrize("outage", ["held", "unavailable", None])
def test_modern_fast_replay_drops_pre_outage_buffer_when_the_failure_frame_is_skipped(monkeypatch, outage):
    plugin, clock = _runtime(monkeypatch)
    plugin.cfg.broadcast_categories = {"lifecycle": False}
    plugin.cfg.global_rate_limit_seconds = 1
    frames = [_modern_frame(timestamp, count, "ammo_low") for count, timestamp in enumerate((10, 11, 12), 1)]
    if outage:
        frames.insert(2, _modern_outage(outage, "ammo_low", previous_count=2, timestamp=11))
    replay = ReplayState(frames, speed=2, clock=lambda: clock[0])
    plugin.safety.mark_output(critical=False, now=clock[0])
    for elapsed in (0, 0.5):
        clock[0] = 1000 + elapsed
        _evaluate_replay_frame(plugin, replay.current_payload())
    assert plugin.arbiter._window_best.event_id == "ground_ammo_low"

    clock[0] = 1001
    _evaluate_replay_frame(plugin, replay.current_payload())
    assert ground_indicator_source(plugin.state).key == ("test-battle", 1, 3)
    expected = ["ground_ammo_low"] if outage is None else []
    assert [message["metadata"]["event_id"] for message in plugin.pushed_messages] == expected


@pytest.mark.parametrize(("event_id", "flag"), [
    ("ground_ammo_low", "ammo_low"),
    ("ground_crew_loss", "crew_loss"),
])
@pytest.mark.parametrize("boundary", ["offline", "dead", "none"])
def test_legacy_fast_replay_confirms_on_two_samples_from_the_same_segment(
    monkeypatch, event_id, flag, boundary,
):
    plugin, clock = _runtime(monkeypatch)
    plugin.cfg.broadcast_categories = {"lifecycle": False}
    frames = []
    for timestamp in (10, 11, 12):
        frame = _legacy_frame(timestamp, 3 if flag == "ammo_low" else 12)
        if flag == "crew_loss":
            frame["processed"].update(crew_current=2, crew_total=4, flags={"crew_loss": True})
        frames.append(frame)
    if boundary == "offline":
        frames.insert(1, {"state": "offline", "in_battle": False, "timestamp": 10.5})
    elif boundary == "dead":
        frames.insert(1, {**_legacy_frame(10.5, 12), "dead": True})
    replay = ReplayState(frames, speed=2, clock=lambda: clock[0])

    count_without_boundary = int(boundary == "none")
    for elapsed, expected_count in ((0, 0), (0.125, 0), (0.5, count_without_boundary),
                                    (0.625, count_without_boundary), (1, 1)):
        clock[0] = 1000 + elapsed
        payload = replay.current_payload()
        assert payload["state"] == "in_battle" and not payload.get("dead")
        _evaluate_replay_frame(plugin, payload)
        assert plugin.state.life_key is None and plugin.state.flag(flag)
        assert [message["metadata"]["event_id"] for message in plugin.pushed_messages] == [event_id] * expected_count


@pytest.mark.parametrize("read_before_boundary", [False, True])
def test_legacy_fast_replay_rejects_a_cached_sample_after_a_skipped_boundary(monkeypatch, read_before_boundary):
    plugin, clock = _runtime(monkeypatch)
    plugin.cfg.broadcast_categories = {"lifecycle": False}
    plugin.cfg.global_rate_limit_seconds = 1
    held = _legacy_frame(11, 3)
    held["meta"]["fast"]["age_sec"] = 1
    frames = [_legacy_frame(10, 3), _legacy_frame(11, 3),
              {"state": "offline", "in_battle": False, "timestamp": 11.5},
              held, _legacy_frame(13, 3), _legacy_frame(14, 3)]
    replay = ReplayState(frames, speed=2, clock=lambda: clock[0])
    plugin.safety.mark_output(critical=False, now=clock[0])

    for elapsed in ((0, 0.5) if read_before_boundary else (0,)):
        clock[0] = 1000 + elapsed
        _evaluate_replay_frame(plugin, replay.current_payload())
    if read_before_boundary:
        assert plugin.arbiter._window_best.event_id == "ground_ammo_low"
    else:
        assert plugin.arbiter._window_best is None

    clock[0] = 1001
    _evaluate_replay_frame(plugin, replay.current_payload())
    assert plugin.state.timestamp == 1000.5
    assert plugin.arbiter._window_best is None
    assert plugin.pushed_messages == []
    clock[0] = 1001.5
    _evaluate_replay_frame(plugin, replay.current_payload())
    assert plugin.pushed_messages == []
    clock[0] = 1002
    _evaluate_replay_frame(plugin, replay.current_payload())
    assert [message["metadata"]["event_id"] for message in plugin.pushed_messages] == ["ground_ammo_low"]


def test_legacy_loop_restarts_confirmation_with_preserved_timestamps():
    frames = [_legacy_frame(timestamp, 3) for timestamp in (10, 11)]
    clock = [1000.0]
    replay = ReplayState(frames, loop=True, refresh_timestamps=False, clock=lambda: clock[0])
    engine = DetectorEngine(build_condition_detectors())
    previous = BattleState()
    for elapsed, timestamp, events in ((0, 10, []), (1, 11, ["ground_ammo_low"]),
                                       (2, 10, []), (3, 11, ["ground_ammo_low"])):
        clock[0] = 1000 + elapsed
        current = parse_telemetry(replay.current_payload())
        assert current.timestamp == timestamp and current.life_key is None
        assert [event.event_id for event in engine.feed(previous, current)] == events
        previous = current


@pytest.mark.parametrize(("event_id", "boundary", "paused"), [
    ("ground_crew_loss", "offline", False),
    ("ground_ammo_low", "offline", True),
    ("ground_ammo_low", "dead", True),
    ("ground_ammo_low", "skipped", False),
])
def test_legacy_buffer_without_life_identity_expires_at_a_discontinuity(
    monkeypatch, event_id, boundary, paused,
):
    plugin, clock = _runtime(monkeypatch)
    plugin.cfg.global_rate_limit_seconds = 4
    plugin.cfg.broadcast_categories = {"lifecycle": False}
    frames = [_legacy_frame(10, 12)]
    for timestamp in (11, 12, 14, 15):
        frame = _legacy_frame(timestamp, 3 if event_id == "ground_ammo_low" else 12)
        if event_id == "ground_crew_loss":
            frame["processed"].update(crew_current=2, crew_total=4, flags={"crew_loss": True})
        frames.append(frame)
    if boundary in {"dead", "skipped"}:
        # In the skipped case the recorded death is between plugin polls.
        frames.insert(3, {**_legacy_frame(13, 12), "dead": True})
    replay = ReplayState(frames, clock=lambda: clock[0])
    plugin.safety.mark_output(critical=False, now=clock[0])

    for now in (1000, 1001, 1002):
        clock[0] = now
        _evaluate_replay_frame(plugin, replay.current_payload())
    assert plugin.state.life_key is None
    assert plugin.arbiter._window_best.event_id == event_id

    if boundary != "skipped":
        clock[0] = 1003
        if paused:
            plugin.safety.pause()
        _evaluate_replay_frame(plugin, None if boundary == "offline" else replay.current_payload())
        assert plugin.arbiter._window_best is None
        if paused:
            plugin.safety.resume()

    clock[0] = 1004
    _evaluate_replay_frame(plugin, replay.current_payload())
    assert plugin.arbiter._window_best is None
    assert not any(message["metadata"]["event_id"] == event_id for message in plugin.pushed_messages)
    if boundary != "skipped":
        clock[0] = 1005
        _evaluate_replay_frame(plugin, replay.current_payload())
        assert [message["metadata"]["event_id"] for message in plugin.pushed_messages] == [event_id]


@pytest.mark.parametrize("return_frame", ["same", "offline_then_same", "new", "invalid"])
def test_legacy_laser_retry_without_life_identity_uses_only_the_original_sample(monkeypatch, return_frame):
    plugin, clock = _runtime(monkeypatch)
    plugin.cfg.broadcast_categories = {"lifecycle": False}
    first = _legacy_frame(10, 12)
    first["indicators"]["lws"] = 1
    first["processed"].update(laser_warning_state=1, flags={"laser_warning": True})
    second = {**first, "timestamp": 11}
    if return_frame == "invalid":
        second = {**second, "indicators": {**first["indicators"], "valid": False}, "vehicle": {"valid": True}}
    replay = ReplayState(
        [first] if return_frame in {"same", "offline_then_same"} else [first, second],
        clock=lambda: clock[0],
    )
    push = plugin.push_message

    def fail(**kwargs):
        raise RuntimeError("synthetic push failure")

    plugin.push_message = fail
    _evaluate_replay_frame(plugin, replay.current_payload())
    assert plugin._pending_dispatch_event.event_id == "ground_laser_warning"
    plugin.push_message = push
    if return_frame == "offline_then_same":
        clock[0] = 1000.25
        _evaluate_replay_frame(plugin, None)
        assert plugin._pending_dispatch_event is None

    clock[0] = 1001
    _evaluate_replay_frame(plugin, replay.current_payload())
    assert plugin._pending_dispatch_event is None
    outputs = [message["metadata"]["event_id"] for message in plugin.pushed_messages]
    assert outputs == (["ground_laser_warning"] if return_frame == "same" else [])


@pytest.mark.parametrize("boundary", ["invalid", "model_change"])
def test_legacy_low_ammo_confirmation_cannot_span_an_instrument_boundary(boundary):
    frames = [_legacy_frame(timestamp, 3) for timestamp in (10, 11, 12)]
    if boundary == "invalid":
        frames[1]["indicators"]["valid"] = False
        frames[1]["vehicle"]["valid"] = True  # /state can remain valid with stale processed flags.
        frames.append(_legacy_frame(13, 3))
    else:
        for frame in frames[1:]:
            frame["indicators"]["vehicle_type"] = "second-test-tank"
    clock = [1000.0]
    replay = ReplayState(frames, clock=lambda: clock[0])
    engine = DetectorEngine(build_condition_detectors())
    previous = BattleState()

    for index in range(len(frames)):
        clock[0] = 1000 + index
        current = parse_telemetry(replay.current_payload())
        events = engine.feed(previous, current)
        assert [event.event_id for event in events] == (
            ["ground_ammo_low"] if index == len(frames) - 1 else []
        )
        previous = current


@pytest.mark.parametrize("end_mode", ["hold", "offline"])
def test_legacy_gzip_replay_deduplicates_reads_and_ages_last_frame(tmp_path, monkeypatch, end_mode):
    path = tmp_path / "frames.000.jsonl.gz"
    frames = [_legacy_frame(timestamp, ammo) for timestamp, ammo in [(10, 12), (11, 3), (12, 3)]]
    repeated_frame = _legacy_frame(11, 3)
    repeated_frame["meta"]["fast"]["age_sec"] = 0.5
    frames.insert(2, repeated_frame)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.writelines(f"{json.dumps(frame)}\n" for frame in frames)
    plugin, clock = _plugin(monkeypatch)
    clock[0] = 1000
    replay = ReplayState(load_frames(path), clock=lambda: clock[0], end_mode=end_mode)
    engine = DetectorEngine(build_condition_detectors())
    previous = BattleState()

    for elapsed, expected_timestamp, expected_events in (
        (0, 1000, []), (1, 1001, []), (1.25, 1001, []), (1.5, 1001, []), (2, 1002, ["ground_ammo_low"]),
    ):
        clock[0] = 1000 + elapsed
        current = parse_telemetry(replay.current_payload())
        assert current.timestamp == expected_timestamp
        assert current.age_seconds == pytest.approx(clock[0] - expected_timestamp)
        assert current.life_key is None
        assert [event.event_id for event in engine.feed(previous, current)] == expected_events
        previous = current

    clock[0] = 1007.25
    current = parse_telemetry(replay.current_payload())
    plugin.state = current
    panel = asyncio.run(plugin.dashboard_context())["ground_status"]
    if end_mode == "hold":
        assert current.timestamp == 1002
        assert panel["status"] == "stale" and panel["ammo_first_stage"] is None
    else:
        assert current.conn_state == "offline" and not current.in_battle
        assert panel is None


def test_legacy_replay_distinguishes_disconnect_recovery_from_respawn(monkeypatch):
    plugin, clock = _plugin(monkeypatch)
    clock[0] = 1000
    frames = []
    for timestamp, life, ammo, state in (
        (10, 1, 12, "alive"), (11, 1, 3, "alive"), (12, 1, 3, "offline"),
        (13, 1, 3, "alive"), (14, 1, 3, "dead"), (15, 2, 3, "alive"), (16, 2, 3, "alive"),
    ):
        frame = _legacy_frame(timestamp, ammo)
        frame.update(battle_id="legacy-battle", life_index=life, dead=state == "dead")
        if state == "offline":
            frame.update(state="offline", in_battle=False)
            frame["indicators"]["valid"] = False
            frame["processed"]["flags"] = {}
        frames.append(frame)

    replay = ReplayState(frames, clock=lambda: clock[0])
    engine = DetectorEngine([*build_condition_detectors(), SpawnDetector()])
    previous = BattleState()
    observed = []
    for elapsed in (0, 1, 1.5, 2, 3, 4, 5, 5.5, 6):
        clock[0] = 1000 + elapsed
        current = parse_telemetry(replay.current_payload())
        plugin.state = current
        panel = asyncio.run(plugin.dashboard_context())["ground_status"]
        expected_status = {2: "offline", 4: "dead"}.get(elapsed, "ready")
        assert panel["status"] == expected_status
        if expected_status != "ready":
            assert panel["ammo_first_stage"] is None
        for event in engine.feed(previous, current):
            observed.append((elapsed, event.event_id, event.payload.get("respawn")))
        previous = current

    assert observed == [(5, "spawn", True), (6, "ground_ammo_low", None)]


@pytest.mark.parametrize(("elapsed", "status", "events"), [
    (4.75, "ready", ["ground_laser_warning"]),
    (5, "stale", []),
])
def test_legacy_last_frame_expires_even_on_first_read(monkeypatch, elapsed, status, events):
    plugin, clock = _plugin(monkeypatch)
    clock[0] = 1000
    frame = _legacy_frame(10, 12)
    frame["indicators"]["lws"] = 1
    frame["processed"].update(laser_warning_state=1, flags={"laser_warning": True})
    replay = ReplayState([frame], clock=lambda: clock[0])
    engine = DetectorEngine(build_condition_detectors())

    clock[0] += elapsed
    current = parse_telemetry(replay.current_payload())
    plugin.state = current
    assert current.flag("laser_warning")
    assert [event.event_id for event in engine.feed(BattleState(), current)] == events
    panel = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert (panel["status"], panel["sample_age_seconds"]) == (status, elapsed)
    assert panel["laser_warning_state"] == (1 if status == "ready" else None)


@pytest.mark.parametrize("skip_held", [False, True])
def test_modern_ground_capture_replays_held_and_respawn_without_renewing_the_source(tmp_path, monkeypatch, skip_held):
    plugin, clock = _plugin(monkeypatch)
    patch_module_clock(monkeypatch, wt_server, time=lambda: clock[0])

    class GroundClient:
        probe_ok = True
        ammo = 12
        crew = 4

        def get_indicators_with_status(self):
            clock[0] += 0.125  # Source request starts before the full probe finishes.
            if not self.probe_ok:
                return False, wt_server.ConnectionState.OFFLINE, wt_server.Indicators(), wt_server.MapInfo()
            return (True, wt_server.ConnectionState.IN_BATTLE,
                    wt_server.Indicators(valid=True, army="tank", vehicle_type="test-tank",
                                         first_stage_ammo=self.ammo, crew_current=self.crew, crew_total=4, speed=0),
                    wt_server.MapInfo(valid=True))

        def get_state_with_status(self):
            return True, wt_server.VehicleState(valid=False)

    client = GroundClient()
    service = wt_server.TelemetryService(client)
    service._state = wt_server.ConnectionState.IN_BATTLE
    service._battle_entry_ts = service._life_entry_ts = 100.0
    service._battle_id, service._life_index = "test-battle", 1
    path = tmp_path / "processed_8112.jsonl"
    with path.open("w", encoding="utf-8") as stream:
        for timestamp, ammo, crew, probe_ok in (
            (1000, 12, 4, True), (1001, 3, 4, True), (1001.5, 3, 4, False),
            (1002, 3, 4, True), (1003, 3, 4, True), (1004, 3, 1, True), (1005, 12, 4, True),
        ):
            clock[0] = timestamp
            client.ammo, client.crew, client.probe_ok = ammo, crew, probe_ok
            service._poll_fast()
            stream.write(json.dumps({"ts": clock[0], "status": 200, "data": service.get_snapshot()}) + "\n")

    clock[0] = 2000
    replay = ReplayState(load_frames(path), speed=2, clock=lambda: clock[0])
    engine = DetectorEngine([*build_condition_detectors(), SpawnDetector()])
    previous = BattleState()
    low_events, respawns = [], []
    sources = {}

    for elapsed in (0, 0.5, 0.625, 0.75, 1, 1.5, 2, 2.5, 2.75):
        if elapsed == 0.75 and skip_held:
            continue
        clock[0] = 2000 + elapsed
        current = parse_telemetry(replay.current_payload())
        plugin.state = current
        panel = asyncio.run(plugin.dashboard_context())["ground_status"]
        sources[elapsed] = ground_indicator_source(current, clock[0])
        if elapsed == 0.5:
            assert current.timestamp == 2000.5 and panel["status"] == "ready"
        if elapsed == 0.75:
            assert current.timestamp == previous.timestamp and current.flag("ammo_low")
            assert panel["status"] == "held"
        if elapsed == 2:
            assert current.dead and panel["status"] == "dead"
        if elapsed in (2.5, 2.75):
            assert current.life_key == ("test-battle", 2) and panel["status"] == "ready"
        for event in engine.feed(previous, current):
            if event.event_id == "ground_ammo_low":
                low_events.append(elapsed)
            if event.event_id == "spawn" and event.payload.get("respawn"):
                respawns.append(elapsed)
        previous = current

    assert low_events == [1.5]
    assert respawns == [2.5]
    first_low, repeated = (sources[elapsed] for elapsed in (0.5, 0.625))
    assert first_low.key == repeated.key == ("test-battle", 1, 2)
    assert first_low.timestamp == repeated.timestamp == 2000.4375
    assert (first_low.age_seconds, repeated.age_seconds) == pytest.approx((0.0625, 0.1875))
    if not skip_held:
        held = sources[0.75]
        assert held.key == first_low.key and held.timestamp == first_low.timestamp
        assert held.age_seconds == pytest.approx(0.3125)
    assert sources[2.5].key == sources[2.75].key == ("test-battle", 2, 5)

    clock[0] = 2008
    plugin.state = parse_telemetry(replay.current_payload())
    panel = asyncio.run(plugin.dashboard_context())["ground_status"]
    assert panel["status"] == "stale" and panel["ammo_first_stage"] is None


def test_modern_ground_loop_finishes_last_frame_and_restarts_confirmation():
    frames = []
    for count, ammo in enumerate((12, 3, 3), start=1):
        timestamp = 9 + count
        frame = _legacy_frame(timestamp, ammo)
        frame.update(battle_id="test-battle", life_index=2)
        frame["meta"]["ground_indicators"] = {
            "status": "ready", "count": count, "sample_timestamp": timestamp, "age_sec": 0,
            "battle_id": "test-battle", "life_index": 2,
        }
        frames.append(frame)

    clock = [2000.0]
    replay = ReplayState(frames, loop=True, clock=lambda: clock[0])
    engine = DetectorEngine(build_condition_detectors())
    previous = BattleState()
    confirmations = []
    for elapsed, count in ((0, 1), (1, 2), (1.5, 2), (2, 3), (2.5, 3),
                           (3, 1), (4, 2), (4.5, 2), (5, 3), (5.5, 3)):
        clock[0] = 2000 + elapsed
        current = parse_telemetry(replay.current_payload())
        source = ground_indicator_source(current, clock[0])
        expected_battle = "test-battle" if elapsed < 3 else "test-battle:replay:1"
        assert source.key == (expected_battle, 2, count)
        assert current.timestamp == source.timestamp == 2000 + int(elapsed)
        confirmations.extend((event.event_id, event.ground_sample) for event in engine.feed(previous, current))
        previous = current

    assert confirmations == [
        ("ground_ammo_low", ("test-battle", 2, 3)),
        ("ground_ammo_low", ("test-battle:replay:1", 2, 3)),
    ]
