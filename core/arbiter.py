"""提示仲裁器（D-B4）。候选 BattleEvent + 当前 Scenario → 至多 1 条输出。

流水线：Scenario 门控 → cooldown 去重 → 分流(抢占/限流) → 抢占立即 / 单槽窗口择优 + 全局限流。
返回 (选中事件 | None, 决策链路)；决策链路供 dry_run 日志解释"为什么说/没说"。
"""

from __future__ import annotations

from typing import Any

from .contracts import CRITICAL_RISK, DEAD, BattleEvent, category_allowed
from .safety_guard import SafetyGuard

class Arbiter:
    def __init__(self, safety: SafetyGuard) -> None:
        self.safety = safety
        self._last_fired: dict[str, tuple[float, str]] = {}
        self._window_best: BattleEvent | None = None
        self._kill_window: BattleEvent | None = None
        self._kill_window_started_at: float = 0.0

    def reset(self) -> None:
        self._last_fired.clear()
        self._window_best = None
        self._kill_window = None
        self._kill_window_started_at = 0.0

    def decide(self, candidates: list[BattleEvent], scenario: str, now: float) -> tuple[BattleEvent | None, list[dict[str, Any]]]:
        chain: list[dict[str, Any]] = []

        if self.safety.stopped:
            for c in candidates:
                chain.append(_rec(c, "suppressed", self.safety.status()))
            return None, chain

        # [1] Scenario 门控 + [2] cooldown 去重
        kill_coalesce_window = self.safety.config.kill_coalesce_window_seconds
        survivors: list[BattleEvent] = []
        for c in candidates:
            allowed, gate_reason = _event_allowed(c, scenario)
            if not allowed:
                if c.event_id == "you_killed" and scenario == DEAD and kill_coalesce_window > 0:
                    if _recent_death_preempt(self._last_fired, now, kill_coalesce_window):
                        trade_kill = _trade_kill_event(c, BattleEvent("you_died", level="critical", ts=now), now)
                        self._fire(trade_kill, now, critical=False)
                        chain.append(_rec(c, "spoken", "trade_kill_after_death"))
                        return trade_kill, chain
                    self._buffer_kill(c, now)
                    chain.append(_rec(c, "buffered", "kill_deferred_dead"))
                    continue
                if c.event_id == "you_killed" and scenario == CRITICAL_RISK and kill_coalesce_window > 0:
                    self._buffer_kill(c, now)
                    chain.append(_rec(c, "buffered", "kill_deferred_critical_risk"))
                    continue
                chain.append(_rec(c, "dropped", gate_reason))
                continue
            cd = c.spec.cooldown_seconds
            last_at, last_level = self._last_fired.get(c.event_id, (-1e9, ""))
            critical_upgrade = c.level == "critical" and last_level != "critical"
            if cd > 0 and (now - last_at) < cd and not critical_upgrade:
                chain.append(_rec(c, "dropped", "cooldown"))
                continue
            survivors.append(c)

        preempt = [c for c in survivors if c.preempt_eligible]
        normal = [c for c in survivors if not c.preempt_eligible]

        # [3]/[4] 抢占通道
        if preempt:
            best = _top(preempt)
            crit_remaining = self.safety.critical_cooldown_remaining(now)
            if crit_remaining > 0 and best.priority < 10:
                chain.append(_rec(best, "suppressed", f"critical_cooldown({crit_remaining:.1f}s)"))
            else:
                trade_kill = None
                if best.event_id == "you_died" and self._kill_window is not None:
                    trade_kill = _trade_kill_event(self._kill_window, best, now)
                self._fire(best, now, critical=True)
                self._window_best = None  # 抢占清空 warning 窗口（不补播）
                if trade_kill is not None:
                    self._fire(trade_kill, now, critical=False)
                    chain.append(_rec(self._kill_window, "spoken", "trade_kill_preempt"))
                    self._kill_window = None
                    self._kill_window_started_at = 0.0
                    return trade_kill, chain
                if self._kill_window is not None:
                    chain.append(_rec(self._kill_window, "dropped", "lost_to_preempt"))
                    self._kill_window = None
                    self._kill_window_started_at = 0.0
                chain.append(_rec(best, "spoken", "preempt"))
                for c in survivors:
                    if c is not best:
                        chain.append(_rec(c, "dropped", "lost_to_preempt"))
                return best, chain

        # [5] 限流通道：单槽窗口择优（留最高 priority），到点 flush
        if kill_coalesce_window > 0:
            kill_events = [c for c in normal if c.event_id == "you_killed"]
            normal = [c for c in normal if c.event_id != "you_killed"]
            for c in kill_events:
                self._buffer_kill(c, now)
                chain.append(_rec(c, "buffered", "kill_coalescing"))

        if normal:
            best = _top(normal)
            if self._window_best is None or _rank(best) > _rank(self._window_best):
                self._window_best = best
            for c in normal:
                if c is not best:
                    chain.append(_rec(c, "dropped", "lost_in_window"))

        rate_remaining = self.safety.rate_limit_remaining(now)
        if (
            self._kill_window is not None
            and kill_coalesce_window > 0
            and now - self._kill_window_started_at >= kill_coalesce_window
            and rate_remaining <= 0
        ):
            chosen = self._kill_window
            allowed, gate_reason = _event_allowed(chosen, scenario)
            if not allowed:
                if chosen.event_id == "you_killed" and scenario == DEAD:
                    chain.append(_rec(chosen, "buffered", "scenario_gated_deferred(DEAD)"))
                    return None, chain
                if chosen.event_id == "you_killed" and scenario == CRITICAL_RISK:
                    chain.append(_rec(chosen, "buffered", "scenario_gated_deferred(CRITICAL_RISK)"))
                    return None, chain
                self._kill_window = None
                self._kill_window_started_at = 0.0
                chain.append(_rec(chosen, "dropped", gate_reason.replace("scenario_gated", "scenario_gated_on_flush", 1)))
                return None, chain
            self._kill_window = None
            self._kill_window_started_at = 0.0
            self._fire(chosen, now, critical=False)
            chain.append(_rec(chosen, "spoken", "kill_coalesced"))
            return chosen, chain

        if self._window_best is not None and rate_remaining <= 0:
            chosen = self._window_best
            self._window_best = None
            # flush 时按【当前】scenario 重新门控：缓冲期内场景可能已切到 DEAD/BATTLE_ENDED/OUT_OF_BATTLE
            allowed, gate_reason = _event_allowed(chosen, scenario)
            if not allowed:
                chain.append(_rec(chosen, "dropped", gate_reason.replace("scenario_gated", "scenario_gated_on_flush", 1)))
                return None, chain
            self._fire(chosen, now, critical=False)
            chain.append(_rec(chosen, "spoken", "window_flush"))
            return chosen, chain

        if self._window_best is not None:
            chain.append(_rec(self._window_best, "buffered", f"rate_limited({rate_remaining:.1f}s)"))
        return None, chain

    def _fire(self, event: BattleEvent, now: float, *, critical: bool) -> None:
        self._last_fired[event.event_id] = (now, event.level)
        self.safety.mark_output(critical=critical, now=now)

    def _buffer_kill(self, event: BattleEvent, now: float) -> None:
        if self._kill_window is None:
            payload = dict(event.payload)
            payload["kill_count"] = int(payload.get("kill_count") or 1)
            self._kill_window = BattleEvent(
                event.event_id,
                edge=event.edge,
                payload=payload,
                ts=event.ts,
                level=event.level,
            )
            self._kill_window_started_at = now
            return

        payload = dict(self._kill_window.payload)
        payload["kill_count"] = int(payload.get("kill_count") or 1) + int(event.payload.get("kill_count") or 1)
        if event.payload.get("victim") is not None:
            payload["victim"] = event.payload.get("victim")
        if event.payload.get("victim_vehicle") is not None:
            payload["victim_vehicle"] = event.payload.get("victim_vehicle")
        if event.payload.get("domain") is not None:
            payload["domain"] = event.payload.get("domain")
        self._kill_window = BattleEvent(
            self._kill_window.event_id,
            edge=self._kill_window.edge,
            payload=payload,
            ts=max(self._kill_window.ts, event.ts),
            level=self._kill_window.level,
        )


def _rank(e: BattleEvent) -> tuple[int, int, float]:
    return (e.priority, e.severity, e.ts)


def _top(events: list[BattleEvent]) -> BattleEvent:
    return max(events, key=_rank)


def _trade_kill_event(kill_event: BattleEvent, death_event: BattleEvent, now: float) -> BattleEvent:
    payload = dict(kill_event.payload)
    payload["trade_death"] = True
    payload["death_event"] = death_event.event_id
    if death_event.payload.get("domain") is not None and payload.get("domain") is None:
        payload["domain"] = death_event.payload.get("domain")
    if death_event.payload.get("cause") is not None:
        payload["death_cause"] = death_event.payload.get("cause")
    return BattleEvent(
        kill_event.event_id,
        edge=kill_event.edge,
        payload=payload,
        ts=now,
        level=kill_event.level,
    )


def _recent_death_preempt(last_fired: dict[str, tuple[float, str]], now: float, window_seconds: float) -> bool:
    last_at, _last_level = last_fired.get("you_died", (-1e9, ""))
    grace = max(window_seconds * 2.0, 4.0)
    return now - last_at <= grace


def _event_allowed(event: BattleEvent, scenario: str) -> tuple[bool, str]:
    if not category_allowed(scenario, event.category):
        return False, f"scenario_gated({scenario})"
    if scenario == "COMBAT_STRESS" and event.event_id in {"enemy_nearby", "ground_target_nearby"}:
        return False, "scenario_gated(COMBAT_STRESS:map_low_priority)"
    return True, ""


def _rec(e: BattleEvent, result: str, reason: str) -> dict[str, Any]:
    return {"event_id": e.event_id, "edge": e.edge, "level": e.level, "result": result, "reason": reason}
