"""Detector：边沿 FSM（confirm/迟滞/re-arm）+ 离散去重（D-B3）。"""

from __future__ import annotations

import pytest

from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core import contracts as C
from neko_warthunder.detectors._base import ConditionDetector, DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from neko_warthunder.detectors.discrete.lifecycle import BattleEndDetector, DeathDetector, KillDetector, SpawnDetector
from neko_warthunder.detectors.discrete.free_text import FreeTextActivityDetector
from neko_warthunder.detectors.discrete.notices import HudNoticeDetector
from neko_warthunder.detectors.discrete.proximity import ProximityDetector
from neko_warthunder.detectors.discrete.radio import RadioCommandDetector, parse_radio_command
from neko_warthunder.detectors.discrete.situation import AirSituationDetector, GroundTargetDetector


def _st(flags=None):
    return C.BattleState(flags=flags or {})


def test_condition_enter_after_confirm():
    d = ConditionDetector("stall_risk", [("stall_warning", "stall_critical")], confirm_enter=2, confirm_exit=2)
    prev = C.BattleState()
    assert d.feed(prev, _st({"stall_warning": True})) is None        # confirming 1/2
    ev = d.feed(prev, _st({"stall_warning": True}))                  # confirming 2/2 -> ACTIVE
    assert ev is not None and ev.event_id == "stall_risk" and ev.edge == "enter" and ev.level == "warning"
    assert d.feed(prev, _st({"stall_warning": True})) is None        # 持续期不重发


def test_condition_debounce_spike():
    d = ConditionDetector("stall_risk", [("stall_warning", "stall_critical")], confirm_enter=2)
    prev = C.BattleState()
    assert d.feed(prev, _st({"stall_warning": True})) is None        # 1
    assert d.feed(prev, _st({})) is None                             # 单帧尖刺被滤，回 ARMED
    assert d.feed(prev, _st({"stall_warning": True})) is None        # 重新计数 1/2


def test_condition_rearm():
    d = ConditionDetector("low_fuel", [("fuel_low", "fuel_critical")], confirm_enter=1, confirm_exit=1)
    prev = C.BattleState()
    assert d.feed(prev, _st({"fuel_low": True})).event_id == "low_fuel"   # confirm_enter=1 当拍触发
    assert d.feed(prev, _st({})) is None                                  # 退出 -> re-arm
    assert d.feed(prev, _st({"fuel_low": True})).event_id == "low_fuel"   # 再次触发


def test_condition_critical_level():
    d = ConditionDetector("stall_risk", [("stall_warning", "stall_critical")], confirm_enter=1)
    ev = d.feed(C.BattleState(), _st({"stall_critical": True}))
    assert ev is not None and ev.level == "critical"


def test_high_aoa_and_over_g_flags_emit_flight_control_events():
    detectors = {d.id: d for d in build_condition_detectors()}

    aoa = detectors["high_aoa"].feed(
        C.BattleState(),
        C.BattleState(domain="air", flags={"aoa_critical": True}, aoa_deg=24.0, g_now=8.5),
    )
    over_g = detectors["over_g"].feed(
        C.BattleState(),
        C.BattleState(domain="air", flags={"over_g_critical": True}, g_now=13.1, aoa_deg=18.0),
    )

    assert aoa is not None and aoa.event_id == "high_aoa" and aoa.level == "critical"
    assert aoa.payload["aoa_deg"] == 24.0
    assert over_g is not None and over_g.event_id == "over_g" and over_g.level == "critical"
    assert over_g.payload["g_now"] == 13.1


def test_condition_escalation_reemits_critical():
    """warning 持续中升级到 critical：应重发一条 critical enter（可抢占）。"""
    d = ConditionDetector("stall_risk", [("stall_warning", "stall_critical")], confirm_enter=1, confirm_exit=2)
    prev = C.BattleState()
    ev1 = d.feed(prev, _st({"stall_warning": True}))
    assert ev1 is not None and ev1.level == "warning"
    ev2 = d.feed(prev, _st({"stall_critical": True}))   # 升级
    assert ev2 is not None and ev2.level == "critical" and ev2.edge == "enter"
    assert d.feed(prev, _st({"stall_critical": True})) is None  # 升级后不重复


def test_spawn_detector():
    det = SpawnDetector()
    prev = C.BattleState(connected=True, in_battle=False, vehicle_valid=False)
    cur = C.BattleState(
        connected=True,
        in_battle=True,
        vehicle_valid=True,
        vehicle_type="bf-109f-4",
        domain="air",
        domain_label="空军",
    )
    ev = det.feed(prev, cur)
    assert ev is not None and ev.event_id == "spawn" and ev.payload.get("vehicle_type") == "bf-109f-4"
    assert ev.payload.get("domain") == "air"
    assert ev.payload.get("domain_label") == "空军"
    assert det.feed(cur, cur) is None  # 已存活不再触发


def test_spawn_not_fired_after_telemetry_blip():
    det = SpawnDetector()
    blip = C.BattleState(connected=False)  # 遥测瞬断
    cur = C.BattleState(connected=True, in_battle=True, vehicle_valid=True)
    assert det.feed(blip, cur) is None  # prev 断连 → 不误判重生


@pytest.mark.parametrize(
    "mission_status,result_kind",
    [
        ("win", "victory"),
        ("defeat", "defeat"),
        ("left", "neutral"),
    ],
)
def test_battle_end_detector_classifies_result(mission_status, result_kind):
    det = BattleEndDetector()
    prev = C.BattleState(in_battle=True, mission_status="running")
    cur = C.BattleState(
        in_battle=False,
        mission_status=mission_status,
        domain="air",
        timestamp=123.0,
        combat={"my": {"kills": 2, "deaths": 1}},
    )

    ev = det.feed(prev, cur)

    assert ev is not None and ev.event_id == "battle_end"
    assert ev.payload == {
        "result": f"{mission_status}, K2/D1",
        "result_kind": result_kind,
        "domain": "air",
    }


def test_death_detector():
    det = DeathDetector()
    prev = C.BattleState(in_battle=True, vehicle_valid=True)
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        combat={"feed": [{"id": 3, "is_my_death": True, "killer": "Opponent", "action": "crashed"}]},
    )
    ev = det.feed(prev, cur)
    assert ev is not None and ev.event_id == "you_died" and ev.level == "critical"


def test_death_detector_emits_when_ownership_arrives_late_for_seen_id():
    det = DeathDetector()
    prev = C.BattleState(in_battle=True, vehicle_valid=True)
    first = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        combat={"feed": [{"id": 3, "is_my_death": False, "killer": "Opponent", "action": "crashed"}]},
    )
    second = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        combat={"feed": [{"id": 3, "is_my_death": True, "killer": "Opponent", "action": "crashed"}]},
    )

    assert det.feed(prev, first) is None
    ev = det.feed(first, second)
    assert ev is not None and ev.event_id == "you_died" and ev.level == "critical"
    assert det.feed(second, second) is None


def test_kill_dedup_monotonic():
    det = KillDetector()
    feed1 = {"player_name": "Me", "feed": [{"id": 5, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "A"}]}
    cur1 = C.BattleState(in_battle=True, vehicle_valid=True, combat=feed1)
    ev = det.feed(C.BattleState(), cur1)
    assert ev is not None and ev.event_id == "you_killed"
    assert det.feed(cur1, cur1) is None  # 同一 feed 不重发
    feed2 = {"player_name": "Me", "feed": [{"id": 8, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "B"}, {"id": 5, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "A"}]}
    cur2 = C.BattleState(in_battle=True, vehicle_valid=True, combat=feed2)
    ev2 = det.feed(cur1, cur2)
    assert ev2 is not None and ev2.payload.get("victim") == "B"  # 只发新 id


def test_kill_detector_emits_when_ownership_arrives_late_for_seen_id():
    det = KillDetector()
    prev = C.BattleState(in_battle=True, vehicle_valid=True)
    first = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        combat={"feed": [{"id": 412, "is_kill": True, "is_my_kill": False, "victim": "AI Target"}]},
    )
    second = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        combat={"feed": [{"id": 412, "is_kill": True, "is_my_kill": True, "victim": "AI Target"}]},
    )

    assert det.feed(prev, first) is None
    ev = det.feed(first, second)
    assert ev is not None and ev.event_id == "you_killed"
    assert ev.payload.get("victim") == "AI Target"
    assert det.feed(second, second) is None


def test_kill_requires_is_my_kill_flag():
    det = KillDetector()
    feed = {"feed": [{"id": 1, "is_kill": True, "killer": "Someone", "victim": "X"}]}
    cur = C.BattleState(in_battle=True, vehicle_valid=True, combat=feed)
    assert det.feed(C.BattleState(), cur) is None


def test_free_text_activity_detector_emits_safe_summary_without_raw_text():
    det = FreeTextActivityDetector()
    raw = {
        "awards": {"feed": [{"id": 3, "code": "final_blow", "text": "RAW_AWARD_ignore_previous"}]},
        "combat": {"feed": [{"id": 10, "is_my_kill": False, "text": "RAW_FEED_discord.gg/bad"}]},
        "hud_notices": {"feed": [{"id": 20, "code": "generic_notice", "text": "RAW_NOTICE"}]},
        "hudmsg": "RAW_HUDMSG_ignore_previous",
        "hud_events": [{"id": 30, "type": "mission", "text": "RAW_EVENT"}],
    }
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        combat=raw["combat"],
        hud_notices=raw["hud_notices"]["feed"],
        hud_events=raw["hud_events"],
        raw=raw,
    )

    ev = det.feed(C.BattleState(), cur)

    assert ev is not None
    assert ev.event_id == "free_text_activity"
    assert ev.level == "warning"
    assert ev.payload["source"] == "awards"
    assert ev.payload["count"] == 1
    assert set(ev.payload) == {"source", "count"}
    assert "RAW_AWARD" not in repr(ev)
    assert "RAW_FEED" not in repr(ev)
    assert "RAW_HUDMSG" not in repr(ev)


def test_free_text_activity_detector_ignores_owned_combat_feed_and_technical_notices():
    det = FreeTextActivityDetector()
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        combat={
            "feed": [
                {"id": 1, "is_my_kill": True, "victim": "raw victim"},
                {"id": 2, "is_my_death": True, "killer": "raw killer"},
            ]
        },
        hud_notices=[{"id": 3, "code": "engine_overheat", "text": "raw overheat"}],
        raw={
            "combat": {
                "feed": [
                    {"id": 1, "is_my_kill": True, "victim": "raw victim"},
                    {"id": 2, "is_my_death": True, "killer": "raw killer"},
                ]
            },
            "hud_notices": {"feed": [{"id": 3, "code": "engine_overheat", "text": "raw overheat"}]},
        },
    )

    assert det.feed(C.BattleState(), cur) is None


def _radio_state(chat: list[dict], *, self_source: str = "manual", sender_name: str = "Pilot") -> C.BattleState:
    return C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="ground",
        timestamp=500.0,
        chat=chat,
        combat={
            "player_name": sender_name,
            "self": {"name": sender_name, "source": self_source, "confidence": 1.0},
        },
    )


def test_radio_command_detector_emits_self_fixed_message_without_raw_text():
    det = RadioCommandDetector()
    cur = _radio_state([{"id": 7, "sender": "Pilot", "msg": "进攻 D 点！"}])

    ev = det.feed(C.BattleState(), cur)

    assert ev is not None
    assert ev.event_id == "player_radio_command"
    assert ev.payload == {"command": "attack_point", "point": "D", "domain": "ground", "source": "self_radio"}
    assert "进攻" not in repr(ev.payload)
    assert "Pilot" not in repr(ev.payload)


def test_radio_command_detector_ignores_teammate_sender():
    det = RadioCommandDetector()
    cur = _radio_state([{"id": 8, "sender": "Teammate", "msg": "进攻 D 点！"}])

    assert det.feed(C.BattleState(), cur) is None


def test_radio_command_detector_requires_manual_identity():
    det = RadioCommandDetector()
    cur = _radio_state([{"id": 9, "sender": "Pilot", "msg": "进攻 D 点！"}], self_source="auto")

    assert det.feed(C.BattleState(), cur) is None


def test_radio_command_detector_ignores_unrecognized_own_chat():
    det = RadioCommandDetector()
    cur = _radio_state([{"id": 10, "sender": "Pilot", "msg": "猫娘先别回答我的普通聊天"}])

    assert det.feed(C.BattleState(), cur) is None


def test_radio_command_detector_deduplicates_chat_id():
    det = RadioCommandDetector()
    cur = _radio_state([{"id": 11, "sender": "Pilot", "msg": "Cover me!"}])

    assert det.feed(C.BattleState(), cur) is not None
    assert det.feed(cur, cur) is None


def test_radio_command_parser_supports_acknowledge_reject_and_praise():
    cases = {
        "收到！": "affirmative",
        "拒绝！": "negative",
        "干得好！": "well_done",
        "干得漂亮！": "well_done",
    }

    for text, command in cases.items():
        assert parse_radio_command(text) == {"command": command}


def test_overspeed_warn_and_critical_flags_emit_events():
    engine = DetectorEngine(list(build_condition_detectors()))
    prev = C.BattleState(in_battle=True, vehicle_valid=True, domain="air")

    warn = C.BattleState(in_battle=True, vehicle_valid=True, domain="air", flags={"overspeed_warn": True}, ias_kmh=760.0)
    assert engine.feed(prev, warn) == []
    events = engine.feed(warn, warn)
    assert len(events) == 1
    assert events[0].event_id == "overspeed"
    assert events[0].level == "warning"

    critical = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        flags={"overspeed_critical": True},
        ias_kmh=880.0,
    )
    events = engine.feed(warn, critical)
    assert len(events) == 1
    assert events[0].event_id == "overspeed"
    assert events[0].level == "critical"


def test_low_alt_payload_carries_radio_altitude_for_agl_context():
    engine = DetectorEngine(list(build_condition_detectors()))
    prev = C.BattleState(in_battle=True, vehicle_valid=True, domain="air")

    low_1 = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        flags={"altitude_critical": True},
        altitude_m=1067.0,
        radio_altitude_m=8.0,
        climb_ms=-3.0,
    )
    low_2 = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        flags={"altitude_critical": True},
        altitude_m=1060.0,
        radio_altitude_m=7.0,
        climb_ms=-4.0,
    )

    assert engine.feed(prev, low_1) == []
    events = engine.feed(low_1, low_2)

    assert len(events) == 1
    assert events[0].event_id == "low_alt_danger"
    assert events[0].payload["radio_altitude_m"] == 7.0
    assert events[0].payload["altitude_m"] == 1060.0


def test_aoa_flags_emit_high_aoa_without_reusing_stall_risk():
    engine = DetectorEngine(list(build_condition_detectors()))
    prev = C.BattleState(in_battle=True, vehicle_valid=True, domain="air")
    high_aoa = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        flags={"aoa_high": True},
        aoa_deg=19.0,
    )

    events = engine.feed(prev, high_aoa)
    assert [e.event_id for e in events] == ["high_aoa"]
    assert engine.feed(high_aoa, high_aoa) == []


def test_fixed_wing_safety_flags_are_suppressed_outside_air_domain():
    air_only_flags = {
        "stall_critical": True,
        "aoa_critical": True,
        "over_g_critical": True,
        "altitude_critical": True,
        "overspeed_critical": True,
        "fuel_critical": True,
    }

    for domain in ("ground", "naval", "heli", ""):
        engine = DetectorEngine(list(build_condition_detectors()))
        state = C.BattleState(
            in_battle=True,
            vehicle_valid=True,
            domain=domain,
            flags=air_only_flags,
            ias_kmh=1200.0,
            aoa_deg=25.0,
            g_now=12.0,
            fuel_fraction=0.02,
            altitude_m=20.0,
            radio_altitude_m=5.0,
        )

        assert engine.feed(C.BattleState(domain=domain), state) == []
        assert engine.feed(state, state) == []


def test_ground_status_flags_emit_only_real_laser_warning_for_ground_domain():
    engine = DetectorEngine(list(build_condition_detectors()))
    prev = C.BattleState(in_battle=True, vehicle_valid=True, domain="ground")
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="ground",
        flags={
            "laser_warning": True,
            "crew_critical": True,
            "gunner_disabled": True,
            "driver_disabled": True,
            "ammo_empty": True,
        },
        crew_current=1,
        crew_total=4,
        gunner_state=0,
        driver_state=0,
        ammo_first_stage=0,
    )

    events = engine.feed(prev, cur)
    assert [event.event_id for event in events] == ["ground_laser_warning"]
    assert events[0].payload == {"domain": "ground"}
    assert engine.feed(cur, cur) == []


def test_ground_status_flags_are_suppressed_outside_ground_domain():
    flags = {
        "laser_warning": True,
        "crew_critical": True,
        "gunner_disabled": True,
        "driver_disabled": True,
        "ammo_empty": True,
        "ammo_low": True,
    }

    for domain in ("air", "heli", "naval", ""):
        engine = DetectorEngine(list(build_condition_detectors()))
        cur = C.BattleState(in_battle=True, vehicle_valid=True, domain=domain, flags=flags)

        assert engine.feed(C.BattleState(domain=domain), cur) == []
        assert engine.feed(cur, cur) == []


def test_kill_detector_uses_is_my_kill_flag():
    det = KillDetector()
    feed = {
        "player_name": "Me",
        "feed": [{"id": 10, "is_kill": True, "is_my_kill": True, "killer": "OtherName", "victim": "Target"}],
    }
    cur = C.BattleState(in_battle=True, vehicle_valid=True, combat=feed)
    ev = det.feed(C.BattleState(), cur)
    assert ev is not None and ev.event_id == "you_killed"
    assert ev.payload.get("victim") == "Target"


def test_kill_detector_carries_domain_for_output_wording():
    det = KillDetector()
    feed = {"feed": [{"id": 12, "is_my_kill": True, "victim": "Target", "victim_vehicle": "Tank"}]}
    cur = C.BattleState(in_battle=True, vehicle_valid=True, domain="ground", combat=feed)

    ev = det.feed(C.BattleState(), cur)

    assert ev is not None and ev.payload.get("domain") == "ground"


def test_death_detector_uses_is_my_death_flag():
    det = DeathDetector()
    feed = {
        "player_name": "Me",
        "feed": [
            {
                "id": 20,
                "is_kill": True,
                "is_my_death": True,
                "killer": "Opponent",
                "victim": "Me",
                "action": "shot_down",
            }
        ],
    }
    cur = C.BattleState(in_battle=True, vehicle_valid=True, combat=feed)
    ev = det.feed(C.BattleState(in_battle=True, vehicle_valid=True), cur)
    assert ev is not None and ev.event_id == "you_died"
    assert ev.payload.get("killer_name") == "Opponent"
    assert ev.payload.get("cause") == "shot_down"


def test_death_detector_carries_domain_for_output_wording():
    det = DeathDetector()
    feed = {"feed": [{"id": 22, "is_my_death": True, "killer": "Opponent", "action": "destroyed"}]}
    cur = C.BattleState(in_battle=True, vehicle_valid=False, domain="ground", combat=feed)

    ev = det.feed(C.BattleState(in_battle=True, vehicle_valid=True), cur)

    assert ev is not None and ev.payload.get("domain") == "ground"


def test_vehicle_valid_drop_is_not_death_signal():
    det = DeathDetector()
    prev = C.BattleState(in_battle=True, vehicle_valid=True)
    cur = C.BattleState(in_battle=True, vehicle_valid=False, combat={"feed": []})
    assert det.feed(prev, cur) is None


def test_replay_telemetry_suppresses_detector_events():
    payload = {
        "state": "in_battle",
        "in_battle": True,
        "replay": True,
        "timestamp": 123.0,
        "combat": {"feed": [{"id": 1, "is_my_death": True, "killer": "Opponent"}]},
        "processed": {"flags": {"overspeed_critical": True}},
    }
    prev = C.BattleState(connected=True, in_battle=True, vehicle_valid=True)
    cur = parse_telemetry(payload)
    engine = DetectorEngine(list(build_condition_detectors()) + [DeathDetector()])
    assert engine.feed(prev, cur) == []


def test_hud_notice_overheat_emits_safe_overheat_event_once():
    det = HudNoticeDetector()
    prev = C.BattleState(in_battle=True, vehicle_valid=True)
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        timestamp=200.0,
        hud_notices=[
            {
                "id": 7,
                "code": "engine_overheat",
                "severity": "warning",
                "text": "水温过高 raw text must not enter payload",
            }
        ],
    )
    ev = det.feed(prev, cur)
    assert ev is not None
    assert ev.event_id == "overheat"
    assert ev.level == "warning"
    assert ev.payload == {"source": "hud_notice", "notice_code": "engine_overheat"}
    assert det.feed(cur, cur) is None


def test_detector_engine_reset_rearms_same_id_kill_and_hud_notice_for_a_new_battle():
    alive = {
        "connected": True,
        "conn_state": "in_battle",
        "in_battle": True,
        "vehicle_valid": True,
        "domain": "air",
    }
    empty = C.BattleState(**alive)
    kill = C.BattleState(
        **alive,
        combat={"feed": [{"id": 1, "is_my_kill": True, "victim": "Target"}]},
    )
    notice = C.BattleState(
        **alive,
        hud_notices=[{"id": 1, "code": "engine_overheat", "level": "warning"}],
    )
    engine = DetectorEngine([KillDetector(), HudNoticeDetector()])

    assert [event.event_id for event in engine.feed(empty, kill)] == ["you_killed"]
    assert [event.event_id for event in engine.feed(kill, notice)] == ["overheat"]

    engine.reset()

    assert [event.event_id for event in engine.feed(empty, kill)] == ["you_killed"]
    assert [event.event_id for event in engine.feed(kill, notice)] == ["overheat"]


def test_detector_engine_reset_rearms_same_id_death_for_a_new_battle():
    alive = C.BattleState(
        connected=True,
        conn_state="in_battle",
        in_battle=True,
        vehicle_valid=True,
        domain="air",
    )
    death_feed = C.BattleState(
        connected=True,
        conn_state="in_battle",
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        combat={"feed": [{"id": 1, "is_my_death": True, "action": "shot_down"}]},
    )
    engine = DetectorEngine([DeathDetector()])

    assert [event.event_id for event in engine.feed(alive, death_feed)] == ["you_died"]

    engine.reset()

    assert [event.event_id for event in engine.feed(alive, death_feed)] == ["you_died"]


def test_hud_notice_uses_data_layer_level_field():
    det = HudNoticeDetector()
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        timestamp=201.0,
        hud_notices=[{"id": 10, "code": "engine_overheat", "level": "critical", "message": "engine disabled"}],
    )

    ev = det.feed(C.BattleState(in_battle=True, vehicle_valid=True), cur)

    assert ev is not None
    assert ev.event_id == "overheat"
    assert ev.level == "critical"


def test_hud_notice_powertrain_failure_is_not_promoted_to_speech_event_yet():
    det = HudNoticeDetector()
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        hud_notices=[{"id": 8, "code": "powertrain_failure", "severity": "critical", "text": "动力系统故障"}],
    )
    assert det.feed(C.BattleState(in_battle=True, vehicle_valid=True), cur) is None


def test_dead_state_suppresses_overheat_candidates():
    engine = DetectorEngine(list(build_condition_detectors()) + [HudNoticeDetector()])
    prev = C.BattleState(in_battle=True, vehicle_valid=True)
    dead = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        dead=True,
        flags={"engine_overheat_critical": True},
        hud_notices=[{"id": 11, "code": "engine_overheat", "severity": "critical", "text": "raw overheat"}],
    )

    assert engine.feed(prev, dead) == []
    assert engine.feed(dead, dead) == []

    persistent_engine = DetectorEngine(
        [
            FreeTextActivityDetector(),
            HudNoticeDetector(),
            ProximityDetector(),
            RadioCommandDetector(),
        ]
    )
    persistent_data = {
        "in_battle": True,
        "vehicle_valid": True,
        "domain": "ground",
        "combat": {
            "player_name": "Pilot",
            "self": {"name": "Pilot", "source": "manual", "confidence": 1.0},
        },
        "raw": {"awards": {"feed": [{"id": 20, "code": "final_blow"}]}},
        "hud_notices": [{"id": 21, "code": "engine_overheat", "level": "critical"}],
        "proximity_events": [{"id": 22, "kind": "enter", "distance_m": 500}],
        "chat": [{"id": 23, "sender": "Pilot", "msg": "进攻 D 点！"}],
    }
    persistent_dead = C.BattleState(**persistent_data, dead=True)
    assert persistent_engine.feed(prev, persistent_dead) == []

    respawned = C.BattleState(**persistent_data)
    assert persistent_engine.feed(persistent_dead, respawned) == []


def test_dead_state_allows_death_event_and_blocks_overheat_same_tick():
    engine = DetectorEngine(list(build_condition_detectors()) + [DeathDetector(), HudNoticeDetector()])
    prev = C.BattleState(in_battle=True, vehicle_valid=True)
    dead = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        dead=True,
        flags={"engine_overheat_critical": True},
        combat={"feed": [{"id": 30, "is_my_death": True, "killer": "Opponent", "action": "crashed"}]},
        hud_notices=[{"id": 12, "code": "engine_overheat", "severity": "critical", "text": "raw overheat"}],
    )

    events = engine.feed(prev, dead)

    assert [ev.event_id for ev in events] == ["you_died"]
    assert events[0].payload.get("cause") == "crashed"


def test_spawn_detector_ignores_dead_state_with_stale_vehicle_valid():
    det = SpawnDetector()
    prev = C.BattleState(connected=True, in_battle=True, vehicle_valid=False, dead=True)
    cur = C.BattleState(connected=True, in_battle=True, vehicle_valid=True, dead=True, vehicle_type="bf-109f-4")

    assert det.feed(prev, cur) is None


def test_hud_notice_overheat_requires_live_vehicle():
    det = HudNoticeDetector()
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=False,
        hud_notices=[{"id": 9, "code": "oil_overheat", "severity": "warning", "text": "油温过高"}],
    )
    assert det.feed(C.BattleState(in_battle=True, vehicle_valid=True), cur) is None


def test_proximity_detector_emits_enemy_nearby_once_by_id():
    det = ProximityDetector()
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        proximity_events=[
            {"id": 1, "kind": "enter", "type": "tank", "category": "enemy_ground", "distance_m": 950, "compass": "E"}
        ],
    )

    ev = det.feed(C.BattleState(), cur)

    assert ev is not None and ev.event_id == "enemy_nearby"
    assert ev.payload == {
        "kind": "enter",
        "target_type": "tank",
        "category": "enemy_ground",
        "is_air": False,
        "distance_m": 950.0,
        "compass": "E",
    }
    assert det.feed(cur, cur) is None


def test_proximity_detector_promotes_air_and_rear_threats():
    det = ProximityDetector()
    air = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        proximity_events=[{"id": 2, "is_air": True, "distance_m": 1800, "clock": 2}],
    )
    rear = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        proximity_events=[
            {"id": 2, "is_air": True, "distance_m": 1800, "clock": 2},
            {"id": 3, "is_air": True, "distance_m": 700, "clock": 6, "text": "unsafe raw proximity text"},
        ],
    )

    air_event = det.feed(C.BattleState(), air)
    rear_event = det.feed(air, rear)

    assert air_event is not None and air_event.event_id == "air_threat_nearby"
    assert rear_event is not None and rear_event.event_id == "enemy_on_six"
    assert "text" not in rear_event.payload


def test_proximity_detector_upgrades_repeated_close_rear_threat_to_tailing_risk():
    det = ProximityDetector(tail_window_seconds=8, tail_confirm_events=2, tail_distance_m=900)
    first = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=100.0,
        proximity_events=[{"id": 10, "is_air": True, "distance_m": 850, "clock": 6}],
    )
    second = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=104.0,
        proximity_events=[
            {"id": 10, "is_air": True, "distance_m": 850, "clock": 6},
            {"id": 11, "is_air": True, "distance_m": 700, "clock": 6, "raw_text": "RAW tail text"},
        ],
    )

    first_event = det.feed(C.BattleState(), first)
    second_event = det.feed(first, second)

    assert first_event is not None and first_event.event_id == "enemy_on_six"
    assert second_event is not None and second_event.event_id == "tailing_risk"
    assert second_event.payload["distance_m"] == 700.0
    assert "raw_text" not in second_event.payload


def test_proximity_detector_does_not_upgrade_distant_or_stale_rear_hits():
    det = ProximityDetector(tail_window_seconds=3, tail_confirm_events=2, tail_distance_m=900)
    distant = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=100.0,
        proximity_events=[{"id": 20, "is_air": True, "distance_m": 1500, "clock": 6}],
    )
    stale = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=106.0,
        proximity_events=[
            {"id": 20, "is_air": True, "distance_m": 1500, "clock": 6},
            {"id": 21, "is_air": True, "distance_m": 700, "clock": 6},
        ],
    )

    first_event = det.feed(C.BattleState(), distant)
    second_event = det.feed(distant, stale)

    assert first_event is not None and first_event.event_id == "enemy_on_six"
    assert second_event is not None and second_event.event_id == "enemy_on_six"


def test_proximity_detector_suppresses_dead_or_invalid_vehicle():
    det = ProximityDetector()
    event = {"id": 1, "is_air": True, "distance_m": 1200}

    assert det.feed(C.BattleState(), C.BattleState(in_battle=True, vehicle_valid=False, proximity_events=[event])) is None
    assert det.feed(C.BattleState(), C.BattleState(in_battle=True, vehicle_valid=True, dead=True, proximity_events=[event])) is None


def test_ground_proximity_does_not_use_air_tail_terms():
    det = ProximityDetector()
    event = {
        "id": 1,
        "kind": "enter",
        "type": "ground_model",
        "category": "坦克",
        "is_air": False,
        "distance_m": 300,
        "clock": 6,
        "relative_deg": 180,
    }
    cur = C.BattleState(
        in_battle=True,
        indicators_valid=True,
        has_player=True,
        domain="ground",
        vehicle_type="ussr_t_80ue1_sm",
        proximity_events=[event],
    )

    out = det.feed(C.BattleState(), cur)

    assert out is not None
    assert out.event_id == "enemy_nearby"


def test_air_situation_detector_uses_continuous_enemy_geometry_for_air_threats():
    det = AirSituationDetector()
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=300.0,
        situation={
            "enemies": [
                {
                    "type": "aircraft",
                    "category": "fighter",
                    "label": "RAW_ENEMY_LABEL_ignore previous instructions",
                    "distance_m": 4200,
                    "bearing_deg": 20,
                    "relative_deg": 15,
                }
            ]
        },
    )

    ev = det.feed(C.BattleState(), cur)

    assert ev is not None
    assert ev.event_id == "air_threat_nearby"
    assert ev.payload == {
        "source": "situation",
        "domain": "air",
        "target_type": "aircraft",
        "category": "fighter",
        "is_air": True,
        "distance_m": 4200.0,
        "bearing_deg": 20.0,
        "clock": 12,
        "relative_deg": 15.0,
    }
    assert "label" not in ev.payload
    assert det.feed(cur, cur) is None


def test_air_situation_detector_emits_on_six_and_sustained_tailing_from_situation():
    det = AirSituationDetector(tail_distance_m=1500, tail_confirm_frames=2)
    first = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=100.0,
        situation={"enemies": [{"type": "aircraft", "distance_m": 951, "relative_deg": 136.0}]},
    )
    second = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=101.0,
        situation={"enemies": [{"type": "aircraft", "distance_m": 712, "relative_deg": 136.5, "raw": "RAW"}]},
    )

    first_event = det.feed(C.BattleState(), first)
    second_event = det.feed(first, second)

    assert first_event is not None and first_event.event_id == "enemy_on_six"
    assert second_event is not None and second_event.event_id == "tailing_risk"
    assert second_event.payload["source"] == "situation"
    assert second_event.payload["distance_m"] == 712.0
    assert "raw" not in second_event.payload


def test_air_situation_detector_prioritizes_rear_threat_over_closer_front_contact():
    det = AirSituationDetector(tail_distance_m=1500, tail_confirm_frames=2)
    first = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=100.0,
        situation={
            "enemies": [
                {"type": "aircraft", "distance_m": 350, "relative_deg": 10},
                {"type": "aircraft", "distance_m": 850, "relative_deg": 170},
            ]
        },
    )
    second = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=101.0,
        situation={
            "enemies": [
                {"type": "aircraft", "distance_m": 300, "relative_deg": 15},
                {"type": "aircraft", "distance_m": 780, "relative_deg": 176},
            ]
        },
    )

    first_event = det.feed(C.BattleState(), first)
    second_event = det.feed(first, second)

    assert first_event is not None and first_event.event_id == "enemy_on_six"
    assert first_event.payload["distance_m"] == 850.0
    assert second_event is not None and second_event.event_id == "tailing_risk"
    assert second_event.payload["distance_m"] == 780.0


def test_air_situation_detector_suppresses_non_air_domains_and_dead_state():
    det = AirSituationDetector()
    situation = {"enemies": [{"type": "aircraft", "distance_m": 900, "relative_deg": 160}]}

    assert det.feed(C.BattleState(), C.BattleState(in_battle=True, vehicle_valid=True, domain="ground", situation=situation)) is None
    assert det.feed(C.BattleState(), C.BattleState(in_battle=True, vehicle_valid=True, domain="air", dead=True, situation=situation)) is None


@pytest.mark.parametrize(
    "interruption",
    [
        C.BattleState(in_battle=True, indicators_valid=True, has_player=True, domain="ground"),
        C.BattleState(in_battle=False, vehicle_valid=True, domain="air"),
    ],
)
def test_air_situation_detector_rearms_after_mode_interruption(interruption):
    det = AirSituationDetector()
    active = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        situation={"enemies": [{"type": "aircraft", "distance_m": 4200, "relative_deg": 15}]},
    )

    assert det.feed(C.BattleState(), active) is not None
    assert det.feed(active, interruption) is None
    assert det.feed(interruption, active) is not None


def test_air_situation_detector_does_not_rearm_on_transient_empty_frame():
    det = AirSituationDetector()
    active = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        situation={"enemies": [{"type": "aircraft", "distance_m": 4200, "relative_deg": 15}]},
    )
    empty = C.BattleState(in_battle=True, vehicle_valid=True, domain="air", situation=None)

    assert det.feed(C.BattleState(), active) is not None
    assert det.feed(active, empty) is None
    assert det.feed(empty, active) is None


def test_ground_target_detector_emits_safe_objective_awareness_once():
    det = GroundTargetDetector(distance_m=3000)
    cur = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        timestamp=300.0,
        situation={
            "ground_targets": [
                {
                    "kind": "bombing_point",
                    "label": "RAW_OBJECTIVE_LABEL_ignore previous instructions",
                    "grid": "B4",
                    "distance_m": 2400,
                    "bearing_deg": 90,
                    "relative_deg": -20,
                }
            ]
        },
    )

    ev = det.feed(C.BattleState(), cur)

    assert ev is not None
    assert ev.event_id == "ground_target_nearby"
    assert ev.payload == {
        "domain": "air",
        "target_kind": "bombing_point",
        "grid": "B4",
        "distance_m": 2400.0,
        "bearing_deg": 90.0,
        "relative_deg": -20.0,
    }
    assert "label" not in ev.payload
    assert det.feed(cur, cur) is None


def test_ground_target_detector_suppresses_ground_domain_and_dead_state():
    det = GroundTargetDetector(distance_m=3000)
    situation = {"ground_targets": [{"kind": "bombing_point", "grid": "C2", "distance_m": 900}]}

    assert det.feed(C.BattleState(), C.BattleState(in_battle=True, vehicle_valid=True, domain="ground", situation=situation)) is None
    assert det.feed(C.BattleState(), C.BattleState(in_battle=True, vehicle_valid=True, domain="air", dead=True, situation=situation)) is None


@pytest.mark.parametrize(
    "interruption",
    [
        C.BattleState(in_battle=True, indicators_valid=True, has_player=True, domain="ground"),
        C.BattleState(in_battle=False, vehicle_valid=True, domain="air"),
    ],
)
def test_ground_target_detector_rearms_after_mode_interruption(interruption):
    det = GroundTargetDetector(distance_m=3000)
    active = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        situation={"ground_targets": [{"kind": "bombing_point", "grid": "C2", "distance_m": 900}]},
    )

    assert det.feed(C.BattleState(), active) is not None
    assert det.feed(active, interruption) is None
    assert det.feed(interruption, active) is not None


def test_ground_target_detector_does_not_rearm_on_transient_empty_frame():
    det = GroundTargetDetector(distance_m=3000)
    active = C.BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        situation={"ground_targets": [{"kind": "bombing_point", "grid": "C2", "distance_m": 900}]},
    )
    empty = C.BattleState(in_battle=True, vehicle_valid=True, domain="air", situation=None)

    assert det.feed(C.BattleState(), active) is not None
    assert det.feed(active, empty) is None
    assert det.feed(empty, active) is None


def test_engine_does_not_replay_battle_kills_after_same_battle_respawn():
    """同局阵亡→重生不得重播整局旧击杀。

    数据层 combat.feed 是整局持久的（只在换局/HUD drain 时清空），阵亡期间若重置
    KillDetector 的 id 游标，重生后 feed 里所有历史 is_my_kill 都会被当成新击杀。
    """
    base = dict(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, battle_id="B1")
    feed = {"feed": [{"id": i, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": f"V{i}"} for i in (1, 2, 3)]}
    engine = DetectorEngine([KillDetector()])

    before = C.BattleState(**base, combat={"feed": []})
    scored = C.BattleState(**base, combat=feed)
    assert [e.event_id for e in engine.feed(before, scored)] == ["you_killed"]

    dead = C.BattleState(**base, combat=feed, dead=True, dead_source="hud")
    for _ in range(3):
        assert engine.feed(scored, dead) == []

    respawned = C.BattleState(**base, combat=feed, dead=False)
    assert engine.feed(dead, respawned) == []


def test_engine_still_emits_kills_earned_after_respawn():
    """重生后的新击杀仍要正常播报（consume 策略不能把真实新事件也吃掉）。"""
    base = dict(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, battle_id="B1")
    old_feed = {"feed": [{"id": 1, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "V1"}]}
    engine = DetectorEngine([KillDetector()])

    scored = C.BattleState(**base, combat=old_feed)
    assert [e.event_id for e in engine.feed(C.BattleState(**base, combat={"feed": []}), scored)] == ["you_killed"]

    dead = C.BattleState(**base, combat=old_feed, dead=True, dead_source="hud")
    engine.feed(scored, dead)

    new_feed = {"feed": old_feed["feed"] + [{"id": 9, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "V9"}]}
    respawned = C.BattleState(**base, combat=new_feed, dead=False)
    events = engine.feed(dead, respawned)
    assert [e.event_id for e in events] == ["you_killed"]
    assert events[0].payload.get("kill_count") == 1
    assert events[0].payload.get("victim") == "V9"


def test_engine_emits_kills_scored_while_dead_once_for_trade_handling():
    """阵亡期间到账的战果交给 Arbiter 判定同归于尽，重生后不补播。"""
    base = dict(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, battle_id="B1")
    engine = DetectorEngine([KillDetector()])
    empty = C.BattleState(**base, combat={"feed": []})

    dead_feed = {"feed": [{"id": 4, "is_kill": True, "is_my_kill": True, "killer": "Me", "victim": "V4"}]}
    dead = C.BattleState(**base, combat=dead_feed, dead=True, dead_source="hud")
    events = engine.feed(empty, dead)
    assert [event.event_id for event in events] == ["you_killed"]
    assert events[0].payload.get("victim") == "V4"

    respawned = C.BattleState(**base, combat=dead_feed, dead=False)
    assert engine.feed(dead, respawned) == []


def _flagged(ts, **flags):
    return C.BattleState(domain="air", timestamp=ts, flags=dict(flags))


def test_critical_condition_reemits_on_heartbeat_while_sustained():
    """危急持续期需要低频重发：否则被抢占冷却压掉的危急永远等不到第二次机会。"""
    d = ConditionDetector(
        "stall_risk", [("stall_warning", "stall_critical")],
        confirm_enter=1, confirm_exit=2, critical_heartbeat_seconds=8.0,
    )
    prev = C.BattleState(domain="air")

    first = d.feed(prev, _flagged(1000.0, stall_critical=True))
    assert first is not None and first.level == "critical"

    assert d.feed(prev, _flagged(1004.0, stall_critical=True)) is None      # 未到心跳间隔
    beat = d.feed(prev, _flagged(1008.0, stall_critical=True))
    assert beat is not None and beat.edge == "enter" and beat.level == "critical"
    assert beat.ts == 1008.0                                               # ts 是新的，不会被下游判过期

    assert d.feed(prev, _flagged(1012.0, stall_critical=True)) is None     # 心跳从上次重发起算
    assert d.feed(prev, _flagged(1016.0, stall_critical=True)) is not None


def test_warning_level_condition_does_not_heartbeat():
    """只有 critical 才心跳；warning 持续期保持安静，不唠叨。"""
    d = ConditionDetector(
        "stall_risk", [("stall_warning", "stall_critical")],
        confirm_enter=1, confirm_exit=2, critical_heartbeat_seconds=8.0,
    )
    prev = C.BattleState(domain="air")

    assert d.feed(prev, _flagged(1000.0, stall_warning=True)) is not None
    for ts in (1008.0, 1020.0, 1040.0):
        assert d.feed(prev, _flagged(ts, stall_warning=True)) is None


def test_condition_heartbeat_stops_after_condition_clears():
    d = ConditionDetector(
        "stall_risk", [("stall_warning", "stall_critical")],
        confirm_enter=1, confirm_exit=2, critical_heartbeat_seconds=8.0,
    )
    prev = C.BattleState(domain="air")
    assert d.feed(prev, _flagged(1000.0, stall_critical=True)) is not None

    clear = C.BattleState(domain="air", timestamp=1002.0)
    assert d.feed(prev, clear) is None
    assert d.feed(prev, C.BattleState(domain="air", timestamp=1003.0)) is None   # confirm_exit 满 → ARMED
    assert d.feed(prev, C.BattleState(domain="air", timestamp=1030.0)) is None   # 已解除，不再心跳


def test_condition_heartbeat_is_off_by_default():
    d = ConditionDetector("overheat", [("engine_overheat", "engine_overheat_critical")], confirm_enter=1)
    prev = C.BattleState(domain="air")
    assert d.feed(prev, _flagged(1000.0, engine_overheat_critical=True)) is not None
    assert d.feed(prev, _flagged(1100.0, engine_overheat_critical=True)) is None


def test_once_per_battle_condition_does_not_rearm_on_flicker():
    """cooldown<0 声明"每局一次"，电平抖动不该反复重报。

    实测样本里 low_fuel 曾在 13 秒内报三次：flag 在阈值附近抖，检测器每次
    confirm_exit 满就 re-arm，而 Arbiter 只对 cd>0 查冷却，于是无人拦。
    """
    d = ConditionDetector(
        "low_fuel", [("fuel_low", "fuel_critical")],
        confirm_enter=1, confirm_exit=2, once_per_battle=True,
    )
    prev = C.BattleState()
    low = C.BattleState(flags={"fuel_low": True})
    clear = C.BattleState()

    assert d.feed(prev, low) is not None                 # 首次报出
    d.mark_delivered()
    assert d.feed(prev, clear) is None
    assert d.feed(prev, clear) is None                   # confirm_exit 满 → SPENT
    assert d.feed(prev, low) is None                     # 再次跌破阈值也不重报
    assert d.feed(prev, low) is None


def test_once_per_battle_rearms_after_engine_reset():
    """换局(engine.reset)后应重新武装。"""
    d = ConditionDetector(
        "low_fuel", [("fuel_low", "fuel_critical")],
        confirm_enter=1, confirm_exit=2, once_per_battle=True,
    )
    prev = C.BattleState()
    low = C.BattleState(flags={"fuel_low": True})
    clear = C.BattleState()

    assert d.feed(prev, low) is not None
    d.mark_delivered()
    d.feed(prev, clear); d.feed(prev, clear)
    assert d.feed(prev, low) is None

    d.reset()
    assert d.feed(prev, low) is not None


def test_once_per_battle_condition_stays_spent_across_same_battle_respawn():
    d = ConditionDetector(
        "low_fuel", [("fuel_low", "fuel_critical")],
        confirm_enter=1, confirm_exit=2, once_per_battle=True,
    )
    engine = DetectorEngine([d])
    prev = C.BattleState()
    low = C.BattleState(flags={"fuel_low": True})

    assert [event.event_id for event in engine.feed(prev, low)] == ["low_fuel"]
    engine.mark_delivered("low_fuel")

    dead = C.BattleState(dead=True)
    assert engine.feed(low, dead) == []

    respawned = C.BattleState(flags={"fuel_low": True})
    assert engine.feed(dead, respawned) == []

    engine.reset()
    assert [event.event_id for event in engine.feed(respawned, low)] == ["low_fuel"]


def test_once_per_battle_still_allows_warning_to_critical_upgrade():
    """升级发生在 ACTIVE 内，不走 re-arm，因此必须仍然生效。"""
    d = ConditionDetector(
        "low_fuel", [("fuel_low", "fuel_critical")],
        confirm_enter=1, confirm_exit=2, once_per_battle=True,
    )
    prev = C.BattleState()

    first = d.feed(prev, C.BattleState(flags={"fuel_low": True}))
    assert first is not None and first.level == "warning"

    upgraded = d.feed(prev, C.BattleState(flags={"fuel_critical": True}))
    assert upgraded is not None and upgraded.level == "critical"


def test_once_per_battle_rearms_when_candidate_was_not_delivered():
    d = ConditionDetector(
        "low_fuel", [("fuel_low", "fuel_critical")],
        confirm_enter=1, confirm_exit=2, once_per_battle=True,
    )
    prev = C.BattleState()
    low = C.BattleState(flags={"fuel_low": True})
    clear = C.BattleState()

    assert d.feed(prev, low) is not None
    assert d.feed(prev, clear) is None
    assert d.feed(prev, clear) is None
    assert d.feed(prev, low) is not None


def test_once_per_battle_rearms_when_real_output_follows_dry_run():
    detector = ConditionDetector(
        "low_fuel",
        [("fuel_low", "fuel_critical")],
        confirm_enter=1,
        confirm_exit=2,
        once_per_battle=True,
    )
    engine = DetectorEngine([detector])
    low = C.BattleState(flags={"fuel_low": True})

    assert [event.event_id for event in engine.feed(C.BattleState(), low)] == ["low_fuel"]

    engine.rearm_uncommitted_once_per_battle()

    assert [event.event_id for event in engine.feed(low, low)] == ["low_fuel"]
    engine.mark_delivered("low_fuel")
    engine.rearm_uncommitted_once_per_battle()
    assert engine.feed(low, low) == []


def test_condition_without_once_per_battle_still_rearms():
    d = ConditionDetector("stall_risk", [("stall_warning", "stall_critical")], confirm_enter=1, confirm_exit=2)
    prev = C.BattleState()
    on = C.BattleState(flags={"stall_warning": True})
    off = C.BattleState()

    assert d.feed(prev, on) is not None
    d.feed(prev, off); d.feed(prev, off)
    assert d.feed(prev, on) is not None


def test_awareness_detectors_share_one_set_of_helpers_and_thresholds():
    """接近/态势两个检测器不得各留一份取值与几何判定副本。

    历史上 _as_float / _as_int / _safe_short_text 在两个文件里逐字重复，后半球判定
    还有 _is_rear 与 _is_behind 两个名字，尾随阈值也分散两处——真机调参时很容易
    只改一边。守住这条，重复回潮会立刻失败。
    """
    import pathlib

    from neko_warthunder.detectors.discrete import _common

    root = pathlib.Path(__file__).resolve().parent.parent / "detectors" / "discrete"
    for name in ("situation.py", "proximity.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert "def _as_float" not in src, f"{name} 又出现了本地 _as_float"
        assert "def _as_int" not in src, f"{name} 又出现了本地 _as_int"
        assert "def _safe_short_text" not in src, f"{name} 又出现了本地 _safe_short_text"
        assert "_BEHIND_CLOCKS = {" not in src, f"{name} 又出现了本地后半球常量"
        assert "from ._common import" in src

    # 两条路径的阈值刻意不同：帧驱动窗短距宽，事件驱动窗长距窄。
    assert _common.SITUATION_TAIL_WINDOW_SECONDS < _common.PROXIMITY_TAIL_WINDOW_SECONDS
    assert _common.SITUATION_TAIL_DISTANCE_M > _common.PROXIMITY_TAIL_DISTANCE_M


def test_shared_rear_predicate_matches_both_clock_and_relative_bearing():
    from neko_warthunder.detectors.discrete._common import is_rear

    assert is_rear({"clock": 6}) is True
    assert is_rear({"clock": 5}) is True
    assert is_rear({"clock": 12}) is False
    assert is_rear({"relative_deg": 180.0}) is True
    assert is_rear({"relative_deg": -140.0}) is True
    assert is_rear({"relative_deg": 20.0}) is False
    assert is_rear({}) is False
    # bool 是 int 的子类，必须被排除，否则 True 会被当成 1 点钟
    assert is_rear({"clock": True}) is False
