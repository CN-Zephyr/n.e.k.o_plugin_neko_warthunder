"""Offline gate for real battle-output freshness contracts.

This gate is synthetic and host-free. It proves that real battle-event
``push_message`` calls carry plugin-owned delivery and dialogue policy:
queue coalescing, event age/expiry, target session, and the plugin-side short
TTS prompt contract. Critical cues use host-generated speech by default so they
reach TTS; plugin-owned blind output remains an explicit compatibility option.
The gate also proves expired events are dropped before real push and dry_run
decisions remain side-effect-free.
"""

from __future__ import annotations

import pathlib as _pathlib
import sys as _sys

_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from typing import Any, Callable

from _common import run_gate_cli
from neko_warthunder.adapters.neko_dispatcher import (
    BATTLE_EVENT_COALESCE_KEY,
    BATTLE_REPLY_CONTRACT,
    BATTLE_REPLY_MAX_CHARS,
    BATTLE_RESPONSE_MODULE_HINT,
    HOST_CALLBACK_CONTRACT_VERSION,
    HOST_QUIET_WINDOW_POLICY,
    NekoDispatcher,
)
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.core.contracts import CRITICAL_EVENT_IDS, BattleEvent, WtConfig


class _CapturePlugin:
    def __init__(self) -> None:
        self.cfg = WtConfig(
            dry_run=False,
            output_backpressure_seconds=20.0,
            output_event_max_age_seconds=8.0,
            user_chat_quiet_window_seconds=0.0,
            battle_output_quiet_window_seconds=0.0,
            target_lanlan="Lanlan",
        )
        self.calls: list[dict[str, Any]] = []

    def push_message(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _clock(values: list[float]) -> Callable[[], float]:
    def tick() -> float:
        return values.pop(0)

    return tick


def run_gate() -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    cases = [
        _case_real_push_contract(failures),
        _case_expired_event_drops_before_push(failures),
        _case_backpressure_suppresses_lower_priority(failures),
        _case_higher_priority_preempts_backpressure(failures),
        _case_death_bypasses_equal_priority_backpressure(failures),
        _case_critical_safety_bypasses_backpressure(failures),
        _case_dry_run_side_effect_free(failures),
        _case_context_target_session(failures),
    ]
    return {
        "status": "pass" if not failures else "fail",
        "cases": cases,
        "failures": failures,
        "policy": {
            "real_battle_push_requires_coalesce_key": True,
            "real_battle_push_requires_freshness_metadata": True,
            "tactical_cues_use_shorter_freshness_windows": True,
            "real_battle_push_requires_target_lanlan_when_resolved": True,
            "real_battle_push_requires_plugin_dialogue_policy": True,
            "real_battle_push_requires_pending_replace_metadata": True,
            "real_battle_push_requires_reply_style_contract": True,
            "real_battle_push_requires_generic_delivery_contract": True,
            "urgent_battle_events_require_interrupt_metadata": True,
            "death_event_bypasses_backpressure": True,
            "critical_safety_event_bypasses_backpressure": True,
            "expired_events_must_not_push": True,
            "dry_run_must_not_push": True,
        },
    }


def _case_real_push_contract(failures: list[dict[str, str]]) -> dict[str, Any]:
    plugin = _CapturePlugin()
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="critical", ts=97.0), dry_run=False)
    if not result.startswith("pushed("):
        failures.append({"case": "real_push_contract", "target": "dispatcher", "reason": "not_pushed"})
    if len(plugin.calls) != 1:
        failures.append({"case": "real_push_contract", "target": "push_message", "reason": "wrong_call_count"})
        return {"name": "real_push_contract", "pushed": False}

    call = plugin.calls[0]
    metadata = call.get("metadata") or {}
    status = timeline.snapshot().get("last_output_status") or {}
    _expect_equal(failures, "real_push_contract", "call.coalesce_key", call.get("coalesce_key"), BATTLE_EVENT_COALESCE_KEY)
    _expect_equal(failures, "real_push_contract", "call.target_lanlan", call.get("target_lanlan"), "Lanlan")
    _expect_equal(failures, "real_push_contract", "call.ai_behavior", call.get("ai_behavior"), "respond")
    _expect_equal(failures, "real_push_contract", "call.visibility", call.get("visibility"), [])
    _expect_required_metadata(failures, "real_push_contract", metadata)
    _expect_required_status_metadata(failures, "real_push_contract.status", status)
    _expect_equal(failures, "real_push_contract", "metadata.event_age_seconds", metadata.get("event_age_seconds"), 3.0)
    _expect_equal(failures, "real_push_contract", "metadata.event_expires_at", metadata.get("event_expires_at"), 101.0)
    _expect_equal(failures, "real_push_contract", "metadata.target_lanlan", metadata.get("target_lanlan"), "Lanlan")
    _expect_equal(failures, "real_push_contract", "metadata.interrupt_battle_event", metadata.get("interrupt_battle_event"), True)
    _expect_equal(failures, "real_push_contract", "metadata.interrupt_pending", metadata.get("interrupt_pending"), True)
    _expect_equal(failures, "real_push_contract", "status.interrupt_battle_event", status.get("interrupt_battle_event"), True)
    _expect_equal(failures, "real_push_contract", "status.interrupt_pending", status.get("interrupt_pending"), True)
    _expect_host_callback_contract(failures, "real_push_contract", metadata)
    return {
        "name": "real_push_contract",
        "pushed": True,
        "event_age_seconds": metadata.get("event_age_seconds"),
        "event_expires_at": metadata.get("event_expires_at"),
        "target_lanlan": metadata.get("target_lanlan"),
        "reply_contract": metadata.get("battle_reply_contract"),
        "ai_behavior": call.get("ai_behavior"),
        "visibility": call.get("visibility"),
        "dialogue_policy_owner": metadata.get("dialogue_policy_owner"),
        "plugin_owned_output": metadata.get("plugin_owned_output"),
        "plugin_recommended_reply": metadata.get("plugin_recommended_reply"),
        "replace_pending": metadata.get("replace_pending"),
        "interrupt_battle_event": metadata.get("interrupt_battle_event"),
        "interrupt_pending": metadata.get("interrupt_pending"),
        "reply_style_contract": metadata.get("reply_style_contract"),
        "host_callback_contract_version": metadata.get("host_callback_contract_version"),
    }


def _case_expired_event_drops_before_push(failures: list[dict[str, str]]) -> dict[str, Any]:
    plugin = _CapturePlugin()
    plugin.cfg.output_event_max_age_seconds = 5.0
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0]))

    result = dispatcher.push_event(BattleEvent("low_alt_danger", level="warning", ts=90.0), dry_run=False)
    status = timeline.snapshot().get("last_output_status") or {}
    _expect_equal(failures, "expired_event_drop", "result", result, "suppressed(event=low_alt_danger/enter, reason=event_expired)")
    _expect_equal(failures, "expired_event_drop", "push_calls", len(plugin.calls), 0)
    _expect_equal(failures, "expired_event_drop", "status.reason", status.get("reason"), "event_expired")
    _expect_equal(failures, "expired_event_drop", "status.event_age_seconds", status.get("event_age_seconds"), 10.0)
    return {
        "name": "expired_event_drop",
        "pushed": bool(plugin.calls),
        "reason": status.get("reason"),
        "event_age_seconds": status.get("event_age_seconds"),
    }


def _case_backpressure_suppresses_lower_priority(failures: list[dict[str, str]]) -> dict[str, Any]:
    plugin = _CapturePlugin()
    timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    dispatcher = NekoDispatcher(plugin, timeline=timeline, clock=_clock([100.0, 105.0]))

    first = dispatcher.push_event(BattleEvent("you_killed", ts=99.0), dry_run=False)
    second = dispatcher.push_event(BattleEvent("spawn", ts=104.0), dry_run=False)
    status = timeline.snapshot().get("last_output_status") or {}
    if not first.startswith("pushed("):
        failures.append({"case": "backpressure_lower_priority", "target": "first", "reason": "not_pushed"})
    _expect_equal(failures, "backpressure_lower_priority", "second", second, "suppressed(event=spawn/enter, reason=output_backpressure)")
    _expect_equal(failures, "backpressure_lower_priority", "push_calls", len(plugin.calls), 1)
    _expect_equal(failures, "backpressure_lower_priority", "status.reason", status.get("reason"), "output_backpressure")
    return {
        "name": "backpressure_lower_priority",
        "push_calls": len(plugin.calls),
        "reason": status.get("reason"),
    }


def _case_higher_priority_preempts_backpressure(failures: list[dict[str, str]]) -> dict[str, Any]:
    plugin = _CapturePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    dispatcher.push_event(BattleEvent("spawn", ts=99.0), dry_run=False)
    result = dispatcher.push_event(BattleEvent("you_died", level="critical", ts=104.0), dry_run=False)
    _expect_equal(failures, "higher_priority_preempts", "push_calls", len(plugin.calls), 2)
    if not result.startswith("pushed("):
        failures.append({"case": "higher_priority_preempts", "target": "second", "reason": "not_pushed"})
    for index, call in enumerate(plugin.calls):
        _expect_equal(
            failures,
            "higher_priority_preempts",
            f"call{index}.coalesce_key",
            call.get("coalesce_key"),
            BATTLE_EVENT_COALESCE_KEY,
        )
    last_metadata = plugin.calls[-1].get("metadata") or {} if plugin.calls else {}
    _expect_equal(failures, "higher_priority_preempts", "last.replace_pending", last_metadata.get("replace_pending"), True)
    _expect_equal(
        failures,
        "higher_priority_preempts",
        "last.interrupt_battle_event",
        last_metadata.get("interrupt_battle_event"),
        True,
    )
    _expect_equal(failures, "higher_priority_preempts", "last.interrupt_pending", last_metadata.get("interrupt_pending"), True)
    return {
        "name": "higher_priority_preempts",
        "push_calls": len(plugin.calls),
        "last_event": last_metadata.get("event_id"),
        "replace_pending": last_metadata.get("replace_pending"),
        "interrupt_battle_event": last_metadata.get("interrupt_battle_event"),
        "interrupt_pending": last_metadata.get("interrupt_pending"),
    }


def _case_death_bypasses_equal_priority_backpressure(failures: list[dict[str, str]]) -> dict[str, Any]:
    plugin = _CapturePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    first = dispatcher.push_event(BattleEvent("you_died", level="critical", ts=99.0), dry_run=False)
    second = dispatcher.push_event(BattleEvent("you_died", level="critical", ts=104.0), dry_run=False)
    if not first.startswith("pushed("):
        failures.append({"case": "death_bypasses_backpressure", "target": "first", "reason": "not_pushed"})
    if not second.startswith("pushed("):
        failures.append({"case": "death_bypasses_backpressure", "target": "second", "reason": "not_pushed"})
    _expect_equal(failures, "death_bypasses_backpressure", "push_calls", len(plugin.calls), 2)
    last_metadata = plugin.calls[-1].get("metadata") or {} if plugin.calls else {}
    _expect_equal(failures, "death_bypasses_backpressure", "last.replace_pending", last_metadata.get("replace_pending"), True)
    _expect_equal(
        failures,
        "death_bypasses_backpressure",
        "last.interrupt_battle_event",
        last_metadata.get("interrupt_battle_event"),
        True,
    )
    _expect_equal(failures, "death_bypasses_backpressure", "last.interrupt_pending", last_metadata.get("interrupt_pending"), True)
    return {
        "name": "death_bypasses_backpressure",
        "push_calls": len(plugin.calls),
        "last_event": last_metadata.get("event_id"),
        "replace_pending": last_metadata.get("replace_pending"),
        "interrupt_battle_event": last_metadata.get("interrupt_battle_event"),
        "interrupt_pending": last_metadata.get("interrupt_pending"),
    }


def _case_critical_safety_bypasses_backpressure(failures: list[dict[str, str]]) -> dict[str, Any]:
    checked: list[str] = []
    for event_id in sorted(CRITICAL_EVENT_IDS):
        plugin = _CapturePlugin()
        dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

        first = dispatcher.push_event(BattleEvent("you_died", level="critical", ts=99.0), dry_run=False)
        second = dispatcher.push_event(BattleEvent(event_id, level="critical", ts=104.0), dry_run=False)
        if not first.startswith("pushed("):
            failures.append({"case": "critical_safety_bypasses_backpressure", "target": f"{event_id}.first", "reason": "not_pushed"})
        if not second.startswith("pushed("):
            failures.append({"case": "critical_safety_bypasses_backpressure", "target": f"{event_id}.second", "reason": "not_pushed"})
        _expect_equal(failures, "critical_safety_bypasses_backpressure", f"{event_id}.push_calls", len(plugin.calls), 2)
        last_metadata = plugin.calls[-1].get("metadata") or {} if plugin.calls else {}
        _expect_equal(failures, "critical_safety_bypasses_backpressure", f"{event_id}.event_id", last_metadata.get("event_id"), event_id)
        _expect_equal(
            failures,
            "critical_safety_bypasses_backpressure",
            f"{event_id}.interrupt_battle_event",
            last_metadata.get("interrupt_battle_event"),
            True,
        )
        _expect_equal(
            failures,
            "critical_safety_bypasses_backpressure",
            f"{event_id}.interrupt_pending",
            last_metadata.get("interrupt_pending"),
            True,
        )
        checked.append(event_id)
    return {
        "name": "critical_safety_bypasses_backpressure",
        "checked_events": checked,
        "interrupt_battle_event": True,
        "interrupt_pending": True,
    }


def _case_dry_run_side_effect_free(failures: list[dict[str, str]]) -> dict[str, Any]:
    plugin = _CapturePlugin()
    dispatcher = NekoDispatcher(plugin, clock=_clock([100.0, 105.0]))

    first = dispatcher.push_event(BattleEvent("you_killed", ts=99.0), dry_run=True)
    second = dispatcher.push_event(BattleEvent("spawn", ts=104.0), dry_run=True)
    if not first.startswith("dry_run(") or not second.startswith("dry_run("):
        failures.append({"case": "dry_run_side_effect_free", "target": "result", "reason": "not_dry_run"})
    _expect_equal(failures, "dry_run_side_effect_free", "push_calls", len(plugin.calls), 0)
    return {
        "name": "dry_run_side_effect_free",
        "push_calls": len(plugin.calls),
        "results": [first.split("(", 1)[0], second.split("(", 1)[0]],
    }


def _case_context_target_session(failures: list[dict[str, str]]) -> dict[str, Any]:
    plugin = _CapturePlugin()
    dispatcher = NekoDispatcher(plugin)

    dispatcher.push_context("safe context")
    _expect_equal(failures, "context_target_session", "push_calls", len(plugin.calls), 1)
    if not plugin.calls:
        return {"name": "context_target_session", "pushed": False}
    call = plugin.calls[0]
    metadata = call.get("metadata") or {}
    _expect_equal(failures, "context_target_session", "target_lanlan", call.get("target_lanlan"), "Lanlan")
    _expect_equal(failures, "context_target_session", "metadata.target_lanlan", metadata.get("target_lanlan"), "Lanlan")
    return {
        "name": "context_target_session",
        "pushed": True,
        "target_lanlan": metadata.get("target_lanlan"),
    }


def _expect_required_metadata(failures: list[dict[str, str]], case: str, metadata: dict[str, Any]) -> None:
    expected = {
        "plugin": "neko_warthunder",
        "coalesce_key": BATTLE_EVENT_COALESCE_KEY,
        "battle_reply_contract": BATTLE_REPLY_CONTRACT,
        "live_reply_contract": BATTLE_REPLY_CONTRACT,
        "max_reply_chars": BATTLE_REPLY_MAX_CHARS,
        "response_module_hint": BATTLE_RESPONSE_MODULE_HINT,
        "replace_pending": True,
        "reply_contract": BATTLE_REPLY_CONTRACT,
        "reply_max_chars": BATTLE_REPLY_MAX_CHARS,
        "dialogue_policy_owner": "plugin",
        "plugin_owned_output": False,
        "plugin_quiet_window_policy": HOST_QUIET_WINDOW_POLICY,
        "host_callback_contract_version": HOST_CALLBACK_CONTRACT_VERSION,
    }
    for key, value in expected.items():
        _expect_equal(failures, case, f"metadata.{key}", metadata.get(key), value)
    policy = metadata.get("plugin_dialogue_policy")
    if not isinstance(policy, dict):
        failures.append({"case": case, "target": "metadata.plugin_dialogue_policy", "reason": "missing"})
    else:
        _expect_equal(failures, case, "plugin_dialogue_policy.owner", policy.get("owner"), "plugin")
        _expect_equal(failures, case, "plugin_dialogue_policy.mode", policy.get("mode"), BATTLE_REPLY_CONTRACT)
        _expect_equal(failures, case, "plugin_dialogue_policy.max_chars", policy.get("max_chars"), BATTLE_REPLY_MAX_CHARS)
        _expect_equal(failures, case, "plugin_dialogue_policy.single_line", policy.get("single_line"), True)
        _expect_equal(failures, case, "plugin_dialogue_policy.no_followup", policy.get("no_followup"), True)
    for key in (
        "event_ts",
        "event_age_seconds",
        "event_max_age_seconds",
        "event_expires_at",
        "reply_style_contract",
        "plugin_recommended_reply",
    ):
        if key not in metadata:
            failures.append({"case": case, "target": f"metadata.{key}", "reason": "missing"})


def _expect_required_status_metadata(failures: list[dict[str, str]], case: str, status: dict[str, Any]) -> None:
    expected = {
        "coalesce_key": BATTLE_EVENT_COALESCE_KEY,
        "battle_reply_contract": BATTLE_REPLY_CONTRACT,
        "live_reply_contract": BATTLE_REPLY_CONTRACT,
        "max_reply_chars": BATTLE_REPLY_MAX_CHARS,
        "response_module_hint": BATTLE_RESPONSE_MODULE_HINT,
        "replace_pending": True,
        "reply_contract": BATTLE_REPLY_CONTRACT,
        "reply_max_chars": BATTLE_REPLY_MAX_CHARS,
        "dialogue_policy_owner": "plugin",
        "plugin_owned_output": False,
        "plugin_quiet_window_policy": HOST_QUIET_WINDOW_POLICY,
        "host_callback_contract_version": HOST_CALLBACK_CONTRACT_VERSION,
    }
    for key, value in expected.items():
        _expect_equal(failures, case, key, status.get(key), value)
    policy = status.get("plugin_dialogue_policy")
    if not isinstance(policy, dict):
        failures.append({"case": case, "target": "plugin_dialogue_policy", "reason": "missing"})
    else:
        _expect_equal(failures, case, "plugin_dialogue_policy.owner", policy.get("owner"), "plugin")
        _expect_equal(failures, case, "plugin_dialogue_policy.mode", policy.get("mode"), BATTLE_REPLY_CONTRACT)
    for key in (
        "event_ts",
        "event_age_seconds",
        "event_max_age_seconds",
        "event_expires_at",
        "reply_style_contract",
        "plugin_recommended_reply",
    ):
        if key not in status:
            failures.append({"case": case, "target": key, "reason": "missing"})


def _expect_host_callback_contract(failures: list[dict[str, str]], case: str, metadata: dict[str, Any]) -> None:
    contract = metadata.get("host_callback_contract")
    if not isinstance(contract, dict):
        failures.append({"case": case, "target": "metadata.host_callback_contract", "reason": "missing"})
        return
    _expect_equal(failures, case, "host_callback_contract.version", contract.get("version"), HOST_CALLBACK_CONTRACT_VERSION)
    _expect_equal(failures, case, "host_callback_contract.kind", contract.get("kind"), "realtime_cue")
    delivery = contract.get("delivery") if isinstance(contract.get("delivery"), dict) else {}
    freshness = contract.get("freshness") if isinstance(contract.get("freshness"), dict) else {}
    _expect_equal(failures, case, "host_callback_contract.delivery.coalesce_key", delivery.get("coalesce_key"), BATTLE_EVENT_COALESCE_KEY)
    _expect_equal(failures, case, "host_callback_contract.delivery.replace_pending", delivery.get("replace_pending"), True)
    _expect_equal(failures, case, "host_callback_contract.delivery.interrupt_pending", delivery.get("interrupt_pending"), True)
    if "reply" in contract:
        failures.append({"case": case, "target": "host_callback_contract.reply", "reason": "must_be_plugin_owned"})
    if "quiet_window" in contract:
        failures.append({"case": case, "target": "host_callback_contract.quiet_window", "reason": "must_be_plugin_owned"})
    _expect_equal(failures, case, "host_callback_contract.freshness.event_age_seconds", freshness.get("event_age_seconds"), 3.0)


def _expect_equal(
    failures: list[dict[str, str]],
    case: str,
    target: str,
    actual: Any,
    expected: Any,
) -> None:
    if actual != expected:
        failures.append(
            {
                "case": case,
                "target": target,
                "reason": f"expected={expected!r} actual={actual!r}",
            }
        )


def render_text(result: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder output freshness gate",
        f"status: {result['status']}",
        "policy: real battle output must be fresh, coalesced, targeted, and plugin-dialogue constrained",
    ]
    for case in result["cases"]:
        details = " ".join(f"{k}={v}" for k, v in case.items() if k != "name")
        lines.append(f"- {case['name']}: {details}".rstrip())
    if result["failures"]:
        lines.append("failures:")
        for failure in result["failures"]:
            lines.append(f"- {failure['case']} {failure['target']} {failure['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    return run_gate_cli(
        description="Check real battle-output freshness contracts.",
        run_gate=run_gate,
        render_text=render_text,
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
