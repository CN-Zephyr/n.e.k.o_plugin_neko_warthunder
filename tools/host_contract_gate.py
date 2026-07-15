"""Optional N.E.K.O host boundary gate for War Thunder output contracts.

The plugin may attach freshness, coalescing, target-session, and short-reply
metadata as a future generic host contract, but it must not require host core
special-cases to shape Lanlan's speech. This gate stays offline and static:
when a local host checkout is available it verifies that War Thunder-specific
speech hooks are absent and that the runtime plugin copy is current.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

_BASE = pathlib.Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Requirement:
    name: str
    snippets: tuple[str, ...]
    reason: str


FORBIDDEN_HOST_SNIPPETS: tuple[Requirement, ...] = (
    Requirement(
        name="no_warthunder_specific_host_speech_hooks",
        reason="all War Thunder speech timing and reply shaping must stay inside the plugin",
        snippets=(
            "_WARTHUNDER_",
            "warthunder_user_input_quiet_window",
            "_filter_warthunder_callbacks_for_user_quiet_window",
            "_filter_warthunder_extra_replies_for_user_quiet_window",
            "neko_warthunder:battle_event",
            "test_warthunder_user_chat_interference_allows_death_to_replace_stale_warning",
        ),
    ),
)


RUNTIME_SYNC_SENTINELS: tuple[pathlib.Path, ...] = (
    pathlib.Path("plugin.toml"),
    pathlib.Path("__init__.py"),
    pathlib.Path("adapters") / "neko_dispatcher.py",
    pathlib.Path("core") / "arbiter.py",
    pathlib.Path("data_layer") / "data process" / "vehicle_profiles.json",
    pathlib.Path("data_layer") / "data process" / "vehicle_profile_vetted_ids.json",
    pathlib.Path("data_layer") / "data process" / "vehicle_profile_identity_aliases.json",
)


def run_gate(
    host_root: str | pathlib.Path | None = None,
    *,
    require_host: bool = False,
    plugin_root: str | pathlib.Path | None = None,
) -> dict[str, Any]:
    host = pathlib.Path(host_root).resolve() if host_root is not None else (_BASE.parent / "N.E.K.O").resolve()
    plugin = pathlib.Path(plugin_root).resolve() if plugin_root is not None else _BASE.resolve()
    main_logic_root = host / "main_logic"
    core_paths = sorted(path for path in main_logic_root.rglob("*.py") if path.is_file())
    runtime_plugin = host / "plugin" / "plugins" / "neko_warthunder"
    test_paths = (
        host / "tests" / "unit" / "test_core_game_route_memory_contract.py",
        host / "tests" / "unit" / "test_callback_instruction_origin.py",
        host / "tests" / "unit" / "test_proactive_sm_integration.py",
    )
    if not core_paths:
        status = "fail" if require_host else "missing_host"
        return {
            "status": status,
            "host_root": str(host),
            "plugin_root": str(plugin),
            "core_path": str(main_logic_root),
            "core_paths": [],
            "runtime_plugin_path": str(runtime_plugin),
            "test_paths": [str(path) for path in test_paths],
            "requirements": [],
            "failures": [
                {
                    "requirement": "host_checkout",
                    "missing": str(main_logic_root),
                    "reason": "host main_logic Python sources were not found",
                }
            ],
            "policy": _policy(require_host=require_host),
        }

    texts = [path.read_text(encoding="utf-8", errors="replace") for path in core_paths]
    for test_path in test_paths:
        if test_path.exists():
            texts.append(test_path.read_text(encoding="utf-8", errors="replace"))
    text = "\n".join(texts)
    checked: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for requirement in FORBIDDEN_HOST_SNIPPETS:
        present = [snippet for snippet in requirement.snippets if snippet in text]
        checked.append(
            {
                "name": requirement.name,
                "status": "pass" if not present else "fail",
                "reason": requirement.reason,
                "forbidden_present": present,
            }
        )
        for snippet in present:
            failures.append(
                {
                    "requirement": requirement.name,
                    "forbidden": snippet,
                    "reason": requirement.reason,
                }
            )
    runtime_plugin_check = _check_runtime_plugin_path(runtime_plugin, plugin)
    checked.append(runtime_plugin_check)
    if runtime_plugin_check["status"] != "pass":
        failures.append(
            {
                "requirement": runtime_plugin_check["name"],
                "missing": runtime_plugin_check["missing"],
                "reason": runtime_plugin_check["reason"],
            }
        )
    return {
        "status": "pass" if not failures else "fail",
        "host_root": str(host),
        "plugin_root": str(plugin),
        "core_path": str(main_logic_root),
        "core_paths": [str(path) for path in core_paths],
        "runtime_plugin_path": str(runtime_plugin),
        "test_paths": [str(path) for path in test_paths],
        "requirements": checked,
        "failures": failures,
        "policy": _policy(require_host=require_host),
    }


def _check_runtime_plugin_path(runtime_plugin: pathlib.Path, plugin_root: pathlib.Path) -> dict[str, Any]:
    reason = (
        "host runtime plugin must either point at this standalone checkout or be a synced runtime copy "
        "for live-test host compatibility"
    )
    name = "host_runtime_plugin_is_current"
    if not runtime_plugin.exists():
        return {
            "name": name,
            "status": "fail",
            "reason": reason,
            "missing": str(runtime_plugin),
        }
    if not plugin_root.exists():
        return {
            "name": name,
            "status": "fail",
            "reason": reason,
            "missing": str(plugin_root),
        }
    try:
        same_path = runtime_plugin.samefile(plugin_root)
    except OSError:
        same_path = False
    if same_path:
        return {
            "name": name,
            "status": "pass",
            "reason": reason,
            "missing": "",
            "mode": "linked_standalone_checkout",
        }

    stale_or_missing: list[str] = []
    for relative_path in RUNTIME_SYNC_SENTINELS:
        runtime_file = runtime_plugin / relative_path
        plugin_file = plugin_root / relative_path
        if not plugin_file.exists():
            stale_or_missing.append(f"{relative_path}: missing in standalone plugin")
            continue
        if not runtime_file.exists():
            stale_or_missing.append(f"{relative_path}: missing in host runtime copy")
            continue
        runtime_text = runtime_file.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        plugin_text = plugin_file.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        if runtime_text != plugin_text:
            stale_or_missing.append(f"{relative_path}: differs from standalone plugin")

    is_current_copy = not stale_or_missing
    return {
        "name": name,
        "status": "pass" if is_current_copy else "fail",
        "reason": reason,
        "missing": "" if is_current_copy else "; ".join(stale_or_missing),
        "mode": "synced_runtime_copy" if is_current_copy else "stale_runtime_copy",
    }


def _policy(*, require_host: bool) -> dict[str, Any]:
    return {
        "host_required": require_host,
        "missing_host_blocks_release": require_host,
        "static_check_only": True,
        "starts_services": False,
        "reads_raw_chat_or_telemetry": False,
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder host contract gate",
        f"status: {payload['status']}",
        f"host_root: {payload['host_root']}",
        f"plugin_root: {payload.get('plugin_root', '')}",
        f"core_path: {payload['core_path']}",
        f"core_files: {len(payload.get('core_paths') or [])}",
        f"runtime_plugin_path: {payload.get('runtime_plugin_path', '')}",
        "test_paths: " + ", ".join(payload.get("test_paths") or []),
        "policy: static offline check; no service startup; no raw chat or telemetry read",
        "",
        "requirements:",
    ]
    for item in payload.get("requirements") or []:
        lines.append(f"- {item['name']}: {item['status']}")
        lines.append(f"  reason: {item['reason']}")
        if item.get("missing"):
            lines.append("  missing: " + _format_missing(item["missing"]))
        if item.get("forbidden_present"):
            lines.append("  forbidden_present: " + _format_missing(item["forbidden_present"]))
    if payload.get("failures"):
        lines.append("")
        lines.append("failures:")
        for failure in payload["failures"]:
            detail = failure.get("missing", failure.get("forbidden", ""))
            lines.append(f"- {failure['requirement']}: {detail}")
    return "\n".join(lines) + "\n"


def _format_missing(missing: Any) -> str:
    if isinstance(missing, str):
        return missing
    return ", ".join(str(item) for item in missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local N.E.K.O host/plugin boundary for battle output hooks.")
    parser.add_argument("--host-root", default=str(_BASE.parent / "N.E.K.O"), help="N.E.K.O host repository root.")
    parser.add_argument("--plugin-root", default=str(_BASE), help="Standalone neko_warthunder plugin repository root.")
    parser.add_argument("--require-host", action="store_true", help="Fail when the host checkout is missing.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    payload = run_gate(args.host_root, require_host=args.require_host, plugin_root=args.plugin_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload), end="")
    return 0 if payload["status"] in {"pass", "missing_host"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
