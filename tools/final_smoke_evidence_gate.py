"""Validate final live-smoke evidence after a real run.

This gate is intentionally offline and read-only. Operators can fill a small
JSON evidence file after the final live smoke; this tool checks that the P1
runtime focus items were observed without storing raw chat, HUD, combat feed,
award, proximity, or objective text.
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

from neko_warthunder.tools.final_smoke_packet import RUNTIME_FOCUS_CHECKS  # noqa: E402

_BATTLE_COALESCE_KEY = "neko_warthunder:battle_event"
_SHORT_TTS_CONTRACT = "short_tts_line"
_MAX_REPLY_CHARS = 28
_MAX_EVENT_AGE_SECONDS = 8.0

_RAW_TEXT_KEYS = {
    "raw",
    "raw_text",
    "raw_chat",
    "raw_hud",
    "raw_combat_feed",
    "raw_awards",
    "hudmsg",
    "combat_feed_text",
    "award_text",
    "player_name_raw",
}


def evidence_template() -> dict[str, Any]:
    """Return a safe skeleton operators can fill after final smoke."""
    return {
        "dry_run_first": True,
        "raw_text_printed": False,
        "runtime_focus_checks": [
            {
                "id": "real_output_freshness",
                "status": "pending",
                "observed": {
                    "event_age_seconds": None,
                    "coalesce_key": _BATTLE_COALESCE_KEY,
                    "target_lanlan": "",
                    "battle_reply_contract": _SHORT_TTS_CONTRACT,
                    "live_reply_contract": _SHORT_TTS_CONTRACT,
                    "max_reply_chars": _MAX_REPLY_CHARS,
                    "expired_event_pushed": False,
                },
            },
            {
                "id": "critical_replaces_stale_warning",
                "status": "pending",
                "observed": {
                    "critical_replaced_stale_warning": False,
                    "old_warning_spoken_after_critical": True,
                },
            },
            {
                "id": "user_chat_quiet_window",
                "status": "pending",
                "observed": {
                    "ordinary_cue_spoken_during_user_turn": True,
                    "death_or_critical_allowed": False,
                },
            },
            {
                "id": "short_tts_contract",
                "status": "pending",
                "observed": {
                    "battle_reply_contract": _SHORT_TTS_CONTRACT,
                    "live_reply_contract": _SHORT_TTS_CONTRACT,
                    "max_reply_chars": _MAX_REPLY_CHARS,
                    "continued_across_chunks": True,
                },
            },
            {
                "id": "mode_domain_boundary",
                "status": "pending",
                "observed": {
                    "fixed_wing_cues_air_only": False,
                    "ground_status_cues_ground_only": False,
                    "ground_status_not_critical_risk": False,
                },
            },
        ],
    }


def safe_transcript_template() -> dict[str, Any]:
    """Return a raw-text-free template for observing Lanlan's actual replies."""
    return {
        "raw_text_printed": False,
        "critical_sequence": {
            "critical_replaced_stale_warning": False,
            "old_warning_spoken_after_critical": True,
        },
        "user_chat_quiet_window": {
            "ordinary_cue_spoken_during_user_turn": True,
            "death_or_critical_allowed": False,
        },
        "battle_reply_observations": [
            {
                "source": "chat_window",
                "line_count": 1,
                "chars": 0,
                "continued_across_chunks": False,
            }
        ],
    }


def build_safe_transcript_metrics(
    *,
    reply_chars: int,
    reply_lines: int = 1,
    reply_source: str = "chat_window",
    continued_across_chunks: bool = False,
    critical_replaced_stale_warning: bool = False,
    user_chat_quiet_window: bool = False,
) -> dict[str, Any]:
    """Build raw-text-free final-smoke transcript metrics from operator facts."""
    return {
        "raw_text_printed": False,
        "critical_sequence": {
            "critical_replaced_stale_warning": bool(critical_replaced_stale_warning),
            "old_warning_spoken_after_critical": not bool(critical_replaced_stale_warning),
        },
        "user_chat_quiet_window": {
            "ordinary_cue_spoken_during_user_turn": not bool(user_chat_quiet_window),
            "death_or_critical_allowed": bool(user_chat_quiet_window),
        },
        "battle_reply_observations": [
            {
                "source": _safe_metric_source(reply_source),
                "line_count": max(0, int(reply_lines)),
                "chars": max(0, int(reply_chars)),
                "continued_across_chunks": bool(continued_across_chunks),
            }
        ],
    }


def run_rehearsal(output_dir: str | pathlib.Path) -> dict[str, Any]:
    """Exercise the final evidence workflow with synthetic safe data."""
    root = pathlib.Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    monitor_path = root / "live_monitor_final.rehearsal.jsonl"
    transcript_path = root / "safe_transcript_metrics.rehearsal.json"
    evidence_path = root / "final_smoke_evidence.rehearsal.json"
    result_path = root / "final_smoke_evidence_gate.rehearsal.json"

    monitor = {
        "context": {
            "observe": {
                "last_output_status": {
                    "outcome": "pushed",
                    "reason": "selected",
                    "event_age_seconds": 2.0,
                    "event_expires_at": 10.0,
                    "coalesce_key": _BATTLE_COALESCE_KEY,
                    "target_lanlan": "Lanlan",
                    "battle_reply_contract": _SHORT_TTS_CONTRACT,
                    "live_reply_contract": _SHORT_TTS_CONTRACT,
                    "max_reply_chars": _MAX_REPLY_CHARS,
                }
            }
        }
    }
    transcript = build_safe_transcript_metrics(
        reply_chars=17,
        reply_lines=1,
        reply_source="operator_observation",
        critical_replaced_stale_warning=True,
        user_chat_quiet_window=True,
    )
    monitor_path.write_text(json.dumps(monitor, ensure_ascii=False) + "\n", encoding="utf-8")
    transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = _apply_safe_transcript_payload(evidence_from_live_monitor(monitor_path), transcript)
    evidence = _apply_mode_domain_boundary_confirmation(evidence)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate = run_gate(evidence_path)
    result = {
        "status": gate["status"],
        "rehearsal_only": True,
        "starts_services": False,
        "raw_text_printed": False,
        "paths": {
            "monitor": str(monitor_path),
            "safe_transcript": str(transcript_path),
            "evidence": str(evidence_path),
            "gate_result": str(result_path),
        },
        "gate": gate,
        "note": "This proves the evidence workflow only; it is not final live-smoke evidence.",
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def evidence_from_live_monitor(path: str | pathlib.Path) -> dict[str, Any]:
    """Draft safe evidence from a live_monitor --json report.

    This intentionally does not auto-pass human-observed checks such as whether
    Lanlan interrupted user chat or continued across chunks.
    """
    reports = _load_json_reports(path)
    payload = evidence_template()
    output = _select_monitor_output(reports)
    freshness = _focus_by_id(payload, "real_output_freshness")
    short_tts = _focus_by_id(payload, "short_tts_contract")
    if freshness is not None:
        observed = freshness["observed"]
        observed["event_age_seconds"] = output.get("event_age_seconds")
        observed["coalesce_key"] = output.get("coalesce_key") or _BATTLE_COALESCE_KEY
        observed["target_lanlan"] = output.get("target_lanlan") or ""
        observed["battle_reply_contract"] = output.get("battle_reply_contract") or _SHORT_TTS_CONTRACT
        observed["live_reply_contract"] = output.get("live_reply_contract") or _SHORT_TTS_CONTRACT
        observed["max_reply_chars"] = output.get("max_reply_chars") or _MAX_REPLY_CHARS
        observed["expired_event_pushed"] = False
        if _output_has_fresh_real_push_metadata(output):
            freshness["status"] = "pass"
    if short_tts is not None:
        observed = short_tts["observed"]
        observed["battle_reply_contract"] = output.get("battle_reply_contract") or _SHORT_TTS_CONTRACT
        observed["live_reply_contract"] = output.get("live_reply_contract") or _SHORT_TTS_CONTRACT
        observed["max_reply_chars"] = output.get("max_reply_chars") or _MAX_REPLY_CHARS
    return payload


def apply_safe_transcript_observations(
    evidence_path: str | pathlib.Path,
    transcript_path: str | pathlib.Path,
) -> dict[str, Any]:
    payload = _load_evidence_payload(evidence_path)
    transcript = _load_safe_transcript_payload(transcript_path)
    return _apply_safe_transcript_payload(payload, transcript)


def _apply_safe_transcript_payload(payload: dict[str, Any], transcript: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)

    critical = _dict_value(transcript.get("critical_sequence"))
    if critical:
        item = _focus_by_id(payload, "critical_replaces_stale_warning")
        if (
            item is not None
            and critical.get("critical_replaced_stale_warning") is True
            and critical.get("old_warning_spoken_after_critical") is False
        ):
            observed = _dict_value(item.get("observed"))
            observed["critical_replaced_stale_warning"] = True
            observed["old_warning_spoken_after_critical"] = False
            item["observed"] = observed
            item["status"] = "pass"

    quiet = _dict_value(transcript.get("user_chat_quiet_window"))
    if quiet:
        item = _focus_by_id(payload, "user_chat_quiet_window")
        if (
            item is not None
            and quiet.get("ordinary_cue_spoken_during_user_turn") is False
            and quiet.get("death_or_critical_allowed") is True
        ):
            observed = _dict_value(item.get("observed"))
            observed["ordinary_cue_spoken_during_user_turn"] = False
            observed["death_or_critical_allowed"] = True
            item["observed"] = observed
            item["status"] = "pass"

    reply_observations = _list_value(transcript.get("battle_reply_observations"))
    reply_summary = _summarize_reply_observations(reply_observations)
    if reply_summary.get("samples", 0) > 0:
        payload["safe_transcript_observations"] = reply_summary
        item = _focus_by_id(payload, "short_tts_contract")
        if item is not None and reply_summary["short_single_line_contract_observed"] is True:
            observed = _dict_value(item.get("observed"))
            observed["battle_reply_contract"] = observed.get("battle_reply_contract") or _SHORT_TTS_CONTRACT
            observed["live_reply_contract"] = observed.get("live_reply_contract") or _SHORT_TTS_CONTRACT
            observed["max_reply_chars"] = observed.get("max_reply_chars") or _MAX_REPLY_CHARS
            observed["continued_across_chunks"] = False
            item["observed"] = observed
            item["status"] = "pass"

    return payload


def apply_operator_confirmations(
    path: str | pathlib.Path,
    *,
    critical_replaced_stale_warning: bool = False,
    user_chat_quiet_window: bool = False,
    short_tts_single_line: bool = False,
    mode_domain_boundary: bool = False,
) -> dict[str, Any]:
    payload = _load_evidence_payload(path)
    if critical_replaced_stale_warning:
        item = _focus_by_id(payload, "critical_replaces_stale_warning")
        if item is not None:
            observed = _dict_value(item.get("observed"))
            observed["critical_replaced_stale_warning"] = True
            observed["old_warning_spoken_after_critical"] = False
            item["observed"] = observed
            item["status"] = "pass"
    if user_chat_quiet_window:
        item = _focus_by_id(payload, "user_chat_quiet_window")
        if item is not None:
            observed = _dict_value(item.get("observed"))
            observed["ordinary_cue_spoken_during_user_turn"] = False
            observed["death_or_critical_allowed"] = True
            item["observed"] = observed
            item["status"] = "pass"
    if short_tts_single_line:
        item = _focus_by_id(payload, "short_tts_contract")
        if item is not None:
            observed = _dict_value(item.get("observed"))
            observed["battle_reply_contract"] = observed.get("battle_reply_contract") or _SHORT_TTS_CONTRACT
            observed["live_reply_contract"] = observed.get("live_reply_contract") or _SHORT_TTS_CONTRACT
            observed["max_reply_chars"] = observed.get("max_reply_chars") or _MAX_REPLY_CHARS
            observed["continued_across_chunks"] = False
            item["observed"] = observed
            item["status"] = "pass"
    if mode_domain_boundary:
        payload = _apply_mode_domain_boundary_confirmation(payload)
    return payload


def _apply_mode_domain_boundary_confirmation(payload: dict[str, Any]) -> dict[str, Any]:
    item = _focus_by_id(payload, "mode_domain_boundary")
    if item is not None:
        observed = _dict_value(item.get("observed"))
        observed["fixed_wing_cues_air_only"] = True
        observed["ground_status_cues_ground_only"] = True
        observed["ground_status_not_critical_risk"] = True
        item["observed"] = observed
        item["status"] = "pass"
    return payload


def run_gate(path: str | pathlib.Path) -> dict[str, Any]:
    evidence_path = pathlib.Path(path)
    failures: list[dict[str, str]] = []
    if not evidence_path.exists():
        return {
            "status": "fail",
            "evidence_path": str(evidence_path),
            "focus_checks": [],
            "failures": [
                {
                    "check": "evidence_file",
                    "target": str(evidence_path),
                    "reason": "missing",
                }
            ],
            "policy": _policy(),
        }

    try:
        payload = _load_evidence_payload(evidence_path)
    except json.JSONDecodeError as exc:
        return {
            "status": "fail",
            "evidence_path": str(evidence_path),
            "focus_checks": [],
            "failures": [{"check": "evidence_file", "target": "json", "reason": str(exc)}],
            "policy": _policy(),
        }

    if payload.get("dry_run_first") is not True:
        failures.append({"check": "safety", "target": "dry_run_first", "reason": "must_be_true"})
    if payload.get("raw_text_printed") is not False:
        failures.append({"check": "safety", "target": "raw_text_printed", "reason": "must_be_false"})
    _collect_raw_text_failures(payload, failures)

    checks = payload.get("runtime_focus_checks")
    if not isinstance(checks, list):
        checks = []
        failures.append({"check": "runtime_focus_checks", "target": "root", "reason": "missing_or_not_list"})
    by_id = {
        str(item.get("id")): item
        for item in checks
        if isinstance(item, dict) and item.get("id")
    }

    checked: list[dict[str, Any]] = []
    for required in RUNTIME_FOCUS_CHECKS:
        check_id = str(required["id"])
        item = by_id.get(check_id)
        if item is None:
            failures.append({"check": check_id, "target": "entry", "reason": "missing"})
            checked.append({"id": check_id, "status": "missing"})
            continue
        status = str(item.get("status") or "").lower()
        if status != "pass":
            failures.append({"check": check_id, "target": "status", "reason": f"expected_pass_actual_{status or 'empty'}"})
        observed = item.get("observed") if isinstance(item.get("observed"), dict) else {}
        _validate_focus_observation(check_id, observed, failures)
        checked.append({"id": check_id, "status": status or "empty"})

    return {
        "status": "pass" if not failures else "fail",
        "evidence_path": str(evidence_path),
        "focus_checks": checked,
        "failures": failures,
        "policy": _policy(),
    }


def _load_evidence_payload(path: str | pathlib.Path) -> dict[str, Any]:
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_safe_transcript_payload(path: str | pathlib.Path) -> dict[str, Any]:
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    payload = payload if isinstance(payload, dict) else {}
    failures: list[dict[str, str]] = []
    if payload.get("raw_text_printed") is not False:
        failures.append({"check": "privacy", "target": "$.raw_text_printed", "reason": "must_be_false"})
    _collect_raw_text_failures(payload, failures)
    if failures:
        details = ", ".join(f"{item['target']}:{item['reason']}" for item in failures)
        raise ValueError(f"unsafe safe transcript metrics: {details}")
    return payload


def _focus_by_id(payload: dict[str, Any], check_id: str) -> dict[str, Any] | None:
    checks = payload.get("runtime_focus_checks")
    if not isinstance(checks, list):
        return None
    for item in checks:
        if isinstance(item, dict) and item.get("id") == check_id:
            return item
    return None


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_metric_source(value: Any) -> str:
    text = str(value or "chat_window").strip().lower().replace("-", "_")
    return text if text in {"chat_window", "tts", "operator_observation"} else "operator_observation"


def _summarize_reply_observations(items: list[Any]) -> dict[str, Any]:
    observations = [_dict_value(item) for item in items if isinstance(item, dict)]
    chars = [item.get("chars") for item in observations if isinstance(item.get("chars"), int)]
    line_counts = [item.get("line_count") for item in observations if isinstance(item.get("line_count"), int)]
    continued = any(item.get("continued_across_chunks") is True for item in observations)
    samples = len(observations)
    max_chars = max(chars) if chars else None
    max_line_count = max(line_counts) if line_counts else None
    short_single_line = (
        samples > 0
        and max_chars is not None
        and max_line_count is not None
        and max_chars <= _MAX_REPLY_CHARS
        and max_line_count <= 1
        and continued is False
        and all(item.get("continued_across_chunks") is False for item in observations)
    )
    return {
        "source": "safe_transcript_metrics",
        "samples": samples,
        "max_observed_reply_chars": max_chars,
        "max_observed_line_count": max_line_count,
        "continued_across_chunks": continued,
        "short_single_line_contract_observed": short_single_line,
    }


def _load_json_reports(path: str | pathlib.Path) -> list[dict[str, Any]]:
    text = pathlib.Path(path).read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        reports: list[dict[str, Any]] = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                reports.append(item)
        return reports
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _select_monitor_output(reports: list[dict[str, Any]]) -> dict[str, Any]:
    outputs: list[dict[str, Any]] = []
    for report in reports:
        context = _dict_value(report.get("context"))
        observe = _dict_value(context.get("observe"))
        output = _dict_value(observe.get("last_output_status"))
        if output:
            outputs.append(output)
    for output in reversed(outputs):
        if _output_has_fresh_real_push_metadata(output):
            return output
    return outputs[-1] if outputs else {}


def _output_has_fresh_real_push_metadata(output: dict[str, Any]) -> bool:
    age = output.get("event_age_seconds")
    return (
        output.get("outcome") == "pushed"
        and output.get("reason") != "event_expired"
        and isinstance(age, (int, float))
        and 0 <= age <= _MAX_EVENT_AGE_SECONDS
        and output.get("coalesce_key") == _BATTLE_COALESCE_KEY
        and bool(str(output.get("target_lanlan") or "").strip())
        and output.get("battle_reply_contract") == _SHORT_TTS_CONTRACT
        and output.get("live_reply_contract") == _SHORT_TTS_CONTRACT
        and output.get("max_reply_chars") == _MAX_REPLY_CHARS
    )


def _validate_focus_observation(
    check_id: str,
    observed: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    if check_id == "real_output_freshness":
        _expect_equal(failures, check_id, "coalesce_key", observed.get("coalesce_key"), _BATTLE_COALESCE_KEY)
        _expect_equal(failures, check_id, "battle_reply_contract", observed.get("battle_reply_contract"), _SHORT_TTS_CONTRACT)
        _expect_equal(failures, check_id, "live_reply_contract", observed.get("live_reply_contract"), _SHORT_TTS_CONTRACT)
        _expect_equal(failures, check_id, "max_reply_chars", observed.get("max_reply_chars"), _MAX_REPLY_CHARS)
        _expect_equal(failures, check_id, "expired_event_pushed", observed.get("expired_event_pushed"), False)
        age = observed.get("event_age_seconds")
        if not isinstance(age, (int, float)) or age < 0 or age > _MAX_EVENT_AGE_SECONDS:
            failures.append({"check": check_id, "target": "event_age_seconds", "reason": "must_be_0_to_8_seconds"})
        if not str(observed.get("target_lanlan") or "").strip():
            failures.append({"check": check_id, "target": "target_lanlan", "reason": "missing"})
    elif check_id == "critical_replaces_stale_warning":
        _expect_equal(failures, check_id, "critical_replaced_stale_warning", observed.get("critical_replaced_stale_warning"), True)
        _expect_equal(failures, check_id, "old_warning_spoken_after_critical", observed.get("old_warning_spoken_after_critical"), False)
    elif check_id == "user_chat_quiet_window":
        _expect_equal(failures, check_id, "ordinary_cue_spoken_during_user_turn", observed.get("ordinary_cue_spoken_during_user_turn"), False)
        _expect_equal(failures, check_id, "death_or_critical_allowed", observed.get("death_or_critical_allowed"), True)
    elif check_id == "short_tts_contract":
        _expect_equal(failures, check_id, "battle_reply_contract", observed.get("battle_reply_contract"), _SHORT_TTS_CONTRACT)
        _expect_equal(failures, check_id, "live_reply_contract", observed.get("live_reply_contract"), _SHORT_TTS_CONTRACT)
        _expect_equal(failures, check_id, "max_reply_chars", observed.get("max_reply_chars"), _MAX_REPLY_CHARS)
        _expect_equal(failures, check_id, "continued_across_chunks", observed.get("continued_across_chunks"), False)
    elif check_id == "mode_domain_boundary":
        _expect_equal(failures, check_id, "fixed_wing_cues_air_only", observed.get("fixed_wing_cues_air_only"), True)
        _expect_equal(failures, check_id, "ground_status_cues_ground_only", observed.get("ground_status_cues_ground_only"), True)
        _expect_equal(failures, check_id, "ground_status_not_critical_risk", observed.get("ground_status_not_critical_risk"), True)


def _expect_equal(
    failures: list[dict[str, str]],
    check: str,
    target: str,
    actual: Any,
    expected: Any,
) -> None:
    if actual != expected:
        failures.append(
            {
                "check": check,
                "target": target,
                "reason": f"expected={expected!r} actual={actual!r}",
            }
        )


def _collect_raw_text_failures(value: Any, failures: list[dict[str, str]], *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.lower() in _RAW_TEXT_KEYS and item not in (None, "", [], {}):
                failures.append({"check": "privacy", "target": child_path, "reason": "raw_text_field_must_be_empty"})
            _collect_raw_text_failures(item, failures, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_raw_text_failures(item, failures, path=f"{path}[{index}]")


def _policy() -> dict[str, Any]:
    return {
        "requires_all_runtime_focus_checks_pass": True,
        "dry_run_first_required": True,
        "raw_text_printed_must_be_false": True,
        "raw_chat_hud_combat_award_text_forbidden": True,
        "starts_services": False,
        "reads_raw_chat_or_telemetry": False,
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder final smoke evidence gate",
        f"status: {result['status']}",
        f"evidence_path: {result['evidence_path']}",
        "policy: offline evidence check; no service startup; raw chat/HUD/combat/award text forbidden",
        "",
        "focus_checks:",
    ]
    for item in result.get("focus_checks") or []:
        lines.append(f"- {item.get('id')}: {item.get('status')}")
    if result.get("failures"):
        lines.append("")
        lines.append("failures:")
        for failure in result["failures"]:
            lines.append(f"- {failure['check']} {failure['target']} {failure['reason']}")
    return "\n".join(lines) + "\n"


def _write_output(path: str | pathlib.Path, text: str) -> None:
    output_path = pathlib.Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate final live-smoke evidence.")
    parser.add_argument("evidence", nargs="?", help="Path to final smoke evidence JSON.")
    parser.add_argument("--template", action="store_true", help="Print a safe evidence JSON template.")
    parser.add_argument(
        "--rehearsal-output-dir",
        help="Write synthetic rehearsal artifacts that exercise the evidence workflow without live claims.",
    )
    parser.add_argument(
        "--safe-transcript-template",
        action="store_true",
        help="Print a raw-text-free template for observing Lanlan's spoken/chat replies.",
    )
    parser.add_argument(
        "--record-safe-transcript",
        action="store_true",
        help="Create raw-text-free transcript metrics from numeric/operator observations.",
    )
    parser.add_argument("--reply-chars", type=int, help="Observed character count for one battle reply.")
    parser.add_argument("--reply-lines", type=int, default=1, help="Observed line count for one battle reply.")
    parser.add_argument(
        "--reply-source",
        default="chat_window",
        choices=["chat_window", "tts", "operator_observation"],
        help="Where the reply metrics were observed; no raw reply text is stored.",
    )
    parser.add_argument(
        "--continued-across-chunks",
        action="store_true",
        help="Record that the battle reply continued across chunks.",
    )
    parser.add_argument("--from-live-monitor", help="Print a draft evidence JSON from live_monitor --json output.")
    parser.add_argument(
        "--safe-transcript",
        help="Merge raw-text-free transcript metrics into an evidence JSON.",
    )
    parser.add_argument("--update", action="store_true", help="Apply explicit operator confirmations to an evidence JSON.")
    parser.add_argument(
        "--confirm-critical-replaced-stale-warning",
        action="store_true",
        help="Operator confirms a death/critical cue replaced an older stale warning.",
    )
    parser.add_argument(
        "--confirm-user-chat-quiet-window",
        action="store_true",
        help="Operator confirms ordinary battle cues stayed quiet during user chat while death/critical passed.",
    )
    parser.add_argument(
        "--confirm-short-tts-single-line",
        action="store_true",
        help="Operator confirms spoken battle output was one short line and did not continue across chunks.",
    )
    parser.add_argument(
        "--confirm-mode-domain-boundary",
        action="store_true",
        help="Operator confirms air-only and ground-only mode/domain boundaries held during final smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result.")
    parser.add_argument("--output", help="Optional file path to save the rendered output.")
    args = parser.parse_args(argv)

    if args.template:
        text = json.dumps(evidence_template(), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_output(args.output, text)
        print(text, end="")
        return 0
    if args.rehearsal_output_dir:
        result = run_rehearsal(args.rehearsal_output_dir)
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_output(args.output, text)
        print(text, end="")
        return 0 if result["status"] == "pass" else 1
    if args.safe_transcript_template:
        text = json.dumps(safe_transcript_template(), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_output(args.output, text)
        print(text, end="")
        return 0
    if args.record_safe_transcript:
        if args.reply_chars is None:
            parser.error("--record-safe-transcript requires --reply-chars")
        payload = build_safe_transcript_metrics(
            reply_chars=args.reply_chars,
            reply_lines=args.reply_lines,
            reply_source=args.reply_source,
            continued_across_chunks=args.continued_across_chunks,
            critical_replaced_stale_warning=args.confirm_critical_replaced_stale_warning,
            user_chat_quiet_window=args.confirm_user_chat_quiet_window,
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_output(args.output, text)
        print(text, end="")
        return 0
    if args.from_live_monitor:
        payload = evidence_from_live_monitor(args.from_live_monitor)
        if args.safe_transcript:
            try:
                payload = _apply_safe_transcript_payload(
                    payload,
                    _load_safe_transcript_payload(args.safe_transcript),
                )
            except ValueError as exc:
                parser.error(str(exc))
        if args.confirm_mode_domain_boundary:
            payload = _apply_mode_domain_boundary_confirmation(payload)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_output(args.output, text)
        print(text, end="")
        return 0
    if args.safe_transcript:
        if not args.evidence:
            parser.error("evidence path is required with --safe-transcript")
        try:
            payload = apply_safe_transcript_observations(args.evidence, args.safe_transcript)
        except ValueError as exc:
            parser.error(str(exc))
        if args.confirm_mode_domain_boundary:
            payload = _apply_mode_domain_boundary_confirmation(payload)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        _write_output(args.output or args.evidence, text)
        print(text, end="")
        return 0
    if args.update:
        if not args.evidence:
            parser.error("evidence path is required with --update")
        if not (
            args.confirm_critical_replaced_stale_warning
            or args.confirm_user_chat_quiet_window
            or args.confirm_short_tts_single_line
            or args.confirm_mode_domain_boundary
        ):
            parser.error("--update requires at least one --confirm-* flag")
        payload = apply_operator_confirmations(
            args.evidence,
            critical_replaced_stale_warning=args.confirm_critical_replaced_stale_warning,
            user_chat_quiet_window=args.confirm_user_chat_quiet_window,
            short_tts_single_line=args.confirm_short_tts_single_line,
            mode_domain_boundary=args.confirm_mode_domain_boundary,
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        _write_output(args.output or args.evidence, text)
        print(text, end="")
        return 0
    if not args.evidence:
        parser.error("evidence path is required unless --template or --from-live-monitor is used")

    result = run_gate(args.evidence)
    if args.json:
        text = json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
    else:
        text = render_text(result)
    if args.output:
        _write_output(args.output, text)
    print(text, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
