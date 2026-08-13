"""把 neko_warthunder 的纯逻辑子包注册成轻量顶层包，绕开会拉 SDK/宿主的包 __init__。

这样单测无需 NEKO 宿主环境即可跑（`uv run pytest -c tests/pytest.ini tests -q`），
只测纯逻辑（contracts / scenario / detectors / arbiter / telemetry 解析）。
"""

from __future__ import annotations

import pathlib
import sys
import types

_PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent
_TOOLS_DIR = _PLUGIN_DIR / "tools"
_DATA_PROCESS_DIR = _PLUGIN_DIR / "data_layer" / "data_process"

for _path in (_TOOLS_DIR, _DATA_PROCESS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_PLUGIN_DIR)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg
