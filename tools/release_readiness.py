"""Offline v1 release readiness helper.

This command is intentionally no-host and no-real-machine by default. It
aggregates deterministic gates and tells operators whether the branch is ready
for the final live smoke, or blocked before that point.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import types
from dataclasses import dataclass
from typing import Any, Sequence

_BASE = pathlib.Path(__file__).resolve().parent.parent
if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg

from neko_warthunder.tools.rc_gap_summary import build_gap_summary  # noqa: E402
from neko_warthunder.tools.v2_readiness import build_v2_readiness  # noqa: E402


@dataclass(frozen=True)
class Check:
    name: str
    cwd: pathlib.Path
    cmd: list[str]
    blocking: bool = True
    review_hint: str = ""


def build_checks(
    *,
    plugin_root: str | pathlib.Path,
    host_root: str | pathlib.Path | None = None,
    sample_rel: str = "local_samples/data_process_20260620",
    include_local_sample: bool = False,
    final_smoke_evidence: str | pathlib.Path | None = None,
) -> list[Check]:
    plugin = pathlib.Path(plugin_root).resolve()
    host = pathlib.Path(host_root).resolve() if host_root is not None else plugin.parent / "N.E.K.O"
    sample = plugin / pathlib.Path(sample_rel)

    checks = [
        Check("logic self-check", plugin, ["uv", "run", "python", "tests/run_logic_tests.py"]),
        Check("pytest", plugin, ["uv", "run", "pytest", "-c", "tests/pytest.ini", "tests", "-q"]),
        Check(
            "rc docs audit",
            plugin,
            ["uv", "run", "python", "tools/rc_audit.py"],
            review_hint="release/status docs must not contain stale baselines or pre-V2 blocker language",
        ),
        Check(
            "vehicle profile id audit",
            plugin,
            ["uv", "run", "python", "tools/vehicle_profile_id_audit.py"],
            review_hint="vehicle profile keys must follow Wiki gameId / runtime vehicle_type identity policy",
        ),
        Check(
            "release defaults gate",
            plugin,
            ["uv", "run", "python", "tools/release_defaults_gate.py"],
            review_hint="release defaults must stay dry_run-first with unverified real output closed",
        ),
        Check(
            "output freshness gate",
            plugin,
            ["uv", "run", "python", "tools/output_freshness_gate.py"],
            review_hint="real battle push must carry coalesce/freshness/target/short-reply metadata and drop expired cues",
        ),
        Check(
            "host contract gate",
            plugin,
            [
                "uv",
                "run",
                "python",
                "tools/host_contract_gate.py",
                "--plugin-root",
                str(plugin),
                "--host-root",
                str(host),
            ],
            review_hint="local host, when present, must consume short-reply metadata and apply War Thunder user-chat quieting",
        ),
        Check(
            "free-text release gate",
            plugin,
            ["uv", "run", "python", "tools/free_text_gate.py"],
            review_hint="raw player/HUD/combat/award text must not enter prompts or push_message text",
        ),
        Check(
            "replay degrade gate",
            plugin,
            ["uv", "run", "python", "tools/replay_gate.py"],
            review_hint="replay=true must not emit candidates, prompts, or push_message output",
        ),
        Check(
            "ownership replay gate",
            plugin,
            ["uv", "run", "python", "tools/ownership_replay_gate.py"],
            review_hint="legacy third-party samples must require explicit identity inference and keep interference unowned",
        ),
        Check(
            "deferred HUD notice gate",
            plugin,
            ["uv", "run", "python", "tools/deferred_hud_gate.py"],
            review_hint="powertrain_failure must stay observable but non-speech without raw HUD text",
        ),
        Check(
            "proximity/objective awareness gate",
            plugin,
            ["uv", "run", "python", "tools/proximity_gate.py"],
            review_hint="V2 proximity.events / situation.ground_targets prompts must stay generic/safe and obey Arbiter gating",
        ),
        Check(
            "V2 readiness summary",
            plugin,
            ["uv", "run", "python", "tools/v2_readiness.py", "--no-sample"],
            review_hint="V2 offline scope must be complete without claiming live-only sample evidence",
        ),
        Check(
            "V2 release matrix",
            plugin,
            ["uv", "run", "python", "tools/v2_release_matrix.py", "--no-sample"],
            review_hint="V2 capabilities must separate code/offline completion from live evidence and real-output policy",
        ),
        Check(
            "V2 output policy gate",
            plugin,
            ["uv", "run", "python", "tools/v2_output_policy_gate.py"],
            review_hint="live-evidence-gated V2 capabilities must stay dry_run-first unless explicitly verified",
        ),
        Check(
            "V2 completion gate",
            plugin,
            ["uv", "run", "python", "tools/v2_completion_gate.py", "--no-sample"],
            review_hint="V2 code/offline scope must be complete without claiming missing live-only evidence",
        ),
        Check(
            "RC handoff report",
            plugin,
            ["uv", "run", "python", "tools/rc_handoff_report.py", "--no-sample"],
            review_hint="maintainer handoff must separate v1 release scope, V2 completion, safety boundary, and live evidence gaps",
        ),
        Check("synthetic replay", plugin, ["uv", "run", "python", "tools/replay.py"]),
    ]
    if host.exists():
        checks.append(
            Check(
                "host War Thunder contract tests",
                host,
                [
                    "uv",
                    "run",
                    "pytest",
                    "tests/unit/test_core_game_route_memory_contract.py",
                    "tests/unit/test_callback_instruction_origin.py",
                    "tests/unit/test_proactive_sm_integration.py",
                    "-q",
                ],
                review_hint="host behavior must consume short battle replies and quiet ordinary War Thunder cues during user chat",
            )
        )
        checks.append(
            Check(
                "plugin check",
                host,
                ["uv", "run", "python", "-m", "plugin.neko_plugin_cli.cli", "check", str(plugin)],
            )
        )
    if include_local_sample and sample.exists():
        checks.extend(
            [
                Check(
                    "local sample replay",
                    plugin,
                    ["uv", "run", "python", "tools/sample_replay.py", sample_rel, "tl0sr2"],
                    review_hint="review session_summary and remaining live scope",
                ),
                Check(
                    "V2 readiness with local sample",
                    plugin,
                    ["uv", "run", "python", "tools/v2_readiness.py", sample_rel, "tl0sr2"],
                    review_hint="V2 sample evidence summary for rear/six threat and objective proximity",
                ),
                Check(
                    "V2 release matrix with local sample",
                    plugin,
                    ["uv", "run", "python", "tools/v2_release_matrix.py", sample_rel, "tl0sr2"],
                    review_hint="V2 capability matrix showing live-evidence pending rows and dry_run-first policy",
                ),
                Check(
                    "V2 completion gate with local sample",
                    plugin,
                    ["uv", "run", "python", "tools/v2_completion_gate.py", sample_rel, "tl0sr2"],
                    review_hint="single V2 done/pending verdict for release handoff without raw telemetry text",
                ),
                Check(
                    "RC handoff report with local sample",
                    plugin,
                    [
                        "uv",
                        "run",
                        "python",
                        "tools/rc_handoff_report.py",
                        "--sample-rel",
                        sample_rel,
                        "--player-name",
                        "tl0sr2",
                        "--offline-gates-passed",
                    ],
                    review_hint="human-readable RC handoff with local sample gaps and dry_run-first safety boundary",
                ),
                Check(
                    "offline readiness report",
                    plugin,
                    ["uv", "run", "python", "tools/offline_report.py", sample_rel, "tl0sr2"],
                    review_hint="safe Markdown readiness report",
                ),
                Check(
                    "rc gap summary",
                    plugin,
                    ["uv", "run", "python", "tools/rc_gap_summary.py", sample_rel, "tl0sr2"],
                    review_hint="machine-readable v1/v2 remaining gap summary without raw telemetry text",
                ),
                Check(
                    "live test plan",
                    plugin,
                    ["uv", "run", "python", "tools/live_test_plan.py", sample_rel, "tl0sr2"],
                    review_hint="operator checklist for the final live smoke",
                ),
            ]
        )
    checks.append(
        Check(
            "final smoke packet",
            plugin,
            ["uv", "run", "python", "tools/final_smoke_packet.py", "--offline-gates-passed"],
            review_hint="single safe handoff packet for final dry_run live smoke",
        )
    )
    if final_smoke_evidence is not None:
        checks.append(
            Check(
                "final smoke evidence gate",
                plugin,
                [
                    "uv",
                    "run",
                    "python",
                    "tools/final_smoke_evidence_gate.py",
                    str(final_smoke_evidence),
                ],
                review_hint="post-smoke P1 evidence must pass without raw chat/HUD/combat/award text",
            )
        )
    return checks


def run_checks(checks: Sequence[Check], *, stream_output: bool = True) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for check in checks:
        completed = subprocess.run(
            check.cmd,
            cwd=check.cwd,
            capture_output=not stream_output,
            text=not stream_output,
        )
        item = {
            "name": check.name,
            "returncode": completed.returncode,
            "blocking": check.blocking,
            "cmd": " ".join(check.cmd),
        }
        if not stream_output:
            stdout = _compact_process_output(getattr(completed, "stdout", "") or "")
            stderr = _compact_process_output(getattr(completed, "stderr", "") or "")
            if stdout:
                item["stdout"] = stdout
            if stderr:
                item["stderr"] = stderr
        results.append(item)
        if check.blocking and completed.returncode != 0:
            return {
                "status": "fail",
                "verdict": "blocked",
                "checks": results,
                "next_step": f"fix {check.name} before final live smoke",
                "release_scope": _blocked_scope(check.name),
            }
    return {
        "status": "pass",
        "verdict": "ready_for_final_live_smoke",
        "checks": results,
        "next_step": "run one focused final live smoke with dry_run first",
        "release_scope": build_release_scope(),
    }


def plan_payload(
    checks: Sequence[Check],
    *,
    sample_summary: dict[str, Any] | None = None,
    v2_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    release_scope = _plan_scope(sample_summary)
    return {
        "status": "plan",
        "verdict": "not_run",
        "checks": [
            {
                "name": check.name,
                "cmd": " ".join(check.cmd),
                "cwd": str(check.cwd),
                "blocking": check.blocking,
                "review_hint": check.review_hint,
            }
            for check in checks
        ],
        "next_step": "run with --run; if pass, proceed to final live smoke",
        "release_scope": release_scope,
        "handoff": build_handoff(release_scope, v2_summary or build_v2_readiness(sample_root=None)),
    }


def _compact_process_output(text: str, *, max_chars: int = 2000) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return "..." + cleaned[-max_chars:]


def build_release_scope(sample_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    sample = sample_summary or {}
    return {
        "ship_status": "offline_gates_passed",
        "final_live_smoke_required": True,
        "real_output_blockers": list(sample.get("blocked_release_items") or []),
        "sample_unproven_items": list(sample.get("sample_unproven_items") or []),
        "next_actions": list(sample.get("next_actions") or []),
        "free_text_real_output_allowed": bool(
            (sample.get("safety") or {}).get("free_text_real_output_allowed", False)
        ),
        "notes": [
            "offline gates passed; do not claim live-only seams without final smoke",
            "free-text real output stays blocked unless its dry_run safety validation passes",
        ],
    }


def build_handoff(release_scope: dict[str, Any], v2_summary: dict[str, Any]) -> dict[str, Any]:
    v2_release = v2_summary.get("release_scope") or {}
    v2_evidence = v2_summary.get("live_evidence") or {}
    real_output_blockers = list(release_scope.get("real_output_blockers") or [])
    sample_unproven = list(release_scope.get("sample_unproven_items") or [])
    v2_next = list(v2_evidence.get("next_actions") or [])
    release_next = list(release_scope.get("next_actions") or [])
    return {
        "status": _handoff_status(release_scope, v2_release),
        "v1": {
            "ship_status": release_scope.get("ship_status"),
            "final_live_smoke_required": bool(release_scope.get("final_live_smoke_required")),
            "real_output_blockers": real_output_blockers,
            "sample_unproven_items": sample_unproven,
            "free_text_real_output_allowed": bool(release_scope.get("free_text_real_output_allowed")),
        },
        "v2": {
            "code_complete": bool(v2_release.get("v2_code_complete")),
            "offline_gate_complete": bool(v2_release.get("v2_offline_gate_complete")),
            "live_evidence_complete": bool(v2_release.get("v2_live_evidence_complete")),
            "live_evidence_status": v2_evidence.get("status"),
            "missing": list(v2_evidence.get("missing") or []),
        },
        "next_actions": _dedupe(release_next + v2_next),
        "notes": [
            "use release_readiness --run as the handoff entry point",
            "V2 code/offline gate completion is separate from live sample evidence",
            "free-text real output remains blocked unless dry_run safety validation passes",
        ],
    }


def _handoff_status(release_scope: dict[str, Any], v2_release: dict[str, Any]) -> str:
    if release_scope.get("ship_status") == "blocked_before_live_smoke":
        return "blocked_before_live_smoke"
    if not v2_release.get("v2_offline_gate_complete"):
        return "blocked_before_live_smoke"
    if release_scope.get("ship_status") == "not_run":
        return "not_run"
    return "ready_for_final_live_smoke"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _blocked_scope(check_name: str) -> dict[str, Any]:
    return {
        "ship_status": "blocked_before_live_smoke",
        "final_live_smoke_required": False,
        "real_output_blockers": [check_name],
        "sample_unproven_items": [],
        "next_actions": [f"fix_{check_name.replace(' ', '_')}"],
        "free_text_real_output_allowed": False,
        "notes": ["a blocking offline gate failed; stop before live smoke"],
    }


def _plan_scope(sample_summary: dict[str, Any] | None) -> dict[str, Any]:
    sample = sample_summary or {}
    return {
        "ship_status": "not_run",
        "final_live_smoke_required": True,
        "real_output_blockers": list(sample.get("blocked_release_items") or []),
        "sample_unproven_items": list(sample.get("sample_unproven_items") or []),
        "next_actions": list(sample.get("next_actions") or ["run_release_readiness"]),
        "free_text_real_output_allowed": bool(
            (sample.get("safety") or {}).get("free_text_real_output_allowed", False)
        ),
        "notes": ["run with --run before using this as release evidence"],
    }


def _load_sample_summary(plugin_root: str | pathlib.Path, sample_rel: str) -> dict[str, Any] | None:
    sample = pathlib.Path(plugin_root).resolve() / pathlib.Path(sample_rel)
    if not sample.exists():
        return None
    return build_gap_summary(sample, player_name="tl0sr2")


def render_text(payload: dict[str, Any]) -> str:
    scope = payload.get("release_scope") or {}
    handoff = payload.get("handoff") or {}
    v2 = handoff.get("v2") or {}
    lines = [
        "# neko_warthunder v1 release readiness",
        f"status: {payload['status']}",
        f"verdict: {payload['verdict']}",
        f"next: {payload['next_step']}",
        f"ship_status: {scope.get('ship_status', '-')}",
        "real_output_blockers: " + (", ".join(scope.get("real_output_blockers") or []) or "-"),
        "sample_unproven_items: " + (", ".join(scope.get("sample_unproven_items") or []) or "-"),
        "scope_next_actions: " + (", ".join(scope.get("next_actions") or []) or "-"),
        f"handoff_status: {handoff.get('status', '-')}",
        f"v2_offline_gate_complete: {v2.get('offline_gate_complete', '-')}",
        f"v2_live_evidence_complete: {v2.get('live_evidence_complete', '-')}",
        "v2_missing: " + (", ".join(v2.get("missing") or []) or "-"),
        "",
        "checks:",
    ]
    for index, check in enumerate(payload["checks"], start=1):
        suffix = ""
        if "returncode" in check:
            suffix = f" -> {check['returncode']}"
        lines.append(f"{index}. {check['name']}{suffix}")
        lines.append(f"   cmd: {check['cmd']}")
        if check.get("review_hint"):
            lines.append(f"   review: {check['review_hint']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check v1 offline release readiness.")
    parser.add_argument("--plugin-root", default=str(_BASE), help="Standalone plugin repository root.")
    parser.add_argument(
        "--host-root",
        default=str(_BASE.parent / "N.E.K.O"),
        help="N.E.K.O host repository root for optional host contract tests and plugin check.",
    )
    parser.add_argument("--run", action="store_true", help="Execute checks instead of printing the plan.")
    parser.add_argument(
        "--include-local-sample",
        action="store_true",
        help="Also run local sample reports when local_samples/data_process_20260620 exists.",
    )
    parser.add_argument(
        "--final-smoke-evidence",
        help="Optional post-smoke evidence JSON to validate with final_smoke_evidence_gate.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    checks = build_checks(
        plugin_root=args.plugin_root,
        host_root=args.host_root,
        include_local_sample=args.include_local_sample,
        final_smoke_evidence=args.final_smoke_evidence,
    )
    sample_summary = (
        _load_sample_summary(args.plugin_root, "local_samples/data_process_20260620")
        if args.include_local_sample
        else None
    )
    sample_root = pathlib.Path(args.plugin_root).resolve() / "local_samples/data_process_20260620"
    v2_summary = build_v2_readiness(
        sample_root=sample_root if args.include_local_sample and sample_root.exists() else None,
        player_name="tl0sr2",
    )
    payload = (
        run_checks(checks, stream_output=not args.json)
        if args.run
        else plan_payload(checks, sample_summary=sample_summary, v2_summary=v2_summary)
    )
    if args.run and payload.get("status") == "pass":
        payload["release_scope"] = build_release_scope(sample_summary)
        payload["handoff"] = build_handoff(payload["release_scope"], v2_summary)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(payload), end="")
    return 0 if payload["status"] in {"plan", "pass"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
