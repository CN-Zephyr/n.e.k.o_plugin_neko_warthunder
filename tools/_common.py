"""Shared plumbing for the offline gate/report tools.

These helpers only remove copy-paste (package bootstrap, `--json` CLI template).
They deliberately contain no gate logic: every safety decision stays in the tool
that owns it, so this module can never weaken a release gate.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import types
from typing import Any, Callable


def ensure_package(tool_file: str) -> pathlib.Path:
    """Register the plugin directory as a lightweight top-level package.

    The tools run as standalone scripts (`uv run python tools/x.py`) but import
    plugin modules as `neko_warthunder.*`. Twenty-five tools used to repeat this
    same five-line block verbatim.

    Returns the plugin root so callers can locate sibling files.
    """
    base = pathlib.Path(tool_file).resolve().parent.parent
    if "neko_warthunder" not in sys.modules:
        pkg = types.ModuleType("neko_warthunder")
        pkg.__path__ = [str(base)]  # type: ignore[attr-defined]
        sys.modules["neko_warthunder"] = pkg
    return base


def run_gate_cli(
    *,
    description: str,
    run_gate: Callable[[], dict[str, Any]],
    render_text: Callable[[dict[str, Any]], str],
    argv: list[str] | None = None,
    pass_status: str = "pass",
    add_arguments: Callable[[argparse.ArgumentParser], None] | None = None,
    run_with_args: Callable[[argparse.Namespace], dict[str, Any]] | None = None,
    json_kwargs: dict[str, Any] | None = None,
) -> int:
    """The `--json` / text / exit-code contract shared by the gate tools.

    Exit code is 0 only when ``result["status"] == pass_status``; every gate
    keeps its own notion of what passing means by returning that status.
    ``json_kwargs`` preserves each tool's existing serialization (most use
    ``sort_keys=True``; a couple emit ``indent=2``) so stdout stays byte-identical.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    if add_arguments is not None:
        add_arguments(parser)
    args = parser.parse_args(argv)

    result = run_with_args(args) if run_with_args is not None else run_gate()
    if args.json:
        dump_kwargs: dict[str, Any] = {"ensure_ascii": False, "sort_keys": True}
        if json_kwargs is not None:
            dump_kwargs = {"ensure_ascii": False, **json_kwargs}
        print(json.dumps(result, **dump_kwargs))
    else:
        print(render_text(result), end="")
    return 0 if result.get("status") == pass_status else 1


def dedupe(items: list[str]) -> list[str]:
    """Order-preserving de-duplication (was hand-rolled in seven tools)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
