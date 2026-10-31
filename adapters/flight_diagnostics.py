"""Readonly, source-labelled state oil temperature and fuel estimate availability."""
from __future__ import annotations

import math
from typing import Any

from ..core.contracts import BattleState


def _number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def snapshot_flight_diagnostics(state: BattleState, trusted: dict[str, Any], now: float) -> dict[str, Any] | None:
    """Reuse validated response/vehicle ages; never update sampling or detection.

    Vehicle sample-life binding remains unverified. Explicit raw C keys and the
    normalized engine channel must agree; indicators/processed temperatures are
    not fallbacks and do not enter this projection or the model fact whitelist.
    """
    if state.domain != "air":
        return None
    sources = trusted.get("sources") or []
    source = next((s for s in sources if s.get("id") == "vehicle"), {})
    status = source.get("status", "unavailable")
    if status == "ready" and not state.is_alive():
        status = "unavailable"
    oil = {"status": status, "source": "state_oil_temp_C", "max_c": None,
           "observed_channels": 0, "unavailable_channels": 0, "life_binding": "unverified"}
    fuel = {"status": status, "source": "state_mass_difference", "burn_kgs": None,
            "remaining_sec": None, "age_sec": None, "max_age_sec": None}
    result = {"oil": oil, "fuel_estimate": fuel}
    if status != "ready":
        return result
    raw = state.raw if isinstance(state.raw, dict) else {}
    vehicle = raw.get("vehicle") if isinstance(raw.get("vehicle"), dict) else {}
    state_raw = vehicle.get("raw") if isinstance(vehicle.get("raw"), dict) else {}
    engines = vehicle.get("engines")
    values = []
    if isinstance(engines, list) and len(engines) <= 8:
        indices = [e.get("index") for e in engines if isinstance(e, dict)]
        for engine in engines:
            if not isinstance(engine, dict):
                oil["unavailable_channels"] += 1
                continue
            index, value = engine.get("index"), engine.get("oil_temp_c")
            valid_index = type(index) is int and 1 <= index <= 8 and indices.count(index) == 1
            original = state_raw.get(f"oil temp {index}, C") if valid_index else None
            if valid_index and _number(value) and _number(original) and value > -200 and value == original:
                values.append(value)
            else:
                oil["unavailable_channels"] += 1
    elif engines:
        oil["unavailable_channels"] = 8
    oil["observed_channels"] = len(values)
    oil["max_c"] = max(values) if values else None
    oil["status"] = "partial" if values and oil["unavailable_channels"] else "ready" if values else "unavailable"

    processed = raw.get("processed") if isinstance(raw.get("processed"), dict) else {}
    estimate_status = processed.get("fuel_estimate_status")
    fuel["status"] = estimate_status if estimate_status in {"waiting", "ready", "stale"} else "unavailable"
    age, limit = processed.get("fuel_estimate_age_sec"), processed.get("fuel_estimate_max_age_sec")
    if _number(age) and age >= 0:
        elapsed = max(0.0, now - state.timestamp - state.age_seconds)
        # Processed values may survive a short /state failure while fast polls
        # continue. Successful vehicle sample age, not only HTTP age, counts.
        vehicle_age = source.get("age_seconds")
        fuel["age_sec"] = round(age + max(elapsed, vehicle_age if _number(vehicle_age) else 0), 3)
    if _number(limit) and 45 <= limit <= 120:
        fuel["max_age_sec"] = limit
    if fuel["status"] == "ready":
        burn, remaining = processed.get("fuel_burn_rate_kgs"), processed.get("fuel_remaining_sec")
        if fuel["age_sec"] is None or fuel["max_age_sec"] is None:
            fuel["status"] = "unavailable"
        elif fuel["age_sec"] > fuel["max_age_sec"]:
            fuel["status"] = "stale"
        elif _number(burn) and burn > 0 and _number(remaining) and remaining >= 0:
            fuel["burn_kgs"], fuel["remaining_sec"] = burn, remaining
        else:
            fuel["status"] = "unavailable"
    return result
