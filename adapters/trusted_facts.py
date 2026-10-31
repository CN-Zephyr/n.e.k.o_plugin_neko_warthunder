"""Bounded, readonly summary of existing dashboard facts; no detection or delivery."""
from __future__ import annotations

import math
from typing import Any

from ..core.contracts import BattleState

_FACTS = {
    "air": ("ias_kmh", "mach", "radio_altitude_m", "altitude_m", "fuel_fraction"),
    "ground": ("crew_current", "ammo_first_stage", "laser_warning_state", "gun_stabilizer", "gear_position"),
    "heli": ("rotor_rpm", "radio_altitude_m", "vario_ms"),
    "naval": ("enemy_count", "ally_count", "air_contact_count", "nearest_distance_m", "nearest_bearing_deg"),
    "unknown": ("enemy_count", "ally_count", "air_contact_count", "nearest_distance_m", "nearest_bearing_deg"),
}
_CAPABILITIES = {
    "air": ("flight_safety", "owned_combat", "air_awareness"),
    "ground": ("ground_status", "laser_warning", "owned_combat"),
    "heli": ("heli_instruments", "vrs_dry_run", "owned_combat"),
    "naval": ("map_observation", "naval_dry_run", "static_reference"),
    "unknown": ("generic_map",),
}
_LIMITS = {
    "air": ("agl_not_msl", "v2_gated"),
    "ground": ("ready_rack_only", "roles_readonly", "laser_not_missile"),
    "heli": ("vrs_no_speech", "no_rotor_alarm"),
    "naval": ("map_icons_only", "naval_values_hidden", "static_not_effective"),
    "unknown": ("domain_unconfirmed", "map_icons_only"),
}


def _number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _response_age(state: BattleState, now: float) -> tuple[str, float | None]:
    age, timestamp = state.age_seconds, state.timestamp
    if not all(_number(v) for v in (age, timestamp, now)) or age < 0 or timestamp <= 0:
        return "unknown_age", None
    # timestamp + fast age identifies the HTTP snapshot observation, not a new sample.
    # age_sec is rounded to milliseconds by the existing HTTP contract.
    if now < timestamp or now + 0.001 < timestamp + age:
        return "invalid_clock", None
    current = now - timestamp
    return ("stale" if current > 5 else "ready"), round(current, 3)


def snapshot_trusted_facts(state: BattleState, dashboard: dict[str, Any], now: float) -> dict[str, Any]:
    """Reuse already-projected values; never serialize raw text, IDs, flags or static values.

    Old vehicle metadata has no independently sampled life binding. We state this
    explicitly rather than inventing one from the response life. Map facts retain
    their existing per-sample life check. Nothing is cached between reads/lives.
    """
    domain = state.domain if state.domain in _FACTS else "unknown"
    response_status, response_age = _response_age(state, now)
    if not state.connected or state.conn_state == "offline":
        context = "offline"
    elif state.replay:
        context = "replay"
    elif not state.in_battle or state.conn_state != "in_battle":
        context = "waiting"
    elif state.dead:
        context = "dead"
    else:
        context = "ready"

    map_domain = domain in {"naval", "unknown"}
    source_id = "map" if map_domain else "vehicle"
    projection_key = {"air": "telemetry", "ground": "ground_status", "heli": "helicopter_status",
                      "naval": "naval_status", "unknown": "map_status"}[domain]
    projection = dashboard.get(projection_key)
    projection = projection if isinstance(projection, dict) else {}
    source = dashboard.get("vehicle_source") if not map_domain else projection
    source = source if isinstance(source, dict) else {}
    statuses = {"ready", "waiting", "offline", "dead", "replay", "stale", "unavailable", "no_player"}
    source_status = source.get("status") if source.get("status") in statuses else "unavailable"
    age = source.get("sample_age_seconds")
    age = age if _number(age) and age >= 0 else None
    if context != "ready":
        source_status = context
    elif response_status != "ready":
        source_status = response_status
    elif source_status == "ready" and age is None:
        source_status = "unknown_age"
    elif source_status == "ready" and age > 5:
        source_status = "stale"

    sources = [{"id": source_id, "status": source_status, "age_seconds": age,
                "life_binding": "sample" if map_domain and source_status == "ready" else "unverified"}]
    facts = []
    for key in _FACTS[domain]:
        value = projection.get(key) if source_status == "ready" else None
        valid = isinstance(value, bool) if key == "gun_stabilizer" else _number(value)
        if valid and key != "gun_stabilizer":
            if key not in {"altitude_m", "vario_ms", "gear_position", "laser_warning_state"} and value < 0:
                valid = False
            if key in {"crew_current", "ammo_first_stage", "laser_warning_state", "gear_position",
                       "enemy_count", "ally_count", "air_contact_count"} and int(value) != value:
                valid = False
            if key == "fuel_fraction" and value > 1:
                valid = False
            if key == "nearest_bearing_deg" and value >= 360:
                valid = False
            if key == "laser_warning_state" and value not in {-1, 0, 1, 2}:
                valid = False
        total = projection.get("crew_total") if key == "crew_current" else None
        if key == "crew_current":
            valid = valid and _number(total) and total > 0 and int(total) == total and value <= total
        row = {"id": key, "source": source_id, "status": "available" if valid else (
            "unknown" if source_status == "ready" else "unavailable"), "value": value if valid else None}
        if key == "crew_current":
            row["total"] = total if valid else None
        facts.append(row)

    available = sum(row["status"] == "available" for row in facts)
    status = context if context != "ready" else (
        "ready" if available == len(facts) else "partial" if available else "unavailable")
    policy = dashboard.get("output_policy") or {}
    safety = dashboard.get("safety") or {}
    # This describes existing switches only, never an allow decision for an event.
    return {"version": 1, "readonly": True, "domain": domain, "status": status,
            "response_age_seconds": response_age, "sources": sources, "facts": facts,
            "capabilities": list(_CAPABILITIES[domain]), "limits": list(_LIMITS[domain]),
            "output": {"mode": "disabled" if dashboard.get("enabled") is not True else "paused" if (
                safety.get("manual_paused") or safety.get("auto_paused") or safety.get("status") != "running"
            ) else "dry_run" if dashboard.get("dry_run") is not False else "existing_policy",
                "ground_status_enabled": policy.get("ground_status_real_output_enabled") is True,
                "v2_enabled": policy.get("v2_live_verified_real_output_enabled") is True,
                "heli_vrs_enabled": False, "naval_contacts_enabled": False}}
