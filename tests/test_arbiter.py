"""Arbiter 仲裁（D-B4）：门控 / 抢占 / 单槽窗口 / 限流 / ≤1 条。"""

from __future__ import annotations

from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.contracts import (
    COMBAT_STRESS,
    CRITICAL_RISK,
    DEAD,
    IN_FLIGHT,
    SPAWNING,
    BattleEvent,
    WtConfig,
)
from neko_warthunder.core.safety_guard import SafetyGuard


def _arb() -> Arbiter:
    return Arbiter(SafetyGuard(WtConfig()))


def test_scenario_gating_drops_low_fuel_in_combat():
    chosen, chain = _arb().decide([BattleEvent("low_fuel", level="warning")], COMBAT_STRESS, 1000.0)
    assert chosen is None
    assert any(c["result"] == "dropped" and "scenario_gated" in c["reason"] for c in chain)


def test_spawning_allows_owned_kill_event():
    arb = _arb()
    chosen, chain = arb.decide([BattleEvent("you_killed", level="warning")], SPAWNING, 1000.0)
    flushed, flush_chain = arb.decide([], SPAWNING, 1006.1)
    assert chosen is None
    assert any(c["result"] == "buffered" and c["reason"] == "kill_coalescing" for c in chain)
    assert flushed is not None and flushed.event_id == "you_killed"
    assert any(c["result"] == "spoken" and c["reason"] == "kill_coalesced" for c in flush_chain)


def test_spawning_still_gates_flight_safety_warning():
    chosen, chain = _arb().decide([BattleEvent("overheat", level="warning")], SPAWNING, 1000.0)
    assert chosen is None
    assert any(c["result"] == "dropped" and c["reason"] == "scenario_gated(SPAWNING)" for c in chain)


def test_idle_immediate_warning():
    chosen, _ = _arb().decide([BattleEvent("low_fuel", level="warning")], IN_FLIGHT, 1000.0)
    assert chosen is not None and chosen.event_id == "low_fuel"


def test_critical_preempts_immediately():
    chosen, chain = _arb().decide([BattleEvent("stall_risk", level="critical")], CRITICAL_RISK, 1000.0)
    assert chosen is not None and chosen.event_id == "stall_risk"
    assert any(c["result"] == "spoken" and c["reason"] == "preempt" for c in chain)


def test_single_output_two_criticals():
    chosen, chain = _arb().decide(
        [BattleEvent("stall_risk", level="critical"), BattleEvent("low_alt_danger", level="critical")],
        CRITICAL_RISK,
        1000.0,
    )
    assert chosen is not None and chosen.event_id == "low_alt_danger"  # 同 priority，severity 9>8
    assert sum(1 for c in chain if c["result"] == "spoken") == 1


def test_rate_limit_buffer_then_flush():
    arb = _arb()
    a, _ = arb.decide([BattleEvent("overheat", level="warning")], IN_FLIGHT, 1000.0)
    assert a is not None and a.event_id == "overheat"               # 空闲即时
    b, _ = arb.decide([BattleEvent("low_fuel", level="warning")], IN_FLIGHT, 1003.0)
    assert b is None                                                # 12s 限流内 → 缓冲
    c, _ = arb.decide([], IN_FLIGHT, 1013.0)
    assert c is not None and c.event_id == "low_fuel"               # 窗口到点 flush


def test_window_flush_preserves_latest_observation_timestamp():
    arb = _arb()
    a, _ = arb.decide([BattleEvent("low_fuel", level="warning", ts=1000.0)], IN_FLIGHT, 1000.0)
    b, _ = arb.decide([BattleEvent("overheat", level="warning", ts=1003.0)], IN_FLIGHT, 1003.0)
    c, chain = arb.decide([], IN_FLIGHT, 1013.0)

    assert a is not None and a.event_id == "low_fuel"
    assert b is None
    assert c is not None and c.event_id == "overheat"
    assert c.ts == 1003.0
    assert any(item["result"] == "spoken" and item["reason"] == "window_flush" for item in chain)


def test_cooldown_drops_repeat():
    arb = _arb()
    arb.decide([BattleEvent("overheat", level="warning")], IN_FLIGHT, 1000.0)
    chosen, chain = arb.decide([BattleEvent("overheat", level="warning")], IN_FLIGHT, 1005.0)
    assert chosen is None
    assert any(c["result"] == "dropped" and c["reason"] == "cooldown" for c in chain)


def test_critical_upgrade_is_not_blocked_by_warning_cooldown():
    arb = _arb()
    first, _ = arb.decide([BattleEvent("overspeed", level="warning")], IN_FLIGHT, 1000.0)
    chosen, chain = arb.decide([BattleEvent("overspeed", level="critical")], CRITICAL_RISK, 1003.0)
    assert first is not None and first.event_id == "overspeed"
    assert chosen is not None and chosen.event_id == "overspeed" and chosen.level == "critical"
    assert any(c["result"] == "spoken" and c["reason"] == "preempt" for c in chain)
    assert not any(c["result"] == "dropped" and c["reason"] == "cooldown" for c in chain)


def test_paused_suppresses_all():
    arb = _arb()
    arb.safety.pause()
    chosen, chain = arb.decide([BattleEvent("stall_risk", level="critical")], CRITICAL_RISK, 1000.0)
    assert chosen is None
    assert any(c["result"] == "suppressed" for c in chain)


def test_disabled_general_safety_category_keeps_critical_safety_alerts():
    config = WtConfig(broadcast_categories={"safety": False})
    arb = Arbiter(SafetyGuard(config))

    warning, warning_chain = arb.decide([BattleEvent("overheat", level="warning")], IN_FLIGHT, 1000.0)
    critical, critical_chain = arb.decide([BattleEvent("stall_risk", level="critical")], CRITICAL_RISK, 1001.0)

    assert warning is None
    assert any(item["reason"] == "broadcast_category_disabled" for item in warning_chain)
    assert critical is not None and critical.event_id == "stall_risk"
    assert any(item["result"] == "spoken" for item in critical_chain)

    buffered_config = WtConfig()
    buffered_arb = Arbiter(SafetyGuard(buffered_config))
    buffered_arb.decide([BattleEvent("low_fuel", level="warning")], IN_FLIGHT, 2000.0)
    buffered_arb.decide([BattleEvent("overheat", level="warning")], IN_FLIGHT, 2001.0)
    buffered_config.broadcast_categories = {"safety": False}
    flushed, flush_chain = buffered_arb.decide([], IN_FLIGHT, 2013.0)
    assert flushed is None
    assert any(item["reason"] == "broadcast_category_disabled_on_flush" for item in flush_chain)


def test_disabled_lifecycle_category_keeps_death_alert():
    config = WtConfig(broadcast_categories={"lifecycle": False})
    arb = Arbiter(SafetyGuard(config))

    spawn, spawn_chain = arb.decide([BattleEvent("spawn")], SPAWNING, 1000.0)
    death, death_chain = arb.decide([BattleEvent("you_died", level="critical")], DEAD, 1001.0)

    assert spawn is None
    assert any(item["reason"] == "broadcast_category_disabled" for item in spawn_chain)
    assert death is not None and death.event_id == "you_died"
    assert any(item["result"] == "spoken" for item in death_chain)


def test_window_flush_dropped_if_scenario_changed():
    arb = _arb()
    a, _ = arb.decide([BattleEvent("overheat", level="warning")], IN_FLIGHT, 1000.0)
    assert a is not None                                            # 占用限流时钟
    b, _ = arb.decide([BattleEvent("low_fuel", level="warning")], IN_FLIGHT, 1003.0)
    assert b is None                                                # 缓冲
    c, chain = arb.decide([], DEAD, 1013.0)                         # 窗口到点但场景已切 DEAD
    assert c is None
    assert any("scenario_gated_on_flush" in x["reason"] for x in chain)


def test_map_awareness_allowed_in_flight_but_low_priority_dropped_in_combat_stress():
    in_flight, _ = _arb().decide([BattleEvent("enemy_nearby", level="warning")], IN_FLIGHT, 1000.0)
    combat, chain = _arb().decide([BattleEvent("enemy_nearby", level="warning")], COMBAT_STRESS, 1000.0)

    assert in_flight is not None and in_flight.event_id == "enemy_nearby"
    assert combat is None
    assert any(c["result"] == "dropped" and "map_low_priority" in c["reason"] for c in chain)


def test_ground_enemy_nearby_is_not_dropped_as_low_priority_map_awareness():
    chosen, chain = _arb().decide(
        [BattleEvent("enemy_nearby", level="warning", payload={"domain": "ground"})],
        COMBAT_STRESS,
        1000.0,
    )

    assert chosen is not None and chosen.event_id == "enemy_nearby"
    assert not any("map_low_priority" in c["reason"] for c in chain)


def test_ground_target_awareness_is_low_priority_map_awareness():
    in_flight, _ = _arb().decide([BattleEvent("ground_target_nearby", level="warning")], IN_FLIGHT, 1000.0)
    combat, chain = _arb().decide([BattleEvent("ground_target_nearby", level="warning")], COMBAT_STRESS, 1000.0)

    assert in_flight is not None and in_flight.event_id == "ground_target_nearby"
    assert combat is None
    assert any(c["result"] == "dropped" and "map_low_priority" in c["reason"] for c in chain)


def test_air_and_rear_threats_allowed_in_combat_stress():
    air, _ = _arb().decide([BattleEvent("air_threat_nearby", level="warning")], COMBAT_STRESS, 1000.0)
    rear, _ = _arb().decide([BattleEvent("enemy_on_six", level="warning")], COMBAT_STRESS, 1000.0)
    tailing, _ = _arb().decide([BattleEvent("tailing_risk", level="warning")], COMBAT_STRESS, 1000.0)

    assert air is not None and air.event_id == "air_threat_nearby"
    assert rear is not None and rear.event_id == "enemy_on_six"
    assert tailing is not None and tailing.event_id == "tailing_risk"


def test_map_awareness_does_not_compete_with_critical_risk():
    chosen, chain = _arb().decide(
        [BattleEvent("tailing_risk", level="warning"), BattleEvent("low_alt_danger", level="critical")],
        CRITICAL_RISK,
        1000.0,
    )

    assert chosen is not None and chosen.event_id == "low_alt_danger"
    assert any(c["event_id"] == "tailing_risk" and c["result"] == "dropped" for c in chain)


def test_map_awareness_suppressed_in_spawning_and_dead():
    spawning, spawning_chain = _arb().decide([BattleEvent("air_threat_nearby", level="warning")], SPAWNING, 1000.0)
    dead, dead_chain = _arb().decide([BattleEvent("enemy_on_six", level="warning")], DEAD, 1000.0)

    assert spawning is None
    assert dead is None
    assert any(c["reason"] == "scenario_gated(SPAWNING)" for c in spawning_chain)
    assert any(c["reason"] == "scenario_gated(DEAD)" for c in dead_chain)
