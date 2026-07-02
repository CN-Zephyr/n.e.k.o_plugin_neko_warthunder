"""Extract read-only vehicle profile candidates from War Thunder Datamine.

This tool intentionally reports candidate values instead of editing
``vehicle_profiles.json``. Stall speed and AoA fields are fairly direct in the
flight-model files; overheat data is a model, so this script keeps it as
evidence until live samples validate a threshold.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


DEFAULT_REF = "master"
RAW_ROOT = "https://raw.githubusercontent.com/gszabi99/War-Thunder-Datamine"
DEFAULT_VEHICLES = [
    "j_15t",
    "su_30mk2v_venezuela",
    "su_30mkk",
    "f_16c_block_50",
    "fa_18c_late",
    "mirage_3e",
    "mirage_2000c_s5",
    "a6m5_hei",
]


@dataclass(frozen=True)
class DatamineFiles:
    vehicle: str
    unit_url: str
    fm_url: str


def _url(ref: str, path: str) -> str:
    return f"{RAW_ROOT}/{ref}/{path}"


def _load_json_url(url: str, *, timeout: float = 25.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "neko-warthunder-profile-audit"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error while fetching {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"timeout while fetching {url}") from exc


def _load_json_file(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_path(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _second_number(value: Any) -> float | None:
    if isinstance(value, list) and len(value) >= 2:
        return _num(value[1])
    return None


def _rounded(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    rounded = round(value, digits)
    return int(rounded) if rounded.is_integer() else rounded


def _dict_without_none(items: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in items.items() if value is not None}


def _candidate_stall(fm: dict[str, Any]) -> dict[str, Any]:
    clean_stall = _second_number(_get_path(fm, "Passport", "Alt", "stallSpeed"))
    landing_stall = _second_number(_get_path(fm, "Passport", "Alt", "stallSpeedLanding"))
    return _dict_without_none(
        {
            "source_field": "Passport.Alt.stallSpeed",
            "stall_critical_kmh": _rounded(clean_stall),
            "stall_warn_kmh": _rounded(clean_stall * 1.15 if clean_stall is not None else None),
            "landing_stall_kmh": _rounded(landing_stall),
            "note": (
                "clean stall is a useful candidate; landing stall should not drive normal "
                "in-flight alerts without takeoff/landing state guards"
            )
            if clean_stall is not None
            else None,
        }
    )


def _flaps_alpha_values(fm: dict[str, Any]) -> dict[str, float]:
    wing = _get_path(fm, "Aerodynamics", "WingPlane")
    if not isinstance(wing, dict):
        return {}
    values: dict[str, float] = {}
    for key, value in sorted(wing.items()):
        if key.startswith("FlapsPolar") and isinstance(value, dict):
            alpha = _num(value.get("alphaCritHigh"))
            if alpha is not None:
                values[key] = alpha
    return values


def _candidate_aoa(fm: dict[str, Any]) -> dict[str, Any]:
    alpha_values = _flaps_alpha_values(fm)
    clean_alpha = alpha_values.get("FlapsPolar0")
    aoa_limits = _get_path(fm, "Autopilot", "Pitch", "AoaLimits")
    positive_limit = _second_number(aoa_limits)
    if positive_limit is not None and not (0 < positive_limit <= 90):
        positive_limit = None

    # The report chooses a conservative candidate but keeps the raw fields so
    # maintainers can decide whether this aircraft should use the limiter or the
    # aerodynamic polar.
    candidate_critical = positive_limit or clean_alpha
    return _dict_without_none(
        {
            "source_fields": [
                "Aerodynamics.WingPlane.FlapsPolar*.alphaCritHigh",
                "Autopilot.Pitch.AoaLimits",
            ],
            "flaps_alpha_crit_high": {k: _rounded(v) for k, v in alpha_values.items()} or None,
            "autopilot_aoa_limits": aoa_limits if isinstance(aoa_limits, list) else None,
            "aoa_critical_deg": _rounded(candidate_critical),
            "aoa_warn_deg": _rounded(candidate_critical * 0.85 if candidate_critical else None),
            "note": (
                "AoA limiter can be lower than raw wing alpha on FBW/modern jets; treat this "
                "as a candidate, not a tested warning line"
            )
            if candidate_critical is not None
            else None,
        }
    )


def _candidate_overspeed(fm: dict[str, Any]) -> dict[str, Any]:
    strength = _get_path(fm, "Aerodynamics", "WingPlane", "Strength")
    if not isinstance(strength, dict):
        return {}
    vne = _num(strength.get("VNE"))
    mne = _num(strength.get("MNE"))
    return _dict_without_none(
        {
            "source_fields": ["Aerodynamics.WingPlane.Strength.VNE", "Aerodynamics.WingPlane.Strength.MNE"],
            "overspeed_critical_kmh": _rounded(vne),
            "overspeed_warn_kmh": _rounded(vne * 0.9 if vne is not None else None),
            "overspeed_critical_mach": _rounded(mne, 2),
            "overspeed_warn_mach": _rounded(mne * 0.9 if mne is not None else None, 2),
        }
    )


def _candidate_mass(fm: dict[str, Any]) -> dict[str, Any]:
    empty_mass = _num(_get_path(fm, "Mass", "EmptyMass"))
    max_fuel_mass = _num(_get_path(fm, "Mass", "MaxFuelMass0"))
    oil_mass = _num(_get_path(fm, "Mass", "OilMass"))
    passport_mass = _num(_get_path(fm, "Passport", "mass"))
    return _dict_without_none(
        {
            "source_fields": [
                "Mass.EmptyMass",
                "Mass.MaxFuelMass0",
                "Mass.OilMass",
                "Passport.mass",
            ],
            "empty_mass_kg": _rounded(empty_mass),
            "max_fuel_mass_kg": _rounded(max_fuel_mass),
            "oil_mass_kg": _rounded(oil_mass),
            "passport_mass_kg": _rounded(passport_mass) if passport_mass and passport_mass > 0 else None,
            "note": (
                "mass is useful evidence for converting structural overload force into a G candidate; "
                "payload mass is not included here"
            )
            if empty_mass is not None
            else None,
        }
    )


def _candidate_overload(fm: dict[str, Any]) -> dict[str, Any]:
    strength_overload = _get_path(fm, "Aerodynamics", "WingPlane", "Strength", "CritOverload")
    mass_overload = _get_path(fm, "Mass", "WingCritOverload")
    raw_overload = strength_overload if isinstance(strength_overload, list) else mass_overload
    source = (
        "Aerodynamics.WingPlane.Strength.CritOverload"
        if isinstance(strength_overload, list)
        else "Mass.WingCritOverload"
        if isinstance(mass_overload, list)
        else None
    )
    negative_force = _num(raw_overload[0]) if isinstance(raw_overload, list) and len(raw_overload) >= 1 else None
    positive_force = _num(raw_overload[1]) if isinstance(raw_overload, list) and len(raw_overload) >= 2 else None
    empty_mass = _num(_get_path(fm, "Mass", "EmptyMass"))
    max_fuel_mass = _num(_get_path(fm, "Mass", "MaxFuelMass0")) or 0.0
    full_fuel_mass = empty_mass + max_fuel_mass if empty_mass is not None else None
    instructor_limits = _get_path(fm, "Instructor", "loadFactorLimit")
    instructor_negative = _num(instructor_limits[0]) if isinstance(instructor_limits, list) and len(instructor_limits) >= 1 else None
    instructor_positive = _num(instructor_limits[1]) if isinstance(instructor_limits, list) and len(instructor_limits) >= 2 else None

    def force_to_g(force: float | None, mass: float | None) -> float | None:
        if force is None or mass is None or mass <= 0:
            return None
        return abs(force) / mass / 9.80665

    return _dict_without_none(
        {
            "source_fields": [source] if source else None,
            "structure_overload_negative_n": _rounded(negative_force),
            "structure_overload_positive_n": _rounded(positive_force),
            "g_limit_negative_empty_candidate": _rounded(force_to_g(negative_force, empty_mass), 2),
            "g_limit_positive_empty_candidate": _rounded(force_to_g(positive_force, empty_mass), 2),
            "g_limit_negative_full_fuel_candidate": _rounded(force_to_g(negative_force, full_fuel_mass), 2),
            "g_limit_positive_full_fuel_candidate": _rounded(force_to_g(positive_force, full_fuel_mass), 2),
            "instructor_g_limit_negative": _rounded(instructor_negative, 2),
            "instructor_g_limit_positive": _rounded(instructor_positive, 2),
            "instructor_limit_overload": _get_path(fm, "Instructor", "limitOverload"),
            "note": (
                "CritOverload/WingCritOverload is structural force evidence, not a direct spoken G alert; "
                "candidate G values use empty/full-fuel mass and exclude payload"
            )
            if source
            else None,
        }
    )


def _engine_performance_evidence(fm: dict[str, Any]) -> dict[str, Any]:
    engines: list[dict[str, Any]] = []
    total_idle = 0.0
    total_half = 0.0
    total_full = 0.0
    total_wep = 0.0
    saw_idle = saw_half = saw_full = saw_wep = False
    max_inertia: float | None = None
    for key, value in sorted(fm.items()):
        if not key.startswith("EngineType") or not isinstance(value, dict):
            continue
        main = value.get("Main") if isinstance(value.get("Main"), dict) else {}
        idle = _num(main.get("FuelConsumptionOnIdle"))
        half = _num(main.get("FuelConsumptionOnHalfThr"))
        full = _num(main.get("FuelConsumptionOnFullThr"))
        wep = _num(main.get("FuelConsumptionOnWEP"))
        inertia = _num(main.get("EngineInertiaMoment"))
        if idle is not None:
            total_idle += idle
            saw_idle = True
        if half is not None:
            total_half += half
            saw_half = True
        if full is not None:
            total_full += full
            saw_full = True
        if wep is not None:
            total_wep += wep
            saw_wep = True
        if inertia is not None:
            max_inertia = max(inertia, max_inertia) if max_inertia is not None else inertia
        row = _dict_without_none(
            {
                "engine": key,
                "engine_type": main.get("Type"),
                "fuel_consumption_idle": _rounded(idle, 4),
                "fuel_consumption_half": _rounded(half, 4),
                "fuel_consumption_full": _rounded(full, 4),
                "fuel_consumption_wep": _rounded(wep, 4),
                "engine_inertia_moment": _rounded(inertia, 4),
            }
        )
        if row:
            engines.append(row)
    return _dict_without_none(
        {
            "source_fields": [
                "EngineType*.Main.FuelConsumptionOnIdle",
                "EngineType*.Main.FuelConsumptionOnHalfThr",
                "EngineType*.Main.FuelConsumptionOnFullThr",
                "EngineType*.Main.FuelConsumptionOnWEP",
                "EngineType*.Main.EngineInertiaMoment",
            ],
            "engine_count": len(engines) or None,
            "engines": engines or None,
            "fuel_consumption_idle_total": _rounded(total_idle, 4) if saw_idle else None,
            "fuel_consumption_half_total": _rounded(total_half, 4) if saw_half else None,
            "fuel_consumption_full_total": _rounded(total_full, 4) if saw_full else None,
            "fuel_consumption_wep_total": _rounded(total_wep, 4) if saw_wep else None,
            "engine_inertia_moment_max": _rounded(max_inertia, 4),
            "note": (
                "fuel consumption values are Datamine engine-model units; keep as evidence until runtime "
                "fuel-time estimates are calibrated"
            )
            if engines
            else None,
        }
    )


def _mode_temperatures(temp: dict[str, Any]) -> dict[str, Any]:
    max_water: float | None = None
    max_oil: float | None = None
    max_head: float | None = None
    for key, value in temp.items():
        if not key.startswith("Mode") or not isinstance(value, dict):
            continue
        water = _num(value.get("WaterTemperature"))
        oil = _num(value.get("OilTemperature"))
        head = _num(value.get("HeadTemperature"))
        max_water = max(filter(lambda x: x is not None, [max_water, water]), default=None)
        max_oil = max(filter(lambda x: x is not None, [max_oil, oil]), default=None)
        max_head = max(filter(lambda x: x is not None, [max_head, head]), default=None)
    return _dict_without_none(
        {
            "max_mode_water_temperature_c": _rounded(max_water),
            "max_mode_oil_temperature_c": _rounded(max_oil),
            "max_mode_head_temperature_c": _rounded(max_head),
        }
    )


def _load_rows(temp: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in sorted(temp.items()):
        if not key.startswith("Load") or not isinstance(value, dict):
            continue
        suffix = key.removeprefix("Load")
        try:
            index = int(suffix)
        except ValueError:
            index = len(rows)
        rows.append(
            _dict_without_none(
                {
                    "name": key,
                    "index": index,
                    "water_temperature_c": _rounded(_num(value.get("WaterTemperature"))),
                    "oil_temperature_c": _rounded(_num(value.get("OilTemperature"))),
                    "head_temperature_c": _rounded(_num(value.get("HeadTemperature"))),
                    "work_time_sec": _rounded(_num(value.get("WorkTime"))),
                    "recover_time_sec": _rounded(_num(value.get("RecoverTime"))),
                }
            )
        )
    return sorted(rows, key=lambda item: item.get("index", 0))


def _first_temperature_at_or_below_work_time(
    rows: list[dict[str, Any]],
    field: str,
    max_work_time_sec: float,
) -> float | None:
    for row in rows:
        value = _num(row.get(field))
        work_time = _num(row.get("work_time_sec"))
        if value is not None and work_time is not None and work_time <= max_work_time_sec:
            return value
    return None


def _max_temperature(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [_num(row.get(field)) for row in rows]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _load_temperature_thresholds(engine_type: str | None, is_water_cooled: bool | None, temp: dict[str, Any]) -> dict[str, Any]:
    rows = _load_rows(temp)
    if not rows:
        return {}

    primary_field = "water_temperature_c"
    primary_warn = _first_temperature_at_or_below_work_time(rows, primary_field, 1800.0)
    primary_critical = _max_temperature(rows, primary_field)
    oil_warn = _first_temperature_at_or_below_work_time(rows, "oil_temperature_c", 900.0)
    oil_critical = _first_temperature_at_or_below_work_time(rows, "oil_temperature_c", 300.0)
    if oil_critical is None:
        oil_critical = _max_temperature(rows, "oil_temperature_c")

    fields: dict[str, Any] = {}
    if engine_type == "Jet":
        fields.update(
            {
                "turbine_temp_warn_c": _rounded(primary_warn),
                "turbine_temp_critical_c": _rounded(primary_critical),
            }
        )
    elif is_water_cooled:
        fields.update(
            {
                "water_temp_warn_c": _rounded(primary_warn),
                "water_temp_critical_c": _rounded(primary_critical),
            }
        )
    else:
        fields.update(
            {
                "head_temp_warn_c": _rounded(primary_warn),
                "head_temp_critical_c": _rounded(primary_critical),
            }
        )

    fields.update(
        {
            "oil_temp_warn_c": _rounded(oil_warn),
            "oil_temp_critical_c": _rounded(oil_critical),
        }
    )
    return _dict_without_none(fields)


def _engine_temperature_evidence(fm: dict[str, Any]) -> list[dict[str, Any]]:
    engines: list[dict[str, Any]] = []
    for key, value in sorted(fm.items()):
        if not key.startswith("EngineType") or not isinstance(value, dict):
            continue
        temp = value.get("Temperature")
        if not isinstance(temp, dict):
            continue
        main = value.get("Main") if isinstance(value.get("Main"), dict) else {}
        row = _dict_without_none(
            {
                "engine": key,
                "engine_type": main.get("Type"),
                "is_water_cooled": main.get("IsWaterCooled"),
                "water_boiling_temperature_c": _rounded(_num(temp.get("WaterBoilingTemperature"))),
                "oil_boiling_temperature_c": _rounded(_num(temp.get("OilBoilingTemperature"))),
                "water_thermostat_set_point_c": _rounded(_num(temp.get("WaterThermostatSetPoint"))),
                "oil_thermostat_set_point_c": _rounded(_num(temp.get("OilThermostatSetPoint"))),
                "water_temperature_no_flow_c": _rounded(_num(temp.get("WaterTemperatureNoFlow"))),
                "oil_temperature_no_flow_c": _rounded(_num(temp.get("OilTemperatureNoFlow"))),
                "cooling_effective_air_speed": _rounded(_num(temp.get("CoolingEffectiveAirSpeed"))),
            }
        )
        row.update(_mode_temperatures(temp))
        load_rows = _load_rows(temp)
        if load_rows:
            row["load_temperatures"] = load_rows
            row["candidate_thresholds"] = _load_temperature_thresholds(
                main.get("Type") if isinstance(main.get("Type"), str) else None,
                main.get("IsWaterCooled") if isinstance(main.get("IsWaterCooled"), bool) else None,
                temp,
            )
        engines.append(row)
    return engines


def _overheat_evidence(unit: dict[str, Any] | None, fm: dict[str, Any]) -> dict[str, Any]:
    overheat_blk = unit.get("overheatBlk") if isinstance(unit, dict) else None
    engines = _engine_temperature_evidence(fm)
    return _dict_without_none(
        {
            "overheat_blk": overheat_blk,
            "engine_temperature_evidence": engines or None,
            "note": (
                "Datamine exposes thermal model parameters, not a direct HUD warning threshold; "
                "keep this report-only until live overheat samples validate warning/critical lines"
            ),
        }
    )


def extract_candidates(
    vehicle: str,
    *,
    unit: dict[str, Any] | None,
    fm: dict[str, Any],
    files: DatamineFiles | None = None,
) -> dict[str, Any]:
    """Build a source-rich candidate profile for one vehicle."""

    report = {
        "vehicle": vehicle,
        "datamine": _dict_without_none(
            {
                "unit_url": files.unit_url if files else None,
                "fm_url": files.fm_url if files else None,
                "fm_file": unit.get("fmFile") if isinstance(unit, dict) else None,
            }
        ),
        "stall": _candidate_stall(fm),
        "aoa": _candidate_aoa(fm),
        "overspeed": _candidate_overspeed(fm),
        "mass": _candidate_mass(fm),
        "overload": _candidate_overload(fm),
        "engine_performance": _engine_performance_evidence(fm),
        "overheat": _overheat_evidence(unit, fm),
    }
    return report


def fetch_vehicle(vehicle: str, *, ref: str = DEFAULT_REF) -> dict[str, Any]:
    unit_url = _url(ref, f"aces.vromfs.bin_u/gamedata/flightmodels/{vehicle}.blkx")
    fm_url = _url(ref, f"aces.vromfs.bin_u/gamedata/flightmodels/fm/{vehicle}.blkx")
    unit_error = None
    try:
        unit: dict[str, Any] | None = _load_json_url(unit_url)
    except RuntimeError as exc:
        unit = None
        unit_error = str(exc)
    fm = _load_json_url(fm_url)
    report = extract_candidates(vehicle, unit=unit, fm=fm, files=DatamineFiles(vehicle, unit_url, fm_url))
    if unit_error is not None:
        report["datamine"]["unit_error"] = unit_error
    return report


def iter_profile_vehicle_ids(profile_path: pathlib.Path) -> Iterable[str]:
    profiles = _load_json_file(profile_path)
    for key, value in profiles.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        yield key


def _write_report(report: dict[str, Any], output: pathlib.Path | None) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"wrote {output}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicle", action="append", dest="vehicles", help="Datamine vehicle id; repeatable")
    parser.add_argument(
        "--from-profiles",
        type=pathlib.Path,
        help="Read exact vehicle ids from vehicle_profiles.json. This may fetch many files.",
    )
    parser.add_argument("--ref", default=DEFAULT_REF, help="Datamine git ref/branch (default: master)")
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("local_test_logs/datamine_profile_candidates.json"),
        help="Report path. Use '-' for stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    vehicles = list(args.vehicles or [])
    if args.from_profiles is not None:
        vehicles.extend(iter_profile_vehicle_ids(args.from_profiles))
    if not vehicles:
        vehicles = list(DEFAULT_VEHICLES)

    unique_vehicles = list(dict.fromkeys(vehicles))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for vehicle in unique_vehicles:
        try:
            results.append(fetch_vehicle(vehicle, ref=args.ref))
        except RuntimeError as exc:
            errors.append({"vehicle": vehicle, "error": str(exc)})

    report = {
        "source": "gszabi99/War-Thunder-Datamine",
        "ref": args.ref,
        "status": "candidate_report_only",
        "vehicles_requested": len(unique_vehicles),
        "vehicles_ok": len(results),
        "vehicles_failed": len(errors),
        "results": results,
        "errors": errors,
    }
    output = None if str(args.output) == "-" else args.output
    _write_report(report, output)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
