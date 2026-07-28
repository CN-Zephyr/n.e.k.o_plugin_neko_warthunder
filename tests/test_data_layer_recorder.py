"""Data-layer recorder lifecycle tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_recorder_module():
    data_process = Path(__file__).resolve().parents[1] / "data_layer" / "data process"
    spec = importlib.util.spec_from_file_location("wt_recorder_test_module", data_process / "wt_recorder.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rolling_stream_prunes_finished_compression_threads_before_rotation(tmp_path):
    module = _load_recorder_module()
    stream = module._RollingStream(str(tmp_path), "frames", module._MIN_SEGMENT_BYTES)

    class FinishedThread:
        @staticmethod
        def is_alive() -> bool:
            return False

        @staticmethod
        def join() -> None:
            raise AssertionError("finished thread should be pruned before close")

    stream._compression_threads.append(FinishedThread())
    stream._rotate()

    assert len(stream._compression_threads) == 1
    stream.close()


def test_session_recorder_never_persists_raw_chat(tmp_path):
    module = _load_recorder_module()
    recorder = module.SessionRecorder(root_dir=str(tmp_path))
    recorder.start()

    recorder.write_events(
        "chat",
        [{"sender": "Pilot", "msg": "raw private chat must not be persisted"}],
    )
    status = recorder.stop()

    assert status["counts"]["chat"] == 0
    assert not list(tmp_path.rglob("chat*"))


def test_recorder_stops_itself_when_session_quota_is_reached(tmp_path):
    """会话总量超限必须自动停录并说明原因。

    frames 会分段 gzip 但历史段永不清理，hudmsg/proximity/events 三条流完全不滚动，
    长期开着 --record 会无声写满磁盘。
    """
    module = _load_recorder_module()
    recorder = module.SessionRecorder(root_dir=str(tmp_path), max_session_bytes=4096)
    recorder.start()
    assert recorder.recording is True

    payload = {"blob": "x" * 512}
    for _ in range(200):
        recorder.write_events("hudmsg", [payload])
        if not recorder.recording:
            break

    status = recorder.status()
    assert recorder.recording is False
    assert status["stopped_reason"] == "max_session_bytes_reached"
    assert status["max_session_bytes"] == 4096


def test_recorder_quota_can_be_disabled_and_reports_usage(tmp_path):
    module = _load_recorder_module()
    recorder = module.SessionRecorder(root_dir=str(tmp_path), max_session_bytes=0)
    recorder.start()

    for _ in range(50):
        recorder.write_events("hudmsg", [{"blob": "y" * 512}])

    status = recorder.status()
    assert recorder.recording is True
    assert status["stopped_reason"] is None
    assert status["session_bytes"] > 0
    recorder.stop()


def test_recorder_new_session_clears_previous_quota_stop_reason(tmp_path):
    module = _load_recorder_module()
    recorder = module.SessionRecorder(root_dir=str(tmp_path), max_session_bytes=2048)
    recorder.start()
    for _ in range(200):
        recorder.write_events("hudmsg", [{"blob": "z" * 512}])
        if not recorder.recording:
            break
    assert recorder.status()["stopped_reason"] == "max_session_bytes_reached"

    recorder.max_session_bytes = 0
    recorder.start()
    assert recorder.status()["stopped_reason"] is None
    recorder.stop()
