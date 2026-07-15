"""Built package artifact gate tests."""

from __future__ import annotations

import contextlib
import io
import json
import zipfile


def _write_package(path, *, extra_entries: tuple[str, ...] = (), omitted: tuple[str, ...] = ()):
    from neko_warthunder.tools import package_artifact_gate

    prefix = "payload/plugins/neko_warthunder/"
    entries = {
        "manifest.toml": 'schema_version = "1.0"\npackage_type = "plugin"\nid = "neko_warthunder"\n',
        "metadata.toml": '[payload]\nhash_algorithm = "sha256"\nhash = "test"\n',
    }
    entries.update({prefix + relative: "test" for relative in package_artifact_gate.REQUIRED_PLUGIN_FILES})
    for name in omitted:
        entries.pop(name, None)
    for name in extra_entries:
        entries[name] = "development cache"

    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def test_package_artifact_gate_accepts_clean_runtime_package(tmp_path):
    from neko_warthunder.tools import package_artifact_gate

    package = tmp_path / "clean.neko-plugin"
    _write_package(package)

    result = package_artifact_gate.run_gate(package)

    assert result["status"] == "pass"
    assert result["failures"] == []
    assert result["missing_required"] == []
    assert result["development_entries"] == []


def test_package_artifact_gate_rejects_development_cache(tmp_path):
    from neko_warthunder.tools import package_artifact_gate

    package = tmp_path / "dirty.neko-plugin"
    cache_entry = "payload/plugins/neko_warthunder/.ruff_cache/0.15.4/cache-entry"
    _write_package(package, extra_entries=(cache_entry,))

    result = package_artifact_gate.run_gate(package)

    assert result["status"] == "fail"
    assert result["development_entries"] == [cache_entry]
    assert any(item["name"] == "development_files_excluded" for item in result["failures"])


def test_package_artifact_gate_rejects_missing_runtime_file(tmp_path):
    from neko_warthunder.tools import package_artifact_gate

    package = tmp_path / "incomplete.neko-plugin"
    missing = "payload/plugins/neko_warthunder/ui/panel.tsx"
    _write_package(package, omitted=(missing,))

    result = package_artifact_gate.run_gate(package)

    assert result["status"] == "fail"
    assert result["missing_required"] == [missing]


def test_package_artifact_gate_cli_json_is_machine_readable(tmp_path):
    from neko_warthunder.tools import package_artifact_gate

    package = tmp_path / "clean.neko-plugin"
    _write_package(package)
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        rc = package_artifact_gate.main([str(package), "--json"])

    payload = json.loads(output.getvalue())
    assert rc == 0
    assert payload["status"] == "pass"
    assert payload["plugin_id"] == "neko_warthunder"
