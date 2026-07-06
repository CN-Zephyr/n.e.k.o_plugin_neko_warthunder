"""Safe one-shot/live runtime monitor for neko_warthunder validation."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import types
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

_BASE = pathlib.Path(__file__).resolve().parent.parent
if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg

ENDPOINTS = {
    "host": "http://127.0.0.1:48911/health",
    "hosted_ui": "http://127.0.0.1:48916/health",
    "data_layer": "http://127.0.0.1:8112/health",
    "context": "http://127.0.0.1:48916/plugin/neko_warthunder/hosted-ui/context?kind=panel&id=main",
    "telemetry": "http://127.0.0.1:8112/api/telemetry",
}

DEFAULT_LOG_FILES = [
    "neko_backend_stdout.log",
    "neko_backend_stderr.log",
    "warthunder_data_layer_8112_stdout.log",
    "warthunder_data_layer_8112_stderr.log",
]

Fetcher = Callable[[str], Any]
LogReader = Callable[[list[pathlib.Path]], list[str]]


def fetch_json(url: str, *, timeout: float = 1.5) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        data = json.loads(body) if body else {}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": exc.__class__.__name__}
    return data if isinstance(data, dict) else {"ok": True, "value_type": type(data).__name__}


def read_recent_log_lines(paths: list[pathlib.Path], *, max_lines: int = 200) -> list[str]:
    lines: list[str] = []
    for path in paths:
        try:
            if not path.exists():
                continue
            lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])
        except OSError:
            continue
    return lines[-max_lines:]


def monitor_once(
    *,
    fetcher: Fetcher | None = None,
    log_reader: LogReader | None = None,
    root: str | pathlib.Path | None = None,
) -> dict[str, Any]:
    fetch = fetcher or fetch_json
    log_root = pathlib.Path(root).resolve() if root is not None else _BASE.parent
    log_paths = [log_root / name for name in DEFAULT_LOG_FILES]
    read_logs = log_reader or read_recent_log_lines

    health = {
        "host": _health(fetch(ENDPOINTS["host"])),
        "hosted_ui": _health(fetch(ENDPOINTS["hosted_ui"])),
        "data_layer": _health(fetch(ENDPOINTS["data_layer"])),
    }
    context_raw = _dict(fetch(ENDPOINTS["context"]))
    telemetry_raw = _dict(fetch(ENDPOINTS["telemetry"]))
    logs = _summarize_logs(read_logs(log_paths))
    context = _summarize_context(context_raw)
    telemetry = _summarize_telemetry(telemetry_raw)
    telemetry["replay_degrade"] = _summarize_replay_degrade(telemetry, context)

    report = {
        "health": health,
        "context": context,
        "telemetry": telemetry,
        "logs": logs,
    }
    report["verdict"] = _build_verdict(report)
    return report


def render_text_report(report: dict[str, Any]) -> str:
    health = report.get("health") if isinstance(report.get("health"), dict) else {}
    context = report.get("context") if isinstance(report.get("context"), dict) else {}
    telemetry = report.get("telemetry") if isinstance(report.get("telemetry"), dict) else {}
    logs = report.get("logs") if isinstance(report.get("logs"), dict) else {}
    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else {}
    observe = context.get("observe") if isinstance(context.get("observe"), dict) else {}
    decision = observe.get("last_decision") if isinstance(observe.get("last_decision"), dict) else {}
    output = observe.get("last_output_status") if isinstance(observe.get("last_output_status"), dict) else {}
    combat = telemetry.get("combat") if isinstance(telemetry.get("combat"), dict) else {}
    free_text = telemetry.get("free_text_safety") if isinstance(telemetry.get("free_text_safety"), dict) else {}
    replay_degrade = telemetry.get("replay_degrade") if isinstance(telemetry.get("replay_degrade"), dict) else {}

    health_line = ", ".join(
        [
            f"Host: {_ok_text(health.get('host'))}",
            f"Hosted UI: {_ok_text(health.get('hosted_ui'))}",
            f"Data layer: {_ok_text(health.get('data_layer'))}",
        ]
    )
    flags = telemetry.get("flags") if isinstance(telemetry.get("flags"), list) else []
    flag_text = ", ".join(str(flag) for flag in flags) if flags else "-"
    free_text_detail = _format_free_text_detail(free_text.get("source_details"))
    lines = [
        "# neko_warthunder live monitor",
        _format_summary_line(health, context, telemetry, logs),
        f"Health: {health_line}",
        "Runtime: dry_run={dry_run}, connected={connected}, game_context_active={game_context_active}, in_battle={in_battle}, scenario={scenario}, safety={safety}".format(
            dry_run=context.get("dry_run"),
            connected=context.get("connected"),
            game_context_active=context.get("game_context_active"),
            in_battle=context.get("in_battle"),
            scenario=context.get("scenario") or "-",
            safety=_safe_get(context.get("safety"), "status"),
        ),
        "Telemetry: replay={replay}, domain={domain}, level={level}, flags={flags}, ownership kill={kill} death={death}".format(
            replay=telemetry.get("replay"),
            domain=telemetry.get("domain") or "-",
            level=telemetry.get("level") or "-",
            flags=flag_text,
            kill=combat.get("is_my_kill_true", 0),
            death=combat.get("is_my_death_true", 0),
        ),
        "FreeText: free_text={status}({sources}), raw_text_fields={raw_fields}, prompt_allowed={prompt_allowed}".format(
            status=free_text.get("status") or "clear",
            sources=", ".join(free_text.get("observed_sources") or []) or "-",
            raw_fields=free_text.get("raw_text_fields_present", False),
            prompt_allowed=free_text.get("prompt_allowed", False),
        ),
        f"FreeText detail: {free_text_detail}",
        "Replay: replay={status}({stage}/{reason}), output_blocked={output_blocked}, prompt_allowed={prompt_allowed}".format(
            status=replay_degrade.get("status") or "clear",
            stage=replay_degrade.get("decision_stage") or "-",
            reason=replay_degrade.get("decision_reason") or "-",
            output_blocked=replay_degrade.get("output_blocked", False),
            prompt_allowed=replay_degrade.get("prompt_allowed", True),
        ),
        "Observe: event={event}, decision={stage}/{outcome}/{reason}, output={out_stage}/{outcome2}/{reason2}".format(
            event=_safe_get(observe.get("last_event"), "event_id") or "-",
            stage=decision.get("stage") or "-",
            outcome=decision.get("outcome") or "-",
            reason=decision.get("reason") or "-",
            out_stage=output.get("stage") or "-",
            outcome2=output.get("outcome") or "-",
            reason2=output.get("reason") or "-",
        ),
        f"Decision detail: {_format_reason_detail(decision.get('reason'), kind='decision')}",
        f"Output detail: {_format_reason_detail(output.get('reason'), kind='output')}",
        "Logs: action_failed={action_failed}, traceback={traceback}, error={error}, dry_run={dry_run}, pushed={pushed}, tts={tts}".format(
            action_failed=logs.get("PLUGIN_UI_ACTION_FAILED", 0),
            traceback=logs.get("Traceback", 0),
            error=logs.get("ERROR", 0),
            dry_run=logs.get("dry_run", 0),
            pushed=logs.get("pushed", 0),
            tts=logs.get("TTS/tts", 0),
        ),
        str(verdict.get("message") or "状态可继续观察"),
    ]
    return "\n".join(lines) + "\n"


def _health(data: Any) -> dict[str, Any]:
    value = _dict(data)
    if "ok" in value:
        return {"ok": bool(value.get("ok")), "error": value.get("error")}
    if value.get("status") in {"ok", "healthy", "ready"}:
        return {"ok": True}
    if value:
        return {"ok": True}
    return {"ok": False, "error": "empty_response"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _summarize_context(data: dict[str, Any]) -> dict[str, Any]:
    state = data.get("state") if isinstance(data.get("state"), dict) else data
    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    observe = state.get("observe") if isinstance(state.get("observe"), dict) else {}
    return {
        "dry_run": state.get("dry_run"),
        "connected": state.get("connected"),
        "conn_state": state.get("conn_state"),
        "game_context_active": state.get("game_context_active"),
        "in_battle": state.get("in_battle"),
        "domain": state.get("domain"),
        "scenario": state.get("scenario"),
        "level": state.get("level"),
        "safety": {
            "status": safety.get("status"),
            "manual_paused": safety.get("manual_paused"),
            "auto_paused": safety.get("auto_paused"),
            "failures": safety.get("failures"),
        },
        "observe": {
            "last_event": _safe_fields(observe.get("last_event"), ["event_id", "edge", "level"]),
            "last_decision": _safe_fields(
                observe.get("last_decision"),
                ["ts", "event_id", "stage", "outcome", "reason", "scenario", "safety_status", "dry_run"],
            ),
            "last_output_status": _safe_fields(
                observe.get("last_output_status"),
                [
                    "ts",
                    "event_id",
                    "stage",
                    "outcome",
                    "reason",
                    "dry_run",
                    "elapsed_ms",
                    "event_age_seconds",
                    "event_expires_at",
                    "coalesce_key",
                    "target_lanlan",
                    "battle_reply_contract",
                    "live_reply_contract",
                    "max_reply_chars",
                ],
            ),
        },
    }


def _summarize_telemetry(data: dict[str, Any]) -> dict[str, Any]:
    vehicle = data.get("vehicle") if isinstance(data.get("vehicle"), dict) else {}
    processed = data.get("processed") if isinstance(data.get("processed"), dict) else {}
    flags = processed.get("flags") if isinstance(processed.get("flags"), dict) else {}
    combat = data.get("combat") if isinstance(data.get("combat"), dict) else {}
    feed = combat.get("feed") if isinstance(combat.get("feed"), list) else []
    hud = data.get("hud_notices") if isinstance(data.get("hud_notices"), dict) else {}
    awards = data.get("awards") if isinstance(data.get("awards"), dict) else {}
    hud_feed = hud.get("feed") if isinstance(hud.get("feed"), list) else []
    award_feed = awards.get("feed") if isinstance(awards.get("feed"), list) else []
    return {
        "state": data.get("state"),
        "replay": data.get("replay"),
        "in_battle": data.get("in_battle"),
        "domain": data.get("domain"),
        "mission_present": isinstance(data.get("mission"), dict) and bool(data.get("mission")),
        "vehicle": {
            "valid": vehicle.get("valid"),
            "altitude_m": vehicle.get("altitude_m"),
            "ias_kmh": vehicle.get("ias_kmh"),
        },
        "level": processed.get("level"),
        "flags": sorted(str(key) for key, value in flags.items() if value),
        "combat": {
            "feed_items": len(feed),
            "is_my_kill_true": _count_true(feed, "is_my_kill"),
            "is_my_death_true": _count_true(feed, "is_my_death"),
            "involves_me_true": _count_true(feed, "involves_me"),
        },
        "hud_notices": {
            "items": len(hud_feed),
            "codes": sorted(
                {
                    str(item.get("code"))
                    for item in hud_feed
                    if isinstance(item, dict) and item.get("code") is not None
                }
            ),
        },
        "awards": {"items": len(award_feed)},
        "free_text_safety": _summarize_free_text_safety(feed, hud_feed, award_feed),
    }


def _summarize_free_text_safety(
    combat_feed: list[Any],
    hud_feed: list[Any],
    award_feed: list[Any],
) -> dict[str, Any]:
    source_items = {
        "awards": award_feed,
        "combat_feed": combat_feed,
        "hud_notices": hud_feed,
    }
    sources = sorted(source for source, items in source_items.items() if items)
    sources = sorted(sources)
    source_details = {
        source: _free_text_source_detail(items)
        for source, items in source_items.items()
        if items
    }
    raw_text_fields = any(detail["raw_text_fields_present"] for detail in source_details.values())
    blocked_reasons = [
        f"{source}_raw_text"
        for source, detail in source_details.items()
        if detail["raw_text_fields_present"]
    ]
    if not sources:
        return {
            "status": "clear",
            "observed_sources": [],
            "raw_text_fields_present": False,
            "prompt_allowed": True,
            "source_details": {},
            "blocked_reasons": [],
        }
    return {
        "status": "dry_run_only",
        "observed_sources": sources,
        "raw_text_fields_present": raw_text_fields,
        "prompt_allowed": False,
        "source_details": source_details,
        "blocked_reasons": blocked_reasons,
    }


def _free_text_source_detail(items: list[Any]) -> dict[str, Any]:
    return {
        "items": len(items),
        "raw_text_fields_present": _has_raw_text_fields(items),
        "prompt_allowed": False,
        "mode": "dry_run_only",
    }


def _format_free_text_detail(value: Any) -> str:
    details = value if isinstance(value, dict) else {}
    if not details:
        return "-"
    parts: list[str] = []
    for source in sorted(details):
        detail = details.get(source) if isinstance(details.get(source), dict) else {}
        status = "blocked" if detail.get("prompt_allowed") is False else "allowed"
        parts.append(f"{source}={detail.get('items', 0)}/{status}")
    return ", ".join(parts)


def _summarize_replay_degrade(telemetry: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    observe = context.get("observe") if isinstance(context.get("observe"), dict) else {}
    decision = observe.get("last_decision") if isinstance(observe.get("last_decision"), dict) else {}
    output = observe.get("last_output_status") if isinstance(observe.get("last_output_status"), dict) else {}
    telemetry_replay = telemetry.get("replay") is True
    decision_stage = decision.get("stage")
    decision_outcome = decision.get("outcome")
    decision_reason = decision.get("reason")
    output_blocked = not bool(output)
    if not telemetry_replay:
        return {
            "status": "clear",
            "telemetry_replay": bool(telemetry.get("replay")),
            "decision_stage": decision_stage,
            "decision_reason": decision_reason,
            "output_blocked": True,
            "prompt_allowed": True,
        }
    suppressed = (
        decision_stage == "detector_suppressed"
        and decision_outcome == "suppressed"
        and decision_reason == "replay"
        and output_blocked
    )
    return {
        "status": "suppressed" if suppressed else "needs_attention",
        "telemetry_replay": True,
        "decision_stage": decision_stage,
        "decision_reason": decision_reason,
        "output_blocked": output_blocked,
        "prompt_allowed": False,
    }


def _summarize_logs(lines: list[str]) -> dict[str, int]:
    counters = {
        "PLUGIN_UI_ACTION_FAILED": 0,
        "Traceback": 0,
        "ERROR": 0,
        "[output]": 0,
        "[arbiter]": 0,
        "TRIGGER": 0,
        "TTS/tts": 0,
        "dry_run": 0,
        "pushed": 0,
    }
    for line in lines:
        lower = line.lower()
        if "plugin_ui_action_failed" in lower:
            counters["PLUGIN_UI_ACTION_FAILED"] += 1
        if "traceback" in lower:
            counters["Traceback"] += 1
        if "error" in lower:
            counters["ERROR"] += 1
        if "[output]" in lower:
            counters["[output]"] += 1
        if "[arbiter]" in lower:
            counters["[arbiter]"] += 1
        if "trigger" in lower:
            counters["TRIGGER"] += 1
        if "tts" in lower:
            counters["TTS/tts"] += 1
        if "dry_run" in lower and "plugin_ui_action_failed" not in lower:
            counters["dry_run"] += 1
        if "pushed" in lower or "push_message" in lower:
            counters["pushed"] += 1
    return counters


def _format_summary_line(
    health: dict[str, Any],
    context: dict[str, Any],
    telemetry: dict[str, Any],
    logs: dict[str, int],
) -> str:
    free_text = telemetry.get("free_text_safety") if isinstance(telemetry.get("free_text_safety"), dict) else {}
    replay = telemetry.get("replay_degrade") if isinstance(telemetry.get("replay_degrade"), dict) else {}
    observe = context.get("observe") if isinstance(context.get("observe"), dict) else {}
    output = observe.get("last_output_status") if isinstance(observe.get("last_output_status"), dict) else {}
    health_state = "ok" if all(_dict(value).get("ok") for value in health.values()) else "fail"
    battle_state = "in_battle" if context.get("in_battle") is True else "not_in_battle"
    scenario = context.get("scenario") or "-"
    output_blocked = replay.get("status") == "suppressed" and replay.get("output_blocked") is True
    output_text = "blocked" if not output and output_blocked else _format_output_summary(output)
    return (
        "Summary: health={health}, battle={battle}/{scenario}, free_text={free_text}, "
        "replay={replay}, output={output}, issues={issues}"
    ).format(
        health=health_state,
        battle=battle_state,
        scenario=scenario,
        free_text=free_text.get("status") or "clear",
        replay=replay.get("status") or "clear",
        output=output_text,
        issues=_format_issue_summary(logs),
    )


def _format_output_summary(output: dict[str, Any]) -> str:
    if not output:
        return "-"
    text = f"{output.get('stage') or '-'}/{output.get('outcome') or '-'}"
    reason = output.get("reason")
    if reason in {"event_expired", "output_backpressure", "repeated_event_collapsed"}:
        text += f"({reason})"
    meta = _format_output_freshness_meta(output)
    if meta:
        text += f"[{meta}]"
    return text


def _format_output_freshness_meta(output: dict[str, Any]) -> str:
    parts: list[str] = []
    age = output.get("event_age_seconds")
    if isinstance(age, (int, float)):
        parts.append(f"age={age:g}s")
    target = str(output.get("target_lanlan") or "").strip()
    if target:
        parts.append(f"target={target}")
    contract = str(output.get("live_reply_contract") or output.get("battle_reply_contract") or "").strip()
    max_chars = output.get("max_reply_chars")
    if contract:
        text = contract
        if isinstance(max_chars, int):
            text += f"/{max_chars}"
        parts.append(f"tts={text}")
    ai_behavior = str(output.get("ai_behavior") or "").strip()
    plugin_owned = output.get("plugin_owned_output")
    if ai_behavior:
        mode = ai_behavior
        if plugin_owned is True:
            mode += "+plugin"
        parts.append(f"mode={mode}")
    return ",".join(parts)


def _format_reason_detail(reason: Any, *, kind: str) -> str:
    if not reason:
        return "-"
    text = str(reason)
    explanations = {
        "selected": "Arbiter 已放行此事件",
        "kill_coalesced": "多次击杀已合并",
        "dry_run_enabled": "dry_run 开启，仅模拟不真实开口",
        "event_expired": "旧战场事件已过期，真实开口前丢弃",
        "output_backpressure": "输出背压中，同级或低优先级提示被压住",
        "repeated_event_collapsed": "短时间重复战场提示已折叠",
        "manual_pause": "手动暂停中，输出被压住",
        "scenario_gated": "当前场景不允许播这个事件",
        "cooldown": "冷却中，避免重复播报",
        "rate_limit": "全局限流中，输出被延后或压住",
        "replay": "回放数据已静默",
        "deferred_hud_notice": "HUD 技术通知已识别，当前策略暂不播报",
        "free_text_blocked": "free-text source observed; prompt/output remains blocked by T-Safety",
    }
    fallback = "已记录决策" if kind == "decision" else "已记录输出状态"
    return f"{text}={explanations.get(text, fallback)}"


def _format_issue_summary(logs: dict[str, int]) -> str:
    names = [
        ("action_failed", "PLUGIN_UI_ACTION_FAILED"),
        ("traceback", "Traceback"),
        ("error", "ERROR"),
        ("tts", "TTS/tts"),
    ]
    issues = [name for name, key in names if logs.get(key, 0) > 0]
    return "+".join(issues) if issues else "none"


def _build_verdict(report: dict[str, Any]) -> dict[str, Any]:
    health = report.get("health") if isinstance(report.get("health"), dict) else {}
    logs = report.get("logs") if isinstance(report.get("logs"), dict) else {}
    health_bad = any(not _dict(value).get("ok") for value in health.values())
    has_runtime_error = any(
        logs.get(key, 0) > 0 for key in ["PLUGIN_UI_ACTION_FAILED", "Traceback", "ERROR", "TTS/tts"]
    )
    if health_bad or has_runtime_error:
        return {
            "needs_attention": True,
            "message": "需要处理：存在 action failed / Traceback / ERROR / TTS 异常",
        }
    return {"needs_attention": False, "message": "状态正常：可继续真机观察"}


def _safe_fields(value: Any, keys: list[str]) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    return {key: data.get(key) for key in keys if key in data}


def _safe_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _count_true(items: list[Any], key: str) -> int:
    return sum(1 for item in items if isinstance(item, dict) and item.get(key) is True)


def _has_raw_text_fields(items: list[Any]) -> bool:
    raw_keys = {
        "text",
        "raw",
        "raw_text",
        "message",
        "hudmsg",
        "hud_text",
        "notice_text",
        "feed_text",
        "feed_raw",
        "award_text",
        "award_name",
        "award_title",
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        if any(key in item and item.get(key) not in {None, ""} for key in raw_keys):
            return True
    return False


def _ok_text(value: Any) -> str:
    return "ok" if isinstance(value, dict) and value.get("ok") else "fail"


def _write_output(path: str | pathlib.Path, chunks: list[str]) -> None:
    output_path = pathlib.Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(chunks), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a safe neko_warthunder live monitor summary.")
    parser.add_argument("--json", action="store_true", help="Print safe JSON instead of the text summary.")
    parser.add_argument("--root", default=str(_BASE.parent), help="Directory containing runtime log files.")
    parser.add_argument("--count", type=int, default=1, help="Number of samples to print.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between samples when --count > 1.")
    parser.add_argument("--output", help="Optional file path to save the safe monitor output.")
    args = parser.parse_args(argv)

    count = max(1, args.count)
    chunks: list[str] = []
    for index in range(count):
        report = monitor_once(root=args.root)
        if args.json:
            chunk = json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n"
        else:
            chunk = render_text_report(report)
        chunks.append(chunk)
        print(chunk, end="")
        if index + 1 < count:
            time.sleep(max(0.1, args.interval))
    if args.output:
        _write_output(args.output, chunks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
