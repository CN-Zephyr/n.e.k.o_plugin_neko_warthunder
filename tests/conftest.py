"""把 neko_warthunder 的纯逻辑子包注册成轻量顶层包，绕开会拉 SDK/宿主的包 __init__。

这样单测无需 NEKO 宿主环境即可跑（`uv run pytest -c tests/pytest.ini tests -q`），
只测纯逻辑（contracts / scenario / detectors / arbiter / telemetry 解析）。
"""

from __future__ import annotations

import builtins
import pathlib
import sys
import types

import pytest

_PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent
_TOOLS_DIR = _PLUGIN_DIR / "tools"
_DATA_PROCESS_DIR = _PLUGIN_DIR / "data_layer" / "data_process"

for _path in (_TOOLS_DIR, _DATA_PROCESS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_pkg = types.ModuleType("neko_warthunder")
_pkg.__path__ = [str(_PLUGIN_DIR)]  # type: ignore[attr-defined]
sys.modules["neko_warthunder"] = _pkg


def _install_sdk_stubs() -> None:
    """Prevent the host SDK from initializing user configuration in logic tests."""
    plugin_pkg = types.ModuleType("plugin")
    sdk_pkg = types.ModuleType("plugin.sdk")
    sdk_plugin = types.ModuleType("plugin.sdk.plugin")

    class NekoPluginBase:
        def __init__(self, ctx):
            self.ctx = ctx

    def identity_decorator(*_args, **_kwargs):
        def wrap(obj):
            return obj

        return wrap

    sdk_plugin.NekoPluginBase = NekoPluginBase
    sdk_plugin.neko_plugin = lambda cls: cls
    sdk_plugin.plugin_entry = identity_decorator
    sdk_plugin.lifecycle = identity_decorator
    sdk_plugin.message = identity_decorator
    sdk_plugin.ui = types.SimpleNamespace(context=identity_decorator, action=identity_decorator)
    sdk_plugin.Ok = lambda value=None: value
    sdk_plugin.Err = lambda value=None: value
    sdk_plugin.SdkError = Exception
    plugin_pkg.sdk = sdk_pkg
    sdk_pkg.plugin = sdk_plugin
    sys.modules["plugin"] = plugin_pkg
    sys.modules["plugin.sdk"] = sdk_pkg
    sys.modules["plugin.sdk.plugin"] = sdk_plugin


_install_sdk_stubs()

_ORIGINAL_PRINT = builtins.print
_HOST_MIGRATION_PREFIXES = ("Migrated memory file:", "Migrated memory directory:")


def _route_host_migration_diagnostics(*args, **kwargs):
    """Keep host first-run migration diagnostics out of JSON stdout assertions."""
    is_host_migration = args and isinstance(args[0], str) and args[0].startswith(_HOST_MIGRATION_PREFIXES)
    if kwargs.get("file") is None and is_host_migration:
        kwargs = {**kwargs, "file": sys.stderr}
    return _ORIGINAL_PRINT(*args, **kwargs)


@pytest.fixture(autouse=True)
def _restore_lightweight_plugin_package():
    """Keep tests that load the real plugin package isolated from later tests."""
    builtins.print = _route_host_migration_diagnostics
    yield
    builtins.print = _ORIGINAL_PRINT
    sys.modules["neko_warthunder"] = _pkg
    _install_sdk_stubs()
