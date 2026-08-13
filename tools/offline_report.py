"""Render a safe offline readiness report from local sample replay output."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from _bootstrap import PLUGIN_ROOT as _BASE
from neko_warthunder.tools.live_test_plan import build_quick_checklist, build_step_from_item
from neko_warthunder.tools.sample_replay import replay_sample_root


def build_markdown_report(root: str | pathlib.Path, *, player_name: str = "tl0sr2") -> str:
    report = replay_sample_root(root, player_name=player_name)
    summary = report.get("session_summary") or {}
    checks = summary.get("validation_checks") or {}
    steps = [build_step_from_item(item) for item in summary.get("live_test_plan") or [] if isinstance(item, dict)]
    quick_checklist = build_quick_checklist(steps)

    lines = [
        "# neko_warthunder offline readiness report",
        "",
        f"- sample root: `{report.get('root')}`",
        f"- files: `{report.get('files')}`",
        f"- frames: `{report.get('frames')}`",
        f"- status: `{summary.get('status') or 'unknown'}`",
        "",
        "## Team brief",
        "",
        *build_team_brief(report),
        "",
        "## Observed outputs",
        "",
        _bullet_list(summary.get("observed_outputs") or []),
        "",
        "## Next test focus",
        "",
        _bullet_list(_next_test_focus(summary)),
        "",
        "## Validation checks",
        "",
        "| check | status | detail |",
        "| --- | --- | --- |",
    ]
    for key in sorted(checks):
        value = checks[key] if isinstance(checks[key], dict) else {}
        lines.append(f"| {key} | {value.get('status') or 'unknown'} | {_check_detail(key, value)} |")

    lines.extend(
        [
            "",
            "## Coverage gaps",
            "",
            _bullet_list(report.get("coverage_gaps") or []),
            "",
            "## V2 capability evidence",
            "",
            "| capability | status | observed/triggered | missing |",
            "| --- | --- | --- | --- |",
            *_v2_capability_rows(_v2_capability_evidence(checks)),
            "",
            "## Next validation steps",
            "",
            _bullet_list(summary.get("next_steps") or []),
            "",
            "## Operator quick checklist",
            "",
            "| 顺序 | 用户操作 | 我方监控重点 | 通过标准 |",
            "| --- | --- | --- | --- |",
            *_quick_checklist_rows(quick_checklist),
            "",
            "## Next live-test plan",
            "",
            "| priority | area | status | action |",
            "| --- | --- | --- | --- |",
            *_live_test_plan_rows(summary.get("live_test_plan") or []),
            "",
            "## Remaining live-test scope",
            "",
            _bullet_list(_remaining_live_scope(summary)),
            "",
            "## Safety notes",
            "",
            "- Raw player names, HUD text, combat feed text, and awards text are not included.",
            "- free_text_safety=dry_run_only means the sample contains free-text sources, but real speech remains blocked.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_compact_report(root: str | pathlib.Path, *, player_name: str = "tl0sr2") -> dict[str, Any]:
    report = replay_sample_root(root, player_name=player_name)
    summary = report.get("session_summary") or {}
    steps = [build_step_from_item(item) for item in summary.get("live_test_plan") or [] if isinstance(item, dict)]
    return {
        "root": report.get("root"),
        "files": report.get("files"),
        "frames": report.get("frames"),
        "status": summary.get("status") or "unknown",
        "observed_outputs": list(summary.get("observed_outputs") or []),
        "validation_checks": dict(summary.get("validation_checks") or {}),
        "v2_capability_evidence": _v2_capability_evidence(summary.get("validation_checks") or {}),
        "next_test_focus": _next_test_focus(summary),
        "live_test_plan": list(summary.get("live_test_plan") or []),
        "quick_checklist": build_quick_checklist(steps),
        "remaining_live_scope": _remaining_live_scope(summary),
        "next_steps": list(summary.get("next_steps") or []),
        "coverage_gaps": list(report.get("coverage_gaps") or []),
    }


def build_team_brief(report: dict[str, Any]) -> list[str]:
    summary = report.get("session_summary") or {}
    checks = summary.get("validation_checks") if isinstance(summary.get("validation_checks"), dict) else {}
    ready = [key for key, value in checks.items() if isinstance(value, dict) and value.get("status") == "ready_for_review"]
    blocked = _remaining_live_scope(summary)
    next_steps = list(summary.get("next_steps") or [])
    return [
        f"- ready: {_inline_list(ready)}",
        f"- blocked: {_inline_list(blocked)}",
        f"- next: {_inline_list(next_steps[:3])}",
    ]


def _bullet_list(values: list[Any]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- `{value}`" for value in values)


def _v2_capability_evidence(checks: Any) -> dict[str, Any]:
    data = checks if isinstance(checks, dict) else {}
    proximity = data.get("proximity_awareness") if isinstance(data.get("proximity_awareness"), dict) else {}
    evidence = proximity.get("capability_evidence")
    return dict(evidence) if isinstance(evidence, dict) else {}


def _v2_capability_rows(evidence: dict[str, Any]) -> list[str]:
    if not evidence:
        return ["| - | - | - | - |"]
    rows: list[str] = []
    for capability in sorted(evidence):
        item = evidence.get(capability) if isinstance(evidence.get(capability), dict) else {}
        missing = ", ".join(str(value) for value in item.get("missing_requirements") or []) or "-"
        rows.append(
            "| {capability} | {status} | {observed}/{triggered} | {missing} |".format(
                capability=capability,
                status=item.get("status") or "unknown",
                observed=int(item.get("observed_count") or 0),
                triggered=int(item.get("trigger_count") or 0),
                missing=missing,
            )
        )
    return rows


def _remaining_live_scope(summary: dict[str, Any]) -> list[str]:
    checks = summary.get("validation_checks") if isinstance(summary.get("validation_checks"), dict) else {}
    scope: list[str] = []
    for key, value in checks.items():
        if not isinstance(value, dict):
            continue
        status = value.get("status")
        if status in {"needs_more_samples", "dry_run_only"}:
            scope.append(f"{key}:{status}")
    return scope


def _inline_list(values: list[Any]) -> str:
    if not values:
        return "-"
    return ", ".join(f"`{value}`" for value in values)


def _check_detail(key: str, value: dict[str, Any]) -> str:
    if key == "free_text_safety" and value.get("source_details"):
        return _free_text_detail(value.get("source_details"))
    if key == "replay_degrade" and value.get("telemetry_replay_frames", 0) > 0:
        return _replay_detail(value)
    detail = value.get("missing") or value.get("observed") or []
    return _inline_list(detail)


def _free_text_detail(value: Any) -> str:
    details = value if isinstance(value, dict) else {}
    if not details:
        return "-"
    parts: list[str] = []
    for source in sorted(details):
        detail = details.get(source) if isinstance(details.get(source), dict) else {}
        status = "blocked" if detail.get("prompt_allowed") is False else "allowed"
        parts.append(f"`{source}={detail.get('items', 0)}/{status}`")
    return ", ".join(parts) if parts else "-"


def _replay_detail(value: dict[str, Any]) -> str:
    status = "suppressed" if value.get("detector_suppressed") else "needs_attention"
    return ", ".join(
        [
            f"`replay={value.get('telemetry_replay_frames', 0)}/{status}`",
            f"`output_blocked={value.get('output_blocked')}`",
            f"`prompt_allowed={value.get('prompt_allowed')}`",
        ]
    )


def _next_test_focus(summary: dict[str, Any]) -> list[str]:
    checks = summary.get("validation_checks") if isinstance(summary.get("validation_checks"), dict) else {}
    focus: list[str] = []
    replay = checks.get("replay_degrade") if isinstance(checks.get("replay_degrade"), dict) else {}
    if replay.get("status") == "suppressed":
        focus.append("replay_true_suppressed")
    elif replay.get("status") == "needs_more_samples":
        focus.append("capture_replay_true_sample")
    elif replay.get("status") == "needs_attention":
        focus.append("fix_replay_output_leak")

    free_text = checks.get("free_text_safety") if isinstance(checks.get("free_text_safety"), dict) else {}
    if free_text.get("status") == "dry_run_only":
        focus.append("free_text_dry_run_only")
    elif free_text.get("status") == "needs_more_samples":
        focus.append("capture_free_text_sample")

    focus.extend(["runtime_output_backpressure", "kill_coalescing"])

    numeric = checks.get("numeric_safety") if isinstance(checks.get("numeric_safety"), dict) else {}
    if "overspeed_critical" in (numeric.get("missing") or []):
        focus.append("overspeed_critical")

    profile = checks.get("profile_calibration") if isinstance(checks.get("profile_calibration"), dict) else {}
    for item in profile.get("missing") or []:
        focus.append(f"profile_{item}")

    return _dedupe(focus)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _live_test_plan_rows(plan: list[Any]) -> list[str]:
    if not plan:
        return ["| - | - | - | - |"]
    rows: list[str] = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        rows.append(
            "| {priority} | {label} | {status} | {action} |".format(
                priority=item.get("priority") or "-",
                label=item.get("label") or "-",
                status=item.get("status") or "-",
                action=item.get("action") or "-",
            )
        )
    return rows or ["| - | - | - | - |"]


def _quick_checklist_rows(items: list[dict[str, str]]) -> list[str]:
    if not items:
        return ["| - | - | - | - |"]
    return [f"| {item['order']} | {item['user_action']} | {item['monitor']} | {item['pass']} |" for item in items]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a safe neko_warthunder offline readiness report.")
    parser.add_argument("root", nargs="?", default=str(_BASE / "local_samples" / "data_process_20260620"))
    parser.add_argument("player_name", nargs="?", default="tl0sr2")
    parser.add_argument("--output", help="Write Markdown report to this path instead of stdout.")
    parser.add_argument("--json", action="store_true", help="Print a compact safe JSON report.")
    args = parser.parse_args(argv)

    if args.json:
        print(json.dumps(build_compact_report(args.root, player_name=args.player_name), ensure_ascii=False, sort_keys=True))
        return 0

    markdown = build_markdown_report(args.root, player_name=args.player_name)
    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
