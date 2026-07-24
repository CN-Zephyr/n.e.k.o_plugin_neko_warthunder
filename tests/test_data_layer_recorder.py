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
