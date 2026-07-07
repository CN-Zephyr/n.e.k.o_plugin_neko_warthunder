"""Final smoke evidence gate tests."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest


def _passing_evidence() -> dict:
    return {
        "dry_run_first": True,
        "raw_text_printed": False,
        "runtime_focus_checks": [
            {
                "id": "real_output_freshness",
                "status": "pass",
                "observed": {
                    "event_age_seconds": 2.5,
                    "coalesce_key": "neko_warthunder:battle_event",
                    "target_lanlan": "Lanlan",
                    "battle_reply_contract": "short_tts_line",
                    "live_reply_contract": "short_tts_line",
                    "max_reply_chars": 28,
                    "expired_event_pushed": False,
                },
            },
            {
                "id": "critical_replaces_stale_warning",
                "status": "pass",
                "observed": {
                    "critical_replaced_stale_warning": True,
                    "old_warning_spoken_after_critical": False,
                },
            },
            {
                "id": "user_chat_quiet_window",
                "status": "pass",
                "observed": {
                    "ordinary_cue_spoken_during_user_turn": False,
                    "death_or_critical_allowed": True,
                },
            },
            {
                "id": "short_tts_contract",
                "status": "pass",
                "observed": {
                    "battle_reply_contract": "short_tts_line",
                    "live_reply_contract": "short_tts_line",
                    "max_reply_chars": 28,
                    "continued_across_chunks": False,
                },
            },
            {
                "id": "mode_domain_boundary",
                "status": "pass",
                "observed": {
                    "fixed_wing_cues_air_only": True,
                    "ground_status_cues_ground_only": True,
                    "ground_status_not_critical_risk": True,
                },
            },
        ],
    }


def test_final_smoke_evidence_gate_passes_complete_evidence(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_passing_evidence()), encoding="utf-8")

    result = final_smoke_evidence_gate.run_gate(evidence)

    assert result["status"] == "pass"
    assert result["failures"] == []
    assert [item["id"] for item in result["focus_checks"]] == [
        "real_output_freshness",
        "critical_replaces_stale_warning",
        "user_chat_quiet_window",
        "short_tts_contract",
        "mode_domain_boundary",
    ]
    assert result["policy"]["raw_chat_hud_combat_award_text_forbidden"] is True


def test_final_smoke_evidence_gate_fails_missing_focus_check(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    payload = _passing_evidence()
    payload["runtime_focus_checks"] = [
        item for item in payload["runtime_focus_checks"] if item["id"] != "short_tts_contract"
    ]
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = final_smoke_evidence_gate.run_gate(evidence)

    assert result["status"] == "fail"
    assert {
        "check": "short_tts_contract",
        "target": "entry",
        "reason": "missing",
    } in result["failures"]


def test_final_smoke_evidence_gate_fails_stale_warning_after_critical(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    payload = _passing_evidence()
    payload["runtime_focus_checks"][1]["observed"]["old_warning_spoken_after_critical"] = True
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = final_smoke_evidence_gate.run_gate(evidence)

    assert result["status"] == "fail"
    assert any(
        failure["check"] == "critical_replaces_stale_warning"
        and failure["target"] == "old_warning_spoken_after_critical"
        for failure in result["failures"]
    )


def test_final_smoke_evidence_gate_rejects_raw_text_fields(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    payload = _passing_evidence()
    payload["runtime_focus_checks"][0]["observed"]["raw_hud"] = "unsafe original hud text"
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = final_smoke_evidence_gate.run_gate(evidence)

    assert result["status"] == "fail"
    assert any(failure["check"] == "privacy" for failure in result["failures"])


def test_final_smoke_evidence_gate_cli_template_and_json(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    template_out = io.StringIO()
    with contextlib.redirect_stdout(template_out):
        template_rc = final_smoke_evidence_gate.main(["--template"])
    template = json.loads(template_out.getvalue())

    assert template_rc == 0
    assert template["runtime_focus_checks"][0]["id"] == "real_output_freshness"

    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_passing_evidence()), encoding="utf-8")
    result_out = io.StringIO()
    with contextlib.redirect_stdout(result_out):
        rc = final_smoke_evidence_gate.main([str(evidence), "--json"])

    result = json.loads(result_out.getvalue())
    assert rc == 0
    assert result["status"] == "pass"


def test_final_smoke_evidence_gate_rehearsal_writes_safe_artifacts(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    output = io.StringIO()
    rehearsal_dir = tmp_path / "final_smoke_rehearsal"

    with contextlib.redirect_stdout(output):
        rc = final_smoke_evidence_gate.main(["--rehearsal-output-dir", str(rehearsal_dir)])

    result = json.loads(output.getvalue())
    paths = result["paths"]
    evidence = json.loads((rehearsal_dir / "final_smoke_evidence.rehearsal.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert result["status"] == "pass"
    assert result["rehearsal_only"] is True
    assert result["starts_services"] is False
    assert result["raw_text_printed"] is False
    assert pathlib.Path(paths["monitor"]).exists()
    assert pathlib.Path(paths["safe_transcript"]).exists()
    assert pathlib.Path(paths["evidence"]).exists()
    assert pathlib.Path(paths["gate_result"]).exists()
    assert result["gate"]["status"] == "pass"
    assert {item["status"] for item in evidence["runtime_focus_checks"]} == {"pass"}


def test_final_smoke_evidence_gate_drafts_from_live_monitor_json(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    monitor = {
        "context": {
            "observe": {
                "last_output_status": {
                    "event_id": "you_died",
                    "stage": "dispatcher_pushed",
                    "outcome": "pushed",
                    "reason": "selected",
                    "event_age_seconds": 1.25,
                    "event_expires_at": 9.25,
                    "coalesce_key": "neko_warthunder:battle_event",
                    "target_lanlan": "Lanlan",
                    "battle_reply_contract": "short_tts_line",
                    "live_reply_contract": "short_tts_line",
                    "max_reply_chars": 28,
                }
            }
        }
    }
    monitor_path = tmp_path / "live_monitor.json"
    monitor_path.write_text(json.dumps(monitor), encoding="utf-8")

    draft = final_smoke_evidence_gate.evidence_from_live_monitor(monitor_path)

    checks = {item["id"]: item for item in draft["runtime_focus_checks"]}
    assert checks["real_output_freshness"]["status"] == "pass"
    assert checks["real_output_freshness"]["observed"]["event_age_seconds"] == 1.25
    assert checks["real_output_freshness"]["observed"]["target_lanlan"] == "Lanlan"
    assert checks["short_tts_contract"]["status"] == "pending"
    assert checks["short_tts_contract"]["observed"]["live_reply_contract"] == "short_tts_line"
    assert checks["critical_replaces_stale_warning"]["status"] == "pending"
    assert checks["user_chat_quiet_window"]["status"] == "pending"


def test_final_smoke_evidence_gate_drafts_from_live_monitor_jsonl(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    first = {"context": {"observe": {"last_output_status": {"event_age_seconds": 9.0}}}}
    second = {
        "context": {
            "observe": {
                "last_output_status": {
                    "outcome": "pushed",
                    "reason": "selected",
                    "event_age_seconds": 2.0,
                    "coalesce_key": "neko_warthunder:battle_event",
                    "target_lanlan": "Lanlan",
                    "battle_reply_contract": "short_tts_line",
                    "live_reply_contract": "short_tts_line",
                    "max_reply_chars": 28,
                }
            }
        }
    }
    third = {
        "context": {
            "observe": {
                "last_output_status": {
                    "outcome": "dropped",
                    "reason": "event_expired",
                    "event_age_seconds": 10.0,
                    "coalesce_key": "neko_warthunder:battle_event",
                    "target_lanlan": "Lanlan",
                    "battle_reply_contract": "short_tts_line",
                    "live_reply_contract": "short_tts_line",
                    "max_reply_chars": 28,
                }
            }
        }
    }
    monitor_path = tmp_path / "live_monitor.jsonl"
    monitor_path.write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n" + json.dumps(third) + "\n",
        encoding="utf-8",
    )

    draft = final_smoke_evidence_gate.evidence_from_live_monitor(monitor_path)

    checks = {item["id"]: item for item in draft["runtime_focus_checks"]}
    assert checks["real_output_freshness"]["status"] == "pass"
    assert checks["real_output_freshness"]["observed"]["event_age_seconds"] == 2.0


def test_final_smoke_evidence_gate_cli_from_live_monitor(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    monitor_path = tmp_path / "live_monitor.json"
    monitor_path.write_text(
        json.dumps(
            {
                "context": {
                    "observe": {
                        "last_output_status": {
                            "outcome": "pushed",
                            "reason": "selected",
                            "event_age_seconds": 3.0,
                            "coalesce_key": "neko_warthunder:battle_event",
                            "target_lanlan": "Lanlan",
                            "battle_reply_contract": "short_tts_line",
                            "live_reply_contract": "short_tts_line",
                            "max_reply_chars": 28,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "local_test_logs" / "final_smoke_evidence.json"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = final_smoke_evidence_gate.main(
            ["--from-live-monitor", str(monitor_path), "--output", str(output_path)]
        )

    draft = json.loads(out.getvalue())
    written = json.loads(output_path.read_text(encoding="utf-8"))
    checks = {item["id"]: item for item in draft["runtime_focus_checks"]}
    assert rc == 0
    assert written == draft
    assert checks["real_output_freshness"]["status"] == "pass"


def test_final_smoke_evidence_gate_cli_combines_monitor_and_safe_transcript(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    monitor_path = tmp_path / "live_monitor_final.jsonl"
    monitor_path.write_text(
        json.dumps(
            {
                "context": {
                    "observe": {
                        "last_output_status": {
                            "outcome": "pushed",
                            "reason": "selected",
                            "event_age_seconds": 2.0,
                            "coalesce_key": "neko_warthunder:battle_event",
                            "target_lanlan": "Lanlan",
                            "battle_reply_contract": "short_tts_line",
                            "live_reply_contract": "short_tts_line",
                            "max_reply_chars": 28,
                        }
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "safe_transcript_metrics.json"
    transcript.write_text(
        json.dumps(
            {
                "raw_text_printed": False,
                "critical_sequence": {
                    "critical_replaced_stale_warning": True,
                    "old_warning_spoken_after_critical": False,
                },
                "user_chat_quiet_window": {
                    "ordinary_cue_spoken_during_user_turn": False,
                    "death_or_critical_allowed": True,
                },
                "battle_reply_observations": [
                    {
                        "source": "chat_window",
                        "line_count": 1,
                        "chars": 18,
                        "continued_across_chunks": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "final_smoke_evidence.json"
    out = io.StringIO()

    with contextlib.redirect_stdout(out):
        rc = final_smoke_evidence_gate.main(
            [
                "--from-live-monitor",
                str(monitor_path),
                "--safe-transcript",
                str(transcript),
                "--confirm-mode-domain-boundary",
                "--output",
                str(evidence),
            ]
        )

    written = json.loads(evidence.read_text(encoding="utf-8"))
    checks = {item["id"]: item for item in written["runtime_focus_checks"]}
    assert rc == 0
    assert json.loads(out.getvalue()) == written
    assert {key: item["status"] for key, item in checks.items()} == {
        "real_output_freshness": "pass",
        "critical_replaces_stale_warning": "pass",
        "user_chat_quiet_window": "pass",
        "short_tts_contract": "pass",
        "mode_domain_boundary": "pass",
    }
    assert written["safe_transcript_observations"]["short_single_line_contract_observed"] is True
    assert final_smoke_evidence_gate.run_gate(evidence)["status"] == "pass"


def test_final_smoke_evidence_gate_records_safe_transcript_metrics_from_flags(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    output_path = tmp_path / "safe_transcript_metrics.json"
    out = io.StringIO()

    with contextlib.redirect_stdout(out):
        rc = final_smoke_evidence_gate.main(
            [
                "--record-safe-transcript",
                "--reply-chars",
                "17",
                "--reply-lines",
                "1",
                "--reply-source",
                "tts",
                "--confirm-critical-replaced-stale-warning",
                "--confirm-user-chat-quiet-window",
                "--output",
                str(output_path),
            ]
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert json.loads(out.getvalue()) == payload
    assert payload == {
        "raw_text_printed": False,
        "critical_sequence": {
            "critical_replaced_stale_warning": True,
            "old_warning_spoken_after_critical": False,
        },
        "user_chat_quiet_window": {
            "ordinary_cue_spoken_during_user_turn": False,
            "death_or_critical_allowed": True,
        },
        "battle_reply_observations": [
            {
                "source": "tts",
                "line_count": 1,
                "chars": 17,
                "continued_across_chunks": False,
            }
        ],
    }


def test_final_smoke_evidence_gate_record_safe_transcript_requires_reply_chars():
    from neko_warthunder.tools import final_smoke_evidence_gate

    err = io.StringIO()
    with contextlib.redirect_stderr(err), pytest.raises(SystemExit) as exc:
        final_smoke_evidence_gate.main(["--record-safe-transcript"])

    assert exc.value.code == 2
    assert "--reply-chars" in err.getvalue()


def test_final_smoke_evidence_gate_update_applies_operator_confirmations(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    payload = _passing_evidence()
    payload["runtime_focus_checks"][1]["status"] = "pending"
    payload["runtime_focus_checks"][1]["observed"] = {
        "critical_replaced_stale_warning": False,
        "old_warning_spoken_after_critical": True,
    }
    payload["runtime_focus_checks"][2]["status"] = "pending"
    payload["runtime_focus_checks"][2]["observed"] = {
        "ordinary_cue_spoken_during_user_turn": True,
        "death_or_critical_allowed": False,
    }
    payload["runtime_focus_checks"][3]["status"] = "pending"
    payload["runtime_focus_checks"][3]["observed"]["continued_across_chunks"] = True
    evidence = tmp_path / "final_smoke_evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    out = io.StringIO()

    with contextlib.redirect_stdout(out):
        rc = final_smoke_evidence_gate.main(
            [
                str(evidence),
                "--update",
                "--confirm-critical-replaced-stale-warning",
                "--confirm-user-chat-quiet-window",
                "--confirm-short-tts-single-line",
                "--confirm-mode-domain-boundary",
            ]
        )

    updated = json.loads(evidence.read_text(encoding="utf-8"))
    checks = {item["id"]: item for item in updated["runtime_focus_checks"]}
    assert rc == 0
    assert json.loads(out.getvalue()) == updated
    assert checks["critical_replaces_stale_warning"]["status"] == "pass"
    assert checks["critical_replaces_stale_warning"]["observed"] == {
        "critical_replaced_stale_warning": True,
        "old_warning_spoken_after_critical": False,
    }
    assert checks["user_chat_quiet_window"]["status"] == "pass"
    assert checks["user_chat_quiet_window"]["observed"] == {
        "ordinary_cue_spoken_during_user_turn": False,
        "death_or_critical_allowed": True,
    }
    assert checks["short_tts_contract"]["status"] == "pass"
    assert checks["short_tts_contract"]["observed"]["continued_across_chunks"] is False
    assert checks["mode_domain_boundary"]["status"] == "pass"
    assert checks["mode_domain_boundary"]["observed"] == {
        "fixed_wing_cues_air_only": True,
        "ground_status_cues_ground_only": True,
        "ground_status_not_critical_risk": True,
    }
    assert final_smoke_evidence_gate.run_gate(evidence)["status"] == "pass"


def test_final_smoke_evidence_gate_merges_safe_transcript_metrics(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    payload = _passing_evidence()
    for index in [1, 2, 3, 4]:
        payload["runtime_focus_checks"][index]["status"] = "pending"
    payload["runtime_focus_checks"][1]["observed"] = {
        "critical_replaced_stale_warning": False,
        "old_warning_spoken_after_critical": True,
    }
    payload["runtime_focus_checks"][2]["observed"] = {
        "ordinary_cue_spoken_during_user_turn": True,
        "death_or_critical_allowed": False,
    }
    payload["runtime_focus_checks"][3]["observed"]["continued_across_chunks"] = True
    evidence = tmp_path / "final_smoke_evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    transcript = tmp_path / "safe_transcript_metrics.json"
    transcript.write_text(
        json.dumps(
            {
                "raw_text_printed": False,
                "critical_sequence": {
                    "critical_replaced_stale_warning": True,
                    "old_warning_spoken_after_critical": False,
                },
                "user_chat_quiet_window": {
                    "ordinary_cue_spoken_during_user_turn": False,
                    "death_or_critical_allowed": True,
                },
                "battle_reply_observations": [
                    {
                        "source": "chat_window",
                        "line_count": 1,
                        "chars": 11,
                        "continued_across_chunks": False,
                    },
                    {
                        "source": "tts",
                        "line_count": 1,
                        "chars": 16,
                        "continued_across_chunks": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    out = io.StringIO()

    with contextlib.redirect_stdout(out):
        rc = final_smoke_evidence_gate.main(
            [str(evidence), "--safe-transcript", str(transcript), "--confirm-mode-domain-boundary"]
        )

    updated = json.loads(evidence.read_text(encoding="utf-8"))
    checks = {item["id"]: item for item in updated["runtime_focus_checks"]}
    assert rc == 0
    assert json.loads(out.getvalue()) == updated
    assert checks["critical_replaces_stale_warning"]["status"] == "pass"
    assert checks["user_chat_quiet_window"]["status"] == "pass"
    assert checks["short_tts_contract"]["status"] == "pass"
    assert checks["mode_domain_boundary"]["status"] == "pass"
    assert updated["safe_transcript_observations"] == {
        "source": "safe_transcript_metrics",
        "samples": 2,
        "max_observed_reply_chars": 16,
        "max_observed_line_count": 1,
        "continued_across_chunks": False,
        "short_single_line_contract_observed": True,
    }
    assert final_smoke_evidence_gate.run_gate(evidence)["status"] == "pass"


def test_final_smoke_evidence_gate_rejects_raw_safe_transcript_metrics(tmp_path):
    from neko_warthunder.tools import final_smoke_evidence_gate

    evidence = tmp_path / "final_smoke_evidence.json"
    evidence.write_text(json.dumps(_passing_evidence()), encoding="utf-8")
    transcript = tmp_path / "unsafe_transcript_metrics.json"
    transcript.write_text(
        json.dumps(
            {
                "raw_text_printed": False,
                "raw_chat": "user original text must not be stored here",
                "battle_reply_observations": [],
            }
        ),
        encoding="utf-8",
    )
    out = io.StringIO()

    with contextlib.redirect_stderr(out), pytest.raises(SystemExit) as exc:
        final_smoke_evidence_gate.main([str(evidence), "--safe-transcript", str(transcript)])

    assert exc.value.code == 2
    assert "raw_text_field_must_be_empty" in out.getvalue()
