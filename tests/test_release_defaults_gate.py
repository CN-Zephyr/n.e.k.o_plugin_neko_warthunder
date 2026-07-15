"""Release-safe default gate tests."""

from __future__ import annotations

import contextlib
import io
import json


def test_release_defaults_gate_passes_with_conservative_defaults():
    from neko_warthunder.tools import release_defaults_gate

    result = release_defaults_gate.run_gate()

    assert result["status"] == "pass"
    assert result["failures"] == []
    assert result["policy"] == {
        "dry_run_first": True,
        "free_text_real_output_allowed": False,
        "v2_live_verified_real_output_enabled": False,
        "debug_timeline_enabled": False,
        "plugin_reply_hint_enabled": True,
        "plugin_owned_battle_output_enabled": False,
        "plugin_owned_urgent_output_enabled": False,
        "plugin_owned_blind_output_enabled": False,
        "user_chat_quiet_window_enabled": True,
        "battle_output_quiet_window_enabled": True,
        "broadcast_frequency": "standard",
        "broadcast_categories_default_enabled": True,
        "critical_safety_always_enabled": True,
        "raw_text_printed": False,
    }
    assert {item["name"] for item in result["checks"]} >= {
        "default_dry_run_true",
        "v2_live_verified_real_output_default_closed",
        "debug_timeline_default_closed",
        "plugin_reply_hint_default_enabled",
        "plugin_owned_battle_output_default_closed",
        "plugin_owned_urgent_output_default_closed",
        "plugin_owned_blind_output_default_closed",
        "real_output_backpressure_enabled",
        "kill_coalescing_enabled",
        "user_chat_quiet_window_enabled",
        "battle_output_quiet_window_enabled",
        "broadcast_frequency_default_standard",
        "broadcast_categories_default_enabled",
        "takeoff_runway_guard_enabled",
        "data_layer_default_url_is_local_8112",
    }


def test_release_defaults_gate_cli_json_is_machine_readable():
    from neko_warthunder.tools import release_defaults_gate

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = release_defaults_gate.main(["--json"])

    payload = json.loads(output.getvalue())

    assert rc == 0
    assert payload["status"] == "pass"
    assert payload["policy"]["dry_run_first"] is True
    assert payload["policy"]["v2_live_verified_real_output_enabled"] is False


def test_release_defaults_gate_cli_text_names_closed_defaults():
    from neko_warthunder.tools import release_defaults_gate

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = release_defaults_gate.main([])

    text = output.getvalue()

    assert rc == 0
    assert "status: pass" in text
    assert "dry_run_first=true" in text
    assert "free_text_real_output_allowed=false" in text
    assert "v2_live_verified_real_output_enabled=false" in text
