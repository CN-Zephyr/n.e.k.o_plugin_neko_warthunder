"""Validate a built ``.neko-plugin`` artifact without installing it.

The gate checks package identity, required runtime files, path safety, and the
absence of development-only caches, tests, docs, samples, and local logs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import tomllib
import zipfile
from typing import Any

REQUIRED_PLUGIN_FILES = (
    "plugin.toml",
    "pyproject.toml",
    "__init__.py",
    "adapters/dispatch_observer.py",
    "adapters/event_delivery.py",
    "ui/panel.tsx",
    "data_layer/data_process/wt_server.py",
    "data_layer/data_process/vehicle_profiles.json",
    "i18n/en.json",
    "i18n/es.json",
    "i18n/ja.json",
    "i18n/ko.json",
    "i18n/pt.json",
    "i18n/ru.json",
    "i18n/zh-CN.json",
    "i18n/zh-TW.json",
)

FORBIDDEN_DIR_NAMES = frozenset(
    {
        ".git",
        ".github",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vscode",
        "__pycache__",
        "captures",
        "docs",
        "local_samples",
        "local_test_logs",
        "maps",
        "records",
        "tests",
        "tools",
    }
)

FORBIDDEN_FILE_NAMES = frozenset(
    {
        ".runtime_state.json",
        "PROJECT_STATUS.md",
        "README.md",
        "uv.lock",
    }
)


def run_gate(package_path: str | pathlib.Path, *, expected_plugin_id: str = "neko_warthunder") -> dict[str, Any]:
    package = pathlib.Path(package_path).expanduser().resolve()
    failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    if not package.is_file():
        failures.append({"name": "package_exists", "detail": "package file is missing"})
        return _result(package, checks, failures)

    try:
        with zipfile.ZipFile(package) as archive:
            names = {info.filename.rstrip("/") for info in archive.infolist() if not info.is_dir()}
            manifest = _read_manifest(archive, failures)
    except (OSError, zipfile.BadZipFile) as exc:
        failures.append({"name": "package_readable", "detail": type(exc).__name__})
        return _result(package, checks, failures)

    plugin_id = str(manifest.get("id") or "")
    _check(checks, failures, "plugin_id", plugin_id == expected_plugin_id, plugin_id or "missing")
    _check(checks, failures, "package_type", manifest.get("package_type") == "plugin", str(manifest.get("package_type") or "missing"))

    plugin_prefix = f"payload/plugins/{expected_plugin_id}/"
    required = {"manifest.toml", "metadata.toml", *(plugin_prefix + item for item in REQUIRED_PLUGIN_FILES)}
    missing = sorted(required - names)
    _check(checks, failures, "required_runtime_files", not missing, missing)

    unsafe_paths = sorted(name for name in names if _is_unsafe_archive_path(name))
    _check(checks, failures, "archive_paths_safe", not unsafe_paths, unsafe_paths)

    development_entries = sorted(name for name in names if _is_development_entry(name, plugin_prefix))
    _check(checks, failures, "development_files_excluded", not development_entries, development_entries)

    result = _result(package, checks, failures)
    result.update(
        {
            "plugin_id": plugin_id or None,
            "entry_count": len(names),
            "missing_required": missing,
            "development_entries": development_entries,
            "unsafe_paths": unsafe_paths,
        }
    )
    return result


def _read_manifest(archive: zipfile.ZipFile, failures: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        raw = archive.read("manifest.toml")
        return tomllib.loads(raw.decode("utf-8"))
    except KeyError:
        failures.append({"name": "manifest_readable", "detail": "manifest.toml is missing"})
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        failures.append({"name": "manifest_readable", "detail": type(exc).__name__})
    return {}


def _is_unsafe_archive_path(name: str) -> bool:
    path = pathlib.PurePosixPath(name.replace("\\", "/"))
    return path.is_absolute() or ".." in path.parts


def _is_development_entry(name: str, plugin_prefix: str) -> bool:
    if not name.startswith(plugin_prefix):
        return False
    relative = pathlib.PurePosixPath(name[len(plugin_prefix) :])
    return any(part in FORBIDDEN_DIR_NAMES for part in relative.parts) or relative.name in FORBIDDEN_FILE_NAMES


def _check(
    checks: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: Any,
) -> None:
    check = {"name": name, "status": "pass" if passed else "fail", "detail": detail}
    checks.append(check)
    if not passed:
        failures.append(check)


def _result(package: pathlib.Path, checks: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "pass" if not failures else "fail",
        "package": str(package),
        "checks": checks,
        "failures": failures,
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder package artifact gate",
        f"status: {result['status']}",
        f"package: {result['package']}",
    ]
    for check in result.get("checks") or []:
        lines.append(f"- {check['name']}: {check['status']}")
    if result.get("failures"):
        lines.append("failures:")
        for failure in result["failures"]:
            lines.append(f"- {failure['name']}: {failure.get('detail')}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a built neko_warthunder package artifact.")
    parser.add_argument("package", help="Path to the .neko-plugin artifact.")
    parser.add_argument("--plugin-id", default="neko_warthunder", help="Expected plugin id.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = run_gate(args.package, expected_plugin_id=args.plugin_id)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(result), end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
