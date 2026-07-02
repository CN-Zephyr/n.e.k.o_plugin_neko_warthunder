"""Bulk-update vehicle_profiles.json from a local War Thunder Datamine checkout.

The updater is intentionally conservative:

* reads local gszabi99/War-Thunder-Datamine files only;
* adds missing exact aircraft entries and missing candidate fields;
* preserves existing fields by default, including live-tested calibration;
* writes a safe maintenance report under local_test_logs by default.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Any, Iterable


BASE = pathlib.Path(__file__).resolve().parent.parent
DATA_PROCESS = BASE / "data_layer" / "data process"
if str(DATA_PROCESS) not in sys.path:
    sys.path.insert(0, str(DATA_PROCESS))
if str(BASE / "tools") not in sys.path:
    sys.path.insert(0, str(BASE / "tools"))

import datamine_profile_candidates as candidates  # noqa: E402


DEFAULT_PROFILES = DATA_PROCESS / "vehicle_profiles.json"
DEFAULT_REPORT = BASE / "local_test_logs" / "vehicle_profiles_datamine_update.json"
DEFAULT_DATAMINE_ROOT = pathlib.Path(os.environ.get("WT_DATAMINE_ROOT", "")) if os.environ.get("WT_DATAMINE_ROOT") else None

PROFILE_FIELD_ORDER = (
    "stall_warn_kmh",
    "stall_critical_kmh",
    "overspeed_warn_kmh",
    "overspeed_critical_kmh",
    "overspeed_warn_mach",
    "overspeed_critical_mach",
    "aoa_warn_deg",
    "aoa_critical_deg",
    "turbine_temp_warn_c",
    "turbine_temp_critical_c",
    "water_temp_warn_c",
    "water_temp_critical_c",
    "head_temp_warn_c",
    "head_temp_critical_c",
    "oil_temp_warn_c",
    "oil_temp_critical_c",
    "empty_mass_kg",
    "max_fuel_mass_kg",
    "structure_overload_negative_n",
    "structure_overload_positive_n",
    "g_limit_negative_empty_candidate",
    "g_limit_positive_empty_candidate",
    "g_limit_negative_full_fuel_candidate",
    "g_limit_positive_full_fuel_candidate",
    "instructor_g_limit_negative",
    "instructor_g_limit_positive",
    "fuel_consumption_idle_total",
    "fuel_consumption_half_total",
    "fuel_consumption_full_total",
    "fuel_consumption_wep_total",
    "engine_inertia_moment_max",
)

TESTED_ENTRY_EVIDENCE_FIELDS = frozenset(
    {
        "empty_mass_kg",
        "max_fuel_mass_kg",
        "structure_overload_negative_n",
        "structure_overload_positive_n",
        "g_limit_negative_empty_candidate",
        "g_limit_positive_empty_candidate",
        "g_limit_negative_full_fuel_candidate",
        "g_limit_positive_full_fuel_candidate",
        "instructor_g_limit_negative",
        "instructor_g_limit_positive",
        "fuel_consumption_idle_total",
        "fuel_consumption_half_total",
        "fuel_consumption_full_total",
        "fuel_consumption_wep_total",
        "engine_inertia_moment_max",
    }
)

JET_CLASSES = {
    "early_jet",
    "transonic_jet",
    "early_supersonic_jet",
    "attacker_jet",
    "subsonic_attacker_jet",
    "supersonic_attacker_jet",
    "modern_jet",
    "modern_high_alpha_fighter",
    "heavy_modern_fighter",
    "jet_bomber",
}
LEGACY_JET_CLASSES = {"early_jet", "attacker_jet", "modern_jet"}
SKIP_PREFIXES = ("uav_", "ucav_")
ROTORCRAFT_COMPACT_PREFIXES = (
    "a109",
    "a129",
    "ab205",
    "ah1",
    "ah2",
    "ah56",
    "ah60",
    "ah64",
    "bo105",
    "glynx",
    "h34",
    "hkp",
    "iar316",
    "ka29",
    "ka50",
    "ka52",
    "lynx",
    "md500",
    "mh60",
    "mi24",
    "mi28",
    "mi35",
    "mi8",
    "oh58",
    "rah66",
    "sa313",
    "sa316",
    "sa341",
    "sa342",
    "scout",
    "superhind",
    "t129",
    "tiger",
    "uh1",
    "wasp",
    "wessex",
    "yah64",
    "z10",
    "z11",
    "z19",
    "z9",
)
CLASS_PREFIX_HINTS: tuple[tuple[str, str], ...] = (
    ("seaharrier", "subsonic_attacker_jet"),
    ("harrier", "subsonic_attacker_jet"),
    ("av8", "subsonic_attacker_jet"),
    ("a10", "subsonic_attacker_jet"),
    ("su25", "subsonic_attacker_jet"),
    ("buccaneer", "subsonic_attacker_jet"),
    ("a4", "supersonic_attacker_jet"),
    ("a7", "supersonic_attacker_jet"),
    ("su24", "supersonic_attacker_jet"),
    ("su34", "supersonic_attacker_jet"),
    ("jaguar", "supersonic_attacker_jet"),
    ("q5", "supersonic_attacker_jet"),
    ("jh7", "supersonic_attacker_jet"),
    ("tornado", "supersonic_attacker_jet"),
    ("b52", "jet_bomber"),
    ("tu95", "jet_bomber"),
    ("b57", "jet_bomber"),
    ("canberra", "jet_bomber"),
    ("f14", "heavy_modern_fighter"),
    ("f15", "heavy_modern_fighter"),
    ("su30", "heavy_modern_fighter"),
    ("su33", "heavy_modern_fighter"),
    ("f16", "modern_high_alpha_fighter"),
    ("fa18", "modern_high_alpha_fighter"),
    ("f18", "modern_high_alpha_fighter"),
    ("cf188", "modern_high_alpha_fighter"),
    ("mig29", "modern_high_alpha_fighter"),
    ("su27", "modern_high_alpha_fighter"),
    ("ef2000", "modern_high_alpha_fighter"),
    ("mirage2000", "modern_high_alpha_fighter"),
    ("rafale", "modern_high_alpha_fighter"),
    ("jas39", "modern_high_alpha_fighter"),
    ("gripen", "modern_high_alpha_fighter"),
    ("j11", "modern_high_alpha_fighter"),
    ("j10", "modern_high_alpha_fighter"),
    ("yak141", "modern_high_alpha_fighter"),
    ("saabjas39", "modern_high_alpha_fighter"),
    ("mig21", "early_supersonic_jet"),
    ("mig23", "early_supersonic_jet"),
    ("mig25", "early_supersonic_jet"),
    ("mirage", "early_supersonic_jet"),
    ("kfir", "early_supersonic_jet"),
    ("j8", "early_supersonic_jet"),
    ("j7", "early_supersonic_jet"),
    ("f100", "early_supersonic_jet"),
    ("f104", "early_supersonic_jet"),
    ("f105", "early_supersonic_jet"),
    ("f4", "early_supersonic_jet"),
    ("f5", "early_supersonic_jet"),
    ("lightning", "early_supersonic_jet"),
    ("f86", "transonic_jet"),
    ("mig15", "transonic_jet"),
    ("mig17", "transonic_jet"),
    ("f84", "transonic_jet"),
    ("meteor", "transonic_jet"),
    ("vampire", "transonic_jet"),
    ("hunter", "transonic_jet"),
)

FIELD_RANGES = {
    "stall_warn_kmh": (20, 500),
    "stall_critical_kmh": (20, 450),
    "overspeed_warn_kmh": (100, 2500),
    "overspeed_critical_kmh": (100, 2600),
    "overspeed_warn_mach": (0.2, 3.5),
    "overspeed_critical_mach": (0.2, 3.8),
    "aoa_warn_deg": (4, 60),
    "aoa_critical_deg": (5, 70),
    "turbine_temp_warn_c": (300, 1300),
    "turbine_temp_critical_c": (300, 1400),
    "water_temp_warn_c": (60, 180),
    "water_temp_critical_c": (60, 220),
    "head_temp_warn_c": (100, 320),
    "head_temp_critical_c": (100, 360),
    "oil_temp_warn_c": (50, 160),
    "oil_temp_critical_c": (50, 180),
    "empty_mass_kg": (100, 400000),
    "max_fuel_mass_kg": (0, 250000),
    "structure_overload_negative_n": (-10000000, -1000),
    "structure_overload_positive_n": (1000, 20000000),
    "g_limit_negative_empty_candidate": (0.5, 30),
    "g_limit_positive_empty_candidate": (0.5, 40),
    "g_limit_negative_full_fuel_candidate": (0.5, 30),
    "g_limit_positive_full_fuel_candidate": (0.5, 40),
    "instructor_g_limit_negative": (-20, 0),
    "instructor_g_limit_positive": (0, 20),
    "fuel_consumption_idle_total": (0, 1000),
    "fuel_consumption_half_total": (0, 1000),
    "fuel_consumption_full_total": (0, 1000),
    "fuel_consumption_wep_total": (0, 1000),
    "engine_inertia_moment_max": (0, 100000),
}


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _round_value(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    rounded = round(float(value), 2)
    return int(rounded) if rounded.is_integer() else rounded


def _in_range(field: str, value: int | float) -> bool:
    lo, hi = FIELD_RANGES[field]
    return lo <= float(value) <= hi


def _compact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _class_candidate_names(vehicle_id: str, unit: dict[str, Any] | None) -> list[str]:
    names = [vehicle_id]
    if isinstance(unit, dict):
        model = unit.get("model")
        if isinstance(model, str):
            names.append(model)
        fm_file = unit.get("fmFile")
        if isinstance(fm_file, str):
            stem = pathlib.Path(fm_file.replace("\\", "/")).stem
            if stem:
                names.append(stem)

    compact_names: list[str] = []
    for name in names:
        compact = _compact_name(name)
        if compact and compact not in compact_names:
            compact_names.append(compact)
        for prefix in ("nt", "ai"):
            if compact.startswith(prefix) and len(compact) > len(prefix):
                stripped = compact[len(prefix) :]
                if stripped and stripped not in compact_names:
                    compact_names.append(stripped)
    return compact_names


def _flightmodels_root(datamine_root: pathlib.Path) -> pathlib.Path:
    candidates_roots = [
        datamine_root,
        datamine_root / "aces.vromfs.bin_u" / "gamedata" / "flightmodels",
    ]
    for root in candidates_roots:
        if (root / "fm").is_dir():
            return root.resolve()
    raise FileNotFoundError(f"could not find gamedata/flightmodels under {datamine_root}")


def _resolve_fm_path(flightmodels_root: pathlib.Path, vehicle_id: str, unit: dict[str, Any] | None) -> pathlib.Path | None:
    fm_file = unit.get("fmFile") if isinstance(unit, dict) else None
    if isinstance(fm_file, str) and fm_file:
        normalized = fm_file.replace("\\", "/")
        if normalized.lower().endswith(".blk"):
            normalized = normalized[:-4] + ".blkx"
        path = flightmodels_root / normalized
        if path.exists():
            return path
    direct = flightmodels_root / "fm" / f"{vehicle_id}.blkx"
    if direct.exists():
        return direct
    return None


def iter_aircraft_records(flightmodels_root: pathlib.Path) -> Iterable[tuple[str, dict[str, Any] | None, pathlib.Path]]:
    referenced_fm: set[pathlib.Path] = set()
    for unit_path in sorted(flightmodels_root.glob("*.blkx")):
        try:
            unit = _load_json(unit_path)
        except (OSError, json.JSONDecodeError):
            continue
        vehicle_id = unit_path.stem
        fm_path = _resolve_fm_path(flightmodels_root, vehicle_id, unit)
        if fm_path is None:
            continue
        referenced_fm.add(fm_path.resolve())
        if _should_skip_vehicle(vehicle_id, unit):
            continue
        yield vehicle_id, unit, fm_path

    for fm_path in sorted((flightmodels_root / "fm").glob("*.blkx")):
        if fm_path.resolve() in referenced_fm:
            continue
        if _should_skip_vehicle(fm_path.stem, None):
            continue
        yield fm_path.stem, None, fm_path


def _should_skip_vehicle(vehicle_id: str, unit: dict[str, Any] | None) -> bool:
    compact = vehicle_id.lower()
    if compact.startswith(SKIP_PREFIXES) or compact in {"dummy_plane"}:
        return True
    compact_id = _compact_name(vehicle_id)
    if any(compact_id.startswith(prefix) for prefix in ROTORCRAFT_COMPACT_PREFIXES):
        return True
    if isinstance(unit, dict) and "helicopter" in unit:
        return True
    return False


def _engine_types(report: dict[str, Any]) -> set[str]:
    overheat = report.get("overheat") if isinstance(report.get("overheat"), dict) else {}
    engines = overheat.get("engine_temperature_evidence") if isinstance(overheat, dict) else None
    if not isinstance(engines, list):
        return set()
    return {
        engine["engine_type"]
        for engine in engines
        if isinstance(engine, dict) and isinstance(engine.get("engine_type"), str)
    }


def _infer_profile_class(vehicle_id: str, unit: dict[str, Any] | None, report: dict[str, Any]) -> str | None:
    compact_ids = _class_candidate_names(vehicle_id, unit)
    for prefix, profile_class in CLASS_PREFIX_HINTS:
        if any(compact_id.startswith(prefix) for compact_id in compact_ids):
            return profile_class

    unit_type = unit.get("type") if isinstance(unit, dict) else None
    engine_types = _engine_types(report)
    is_jet = "Jet" in engine_types
    overspeed = report.get("overspeed") if isinstance(report.get("overspeed"), dict) else {}
    vne = _round_value(overspeed.get("overspeed_critical_kmh")) if isinstance(overspeed, dict) else None
    mne = _round_value(overspeed.get("overspeed_critical_mach")) if isinstance(overspeed, dict) else None

    if unit_type == "typeBomber":
        return "jet_bomber" if is_jet else "ww2_bomber"
    if unit_type == "typeStormovik":
        if is_jet:
            if (isinstance(mne, (int, float)) and mne >= 1.0) or (isinstance(vne, (int, float)) and vne >= 1050):
                return "supersonic_attacker_jet"
            return "subsonic_attacker_jet"
        return "ww2_bomber"
    if unit_type == "typeFighter":
        if is_jet:
            if (isinstance(mne, (int, float)) and mne >= 1.35) or (isinstance(vne, (int, float)) and vne >= 1450):
                return "modern_high_alpha_fighter"
            if (isinstance(mne, (int, float)) and mne >= 1.0) or (isinstance(vne, (int, float)) and vne >= 1120):
                return "early_supersonic_jet"
            return "transonic_jet"
        if isinstance(vne, (int, float)) and vne <= 500:
            return "biplane"
        return "ww2_prop_fighter"
    if is_jet:
        if (isinstance(mne, (int, float)) and mne >= 1.35) or (isinstance(vne, (int, float)) and vne >= 1450):
            return "modern_high_alpha_fighter"
        if (isinstance(mne, (int, float)) and mne >= 1.0) or (isinstance(vne, (int, float)) and vne >= 1120):
            return "early_supersonic_jet"
        return "transonic_jet"
    return None


def _should_refresh_class(entry: dict[str, Any], inferred_class: str | None) -> bool:
    if not inferred_class:
        return False
    current = entry.get("class")
    if not isinstance(current, str):
        return True
    if current == inferred_class:
        return False
    # Only migrate broad legacy jet buckets into the newer performance bands.
    # Exact thresholds and live-tested fields remain governed by overwrite rules.
    return current in JET_CLASSES and inferred_class in JET_CLASSES


def _class_defaults(profiles: dict[str, Any], profile_class: str | None) -> dict[str, Any]:
    if not profile_class:
        return {}
    template = profiles.get("_classes", {}).get(profile_class)
    return template if isinstance(template, dict) else {}


def _family_fallback_fields(profiles: dict[str, Any], vehicle_id: str) -> dict[str, Any]:
    families = profiles.get("_families")
    if not isinstance(families, list):
        return {}
    compact_id = _compact_name(vehicle_id)
    best: dict[str, Any] | None = None
    best_len = -1
    for family in families:
        if not isinstance(family, dict) or not isinstance(family.get("prefix"), str):
            continue
        compact_prefix = _compact_name(family["prefix"])
        if compact_prefix and compact_id.startswith(compact_prefix) and len(compact_prefix) > best_len:
            best = family
            best_len = len(compact_prefix)
    if best is None:
        return {}

    merged: dict[str, Any] = {}
    family_class = best.get("class") if isinstance(best.get("class"), str) else None
    class_template = _class_defaults(profiles, family_class)
    for field in PROFILE_FIELD_ORDER:
        if field in class_template:
            merged[field] = class_template[field]
    for field in PROFILE_FIELD_ORDER:
        if field in best:
            merged[field] = best[field]
    return merged


def _target_profile_ids(profiles: dict[str, Any], vehicle_id: str, fm_path: pathlib.Path) -> list[str]:
    """Return existing profile ids that should receive this FM's missing fields.

    Some game `vehicle_type` ids use the FM filename directly while a Datamine
    unit file with a different id references that FM. Preserve the main unit
    behavior, but also backfill already-existing exact entries for the same FM.
    This does not create new aliases.
    """

    targets: list[str] = []

    def add(candidate: str | None) -> None:
        if candidate and candidate not in targets:
            targets.append(candidate)

    add(vehicle_id)
    fm_stem = fm_path.stem
    if isinstance(profiles.get(fm_stem), dict):
        add(fm_stem)

    compact_candidates = {_compact_name(vehicle_id), _compact_name(fm_stem)}
    for key, value in profiles.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        if _compact_name(key) in compact_candidates:
            add(key)
    return targets


def _drop_suspect_jet_overspeed(fields: dict[str, int | float], profile_class: str | None, class_defaults: dict[str, Any]) -> None:
    if profile_class not in JET_CLASSES:
        return
    if "overspeed_critical_mach" in fields:
        return
    critical_kmh = fields.get("overspeed_critical_kmh")
    class_critical = class_defaults.get("overspeed_critical_kmh")
    if not isinstance(critical_kmh, (int, float)) or not isinstance(class_critical, (int, float)):
        return
    if float(critical_kmh) < float(class_critical) * 0.85:
        fields.pop("overspeed_warn_kmh", None)
        fields.pop("overspeed_critical_kmh", None)


def _thermal_fields(report: dict[str, Any]) -> dict[str, int | float]:
    overheat = report.get("overheat") if isinstance(report.get("overheat"), dict) else {}
    engines = overheat.get("engine_temperature_evidence") if isinstance(overheat, dict) else None
    if not isinstance(engines, list):
        return {}

    merged: dict[str, int | float] = {}
    for engine in engines:
        if not isinstance(engine, dict):
            continue
        thresholds = engine.get("candidate_thresholds")
        if not isinstance(thresholds, dict):
            continue
        for field in PROFILE_FIELD_ORDER:
            value = _round_value(thresholds.get(field))
            if value is None or not _in_range(field, value):
                continue
            current = merged.get(field)
            if current is None or float(value) < float(current):
                merged[field] = value
    return merged


def _candidate_group_fields(report: dict[str, Any], group_names: Iterable[str]) -> dict[str, int | float]:
    fields: dict[str, int | float] = {}
    for group_name in group_names:
        group = report.get(group_name)
        if not isinstance(group, dict):
            continue
        for field in PROFILE_FIELD_ORDER:
            if field in fields:
                continue
            value = _round_value(group.get(field))
            if value is not None and _in_range(field, value):
                fields[field] = value
    return fields


def profile_fields_from_candidate(
    report: dict[str, Any],
    *,
    profile_class: str | None = None,
    class_defaults: dict[str, Any] | None = None,
) -> dict[str, int | float]:
    fields: dict[str, int | float] = {}
    fields.update(_candidate_group_fields(report, ("stall", "overspeed", "aoa", "mass", "overload", "engine_performance")))
    _drop_suspect_jet_overspeed(fields, profile_class, class_defaults or {})
    fields.update(_thermal_fields(report))
    return {field: fields[field] for field in PROFILE_FIELD_ORDER if field in fields}


def build_candidate_from_fm(vehicle_id: str, unit: dict[str, Any] | None, fm_path: pathlib.Path) -> dict[str, Any]:
    fm = _load_json(fm_path)
    return candidates.extract_candidates(vehicle_id, unit=unit, fm=fm)


def update_profiles(
    *,
    profiles_path: pathlib.Path,
    datamine_root: pathlib.Path,
    overwrite_existing: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    profiles = _load_json(profiles_path)
    flightmodels_root = _flightmodels_root(datamine_root)
    created: list[str] = []
    updated: list[str] = []
    skipped_empty: list[str] = []
    preserved_fields = 0
    added_fields = 0
    scanned = 0

    for vehicle_id, unit, fm_path in iter_aircraft_records(flightmodels_root):
        if limit is not None and scanned >= limit:
            break
        scanned += 1
        report = build_candidate_from_fm(vehicle_id, unit, fm_path)
        inferred_class = _infer_profile_class(vehicle_id, unit, report)
        class_defaults = _class_defaults(profiles, inferred_class)
        fields = {
            **_family_fallback_fields(profiles, vehicle_id),
            **profile_fields_from_candidate(report, profile_class=inferred_class, class_defaults=class_defaults),
        }
        if not fields:
            skipped_empty.append(vehicle_id)
            continue

        for target_id in _target_profile_ids(profiles, vehicle_id, fm_path):
            entry = profiles.get(target_id)
            if not isinstance(entry, dict):
                if target_id != vehicle_id:
                    continue
                new_entry = dict(fields)
                if inferred_class:
                    new_entry = {"class": inferred_class, **new_entry}
                profiles[target_id] = new_entry
                created.append(target_id)
                added_fields += len(new_entry)
                continue
            changed = False
            if _should_refresh_class(entry, inferred_class):
                entry["class"] = inferred_class
                changed = True
                added_fields += 1
            for field, value in fields.items():
                if field in entry and not overwrite_existing:
                    preserved_fields += 1
                    continue
                if entry.get("_tested") is True and not overwrite_existing and field not in TESTED_ENTRY_EVIDENCE_FIELDS:
                    preserved_fields += 1
                    continue
                if entry.get(field) != value:
                    entry[field] = value
                    changed = True
                    added_fields += 1
            if changed:
                updated.append(target_id)

    _write_json(profiles_path, profiles)
    return {
        "status": "updated",
        "profiles": str(profiles_path),
        "datamine_root": str(flightmodels_root),
        "policy": {
            "overwrite_existing": overwrite_existing,
            "tested_entries_preserved": True,
            "tested_entries_allow_missing_readonly_evidence": True,
            "source": "gszabi99/War-Thunder-Datamine local checkout",
        },
        "scanned": scanned,
        "created": len(created),
        "updated": len(updated),
        "skipped_empty": len(skipped_empty),
        "fields_added_or_refreshed": added_fields,
        "fields_preserved": preserved_fields,
        "created_vehicle_ids": created,
        "updated_vehicle_ids": updated,
        "skipped_empty_vehicle_ids": skipped_empty,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=pathlib.Path, default=DEFAULT_PROFILES)
    parser.add_argument(
        "--datamine-root",
        type=pathlib.Path,
        default=DEFAULT_DATAMINE_ROOT,
        required=DEFAULT_DATAMINE_ROOT is None,
        help="War-Thunder-Datamine root, or aces.vromfs.bin_u/gamedata/flightmodels.",
    )
    parser.add_argument("--overwrite-existing", action="store_true", help="Refresh non-tested existing fields too.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N records, for tests.")
    parser.add_argument("--report", type=pathlib.Path, default=DEFAULT_REPORT, help="Maintenance report path.")
    parser.add_argument("--json", action="store_true", help="Print the summary JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = update_profiles(
        profiles_path=args.profiles,
        datamine_root=args.datamine_root,
        overwrite_existing=args.overwrite_existing,
        limit=args.limit,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "updated vehicle profiles: "
            f"scanned={report['scanned']} created={report['created']} "
            f"updated={report['updated']} preserved_fields={report['fields_preserved']}"
        )
        print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
