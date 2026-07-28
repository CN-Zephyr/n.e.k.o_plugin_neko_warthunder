"""Scenario phase 机解析（D-B1）。"""

from __future__ import annotations

from neko_warthunder.core import contracts as C
from neko_warthunder.core.scenario import ScenarioResolver


def _alive(**kw):
    base = dict(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="air")
    base.update(kw)
    return C.BattleState(**base)


def _owned_damage(feed_id: int = 3):
    """归属到本机的 combat.feed 条目——交火压力只认这种，不认全场击杀榜。"""
    return {"feed": [{"id": feed_id, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "X"}]}


def test_out_of_battle():
    r = ScenarioResolver()
    assert r.resolve(C.BattleState(connected=False), 1000.0, 6) == C.OUT_OF_BATTLE
    assert r.resolve(C.BattleState(connected=True, conn_state="not_in_battle"), 1000.0, 6) == C.OUT_OF_BATTLE


def test_spawn_then_in_flight():
    r = ScenarioResolver()
    assert r.resolve(_alive(), 1000.0, 6) == C.SPAWNING
    assert r.resolve(_alive(), 1003.0, 6) == C.SPAWNING
    assert r.resolve(_alive(), 1007.0, 6) == C.IN_FLIGHT


def test_ground_alive_uses_indicators_when_vehicle_state_is_absent():
    r = ScenarioResolver()
    ground = C.BattleState(
        connected=True,
        conn_state="in_battle",
        in_battle=True,
        vehicle_valid=False,
        indicators_valid=True,
        has_player=True,
        domain="ground",
        vehicle_type="ussr_t_80ue1_sm",
    )
    assert r.resolve(ground, 1000.0, 6) == C.SPAWNING
    assert r.resolve(ground, 1007.0, 6) == C.IN_FLIGHT


def test_critical_risk():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)
    crit = _alive(flags={"stall_critical": True})
    assert r.resolve(crit, 1008.0, 6) == C.CRITICAL_RISK


def test_flight_control_critical_flags_enter_critical_risk():
    for code in ("aoa_critical", "over_g_critical"):
        r = ScenarioResolver()
        r.resolve(_alive(), 1000.0, 6)
        r.resolve(_alive(), 1007.0, 6)
        assert r.resolve(_alive(flags={code: True}), 1008.0, 6) == C.CRITICAL_RISK


def test_combat_stress_high_g():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)
    assert r.resolve(_alive(g_now=6.0), 1008.0, 6) == C.COMBAT_STRESS
    assert r.current_stress_reasons(1008.0) == frozenset({"maneuver"})


def test_ground_high_g_does_not_enter_air_maneuver_stress():
    r = ScenarioResolver()
    r.resolve(_alive(domain="ground", indicators_valid=True, has_player=True), 1000.0, 6)
    r.resolve(_alive(domain="ground", indicators_valid=True, has_player=True), 1007.0, 6)

    assert r.resolve(_alive(domain="ground", indicators_valid=True, has_player=True, g_now=6.0), 1008.0, 6) == C.IN_FLIGHT
    assert r.current_stress_reasons(1008.0) == frozenset()


def test_ground_close_surface_contact_has_ground_disengagement_window():
    r = ScenarioResolver()
    base = dict(domain="ground", indicators_valid=True, has_player=True)
    close = _alive(
        **base,
        situation={"enemies": [{"type": "ground_model", "distance_m": 450}]},
        proximity={"thresholds_m": {"vs_ground": 500}},
    )
    clear = _alive(
        **base,
        situation={"enemies": [{"type": "ground_model", "distance_m": 1200}]},
        proximity={"thresholds_m": {"vs_ground": 500}},
    )

    r.resolve(_alive(**base), 1000.0, 6)
    r.resolve(_alive(**base), 1007.0, 6)

    assert r.resolve(close, 1008.0, 6) == C.COMBAT_STRESS
    assert r.current_stress_reasons(1008.0) == frozenset({"surface_contact"})
    assert r.resolve(clear, 1017.0, 6) == C.COMBAT_STRESS
    assert r.resolve(clear, 1018.1, 6) == C.IN_FLIGHT
    assert r.current_stress_reasons(1018.1) == frozenset()


def test_naval_surface_contact_uses_longer_disengagement_window():
    r = ScenarioResolver()
    base = dict(domain="naval", indicators_valid=True, has_player=True)
    close = _alive(
        **base,
        situation={"nearest_enemy": {"type": "ground_model", "distance_m": 1800}},
        proximity={"thresholds_m": {"vs_ground": 2000}},
    )
    clear = _alive(
        **base,
        situation={"nearest_enemy": {"type": "ground_model", "distance_m": 5000}},
        proximity={"thresholds_m": {"vs_ground": 2000}},
    )

    r.resolve(_alive(**base), 1000.0, 6)
    r.resolve(_alive(**base), 1007.0, 6)

    assert r.resolve(close, 1008.0, 6) == C.COMBAT_STRESS
    assert r.resolve(clear, 1027.0, 6) == C.COMBAT_STRESS
    assert r.resolve(clear, 1028.1, 6) == C.IN_FLIGHT


def test_air_close_air_contact_has_air_disengagement_window():
    r = ScenarioResolver()
    close = _alive(
        domain="air",
        situation={"nearest_air_threat": {"type": "aircraft", "distance_m": 4200}},
        proximity={"thresholds_m": {"vs_air": 5000}},
    )
    clear = _alive(
        domain="air",
        situation={"nearest_air_threat": {"type": "aircraft", "distance_m": 7000}},
        proximity={"thresholds_m": {"vs_air": 5000}},
    )

    r.resolve(_alive(domain="air"), 1000.0, 6)
    r.resolve(_alive(domain="air"), 1007.0, 6)

    assert r.resolve(close, 1008.0, 6) == C.COMBAT_STRESS
    assert r.current_stress_reasons(1008.0) == frozenset({"air_contact"})
    assert r.resolve(clear, 1015.0, 6) == C.COMBAT_STRESS
    assert r.resolve(clear, 1016.1, 6) == C.IN_FLIGHT


def test_death():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)
    dead = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False)
    assert r.resolve(dead, 1008.0, 6) == C.DEAD


def test_dead_flag_overrides_stale_vehicle_valid():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)
    dead = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, dead=True)
    assert r.resolve(dead, 1008.0, 6) == C.DEAD


def test_battle_ended():
    r = ScenarioResolver()
    assert r.resolve(_alive(mission_status="win"), 1000.0, 6) == C.BATTLE_ENDED


def test_combat_stress_not_stuck_on_stale_damage():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)
    dmg = _alive(combat=_owned_damage())
    assert r.resolve(dmg, 1008.0, 6) == C.COMBAT_STRESS          # 新的本机战斗条目 → 进 stress
    assert r.current_stress_reasons(1008.0) == frozenset({"damage"})
    assert r.resolve(dmg, 1018.0, 6) == C.IN_FLIGHT              # 同一条旧 damage 不应永久卡住
    assert r.current_stress_reasons(1018.0) == frozenset()


def test_combat_stress_reasons_expire_independently():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)
    assert r.resolve(_alive(g_now=6.0), 1008.0, 6) == C.COMBAT_STRESS
    assert r.resolve(_alive(combat=_owned_damage()), 1012.0, 6) == C.COMBAT_STRESS
    assert r.current_stress_reasons(1012.0) == frozenset({"maneuver", "damage"})
    assert r.current_stress_reasons(1016.5) == frozenset({"damage"})


def test_domain_change_clears_mode_stress_but_preserves_damage():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)
    stressed = _alive(g_now=6.0, combat=_owned_damage())

    assert r.resolve(stressed, 1008.0, 6) == C.COMBAT_STRESS
    assert r.current_stress_reasons(1008.0) == frozenset({"maneuver", "damage"})

    ground = _alive(domain="ground", indicators_valid=True, has_player=True)
    assert r.resolve(ground, 1009.0, 6) == C.COMBAT_STRESS
    assert r.current_stress_reasons(1009.0) == frozenset({"damage"})
    assert r.resolve(ground, 1016.1, 6) == C.IN_FLIGHT


def test_combat_stress_ignores_unowned_battle_log_activity():
    """全场击杀榜不得被当成本机受创。

    数据层 hud_events 是未过滤的全场战斗日志，多人对局里近乎连续；若按它计压力，
    玩家独自巡航也会长期停在 COMBAT_STRESS，压掉 low_fuel 与陪伴类输出。
    """
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)

    others = _alive(
        hud_events=[{"id": 3, "kind": "damage"}, {"id": 4, "kind": "damage"}],
        combat={"feed": [{"id": 4, "is_kill": True, "is_my_kill": False, "is_my_death": False, "victim": "Someone"}]},
    )
    assert r.resolve(others, 1008.0, 6) == C.IN_FLIGHT
    assert r.current_stress_reasons(1008.0) == frozenset()


def test_combat_stress_enters_on_owned_death_feed_entry():
    r = ScenarioResolver()
    r.resolve(_alive(), 1000.0, 6)
    r.resolve(_alive(), 1007.0, 6)

    owned_death = _alive(combat={"feed": [{"id": 7, "is_kill": True, "is_my_death": True, "killer": "Bandit"}]})
    assert r.resolve(owned_death, 1008.0, 6) == C.COMBAT_STRESS
    assert r.current_stress_reasons(1008.0) == frozenset({"damage"})
