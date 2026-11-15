"""Read-only map and naval dashboard snapshots."""

from __future__ import annotations

import time
from typing import Any

from ..core.contracts import BattleState
from .dashboard_telemetry import VEHICLE_STATUS_MAX_AGE_SECONDS, status_number


def map_status_snapshot(s: BattleState) -> dict[str, Any]:
    """Whitelist map facts, independently aged and bound to the sampled life."""
    number = status_number
    raw = s.raw if isinstance(s.raw, dict) else {}
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    sample = meta.get("map_objects") if isinstance(meta.get("map_objects"), dict) else {}
    age, fast_age, timestamp = number(sample.get("age_sec")), number(s.age_seconds), number(s.timestamp)
    known_age = (age is not None and age >= 0 and fast_age is not None and fast_age >= 0
                 and timestamp is not None and timestamp > 0)
    elapsed = max(0.0, time.time() - timestamp - fast_age) if known_age else 0.0
    sample_age = round(age + elapsed, 3) if known_age else None
    life = number(sample.get("life_index"))
    same_life = life is not None and life.is_integer() and life >= 1 and life == s.life_index
    situation = s.situation if isinstance(s.situation, dict) else {}
    player = situation.get("player") if isinstance(situation.get("player"), dict) else {}
    has_position = situation.get("has_player") is True and all(
        (value := number(player.get(key))) is not None and 0 <= value <= 1 for key in ("x", "y")
    )
    if not s.connected or s.conn_state == "offline":
        status = "offline"
    elif s.replay:
        status = "replay"
    elif not s.in_battle:
        status = "waiting"
    elif s.dead:
        status = "dead"
    elif known_age and max(age + elapsed, fast_age, elapsed) > VEHICLE_STATUS_MAX_AGE_SECONDS:
        status = "stale"
    elif not known_age or not same_life:
        status = "unavailable"
    elif not has_position:
        status = "no_player"
    else:
        status = "ready"

    def count(key: str) -> int | None:
        value = number(situation.get(key))
        return int(value) if value is not None and value >= 0 and value.is_integer() else None

    enemy, ally, air = count("enemy_count"), count("ally_count"), count("air_threat_count")
    if enemy is None or (air is not None and air > enemy):
        air = None
    nearest = situation.get("nearest_enemy")
    nearest = nearest if isinstance(nearest, dict) else {}
    distance, bearing = number(nearest.get("distance_m")), number(nearest.get("bearing_deg"))
    map_info = raw.get("map_info") if isinstance(raw.get("map_info"), dict) else {}
    # wt_geo can fall back to grid_size, which is not the full map scale.
    # Do not call the first unsortable contact "nearest" without a known world span.
    bounds = [map_info.get(key) for key in ("map_min", "map_max")]
    scale_known = map_info.get("valid") is True and all(
        isinstance(bound, (list, tuple)) and len(bound) == 2
        and all(number(value) is not None for value in bound) for bound in bounds
    )
    if scale_known:
        scale_known = all(bounds[1][i] > bounds[0][i] for i in (0, 1))
    contact_known = (scale_known and enemy is not None and enemy > 0
                     and distance is not None and distance >= 0
                     and nearest.get("type") in {"aircraft", "ground_model"})
    facts = {
        "enemy_count": enemy, "ally_count": ally, "air_contact_count": air,
        "nearest_type": nearest.get("type") if contact_known else None,
        "nearest_distance_m": distance if contact_known else None,
        "nearest_bearing_deg": bearing if contact_known and bearing is not None and 0 <= bearing < 360 else None,
    }
    result = {"status": status, "sample_age_seconds": sample_age,
              **{key: value if status == "ready" else None for key, value in facts.items()}}
    if status != "ready" or not s.battle_id:
        return result

    # 舰艇重生点只说明战场类型。自身载具域仍由独立的仪表数据决定。
    objects = raw.get("map_objects")
    naval_battlefield = isinstance(objects, list) and any(
        isinstance(obj, dict) and obj.get("type") in ("respawn_base_ship", "respawn_base_destroyer")
        and obj.get("icon") == obj["type"] for obj in objects
    )
    if naval_battlefield:
        result["battlefield"] = "naval"
    if naval_battlefield or s.domain == "naval":
        # 昵称切换会先更新面板身份。等下一帧战绩与当前身份一致后再显示。
        combat = raw.get("combat") if isinstance(raw.get("combat"), dict) else {}
        identity = combat.get("self")
        personal = combat.get("my")
        if (isinstance(identity, dict) and identity.get("source") == "manual"
                and identity.get("name") and identity == s.combat.get("self")
                and isinstance(personal, dict)):
            result["personal_combat"] = {
                key: personal[key] for key in ("kills", "deaths")
                if type(personal.get(key)) is int and personal[key] >= 0
            }
    return result
