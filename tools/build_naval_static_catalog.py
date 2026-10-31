"""Build deterministic, hash-verified naval static references from pinned local Datamine files.

Offline only. No threshold/profile updates, live telemetry, network or runtime mutations.
The output catalog itself can serve as the manifest for a later reproducible rebuild.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import _bootstrap as _bootstrap  # noqa: F401
from naval_modification_resolution import resolve_modifications
from neko_warthunder.adapters.naval_instrument_fields import _finite
from neko_warthunder.adapters.naval_static_reference import DIRECTORY, MODIFICATION_SOURCE, REPOSITORY, validate_catalog


def _number(value):
    return value if _finite(value) else None


def _count(value):
    return value if type(value) is int and 0 <= value <= 1000000 else None


def _code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}", value) else None


def extract_static(unit: dict) -> dict:
    phys = unit.get("ShipPhys")
    phys = phys if isinstance(phys, dict) else {}
    engines, mass = phys.get("engines"), phys.get("mass")
    engines = engines if isinstance(engines, dict) else {}
    mass = mass if isinstance(mass, dict) else {}
    propulsion = engines.get("engine")
    engine_entries = (
        propulsion if isinstance(propulsion, list) and all(isinstance(item, dict) for item in propulsion) else None
    )
    if isinstance(propulsion, dict) and "outputParam" in propulsion:
        engine_entries = [propulsion]
    propellers = [item.get("propeller") for item in engine_entries] if engine_entries is not None else []
    propulsion_count = (
        len(set(propellers))
        if engine_entries is not None and all(isinstance(item, str) and item for item in propellers)
        else None
    )
    crew = unit.get("tank_crew")
    crew = crew if isinstance(crew, dict) else {}
    stations = [item for key, item in crew.items() if re.fullmatch(r"sailor\d+", key)]
    distribution = [item.get("crew") if isinstance(item, dict) else None for item in stations]
    known_crew = bool(stations) and all(_count(value) is not None for value in distribution)
    return {
        "type_code": _code(unit.get("type")),
        "move_type": _code(unit.get("moveType")),
        "economic_class_code": _code(unit.get("expClass")),
        "mass_empty_config": _number(mass.get("Empty")),
        "forward_speed_config": _number(unit.get("maxFwdSpeed")),
        "reverse_speed_config": _number(unit.get("maxRevSpeed")),
        "engine_forward_speed_config": _number(engines.get("maxSpeed")),
        "engine_reverse_speed_config": _number(engines.get("maxReverseSpeed")),
        "engine_entry_count": _count(len(engine_entries)) if engine_entries is not None else None,
        "propulsion_count": _count(propulsion_count),
        "crew_station_count": len(stations) if stations else None,
        "crew_distribution_total": _count(sum(distribution)) if known_crew else None,
        "min_alive_crew_config": _count(crew.get("minCrewMemberAliveCount")),
        "min_repair_crew_config": _count(crew.get("minCrewMemberRepairCount")),
    }


def build_catalog(source_dir: Path, manifest: dict, *, modifications_file: Path | None = None,
                  resolution_report: dict | None = None) -> dict:
    source = manifest.get("source", manifest)
    if source.get("repository") != REPOSITORY or source.get("directory") != DIRECTORY:
        raise ValueError("Unsupported source")
    ref, version = source.get("ref"), source.get("version")
    if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("An immutable source commit is required")
    entries = manifest.get("entries")
    if entries is None and isinstance(manifest.get("records"), dict):
        entries = [
            {"name": key + ".blkx", "sha": record["blob_sha"], "size": record["source_bytes"]}
            for key, record in manifest["records"].items()
        ]
    if not isinstance(entries, list) or not 0 < len(entries) <= 2000:
        raise ValueError("Invalid source index")
    descriptor = manifest.get("modification_source")
    if manifest.get("schema_version") == 2 and descriptor is None:
        raise ValueError("Schema v2 requires pinned common modification provenance")
    definitions, modification_source = None, None
    if descriptor is not None:
        if not isinstance(descriptor, dict) or descriptor.get("path") != MODIFICATION_SOURCE or modifications_file is None:
            raise ValueError("Pinned common modification source is required")
        if modifications_file.stat().st_size > 1024 * 1024:
            raise ValueError("Common source too large")
        raw = modifications_file.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        expected_size = descriptor.get("source_bytes", descriptor.get("size"))
        expected_sha = descriptor.get("blob_sha", descriptor.get("sha"))
        if type(expected_size) is not int or len(raw) != expected_size or blob != expected_sha:
            raise ValueError("Common source size/hash mismatch")
        definitions = json.loads(raw)
        if not isinstance(definitions, dict):
            raise ValueError("Invalid common source")
        modification_source = {"path": MODIFICATION_SOURCE, "blob_sha": blob, "source_bytes": len(raw)}
    elif modifications_file is not None:
        raise ValueError("A modification source without a pinned descriptor is not accepted")
    root = source_dir / DIRECTORY if (source_dir / DIRECTORY).is_dir() else source_dir
    records = {}
    for entry in entries:
        name = entry.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_]{0,127}\.blkx", name):
            raise ValueError("Invalid source name")
        key = name[:-5]
        if key in records:
            raise ValueError("Duplicate source name")
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("Source escaped the selected root")
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Source too large")
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if type(entry.get("size")) is not int or len(raw) != entry["size"] or blob != entry.get("sha"):
            raise ValueError("Source size/hash mismatch")
        unit = json.loads(raw)
        if not isinstance(unit, dict):
            raise ValueError("Invalid source document")
        records[key] = {"blob_sha": blob, "source_bytes": len(raw), "static": extract_static(unit)}
        if definitions is not None:
            resolved = resolve_modifications(unit, definitions)
            records[key]["configuration"] = resolved["summary"]
            if resolution_report is not None:
                resolution_report[key] = resolved
    catalog = {
        "schema_version": 2 if definitions is not None else 1,
        "source": {"repository": REPOSITORY, "directory": DIRECTORY, "ref": ref, "version": version},
        "coverage": {
            "indexed_files": len(entries),
            "parsed_files": len(records),
            "scope": "top_level_ship_blkx_including_nonplayable",
        },
        "records": records,
    }
    if modification_source is not None:
        catalog["modification_source"] = modification_source
    if not validate_catalog(catalog):
        raise ValueError("Invalid extracted catalog")
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--modifications", type=Path)
    parser.add_argument("--resolution-report", type=Path)
    args = parser.parse_args()
    details = {}
    catalog = build_catalog(args.source_dir, json.loads(args.manifest.read_text(encoding="utf-8")),
                            modifications_file=args.modifications, resolution_report=details)
    # All inputs must pass before replacing any output. No partial catalog is emitted.
    encoded = json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    # Write exact UTF-8 bytes: Windows newline translation must not invalidate
    # the reported digest or platform-independent reproducible build.
    args.out.write_bytes(encoded.encode("utf-8"))
    if args.resolution_report:
        args.resolution_report.write_bytes((json.dumps(details, ensure_ascii=False, sort_keys=True, indent=2,
                                                       allow_nan=False) + "\n").encode("utf-8"))
    print(
        json.dumps(
            {
                "status": "pass",
                **catalog["coverage"],
                "catalog_bytes": len(encoded.encode()),
                "catalog_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
