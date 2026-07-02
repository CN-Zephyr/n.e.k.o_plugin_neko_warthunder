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
