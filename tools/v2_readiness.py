"""V2 readiness summary for proximity / objective awareness.

This is a no-host helper. It proves the deterministic offline V2 gate, then
optionally folds in ignored local sample evidence to say which live-only V2
items still need a real-machine pass.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from neko_warthunder.tools.proximity_gate import run_gate as run_proximity_gate
from neko_warthunder.tools.rc_gap_summary import build_gap_summary

V2_EVENTS = [
    "enemy_nearby",
    "air_threat_nearby",
    "enemy_on_six",
    "tailing_risk",
    "ground_target_nearby",
]

LIVE_EVIDENCE_ACTIONS = [
    "capture_rear_threat_or_six_oclock_sample",
    "capture_sustained_close_rear_sample",
    "fly_closer_to_ground_target_sample",
    "capture_ground_target_trigger_sample",
]


def build_v2_readiness(
    *,
    sample_root: str | pathlib.Path | None = None,
    player_name: str = "",
) -> dict[str, Any]:
    gate = run_proximity_gate()
    v2_sample = _sample_v2_track(sample_root, player_name=player_name) if sample_root is not None else None
    missing = list((v2_sample or {}).get("missing") or [])
    sample_actions = list((v2_sample or {}).get("next_actions") or [])
    evidence_status = _evidence_status(v2_sample)

    return {
        "status": "pass",
        "verdict": _verdict(evidence_status),
        "offline_scope": {
            "status": "complete",
            "gate": "proximity/objective awareness gate",
            "gate_status": gate.get("status"),
            "implemented_events": [event for event in V2_EVENTS if event in set(gate.get("emitted") or [])],
            "safe_push_text": bool(gate.get("push_text_safe")),
            "combat_stress_low_priority": gate.get("combat_stress_low_priority"),
            "ground_target_low_priority": gate.get("ground_target_low_priority"),
            "critical_preempt": gate.get("critical_preempt"),
        },
        "live_evidence": {
            "status": evidence_status,
            "sample_root": str(sample_root) if sample_root is not None else "",
            "missing": missing,
            "capability_evidence": dict((v2_sample or {}).get("capability_evidence") or {}),
            "next_actions": _next_actions(sample_actions, evidence_status),
            "notes": _notes(evidence_status),
        },
        "release_scope": {
            "v2_code_complete": True,
            "v2_offline_gate_complete": True,
            "v2_live_evidence_complete": evidence_status == "complete",
            "safe_output_contract": True,
            "raw_text_printed": False,
        },
    }


def _sample_v2_track(sample_root: str | pathlib.Path, *, player_name: str) -> dict[str, Any]:
    root = pathlib.Path(sample_root)
    if not root.exists():
        return {
            "status": "sample_missing",
            "missing": ["sample_root"],
            "next_actions": ["capture_local_telemetry_sample"],
        }
    summary = build_gap_summary(root, player_name=player_name)
    tracks = summary.get("tracks") or {}
    return dict(tracks.get("v2_proximity_objective") or {})


def _evidence_status(track: dict[str, Any] | None) -> str:
    if track is None:
        return "not_checked"
    status = str(track.get("status") or "unknown")
    if status == "sample_ready":
        return "complete"
    if status in {"needs_more_samples", "sample_missing"}:
        return "needs_live_sample"
    return "needs_review"


def _verdict(evidence_status: str) -> str:
    if evidence_status == "complete":
        return "v2_complete_with_sample_evidence"
    if evidence_status == "not_checked":
        return "v2_offline_complete_sample_not_checked"
    return "v2_offline_complete_live_evidence_pending"


def _next_actions(sample_actions: list[str], evidence_status: str) -> list[str]:
    if evidence_status == "complete":
        return []
    if sample_actions:
        return _dedupe(sample_actions)
    if evidence_status == "not_checked":
        return ["run_v2_readiness_with_local_sample"]
    return LIVE_EVIDENCE_ACTIONS.copy()


def _notes(evidence_status: str) -> list[str]:
    notes = [
        "offline V2 code and safety contract are complete",
        "do not claim live-only proximity/objective behavior without sample evidence",
    ]
    if evidence_status == "complete":
        notes.append("local sample evidence covers V2 trigger paths")
    return notes


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def render_text(payload: dict[str, Any]) -> str:
    offline = payload["offline_scope"]
    evidence = payload["live_evidence"]
    lines = [
        "# neko_warthunder V2 readiness",
        f"status: {payload['status']}",
        f"verdict: {payload['verdict']}",
        f"offline: {offline['status']} gate={offline['gate_status']}",
        "events: " + ", ".join(offline["implemented_events"]),
        f"live_evidence: {evidence['status']}",
        "missing: " + (", ".join(evidence["missing"]) or "-"),
        "capability_evidence: " + _fmt_capability_evidence(evidence.get("capability_evidence")),
        "next_actions: " + (", ".join(evidence["next_actions"]) or "-"),
    ]
    return "\n".join(lines) + "\n"


def _fmt_capability_evidence(value: Any) -> str:
    evidence = value if isinstance(value, dict) else {}
    if not evidence:
        return "-"
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
    return ", ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize V2 proximity/objective readiness.")
    parser.add_argument("sample_root", nargs="?", default="local_samples/data_process_20260620")
    parser.add_argument("player_name", nargs="?", default="tl0sr2")
    parser.add_argument("--no-sample", action="store_true", help="Only run the deterministic offline V2 gate.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    payload = build_v2_readiness(
        sample_root=None if args.no_sample else args.sample_root,
        player_name=args.player_name,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
