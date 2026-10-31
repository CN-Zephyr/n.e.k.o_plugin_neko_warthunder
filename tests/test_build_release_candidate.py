"""Offline release-candidate builder contract tests."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import types
import zipfile
from pathlib import Path


def test_release_candidate_subprocess_decodes_utf8_output(tmp_path):
    from neko_warthunder.tools import build_release_candidate

    completed = build_release_candidate._run(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write('发布门禁通过 ✓'.encode('utf-8'))"], cwd=tmp_path,
    )
    assert completed.stdout.strip() == "发布门禁通过 ✓"


def _write_plugin_manifest(root, version="0.1.0"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.toml").write_text(
        f'[plugin]\nid = "neko_warthunder"\nversion = "{version}"\n',
        encoding="utf-8",
    )


def _write_installed_tree(root):
    from neko_warthunder.tools import build_release_candidate

    for relative in build_release_candidate.INSTALLED_REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")
    for locale in build_release_candidate.LOCALE_NAMES:
        path = root / "i18n" / f"{locale}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")


def test_release_candidate_default_output_uses_version_and_date(tmp_path):
    from neko_warthunder.tools import build_release_candidate

    source = tmp_path / "plugin-source"
    _write_plugin_manifest(source, "1.2.3")

    output = build_release_candidate.default_output_path(source, today=dt.date(2026, 7, 15))

    assert output == tmp_path / "dist" / "neko_warthunder-1.2.3-20260715-offline-rc.neko-plugin"


def test_release_candidate_command_uses_official_release_check(tmp_path):
    from neko_warthunder.tools import build_release_candidate

    command = build_release_candidate.release_check_command(tmp_path / "source", tmp_path / "stage", skip_tests=True)

    assert command[:6] == ["uv", "run", "python", "-m", "plugin.neko_plugin_cli.cli", "check"]
    assert "--release" in command
    assert "--target-dir" in command
    assert command[-1] == "--skip-tests"


def test_release_candidate_install_gate_accepts_complete_runtime_tree(tmp_path):
    from neko_warthunder.tools import build_release_candidate

    installed = tmp_path / "neko_warthunder"
    _write_installed_tree(installed)

    result = build_release_candidate.validate_installed_tree(installed)

    assert result["status"] == "pass"
    assert result["failures"] == []


def test_release_candidate_install_gate_rejects_missing_locale_and_cache(tmp_path):
    from neko_warthunder.tools import build_release_candidate

    installed = tmp_path / "neko_warthunder"
    _write_installed_tree(installed)
    (installed / "i18n" / "ja.json").unlink()
    cache = installed / ".ruff_cache" / "entry"
    cache.parent.mkdir()
    cache.write_text("cache", encoding="utf-8")

    result = build_release_candidate.validate_installed_tree(installed)

    assert result["status"] == "fail"
    assert result["missing_locales"] == ["ja"]
    assert result["development_entries"] == [".ruff_cache"]


def test_release_candidate_build_accepts_code_only_install_contract(tmp_path, monkeypatch):
    """Current SDK deploys code and returns no exported profile directory."""
    from neko_warthunder.tools import build_release_candidate as builder
    from neko_warthunder.tools.package_artifact_gate import REQUIRED_PLUGIN_FILES

    source = tmp_path / "source"
    _write_plugin_manifest(source)
    host = tmp_path / "host"
    cli = host / "plugin/neko_plugin_cli/cli.py"
    cli.parent.mkdir(parents=True)
    cli.touch()
    output = tmp_path / "dist/rc.neko-plugin"
    payload_hash = "a" * 64
    steps = []

    def code_only_sdk(command, *, cwd):
        steps.append(command)
        assert cwd == host
        if "--release" in command:
            stage = Path(command[command.index("--target-dir") + 1])
            with zipfile.ZipFile(stage / "neko_warthunder.neko-plugin", "w") as archive:
                archive.writestr("manifest.toml", 'id = "neko_warthunder"\npackage_type = "plugin"\n')
                archive.writestr("metadata.toml", "")
                for rel in REQUIRED_PLUGIN_FILES:
                    archive.writestr(f"payload/plugins/neko_warthunder/{rel}", "fixture")
        else:
            # Execute the actual verification/install script against a code-only SDK
            # fixture, so its API arguments and lack of profile exports are tested.
            sdk = types.ModuleType("plugin.neko_plugin_cli.core")

            def inspect_package(package):
                return types.SimpleNamespace(payload_hash_verified=True, payload_hash=payload_hash)

            def install_package(package, *, plugins_root, on_conflict):
                assert on_conflict == "fail"
                _write_installed_tree(Path(plugins_root) / "neko_warthunder")
                return types.SimpleNamespace(payload_hash_verified=True, profile_dir=None)

            sdk.inspect_package = inspect_package
            sdk.install_package = install_package
            with monkeypatch.context() as patch:
                patch.setitem(sys.modules, "plugin.neko_plugin_cli.core", sdk)
                patch.setattr(sys, "argv", ["-c", *command[5:]])
                exec(command[4], {"__name__": "__main__"})
        return subprocess.CompletedProcess(command, 0, stdout=f"payload_hash={payload_hash}\n")

    monkeypatch.setattr(builder, "_run", code_only_sdk)
    result = builder.build_release_candidate(source_root=source, host_root=host, output_path=output)
    assert result["status"] == "pass" and output.is_file()
    assert result["tests"] == "passed"
    assert result["checks"]["temporary_install_smoke"] == "pass"
    assert result["payload_hash"] == payload_hash
    assert len(steps) == 2
