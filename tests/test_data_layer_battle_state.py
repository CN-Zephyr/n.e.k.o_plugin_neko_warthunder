"""Data-layer battle state-machine edge cases (replay detection, alert suppression, drain recovery)."""

from __future__ import annotations

import importlib
import pathlib
import threading
import time
import types

import pytest


def _server_module():
    return importlib.import_module("neko_warthunder.data_layer.data_process.wt_server")


def _service(module):
    """A TelemetryService with no threads started; we only drive its state machine."""
    service = object.__new__(module.TelemetryService)
    service._replay = False
    service._last_game_time = None
    service._mission_status = None
    service._mission_running_seen = False
    service._battle_entry_ts = None
    return service


def test_replay_detection_treats_midnight_wrap_as_forward_time():
    """座舱时钟是当日秒数，跨 00:00 会从 ~86399 跳回 0，不能判成回放拖时间轴。

    误判的代价是整局锁定 replay：告警/战绩/态势/嘉奖全部停报，直到离局才复位。
    """
    module = _server_module()
    service = _service(module)

    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=86390.0), 1000.0)
    assert service._replay is False

    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=5.0), 1001.0)
    assert service._replay is False
    assert service._last_game_time == 5.0


def test_replay_detection_still_catches_timeline_scrub():
    """明显倒退仍然判回放。"""
    module = _server_module()
    service = _service(module)

    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=600.0), 1000.0)
    assert service._replay is False

    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=120.0), 1001.0)
    assert service._replay is True


def test_replay_detection_catches_large_scrub_not_near_midnight():
    module = _server_module()
    service = _service(module)

    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=20 * 3600.0), 1000.0)
    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=1 * 3600.0), 1001.0)

    assert service._replay is True


def _assert_midnight_wrap_boundary(
    previous_game_time,
    current_game_time,
    expected_replay,
):
    module = _server_module()
    service = _service(module)

    service._detect_replay_locked(
        types.SimpleNamespace(game_time_sec=previous_game_time),
        1000.0,
    )
    service._detect_replay_locked(
        types.SimpleNamespace(game_time_sec=current_game_time),
        1001.0,
    )

    assert service._replay is expected_replay


def test_midnight_wrap_at_the_edge_is_allowed():
    _assert_midnight_wrap_boundary(
        23 * 3600.0 + 59 * 60.0 + 59.0,
        0.0,
        False,
    )


def test_non_midnight_backwards_jump_is_replay():
    _assert_midnight_wrap_boundary(
        23 * 3600.0,
        1 * 3600.0 + 1.0,
        True,
    )
def test_replay_detection_ignores_small_jitter():
    module = _server_module()
    service = _service(module)

    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=600.0), 1000.0)
    service._detect_replay_locked(types.SimpleNamespace(game_time_sec=598.0), 1001.0)
    assert service._replay is False


def test_suppressed_alerts_also_reset_derived_level():
    """清空 alerts 时必须一并把派生的 level 降回 info。

    否则 /api/processed 与 /api/alerts 返回 {"level": "critical", "alerts": []}，
    按 level 判紧急程度的下游会读到被抑制掉的假警等级。
    """
    module = _server_module()
    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "data_layer" / "data_process" / "wt_server.py"
    ).read_text(encoding="utf-8")

    assert '"alerts": [], "flags": {}, "level": "info"' in source
    assert '"alerts": [], "flags": {}}' not in source
    assert module is not None


def test_cold_start_drain_failure_does_not_keep_zero_recovery_cursor():
    """冷启动(服务在对局中途启动)时客户端游标仍是 0，不是可信的进局前边界。

    保存 {0,0} 作为恢复游标会让重试从 8111 跨局缓冲最开头读取，把上一局残留
    当成本局击杀/阵亡——正是 drain 机制要消除的污染。
    """
    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "data_layer" / "data_process" / "wt_server.py"
    ).read_text(encoding="utf-8")

    assert "if last_evt or last_dmg:" in source
    assert "self._hud_recovery_cursor = None" in source


def test_worker_restart_refuses_to_revive_a_blocked_previous_generation():
    module = _server_module()
    original_join_timeout = module._WORKER_JOIN_TIMEOUT_SECONDS
    module._WORKER_JOIN_TIMEOUT_SECONDS = 0.01

    class BlockingClient:
        def __init__(self):
            self.entered = threading.Event()
            self.release = threading.Event()
            self.fast_thread_ids: list[int] = []

        def get_indicators_with_status(self):
            self.fast_thread_ids.append(threading.get_ident())
            if len(self.fast_thread_ids) == 1:
                self.entered.set()
                self.release.wait(timeout=2.0)
            return False, None, None, None

    client = BlockingClient()
    service = module.TelemetryService(
        client,
        fast_interval=0.01,
        map_interval=10.0,
        event_interval=10.0,
        mapimg_interval=10.0,
    )
    old_fast = None
    try:
        service.start()
        assert client.entered.wait(timeout=1.0)
        old_fast = next(thread for thread in service._threads if thread.name == "wt-fast")

        service.stop()
        assert old_fast.is_alive()
        assert old_fast in service._threads
        with pytest.raises(RuntimeError, match="telemetry_workers_still_stopping"):
            service.start()

        client.release.set()
        old_fast.join(timeout=1.0)
        assert not old_fast.is_alive()

        service.start()
        time.sleep(0.03)
        service.stop()
        assert len(set(client.fast_thread_ids)) <= 2
    finally:
        client.release.set()
        service.stop()
        if old_fast is not None:
            old_fast.join(timeout=1.0)
        module._WORKER_JOIN_TIMEOUT_SECONDS = original_join_timeout
