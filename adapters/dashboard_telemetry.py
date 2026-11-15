"""Shared instrument validity and freshness for dashboard projections."""

from __future__ import annotations

import math
import time
from typing import Any

from ..core.contracts import BattleState
from ..core.telemetry_freshness import (
    GROUND_SAMPLE_MAX_AGE_SECONDS,
    legacy_ground_sample_age,
)

# Align dashboard availability with the data layer's vehicle cache.
VEHICLE_STATUS_MAX_AGE_SECONDS = 5.0


def status_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def vehicle_status_snapshot(
    s: BattleState, *, indicators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared read-only availability and source age for vehicle status cards."""
    number = status_number
    fast_age = max(0.0, number(s.age_seconds) or 0.0)
    timestamp = number(s.timestamp) or 0.0
    now = time.time()
    if indicators is not None:
        sample_age = legacy_ground_sample_age(s, now)
        valid = sample_age is not None
        stale = sample_age is not None and sample_age >= GROUND_SAMPLE_MAX_AGE_SECONDS
        sample_age = round(sample_age, 3) if sample_age is not None else None
    else:
        raw = s.raw if isinstance(s.raw, dict) else {}
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        vehicle_meta = meta.get("vehicle") if isinstance(meta.get("vehicle"), dict) else {}
        sample_age = number(vehicle_meta.get("age_sec"))
        # The source age is relative to the HTTP snapshot. Include time spent in the plugin cache.
        elapsed = max(0.0, now - timestamp - fast_age) if timestamp > 0 else 0.0
        sample_age = round(sample_age + elapsed, 3) if sample_age is not None and sample_age >= 0 else None
        valid = s.vehicle_valid
        stale = max(elapsed, fast_age, sample_age or 0.0) > VEHICLE_STATUS_MAX_AGE_SECONDS
    if not s.connected or s.conn_state == "offline":
        status = "offline"
    elif s.replay:
        status = "replay"
    elif not s.in_battle or (indicators is not None and s.conn_state != "in_battle"):
        status = "waiting"
    elif s.dead:
        status = "dead"
    elif stale:
        status = "stale"
    elif not valid:
        status = "unavailable"
    else:
        status = "ready"

    return {"status": status, "sample_age_seconds": sample_age}
