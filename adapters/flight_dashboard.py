"""Read-only flight telemetry projection for the dashboard."""

from __future__ import annotations

from typing import Any

from ..core.contracts import BattleState


def flight_status_snapshot(s: BattleState) -> dict[str, Any]:
    return {
        "age_seconds": s.age_seconds,
        "ias_kmh": s.ias_kmh,
        "mach": s.mach,
        "altitude_m": s.altitude_m,
        "radio_altitude_m": s.radio_altitude_m,
        "climb_ms": s.climb_ms,
        "fuel_fraction": s.fuel_fraction,
        "level": s.level,
        "flags": dict(sorted((s.flags or {}).items())),
    }
