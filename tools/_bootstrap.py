"""Import bootstrap shared by standalone development tools."""

from __future__ import annotations

import pathlib
import sys
import types

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS_ROOT = PLUGIN_ROOT / "tools"
DATA_PROCESS_ROOT = PLUGIN_ROOT / "data_layer" / "data_process"

for _path in (TOOLS_ROOT, DATA_PROCESS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

if "neko_warthunder" not in sys.modules:
    _package = types.ModuleType("neko_warthunder")
    _package.__path__ = [str(PLUGIN_ROOT)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _package
