"""Build and validate one offline release-candidate package.

The final artifact is published only after the host release check, package
content gate, official hash verification, and isolated installation smoke all
pass. The command never installs into the operator's real plugin directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import tomllib
import uuid
from typing import Any

try:
    from .package_artifact_gate import run_gate
except ImportError:  # Direct script execution from tools/.
    from package_artifact_gate import run_gate


PLUGIN_ID = "neko_warthunder"
INSTALLED_REQUIRED_FILES = (
    "plugin.toml",
    "pyproject.toml",
    "__init__.py",
    "adapters/dispatch_observer.py",
    "adapters/event_delivery.py",
    "ui/panel.tsx",
    "data_layer/data_process/wt_server.py",
    "i18n/en.json",
    "i18n/zh-CN.json",
)
DEVELOPMENT_DIR_NAMES = frozenset({".pytest_cache", ".ruff_cache", ".venv", "__pycache__"})
LOCALE_NAMES = frozenset({"en", "es", "ja", "ko", "pt", "ru", "zh-CN", "zh-TW"})


def _plugin_version(source_root: pathlib.Path) -> str:
    with (source_root / "plugin.toml").open("rb") as handle:
        data = tomllib.load(handle)
    return str(data["plugin"]["version"])


def default_output_path(source_root: pathlib.Path, *, today: dt.date | None = None) -> pathlib.Path:
    date = today or dt.date.today()
    version = _plugin_version(source_root)
    return source_root.parent / "dist" / f"{PLUGIN_ID}-{version}-{date:%Y%m%d}-offline-rc.neko-plugin"


def release_check_command(
    source_root: pathlib.Path,
    staging_root: pathlib.Path,
    *,
    skip_tests: bool,
) -> list[str]:
    command = [
        "uv",
        "run",
        "python",
        "-m",
        "plugin.neko_plugin_cli.cli",
        "check",
        "--release",
        str(source_root),
        "--target-dir",
        str(staging_root),
    ]
    if skip_tests:
        command.append("--skip-tests")
    return command


def validate_installed_tree(
    installed_plugin: pathlib.Path,
    installed_profile: pathlib.Path | None = None,
) -> dict[str, Any]:
    missing = sorted(relative for relative in INSTALLED_REQUIRED_FILES if not (installed_plugin / relative).is_file())
    locale_dir = installed_plugin / "i18n"
    locales = {path.stem for path in locale_dir.glob("*.json")} if locale_dir.is_dir() else set()
    missing_locales = sorted(LOCALE_NAMES - locales)
    extra_locales = sorted(locales - LOCALE_NAMES)
    development_entries = sorted(
        str(path.relative_to(installed_plugin))
        for path in installed_plugin.rglob("*")
        if path.name in DEVELOPMENT_DIR_NAMES
    )
    failures: list[dict[str, Any]] = []
    if missing:
        failures.append({"name": "installed_runtime_files", "detail": missing})
    if missing_locales or extra_locales:
        failures.append(
            {
                "name": "installed_locales",
                "detail": {"missing": missing_locales, "extra": extra_locales},
            }
        )
    if development_entries:
        failures.append({"name": "installed_development_files", "detail": development_entries})
    profile_default_present = installed_profile is None or (installed_profile / "default.toml").is_file()
    if not profile_default_present:
        failures.append({"name": "installed_default_profile", "detail": "default.toml is missing"})
    return {
        "status": "pass" if not failures else "fail",
        "missing_runtime_files": missing,
        "missing_locales": missing_locales,
        "extra_locales": extra_locales,
        "development_entries": development_entries,
        "profile_default_present": profile_default_present,
        "failures": failures,
    }


def _run(command: list[str], *, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        tail = "\n".join(completed.stdout.splitlines()[-30:])
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{tail}")
    return completed


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _payload_hash(output: str) -> str | None:
    match = re.search(r"(?m)^\s*payload_hash=([0-9a-fA-F]{64})\s*$", output)
    return match.group(1).lower() if match else None


def _publish(staged_package: pathlib.Path, output_path: pathlib.Path, *, force: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        raise FileExistsError(f"output already exists: {output_path}; pass --force to replace it")
    temporary_output = output_path.with_name(f".{output_path.name}.tmp-{uuid.uuid4().hex}")
    try:
        shutil.copy2(staged_package, temporary_output)
        os.replace(temporary_output, output_path)
    finally:
        temporary_output.unlink(missing_ok=True)


def build_release_candidate(
    *,
    source_root: pathlib.Path,
    host_root: pathlib.Path,
    output_path: pathlib.Path,
    skip_tests: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    source_root = source_root.expanduser().resolve()
    host_root = host_root.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not (source_root / "plugin.toml").is_file():
        raise FileNotFoundError(f"plugin.toml is missing under source root: {source_root}")
    if not (host_root / "plugin/neko_plugin_cli/cli.py").is_file():
        raise FileNotFoundError(f"N.E.K.O plugin CLI is missing under host root: {host_root}")
    if output_path.suffix != ".neko-plugin":
        raise ValueError("output path must end with .neko-plugin")
    if output_path.exists() and not force:
        raise FileExistsError(f"output already exists: {output_path}; pass --force to replace it")

    with tempfile.TemporaryDirectory(prefix="neko-warthunder-rc-build-") as temporary:
        temp_root = pathlib.Path(temporary)
        staging_root = temp_root / "staging"
        plugins_root = temp_root / "installed" / "plugins"
        profiles_root = temp_root / "installed" / "profiles"
        staging_root.mkdir(parents=True)
        plugins_root.mkdir(parents=True)
        profiles_root.mkdir(parents=True)

        _run(
            release_check_command(source_root, staging_root, skip_tests=skip_tests),
            cwd=host_root,
        )
        staged_package = staging_root / f"{PLUGIN_ID}.neko-plugin"
        if not staged_package.is_file():
            raise FileNotFoundError(f"release check did not create expected package: {staged_package}")

        artifact_gate = run_gate(staged_package, expected_plugin_id=PLUGIN_ID)
        if artifact_gate["status"] != "pass":
            raise RuntimeError(f"package artifact gate failed: {artifact_gate['failures']}")

        verify_result = _run(
            ["uv", "run", "python", "-m", "plugin.neko_plugin_cli.cli", "verify", str(staged_package)],
            cwd=host_root,
        )
        _run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "plugin.neko_plugin_cli.cli",
                "install",
                str(staged_package),
                "--plugins-root",
                str(plugins_root),
                "--profiles-root",
                str(profiles_root),
                "--on-conflict",
                "fail",
            ],
            cwd=host_root,
        )
        install_gate = validate_installed_tree(
            plugins_root / PLUGIN_ID,
            profiles_root / PLUGIN_ID,
        )
        if install_gate["status"] != "pass":
            raise RuntimeError(f"temporary installation gate failed: {install_gate['failures']}")

        archive_sha256 = _sha256_file(staged_package)
        payload_hash = _payload_hash(verify_result.stdout)
        if payload_hash is None:
            raise RuntimeError("official payload verify did not report a payload hash")
        _publish(staged_package, output_path, force=force)

    return {
        "status": "pass",
        "plugin_id": PLUGIN_ID,
        "version": _plugin_version(source_root),
        "package": str(output_path),
        "package_bytes": output_path.stat().st_size,
        "archive_sha256": archive_sha256,
        "payload_hash": payload_hash,
        "tests": "skipped" if skip_tests else "passed",
        "checks": {
            "official_release_check": "pass",
            "package_artifact_gate": "pass",
            "official_payload_verify": "pass",
            "temporary_install_smoke": "pass",
        },
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder release candidate",
        f"status: {result['status']}",
        f"package: {result['package']}",
        f"bytes: {result['package_bytes']}",
        f"archive_sha256: {result['archive_sha256']}",
        f"payload_hash: {result['payload_hash'] or '-'}",
        f"tests: {result['tests']}",
    ]
    lines.extend(f"- {name}: {status}" for name, status in result["checks"].items())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    source_default = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build and validate a neko_warthunder offline RC package.")
    parser.add_argument("--source-root", type=pathlib.Path, default=source_default)
    parser.add_argument("--host-root", type=pathlib.Path, default=source_default.parent / "N.E.K.O")
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--skip-tests", action="store_true", help="Skip the official release check's pytest run.")
    parser.add_argument("--force", action="store_true", help="Replace an existing output only after all checks pass.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    source_root = args.source_root.expanduser().resolve()
    output_path = args.output or default_output_path(source_root)
    try:
        result = build_release_candidate(
            source_root=source_root,
            host_root=args.host_root,
            output_path=output_path,
            skip_tests=args.skip_tests,
            force=args.force,
        )
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as exc:
        failure = {"status": "fail", "error": str(exc)}
        if args.json:
            print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
        else:
            print(f"release candidate build failed: {exc}")
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
