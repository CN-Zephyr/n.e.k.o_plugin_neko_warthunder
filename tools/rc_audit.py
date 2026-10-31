"""Offline release-candidate documentation audit.

This gate checks that the handoff/release documents describe the current
plugin state instead of stale pre-V2 or pre-current-test-baseline status.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import types
from typing import Any

_BASE = pathlib.Path(__file__).resolve().parent.parent
if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg

BASELINE_DOCUMENT = "docs/当前开发状态.md"

AUDITED_FILES = [
    BASELINE_DOCUMENT,
    "README.md",
    "PROJECT_STATUS.md",
    "docs/实现计划-codex.md",
    "docs/待办事项.md",
    "docs/统一测试前-离线检查.md",
    "docs/真机验证-checklist.md",
    "docs/样本回放-20260620.md",
    "docs/v1-release-readiness.md",
]

REQUIRED_SNIPPETS = [
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
    "tools/build_release_candidate.py",
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
    "--confirm-mode-domain-boundary",
    "mode_domain_boundary",
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


# Counts are documentation claims, not evidence that tests were executed.
_PASSED = re.compile(r"(?<![\w/.,])(\d+)(?:/(\d+))?\s+passed\b")
_HISTORICAL_HEADING = re.compile(r"历史|historical|history", re.IGNORECASE)
_HISTORICAL_LINE = re.compile(r"历史|historical|旧基线|旧计数|当时|此前", re.IGNORECASE)
_CURRENT = re.compile(r"当前|最近|latest|current", re.IGNORECASE)
_REQUIRED_BASELINE_FILES = {"README.md", "PROJECT_STATUS.md", BASELINE_DOCUMENT}


def _historical_file(relative: str) -> bool:
    path = pathlib.PurePosixPath(relative)
    return "history" in path.parts or bool(
        re.search(r"(?:^|[-_])20\d{6}(?:[._-]|$)", path.name)
    )


def _current_text(text: str) -> str:
    """Exclude explicitly historical sections/lines, preserving current claims."""
    lines = []
    historical_level = None
    fence = None
    for line in text.splitlines():
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match[1]
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
        heading = re.match(r"^(#{1,6})\s+(.+)", line) if fence is None else None
        if heading:
            level = len(heading[1])
            if historical_level is not None and level <= historical_level:
                historical_level = None
            if (historical_level is None and _HISTORICAL_HEADING.search(heading[2])
                    and not _CURRENT.search(heading[2])):
                historical_level = level
        if historical_level is not None:
            continue
        if _HISTORICAL_LINE.search(line) and not _CURRENT.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def audit_docs(root: str | pathlib.Path) -> dict[str, Any]:
    base = pathlib.Path(root)
    files: dict[str, str] = {}
    historical_files: list[str] = []
    failures: list[dict[str, str]] = []

    for rel in AUDITED_FILES:
        path = base / rel
        if not path.is_file():
            failures.append({"kind": "missing_file", "file": rel, "detail": rel})
            continue
        if _historical_file(rel):
            historical_files.append(rel)
        else:
            files[rel] = _current_text(path.read_text(encoding="utf-8", errors="replace"))

    rows = [line for line in files.get(BASELINE_DOCUMENT, "").splitlines()
            if re.match(r"^\|\s*完整\s+pytest\s*\|", line, re.IGNORECASE)]
    claims = list(_PASSED.finditer(rows[0])) if len(rows) == 1 else []
    baseline = None
    if len(claims) == 1:
        claim = claims[0]
        count = int(claim[1])
        if count > 0 and (claim[2] is None or int(claim[2]) == count):
            baseline = count
    if baseline is None:
        failures.append({
            "kind": "missing_current_baseline", "file": BASELINE_DOCUMENT,
            "detail": "Require one full-pytest row with a positive, fully passed count",
        })

    corpus = "\n".join(files.values())
    for snippet in REQUIRED_SNIPPETS:
        if snippet not in corpus:
            failures.append({"kind": "missing_required_snippet", "file": "-", "detail": snippet})

    for rel, text in files.items():
        claims = list(_PASSED.finditer(text))
        if baseline is not None:
            if rel in _REQUIRED_BASELINE_FILES and not claims:
                failures.append({"kind": "missing_required_baseline", "file": rel,
                                 "detail": f"Expected {baseline} passed"})
            for claim in claims:
                if int(claim[1]) != baseline or (
                    claim[2] is not None and int(claim[2]) != baseline
                ):
                    failures.append({"kind": "stale_baseline", "file": rel,
                                     "detail": f"{claim[0]}; expected {baseline} passed"})
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text:
                failures.append({"kind": "forbidden_phrase", "file": rel, "detail": phrase})

    return {
        "status": "pass" if not failures else "fail",
        "audited_files": sorted([*files, *historical_files]),
        "historical_files_skipped": sorted(historical_files),
        "pytest_baseline": baseline,
        "baseline_source": BASELINE_DOCUMENT,
        "failures": failures,
        "required_snippets": REQUIRED_SNIPPETS,
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder rc docs audit",
        f"status: {result['status']}",
        f"pytest baseline: {result.get('pytest_baseline')} (source: {BASELINE_DOCUMENT})",
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
