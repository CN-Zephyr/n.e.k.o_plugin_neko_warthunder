"""Unified offline preflight helper for the next live test.

By default this prints the documented offline checks. Pass ``--run`` to execute
them in order. Optional checks are included only when their local paths exist.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import types
from dataclasses import dataclass
from typing import Sequence

_BASE = pathlib.Path(__file__).resolve().parent.parent
if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg


@dataclass(frozen=True)
class Check:
    name: str
    cwd: pathlib.Path
    cmd: list[str]
    review_hint: str = ""


def build_checks(
    *,
    plugin_root: str | pathlib.Path,
    host_root: str | pathlib.Path | None = None,
    sample_rel: str = "local_samples/data_process_20260620",
    report_output: str | pathlib.Path | None = None,
    final_smoke_evidence: str | pathlib.Path | None = None,
) -> list[Check]:
    plugin = pathlib.Path(plugin_root).resolve()
    host = pathlib.Path(host_root).resolve() if host_root is not None else plugin.parent / "N.E.K.O"
    sample = plugin / pathlib.Path(sample_rel)

    checks = [
        Check("logic self-check", plugin, ["uv", "run", "python", "tests/run_logic_tests.py"]),
        Check("pytest", plugin, ["uv", "run", "pytest", "-c", "tests/pytest.ini", "tests", "-q"]),
        Check(
            "vehicle profile id audit",
            plugin,
            ["uv", "run", "python", "tools/vehicle_profile_id_audit.py"],
            "vehicle profile keys must follow Wiki gameId / runtime vehicle_type identity policy",
        ),
        Check(
            "release defaults gate",
            plugin,
            ["uv", "run", "python", "tools/release_defaults_gate.py"],
            "release defaults must stay dry_run-first with unverified real output closed",
        ),
        Check(
            "output freshness gate",
            plugin,
            ["uv", "run", "python", "tools/output_freshness_gate.py"],
            "real battle push must carry coalesce/freshness/target/short-reply metadata and drop expired cues",
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
            "local host, when present, must consume short-reply metadata and apply War Thunder user-chat quieting",
        ),
        Check(
            "free-text release gate",
            plugin,
            ["uv", "run", "python", "tools/free_text_gate.py"],
            "hudmsg / combat.feed / awards raw text must stay out of prompt and push_message text",
        ),
        Check(
            "replay degrade gate",
            plugin,
            ["uv", "run", "python", "tools/replay_gate.py"],
            "replay=true frames must not emit Detector candidates, prompts, or push_message output",
        ),
        Check(
            "ownership replay gate",
            plugin,
            ["uv", "run", "python", "tools/ownership_replay_gate.py"],
            "legacy third-party samples must require explicit identity inference and keep interference unowned",
        ),
        Check(
            "deferred HUD notice gate",
            plugin,
            ["uv", "run", "python", "tools/deferred_hud_gate.py"],
            "powertrain_failure HUD notices must stay observable but non-speech without raw HUD text",
        ),
        Check(
            "proximity/objective awareness gate",
            plugin,
            ["uv", "run", "python", "tools/proximity_gate.py"],
            "V2 proximity.events / situation.ground_targets must produce safe metadata prompts and obey Arbiter gating",
        ),
        Check(
            "V2 readiness summary",
            plugin,
            ["uv", "run", "python", "tools/v2_readiness.py", "--no-sample"],
            "V2 offline scope should be complete while live-only evidence stays explicit",
        ),
        Check(
            "V2 release matrix",
            plugin,
            ["uv", "run", "python", "tools/v2_release_matrix.py", "--no-sample"],
            "V2 capability rows must show code/offline/live evidence and dry_run-first policy",
        ),
        Check(
            "V2 output policy gate",
            plugin,
            ["uv", "run", "python", "tools/v2_output_policy_gate.py"],
            "V2 live-evidence-gated capabilities must suppress real output until explicitly verified",
        ),
        Check(
            "V2 completion gate",
            plugin,
            ["uv", "run", "python", "tools/v2_completion_gate.py", "--no-sample"],
            "V2 code/offline scope must be complete while live-only evidence remains explicit",
        ),
        Check(
            "RC handoff report",
            plugin,
            ["uv", "run", "python", "tools/rc_handoff_report.py", "--no-sample"],
            "maintainer handoff must separate v1 release scope, V2 completion, safety boundary, and live evidence gaps",
        ),
        Check(
            "final smoke packet",
            plugin,
            ["uv", "run", "python", "tools/final_smoke_packet.py"],
            "single safe handoff packet for final dry_run live smoke",
        ),
    ]
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
                "post-smoke P1 evidence must pass without raw chat/HUD/combat/award text",
            )
        )
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
                "host behavior must consume short battle replies and quiet ordinary War Thunder cues during user chat",
            )
        )
        checks.append(
            Check(
                "plugin check",
                host,
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "plugin.neko_plugin_cli.cli",
                    "check",
                    str(plugin),
                ],
            )
        )
    checks.append(
        Check(
            "runtime smoke",
            plugin,
            ["uv", "run", "python", "tools/live_monitor.py", "--count", "1"],
            "dry_run / paused / Hosted UI / 8112 ownership / duplicate plugin scan risk",
        )
    )
    checks.append(Check("synthetic replay", plugin, ["uv", "run", "python", "tools/replay.py"]))
    if sample.exists():
        checks.append(
            Check(
                "local sample replay",
                plugin,
                ["uv", "run", "python", "tools/sample_replay.py", sample_rel, "tl0sr2"],
                "session_summary for observed outputs and next validation steps",
            )
        )
        checks.append(
            Check(
                "V2 readiness with local sample",
                plugin,
                ["uv", "run", "python", "tools/v2_readiness.py", sample_rel, "tl0sr2"],
                "V2 sample evidence summary for rear/six threat and objective proximity",
            )
        )
        checks.append(
            Check(
                "V2 release matrix with local sample",
                plugin,
                ["uv", "run", "python", "tools/v2_release_matrix.py", sample_rel, "tl0sr2"],
                "V2 capability matrix for code/offline/live-evidence handoff without raw telemetry text",
            )
        )
        checks.append(
            Check(
                "V2 completion gate with local sample",
                plugin,
                ["uv", "run", "python", "tools/v2_completion_gate.py", sample_rel, "tl0sr2"],
                "single V2 done/pending verdict for handoff without claiming missing live-only evidence",
            )
        )
        checks.append(
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
                "safe human-readable RC handoff for maintainers before the final live smoke",
            )
        )
        checks.append(
            Check(
                "offline readiness report",
                plugin,
                _offline_report_cmd(sample_rel, report_output),
                "Markdown summary with Team brief, Operator quick checklist, quick_checklist JSON, and next live-test scope",
            )
        )
        checks.append(
            Check(
                "rc gap summary",
                plugin,
                ["uv", "run", "python", "tools/rc_gap_summary.py", sample_rel, "tl0sr2"],
                "compact v1/v2 remaining gap summary for release handoff without raw telemetry text",
            )
        )
        checks.append(
            Check(
                "live test plan",
                plugin,
                ["uv", "run", "python", "tools/live_test_plan.py", sample_rel, "tl0sr2"],
                "Operator quick checklist plus detailed operation steps for the next live validation run",
            )
        )
    return checks


def _offline_report_cmd(sample_rel: str, report_output: str | pathlib.Path | None) -> list[str]:
    cmd = ["uv", "run", "python", "tools/offline_report.py", sample_rel, "tl0sr2"]
    if report_output is not None:
        cmd.extend(["--output", str(report_output)])
    return cmd


def _format_cmd(check: Check) -> str:
    return " ".join(check.cmd)


def print_plan(checks: Sequence[Check]) -> None:
    print("# neko_warthunder offline preflight")
    print("## Quick read")
    print("- baseline: logic self-check should report 369/369 passed")
    print("- vehicle profile id audit must keep Wiki gameId / runtime vehicle_type identity policy intact")
    print("- release defaults gate must keep dry_run-first and unverified real output closed")
    print("- output freshness gate must prove battle pushes are fresh, coalesced, targeted, and short-reply constrained")
    print("- host contract gate must prove the local host consumes short-reply metadata and quiets ordinary battle cues during user chat")
    print("- host War Thunder contract tests should pass when a local N.E.K.O checkout is present")
    print("- free-text release gate must pass before hudmsg / combat.feed / awards can be unstubbed")
    print("- replay degrade gate must pass before replay=true traffic can be considered safe")
    print("- ownership replay gate must keep third-party sample ownership explicit and interference unowned")
    print("- deferred HUD notice gate must pass before powertrain_failure strategy can change")
    print("- proximity/objective awareness gate must pass before V2 proximity/objective prompts can be considered safe")
    print("- V2 readiness summary must separate offline-complete code from live-only sample evidence")
    print("- V2 release matrix must show which capabilities are dry_run-first until live evidence exists")
    print("- V2 output policy gate must keep unverified V2 capabilities from real push")
    print("- V2 completion gate must prove V2 code/offline completion without claiming missing live evidence")
    print("- RC handoff report must summarize v1/v2 state, safety boundary, and remaining live evidence")
    print("- final smoke packet must summarize go/no-go, commands, V2 evidence, and safety boundary")
    print("- final smoke evidence gate is optional; use --final-smoke-evidence after a real smoke run")
    print("- watch live_monitor Summary first for health, dry_run, Hosted UI, 8112, and output reasons")
    print("- if this passes: keep dry_run=true and follow the live test plan")
    print("- if this fails: stop before real-machine testing and fix the failed check")
    print("\n## Checks")
    for index, check in enumerate(checks, start=1):
        print(f"{index}. {check.name}")
        print(f"   cwd: {check.cwd}")
        print(f"   cmd: {_format_cmd(check)}")
        if check.review_hint:
            print(f"   review: {check.review_hint}")
    print("\nuse --run to execute")


def run_checks(checks: Sequence[Check]) -> int:
    for check in checks:
        print(f"\n==> {check.name}")
        print(f"cwd: {check.cwd}")
        print(f"cmd: {_format_cmd(check)}")
        completed = subprocess.run(check.cmd, cwd=check.cwd)
        if completed.returncode != 0:
            print(f"FAILED: {check.name} exited with {completed.returncode}")
            print("stop before real-machine testing; fix this check first")
            return completed.returncode
    print("\npreflight passed: ready for dry_run live validation")
    print("keep dry_run=true, then follow tools/live_test_plan.py and watch live_monitor Summary first")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or print neko_warthunder offline preflight checks.")
    parser.add_argument("--plugin-root", default=str(_BASE), help="Standalone plugin repository root.")
    parser.add_argument(
        "--host-root",
        default=str(_BASE.parent / "N.E.K.O"),
        help="N.E.K.O host repository root for host contract gates and plugin check.",
    )
    parser.add_argument("--run", action="store_true", help="Execute checks instead of only printing them.")
    parser.add_argument("--report-output", help="Write the offline readiness Markdown report to this path.")
    parser.add_argument(
        "--final-smoke-evidence",
        help="Optional post-smoke evidence JSON to validate with final_smoke_evidence_gate.",
    )
    args = parser.parse_args(argv)

    checks = build_checks(
        plugin_root=args.plugin_root,
        host_root=args.host_root,
        report_output=args.report_output,
        final_smoke_evidence=args.final_smoke_evidence,
    )
    if not args.run:
        print_plan(checks)
        return 0
    return run_checks(checks)


if __name__ == "__main__":
    raise SystemExit(main())
