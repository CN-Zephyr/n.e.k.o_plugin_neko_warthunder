"""Host boundary gate tests."""

from __future__ import annotations

import contextlib
import io
import json


def _host_core_text() -> str:
    return """
def enqueue_agent_callback(callback):
    return callback

class LLMSessionManager:
    pass
"""


def _host_core_with_warthunder_special_case() -> str:
    return """
_WARTHUNDER_BATTLE_COALESCE_KEY = "neko_warthunder:battle_event"

def _filter_warthunder_callbacks_for_user_quiet_window(callbacks):
    return callbacks

def test_warthunder_user_chat_interference_allows_death_to_replace_stale_warning():
    pass
"""


def _write_host_fixture(root, *, special_case: bool = False):
    core = root / "N.E.K.O" / "main_logic" / "core.py"
    core.parent.mkdir(parents=True)
    core.write_text(
        _host_core_with_warthunder_special_case() if special_case else _host_core_text(),
        encoding="utf-8",
    )
    runtime_plugin = root / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"
    runtime_plugin.mkdir(parents=True)
    return core


def _write_runtime_sync_sentinels(root, host_contract_gate, *, marker: str):
    for relative_path in host_contract_gate.RUNTIME_SYNC_SENTINELS:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative_path.as_posix()}::{marker}\n", encoding="utf-8")


def test_host_contract_gate_passes_clean_host_boundary(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    _write_host_fixture(tmp_path)
    runtime_plugin = tmp_path / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"

    payload = host_contract_gate.run_gate(tmp_path / "N.E.K.O", require_host=True, plugin_root=runtime_plugin)

    assert payload["status"] == "pass"
    assert payload["failures"] == []
    assert {item["name"] for item in payload["requirements"]} == {
        "no_warthunder_specific_host_speech_hooks",
        "host_runtime_plugin_is_current",
    }
    assert payload["policy"]["starts_services"] is False
    assert payload["policy"]["reads_raw_chat_or_telemetry"] is False


def test_host_contract_gate_fails_when_host_has_warthunder_speech_special_case(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    _write_host_fixture(tmp_path, special_case=True)
    runtime_plugin = tmp_path / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"

    payload = host_contract_gate.run_gate(tmp_path / "N.E.K.O", require_host=True, plugin_root=runtime_plugin)

    assert payload["status"] == "fail"
    assert {
        "requirement": "no_warthunder_specific_host_speech_hooks",
        "forbidden": "_WARTHUNDER_",
        "reason": "all War Thunder speech timing and reply shaping must stay inside the plugin",
    } in payload["failures"]
    assert "forbidden_present" in host_contract_gate.render_text(payload)


def test_host_contract_gate_passes_synced_runtime_copy(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    _write_host_fixture(tmp_path)
    standalone_plugin = tmp_path / "standalone-plugin"
    runtime_plugin = tmp_path / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"
    _write_runtime_sync_sentinels(standalone_plugin, host_contract_gate, marker="same")
    _write_runtime_sync_sentinels(runtime_plugin, host_contract_gate, marker="same")

    payload = host_contract_gate.run_gate(
        tmp_path / "N.E.K.O",
        require_host=True,
        plugin_root=standalone_plugin,
    )

    assert payload["status"] == "pass"
    runtime_check = payload["requirements"][-1]
    assert runtime_check["name"] == "host_runtime_plugin_is_current"
    assert runtime_check["mode"] == "synced_runtime_copy"


def test_host_contract_gate_fails_when_runtime_plugin_is_stale_copy(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    _write_host_fixture(tmp_path)
    standalone_plugin = tmp_path / "standalone-plugin"
    runtime_plugin = tmp_path / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"
    _write_runtime_sync_sentinels(standalone_plugin, host_contract_gate, marker="new")
    _write_runtime_sync_sentinels(runtime_plugin, host_contract_gate, marker="old")

    payload = host_contract_gate.run_gate(
        tmp_path / "N.E.K.O",
        require_host=True,
        plugin_root=standalone_plugin,
    )

    assert payload["status"] == "fail"
    assert payload["failures"][-1]["requirement"] == "host_runtime_plugin_is_current"
    assert "differs from standalone plugin" in payload["failures"][-1]["missing"]
    assert "differs from standalone plugin" in host_contract_gate.render_text(payload)


def test_host_contract_gate_missing_host_is_nonblocking_by_default(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    payload = host_contract_gate.run_gate(tmp_path / "missing-host")

    assert payload["status"] == "missing_host"
    assert payload["policy"]["missing_host_blocks_release"] is False


def test_host_contract_gate_require_host_blocks_missing_checkout(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    payload = host_contract_gate.run_gate(tmp_path / "missing-host", require_host=True)

    assert payload["status"] == "fail"
    assert payload["policy"]["missing_host_blocks_release"] is True
    assert payload["failures"][0]["requirement"] == "host_checkout"


def test_host_contract_gate_cli_json(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    _write_host_fixture(tmp_path)
    runtime_plugin = tmp_path / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = host_contract_gate.main(
            [
                "--host-root",
                str(tmp_path / "N.E.K.O"),
                "--plugin-root",
                str(runtime_plugin),
                "--require-host",
                "--json",
            ]
        )

    payload = json.loads(output.getvalue())
    assert rc == 0
    assert payload["status"] == "pass"
