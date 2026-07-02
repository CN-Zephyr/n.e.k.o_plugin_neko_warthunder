"""Host compatibility gate tests."""

from __future__ import annotations

import contextlib
import io
import json


def _host_core_text() -> str:
    return '''
_WARTHUNDER_BATTLE_COALESCE_KEY = "neko_warthunder:battle_event"
_WARTHUNDER_USER_INPUT_QUIET_WINDOW_SECONDS = 10.0
_WARTHUNDER_ALWAYS_ALLOW_DURING_USER_INPUT = frozenset({"you_died"})
_SHORT_TTS_REPLY_CONTRACT = "short_tts_line"

def _render_short_tts_reply_contract_instruction():
    pass

def _shape_short_tts_reply_text(text, metadata, *, used_chars=0):
    metadata["short_tts_reply_total_output_chars"] = used_chars
    metadata["short_tts_reply_complete"] = True
    return text

def _is_short_tts_reply_complete_metadata(metadata):
    return bool(metadata.get("short_tts_reply_complete"))

def _callback_coalesce_key(callback):
    metadata = callback.get("metadata") or {}
    return metadata.get("coalesce_key") or callback.get("coalesce_key") or ""

def _render_pending_extra_replies_by_origin(task_entries, event_entries):
    return _render_short_tts_reply_contract_instruction(task_entries + event_entries)

def enqueue_agent_callback(callback):
    metadata = callback.get("metadata")
    extra_reply = {}
    coalesce_key = _callback_coalesce_key(callback)
    if coalesce_key:
        extra_reply["coalesce_key"] = coalesce_key
    extra_reply["metadata"] = dict(metadata)
    return extra_reply

class LLMSessionManager:
    def __init__(self):
        self._short_tts_reply_completed_for_turn = False
        self._short_tts_reply_chars_for_turn = 0

    def _coalesce_pending_agent_callback_queues(self, callback):
        callback.setdefault("coalesce_key", "same-source")
        resolve_callback_delivery_ack(queued_cb, False)
        self.pending_extra_replies = []

    def _mark_warthunder_user_input_quiet_window(self):
        pass

    def _warthunder_user_input_quiet_window_active(self):
        return False

    def _filter_warthunder_callbacks_for_user_quiet_window(self, callbacks, *, reason="passive_drain"):
        reason="proactive_trigger"
        reason="proactive_release"
        return callbacks

    def _filter_warthunder_extra_replies_for_user_quiet_window(self, replies, *, reason="hot_swap_prime"):
        return replies
'''


def _write_host_fixture(root):
    core = root / "N.E.K.O" / "main_logic" / "core.py"
    core.parent.mkdir(parents=True)
    core.write_text(_host_core_text(), encoding="utf-8")
    runtime_plugin = root / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"
    runtime_plugin.mkdir(parents=True)
    tests = root / "N.E.K.O" / "tests" / "unit" / "test_proactive_sm_integration.py"
    tests.parent.mkdir(parents=True)
    tests.write_text(
        "def test_warthunder_user_chat_interference_allows_death_to_replace_stale_warning():\n"
        "    pass\n",
        encoding="utf-8",
    )
    return core


def _write_runtime_sync_sentinels(root, host_contract_gate, *, marker: str):
    for relative_path in host_contract_gate.RUNTIME_SYNC_SENTINELS:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative_path.as_posix()}::{marker}\n", encoding="utf-8")


def test_host_contract_gate_passes_complete_host(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    _write_host_fixture(tmp_path)
    runtime_plugin = tmp_path / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"

    payload = host_contract_gate.run_gate(tmp_path / "N.E.K.O", require_host=True, plugin_root=runtime_plugin)

    assert payload["status"] == "pass"
    assert payload["failures"] == []
    assert {item["name"] for item in payload["requirements"]} == {
        "short_tts_contract_consumed",
        "voice_hot_swap_short_tts_prompted",
        "warthunder_metadata_preserved_to_extra_reply",
        "pending_callback_coalesce_consumed",
        "warthunder_user_input_quiet_window",
        "warthunder_quiet_window_call_sites",
        "host_runtime_plugin_is_current",
    }
    assert payload["policy"]["starts_services"] is False
    assert payload["policy"]["reads_raw_chat_or_telemetry"] is False


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


def test_host_contract_gate_fails_when_short_tts_consumption_missing(tmp_path):
    from neko_warthunder.tools import host_contract_gate

    core = _write_host_fixture(tmp_path)
    core.write_text(_host_core_text().replace("_short_tts_reply_chars_for_turn", "old_counter"), encoding="utf-8")
    runtime_plugin = tmp_path / "N.E.K.O" / "plugin" / "plugins" / "neko_warthunder"

    payload = host_contract_gate.run_gate(tmp_path / "N.E.K.O", require_host=True, plugin_root=runtime_plugin)

    assert payload["status"] == "fail"
    assert {
        "requirement": "short_tts_contract_consumed",
        "missing": "_short_tts_reply_chars_for_turn",
        "reason": "host must turn short_tts_line metadata into short, bounded Lanlan output",
    } in payload["failures"]


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
