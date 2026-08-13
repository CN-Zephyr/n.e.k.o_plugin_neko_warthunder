"""Build the final live-smoke handoff packet.

This helper is intentionally read-only. It does not start N.E.K.O, War
Thunder, or the data layer. It turns the existing release scope, V2 readiness,
and live-test plan into one operator packet for the last live validation pass.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from _bootstrap import PLUGIN_ROOT as _BASE
from neko_warthunder.tools.live_test_plan import build_compact_plan
from neko_warthunder.tools.rc_gap_summary import build_gap_summary
from neko_warthunder.tools.release_readiness import build_handoff, build_release_scope
from neko_warthunder.tools.v2_readiness import build_v2_readiness
from neko_warthunder.tools.v2_release_matrix import build_v2_release_matrix

RUNTIME_FOCUS_CHECKS: tuple[dict[str, Any], ...] = (
    {
        "id": "real_output_freshness",
        "priority": "P1",
        "action": "verify_output_backpressure",
        "observe": [
            "last_output_status.event_age_seconds",
            "last_output_status.event_expires_at",
            "last_output_status.coalesce_key",
            "last_output_status.target_lanlan",
        ],
        "pass": "fresh real battle output is short, targeted, and not replaying expired low-priority cues",
    },
    {
        "id": "critical_replaces_stale_warning",
        "priority": "P1",
        "action": "verify_user_chat_interference_quiet_window",
        "observe": [
            "neko_warthunder:battle_event metadata",
            "host pending callback coalesce",
            "you_died or critical cue after ordinary warning",
        ],
        "pass": "death or critical output replaces older warning cues instead of arriving after them",
    },
    {
        "id": "user_chat_quiet_window",
        "priority": "P1",
        "action": "verify_user_chat_interference_quiet_window",
        "observe": [
            "chat window user message",
            "ordinary battle cue within 10 seconds",
            "death or critical cue within 10 seconds",
        ],
        "pass": "ordinary battle cues stay out of the user's chat turn while death and critical cues may interrupt",
    },
    {
        "id": "short_tts_contract",
        "priority": "P1",
        "action": "verify_short_tts_line_contract",
        "observe": [
            "battle_reply_contract=short_tts_line",
            "live_reply_contract=short_tts_line",
            "max_reply_chars=28",
        ],
        "pass": "spoken battle replies are one short line and do not continue across chunks",
    },
    {
        "id": "mode_domain_boundary",
        "priority": "P1",
        "action": "verify_mode_domain_boundary",
        "observe": [
            "telemetry.domain",
            "observe.last_event.event_id",
            "fixed-wing safety cues in air domain",
            "ground status cues in ground domain",
        ],
        "pass": "fixed-wing safety cues stay air-only, while ground status cues stay ground-only and outside fixed-wing critical risk",
    },
)


def build_packet(
    *,
    plugin_root: str | pathlib.Path = _BASE,
    sample_rel: str = "local_samples/data_process_20260620",
    player_name: str = "tl0sr2",
    offline_gates_passed: bool = False,
) -> dict[str, Any]:
    root = pathlib.Path(plugin_root).resolve()
    sample = root / pathlib.Path(sample_rel)
    sample_summary = build_gap_summary(sample, player_name=player_name) if sample.exists() else None
    release_scope = build_release_scope(sample_summary)
    v2_summary = build_v2_readiness(sample_root=sample if sample.exists() else None, player_name=player_name)
    v2_matrix = build_v2_release_matrix(sample_root=sample if sample.exists() else None, player_name=player_name)
    handoff = build_handoff(release_scope, v2_summary)
    live_plan = build_compact_plan(sample, player_name=player_name) if sample.exists() else None

    return {
        "status": "ready_for_final_live_smoke_packet",
        "offline_gate_status": "passed" if offline_gates_passed else "must_run",
        "go_no_go": _go_no_go(handoff, offline_gates_passed=offline_gates_passed),
        "commands": {
            "offline_gate": "uv run python tools\\release_readiness.py --run",
            "live_monitor_once": "uv run python tools\\live_monitor.py --count 1",
            "live_monitor_json": "uv run python tools\\live_monitor.py --count 3 --interval 1 --json --output local_test_logs\\live_monitor_final.json",
            "v2_readiness": f"uv run python tools\\v2_readiness.py {sample_rel} {player_name}",
            "v2_release_matrix": f"uv run python tools\\v2_release_matrix.py {sample_rel} {player_name}",
            "live_test_plan": f"uv run python tools\\live_test_plan.py {sample_rel} {player_name}",
            "evidence_rehearsal": "uv run python tools\\final_smoke_evidence_gate.py --rehearsal-output-dir local_test_logs\\final_smoke_rehearsal",
            "evidence_template": "uv run python tools\\final_smoke_evidence_gate.py --template",
            "safe_transcript_template": "uv run python tools\\final_smoke_evidence_gate.py --safe-transcript-template --output local_test_logs\\safe_transcript_metrics.json",
            "safe_transcript_record": "uv run python tools\\final_smoke_evidence_gate.py --record-safe-transcript --reply-chars <count> --reply-lines 1 --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --output local_test_logs\\safe_transcript_metrics.json",
            "evidence_from_monitor": "uv run python tools\\final_smoke_evidence_gate.py --from-live-monitor local_test_logs\\live_monitor_final.json --output local_test_logs\\final_smoke_evidence.json",
            "evidence_from_monitor_and_transcript": "uv run python tools\\final_smoke_evidence_gate.py --from-live-monitor local_test_logs\\live_monitor_final.json --safe-transcript local_test_logs\\safe_transcript_metrics.json --confirm-mode-domain-boundary --output local_test_logs\\final_smoke_evidence.json",
            "evidence_from_transcript": "uv run python tools\\final_smoke_evidence_gate.py local_test_logs\\final_smoke_evidence.json --safe-transcript local_test_logs\\safe_transcript_metrics.json",
            "evidence_confirm": "uv run python tools\\final_smoke_evidence_gate.py local_test_logs\\final_smoke_evidence.json --update --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --confirm-short-tts-single-line --confirm-mode-domain-boundary",
            "evidence_gate": "uv run python tools\\final_smoke_evidence_gate.py local_test_logs\\final_smoke_evidence.json",
        },
        "handoff": handoff,
        "v1_release_scope": release_scope,
        "v2_release_scope": v2_summary.get("release_scope") or {},
        "v2_live_evidence": v2_summary.get("live_evidence") or {},
        "v2_release_matrix": {
            "verdict": v2_matrix.get("verdict"),
            "summary": v2_matrix.get("summary") or {},
            "capabilities": v2_matrix.get("capabilities") or [],
        },
        "operator_quick_checklist": (live_plan or {}).get("quick_checklist") or [],
        "runtime_focus_checks": [dict(item) for item in RUNTIME_FOCUS_CHECKS],
        "remaining_live_actions": _dedupe(
            list(handoff.get("next_actions") or []) + list((live_plan or {}).get("next_steps") or [])
        ),
        "safety_boundary": {
            "dry_run_first": True,
            "free_text_real_output_allowed": bool(release_scope.get("free_text_real_output_allowed")),
            "v2_live_verified_real_output_enabled": False,
            "v2_live_evidence_gated_events": ["enemy_on_six", "tailing_risk", "ground_target_nearby"],
            "raw_text_printed": False,
            "do_not_claim_live_only_without_sample": True,
        },
    }


def _go_no_go(handoff: dict[str, Any], *, offline_gates_passed: bool) -> str:
    if handoff.get("status") != "ready_for_final_live_smoke":
        return "no_go_fix_offline_gate"
    if not offline_gates_passed:
        return "review_required_run_offline_gate"
    return "go_dry_run_final_smoke"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def render_text(packet: dict[str, Any]) -> str:
    commands = packet.get("commands") or {}
    handoff = packet.get("handoff") or {}
    v2 = handoff.get("v2") or {}
    lines = [
        "# neko_warthunder final smoke packet",
        f"status: {packet.get('status')}",
        f"offline_gate_status: {packet.get('offline_gate_status')}",
        f"go_no_go: {packet.get('go_no_go')}",
        f"handoff_status: {handoff.get('status')}",
        f"v2_offline_gate_complete: {v2.get('offline_gate_complete')}",
        f"v2_live_evidence_complete: {v2.get('live_evidence_complete')}",
        "v2_missing: " + (", ".join(v2.get("missing") or []) or "-"),
        "",
        "commands:",
    ]
    for key in ["offline_gate", "live_monitor_once", "live_monitor_json", "v2_readiness", "v2_release_matrix", "live_test_plan"]:
        lines.append(f"- {key}: `{commands.get(key)}`")
    for key in [
        "evidence_rehearsal",
        "evidence_template",
        "safe_transcript_template",
        "safe_transcript_record",
        "evidence_from_monitor",
        "evidence_from_monitor_and_transcript",
        "evidence_from_transcript",
        "evidence_confirm",
        "evidence_gate",
    ]:
        lines.append(f"- {key}: `{commands.get(key)}`")
    lines.extend(
        [
            "",
            "V2 capability matrix:",
            "| capability | live evidence | observed/triggered | real output | missing |",
            "| --- | --- | --- | --- | --- |",
            *_v2_matrix_rows(packet.get("v2_release_matrix") or {}),
            "",
            "runtime focus checks:",
            *_runtime_focus_rows(packet.get("runtime_focus_checks") or []),
            "",
            "remaining_live_actions: " + (", ".join(packet.get("remaining_live_actions") or []) or "-"),
            "safety: dry_run_first=true, v2_live_verified_real_output_enabled=false, raw_text_printed=false",
        ]
    )
    return "\n".join(lines) + "\n"


def _v2_matrix_rows(matrix: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for row in matrix.get("capabilities") or []:
        if not isinstance(row, dict):
            continue
        missing = ", ".join(str(item) for item in row.get("missing_requirements") or []) or "-"
        rows.append(
            "| {id} | {live_evidence_status} | {observed_count}/{trigger_count} | "
            "{real_output_policy} | {missing} |".format(**row, missing=missing)
        )
    return rows or ["| - | - | - | - | - |"]


def _runtime_focus_rows(checks: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        rows.append(
            "- {priority} {id}: action={action}; pass={pass_text}".format(
                priority=check.get("priority") or "-",
                id=check.get("id") or "-",
                action=check.get("action") or "-",
                pass_text=check.get("pass") or "-",
            )
        )
    return rows or ["- -"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the final neko_warthunder live-smoke packet.")
    parser.add_argument("--plugin-root", default=str(_BASE), help="Standalone plugin repository root.")
    parser.add_argument("--sample-rel", default="local_samples/data_process_20260620")
    parser.add_argument("--player-name", default="tl0sr2")
    parser.add_argument(
        "--offline-gates-passed",
        action="store_true",
        help="Mark the packet as ready for dry_run smoke after release_readiness --run has passed.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    packet = build_packet(
        plugin_root=args.plugin_root,
        sample_rel=args.sample_rel,
        player_name=args.player_name,
        offline_gates_passed=args.offline_gates_passed,
    )
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(packet), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
