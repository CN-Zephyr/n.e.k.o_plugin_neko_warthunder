"""Scenario phase 机解析（D-B1）。"""

from __future__ import annotations

from neko_warthunder.core import contracts as C
from neko_warthunder.core.scenario import ScenarioResolver


def _alive(**kw):
    base = dict(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True)
    base.update(kw)
    return C.BattleState(**base)


def test_out_of_battle():
    r = ScenarioResolver()
    assert r.resolve(C.BattleState(connected=False), 1000.0, 6) == C.OUT_OF_BATTLE
    assert r.resolve(C.BattleState(connected=True, conn_state="not_in_battle"), 1000.0, 6) == C.OUT_OF_BATTLE


def test_spawn_then_in_flight():
    r = ScenarioResolver()
    assert r.resolve(_alive(), 1000.0, 6) == C.SPAWNING
    assert r.resolve(_alive(), 1003.0, 6) == C.SPAWNING
    assert r.resolve(_alive(), 1007.0, 6) == C.IN_FLIGHT


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
    dmg = _alive(hud_events=[{"id": 3, "kind": "damage"}])
    assert r.resolve(dmg, 1008.0, 6) == C.COMBAT_STRESS          # 新受创 → 进 stress
    assert r.resolve(dmg, 1018.0, 6) == C.IN_FLIGHT              # 同一条旧 damage 不应永久卡住
