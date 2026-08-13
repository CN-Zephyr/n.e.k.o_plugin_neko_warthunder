"""Summarize release-candidate gaps from local telemetry samples.

The tool is intentionally read-only and safe: it consumes ignored local
``/api/telemetry`` captures through ``sample_replay`` and emits only aggregate
status, release blockers, and next actions. It never prints raw player names,
HUD text, combat feed text, award text, proximity text, or objective labels.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from neko_warthunder.tools.sample_replay import replay_sample_root

_CHECK_TO_TRACK = {
    "numeric_safety": "v1_numeric_safety",
    "ownership": "v1_owned_combat",
    "free_text_safety": "v1_free_text_output",
    "replay_degrade": "v1_replay_degrade",
    "profile_calibration": "v1_profile_calibration",
    "proximity_awareness": "v2_proximity_objective",
}

_MISSING_ACTIONS = {
    "overspeed_critical": "trigger_overspeed_critical",
    "ownership_fields": "use_v16_combat_feed_ownership_fields",
    "owned_kill_or_death": "capture_owned_kill_or_death",
    "manual_identity": "set_manual_identity_before_capture",
    "combat_feed": "capture_combat_feed_sample",
    "hud_notices": "capture_hud_notice_sample",
    "awards": "capture_awards_sample",
    "replay_true": "capture_replay_true_sample",
    "oil_overheat": "capture_oil_overheat_notice",
    "powertrain_failure": "wait_for_powertrain_profile_or_sample",
    "hud_notice_severity": "verify_hud_notice_severity_mapping",
    "proximity_events": "capture_proximity_sample",
    "generic_enemy_proximity_events": "capture_generic_enemy_proximity_sample",
    "enemy_nearby_trigger": "capture_generic_enemy_proximity_sample",
    "proximity_air_events": "capture_air_proximity_sample",
    "air_threat_candidates": "capture_air_threat_or_situation_sample",
    "air_threat_nearby_trigger": "capture_air_proximity_trigger_sample",
    "proximity_rear_events": "capture_rear_threat_or_six_oclock_sample",
    "rear_threat_candidates": "capture_rear_threat_or_six_oclock_sample",
    "enemy_on_six_trigger": "capture_rear_threat_or_six_oclock_sample",
    "tailing_risk_trigger": "capture_sustained_close_rear_sample",
    "situation": "capture_situation_sample",
    "ground_targets": "capture_ground_target_sample",
    "ground_target_live_sample": "capture_live_ground_target_sample",
    "ground_target_close_candidates": "fly_closer_to_ground_target_sample",
    "ground_target_trigger": "capture_ground_target_trigger_sample",
}


def build_gap_summary(sample_root: str | pathlib.Path, *, player_name: str = "") -> dict[str, Any]:
    root = pathlib.Path(sample_root)
    if not root.exists():
        return {
            "status": "no_sample",
            "sample_root": str(root),
            "tracks": {},
            "remaining_gaps": ["sample_root_missing"],
            "blocked_release_items": ["final_live_claim"],
            "next_actions": ["capture_local_telemetry_sample"],
        }

    report = replay_sample_root(root, player_name=player_name)
    session = report.get("session_summary") or {}
    checks = session.get("validation_checks") or {}
    tracks = _tracks_from_checks(checks)
    remaining_gaps = _remaining_gaps(tracks)
    sample_unproven_items = _sample_unproven_items(tracks)
    blocked_release_items = _blocked_release_items(tracks)
    next_actions = _dedupe(
        list(session.get("next_steps") or [])
        + [action for track in tracks.values() for action in track.get("next_actions", [])]
    )

    return {
        "status": "ready_for_final_live_smoke" if not blocked_release_items else "needs_more_samples",
        "sample_root": str(root),
        "frames": int(report.get("frames") or 0),
        "tracks": tracks,
        "remaining_gaps": remaining_gaps,
        "sample_unproven_items": sample_unproven_items,
        "blocked_release_items": blocked_release_items,
        "next_actions": next_actions,
        "safety": {
            "raw_text_printed": False,
            "free_text_real_output_allowed": False,
            "generic_kill_death_allowed": True,
        },
    }


def _tracks_from_checks(checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    tracks: dict[str, dict[str, Any]] = {}
    for check_name, track_name in _CHECK_TO_TRACK.items():
        check = checks.get(check_name) or {}
        status = _track_status(check_name, check)
        missing = list(check.get("missing") or [])
        tracks[track_name] = {
            "status": status,
            "source_check": check_name,
            "missing": missing,
            "next_actions": [_MISSING_ACTIONS.get(item, f"capture_{item}") for item in missing],
        }
        if check_name == "proximity_awareness" and check.get("capability_evidence"):
            tracks[track_name]["capability_evidence"] = check.get("capability_evidence")

    free_text = checks.get("free_text_safety") or {}
    if free_text.get("status") == "dry_run_only":
        tracks["v1_free_text_output"]["next_actions"] = ["run_free_text_dry_run_safety_check"]
    replay = checks.get("replay_degrade") or {}
    if replay.get("status") == "suppressed":
        tracks["v1_replay_degrade"]["next_actions"] = []
    return tracks


def _track_status(check_name: str, check: dict[str, Any]) -> str:
    status = str(check.get("status") or "unknown")
    if check_name == "free_text_safety" and status == "dry_run_only":
        return "blocked_for_real_output"
    if check_name == "replay_degrade" and status == "suppressed":
        return "validated_by_sample"
    if status == "ready_for_review":
        return "sample_ready"
    if status == "needs_more_samples":
        return "needs_more_samples"
    if status == "needs_attention":
        return "needs_fix"
    return status


def _remaining_gaps(tracks: dict[str, dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for track_name, track in tracks.items():
        status = track.get("status")
        if status in {"sample_ready", "validated_by_sample"}:
            continue
        missing = track.get("missing") or []
        if missing:
            gaps.extend(f"{track_name}:{item}" for item in missing)
        else:
            gaps.append(f"{track_name}:{status}")
    return gaps


def _blocked_release_items(tracks: dict[str, dict[str, Any]]) -> list[str]:
    blocked: list[str] = []
    for track_name, track in tracks.items():
        status = track.get("status")
        if status == "blocked_for_real_output":
            blocked.append(track_name)
        elif status in {"needs_fix", "unknown"}:
            blocked.append(track_name)
    return blocked


def _sample_unproven_items(tracks: dict[str, dict[str, Any]]) -> list[str]:
    return [name for name, track in tracks.items() if track.get("status") == "needs_more_samples"]


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder RC gap summary",
        f"status: {summary['status']}",
        f"sample_root: {summary['sample_root']}",
    ]
    if "frames" in summary:
        lines.append(f"frames: {summary['frames']}")
    lines.append("")
    lines.append("tracks:")
    for name, track in (summary.get("tracks") or {}).items():
        missing = ", ".join(track.get("missing") or []) or "-"
        evidence = _render_capability_evidence(track.get("capability_evidence"))
        suffix = f" evidence={evidence}" if evidence else ""
        lines.append(f"- {name}: {track.get('status')} missing={missing}{suffix}")
    lines.append("")
    lines.append("sample_unproven_items: " + (", ".join(summary.get("sample_unproven_items") or []) or "-"))
    lines.append("blocked_release_items: " + (", ".join(summary.get("blocked_release_items") or []) or "-"))
    lines.append("next_actions: " + (", ".join(summary.get("next_actions") or []) or "-"))
    return "\n".join(lines) + "\n"


def _render_capability_evidence(value: Any) -> str:
    evidence = value if isinstance(value, dict) else {}
    if not evidence:
        return ""
    parts: list[str] = []
    for capability in sorted(evidence):
        detail = evidence.get(capability) if isinstance(evidence.get(capability), dict) else {}
        parts.append(
            "{capability}:{status}:{trigger}/{observed}".format(
                capability=capability,
                status=detail.get("status") or "unknown",
                trigger=detail.get("trigger_count", 0),
                observed=detail.get("observed_count", 0),
            )
        )
    return ",".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize v1/v2 RC gaps from local telemetry samples.")
    parser.add_argument("sample_root", nargs="?", default="local_samples/data_process_20260620")
    parser.add_argument("player_name", nargs="?", default="")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    summary = build_gap_summary(args.sample_root, player_name=args.player_name)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
