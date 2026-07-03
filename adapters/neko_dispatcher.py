"""唯一 NEKO 输出边界（D-B4）。

所有开口只走这里：把 BattleEvent 拼成"事实行 + 要求行"prompt（带 {MASTER_NAME} 占位符，
宿主按会话展开），经 push_message(visibility=[], ai_behavior="respond") 交给猫娘 LLM 润色。
dry_run 时短路、绝不真投。常驻场景上下文走 push_context(ai_behavior="read")。
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from ..core.contracts import BattleEvent
from .runtime_timeline import RuntimeTimeline
from .text_safety import sanitize_event_payload

BATTLE_EVENT_COALESCE_KEY = "neko_warthunder:battle_event"
BATTLE_REPLY_CONTRACT = "short_tts_line"
BATTLE_REPLY_MAX_CHARS = 28
BATTLE_RESPONSE_MODULE_HINT = "war_thunder_battle_event"
HOST_CALLBACK_CONTRACT_VERSION = "neko.callback.v1"
HOST_CALLBACK_KIND = "realtime_cue"
HOST_REPLY_STYLE = "short_line"
HOST_QUIET_WINDOW_POLICY = "suppress_non_urgent_during_user_input"
V2_LIVE_EVIDENCE_GATED_EVENTS = frozenset({"enemy_on_six", "tailing_risk", "ground_target_nearby"})
FREE_TEXT_DRY_RUN_ONLY_EVENTS = frozenset({"free_text_activity"})
BACKPRESSURE_BYPASS_EVENTS = frozenset({"you_died"})
URGENT_REPLACE_EVENTS = frozenset({"you_died", "stall_risk", "low_alt_danger", "overspeed"})
EVENT_MAX_AGE_OVERRIDES_SECONDS: dict[str, float] = {
    # These cues are useful only while the condition is still tactically fresh.
    "spawn": 3.0,
    "enemy_nearby": 3.0,
    "air_threat_nearby": 3.0,
    "enemy_on_six": 3.0,
    "tailing_risk": 3.0,
    "ground_target_nearby": 4.0,
    "low_alt_danger": 4.0,
    "overspeed": 4.0,
    "stall_risk": 5.0,
    "overheat": 6.0,
    # Kill/death/battle-end can tolerate a little more host latency, but still
    # should not be replayed as old news.
    "you_killed": 6.0,
    "you_died": 8.0,
    "battle_end": 8.0,
}
COPILOT_ROLE_BOUNDARY = (
    "边界：后座/WSO，只报事实和动作建议；不接管、不编锁定/开火/击杀/损伤/威胁。"
)

# 每个事件的"要求行"意图（不写最终台词，台词归角色 LLM）。
_INTENT: dict[str, str] = {
    "stall_risk": "濒临失速，提醒 {MASTER_NAME} 加速/松杆改出",
    "low_alt_danger": "离地太近还在下沉，提醒 {MASTER_NAME} 立刻拉起",
    "overspeed": "速度过头，提醒 {MASTER_NAME} 收油门改出，别硬拉",
    "overheat": "发动机温度高，提醒 {MASTER_NAME} 收油门散热",
    "low_fuel": "油不多了，提醒 {MASTER_NAME} 留油返航",
    "ground_target_nearby": "报任务目标点接近，提醒 {MASTER_NAME} 看方位",
    "enemy_nearby": "报附近接触，提醒 {MASTER_NAME} 保持观察",
    "air_threat_nearby": "报空中威胁方位，提醒 {MASTER_NAME} 抬头确认",
    "enemy_on_six": "报后方威胁，提醒 {MASTER_NAME} 别让对面贴住",
    "tailing_risk": "报后方持续贴近，提醒 {MASTER_NAME} 立刻改出",
    "free_text_activity": "提醒 {MASTER_NAME} 检测到战场文字来源，只做安全泛化提示，不复读原文",
    "you_killed": "确认刚才击杀，给 {MASTER_NAME} 一句短夸",
    "you_died": "按事实安抚 {MASTER_NAME}，准备重整",
    "spawn": (
        "上机就位，跟 {MASTER_NAME} 打声短招呼；只说上机/就位/跟上，"
        "不要报敌情、方位、雷达目标、锁定、击杀或威胁"
    ),
    "battle_end": "这局结束，给 {MASTER_NAME} 收尾一句，不展开战报",
}

_RECOVERY_INTENT = "刚才的危险解除了，跟 {MASTER_NAME} 说句'好险、稳住了'之类的"


def _output_backpressure_seconds(plugin: Any) -> float:
    cfg = getattr(plugin, "cfg", None)
    try:
        return max(0.0, float(getattr(cfg, "output_backpressure_seconds", 20.0)))
    except (TypeError, ValueError):
        return 20.0


def _output_event_max_age_seconds(plugin: Any, event: BattleEvent | None = None) -> float:
    cfg = getattr(plugin, "cfg", None)
    try:
        configured = max(0.0, float(getattr(cfg, "output_event_max_age_seconds", 8.0)))
    except (TypeError, ValueError):
        configured = 8.0
    if event is None or configured <= 0:
        return configured
    override = EVENT_MAX_AGE_OVERRIDES_SECONDS.get(event.event_id)
    if override is None:
        return configured
    return min(configured, override)


def _v2_live_verified_real_output_enabled(plugin: Any) -> bool:
    cfg = getattr(plugin, "cfg", None)
    return bool(getattr(cfg, "v2_live_verified_real_output_enabled", False))


def _clean_target_lanlan(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()[:80]


def _resolve_target_lanlan(plugin: Any, event: BattleEvent | None = None) -> str:
    payload = event.payload if event and isinstance(event.payload, dict) else {}
    for candidate in (
        payload.get("target_lanlan"),
        payload.get("lanlan_name"),
    ):
        target = _clean_target_lanlan(candidate)
        if target:
            return target

    ctx_obj = payload.get("_ctx")
    if isinstance(ctx_obj, dict):
        target = _clean_target_lanlan(ctx_obj.get("lanlan_name"))
        if target:
            return target

    cfg = getattr(plugin, "cfg", None)
    for candidate in (
        getattr(cfg, "target_lanlan", ""),
        getattr(cfg, "lanlan_name", ""),
    ):
        target = _clean_target_lanlan(candidate)
        if target:
            return target

    plugin_ctx = getattr(plugin, "ctx", None)
    target = _clean_target_lanlan(getattr(plugin_ctx, "_current_lanlan", None))
    if target:
        return target

    for env_name in ("NEKO_WARTHUNDER_TARGET_LANLAN", "NEKO_TARGET_LANLAN", "NEKO_LANLAN_NAME", "NEKO_HER_NAME"):
        target = _clean_target_lanlan(os.getenv(env_name, ""))
        if target:
            return target

    try:
        from utils.config_manager import get_config_manager

        character_data = get_config_manager().get_character_data()
        if isinstance(character_data, tuple) and len(character_data) >= 2:
            target = _clean_target_lanlan(character_data[1])
            if target:
                return target
    except Exception:
        pass

    return ""


def _event_freshness_metadata(event: BattleEvent, now: float, plugin: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    max_age = _output_event_max_age_seconds(plugin, event)
    if event.ts > 0:
        out["event_ts"] = round(float(event.ts), 3)
        if now >= event.ts:
            out["event_age_seconds"] = round(float(now - event.ts), 3)
        if max_age > 0:
            out["event_max_age_seconds"] = round(float(max_age), 3)
            out["event_expires_at"] = round(float(event.ts + max_age), 3)
    elif max_age > 0:
        out["event_max_age_seconds"] = round(float(max_age), 3)
    return out


def _reply_style_contract(event: BattleEvent) -> str:
    if event.event_id == "you_killed":
        if event.payload.get("trade_death"):
            return (
                "Style: one short Chinese line; vehicle was lost, but praise the trade kill as not wasted; no analysis."
            )
        kill_count = 1
        try:
            kill_count = int(event.payload.get("kill_count") or 1)
        except (TypeError, ValueError):
            kill_count = 1
        if kill_count > 1:
            return "Style: one short Chinese line; acknowledge multi-kill once; no repeated praise."
        return "Style: one short Chinese line; confirm kill once; no hype."
    if event.event_id == "you_died":
        return "Style: one short Chinese line; calm reset; no analysis."
    if event.event_id in URGENT_REPLACE_EVENTS or event.level == "critical":
        return "Style: one short Chinese line; urgent command; no filler."
    if event.event_id in {"air_threat_nearby", "enemy_nearby", "enemy_on_six", "tailing_risk"}:
        return "Style: one short Chinese line; situational cue; no takeover."
    if event.event_id == "ground_target_nearby":
        return "Style: one short Chinese line; target/nav cue only; no takeover."
    if event.event_id == "overheat":
        return "Style: one short Chinese line; situational cue; no repeated wording."
    return "Style: one short Chinese line; concise copilot cue."


def _copilot_role_boundary(event: BattleEvent) -> str:
    if event.event_id in {
        "enemy_nearby",
        "air_threat_nearby",
        "enemy_on_six",
        "tailing_risk",
        "ground_target_nearby",
    }:
        return (
            COPILOT_ROLE_BOUNDARY
            + " 目标/威胁只报观测到的方位距离；禁句：交给我/我来/已锁定/开火。"
        )
    return COPILOT_ROLE_BOUNDARY


def _prompt_style_hint(event: BattleEvent) -> str:
    if event.event_id == "you_killed":
        if event.payload.get("trade_death"):
            return "风格：一句中文短句；载具没了也要肯定换掉一个，不展开分析。"
        kill_count = 1
        try:
            kill_count = int(event.payload.get("kill_count") or 1)
        except (TypeError, ValueError):
            kill_count = 1
        if kill_count > 1:
            return "风格：一句中文短句；只夸一次连杀，别连续刷屏。"
        return "风格：一句中文短句；确认击杀，克制一点。"
    if event.event_id == "you_died":
        return "风格：一句中文短句；安抚并重整，不复盘。"
    if event.event_id in URGENT_REPLACE_EVENTS or event.level == "critical":
        return "风格：一句中文短句；急促指令，不闲聊。"
    if event.event_id in {"air_threat_nearby", "enemy_nearby", "enemy_on_six", "tailing_risk"}:
        return "风格：一句中文短句；只报态势，不接管武器。"
    if event.event_id == "ground_target_nearby":
        return "风格：一句中文短句；只做目标/航向提示。"
    if event.event_id == "overheat":
        return "风格：一句中文短句；直接提醒处置。"
    return "风格：一句中文短句；干净利落。"


def _host_interrupt_pending(event: BattleEvent) -> bool:
    return event.event_id in URGENT_REPLACE_EVENTS


def _host_callback_contract(
    event: BattleEvent,
    *,
    freshness: dict[str, float],
    target_lanlan: str,
) -> dict[str, Any]:
    delivery = {
        "coalesce_key": BATTLE_EVENT_COALESCE_KEY,
        "replace_pending": True,
        "interrupt_pending": _host_interrupt_pending(event),
        "priority": event.priority,
    }
    if freshness.get("event_expires_at") is not None:
        delivery["expires_at"] = freshness["event_expires_at"]
    if freshness.get("event_max_age_seconds") is not None:
        delivery["max_age_seconds"] = freshness["event_max_age_seconds"]

    contract: dict[str, Any] = {
        "version": HOST_CALLBACK_CONTRACT_VERSION,
        "kind": HOST_CALLBACK_KIND,
        "delivery": delivery,
        "reply": {
            "mode": BATTLE_REPLY_CONTRACT,
            "style": HOST_REPLY_STYLE,
            "max_chars": BATTLE_REPLY_MAX_CHARS,
            "single_turn": True,
            "drop_followup_chunks": True,
            "style_hint": _reply_style_contract(event),
        },
        "quiet_window": {
            "policy": HOST_QUIET_WINDOW_POLICY,
            "bypass": _host_interrupt_pending(event) or event.level == "critical",
        },
        "freshness": {
            key: freshness[key]
            for key in ("event_ts", "event_age_seconds", "event_max_age_seconds", "event_expires_at")
            if freshness.get(key) is not None
        },
    }
    if target_lanlan:
        contract["target"] = {"lanlan": target_lanlan}
    return contract


def _fact_line(event: BattleEvent) -> str:
    p, _ = sanitize_event_payload(event.event_id, event.payload)
    bits: list[str] = []
    kill_fact = _kill_fact(event.event_id, p)
    death_fact = _death_fact(event.event_id, p)
    proximity_fact = _proximity_fact(event.event_id, p)
    objective_fact = _objective_fact(event.event_id, p)
    free_text_fact = _free_text_fact(event.event_id, p)
    has_radio_altitude = p.get("radio_altitude_m") is not None
    order = [
        ("ias_kmh", "IAS {:.0f}km/h"),
        ("aoa_deg", "迎角 {:.0f}°"),
        ("altitude_m", "高度 {:.0f}m"),
        ("climb_ms", "垂速 {:+.0f}m/s"),
        ("mach", "M {:.2f}"),
        ("fuel_fraction", "余油 {:.0%}"),
        ("temp_c", "温度 {:.0f}℃"),
        ("kill_count", "连杀 {}"),
        ("result", "战果 {}"),
    ]
    if kill_fact:
        bits.append(kill_fact)
    if event.event_id == "you_killed" and p.get("trade_death"):
        bits.append("同归于尽/换掉一个")
    if death_fact:
        bits.append(death_fact)
    if proximity_fact:
        bits.append(proximity_fact)
    if objective_fact:
        bits.append(objective_fact)
    if free_text_fact:
        bits.append(free_text_fact)
    if has_radio_altitude:
        try:
            bits.append("AGL {:.0f}m".format(p["radio_altitude_m"]))
        except (ValueError, TypeError):
            pass
    for key, fmt in order:
        if key == "altitude_m" and has_radio_altitude:
            continue
        if key in p and p[key] is not None:
            try:
                bits.append(fmt.format(p[key]))
            except (ValueError, TypeError):
                pass
    return "、".join(bits)


def _kill_fact(event_id: str, payload: dict[str, Any]) -> str:
    if event_id != "you_killed":
        return ""
    domain = str(payload.get("domain") or "").lower()
    if domain in {"air", "heli"}:
        return "击落敌方空中目标"
    if domain == "ground":
        return "击毁敌方地面目标"
    if domain == "naval":
        return "击毁敌方舰艇"
    return "击毁敌方目标"


def _death_fact(event_id: str, payload: dict[str, Any]) -> str:
    if event_id != "you_died":
        return ""
    cause = str(payload.get("cause") or "").lower()
    domain = str(payload.get("domain") or "").lower()
    if cause == "crashed":
        return "己方载具坠毁"
    if cause in {"destroyed", "wrecked"}:
        if domain == "naval":
            return "己方舰艇被摧毁"
        return "己方载具被摧毁"
    if cause == "shot_down":
        if domain in {"air", "heli"}:
            return "己方空中载具被击落"
        return "己方载具被击毁"
    return "己方载具损失"


def _proximity_fact(event_id: str, payload: dict[str, Any]) -> str:
    if event_id not in {"enemy_nearby", "air_threat_nearby", "enemy_on_six", "tailing_risk"}:
        return ""
    if event_id == "tailing_risk":
        base = "后方威胁持续接近"
    elif event_id == "enemy_on_six":
        base = "后方威胁接近"
    elif event_id == "air_threat_nearby":
        base = "空中威胁接近"
    else:
        base = "敌方目标接近"

    detail: list[str] = []
    clock = payload.get("clock")
    if isinstance(clock, int) and 1 <= clock <= 12:
        detail.append(f"{clock}点钟")
    elif payload.get("compass"):
        detail.append(f"{payload['compass']}方向")

    distance = payload.get("distance_m")
    try:
        if distance is not None:
            detail.append("距离{:.0f}m".format(float(distance)))
    except (TypeError, ValueError):
        pass

    return base if not detail else f"{base}（{'，'.join(detail)}）"


def _objective_fact(event_id: str, payload: dict[str, Any]) -> str:
    if event_id != "ground_target_nearby":
        return ""

    detail: list[str] = []
    grid = payload.get("grid")
    if isinstance(grid, str) and grid:
        detail.append(f"{grid}网格")

    distance = payload.get("distance_m")
    try:
        if distance is not None:
            detail.append("距离{:.0f}m".format(float(distance)))
    except (TypeError, ValueError):
        pass

    return "任务目标点接近" if not detail else f"任务目标点接近（{'，'.join(detail)}）"


def _free_text_fact(event_id: str, payload: dict[str, Any]) -> str:
    if event_id != "free_text_activity":
        return ""
    source_labels = {
        "awards": "奖励/战绩通知",
        "combat_feed": "战斗记录",
        "hud_notices": "HUD通知",
        "hud_events": "HUD事件",
        "hudmsg": "战场提示",
    }
    source = str(payload.get("source") or "")
    label = source_labels.get(source, "战场文字来源")
    detail: list[str] = []
    try:
        count = int(payload.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    if count > 0:
        detail.append(f"{count}条")
    code = payload.get("latest_code")
    if isinstance(code, str) and code:
        detail.append(code)
    return label if not detail else f"{label}（{'，'.join(detail)}）"


class NekoDispatcher:
    def __init__(
        self,
        plugin: Any,
        *,
        timeline: RuntimeTimeline | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.plugin = plugin
        self.timeline = timeline
        self.logger = getattr(plugin, "logger", None)
        self._clock = clock or time.time
        self._last_push_at: float | None = None
        self._last_push_priority = -1

    def build_prompt(self, event: BattleEvent) -> str:
        intent = _RECOVERY_INTENT if event.edge == "recovery" else _INTENT.get(event.event_id, "")
        fact = _fact_line(event)
        lines = []
        if fact:
            lines.append(f"[当前] {fact}")
        lines.append(f"[要求] {intent}。一句中文短句；不反问、不续聊、别复述数字/流程。")
        lines.append(_copilot_role_boundary(event))
        lines.append(_prompt_style_hint(event))
        return "\n".join(lines)

    def push_event(self, event: BattleEvent, *, dry_run: bool) -> str:
        """把一个 BattleEvent 投给猫娘。dry_run 时只返回摘要、不真投。"""
        if dry_run:
            text = self.build_prompt(event)
            if self.timeline:
                self.timeline.record_stage(
                    stage="dispatcher_dry_run",
                    outcome="dry_run",
                    reason="dry_run_enabled",
                    event_id=event.event_id,
                    edge=event.edge,
                    level=event.level,
                    priority=event.priority,
                    dry_run=True,
                    kind="event",
                    ai_behavior="respond",
                    pushed=False,
                    safe_summary=f"{event.event_id}/{event.edge}/{event.level}",
            )
            return f"dry_run(event={event.event_id}/{event.edge}/{event.level}, prio={event.priority}, preempt={event.preempt_eligible})"
        if event.event_id in FREE_TEXT_DRY_RUN_ONLY_EVENTS:
            if self.timeline:
                self.timeline.record_stage(
                    stage="dispatcher_suppressed",
                    outcome="dropped",
                    reason="free_text_dry_run_only",
                    event_id=event.event_id,
                    edge=event.edge,
                    level=event.level,
                    priority=event.priority,
                    dry_run=False,
                    kind="event",
                    ai_behavior="respond",
                    pushed=False,
                    safe_summary=f"{event.event_id}/{event.edge}/{event.level}",
                )
            return f"suppressed(event={event.event_id}/{event.edge}, reason=free_text_dry_run_only)"
        if self._is_v2_live_evidence_gated(event):
            if self.timeline:
                self.timeline.record_stage(
                    stage="dispatcher_suppressed",
                    outcome="dropped",
                    reason="v2_live_evidence_pending",
                    event_id=event.event_id,
                    edge=event.edge,
                    level=event.level,
                    priority=event.priority,
                    dry_run=False,
                    kind="event",
                    ai_behavior="respond",
                    pushed=False,
                    safe_summary=f"{event.event_id}/{event.edge}/{event.level}",
                )
            return f"suppressed(event={event.event_id}/{event.edge}, reason=v2_live_evidence_pending)"
        now = self._clock()
        freshness = _event_freshness_metadata(event, now, self.plugin)
        if self._is_expired(event, now):
            if self.timeline:
                self.timeline.record_stage(
                    stage="dispatcher_suppressed",
                    outcome="dropped",
                    reason="event_expired",
                    event_id=event.event_id,
                    edge=event.edge,
                    level=event.level,
                    priority=event.priority,
                    dry_run=False,
                    kind="event",
                    ai_behavior="respond",
                    pushed=False,
                    safe_summary=f"{event.event_id}/{event.edge}/{event.level}",
                    **freshness,
                )
            return f"suppressed(event={event.event_id}/{event.edge}, reason=event_expired)"
        if self._is_backpressured(event, now):
            if self.timeline:
                self.timeline.record_stage(
                    stage="dispatcher_suppressed",
                    outcome="dropped",
                    reason="output_backpressure",
                    event_id=event.event_id,
                    edge=event.edge,
                    level=event.level,
                    priority=event.priority,
                    dry_run=False,
                    kind="event",
                    ai_behavior="respond",
                    pushed=False,
                    safe_summary=f"{event.event_id}/{event.edge}/{event.level}",
                    **freshness,
                )
            return f"suppressed(event={event.event_id}/{event.edge}, reason=output_backpressure)"
        text = self.build_prompt(event)
        target_lanlan = _resolve_target_lanlan(self.plugin, event)
        host_contract = _host_callback_contract(event, freshness=freshness, target_lanlan=target_lanlan)
        metadata = {
            "plugin": "neko_warthunder",
            "event_id": event.event_id,
            "edge": event.edge,
            "level": event.level,
            "coalesce_key": BATTLE_EVENT_COALESCE_KEY,
            "replace_pending": True,
            "interrupt_battle_event": _host_interrupt_pending(event),
            "interrupt_pending": _host_interrupt_pending(event),
            "battle_reply_contract": BATTLE_REPLY_CONTRACT,
            "live_reply_contract": BATTLE_REPLY_CONTRACT,
            "reply_contract": BATTLE_REPLY_CONTRACT,
            "max_reply_chars": BATTLE_REPLY_MAX_CHARS,
            "reply_max_chars": BATTLE_REPLY_MAX_CHARS,
            "response_module_hint": BATTLE_RESPONSE_MODULE_HINT,
            "reply_style_contract": _reply_style_contract(event),
            "quiet_window_policy": HOST_QUIET_WINDOW_POLICY,
            "host_callback_contract_version": HOST_CALLBACK_CONTRACT_VERSION,
            "host_callback_contract": host_contract,
            **freshness,
        }
        if target_lanlan:
            metadata["target_lanlan"] = target_lanlan
        try:
            self.plugin.push_message(
                source="neko_warthunder",
                visibility=[],
                ai_behavior="respond",
                parts=[{"type": "text", "text": text}],
                priority=event.priority,
                coalesce_key=BATTLE_EVENT_COALESCE_KEY,
                metadata=metadata,
                target_lanlan=target_lanlan or None,
            )
        except Exception as exc:
            if self.timeline:
                self.timeline.record_stage(
                    stage="dispatcher_failed",
                    outcome="failed",
                    reason=type(exc).__name__,
                    event_id=event.event_id,
                    edge=event.edge,
                    level=event.level,
                    priority=event.priority,
                    dry_run=False,
                    kind="event",
                    ai_behavior="respond",
                    pushed=False,
                )
            raise
        self._last_push_at = now
        self._last_push_priority = event.priority
        if self.timeline:
            self.timeline.record_stage(
                stage="dispatcher_pushed",
                outcome="pushed",
                reason="push_message_accepted",
                event_id=event.event_id,
                edge=event.edge,
                level=event.level,
                priority=event.priority,
                dry_run=False,
                kind="event",
                ai_behavior="respond",
                pushed=True,
                safe_summary=f"{event.event_id}/{event.edge}/{event.level}",
                target_lanlan=target_lanlan,
                coalesce_key=BATTLE_EVENT_COALESCE_KEY,
                battle_reply_contract=BATTLE_REPLY_CONTRACT,
                live_reply_contract=BATTLE_REPLY_CONTRACT,
                max_reply_chars=BATTLE_REPLY_MAX_CHARS,
                response_module_hint=BATTLE_RESPONSE_MODULE_HINT,
                replace_pending=True,
                interrupt_battle_event=_host_interrupt_pending(event),
                interrupt_pending=_host_interrupt_pending(event),
                reply_style_contract=_reply_style_contract(event),
                reply_contract=BATTLE_REPLY_CONTRACT,
                reply_max_chars=BATTLE_REPLY_MAX_CHARS,
                quiet_window_policy=HOST_QUIET_WINDOW_POLICY,
                host_callback_contract_version=HOST_CALLBACK_CONTRACT_VERSION,
                **freshness,
            )
        return f"pushed(event={event.event_id}/{event.edge})"

    def _is_backpressured(self, event: BattleEvent, now: float) -> bool:
        if event.event_id in BACKPRESSURE_BYPASS_EVENTS or event.level == "critical":
            return False
        guard = _output_backpressure_seconds(self.plugin)
        if guard <= 0 or self._last_push_at is None:
            return False
        if now - self._last_push_at >= guard:
            return False
        return event.priority <= self._last_push_priority

    def _is_expired(self, event: BattleEvent, now: float) -> bool:
        max_age = _output_event_max_age_seconds(self.plugin, event)
        if max_age <= 0 or event.ts <= 0:
            return False
        return now >= event.ts and now - event.ts > max_age

    def _is_v2_live_evidence_gated(self, event: BattleEvent) -> bool:
        if event.event_id not in V2_LIVE_EVIDENCE_GATED_EVENTS:
            return False
        return not _v2_live_verified_real_output_enabled(self.plugin)

    def push_context(self, text: str) -> None:
        """注入/恢复常驻场景上下文（ai_behavior='read'，不触发回复）。"""
        target_lanlan = _resolve_target_lanlan(self.plugin)
        metadata = {"plugin": "neko_warthunder", "kind": "context"}
        if target_lanlan:
            metadata["target_lanlan"] = target_lanlan
        try:
            self.plugin.push_message(
                source="neko_warthunder",
                visibility=[],
                ai_behavior="read",
                parts=[{"type": "text", "text": text}],
                priority=0,
                metadata=metadata,
                target_lanlan=target_lanlan or None,
            )
            if self.timeline:
                self.timeline.record_stage(
                    stage="context_pushed",
                    outcome="pushed",
                    reason="push_message_accepted",
                    kind="context",
                    ai_behavior="read",
                    pushed=True,
                    dry_run=False,
                    safe_summary="context/read",
                    target_lanlan=target_lanlan,
                )
        except Exception as exc:  # noqa: BLE001 — 上下文注入失败不致命
            if self.timeline:
                self.timeline.record_stage(
                    stage="context_failed",
                    outcome="failed",
                    reason=type(exc).__name__,
                    kind="context",
                    ai_behavior="read",
                    pushed=False,
                    dry_run=False,
                )
            if self.logger:
                self.logger.warning(f"push_context failed: {type(exc).__name__}")
