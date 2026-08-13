"""Render the V2 release capability matrix.

This no-host helper turns the existing V2 readiness result into a capability
matrix. It deliberately separates code/offline completion from live evidence,
so maintainers can move quickly without accidentally claiming unproven
real-machine behavior.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from neko_warthunder.tools.v2_readiness import build_v2_readiness

CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "enemy_nearby",
        "group": "proximity",
        "summary": "generic nearby enemy awareness",
        "requires": ["proximity_events"],
        "real_output_policy": "safe_generic_after_final_smoke",
    },
    {
        "id": "air_threat_nearby",
        "group": "proximity",
        "summary": "generic nearby air threat awareness",
        "requires": ["air_threat_candidates"],
        "real_output_policy": "safe_generic_after_final_smoke",
    },
    {
        "id": "enemy_on_six",
        "group": "rear_threat",
        "summary": "enemy behind or six-o'clock warning",
        "requires": ["rear_threat_candidates"],
        "real_output_policy": "dry_run_until_live_evidence",
    },
    {
        "id": "tailing_risk",
        "group": "rear_threat",
        "summary": "sustained close rear threat escalation",
        "requires": ["rear_close_threat_candidates", "tailing_risk_trigger"],
        "real_output_policy": "dry_run_until_live_evidence",
    },
    {
        "id": "ground_target_nearby",
        "group": "objective",
        "summary": "nearby ground objective reminder",
        "requires": ["ground_target_close_candidates", "ground_target_trigger"],
        "real_output_policy": "dry_run_until_live_evidence",
    },
]


def build_v2_release_matrix(
    *,
    sample_root: str | pathlib.Path | None = None,
    player_name: str = "tl0sr2",
) -> dict[str, Any]:
    readiness = build_v2_readiness(sample_root=sample_root, player_name=player_name)
    live = readiness.get("live_evidence") or {}
    missing = set(live.get("missing") or [])
    capability_evidence = live.get("capability_evidence") if isinstance(live.get("capability_evidence"), dict) else {}
    implemented = set((readiness.get("offline_scope") or {}).get("implemented_events") or [])
    live_status = str(live.get("status") or "unknown")

    rows = [
        _capability_row(
            capability,
            implemented=implemented,
            missing=missing,
            live_status=live_status,
            evidence=capability_evidence.get(capability["id"]) if isinstance(capability_evidence, dict) else None,
        )
        for capability in CAPABILITIES
    ]
    live_pending = [
        row["id"]
        for row in rows
        if row["live_evidence_status"] in {"needs_live_sample", "not_checked", "needs_review"}
    ]
    blocked_real_output = [
        row["id"]
        for row in rows
        if row["real_output_policy"] == "dry_run_until_live_evidence" and row["live_evidence_status"] != "complete"
    ]

    return {
        "status": "pass",
        "verdict": _matrix_verdict(readiness),
        "sample_root": str(sample_root) if sample_root is not None else "",
        "capabilities": rows,
        "summary": {
            "code_complete": bool((readiness.get("release_scope") or {}).get("v2_code_complete")),
            "offline_gate_complete": bool((readiness.get("release_scope") or {}).get("v2_offline_gate_complete")),
            "live_evidence_complete": bool(
                (readiness.get("release_scope") or {}).get("v2_live_evidence_complete")
            ),
            "live_pending": live_pending,
            "blocked_real_output_until_live_evidence": blocked_real_output,
            "safe_output_contract": bool((readiness.get("release_scope") or {}).get("safe_output_contract")),
            "raw_text_printed": False,
        },
        "next_actions": list(live.get("next_actions") or []),
        "notes": [
            "V2 code/offline completion is not the same as live verification",
            "capabilities without live evidence stay dry_run-first for real-machine rollout",
            "matrix contains only metadata and safe summaries",
        ],
    }


def _capability_row(
    capability: dict[str, Any],
    *,
    implemented: set[str],
    missing: set[str],
    live_status: str,
    evidence: Any = None,
) -> dict[str, Any]:
    required = list(capability["requires"])
    evidence_detail = evidence if isinstance(evidence, dict) else {}
    missing_requirements = list(evidence_detail.get("missing_requirements") or [])
    if not evidence_detail:
        missing_requirements = [item for item in required if item in missing]
    if live_status == "complete":
        evidence = "complete"
    elif live_status == "not_checked":
        evidence = "not_checked"
    elif evidence_detail:
        evidence = str(evidence_detail.get("status") or "needs_live_sample")
    elif missing_requirements:
        evidence = "needs_live_sample"
    else:
        evidence = "covered_by_current_sample"

    return {
        "id": capability["id"],
        "group": capability["group"],
        "summary": capability["summary"],
        "code_status": "complete" if capability["id"] in implemented else "missing_from_offline_gate",
        "offline_gate_status": "passed" if capability["id"] in implemented else "failed",
        "live_evidence_status": evidence,
        "observed_count": int(evidence_detail.get("observed_count") or 0),
        "trigger_count": int(evidence_detail.get("trigger_count") or 0),
        "missing_requirements": missing_requirements,
        "real_output_policy": capability["real_output_policy"],
        "raw_text_allowed": False,
    }


def _matrix_verdict(readiness: dict[str, Any]) -> str:
    release = readiness.get("release_scope") or {}
    if not release.get("v2_code_complete") or not release.get("v2_offline_gate_complete"):
        return "v2_blocked_before_live"
    if release.get("v2_live_evidence_complete"):
        return "v2_live_verified"
    return "v2_code_complete_live_pending"


def render_text(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# neko_warthunder V2 release matrix",
        f"status: {payload.get('status')}",
        f"verdict: {payload.get('verdict')}",
        f"code_complete: {summary.get('code_complete')}",
        f"offline_gate_complete: {summary.get('offline_gate_complete')}",
        f"live_evidence_complete: {summary.get('live_evidence_complete')}",
        "",
        "| capability | code | offline | live evidence | observed/triggered | real output | missing |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload.get("capabilities") or []:
        missing = ", ".join(row.get("missing_requirements") or []) or "-"
        lines.append(
            "| {id} | {code_status} | {offline_gate_status} | {live_evidence_status} | "
            "{observed_count}/{trigger_count} | {real_output_policy} | {missing} |".format(**row, missing=missing)
        )
    lines.extend(
        [
            "",
            "blocked_real_output_until_live_evidence: "
            + (", ".join(summary.get("blocked_real_output_until_live_evidence") or []) or "-"),
            "next_actions: " + (", ".join(payload.get("next_actions") or []) or "-"),
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the V2 release capability matrix.")
    parser.add_argument("sample_root", nargs="?", default="local_samples/data_process_20260620")
    parser.add_argument("player_name", nargs="?", default="tl0sr2")
    parser.add_argument("--no-sample", action="store_true", help="Only prove code/offline readiness.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    payload = build_v2_release_matrix(
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
