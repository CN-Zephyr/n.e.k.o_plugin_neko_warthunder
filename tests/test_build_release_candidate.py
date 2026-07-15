"""Offline release-candidate builder contract tests."""

from __future__ import annotations

import datetime as dt


def _write_plugin_manifest(root, version="0.1.0"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.toml").write_text(
        f'[plugin]\nid = "neko_warthunder"\nversion = "{version}"\n',
        encoding="utf-8",
    )


def _write_installed_tree(root, profile_root=None):
    from neko_warthunder.tools import build_release_candidate

    for relative in build_release_candidate.INSTALLED_REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")
    for locale in build_release_candidate.LOCALE_NAMES:
        path = root / "i18n" / f"{locale}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    if profile_root is not None:
        profile_root.mkdir(parents=True, exist_ok=True)
        (profile_root / "default.toml").write_text("[profile]\n", encoding="utf-8")


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
    profile = tmp_path / "profiles" / "neko_warthunder"
    _write_installed_tree(installed, profile)

    result = build_release_candidate.validate_installed_tree(installed, profile)

    assert result["status"] == "pass"
    assert result["failures"] == []


def test_release_candidate_install_gate_rejects_missing_locale_and_cache(tmp_path):
    from neko_warthunder.tools import build_release_candidate

    installed = tmp_path / "neko_warthunder"
    profile = tmp_path / "profiles" / "neko_warthunder"
    _write_installed_tree(installed, profile)
    (installed / "i18n" / "ja.json").unlink()
    cache = installed / ".ruff_cache" / "entry"
    cache.parent.mkdir()
    cache.write_text("cache", encoding="utf-8")

    (profile / "default.toml").unlink()

    result = build_release_candidate.validate_installed_tree(installed, profile)

    assert result["status"] == "fail"
    assert result["missing_locales"] == ["ja"]
    assert result["development_entries"] == [".ruff_cache"]
    assert result["profile_default_present"] is False
