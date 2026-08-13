"""Backfill small official economy/rank metadata into vehicle_profiles.json.

This intentionally reads only compact metadata from a local
gszabi99/War-Thunder-Datamine checkout:

* rank
* economicRankArcade / economicRankHistorical / economicRankSimulation
* country
* unitClass
* unitMoveType

It does not import cost tables, rewards, weapon prices, modifications, or
large economy blobs. Existing exact profile entries are updated in place; no
new profile aliases are created.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
from typing import Any


BASE = pathlib.Path(__file__).resolve().parent.parent
DATA_PROCESS = BASE / "data_layer" / "data_process"
DEFAULT_PROFILES = DATA_PROCESS / "vehicle_profiles.json"
DEFAULT_REPORT = BASE / "local_test_logs" / "vehicle_profiles_economy_update.json"
DEFAULT_DATAMINE_ROOT = pathlib.Path(os.environ.get("WT_DATAMINE_ROOT", "")) if os.environ.get("WT_DATAMINE_ROOT") else None

FIELD_MAP = (
    ("rank", "rank"),
    ("economicRankArcade", "economic_rank_arcade"),
    ("economicRankHistorical", "economic_rank_realistic"),
    ("economicRankSimulation", "economic_rank_simulation"),
    ("country", "country"),
    ("unitClass", "unit_class"),
    ("unitMoveType", "unit_move_type"),
)


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _compact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _config_root(datamine_root: pathlib.Path) -> pathlib.Path:
    candidates = [
        datamine_root,
        datamine_root / "char.vromfs.bin_u" / "config",
    ]
    for root in candidates:
        if (root / "wpcost.blkx").is_file():
            return root.resolve()
    raise FileNotFoundError(f"could not find char.vromfs.bin_u/config/wpcost.blkx under {datamine_root}")


def _normalize_country(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.removeprefix("country_")


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if int(value) != value:
        return None
    return int(value)


def _safe_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _metadata_from_wpcost(record: dict[str, Any]) -> dict[str, int | str]:
    fields: dict[str, int | str] = {}
    for source, target in FIELD_MAP:
        value = record.get(source)
        if target == "country":
            normalized = _normalize_country(value)
            if normalized is not None:
                fields[target] = normalized
            continue
        if target in {"unit_class", "unit_move_type"}:
            text = _safe_str(value)
            if text is not None:
                fields[target] = text
            continue
        number = _safe_int(value)
        if number is not None:
            fields[target] = number
    return fields


def _existing_profile_ids_by_compact_name(profiles: dict[str, Any]) -> dict[str, list[str]]:
    by_compact: dict[str, list[str]] = {}
    for profile_id, entry in profiles.items():
        if profile_id.startswith("_") or not isinstance(entry, dict):
            continue
        by_compact.setdefault(_compact_name(profile_id), []).append(profile_id)
    return by_compact


def _target_profile_ids(
    profiles: dict[str, Any],
    by_compact: dict[str, list[str]],
    vehicle_id: str,
) -> list[str]:
    targets: list[str] = []

    def add(candidate: str) -> None:
        if candidate not in targets:
            targets.append(candidate)

    if isinstance(profiles.get(vehicle_id), dict):
        add(vehicle_id)
    for candidate in by_compact.get(_compact_name(vehicle_id), []):
        add(candidate)
    return targets


def update_profiles(
    *,
    profiles_path: pathlib.Path,
    datamine_root: pathlib.Path,
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    profiles = _load_json(profiles_path)
    config_root = _config_root(datamine_root)
    wpcost = _load_json(config_root / "wpcost.blkx")
    by_compact = _existing_profile_ids_by_compact_name(profiles)

    scanned = 0
    air_records = 0
    matched_records = 0
    updated: list[str] = []
    skipped_non_air: list[str] = []
    skipped_no_profile: list[str] = []
    added_fields = 0
    preserved_fields = 0

    for vehicle_id, record in sorted(wpcost.items()):
        if not isinstance(record, dict):
            continue
        scanned += 1
        if record.get("unitMoveType") != "air":
            skipped_non_air.append(vehicle_id)
            continue
        air_records += 1
        fields = _metadata_from_wpcost(record)
        if not fields:
            continue
        targets = _target_profile_ids(profiles, by_compact, vehicle_id)
        if not targets:
            skipped_no_profile.append(vehicle_id)
            continue
        matched_records += 1
        for target_id in targets:
            entry = profiles.get(target_id)
            if not isinstance(entry, dict):
                continue
            changed = False
            for field, value in fields.items():
                if field in entry and not overwrite_existing:
                    preserved_fields += 1
                    continue
                if entry.get(field) != value:
                    entry[field] = value
                    changed = True
                    added_fields += 1
            if changed and target_id not in updated:
                updated.append(target_id)

    _write_json(profiles_path, profiles)
    exact_entries = {
        key: value
        for key, value in profiles.items()
        if not key.startswith("_") and isinstance(value, dict)
    }
    coverage = {
        "exact_entries": len(exact_entries),
        "rank": sum(1 for entry in exact_entries.values() if "rank" in entry),
        "economic_rank_realistic": sum(1 for entry in exact_entries.values() if "economic_rank_realistic" in entry),
        "country": sum(1 for entry in exact_entries.values() if "country" in entry),
        "unit_class": sum(1 for entry in exact_entries.values() if "unit_class" in entry),
    }
    return {
        "status": "updated",
        "profiles": str(profiles_path),
        "datamine_root": str(config_root),
        "policy": {
            "overwrite_existing": overwrite_existing,
            "source": "gszabi99/War-Thunder-Datamine char.vromfs.bin_u/config/wpcost.blkx",
            "scope": "existing exact air profiles only",
            "excluded": ["cost tables", "reward multipliers", "weapons", "modifications"],
        },
        "scanned": scanned,
        "air_records": air_records,
        "matched_records": matched_records,
        "updated": len(updated),
        "fields_added_or_refreshed": added_fields,
        "fields_preserved": preserved_fields,
        "skipped_non_air": len(skipped_non_air),
        "skipped_no_profile": len(skipped_no_profile),
        "coverage": coverage,
        "updated_vehicle_ids": updated,
        "skipped_no_profile_vehicle_ids": skipped_no_profile,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=pathlib.Path, default=DEFAULT_PROFILES)
    parser.add_argument(
        "--datamine-root",
        type=pathlib.Path,
        default=DEFAULT_DATAMINE_ROOT,
        required=DEFAULT_DATAMINE_ROOT is None,
        help="War-Thunder-Datamine root, or char.vromfs.bin_u/config.",
    )
    parser.add_argument("--overwrite-existing", action="store_true", help="Refresh existing economy metadata fields too.")
    parser.add_argument("--report", type=pathlib.Path, default=DEFAULT_REPORT, help="Maintenance report path.")
    parser.add_argument("--json", action="store_true", help="Print the summary JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = update_profiles(
        profiles_path=args.profiles,
        datamine_root=args.datamine_root,
        overwrite_existing=args.overwrite_existing,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        coverage = report["coverage"]
        print(
            "updated vehicle profile economy metadata: "
            f"air_records={report['air_records']} matched={report['matched_records']} "
            f"updated={report['updated']} rank_coverage={coverage['rank']}/{coverage['exact_entries']}"
        )
        print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
