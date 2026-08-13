"""Single V2 completion gate for release handoff.

This helper answers the narrow release question: is the V2 code/offline scope
complete and protected by the real-output policy gate? It intentionally does
not claim live-only evidence unless a supplied sample proves it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from neko_warthunder.tools.v2_output_policy_gate import run_gate as run_output_policy_gate
from neko_warthunder.tools.v2_readiness import build_v2_readiness
from neko_warthunder.tools.v2_release_matrix import build_v2_release_matrix


def run_gate(
    *,
    sample_root: str | pathlib.Path | None = None,
    player_name: str = "tl0sr2",
) -> dict[str, Any]:
    readiness = build_v2_readiness(sample_root=sample_root, player_name=player_name)
    matrix = build_v2_release_matrix(sample_root=sample_root, player_name=player_name)
    output_policy = run_output_policy_gate()
    release = readiness.get("release_scope") or {}
    matrix_summary = matrix.get("summary") or {}
    live_evidence = readiness.get("live_evidence") or {}

    code_complete = bool(release.get("v2_code_complete")) and bool(matrix_summary.get("code_complete"))
    offline_gate_complete = bool(release.get("v2_offline_gate_complete")) and bool(
        matrix_summary.get("offline_gate_complete")
    )
    live_evidence_complete = bool(release.get("v2_live_evidence_complete")) and bool(
        matrix_summary.get("live_evidence_complete")
    )
    real_output_policy_safe = output_policy.get("status") == "pass"
    safe_output_contract = bool(release.get("safe_output_contract")) and bool(
        matrix_summary.get("safe_output_contract")
    )
    raw_text_printed = bool(release.get("raw_text_printed")) or bool(matrix_summary.get("raw_text_printed"))
    failures = _failures(
        code_complete=code_complete,
        offline_gate_complete=offline_gate_complete,
        real_output_policy_safe=real_output_policy_safe,
        safe_output_contract=safe_output_contract,
        raw_text_printed=raw_text_printed,
    )

    blocked_until_evidence = sorted(matrix_summary.get("blocked_real_output_until_live_evidence") or [])
    return {
        "status": "pass" if not failures else "fail",
        "verdict": _verdict(
            failures=failures,
            live_evidence_complete=live_evidence_complete,
        ),
        "completion": {
            "code_complete": code_complete,
            "offline_gate_complete": offline_gate_complete,
            "live_evidence_complete": live_evidence_complete,
            "real_output_policy_safe": real_output_policy_safe,
            "safe_output_contract": safe_output_contract,
            "raw_text_printed": raw_text_printed,
        },
        "release_policy": {
            "dry_run_first": True,
            "do_not_claim_live_only_without_sample": not live_evidence_complete,
            "v2_live_verified_real_output_enabled": False,
            "blocked_real_output_until_live_evidence": blocked_until_evidence,
        },
        "live_evidence": {
            "status": live_evidence.get("status") or "unknown",
            "missing": list(live_evidence.get("missing") or []),
            "capability_evidence": dict(live_evidence.get("capability_evidence") or {}),
        },
        "matrix": {
            "verdict": matrix.get("verdict"),
            "summary": matrix_summary,
            "capabilities": list(matrix.get("capabilities") or []),
        },
        "output_policy": {
            "status": output_policy.get("status"),
            "policy": output_policy.get("policy") or {},
        },
        "next_actions": list(live_evidence.get("next_actions") or []),
        "failures": failures,
    }


def _failures(
    *,
    code_complete: bool,
    offline_gate_complete: bool,
    real_output_policy_safe: bool,
    safe_output_contract: bool,
    raw_text_printed: bool,
) -> list[str]:
    failures: list[str] = []
    if not code_complete:
        failures.append("v2_code_incomplete")
    if not offline_gate_complete:
        failures.append("v2_offline_gate_incomplete")
    if not real_output_policy_safe:
        failures.append("v2_output_policy_failed")
    if not safe_output_contract:
        failures.append("v2_safe_output_contract_missing")
    if raw_text_printed:
        failures.append("raw_text_printed")
    return failures


def _verdict(*, failures: list[str], live_evidence_complete: bool) -> str:
    if failures:
        return "v2_blocked_before_live"
    if live_evidence_complete:
        return "v2_complete_with_live_evidence"
    return "v2_code_offline_complete_live_evidence_pending"


def render_text(payload: dict[str, Any]) -> str:
    completion = payload.get("completion") or {}
    policy = payload.get("release_policy") or {}
    live = payload.get("live_evidence") or {}
    lines = [
        "# neko_warthunder V2 completion gate",
        f"status: {payload.get('status')}",
        f"verdict: {payload.get('verdict')}",
        f"code_complete: {completion.get('code_complete')}",
        f"offline_gate_complete: {completion.get('offline_gate_complete')}",
        f"live_evidence_complete: {completion.get('live_evidence_complete')}",
        f"real_output_policy_safe: {completion.get('real_output_policy_safe')}",
        f"safe_output_contract: {completion.get('safe_output_contract')}",
        "raw_text_printed: false",
        "blocked_real_output_until_live_evidence: "
        + (", ".join(policy.get("blocked_real_output_until_live_evidence") or []) or "-"),
        "live_missing: " + (", ".join(live.get("missing") or []) or "-"),
        "next_actions: " + (", ".join(payload.get("next_actions") or []) or "-"),
    ]
    failures = payload.get("failures") or []
    if failures:
        lines.append("failures: " + ", ".join(failures))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the V2 completion release gate.")
    parser.add_argument("sample_root", nargs="?", default="local_samples/data_process_20260620")
    parser.add_argument("player_name", nargs="?", default="tl0sr2")
    parser.add_argument("--no-sample", action="store_true", help="Only prove V2 code/offline completion.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    payload = run_gate(
        sample_root=None if args.no_sample else args.sample_root,
        player_name=args.player_name,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(payload), end="")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
