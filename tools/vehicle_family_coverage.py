"""Report vehicle family coverage from vehicle_profiles.json.

The report is read-only. It helps maintainers decide whether to add exact
profiles, improve a family rule, or leave a vehicle on class fallback.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any


BASE = pathlib.Path(__file__).resolve().parent.parent
DATA_PROCESS = BASE / "data_layer" / "data process"
DEFAULT_PROFILES = DATA_PROCESS / "vehicle_profiles.json"
DEFAULT_REPORT = BASE / "local_test_logs" / "vehicle_family_coverage.json"


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _compact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _exact_entries(profiles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: value
        for key, value in profiles.items()
        if not key.startswith("_") and isinstance(value, dict)
    }


def _has_group(entry: dict[str, Any], group: str) -> bool:
    if group == "stall":
        return "stall_warn_kmh" in entry and "stall_critical_kmh" in entry
    if group == "aoa":
        return "aoa_warn_deg" in entry and "aoa_critical_deg" in entry
    if group == "overspeed":
        return "overspeed_critical_kmh" in entry or "overspeed_critical_mach" in entry
    if group == "oil_temperature":
        return "oil_temp_warn_c" in entry and "oil_temp_critical_c" in entry
    if group == "turbine_temperature":
        return "turbine_temp_warn_c" in entry and "turbine_temp_critical_c" in entry
    if group == "g_evidence":
        return any(
            field in entry
            for field in (
                "structure_overload_positive_n",
                "g_limit_positive_empty_candidate",
                "g_limit_positive_full_fuel_candidate",
                "instructor_g_limit_positive",
            )
        )
    if group == "fuel_inertia":
        return any(
            field in entry
            for field in (
                "fuel_consumption_idle_total",
                "fuel_consumption_full_total",
                "fuel_consumption_wep_total",
                "engine_inertia_moment_max",
            )
        )
    if group == "economy_metadata":
        return "rank" in entry and "country" in entry and "unit_class" in entry
    raise KeyError(group)


def _coverage_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    groups = (
        "stall",
        "aoa",
        "overspeed",
        "oil_temperature",
        "turbine_temperature",
        "g_evidence",
        "fuel_inertia",
        "economy_metadata",
    )
    return {group: sum(1 for entry in entries if _has_group(entry, group)) for group in groups}


def _best_family_prefix_len(compact_vehicle_id: str, compact_prefixes: list[str]) -> int:
    return max(
        (len(prefix) for prefix in compact_prefixes if prefix and compact_vehicle_id.startswith(prefix)),
        default=0,
    )


def _family_risks(
    *,
    family: dict[str, Any],
    class_exists: bool,
    exact_count: int,
    coverage: dict[str, int],
    narrower_families: list[str],
) -> list[str]:
    risks: list[str] = []
    if not class_exists:
        risks.append("missing_class_template")
    if exact_count == 0:
        risks.append("no_exact_matches")
    if narrower_families:
        risks.append("has_narrower_family_prefixes")
    if exact_count > 0:
        if coverage["economy_metadata"] < exact_count:
            risks.append("missing_economy_metadata")
        if coverage["oil_temperature"] == 0 and coverage["turbine_temperature"] == 0:
            risks.append("no_family_exact_thermal_evidence")
        if coverage["g_evidence"] == 0:
            risks.append("no_family_exact_g_evidence")
    if not isinstance(family.get("prefix"), str) or not family.get("prefix"):
        risks.append("invalid_prefix")
    return risks


def build_report(*, profiles_path: str | pathlib.Path = DEFAULT_PROFILES) -> dict[str, Any]:
    profiles = _load_json(pathlib.Path(profiles_path))
    exact = _exact_entries(profiles)
    families = [family for family in profiles.get("_families", []) if isinstance(family, dict)]
    classes = profiles.get("_classes") if isinstance(profiles.get("_classes"), dict) else {}
    compact_exact = {vehicle_id: _compact_name(vehicle_id) for vehicle_id in exact}
    compact_family_prefixes = [
        _compact_name(str(family["prefix"]))
        for family in families
        if isinstance(family.get("prefix"), str) and family.get("prefix")
    ]

    family_rows: list[dict[str, Any]] = []
    for family in families:
        prefix = family.get("prefix") if isinstance(family.get("prefix"), str) else ""
        compact_prefix = _compact_name(prefix)
        matches = [
            vehicle_id
            for vehicle_id, compact_vehicle_id in compact_exact.items()
            if compact_prefix
            and compact_vehicle_id.startswith(compact_prefix)
            and len(compact_prefix) == _best_family_prefix_len(compact_vehicle_id, compact_family_prefixes)
        ]
        shadowed_matches = [
            vehicle_id
            for vehicle_id, compact_vehicle_id in compact_exact.items()
            if compact_prefix
            and compact_vehicle_id.startswith(compact_prefix)
            and len(compact_prefix) < _best_family_prefix_len(compact_vehicle_id, compact_family_prefixes)
        ]
        infix_matches = [
            vehicle_id
            for vehicle_id, compact_vehicle_id in compact_exact.items()
            if compact_prefix and not compact_vehicle_id.startswith(compact_prefix) and compact_prefix in compact_vehicle_id
        ]
        entries = [exact[vehicle_id] for vehicle_id in matches]
        coverage = _coverage_counts(entries)
        family_class = family.get("class") if isinstance(family.get("class"), str) else ""
        narrower = [
            str(other.get("label") or other.get("prefix"))
            for other in families
            if other is not family
            and isinstance(other.get("prefix"), str)
            and compact_prefix
            and _compact_name(other["prefix"]).startswith(compact_prefix)
        ]
        row = {
            "prefix": prefix,
            "label": family.get("label") if isinstance(family.get("label"), str) else prefix,
            "class": family_class,
            "class_exists": bool(family_class and family_class in classes),
            "exact_count": len(matches),
            "exact_samples": matches[:8],
            "shadowed_exact_count": len(shadowed_matches),
            "shadowed_exact_samples": shadowed_matches[:8],
            "infix_exact_count": len(infix_matches),
            "infix_exact_samples": infix_matches[:8],
            "coverage": coverage,
            "narrower_family_prefixes": narrower[:12],
        }
        row["risks"] = _family_risks(
            family=family,
            class_exists=row["class_exists"],
            exact_count=row["exact_count"],
            coverage=coverage,
            narrower_families=row["narrower_family_prefixes"],
        )
        family_rows.append(row)

    exact_count_by_label: dict[str, int] = {}
    for row in family_rows:
        label = str(row["label"])
        exact_count_by_label[label] = exact_count_by_label.get(label, 0) + int(row["exact_count"])
    for row in family_rows:
        sibling_exact_count = exact_count_by_label.get(str(row["label"]), 0) - int(row["exact_count"])
        row["sibling_family_exact_count"] = sibling_exact_count
        if sibling_exact_count > 0 and "no_exact_matches" in row["risks"]:
            row["risks"] = [
                "alias_family_no_exact_matches" if risk == "no_exact_matches" else risk
                for risk in row["risks"]
            ]
        if int(row.get("infix_exact_count") or 0) > 0 and "no_exact_matches" in row["risks"]:
            row["risks"] = [
                "infix_family_no_exact_matches" if risk == "no_exact_matches" else risk
                for risk in row["risks"]
            ]

    exact_coverage = _coverage_counts(list(exact.values()))
    families_with_risks = [row for row in family_rows if row["risks"]]
    priority_gaps = sorted(
        families_with_risks,
        key=lambda row: (
            "missing_class_template" not in row["risks"],
            "no_exact_matches" not in row["risks"],
            "alias_family_no_exact_matches" in row["risks"],
            "infix_family_no_exact_matches" in row["risks"],
            -int(row["exact_count"]),
            str(row["label"]),
        ),
    )[:25]

    return {
        "status": "pass",
        "profiles": str(pathlib.Path(profiles_path)),
        "summary": {
            "exact_profiles": len(exact),
            "families": len(families),
            "classes": len(classes),
            "exact_coverage": exact_coverage,
            "families_with_risks": len(families_with_risks),
        },
        "policy": {
            "read_only": True,
            "runtime_behavior_changes": False,
            "raw_sample_text_read": False,
        },
        "families": family_rows,
        "priority_gaps": priority_gaps,
    }


def render_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    coverage = summary["exact_coverage"]
    lines = [
        "# neko_warthunder vehicle family coverage",
        f"status: {report['status']}",
        f"exact_profiles: {summary['exact_profiles']}",
        f"families: {summary['families']}",
        f"classes: {summary['classes']}",
        f"families_with_risks: {summary['families_with_risks']}",
        "exact_coverage:",
    ]
    for key in sorted(coverage):
        lines.append(f"- {key}: {coverage[key]}/{summary['exact_profiles']}")
    gaps = report.get("priority_gaps") or []
    lines.append("priority_gaps:")
    if not gaps:
        lines.append("- -")
    for row in gaps[:10]:
        risks = ",".join(row["risks"])
        lines.append(
            f"- {row['label']} ({row['prefix']}): exact={row['exact_count']} "
            f"class={row['class'] or '-'} risks={risks}"
        )
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=pathlib.Path, default=DEFAULT_PROFILES)
    parser.add_argument("--output", type=pathlib.Path, help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(profiles_path=args.profiles)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
        if args.output:
            print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
