"""Unified offline preflight helper tests."""

from __future__ import annotations

import contextlib
import io
import tempfile
import types
from pathlib import Path


def test_preflight_plan_contains_documented_checks():
    from neko_warthunder.tools import preflight

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plugin_root = root / "plugin"
        host_root = root / "N.E.K.O"
        sample_root = plugin_root / "local_samples" / "data_process_20260620"
        sample_root.mkdir(parents=True)
        host_root.mkdir()

        checks = preflight.build_checks(plugin_root=plugin_root, host_root=host_root)
        names = [check.name for check in checks]

        assert names == [
            "logic self-check",
            "pytest",
            "vehicle profile id audit",
            "release defaults gate",
            "output freshness gate",
            "host boundary gate",
            "free-text release gate",
            "replay degrade gate",
            "ownership replay gate",
            "deferred HUD notice gate",
            "mode/domain boundary gate",
            "proximity/objective awareness gate",
            "V2 readiness summary",
            "V2 release matrix",
            "V2 output policy gate",
            "V2 completion gate",
            "RC handoff report",
            "final smoke packet",
            "plugin check",
            "runtime smoke",
            "synthetic replay",
            "local sample replay",
            "V2 readiness with local sample",
            "V2 release matrix with local sample",
            "V2 completion gate with local sample",
            "RC handoff report with local sample",
            "offline readiness report",
            "rc gap summary",
            "live test plan",
        ]
        assert checks[0].cwd == plugin_root.resolve()
        assert checks[0].cmd == ["uv", "run", "python", "tests/run_logic_tests.py"]
        assert checks[2].cmd == ["uv", "run", "python", "tools/vehicle_profile_id_audit.py"]
        assert "vehicle_type" in checks[2].review_hint
        assert checks[3].cmd == ["uv", "run", "python", "tools/release_defaults_gate.py"]
        assert "dry_run-first" in checks[3].review_hint
        assert checks[4].cmd == ["uv", "run", "python", "tools/output_freshness_gate.py"]
        assert "coalesce" in checks[4].review_hint
        assert "plugin-owned dialogue policy" in checks[4].review_hint
        assert checks[5].cmd[:4] == ["uv", "run", "python", "tools/host_contract_gate.py"]
        assert checks[5].cmd[-2] == "--host-root"
        assert "must not contain" in checks[5].review_hint
        assert checks[6].cmd == ["uv", "run", "python", "tools/free_text_gate.py"]
        assert "hudmsg" in checks[6].review_hint
        assert "push_message" in checks[6].review_hint
        assert checks[7].cmd == ["uv", "run", "python", "tools/replay_gate.py"]
        assert "replay=true" in checks[7].review_hint
        assert "push_message" in checks[7].review_hint
        assert checks[8].cmd == ["uv", "run", "python", "tools/ownership_replay_gate.py"]
        assert "interference unowned" in checks[8].review_hint
        assert checks[9].cmd == ["uv", "run", "python", "tools/deferred_hud_gate.py"]
        assert "powertrain_failure" in checks[9].review_hint
        assert checks[10].cmd == ["uv", "run", "python", "tools/domain_boundary_gate.py"]
        assert "air-only" in checks[10].review_hint
        assert checks[11].cmd == ["uv", "run", "python", "tools/proximity_gate.py"]
        assert "proximity.events" in checks[11].review_hint
        assert checks[12].cmd == ["uv", "run", "python", "tools/v2_readiness.py", "--no-sample"]
        assert checks[13].cmd == ["uv", "run", "python", "tools/v2_release_matrix.py", "--no-sample"]
        assert checks[14].cmd == ["uv", "run", "python", "tools/v2_output_policy_gate.py"]
        assert checks[15].cmd == ["uv", "run", "python", "tools/v2_completion_gate.py", "--no-sample"]
        assert checks[16].cmd == ["uv", "run", "python", "tools/rc_handoff_report.py", "--no-sample"]
        assert checks[17].cmd == ["uv", "run", "python", "tools/final_smoke_packet.py"]
        assert checks[18].cwd == host_root.resolve()
        assert checks[18].cmd[-1] == str(plugin_root.resolve())
        assert checks[19].cmd == ["uv", "run", "python", "tools/live_monitor.py", "--count", "1"]
        assert "dry_run" in checks[19].review_hint
        assert "paused" in checks[19].review_hint
        assert "8112" in checks[19].review_hint
        assert checks[-1].cmd == [
            "uv",
            "run",
            "python",
            "tools/live_test_plan.py",
            "local_samples/data_process_20260620",
            "tl0sr2",
        ]
        assert checks[-2].cmd == [
            "uv",
            "run",
            "python",
            "tools/rc_gap_summary.py",
            "local_samples/data_process_20260620",
            "tl0sr2",
        ]
        assert checks[-3].cmd == [
            "uv",
            "run",
            "python",
            "tools/offline_report.py",
            "local_samples/data_process_20260620",
            "tl0sr2",
        ]
        assert checks[-4].cmd == [
            "uv",
            "run",
            "python",
            "tools/rc_handoff_report.py",
            "--sample-rel",
            "local_samples/data_process_20260620",
            "--player-name",
            "tl0sr2",
            "--offline-gates-passed",
        ]
        assert checks[-5].cmd == [
            "uv",
            "run",
            "python",
            "tools/v2_completion_gate.py",
            "local_samples/data_process_20260620",
            "tl0sr2",
        ]
        assert checks[-6].cmd == [
            "uv",
            "run",
            "python",
            "tools/v2_release_matrix.py",
            "local_samples/data_process_20260620",
            "tl0sr2",
        ]
        assert checks[-7].cmd == [
            "uv",
            "run",
            "python",
            "tools/v2_readiness.py",
            "local_samples/data_process_20260620",
            "tl0sr2",
        ]
        assert checks[-8].cmd == [
            "uv",
            "run",
            "python",
            "tools/sample_replay.py",
            "local_samples/data_process_20260620",
            "tl0sr2",
        ]


def test_preflight_plan_skips_optional_sample_when_missing():
    from neko_warthunder.tools import preflight

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        checks = preflight.build_checks(plugin_root=root, host_root=root / "missing-host")
        names = [check.name for check in checks]

        assert "plugin check" not in names
        assert "host War Thunder contract tests" not in names
        assert "local sample replay" not in names
        assert "offline readiness report" not in names
        assert "rc gap summary" not in names
        assert "live test plan" not in names
        assert names == [
            "logic self-check",
            "pytest",
            "vehicle profile id audit",
            "release defaults gate",
            "output freshness gate",
            "host boundary gate",
            "free-text release gate",
            "replay degrade gate",
            "ownership replay gate",
            "deferred HUD notice gate",
            "mode/domain boundary gate",
            "proximity/objective awareness gate",
            "V2 readiness summary",
            "V2 release matrix",
            "V2 output policy gate",
            "V2 completion gate",
            "RC handoff report",
            "final smoke packet",
            "runtime smoke",
            "synthetic replay",
        ]


def test_preflight_can_include_final_smoke_evidence_gate_explicitly():
    from neko_warthunder.tools import preflight

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        evidence = root / "local_test_logs" / "final_smoke_evidence.json"
        checks = preflight.build_checks(
            plugin_root=root,
            host_root=root / "missing-host",
            final_smoke_evidence=evidence,
        )
        names = [check.name for check in checks]

    assert "final smoke evidence gate" in names
    evidence_check = next(check for check in checks if check.name == "final smoke evidence gate")
    assert evidence_check.cmd == [
        "uv",
        "run",
        "python",
        "tools/final_smoke_evidence_gate.py",
        str(evidence),
    ]
    assert "post-smoke P1 evidence" in evidence_check.review_hint


def test_preflight_dry_run_prints_commands_without_running():
    from neko_warthunder.tools import preflight

    with tempfile.TemporaryDirectory() as td:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = preflight.main(["--plugin-root", td])

        text = output.getvalue()
        assert rc == 0
        assert "# neko_warthunder offline preflight" in text
        assert "## Quick read" in text
        assert "baseline: logic self-check should report 493/493 passed" in text
        assert "vehicle profile id audit must keep" in text
        assert "release defaults gate must keep dry_run-first" in text
        assert "output freshness gate must prove battle pushes are fresh" in text
        assert "host boundary gate must prove" in text
        assert "free-text release gate must pass" in text
        assert "replay degrade gate must pass" in text
        assert "ownership replay gate must keep" in text
        assert "deferred HUD notice gate must pass" in text
        assert "mode/domain boundary gate must keep" in text
        assert "proximity/objective awareness gate must pass" in text
        assert "V2 readiness summary must separate offline-complete code" in text
        assert "V2 release matrix must show" in text
        assert "V2 output policy gate must keep" in text
        assert "V2 completion gate must prove" in text
        assert "RC handoff report must summarize" in text
        assert "final smoke packet must summarize go/no-go" in text
        assert "final smoke evidence gate is optional" in text
        assert "if this passes: keep dry_run=true and follow the live test plan" in text
        assert "if this fails: stop before real-machine testing" in text
        assert "watch live_monitor Summary first" in text
        assert "uv run python tests/run_logic_tests.py" in text
        assert "uv run pytest -c tests/pytest.ini tests -q" in text
        assert "vehicle profile id audit" in text
        assert "uv run python tools/vehicle_profile_id_audit.py" in text
        assert "release defaults gate" in text
        assert "uv run python tools/release_defaults_gate.py" in text
        assert "output freshness gate" in text
        assert "uv run python tools/output_freshness_gate.py" in text
        assert "free-text release gate" in text
        assert "uv run python tools/free_text_gate.py" in text
        assert "replay degrade gate" in text
        assert "uv run python tools/replay_gate.py" in text
        assert "ownership replay gate" in text
        assert "uv run python tools/ownership_replay_gate.py" in text
        assert "deferred HUD notice gate" in text
        assert "uv run python tools/deferred_hud_gate.py" in text
        assert "mode/domain boundary gate" in text
        assert "uv run python tools/domain_boundary_gate.py" in text
        assert "proximity/objective awareness gate" in text
        assert "uv run python tools/proximity_gate.py" in text
        assert "V2 readiness summary" in text
        assert "uv run python tools/v2_readiness.py --no-sample" in text
        assert "V2 release matrix" in text
        assert "uv run python tools/v2_release_matrix.py --no-sample" in text
        assert "V2 output policy gate" in text
        assert "uv run python tools/v2_output_policy_gate.py" in text
        assert "V2 completion gate" in text
        assert "uv run python tools/v2_completion_gate.py --no-sample" in text
        assert "RC handoff report" in text
        assert "uv run python tools/rc_handoff_report.py --no-sample" in text
        assert "final smoke packet" in text
        assert "uv run python tools/final_smoke_packet.py" in text
        assert "runtime smoke" in text
        assert "tools/live_monitor.py --count 1" in text
        assert "dry_run / paused / Hosted UI / 8112 ownership / duplicate plugin scan risk" in text
        assert "uv run python tools/replay.py" in text
        assert "use --run to execute" in text


def test_preflight_plan_points_sample_replay_to_session_summary():
    from neko_warthunder.tools import preflight

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sample_root = root / "local_samples" / "data_process_20260620"
        sample_root.mkdir(parents=True)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            rc = preflight.main(["--plugin-root", str(root), "--host-root", str(root / "missing-host")])

        text = output.getvalue()
        assert rc == 0
        assert "local sample replay" in text
        assert "V2 readiness with local sample" in text
        assert "V2 release matrix with local sample" in text
        assert "V2 completion gate with local sample" in text
        assert "RC handoff report with local sample" in text
        assert "review: session_summary" in text
        assert "next validation steps" in text
        assert "Operator quick checklist" in text
        assert "quick_checklist" in text
        assert "rc gap summary" in text
        assert "live test plan" in text


def test_preflight_can_write_offline_readiness_report_to_file():
    from neko_warthunder.tools import preflight

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sample_root = root / "local_samples" / "data_process_20260620"
        report_out = root / "out" / "offline-report.md"
        sample_root.mkdir(parents=True)

        checks = preflight.build_checks(
            plugin_root=root,
            host_root=root / "missing-host",
            report_output=report_out,
        )

    offline = next(check for check in checks if check.name == "offline readiness report")
    assert offline.name == "offline readiness report"
    assert offline.cmd[-2:] == ["--output", str(report_out)]


def test_preflight_run_success_prints_next_action():
    from neko_warthunder.tools import preflight

    calls: list[list[str]] = []

    def fake_run(cmd, cwd):
        calls.append(list(cmd))
        return types.SimpleNamespace(returncode=0)

    checks = [
        preflight.Check("logic self-check", Path.cwd(), ["uv", "run", "python", "tests/run_logic_tests.py"]),
        preflight.Check("runtime smoke", Path.cwd(), ["uv", "run", "python", "tools/live_monitor.py", "--count", "1"]),
    ]
    output = io.StringIO()

    original_run = preflight.subprocess.run
    preflight.subprocess.run = fake_run
    try:
        with contextlib.redirect_stdout(output):
            rc = preflight.run_checks(checks)
    finally:
        preflight.subprocess.run = original_run

    text = output.getvalue()
    assert rc == 0
    assert len(calls) == 2
    assert "preflight passed: ready for dry_run live validation" in text
    assert "keep dry_run=true" in text


def test_preflight_run_failure_tells_operator_to_stop():
    from neko_warthunder.tools import preflight

    def fake_run(cmd, cwd):
        return types.SimpleNamespace(returncode=7)

    checks = [preflight.Check("runtime smoke", Path.cwd(), ["uv", "run", "python", "tools/live_monitor.py"])]
    output = io.StringIO()

    original_run = preflight.subprocess.run
    preflight.subprocess.run = fake_run
    try:
        with contextlib.redirect_stdout(output):
            rc = preflight.run_checks(checks)
    finally:
        preflight.subprocess.run = original_run

    text = output.getvalue()
    assert rc == 7
    assert "FAILED: runtime smoke exited with 7" in text
    assert "stop before real-machine testing" in text

