"""Compare vehicle_profiles.json against Datamine candidate reports.

The output is a maintenance report. It does not edit the profile database.
Use it to decide which exact/family entries are safe to update from
``tools/datamine_profile_candidates.py`` output.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import types
from dataclasses import dataclass
from typing import Any


BASE = pathlib.Path(__file__).resolve().parent.parent
DATA_PROCESS = BASE / "data_layer" / "data process"
if str(DATA_PROCESS) not in sys.path:
    sys.path.insert(0, str(DATA_PROCESS))
if "neko_warthunder" not in sys.modules:
    pkg = types.ModuleType("neko_warthunder")
    pkg.__path__ = [str(BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = pkg

import datamine_profile_candidates as candidates_tool  # noqa: E402
from wt_processor import TelemetryProcessor, _merge_profile  # noqa: E402


DEFAULT_PROFILES = DATA_PROCESS / "vehicle_profiles.json"
DEFAULT_CANDIDATES = BASE / "local_test_logs" / "datamine_profile_candidates.json"
DEFAULT_OUTPUT = BASE / "local_test_logs" / "profile_candidate_diff.json"


@dataclass(frozen=True)
class FieldRule:
    group: str
    field: str
    tolerance: float


FIELD_RULES = [
    FieldRule("stall", "stall_critical_kmh", 5.0),
    FieldRule("stall", "stall_warn_kmh", 5.0),
    FieldRule("aoa", "aoa_critical_deg", 1.0),
    FieldRule("aoa", "aoa_warn_deg", 1.0),
    FieldRule("overspeed", "overspeed_critical_kmh", 8.0),
    FieldRule("overspeed", "overspeed_warn_kmh", 8.0),
    FieldRule("overspeed", "overspeed_critical_mach", 0.03),
    FieldRule("overspeed", "overspeed_warn_mach", 0.03),
]


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _round_delta(value: float) -> float | int:
    rounded = round(value, 3)
    return int(rounded) if rounded.is_integer() else rounded


def _candidate_records(report: dict[str, Any]) -> list[dict[str, Any]]:
    records = report.get("results", [])
    if not isinstance(records, list):
        raise ValueError("candidate report must contain a list at results")
    return [record for record in records if isinstance(record, dict)]


def _field_compare(cfg: dict[str, Any], candidate: dict[str, Any], rule: FieldRule) -> dict[str, Any] | None:
    group = candidate.get(rule.group)
    if not isinstance(group, dict):
        return None
    candidate_value = _num(group.get(rule.field))
    if candidate_value is None:
        return None
    current_value = _num(cfg.get(rule.field))
    if current_value is None:
        return {
            "field": rule.field,
            "status": "missing_current",
            "current": None,
            "candidate": candidate_value,
            "delta": None,
        }
    delta = candidate_value - current_value
    status = "match" if abs(delta) <= rule.tolerance else "diff"
    return {
        "field": rule.field,
        "status": status,
        "current": current_value,
        "candidate": candidate_value,
        "delta": _round_delta(delta),
    }


def compare_candidate(
    candidate: dict[str, Any],
    *,
    processor: TelemetryProcessor,
) -> dict[str, Any]:
    vehicle = str(candidate.get("vehicle") or "")
    cfg, matched, source, family = _merge_profile(
        processor.profiles,
        vehicle,
        "air",
        processor._family_rules,
    )
    comparisons = [
        comparison
        for rule in FIELD_RULES
        if (comparison := _field_compare(cfg, candidate, rule)) is not None
    ]
    diffs = [item for item in comparisons if item["status"] == "diff"]
    missing = [item for item in comparisons if item["status"] == "missing_current"]
    matches = [item for item in comparisons if item["status"] == "match"]
    overheat = candidate.get("overheat") if isinstance(candidate.get("overheat"), dict) else {}
    overheat_engines = overheat.get("engine_temperature_evidence") if isinstance(overheat, dict) else None

    if missing:
        action = "add_or_review_missing_candidate_fields"
    elif diffs:
        action = "review_candidate_differences"
    else:
        action = "candidate_matches_current_profile"

    return {
        "vehicle": vehicle,
        "profile_source": source,
        "profile_family": family,
        "profile_matched": matched,
        "action": action,
        "counts": {
            "match": len(matches),
            "diff": len(diffs),
            "missing_current": len(missing),
        },
        "comparisons": comparisons,
        "overheat_evidence": {
            "present": bool(overheat_engines),
            "policy": "report_only_not_threshold",
        },
    }


def build_report(
    *,
    profiles_path: pathlib.Path,
    candidate_report: dict[str, Any],
) -> dict[str, Any]:
    processor = TelemetryProcessor(str(profiles_path))
    records = _candidate_records(candidate_report)
    vehicles = [compare_candidate(record, processor=processor) for record in records]
    actions: dict[str, int] = {}
    profile_sources: dict[str, int] = {}
    for row in vehicles:
        actions[row["action"]] = actions.get(row["action"], 0) + 1
        profile_sources[row["profile_source"]] = profile_sources.get(row["profile_source"], 0) + 1
    return {
        "status": "profile_candidate_diff",
        "profiles": str(profiles_path),
        "candidate_source": candidate_report.get("source"),
        "candidate_ref": candidate_report.get("ref"),
        "vehicles_checked": len(vehicles),
        "actions": actions,
        "profile_sources": profile_sources,
        "policy": {
            "stall_aoa_overspeed": "candidate_review_allowed",
            "overheat": "report_only_until_live_sample",
            "no_auto_write": True,
        },
        "vehicles": vehicles,
    }


def _fetch_default_candidates() -> dict[str, Any]:
    results = [candidates_tool.fetch_vehicle(vehicle) for vehicle in candidates_tool.DEFAULT_VEHICLES]
    return {
        "source": "gszabi99/War-Thunder-Datamine",
        "ref": candidates_tool.DEFAULT_REF,
        "status": "candidate_report_only",
        "vehicles_requested": len(results),
        "vehicles_ok": len(results),
        "vehicles_failed": 0,
        "results": results,
        "errors": [],
    }


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
    parser.add_argument("--profiles", type=pathlib.Path, default=DEFAULT_PROFILES)
    parser.add_argument(
        "--candidates",
        type=pathlib.Path,
        default=DEFAULT_CANDIDATES,
        help="Candidate report JSON from tools/datamine_profile_candidates.py",
    )
    parser.add_argument(
        "--fetch-default",
        action="store_true",
        help="Fetch the built-in candidate vehicle set instead of reading --candidates.",
    )
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT, help="Report path. Use '-' for stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    candidate_report = _fetch_default_candidates() if args.fetch_default else _load_json(args.candidates)
    report = build_report(profiles_path=args.profiles, candidate_report=candidate_report)
    output = None if str(args.output) == "-" else args.output
    _write_report(report, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
