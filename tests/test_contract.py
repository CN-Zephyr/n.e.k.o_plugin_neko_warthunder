"""契约：parse_telemetry 把 /api/telemetry 归一化成 BattleState（接缝②回归）。"""

from __future__ import annotations

from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core.contracts import (
    CAT_SAFETY_CRITICAL,
    CRITICAL_EVENT_IDS,
    CRITICAL_FLAG_CODES,
    EVENT_CATALOG,
    WtConfig,
)
from neko_warthunder.core.flag_codes import CONDITION_FLAG_GROUPS


def _sample() -> dict:
    return {
        "state": "in_battle",
        "in_battle": True,
        "domain": "air",
        "timestamp": 123.0,
        "vehicle": {"valid": True, "ias_kmh": 180.0, "aoa_deg": 16.0, "altitude_m": 400.0, "climb_ms": -12.0, "mach": 0.3, "load_factor": 4.5},
        "indicators": {"valid": True, "vehicle_type": "bf-109f-4", "army": "air"},
        "processed": {
            "flags": {"stall_warning": True, "altitude_low": True},
            "level": "warning",
            "ias_kmh": 180.0, "aoa_deg": 16.0, "altitude_m": 400.0, "radio_altitude_m": 8.0,
            "fuel_fraction": 0.42, "g_now": 4.5, "water_temp_c": 112.0,
        },
        "hud_events": [{"id": 1, "kind": "damage", "msg": "x"}],
        "chat": [{"id": 2, "sender": "Me", "msg": "进攻 D 点！"}],
        "combat": {"player_name": "Me", "my": {"kills": 2, "deaths": 0}, "feed": []},
        "mission_status": "running",
        "meta": {"fast": {"age_sec": 0.1}},
    }


def test_parse_in_battle():
    s = parse_telemetry(_sample())
    assert s.connected and s.in_battle and s.conn_state == "in_battle"
    assert s.vehicle_valid is True
    assert s.domain == "air" and s.vehicle_type == "bf-109f-4"
    assert s.ias_kmh == 180.0 and s.altitude_m == 400.0 and s.radio_altitude_m == 8.0 and s.climb_ms == -12.0
    assert s.flag("stall_warning") and s.flag("altitude_low")
    assert s.any_critical_flag() is False  # 只有 warning 级
    assert s.fuel_fraction == 0.42 and s.water_temp_c == 112.0
    assert s.chat == [{"id": 2, "sender": "Me", "msg": "进攻 D 点！"}]


def test_parse_offline():
    s = parse_telemetry(None)
    assert s.connected is False and s.conn_state == "offline" and s.in_battle is False
    assert s.vehicle_valid is False


def test_critical_flag():
    payload = _sample()
    payload["processed"]["flags"] = {"stall_critical": True}
    s = parse_telemetry(payload)
    assert s.any_critical_flag() is True


def test_flight_control_critical_flags_drive_critical_risk_contract():
    for code in ("aoa_critical", "over_g_critical"):
        payload = _sample()
        payload["processed"]["flags"] = {code: True}
        s = parse_telemetry(payload)
        assert s.any_critical_flag() is True


def test_critical_event_flag_groups_stay_in_sync_with_critical_risk_flags():
    assert CRITICAL_EVENT_IDS == {
        event_id
        for event_id, spec in EVENT_CATALOG.items()
        if spec.category == CAT_SAFETY_CRITICAL
    }
    expected_flag_codes = {
        critical_flag
        for event_id in CRITICAL_EVENT_IDS
        for _, critical_flag in CONDITION_FLAG_GROUPS[event_id]
    }
    assert CRITICAL_FLAG_CODES == expected_flag_codes


def test_parse_replay_flag():
    payload = _sample()
    payload["replay"] = True
    s = parse_telemetry(payload)
    assert getattr(s, "replay", False) is True


def test_parse_radio_altitude_falls_back_to_indicators():
    payload = _sample()
    payload["processed"].pop("radio_altitude_m", None)
    payload["indicators"]["radio_altitude"] = 12.5

    s = parse_telemetry(payload)

    assert s.radio_altitude_m == 12.5


def test_parse_dead_and_profile_fields_from_v18_contract():
    payload = _sample()
    payload["dead"] = True
    payload["domain_label"] = "Air"
    payload["processed"]["profile_matched"] = True
    payload["processed"]["profile_source"] = "family"
    payload["processed"]["profile_family"] = "Bf 109"
    s = parse_telemetry(payload)
    assert s.dead is True
    assert s.domain_label == "Air"
    assert s.profile_matched is True
    assert s.profile_source == "family"
    assert s.profile_family == "Bf 109"


def test_parse_ground_processed_fields_from_v18_contract():
    payload = _sample()
    payload["domain"] = "ground"
    payload["processed"].update(
        {
            "crew_current": 1,
            "crew_total": 4,
            "ammo_first_stage": 0,
            "gun_stabilizer": True,
            "gear_position": -1,
            "gunner_state": 0,
            "driver_state": 0,
            "flags": {
                "crew_critical": True,
                "ammo_empty": True,
                "laser_warning": True,
                "gunner_disabled": True,
                "driver_disabled": True,
            },
        }
    )

    s = parse_telemetry(payload)

    assert s.domain == "ground"
    assert s.crew_current == 1
    assert s.crew_total == 4
    assert s.ammo_first_stage == 0
    assert s.gun_stabilizer is True
    assert s.gear_position == -1
    assert s.gunner_state == 0
    assert s.driver_state == 0
    assert s.flag("crew_critical")
    assert s.flag("ammo_empty")
    assert s.flag("laser_warning")
    assert s.flag("gunner_disabled")
    assert s.flag("driver_disabled")


def test_parse_hud_notices_feed_without_losing_raw_contract():
    payload = _sample()
    payload["hud_notices"] = {
        "feed": [
            {"id": 42, "code": "engine_overheat", "severity": "warning", "text": "水温过高"},
        ],
    }
    s = parse_telemetry(payload)
    assert s.hud_notices == payload["hud_notices"]["feed"]
    assert s.raw["hud_notices"]["feed"][0]["text"] == "水温过高"


def test_parse_proximity_and_situation_from_v2_contract():
    payload = _sample()
    payload["proximity"] = {
        "thresholds_m": {"vs_air": 3000},
        "events": [
            {
                "id": 7,
                "kind": "enter",
                "type": "fighter",
                "category": "enemy_air",
                "is_air": True,
                "distance_m": 1800,
                "compass": "NW",
                "clock": 10,
                "text": "unsafe raw text must stay raw-only",
            }
        ],
    }
    payload["situation"] = {
        "air_threat_count": 1,
        "ground_targets": [{"kind": "bombing_point", "label": "轰炸点", "grid": "B4", "distance_m": 2400}],
    }

    s = parse_telemetry(payload)

    assert s.proximity_events == payload["proximity"]["events"]
    assert s.proximity["thresholds_m"]["vs_air"] == 3000
    assert s.situation == payload["situation"]
    assert s.raw["proximity"]["events"][0]["text"] == "unsafe raw text must stay raw-only"


def test_v16_event_catalog_entries_are_not_marked_blocked():
    for event_id in (
        "overspeed",
        "you_killed",
        "you_died",
        "ground_target_nearby",
        "enemy_nearby",
        "air_threat_nearby",
        "enemy_on_six",
        "tailing_risk",
    ):
        assert EVENT_CATALOG[event_id].blocked is False


def test_v2_live_verified_real_output_config_defaults_closed_and_can_be_enabled():
    assert WtConfig().v2_live_verified_real_output_enabled is False
    assert WtConfig.from_mapping({}).v2_live_verified_real_output_enabled is False
    assert WtConfig.from_mapping({"v2_live_verified_real_output_enabled": True}).v2_live_verified_real_output_enabled is True


def test_broadcast_preferences_default_to_current_standard_behavior():
    config = WtConfig.from_mapping({})

    assert config.broadcast_frequency == "standard"
    assert config.broadcast_categories == {
        "safety": True,
        "combat": True,
        "radio": True,
        "awareness": True,
        "lifecycle": True,
    }


def test_broadcast_preferences_normalize_invalid_frequency_and_partial_categories():
    config = WtConfig.from_mapping(
        {
            "broadcast_frequency": "unknown",
            "broadcast_categories": {"radio": False, "unrecognized": False},
        }
    )

    assert config.broadcast_frequency == "standard"
    assert config.broadcast_categories["radio"] is False
    assert config.broadcast_categories["safety"] is True
    assert "unrecognized" not in config.broadcast_categories


def test_mission_status_normalization_is_shared_across_end_and_result_checks():
    """"是否终局"与"胜负判定"必须用同一套归一化。

    数据层可能给出带空白的值，或 "win, K3/D1" 这类复合串；历史上场景机与
    battle_end 检测器只做 lower()，而 classify_battle_result 还做 strip + 逗号截断，
    于是同一个值会出现"场景机不认为结束、classify 却识别得出"的分裂。
    """
    from neko_warthunder.core.contracts import (
        classify_battle_result,
        is_battle_end_status,
        normalize_mission_status,
    )

    for raw, kind in [
        ("win", "victory"),
        ("  Win  ", "victory"),
        ("win, K3/D1", "victory"),
        ("DEFEAT", "defeat"),
        (" lost , K0/D2", "defeat"),
        ("left", "neutral"),
    ]:
        assert is_battle_end_status(raw) is True, raw
        assert classify_battle_result(raw) == kind, raw

    for raw in ("running", "", None, "   ", "in_progress"):
        assert is_battle_end_status(raw) is False, raw
        assert classify_battle_result(raw) == "unknown", raw

    assert normalize_mission_status("  Win, K3/D1 ") == "win"


def test_scenario_and_battle_end_detector_agree_on_compound_status():
    """场景机与 battle_end 检测器对复合状态串的判定必须一致。"""
    from neko_warthunder.core import contracts as C
    from neko_warthunder.core.scenario import ScenarioResolver
    from neko_warthunder.detectors.discrete.lifecycle import BattleEndDetector

    compound = "win, K3/D1"
    resolver = ScenarioResolver()
    state = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, mission_status=compound)
    assert resolver.resolve(state, 1000.0, 6) == C.BATTLE_ENDED

    det = BattleEndDetector()
    prev = C.BattleState(connected=True, conn_state="in_battle", in_battle=True, mission_status="running")
    ev = det.feed(prev, state)
    assert ev is not None and ev.event_id == "battle_end"
    assert ev.payload["result_kind"] == "victory"
