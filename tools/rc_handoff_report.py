"""Build a maintainer-facing RC handoff report.

This helper is intentionally no-host and no-live-machine. It combines the
existing v1 release scope, V2 completion gate, final-smoke packet, and optional
local sample evidence into one safe report for humans.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from _bootstrap import PLUGIN_ROOT as _BASE
from neko_warthunder.tools.final_smoke_packet import build_packet
from neko_warthunder.tools.rc_gap_summary import build_gap_summary
from neko_warthunder.tools.release_readiness import build_handoff, build_release_scope
from neko_warthunder.tools.v2_completion_gate import run_gate as run_v2_completion_gate
from neko_warthunder.tools.v2_readiness import build_v2_readiness


def build_report(
    *,
    plugin_root: str | pathlib.Path = _BASE,
    sample_rel: str = "local_samples/data_process_20260620",
    player_name: str = "tl0sr2",
    offline_gates_passed: bool = False,
    use_sample: bool = True,
) -> dict[str, Any]:
    root = pathlib.Path(plugin_root).resolve()
    sample = root / pathlib.Path(sample_rel)
    sample_root = sample if use_sample and sample.exists() else None
    sample_summary = build_gap_summary(sample, player_name=player_name) if sample_root is not None else None
    release_scope = build_release_scope(sample_summary)
    v2_summary = build_v2_readiness(sample_root=sample_root, player_name=player_name)
    v2_completion = run_v2_completion_gate(sample_root=sample_root, player_name=player_name)
    final_packet = build_packet(
        plugin_root=root,
        sample_rel=sample_rel,
        player_name=player_name,
        offline_gates_passed=offline_gates_passed,
    )
    handoff = build_handoff(release_scope, v2_summary)
    completion = v2_completion.get("completion") or {}
    live = v2_completion.get("live_evidence") or {}
    policy = v2_completion.get("release_policy") or {}

    return {
        "status": "ready_for_rc_handoff_report",
        "verdict": _verdict(
            release_scope=release_scope,
            v2_completion=v2_completion,
            offline_gates_passed=offline_gates_passed,
        ),
        "headline": "V1 offline gates are ready for final smoke; V2 code/offline scope is complete; live evidence remains explicit.",
        "v1": {
            "ship_status": release_scope.get("ship_status"),
            "final_live_smoke_required": bool(release_scope.get("final_live_smoke_required")),
            "real_output_blockers": list(release_scope.get("real_output_blockers") or []),
            "sample_unproven_items": list(release_scope.get("sample_unproven_items") or []),
            "free_text_real_output_allowed": bool(release_scope.get("free_text_real_output_allowed")),
        },
        "v2": {
            "status": v2_completion.get("status"),
            "verdict": v2_completion.get("verdict"),
            "code_complete": bool(completion.get("code_complete")),
            "offline_gate_complete": bool(completion.get("offline_gate_complete")),
            "live_evidence_complete": bool(completion.get("live_evidence_complete")),
            "real_output_policy_safe": bool(completion.get("real_output_policy_safe")),
            "safe_output_contract": bool(completion.get("safe_output_contract")),
            "missing_live_evidence": list(live.get("missing") or []),
            "blocked_real_output_until_live_evidence": list(
                policy.get("blocked_real_output_until_live_evidence") or []
            ),
        },
        "handoff": handoff,
        "safety": {
            "dry_run_first": True,
            "raw_text_printed": False,
            "free_text_real_output_allowed": bool(release_scope.get("free_text_real_output_allowed")),
            "v2_live_verified_real_output_enabled": False,
            "do_not_claim_live_only_without_sample": not bool(completion.get("live_evidence_complete")),
        },
        "final_smoke": {
            "offline_gate_status": final_packet.get("offline_gate_status"),
            "go_no_go": final_packet.get("go_no_go"),
            "remaining_live_actions": list(final_packet.get("remaining_live_actions") or []),
        },
        "next_actions": _dedupe(
            list(release_scope.get("next_actions") or [])
            + list(v2_completion.get("next_actions") or [])
            + list(final_packet.get("remaining_live_actions") or [])
        ),
        "operator_summary": _operator_summary(completion, live),
        "commands": {
            "offline_gate": "uv run python tools\\release_readiness.py --run",
            "rc_handoff_report": "uv run python tools\\rc_handoff_report.py --offline-gates-passed",
            "final_smoke_packet": "uv run python tools\\final_smoke_packet.py --offline-gates-passed",
            "live_monitor_once": "uv run python tools\\live_monitor.py --count 1",
        },
    }


def _verdict(
    *,
    release_scope: dict[str, Any],
    v2_completion: dict[str, Any],
    offline_gates_passed: bool,
) -> str:
    if release_scope.get("ship_status") == "blocked_before_live_smoke":
        return "blocked_before_live_smoke"
    if v2_completion.get("status") != "pass":
        return "blocked_before_live_smoke"
    if not offline_gates_passed:
        return "rc_report_ready_run_offline_gate_before_live"
    return "rc_offline_ready_live_smoke_required"


def _operator_summary(completion: dict[str, Any], live: dict[str, Any]) -> list[str]:
    lines = [
        "V1 离线门禁已可交接，最终真机 smoke 前仍应先跑 release_readiness。",
        "V2 代码、离线门禁和输出保护已收口，但不能把缺失的真机证据说成已验证。",
        "自由文本真实播报仍关闭；数值安全事件和已验证 generic kill/death 不受该阻塞。",
    ]
    if not completion.get("live_evidence_complete"):
        missing = ", ".join(live.get("missing") or [])
        if missing:
            lines.append(f"下一轮真机重点补证据：{missing}。")
    lines.append("真实输出前保持 dry_run-first，不记录 raw 玩家名、HUD、combat.feed 或 awards 原文。")
    return lines


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def render_text(report: dict[str, Any]) -> str:
    v1 = report.get("v1") or {}
    v2 = report.get("v2") or {}
    final_smoke = report.get("final_smoke") or {}
    commands = report.get("commands") or {}
    lines = [
        "# neko_warthunder RC handoff report",
        f"status: {report.get('status')}",
        f"verdict: {report.get('verdict')}",
        f"headline: {report.get('headline')}",
        f"v1_ship_status: {v1.get('ship_status')}",
        f"v1_final_live_smoke_required: {v1.get('final_live_smoke_required')}",
        f"v1_free_text_real_output_allowed: {v1.get('free_text_real_output_allowed')}",
        f"v2_code_complete: {v2.get('code_complete')}",
        f"v2_offline_gate_complete: {v2.get('offline_gate_complete')}",
        f"v2_live_evidence_complete: {v2.get('live_evidence_complete')}",
        f"v2_completion_verdict: {v2.get('verdict')}",
        "v2_missing_live_evidence: " + (", ".join(v2.get("missing_live_evidence") or []) or "-"),
        "v2_blocked_real_output_until_live_evidence: "
        + (", ".join(v2.get("blocked_real_output_until_live_evidence") or []) or "-"),
        f"final_smoke_go_no_go: {final_smoke.get('go_no_go')}",
        "safety: dry_run_first=true, raw_text_printed=false, v2_live_verified_real_output_enabled=false",
        "",
        "summary:",
    ]
    lines.extend(f"- {line}" for line in report.get("operator_summary") or [])
    lines.extend(["", "next_actions:"])
    lines.extend(f"- {action}" for action in (report.get("next_actions") or ["-"]))
    lines.extend(["", "commands:"])
    for key in ["offline_gate", "rc_handoff_report", "final_smoke_packet", "live_monitor_once"]:
        lines.append(f"- {key}: `{commands.get(key)}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a safe neko_warthunder RC handoff report.")
    parser.add_argument("--plugin-root", default=str(_BASE), help="Standalone plugin repository root.")
    parser.add_argument("--sample-rel", default="local_samples/data_process_20260620")
    parser.add_argument("--player-name", default="tl0sr2")
    parser.add_argument("--no-sample", action="store_true", help="Do not use local sample evidence.")
    parser.add_argument(
        "--offline-gates-passed",
        action="store_true",
        help="Set after release_readiness --run has passed in the same revision.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = build_report(
        plugin_root=args.plugin_root,
        sample_rel=args.sample_rel,
        player_name=args.player_name,
        offline_gates_passed=args.offline_gates_passed,
        use_sample=not args.no_sample,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
