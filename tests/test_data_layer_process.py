"""Data-layer process ownership contracts for L8 orchestration."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from neko_warthunder.adapters import data_layer_process as module
from neko_warthunder.adapters.data_layer_process import DataLayerProcessManager
from neko_warthunder.core.contracts import WtConfig


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 4321
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return 0


class ExitedProcess:
    def __init__(self, returncode: int = 1) -> None:
        self.pid = 8765
        self.returncode = returncode

    def poll(self):
        return self.returncode


def _fake_plugin_root() -> TemporaryDirectory[str]:
    temp = TemporaryDirectory()
    root = Path(temp.name)
    data_process = root / "data_layer" / "data process"
    data_process.mkdir(parents=True)
    (data_process / "wt_server.py").write_text("# fake server\n", encoding="utf-8")
    return temp


def test_external_data_layer_is_not_terminated_on_shutdown():
    cfg = WtConfig(data_layer_auto_start=True)
    launched: list[Any] = []

    with _fake_plugin_root() as root:
        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: True,
            popen_factory=lambda *args, **kwargs: launched.append((args, kwargs)),
        )

        status = manager.start_if_needed()
        manager.stop()

    assert status["mode"] == "external"
    assert status["started_by_plugin"] is False
    assert status["health"] is True
    assert launched == []
    assert manager.snapshot()["mode"] == "external"


def test_missing_data_layer_is_started_and_owned_by_plugin():
    cfg = WtConfig(data_layer_auto_start=True, data_layer_url="http://127.0.0.1:8112")
    checks = iter([False, True])
    proc = FakeProcess()
    launched: list[list[str]] = []

    with _fake_plugin_root() as root:
        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: next(checks),
            popen_factory=lambda args, **_kwargs: launched.append(list(args)) or proc,
            sleep=lambda _seconds: None,
        )

        status = manager.start_if_needed()
        manager.stop()

    assert status["mode"] == "managed"
    assert status["pid"] == 4321
    assert status["started_by_plugin"] is True
    assert launched
    assert launched[0][-5:] == ["wt_server.py", "--host", "127.0.0.1", "--port", "8112"]
    assert proc.terminated is True
    assert proc.waited is True
    assert proc.killed is False

    remote_cfg = WtConfig(data_layer_auto_start=True, data_layer_url="http://192.0.2.10:8112")
    with _fake_plugin_root() as root:
        remote_manager = DataLayerProcessManager(
            remote_cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: False,
        )
        remote_status = remote_manager.start_if_needed()
    assert remote_status["mode"] == "failed"
    assert remote_status["started_by_plugin"] is False
    assert "managed_data_layer_requires_loopback_url" in remote_status["last_error"]


def test_repeated_start_keeps_managed_process_owned_and_stoppable():
    cfg = WtConfig(data_layer_auto_start=True)
    proc = FakeProcess()

    with _fake_plugin_root() as root:
        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: True,
        )
        manager._process = proc
        manager._started_by_plugin = True
        manager._mode = "managed"

        status = manager.start_if_needed()
        stopped = manager.stop()

    assert status["mode"] == "managed"
    assert status["started_by_plugin"] is True
    assert status["pid"] == proc.pid
    assert proc.terminated is True
    assert stopped["mode"] == "stopped"


def test_data_layer_auto_start_can_be_disabled():
    cfg = WtConfig(data_layer_auto_start=False)

    with _fake_plugin_root() as root:
        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: False,
        )

        status = manager.start_if_needed()

    assert status["mode"] == "missing"
    assert status["started_by_plugin"] is False
    assert status["health"] is False


def test_exited_managed_process_preserves_failure_when_auto_start_is_disabled():
    cfg = WtConfig(data_layer_auto_start=False)

    with _fake_plugin_root() as root:
        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: False,
        )
        manager._process = ExitedProcess(7)
        manager._started_by_plugin = True

        status = manager.start_if_needed()

    assert status["mode"] == "failed"
    assert status["started_by_plugin"] is False
    assert status["last_error"] == "process_exited_before_healthy(exit=7)"


def test_exited_data_layer_reports_stderr_tail():
    cfg = WtConfig(data_layer_auto_start=True, data_layer_startup_timeout_seconds=3)

    with _fake_plugin_root() as root:
        def fake_popen(_args, **kwargs):
            kwargs["stderr"].write("Traceback: port 8112 already in use\n")
            kwargs["stderr"].flush()
            return ExitedProcess(1)

        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: False,
            popen_factory=fake_popen,
            sleep=lambda _seconds: None,
        )

        status = manager.start_if_needed()

    assert status["mode"] == "failed"
    assert status["started_by_plugin"] is True
    assert status["last_error"] == "process_exited_before_healthy(exit=1; Traceback: port 8112 already in use)"
    assert status["stderr_log"].endswith("warthunder_data_layer_8112_stderr.log")
    assert "python" in status["python_cmd"].lower() or status["python_cmd"].lower().startswith("py")


def test_missing_python_runner_uses_embedded_fallback():
    cfg = WtConfig(data_layer_auto_start=True, data_layer_url="http://127.0.0.1:8112")
    checks = iter([False, True])
    proc = FakeProcess()
    embedded_calls: list[tuple[Path, str, int]] = []

    def fake_embedded(data_process_dir: Path, *, host: str, port: int):
        embedded_calls.append((data_process_dir, host, port))
        return proc

    old_python_command_prefixes = module._python_command_prefixes
    old_spawn_embedded_data_layer = module._spawn_embedded_data_layer
    module._python_command_prefixes = lambda: []
    module._spawn_embedded_data_layer = fake_embedded
    try:
        with _fake_plugin_root() as root:
            manager = DataLayerProcessManager(
                cfg,
                plugin_root=Path(root),
                health_check=lambda _url, _timeout: next(checks),
                sleep=lambda _seconds: None,
            )

            status = manager.start_if_needed()
            manager.stop()
    finally:
        module._python_command_prefixes = old_python_command_prefixes
        module._spawn_embedded_data_layer = old_spawn_embedded_data_layer

    assert status["mode"] == "managed"
    assert status["python_cmd"] == "embedded"
    assert embedded_calls
    assert embedded_calls[0][0].name == "data process"
    assert embedded_calls[0][1:] == ("127.0.0.1", 8112)
    assert proc.terminated is True
    assert manager._stdout_handle is None
    assert manager._stderr_handle is None


def test_spawn_failure_closes_log_handles():
    cfg = WtConfig(data_layer_auto_start=True)

    with _fake_plugin_root() as root:
        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: False,
            popen_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("spawn failed")),
        )

        status = manager.start_if_needed()

    assert status["mode"] == "failed"
    assert "spawn failed" in status["last_error"]
    assert manager._stdout_handle is None
    assert manager._stderr_handle is None


def test_runtime_health_observation_updates_snapshot_and_detects_exit():
    cfg = WtConfig(data_layer_auto_start=True)
    checks = iter([False, True])
    proc = FakeProcess()

    with _fake_plugin_root() as root:
        manager = DataLayerProcessManager(
            cfg,
            plugin_root=Path(root),
            health_check=lambda _url, _timeout: next(checks),
            popen_factory=lambda *_args, **_kwargs: proc,
            sleep=lambda _seconds: None,
        )
        assert manager.start_if_needed()["health"] is True

        manager.observe_health(False)
        assert manager.snapshot()["health"] is False
        assert manager.snapshot()["mode"] == "managed"

        proc.returncode = 7
        manager.observe_health(False)

    status = manager.snapshot()
    assert status["mode"] == "failed"
    assert status["started_by_plugin"] is False
    assert status["pid"] is None
    assert status["last_error"] == "process_exited_before_healthy(exit=7)"
