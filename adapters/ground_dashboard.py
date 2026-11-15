"""Read-only ground dashboard snapshot."""

from __future__ import annotations

import time
from typing import Any

from ..core.contracts import BattleState
from ..core.telemetry_freshness import ground_indicator_source
from .dashboard_telemetry import status_number, vehicle_status_snapshot


def ground_status_snapshot(s: BattleState) -> dict[str, Any] | None:
    """Read-only, numeric ground facts; never turn missing or stale data into zero."""
    if (s.domain or "").lower() != "ground":
        return None
    raw = s.raw if isinstance(s.raw, dict) else {}
    indicators = raw.get("indicators")
    indicators = indicators if isinstance(indicators, dict) else {}
    snapshot = vehicle_status_snapshot(s, indicators=indicators)
    source = ground_indicator_source(s, time.time())
    if source is None:
        snapshot["sample_timestamp"] = s.timestamp if snapshot["sample_age_seconds"] is not None else None
    elif snapshot["status"] not in ("offline", "waiting", "dead", "replay"):
        snapshot = {"status": source.status, "sample_age_seconds": source.age_seconds,
                    "sample_timestamp": source.timestamp}
    else:
        snapshot["sample_timestamp"] = None

    def integer(value: Any, *, signed: bool = False) -> int | None:
        value = status_number(value)
        if value is None or not value.is_integer() or (not signed and value < 0):
            return None
        return int(value)

    # processed may contain cached facts when the separate /state request fails.
    crew_current = integer(indicators.get("crew_current"))
    crew_total = integer(indicators.get("crew_total"))
    if crew_total == 0 or (crew_current is not None and crew_total is not None and crew_current > crew_total):
        crew_current = crew_total = None
    stabilizer = status_number(indicators.get("stabilizer"))
    gear = status_number(indicators.get("gear"))
    neutral = status_number(indicators.get("gear_neutral"))
    gear_position = status_number(gear - neutral) if gear is not None and neutral is not None else None
    rpm = status_number(indicators.get("rpm"))
    indicator_raw = indicators.get("raw")
    indicator_raw = indicator_raw if isinstance(indicator_raw, dict) else {}

    def damage(key: str) -> bool | None:
        value = indicator_raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in (0, 1):
            return None
        return value == 1

    facts = {
        "crew_current": crew_current,
        "crew_total": crew_total,
        "ammo_first_stage": integer(indicators.get("first_stage_ammo")),
        "gun_stabilizer": stabilizer >= 0.5 if stabilizer is not None else None,
        "gear_position": round(gear_position) if gear_position is not None else None,
        "speed_kmh": status_number(indicators.get("speed")),
        "engine_rpm": rpm if rpm is not None and rpm >= 0 else None,
        "gunner_state": integer(indicators.get("gunner_state")),
        "driver_state": integer(indicators.get("driver_state")),
        "laser_warning_state": integer(indicators.get("lws"), signed=True),
        "track_broken": damage("track_broken"),
        "h_drive_dead": damage("h_drive_dead"),
        "breach_dead": damage("breach_dead"),
        "barrel_dead": damage("barrel_dead"),
    }
    return {**snapshot,
            **{key: value if snapshot["status"] in ("ready", "held") else None for key, value in facts.items()}}
