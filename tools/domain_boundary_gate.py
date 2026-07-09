"""Offline gate for mode/domain detector boundaries.

The gate keeps fixed-wing flight safety cues out of ground/naval/heli domains
and keeps ground vehicle status cues out of non-ground domains. It is synthetic,
no-host, and does not start War Thunder or the data-layer subprocess.
"""

from __future__ import annotations

import json
import pathlib
import sys
import types
from typing import Any

_BASE = pathlib.Path(__file__).resolve().parent.parent
if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg

from neko_warthunder.core.contracts import BattleState  # noqa: E402
from neko_warthunder.detectors._base import DetectorEngine  # noqa: E402
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors  # noqa: E402


AIR_ONLY_FLAGS = {
    "stall_critical": True,
    "aoa_critical": True,
    "over_g_critical": True,
    "altitude_critical": True,
    "overspeed_critical": True,
    "fuel_critical": True,
}

GROUND_ONLY_FLAGS = {
    "laser_warning": True,
    "crew_critical": True,
    "gunner_disabled": True,
    "driver_disabled": True,
    "ammo_empty": True,
    "ammo_low": True,
}

EXPECTED_AIR_EVENTS = {
    "stall_risk",
    "high_aoa",
    "over_g",
    "low_alt_danger",
    "overspeed",
    "low_fuel",
}

EXPECTED_GROUND_EVENTS = {
    "ground_laser_warning",
    "ground_crew_loss",
    "ground_gunner_disabled",
    "ground_driver_disabled",
    "ground_ammo_empty",
    "ground_ammo_low",
}


def _condition_engine() -> DetectorEngine:
    return DetectorEngine(list(build_condition_detectors()))


def _event_ids(events: list[Any]) -> list[str]:
    return [str(event.event_id) for event in events]


def _air_pressure_state(domain: str) -> BattleState:
    return BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain=domain,
        flags=dict(AIR_ONLY_FLAGS),
        ias_kmh=1280.0,
        mach=1.08,
        aoa_deg=25.0,
        g_now=12.0,
        fuel_fraction=0.02,
        altitude_m=18.0,
        radio_altitude_m=6.0,
    )


def _ground_pressure_state(domain: str) -> BattleState:
    return BattleState(
        in_battle=True,
        vehicle_valid=True,
        domain=domain,
        flags=dict(GROUND_ONLY_FLAGS),
        crew_current=1,
        crew_total=4,
        gunner_state=0,
        driver_state=0,
        ammo_first_stage=0,
    )


def _collect_condition_events(engine: DetectorEngine, prev: BattleState, cur: BattleState, ticks: int) -> list[str]:
    emitted: list[str] = []
    last = prev
    for _ in range(ticks):
        events = engine.feed(last, cur)
        emitted.extend(_event_ids(events))
        last = cur
    return emitted


def _failure(kind: str, detail: str) -> dict[str, str]:
    return {"kind": kind, "detail": detail}


def run_gate() -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    results: dict[str, Any] = {
        "air_only_checked_domains": ["ground", "naval", "heli", ""],
        "air_emit_events": [],
        "ground_only_checked_domains": ["air", "heli", "naval", ""],
        "ground_emit_events": [],
    }

    for domain in results["air_only_checked_domains"]:
        engine = _condition_engine()
        cur = _air_pressure_state(domain)
        emitted = _collect_condition_events(engine, BattleState(domain=domain), cur, ticks=3)
        leaked = sorted(set(emitted) & EXPECTED_AIR_EVENTS)
        if leaked:
            failures.append(_failure("air_only_event_leaked", f"domain={domain or '<empty>'} events={leaked}"))

    for domain in results["ground_only_checked_domains"]:
        engine = _condition_engine()
        cur = _ground_pressure_state(domain)
        emitted = _collect_condition_events(engine, BattleState(domain=domain), cur, ticks=4)
        leaked = sorted(set(emitted) & EXPECTED_GROUND_EVENTS)
        if leaked:
            failures.append(_failure("ground_only_event_leaked", f"domain={domain or '<empty>'} events={leaked}"))

    air_engine = _condition_engine()
    air_cur = _air_pressure_state("air")
    air_emitted = _collect_condition_events(air_engine, BattleState(domain="air"), air_cur, ticks=3)
    results["air_emit_events"] = air_emitted
    missing_air = sorted(EXPECTED_AIR_EVENTS - set(air_emitted))
    if missing_air:
        failures.append(_failure("air_event_missing", f"events={missing_air}"))

    ground_engine = _condition_engine()
    ground_cur = _ground_pressure_state("ground")
    ground_emitted = _collect_condition_events(ground_engine, BattleState(domain="ground"), ground_cur, ticks=4)
    results["ground_emit_events"] = ground_emitted
    missing_ground = sorted(EXPECTED_GROUND_EVENTS - set(ground_emitted))
    if missing_ground:
        failures.append(_failure("ground_event_missing", f"events={missing_ground}"))

    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "results": results,
    }


def main() -> int:
    payload = run_gate()
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
