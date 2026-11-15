"""Format allowlisted telemetry facts for battle announcements."""

from __future__ import annotations

from typing import Any

from ..core.contracts import BattleEvent
from .text_safety import sanitize_event_payload

_TEMPERATURE_LABELS = {
    "water_temp_c": "水温",
    "head_temp_c": "缸头温度",
    "turbine_temp_c": "涡轮温度",
    "oil_temp_c": "油温",
}


def format_battle_facts(event: BattleEvent) -> str:
    p, _ = sanitize_event_payload(event.event_id, event.payload)
    bits: list[str] = []
    kill_fact = _kill_fact(event.event_id, p)
    death_fact = _death_fact(event.event_id, p)
    proximity_fact = _proximity_fact(event.event_id, p)
    objective_fact = _objective_fact(event.event_id, p)
    ground_fact = _ground_vehicle_fact(event.event_id, p)
    free_text_fact = _free_text_fact(event.event_id, p)
    radio_fact = _radio_command_fact(event.event_id, p)
    has_radio_altitude = p.get("radio_altitude_m") is not None
    temp_source = p.get("temp_source")
    temperature_label = _TEMPERATURE_LABELS.get(temp_source, "温度") if isinstance(temp_source, str) else "温度"
    order = [
        ("ias_kmh", "IAS {:.0f}km/h"),
        ("aoa_deg", "迎角 {:.0f}°"),
        ("altitude_m", "高度 {:.0f}m"),
        ("climb_ms", "垂速 {:+.0f}m/s"),
        ("mach", "M {:.2f}"),
        ("fuel_fraction", "余油 {:.0%}"),
        ("temp_c", temperature_label + " {:.0f}℃"),
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
    if ground_fact:
        bits.append(ground_fact)
    if free_text_fact:
        bits.append(free_text_fact)
    if radio_fact:
        bits.append(radio_fact)
    if has_radio_altitude:
        try:
            bits.append("AGL {:.0f}m".format(p["radio_altitude_m"]))
        except (ValueError, TypeError):
            # Ignore malformed optional telemetry and keep the remaining facts.
            pass
    for key, fmt in order:
        if key == "altitude_m" and has_radio_altitude:
            continue
        if key in p and p[key] is not None:
            try:
                bits.append(fmt.format(p[key]))
            except (ValueError, TypeError):
                # Ignore malformed optional telemetry and keep the remaining facts.
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
        # Invalid optional distance does not invalidate the proximity event.
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
        # Invalid optional distance does not invalidate the objective event.
        pass

    return "任务目标点接近" if not detail else f"任务目标点接近（{'，'.join(detail)}）"


def _ground_vehicle_fact(event_id: str, payload: dict[str, Any]) -> str:
    if event_id == "ground_laser_warning":
        return "陆战激光告警"
    if event_id == "ground_crew_loss":
        return "陆战车组受损"
    if event_id == "ground_gunner_disabled":
        return "陆战炮手失能"
    if event_id == "ground_driver_disabled":
        return "陆战驾驶员失能"
    if event_id == "ground_ammo_empty":
        return "一级弹药打空"
    if event_id == "ground_ammo_low":
        return "一级待发弹偏少（不代表全车余弹不足）"
    return ""


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


def _radio_point(payload: dict[str, Any]) -> str:
    point = str(payload.get("point") or "").strip().upper()
    return point if point in {"A", "B", "C", "D"} else ""


def _radio_command_label(payload: dict[str, Any]) -> str:
    command = str(payload.get("command") or "")
    point = _radio_point(payload)
    if command == "attack_point":
        return f"进攻{point}点" if point else "进攻目标点"
    if command == "defend_point":
        return f"防守{point}点" if point else "防守目标点"
    labels = {
        "cover_me": "掩护我",
        "need_help": "需要支援",
        "return_to_base": "返回基地",
        "repairing": "正在维修",
        "follow_me": "跟着我",
        "thanks": "感谢",
        "affirmative": "肯定",
        "negative": "否定",
        "well_done": "干得好",
    }
    return labels.get(command, "无线电口令")


def _radio_command_fact(event_id: str, payload: dict[str, Any]) -> str:
    if event_id != "player_radio_command":
        return ""
    return f"玩家无线电：{_radio_command_label(payload)}"
