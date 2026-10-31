"""Integration coverage for the Battle Awareness logic chain."""

from __future__ import annotations

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core import contracts as C
from neko_warthunder.core.scenario import ScenarioResolver
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from neko_warthunder.detectors.discrete.lifecycle import SpawnDetector, build_discrete_detectors


@pytest.mark.parametrize("domain,army,vehicle_valid", [
    ("air", "air", True), ("heli", "air", True),
    ("ground", "tank", False), ("naval", "ship", False),
])
@pytest.mark.parametrize("respawn", [False, True])
def test_spawn_delivery_preserves_domain_without_inventing_motion(domain, army, vehicle_valid, respawn):
    """Exercise telemetry -> life edge -> actual dispatch, including land without /state."""
    prev = C.BattleState(connected=True, dead=respawn)
    cur = parse_telemetry({
        "state": "in_battle", "in_battle": True, "timestamp": 100.0,
        "domain": domain, "domain_source": "indicators_army",
        "vehicle": {"valid": vehicle_valid},
        "indicators": {"valid": True, "army": army, "vehicle_type": "fixture_vehicle"},
    })
    event = SpawnDetector().detect(prev, cur)
    assert event is not None
    calls = []

    class Plugin:
        cfg = C.WtConfig()

        def push_message(self, **kwargs):
            calls.append(kwargs)
            return {"submitted": True}

    result = NekoDispatcher(Plugin(), clock=lambda: 100.0).push_event(event, dry_run=False)
    assert result.startswith("pushed(") and len(calls) == 1
    delivery = calls[0]
    assert delivery["metadata"]["domain"] == domain
    prompt = delivery["parts"][0]["text"]
    assert "事件不证明载具运动状态" in prompt
    assert ("已完成重生" in prompt) is respawn
    assert ("已进入战局" in prompt) is not respawn
    for unsupported_action in ("升空", "起飞", "出航", "悬停", "装填"):
        assert unsupported_action not in prompt
    assert "建议台词：" not in prompt
    assert "轻松陪伴，不责怪、不嘲讽、不催战绩" in prompt


def _alive(**kw):
    base = dict(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="air")
    base.update(kw)
    return C.BattleState(**base)


def test_detector_engine_collects_condition_and_discrete_events_then_dedups():
    engine = DetectorEngine(list(build_condition_detectors()) + list(build_discrete_detectors("Me")))
    prev = C.BattleState(connected=True, conn_state="not_in_battle", in_battle=False, vehicle_valid=False)
    cur = _alive(
        timestamp=100.0,
        vehicle_type="bf-109f-4",
        domain="air",
        domain_label="空军",
        fuel_fraction=0.08,
        flags={"fuel_low": True},
        combat={"feed": [{"id": 7, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "Bandit"}]},
    )

    events = engine.feed(prev, cur)
    assert [event.event_id for event in events] == ["low_fuel", "spawn", "you_killed"]
    assert events[0].payload == {"domain": "air", "fuel_fraction": 0.08}
    assert events[1].payload == {
        "vehicle_type": "bf-109f-4",
        "domain": "air",
        "domain_label": "空军",
        "respawn": False,
    }
    assert events[2].payload["victim"] == "Bandit"

    assert engine.feed(cur, cur) == []


def test_dispatcher_builds_prompt_for_each_event_and_recovery():
    dispatcher = NekoDispatcher(None)
    payloads = {
        "stall_risk": {"ias_kmh": 180, "aoa_deg": 16},
        "high_aoa": {"aoa_deg": 24, "g_now": 8.5},
        "over_g": {"g_now": 13.1, "aoa_deg": 18},
        "low_alt_danger": {"altitude_m": 120, "climb_ms": -18},
        "overspeed": {"ias_kmh": 760, "mach": 0.82},
        "overheat": {"temp_c": 118},
        "low_fuel": {"fuel_fraction": 0.07},
        "ground_laser_warning": {"domain": "ground"},
        "ground_crew_loss": {"domain": "ground", "crew_current": 1, "crew_total": 4},
        "ground_gunner_disabled": {"domain": "ground", "gunner_state": 0},
        "ground_driver_disabled": {"domain": "ground", "driver_state": 0},
        "ground_ammo_empty": {"domain": "ground", "ammo_first_stage": 0},
        "ground_ammo_low": {"domain": "ground", "ammo_first_stage": 3},
        "heli_vrs_risk": {"domain": "heli"},
        "naval_map_contact": {"domain": "naval"},
        "naval_air_contact": {"domain": "naval"},
        "ground_target_nearby": {"grid": "B4", "distance_m": 2400},
        "enemy_nearby": {"distance_m": 1200, "compass": "E"},
        "air_threat_nearby": {"distance_m": 1800, "clock": 2},
        "enemy_on_six": {"distance_m": 700, "clock": 6},
        "tailing_risk": {"distance_m": 620, "clock": 6},
        "free_text_activity": {"source": "awards", "count": 1, "latest_code": "final_blow"},
        "player_radio_command": {"command": "attack_point", "point": "D", "domain": "ground"},
        "you_killed": {"victim": "Bandit"},
        "you_died": {"cause": "unknown"},
        "spawn": {"vehicle_type": "bf-109f-4", "domain": "air"},
        "battle_end": {"result": "win, K2/D1", "result_kind": "victory"},
    }

    for event_id in C.EVENT_CATALOG:
        prompt = dispatcher.build_prompt(C.BattleEvent(event_id, payload=payloads[event_id]))
        assert prompt
        assert "{MASTER_NAME}" in prompt
        assert "None" not in prompt

    recovery_prompt = dispatcher.build_prompt(C.BattleEvent("stall_risk", edge="recovery"))
    assert "{MASTER_NAME}" in recovery_prompt


def test_scenario_resolver_handles_multi_tick_battle_sequence():
    resolver = ScenarioResolver()
    sequence = [
        (C.BattleState(connected=False), 100.0, C.OUT_OF_BATTLE),
        (_alive(), 101.0, C.SPAWNING),
        (_alive(), 108.0, C.IN_FLIGHT),
        (_alive(g_now=6.2), 109.0, C.COMBAT_STRESS),
        (_alive(), 116.0, C.COMBAT_STRESS),
        (_alive(), 118.0, C.IN_FLIGHT),
        (_alive(flags={"stall_critical": True}), 119.0, C.CRITICAL_RISK),
        (C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False), 120.0, C.DEAD),
        (_alive(mission_status="win"), 121.0, C.BATTLE_ENDED),
    ]

    for state, now, expected in sequence:
        assert resolver.resolve(state, now, grace_seconds=6.0) == expected
