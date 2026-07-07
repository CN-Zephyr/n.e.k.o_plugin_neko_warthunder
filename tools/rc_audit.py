"""Offline release-candidate documentation audit.

This gate checks that the handoff/release documents describe the current
plugin state instead of stale pre-V2 or pre-current-test-baseline status.
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

AUDITED_FILES = [
    "README.md",
    "PROJECT_STATUS.md",
    "docs/实现计划-codex.md",
    "docs/待办事项.md",
    "docs/统一测试前-离线检查.md",
    "docs/真机验证-checklist.md",
    "docs/样本回放-20260620.md",
    "docs/v1-release-readiness.md",
]

STALE_BASELINES = [
    "29/29 passed",
    "32/32 passed",
    "42/42 passed",
    "71/71 passed",
    "74/74 passed",
    "78/78 passed",
    "127/127 passed",
    "180 passed",
    "192/192 passed",
    "202/202 passed",
    "202 passed",
    "205/205 passed",
    "205 passed",
    "209/209 passed",
    "209 passed",
    "219/219 passed",
    "219 passed",
    "223/223 passed",
    "223 passed",
    "224/224 passed",
    "224 passed",
    "225/225 passed",
    "225 passed",
    "228/228 passed",
    "228 passed",
    "232/232 passed",
    "232 passed",
    "239/239 passed",
    "239 passed",
    "242/242 passed",
    "242 passed",
    "245/245 passed",
    "245 passed",
    "249/249 passed",
    "249 passed",
    "253/253 passed",
    "253 passed",
    "254/254 passed",
    "254 passed",
    "256/256 passed",
    "271/271 passed",
    "271 passed",
    "278/278 passed",
    "278 passed",
    "281/281 passed",
    "281 passed",
    "286/286 passed",
    "286 passed",
    "289/289 passed",
    "289 passed",
    "292/292 passed",
    "292 passed",
    "293/293 passed",
    "293 passed",
    "294/294 passed",
    "294 passed",
    "296/296 passed",
    "296 passed",
    "297/297 passed",
    "297 passed",
    "299/299 passed",
    "299 passed",
    "312/312 passed",
    "312 passed",
    "353/353 passed",
    "353 passed",
    "357/357 passed",
    "357 passed",
    "360/360 passed",
    "360 passed",
    "364/364 passed",
    "364 passed",
    "365/365 passed",
    "365 passed",
    "366/366 passed",
    "366 passed",
    "392/392 passed",
    "392 passed",
    "403/403 passed",
    "403 passed",
    "405/405 passed",
    "405 passed",
    "442/442 passed",
    "442 passed",
]

REQUIRED_SNIPPETS = [
    "444/444 passed",
    "vehicle profile id audit",
    "tools/vehicle_profile_id_audit.py",
    "vehicle profile economy metadata",
    "tools/update_vehicle_profile_economy_from_datamine.py",
    "vehicle family coverage",
    "tools/vehicle_family_coverage.py",
    "wpcost.blkx",
    "release defaults gate",
    "tools/release_defaults_gate.py",
    "handoff_status",
    "final smoke packet",
    "tools/final_smoke_packet.py",
    "runtime focus checks",
    "tools/final_smoke_evidence_gate.py",
    "--rehearsal-output-dir",
    "evidence_rehearsal",
    "final_smoke_rehearsal",
    "--from-live-monitor",
    "--safe-transcript-template",
    "--record-safe-transcript",
    "--reply-chars",
    "--safe-transcript",
    "safe_transcript_record",
    "evidence_from_monitor_and_transcript",
    "--output",
    "--update",
    "--confirm-critical-replaced-stale-warning",
    "--confirm-user-chat-quiet-window",
    "--confirm-short-tts-single-line",
    "JSONL",
    "live_monitor_final.json",
    "safe_transcript_metrics.json",
    "--final-smoke-evidence",
    "RC handoff report",
    "tools/rc_handoff_report.py",
    "V2 release matrix",
    "tools/v2_release_matrix.py",
    "V2 output policy gate",
    "tools/v2_output_policy_gate.py",
    "V2 completion gate",
    "tools/v2_completion_gate.py",
    "V2 proximity / objective awareness",
    "ground_target_nearby",
    "tailing_risk",
    "free_text_activity",
    "free_text_dry_run_only",
    "free-text release gate",
    "replay degrade gate",
    "ownership replay gate",
    "tools/ownership_replay_gate.py",
    "deferred HUD notice gate",
    "mode/domain boundary gate",
    "tools/domain_boundary_gate.py",
    "proximity/objective awareness gate",
    "host boundary gate",
    "tools/host_contract_gate.py",
    "local host compatibility checks",
    "V2 readiness summary",
    "tools/v2_readiness.py",
    "RC gap summary",
    "ready_for_final_live_smoke",
    "no_ground_target_close_candidates",
    "verify_user_chat_interference_quiet_window",
]

FORBIDDEN_PHRASES = [
    "ui/panel.tsx 未实现",
    "数据层 blocker 未解决",
    "等待数据层补齐",
]


def audit_docs(root: str | pathlib.Path) -> dict[str, Any]:
    base = pathlib.Path(root)
    files: dict[str, str] = {}
    failures: list[dict[str, str]] = []

    for rel in AUDITED_FILES:
        path = base / rel
        if not path.exists():
            failures.append({"kind": "missing_file", "file": rel, "detail": rel})
            continue
        files[rel] = path.read_text(encoding="utf-8", errors="replace")

    corpus = "\n".join(files.values())
    for snippet in REQUIRED_SNIPPETS:
        if snippet not in corpus:
            failures.append({"kind": "missing_required_snippet", "file": "-", "detail": snippet})

    for rel, text in files.items():
        for stale in STALE_BASELINES:
            if stale in text:
                failures.append({"kind": "stale_baseline", "file": rel, "detail": stale})
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text:
                failures.append({"kind": "forbidden_phrase", "file": rel, "detail": phrase})

    return {
        "status": "pass" if not failures else "fail",
        "audited_files": sorted(files),
        "failures": failures,
        "required_snippets": REQUIRED_SNIPPETS,
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder rc docs audit",
        f"status: {result['status']}",
        f"files: {len(result.get('audited_files') or [])}/{len(AUDITED_FILES)}",
    ]
    failures = result.get("failures") or []
    if failures:
        lines.append("failures:")
        for item in failures:
            lines.append(f"- {item['kind']}: {item['file']} -> {item['detail']}")
    else:
        lines.append("failures: -")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit RC docs for stale release status.")
    parser.add_argument("--plugin-root", default=str(_BASE), help="Standalone plugin repository root.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = audit_docs(args.plugin_root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(result), end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

