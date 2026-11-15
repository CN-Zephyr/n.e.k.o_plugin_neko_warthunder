"""Read-only helicopter dashboard snapshot."""

from __future__ import annotations

from typing import Any

from ..core.contracts import BattleState
from .dashboard_telemetry import status_number, vehicle_status_snapshot


def helicopter_status_snapshot(s: BattleState) -> dict[str, Any] | None:
    """Project helicopter instruments only; no VRS, RPM thresholds or output policy."""
    if (s.domain or "").lower() != "heli":
        return None
    snapshot = vehicle_status_snapshot(s)
    facts = {key: status_number(getattr(s, key))
             for key in ("rotor_rpm", "radio_altitude_m", "vario_ms")}
    for key in ("rotor_rpm", "radio_altitude_m"):
        if facts[key] is not None and facts[key] < 0:
            facts[key] = None
    return {**snapshot,
            **{key: value if snapshot["status"] == "ready" else None for key, value in facts.items()}}
