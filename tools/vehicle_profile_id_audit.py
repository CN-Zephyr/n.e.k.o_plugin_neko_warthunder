"""Audit vehicle profile identity keys without network access.

The database key is the runtime ``/api/processed.vehicle_type``. War Thunder
Wiki ``/unit/<gameId>`` is the preferred offline candidate for new exact keys,
but live 8112 telemetry remains the final authority.
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
DEFAULT_VETTED_IDS = DATA_PROCESS / "vehicle_profile_vetted_ids.json"
DEFAULT_REVIEWED_ALIASES = DATA_PROCESS / "vehicle_profile_identity_aliases.json"
DEFAULT_REPORT = BASE / "local_test_logs" / "vehicle_profile_id_audit.json"

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _exact_entries(profiles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: value
        for key, value in profiles.items()
        if not key.startswith("_") and isinstance(value, dict)
    }


def _compact_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _load_vetted_ids(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json(path)
    ids = payload.get("ids")
    if not isinstance(ids, list):
        raise ValueError(f"{path} must contain an ids list")
    rows: list[dict[str, Any]] = []
    for row in ids:
        if isinstance(row, str):
            rows.append({"vehicle_type": row})
        elif isinstance(row, dict):
            rows.append(dict(row))
    return rows


def _load_reviewed_aliases(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = _load_json(path)
    aliases = payload.get("aliases")
    if not isinstance(aliases, list):
        raise ValueError(f"{path} must contain an aliases list")
    result: dict[str, dict[str, Any]] = {}
    for row in aliases:
        if not isinstance(row, dict):
            continue
        canonical = str(row.get("canonical") or "")
        alias_ids = row.get("aliases")
        if not canonical or not isinstance(alias_ids, list):
            continue
        ids = sorted({canonical, *[str(alias) for alias in alias_ids if alias]})
        compact = _compact_id(canonical)
        result[compact] = {**row, "vehicle_ids": ids}
    return result


def _add_issue(issues: list[dict[str, Any]], code: str, vehicle_id: str, detail: str = "") -> None:
    item = {"code": code, "vehicle_id": vehicle_id}
    if detail:
        item["detail"] = detail
    issues.append(item)


def build_report(
    *,
    profiles_path: str | pathlib.Path = DEFAULT_PROFILES,
    vetted_ids_path: str | pathlib.Path = DEFAULT_VETTED_IDS,
    reviewed_aliases_path: str | pathlib.Path = DEFAULT_REVIEWED_ALIASES,
) -> dict[str, Any]:
    profiles_file = pathlib.Path(profiles_path)
    vetted_file = pathlib.Path(vetted_ids_path)
    aliases_file = pathlib.Path(reviewed_aliases_path)
    profiles = _load_json(profiles_file)
    exact = _exact_entries(profiles)
    vetted_rows = _load_vetted_ids(vetted_file)
    reviewed_aliases = _load_reviewed_aliases(aliases_file)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    info: list[dict[str, Any]] = []
    reviewed_alias_groups: list[dict[str, Any]] = []

    for key in sorted(key for key in profiles if not key.startswith("_")):
        value = profiles[key]
        if not isinstance(value, dict):
            _add_issue(errors, "non_object_profile", key, "exact profile entries must be JSON objects")
            continue
        if not KEY_RE.fullmatch(key):
            _add_issue(errors, "invalid_exact_key_shape", key, "expected lower-case gameId/vehicle_type characters")
        if not value:
            _add_issue(warnings, "empty_exact_profile", key, "profile only falls back to defaults/classes")

    compact_groups: dict[str, list[str]] = {}
    for vehicle_id in exact:
        compact_groups.setdefault(_compact_id(vehicle_id), []).append(vehicle_id)
    alias_groups = [
        {"compact_id": compact, "vehicle_ids": sorted(ids)}
        for compact, ids in sorted(compact_groups.items())
        if len(ids) > 1
    ]
    for group in alias_groups:
        reviewed = reviewed_aliases.get(group["compact_id"])
        if reviewed and sorted(reviewed["vehicle_ids"]) == group["vehicle_ids"]:
            reviewed_alias_groups.append(
                {
                    "compact_id": group["compact_id"],
                    "canonical": reviewed.get("canonical"),
                    "vehicle_ids": group["vehicle_ids"],
                    "source": reviewed.get("source"),
                    "status": reviewed.get("status"),
                }
            )
            continue
        warnings.append(
            {
                "code": "unreviewed_compact_alias_group",
                "compact_id": group["compact_id"],
                "vehicle_ids": group["vehicle_ids"],
                "detail": "review whether both separator variants are intentional runtime ids",
            }
        )

    for compact, row in sorted(reviewed_aliases.items()):
        canonical = str(row.get("canonical") or "")
        if canonical not in exact:
            _add_issue(errors, "reviewed_alias_missing_canonical", canonical or compact)
        for alias in row.get("aliases") or []:
            if str(alias) not in exact:
                _add_issue(errors, "reviewed_alias_missing_profile", str(alias))

    vetted_seen: set[str] = set()
    for row in vetted_rows:
        vehicle_id = str(row.get("vehicle_type") or "")
        if not vehicle_id:
            _add_issue(errors, "invalid_vetted_row", "-", "missing vehicle_type")
            continue
        if vehicle_id in vetted_seen:
            _add_issue(errors, "duplicate_vetted_id", vehicle_id)
        vetted_seen.add(vehicle_id)
        if not KEY_RE.fullmatch(vehicle_id):
            _add_issue(errors, "invalid_vetted_id_shape", vehicle_id)
        profile = exact.get(vehicle_id)
        if profile is None:
            _add_issue(errors, "vetted_id_missing_profile", vehicle_id)
            continue
        if profile.get("_tested") is not True:
            _add_issue(errors, "vetted_id_not_marked_tested", vehicle_id)

    tested_ids = sorted(vehicle_id for vehicle_id, entry in exact.items() if entry.get("_tested") is True)
    unlisted_tested = [vehicle_id for vehicle_id in tested_ids if vehicle_id not in vetted_seen]
    for vehicle_id in unlisted_tested:
        _add_issue(warnings, "tested_id_not_in_vetted_list", vehicle_id)

    source_counts: dict[str, int] = {}
    for entry in exact.values():
        source = str(entry.get("_profile_key_source") or "unspecified")
        source_counts[source] = source_counts.get(source, 0) + 1
    info.append(
        {
            "code": "identity_source_policy",
            "policy": "prefer Wiki /unit/<gameId>; verify with /api/processed.vehicle_type; use Datamine for numeric evidence",
        }
    )

    return {
        "status": "fail" if errors else "pass",
        "profiles": str(profiles_file),
        "vetted_ids": str(vetted_file),
        "reviewed_aliases": str(aliases_file),
        "summary": {
            "exact_profiles": len(exact),
            "vetted_ids": len(vetted_rows),
            "tested_profiles": len(tested_ids),
            "invalid_keys": sum(1 for item in errors if item["code"].endswith("_shape")),
            "compact_alias_groups": len(alias_groups),
            "reviewed_alias_groups": len(reviewed_alias_groups),
            "unreviewed_alias_groups": sum(
                1 for item in warnings if item["code"] == "unreviewed_compact_alias_group"
            ),
            "warnings": len(warnings),
            "errors": len(errors),
            "profile_key_sources": source_counts,
        },
        "policy": {
            "read_only": True,
            "network_access": False,
            "runtime_behavior_changes": False,
            "canonical_candidate": "War Thunder Wiki /unit/<gameId>",
            "runtime_authority": "/api/processed.vehicle_type",
            "numeric_evidence_source": "Datamine flightmodels",
        },
        "errors": errors,
        "warnings": warnings,
        "reviewed_alias_groups": reviewed_alias_groups,
        "info": info,
    }


def render_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# neko_warthunder vehicle profile id audit",
        f"status: {report['status']}",
        f"exact_profiles: {summary['exact_profiles']}",
        f"vetted_ids: {summary['vetted_ids']}",
        f"tested_profiles: {summary['tested_profiles']}",
        f"compact_alias_groups: {summary['compact_alias_groups']}",
        f"reviewed_alias_groups: {summary['reviewed_alias_groups']}",
        f"unreviewed_alias_groups: {summary['unreviewed_alias_groups']}",
        f"errors: {summary['errors']}",
        f"warnings: {summary['warnings']}",
        "policy: Wiki /unit/<gameId> candidate, 8112 vehicle_type authority, Datamine numeric evidence",
    ]
    if report["errors"]:
        lines.append("errors_detail:")
        for item in report["errors"][:12]:
            lines.append(f"- {item['code']}: {item.get('vehicle_id', '-')}")
    if report["warnings"]:
        lines.append("warnings_detail:")
        for item in report["warnings"][:12]:
            label = item.get("vehicle_id") or ",".join(item.get("vehicle_ids") or [])
            lines.append(f"- {item['code']}: {label}")
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=pathlib.Path, default=DEFAULT_PROFILES)
    parser.add_argument("--vetted-ids", type=pathlib.Path, default=DEFAULT_VETTED_IDS)
    parser.add_argument("--reviewed-aliases", type=pathlib.Path, default=DEFAULT_REVIEWED_ALIASES)
    parser.add_argument("--output", type=pathlib.Path, help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(
        profiles_path=args.profiles,
        vetted_ids_path=args.vetted_ids,
        reviewed_aliases_path=args.reviewed_aliases,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
        if args.output:
            print(f"wrote {args.output}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
