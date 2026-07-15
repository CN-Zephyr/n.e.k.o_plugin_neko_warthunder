"""Offline gate for release-safe default configuration.

This helper proves the plugin still starts in a conservative release posture:
dry-run first, unverified V2 real output disabled, debug timeline disabled, and
real output queue guards enabled. It is intentionally no-host and no-data-layer.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import types
from typing import Any

_BASE = pathlib.Path(__file__).resolve().parent.parent
if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg

from neko_warthunder.core.contracts import WtConfig  # noqa: E402


def run_gate() -> dict[str, Any]:
    defaults = WtConfig()
    empty_mapping = WtConfig.from_mapping({})
    checks = _checks(defaults, empty_mapping)
    failures = [item for item in checks if item["status"] != "pass"]
    return {
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
        "policy": {
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
        },
    }


def _checks(defaults: WtConfig, empty_mapping: WtConfig) -> list[dict[str, Any]]:
    return [
        _expect("default_dry_run_true", defaults.dry_run is True and empty_mapping.dry_run is True),
        _expect(
            "v2_live_verified_real_output_default_closed",
            defaults.v2_live_verified_real_output_enabled is False
            and empty_mapping.v2_live_verified_real_output_enabled is False,
        ),
        _expect(
            "debug_timeline_default_closed",
            defaults.observability_enabled is False
            and empty_mapping.observability_enabled is False
            and defaults.observability_include_prompt_preview is False
            and empty_mapping.observability_include_prompt_preview is False,
        ),
        _expect(
            "plugin_reply_hint_default_enabled",
            defaults.plugin_reply_hint_enabled is True and empty_mapping.plugin_reply_hint_enabled is True,
        ),
        _expect(
            "plugin_owned_battle_output_default_closed",
            defaults.plugin_owned_battle_output_enabled is False
            and empty_mapping.plugin_owned_battle_output_enabled is False,
        ),
        _expect(
            "plugin_owned_urgent_output_default_closed",
            defaults.plugin_owned_urgent_output_enabled is False
            and empty_mapping.plugin_owned_urgent_output_enabled is False,
        ),
        _expect(
            "plugin_owned_blind_output_default_closed",
            defaults.plugin_owned_blind_output_enabled is False
            and empty_mapping.plugin_owned_blind_output_enabled is False,
        ),
        _expect(
            "real_output_backpressure_enabled",
            defaults.output_backpressure_seconds > 0
            and empty_mapping.output_backpressure_seconds > 0
            and defaults.output_event_max_age_seconds > 0
            and empty_mapping.output_event_max_age_seconds > 0,
        ),
        _expect(
            "kill_coalescing_enabled",
            defaults.kill_coalesce_window_seconds > 0 and empty_mapping.kill_coalesce_window_seconds > 0,
        ),
        _expect(
            "user_chat_quiet_window_enabled",
            defaults.user_chat_quiet_window_seconds > 0 and empty_mapping.user_chat_quiet_window_seconds > 0,
        ),
        _expect(
            "battle_output_quiet_window_enabled",
            defaults.battle_output_quiet_window_seconds > 0 and empty_mapping.battle_output_quiet_window_seconds > 0,
        ),
        _expect(
            "broadcast_frequency_default_standard",
            defaults.broadcast_frequency == "standard" and empty_mapping.broadcast_frequency == "standard",
        ),
        _expect(
            "broadcast_categories_default_enabled",
            all(defaults.broadcast_categories.values()) and all(empty_mapping.broadcast_categories.values()),
        ),
        _expect(
            "takeoff_runway_guard_enabled",
            defaults.takeoff_low_alt_grace_seconds > 0
            and defaults.takeoff_radio_altitude_enter_m >= 0
            and defaults.takeoff_radio_altitude_exit_m > defaults.takeoff_radio_altitude_enter_m,
        ),
        _expect(
            "data_layer_default_url_is_local_8112",
            defaults.data_layer_url == "http://127.0.0.1:8112"
            and empty_mapping.data_layer_url == "http://127.0.0.1:8112",
        ),
    ]


def _expect(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "status": "pass" if ok else "fail"}


def render_text(result: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder release defaults gate",
        f"status: {result['status']}",
        "policy: dry_run_first=true, free_text_real_output_allowed=false, v2_live_verified_real_output_enabled=false",
    ]
    for check in result.get("checks") or []:
        lines.append(f"- {check['name']}: {check['status']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check release-safe default configuration.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = run_gate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(result), end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
