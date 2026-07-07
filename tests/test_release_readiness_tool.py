"""Release readiness helper tests."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import types
from pathlib import Path


def test_release_readiness_plan_lists_offline_release_gates():
    from neko_warthunder.tools import release_readiness

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        host = root / "N.E.K.O"
        host.mkdir()

        checks = release_readiness.build_checks(plugin_root=root / "plugin", host_root=host)
        names = [check.name for check in checks]

        assert names == [
            "logic self-check",
            "pytest",
            "rc docs audit",
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
            "synthetic replay",
            "plugin check",
            "final smoke packet",
        ]
        assert checks[2].cmd == ["uv", "run", "python", "tools/rc_audit.py"]
        assert checks[3].cmd == ["uv", "run", "python", "tools/vehicle_profile_id_audit.py"]
        assert checks[4].cmd == ["uv", "run", "python", "tools/release_defaults_gate.py"]
        assert checks[5].cmd == ["uv", "run", "python", "tools/output_freshness_gate.py"]
        assert checks[6].cmd[:4] == ["uv", "run", "python", "tools/host_contract_gate.py"]
        assert checks[6].cmd[-2] == "--host-root"
        assert checks[7].cmd == ["uv", "run", "python", "tools/free_text_gate.py"]
        assert checks[8].cmd == ["uv", "run", "python", "tools/replay_gate.py"]
        assert checks[9].cmd == ["uv", "run", "python", "tools/ownership_replay_gate.py"]
        assert checks[10].cmd == ["uv", "run", "python", "tools/deferred_hud_gate.py"]
        assert checks[11].cmd == ["uv", "run", "python", "tools/domain_boundary_gate.py"]
        assert checks[12].cmd == ["uv", "run", "python", "tools/proximity_gate.py"]
        assert checks[13].cmd == ["uv", "run", "python", "tools/v2_readiness.py", "--no-sample"]
        assert checks[14].cmd == ["uv", "run", "python", "tools/v2_release_matrix.py", "--no-sample"]
        assert checks[15].cmd == ["uv", "run", "python", "tools/v2_output_policy_gate.py"]
        assert checks[16].cmd == ["uv", "run", "python", "tools/v2_completion_gate.py", "--no-sample"]
        assert checks[17].cmd == ["uv", "run", "python", "tools/rc_handoff_report.py", "--no-sample"]
        assert checks[18].cmd == ["uv", "run", "python", "tools/replay.py"]
        assert checks[19].cwd == host.resolve()
        assert checks[19].name == "plugin check"
        assert checks[-1].cmd == ["uv", "run", "python", "tools/final_smoke_packet.py", "--offline-gates-passed"]


def test_release_readiness_can_include_local_sample_checks_explicitly():
    from neko_warthunder.tools import release_readiness

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sample = root / "plugin" / "local_samples" / "data_process_20260620"
        sample.mkdir(parents=True)

        checks = release_readiness.build_checks(
            plugin_root=root / "plugin",
            host_root=root / "missing-host",
            include_local_sample=True,
        )
        names = [check.name for check in checks]

        assert names[-9:] == [
            "local sample replay",
            "V2 readiness with local sample",
            "V2 release matrix with local sample",
            "V2 completion gate with local sample",
            "RC handoff report with local sample",
            "offline readiness report",
            "rc gap summary",
            "live test plan",
            "final smoke packet",
        ]


def test_release_readiness_can_include_final_smoke_evidence_gate_explicitly():
    from neko_warthunder.tools import release_readiness

    with tempfile.TemporaryDirectory() as td:
        evidence = Path(td) / "final_smoke_evidence.json"
        checks = release_readiness.build_checks(
            plugin_root=td,
            host_root=Path(td) / "missing-host",
            final_smoke_evidence=evidence,
        )

    assert checks[-2].name == "final smoke packet"
    assert checks[-1].name == "final smoke evidence gate"
    assert checks[-1].cmd == [
        "uv",
        "run",
        "python",
        "tools/final_smoke_evidence_gate.py",
        str(evidence),
    ]
    assert "post-smoke P1 evidence" in checks[-1].review_hint


def test_release_readiness_plan_does_not_require_running_services():
    from neko_warthunder.tools import release_readiness

    with tempfile.TemporaryDirectory() as td:
        checks = release_readiness.build_checks(plugin_root=td, host_root=Path(td) / "missing-host")
        names = [check.name for check in checks]

        assert "runtime smoke" not in names
        assert "live monitor" not in names
        assert "host War Thunder contract tests" not in names
        assert names == [
            "logic self-check",
            "pytest",
            "rc docs audit",
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
            "synthetic replay",
            "final smoke packet",
        ]


def test_release_readiness_run_success_returns_rc_verdict():
    from neko_warthunder.tools import release_readiness

    calls: list[list[str]] = []

    def fake_run(cmd, cwd, **kwargs):
        calls.append(list(cmd))
        return types.SimpleNamespace(returncode=0)

    checks = [
        release_readiness.Check("logic self-check", Path.cwd(), ["uv", "run", "python", "tests/run_logic_tests.py"]),
        release_readiness.Check("replay degrade gate", Path.cwd(), ["uv", "run", "python", "tools/replay_gate.py"]),
    ]
    original_run = release_readiness.subprocess.run
    release_readiness.subprocess.run = fake_run
    try:
        result = release_readiness.run_checks(checks)
    finally:
        release_readiness.subprocess.run = original_run

    assert len(calls) == 2
    assert result["status"] == "pass"
    assert result["verdict"] == "ready_for_final_live_smoke"
    assert result["release_scope"]["ship_status"] == "offline_gates_passed"


def test_release_readiness_run_failure_blocks_rc():
    from neko_warthunder.tools import release_readiness

    def fake_run(cmd, cwd, **kwargs):
        return types.SimpleNamespace(returncode=9)

    checks = [release_readiness.Check("pytest", Path.cwd(), ["uv", "run", "pytest"])]
    original_run = release_readiness.subprocess.run
    release_readiness.subprocess.run = fake_run
    try:
        result = release_readiness.run_checks(checks)
    finally:
        release_readiness.subprocess.run = original_run

    assert result["status"] == "fail"
    assert result["verdict"] == "blocked"
    assert result["checks"][0]["returncode"] == 9
    assert result["release_scope"]["ship_status"] == "blocked_before_live_smoke"


def test_release_readiness_run_json_captures_failure_output():
    from neko_warthunder.tools import release_readiness

    def fake_run(cmd, cwd, **kwargs):
        return types.SimpleNamespace(
            returncode=9,
            stdout="short stdout",
            stderr="plugin check failed: syntax error",
        )

    checks = [release_readiness.Check("plugin check", Path.cwd(), ["uv", "run", "plugin-check"])]
    original_run = release_readiness.subprocess.run
    release_readiness.subprocess.run = fake_run
    try:
        result = release_readiness.run_checks(checks, stream_output=False)
    finally:
        release_readiness.subprocess.run = original_run

    assert result["status"] == "fail"
    assert result["checks"][0]["stdout"] == "short stdout"
    assert result["checks"][0]["stderr"] == "plugin check failed: syntax error"


def test_release_readiness_run_json_truncates_long_output_from_the_tail():
    from neko_warthunder.tools import release_readiness

    text = "a" * 2100 + "tail"
    compact = release_readiness._compact_process_output(text, max_chars=20)

    assert compact == "..." + text[-20:]


def test_release_readiness_cli_json_is_machine_readable():
    from neko_warthunder.tools import release_readiness

    output = io.StringIO()
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(output):
            rc = release_readiness.main(["--plugin-root", td, "--host-root", str(Path(td) / "missing"), "--json"])

    payload = json.loads(output.getvalue())

    assert rc == 0
    assert payload["status"] == "plan"
    assert payload["verdict"] == "not_run"
    assert payload["release_scope"]["ship_status"] == "not_run"
    assert "rc docs audit" in [check["name"] for check in payload["checks"]]
    assert "vehicle profile id audit" in [check["name"] for check in payload["checks"]]
    assert "release defaults gate" in [check["name"] for check in payload["checks"]]
    assert "output freshness gate" in [check["name"] for check in payload["checks"]]
    assert "replay degrade gate" in [check["name"] for check in payload["checks"]]
    assert "deferred HUD notice gate" in [check["name"] for check in payload["checks"]]
    assert "mode/domain boundary gate" in [check["name"] for check in payload["checks"]]
    assert "proximity/objective awareness gate" in [check["name"] for check in payload["checks"]]
    assert "V2 readiness summary" in [check["name"] for check in payload["checks"]]
    assert "V2 release matrix" in [check["name"] for check in payload["checks"]]
    assert "V2 output policy gate" in [check["name"] for check in payload["checks"]]
    assert "V2 completion gate" in [check["name"] for check in payload["checks"]]
    assert "RC handoff report" in [check["name"] for check in payload["checks"]]
    assert "final smoke packet" in [check["name"] for check in payload["checks"]]


def test_release_readiness_cli_can_plan_final_smoke_evidence_gate():
    from neko_warthunder.tools import release_readiness

    output = io.StringIO()
    with tempfile.TemporaryDirectory() as td:
        evidence = Path(td) / "evidence.json"
        with contextlib.redirect_stdout(output):
            rc = release_readiness.main(
                [
                    "--plugin-root",
                    td,
                    "--host-root",
                    str(Path(td) / "missing"),
                    "--final-smoke-evidence",
                    str(evidence),
                    "--json",
                ]
            )

    payload = json.loads(output.getvalue())
    assert rc == 0
    assert "final smoke evidence gate" in [check["name"] for check in payload["checks"]]


def test_release_readiness_cli_text_names_next_step():
    from neko_warthunder.tools import release_readiness

    output = io.StringIO()
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(output):
            rc = release_readiness.main(["--plugin-root", td, "--host-root", str(Path(td) / "missing")])

    text = output.getvalue()

    assert rc == 0
    assert "# neko_warthunder v1 release readiness" in text
    assert "vehicle profile id audit" in text
    assert "release defaults gate" in text
    assert "output freshness gate" in text
    assert "replay degrade gate" in text
    assert "deferred HUD notice gate" in text
    assert "mode/domain boundary gate" in text
    assert "proximity/objective awareness gate" in text
    assert "V2 readiness summary" in text
    assert "V2 release matrix" in text
    assert "V2 output policy gate" in text
    assert "V2 completion gate" in text
    assert "RC handoff report" in text
    assert "final smoke packet" in text
    assert "final live smoke" in text
    assert "ship_status:" in text


def test_release_readiness_plan_can_include_v2_sample_evidence():
    from neko_warthunder.tools import release_readiness

    sample_summary = {"blocked_release_items": [], "sample_unproven_items": [], "next_actions": []}
    v2_summary = {
        "release_scope": {
            "v2_code_complete": True,
            "v2_offline_gate_complete": True,
            "v2_live_evidence_complete": False,
        },
        "live_evidence": {
            "status": "needs_live_sample",
            "missing": ["rear_threat_candidates"],
            "next_actions": ["capture_rear_threat_or_six_oclock_sample"],
        },
    }

    payload = release_readiness.plan_payload([], sample_summary=sample_summary, v2_summary=v2_summary)

    assert payload["status"] == "plan"
    assert payload["handoff"]["v2"]["live_evidence_status"] == "needs_live_sample"
    assert payload["handoff"]["v2"]["missing"] == ["rear_threat_candidates"]


def test_release_readiness_scope_summarizes_sample_gaps_without_raw_text():
    from neko_warthunder.tools import release_readiness

    sample = {
        "status": "needs_more_samples",
        "sample_unproven_items": ["v2_proximity_objective"],
        "blocked_release_items": ["v1_free_text_output"],
        "next_actions": ["fly_closer_to_ground_target_sample", "run_free_text_dry_run_safety_check"],
        "safety": {"free_text_real_output_allowed": False},
    }

    scope = release_readiness.build_release_scope(sample)

    assert scope["ship_status"] == "offline_gates_passed"
    assert scope["final_live_smoke_required"] is True
    assert scope["real_output_blockers"] == ["v1_free_text_output"]
    assert scope["sample_unproven_items"] == ["v2_proximity_objective"]
    assert "fly_closer_to_ground_target_sample" in scope["next_actions"]
    assert "raw" not in json.dumps(scope, ensure_ascii=False).lower()


def test_release_readiness_handoff_separates_v1_scope_and_v2_live_evidence():
    from neko_warthunder.tools import release_readiness

    release_scope = {
        "ship_status": "offline_gates_passed",
        "final_live_smoke_required": True,
        "real_output_blockers": ["v1_free_text_output"],
        "sample_unproven_items": ["v2_proximity_objective"],
        "next_actions": ["run_free_text_dry_run_safety_check"],
        "free_text_real_output_allowed": False,
    }
    v2_summary = {
        "release_scope": {
            "v2_code_complete": True,
            "v2_offline_gate_complete": True,
            "v2_live_evidence_complete": False,
        },
        "live_evidence": {
            "status": "needs_live_sample",
            "missing": ["rear_threat_candidates", "ground_target_close_candidates"],
            "next_actions": ["capture_rear_threat_or_six_oclock_sample"],
        },
    }

    handoff = release_readiness.build_handoff(release_scope, v2_summary)

    assert handoff["status"] == "ready_for_final_live_smoke"
    assert handoff["v1"]["real_output_blockers"] == ["v1_free_text_output"]
    assert handoff["v1"]["free_text_real_output_allowed"] is False
    assert handoff["v2"]["code_complete"] is True
    assert handoff["v2"]["offline_gate_complete"] is True
    assert handoff["v2"]["live_evidence_complete"] is False
    assert handoff["v2"]["missing"] == ["rear_threat_candidates", "ground_target_close_candidates"]
    assert "capture_rear_threat_or_six_oclock_sample" in handoff["next_actions"]


def test_release_readiness_run_json_is_single_parseable_payload():
    from neko_warthunder.tools import release_readiness

    def fake_run(cmd, cwd, **kwargs):
        return types.SimpleNamespace(returncode=0)

    original_run = release_readiness.subprocess.run
    release_readiness.subprocess.run = fake_run
    output = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as td:
            with contextlib.redirect_stdout(output):
                rc = release_readiness.main(
                    ["--plugin-root", td, "--host-root", str(Path(td) / "missing"), "--run", "--json"]
                )
    finally:
        release_readiness.subprocess.run = original_run

    payload = json.loads(output.getvalue())
    assert rc == 0
    assert payload["status"] == "pass"
    assert payload["release_scope"]["ship_status"] == "offline_gates_passed"
    assert payload["handoff"]["status"] == "ready_for_final_live_smoke"
    assert payload["handoff"]["v2"]["offline_gate_complete"] is True
