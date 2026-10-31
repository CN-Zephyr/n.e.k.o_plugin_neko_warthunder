"""Pinned static references for diagnostics only; never enrich live BattleState or events."""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

from ..core.contracts import BattleState
from .naval_instrument_fields import _finite

REPOSITORY = "gszabi99/War-Thunder-Datamine"
DIRECTORY = "aces.vromfs.bin_u/gamedata/units/ships"
MODIFICATION_SOURCE = "char.vromfs.bin_u/config/modifications.blkx"
CONFIGURATION_COUNTERS = (
    "declared_count", "common_definition_count", "missing_common_definition_count", "local_override_count",
    "dependency_edge_count", "missing_dependency_count", "cycle_node_count", "template_reference_count",
    "missing_template_count", "external_weapon_template_count", "explicit_empty_block_count",
    "overlapping_block_count", "complex_effect_block_count", "uninterpreted_effect_value_count",
    "unsupported_directive_count", "invalid_declaration_count",
)
CATALOG_PATH = Path(__file__).resolve().parents[1] / "contract/naval_static_catalog.json"
_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,127}")
_SHA = re.compile(r"[0-9a-f]{40}")
_CODE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{0,63}")
_NUMERIC_FIELDS = {
    "mass_empty_config",
    "forward_speed_config",
    "reverse_speed_config",
    "engine_forward_speed_config",
    "engine_reverse_speed_config",
}
_COUNT_FIELDS = {
    "engine_entry_count",
    "propulsion_count",
    "crew_station_count",
    "crew_distribution_total",
    "min_alive_crew_config",
    "min_repair_crew_config",
}
_CODE_FIELDS = {"type_code", "move_type", "economic_class_code"}
FIELD_MAPPING = (
    {
        "id": "speed",
        "raw_key": "speed",
        "normalized_key": "indicators.speed",
        "static_paths": ["maxFwdSpeed", "maxRevSpeed", "ShipPhys.engines.maxSpeed", "ShipPhys.engines.maxReverseSpeed"],
        "relation": "configuration_not_reading",
    },
    {
        "id": "heading",
        "raw_key": "compass",
        "normalized_key": "indicators.heading_deg",
        "static_paths": [],
        "relation": "no_direct_static_mapping",
    },
    {
        "id": "rpm",
        "raw_key": "rpm",
        "normalized_key": "indicators.rpm",
        "static_paths": ["ShipPhys.engines.engine"],
        "relation": "structure_not_reading",
    },
    {
        "id": "throttle",
        "raw_key": "throttle",
        "normalized_key": "indicators.throttle",
        "static_paths": ["ShipPhys.engines.speedToTime", "ShipPhys.engines.reverseSpeedToTime"],
        "relation": "model_not_control",
    },
)


def validate_catalog(catalog: dict) -> bool:
    if (
        not isinstance(catalog, dict)
        or type(catalog.get("schema_version")) is not int
        or catalog["schema_version"] not in (1, 2)
    ):
        return False
    source, records, coverage = (catalog.get(key) for key in ("source", "records", "coverage"))
    if not all(isinstance(item, dict) for item in (source, records, coverage)):
        return False
    if catalog["schema_version"] == 2:
        descriptor = catalog.get("modification_source")
        if (not isinstance(descriptor, dict) or set(descriptor) != {"path", "blob_sha", "source_bytes"}
                or descriptor.get("path") != MODIFICATION_SOURCE
                or not isinstance(descriptor.get("blob_sha"), str) or not _SHA.fullmatch(descriptor["blob_sha"])
                or type(descriptor.get("source_bytes")) is not int or not 0 < descriptor["source_bytes"] <= 1024 * 1024):
            return False
    if (
        set(source) != {"repository", "directory", "ref", "version"}
        or source.get("repository") != REPOSITORY
        or source.get("directory") != DIRECTORY
        or not isinstance(source.get("ref"), str)
        or not _SHA.fullmatch(source["ref"])
        or not isinstance(source.get("version"), str)
        or not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", source["version"])
        or not 0 < len(records) <= 2000
        or type(coverage.get("indexed_files")) is not int
        or type(coverage.get("parsed_files")) is not int
        or coverage.get("indexed_files") != len(records)
        or coverage.get("parsed_files") != len(records)
    ):
        return False
    for vehicle_id, record in records.items():
        if not isinstance(vehicle_id, str) or not _ID.fullmatch(vehicle_id) or not isinstance(record, dict):
            return False
        if (
            not isinstance(record.get("blob_sha"), str)
            or not _SHA.fullmatch(record["blob_sha"])
            or type(record.get("source_bytes")) is not int
            or not 0 < record["source_bytes"] <= 1024 * 1024
        ):
            return False
        facts = record.get("static")
        if not isinstance(facts, dict) or set(facts) != _NUMERIC_FIELDS | _COUNT_FIELDS | _CODE_FIELDS:
            return False
        for key, value in facts.items():
            if value is None:
                continue
            if key in _CODE_FIELDS:
                if not isinstance(value, str) or not _CODE.fullmatch(value):
                    return False
            elif key in _COUNT_FIELDS:
                if type(value) is not int or not 0 <= value <= 1000000:
                    return False
            elif not _finite(value):
                return False
        if catalog["schema_version"] == 2 and not validate_configuration(record.get("configuration")):
            return False
    return True


def validate_configuration(summary) -> bool:
    flags = {"effective_parameters_available", "installed_state_known", "engine_composition_verified"}
    if not isinstance(summary, dict) or set(summary) != set(CONFIGURATION_COUNTERS) | flags | {"status", "base_status"}:
        return False
    if (summary["status"] not in ("none_declared", "declarations_resolved", "partial")
            or summary["base_status"] not in ("direct_fields", "unresolved_directives")
            or any(summary[key] is not False for key in flags)
            or any(type(summary[key]) is not int or not 0 <= summary[key] <= 100000 for key in CONFIGURATION_COUNTERS)):
        return False
    count = summary["declared_count"]
    partial = any(summary[key] for key in (
        "missing_common_definition_count", "missing_dependency_count", "cycle_node_count",
        "missing_template_count", "unsupported_directive_count", "invalid_declaration_count"))
    expected_status = "partial" if partial else "declarations_resolved" if count else "none_declared"
    expected_base = "unresolved_directives" if summary["unsupported_directive_count"] else "direct_fields"
    return (count <= 256 and summary["common_definition_count"] + summary["missing_common_definition_count"] == count
            and summary["local_override_count"] <= count and summary["cycle_node_count"] <= count
            and summary["missing_template_count"] <= summary["template_reference_count"] <= count * 2
            and summary["missing_dependency_count"] <= summary["dependency_edge_count"] <= count * 128
            and summary["status"] == expected_status and summary["base_status"] == expected_base)


@lru_cache(maxsize=1)
def _load_catalog() -> dict | None:
    try:
        if CATALOG_PATH.stat().st_size > 2 * 1024 * 1024:
            return None
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return catalog if validate_catalog(catalog) else None
    except (OSError, ValueError, RecursionError):
        return None


def snapshot_naval_static_reference(state: BattleState, inventory: dict | None) -> dict | None:
    if inventory is None:
        return None
    result = {
        "status": "catalog_unavailable",
        "source": None,
        "indexed_files": 0,
        "vehicle": None,
        "field_mapping": copy.deepcopy(FIELD_MAPPING),
        "game_version_verified": False,
        "live_values_enriched": False,
        "naval_semantics_verified": False,
        "real_output_enabled": False,
        "effective_parameters_available": False,
        "catalog_schema_version": None,
    }
    catalog = _load_catalog()
    if catalog is None:
        return result
    result.update(source=dict(catalog["source"]), indexed_files=len(catalog["records"]), status="sample_unavailable",
                  catalog_schema_version=catalog["schema_version"])
    # Static references do not establish domain, life identity or instrument freshness.
    if (
        state.domain != "naval"
        or inventory.get("sampling_status") != "ready"
        or inventory.get("sample_life_bound") is not True
    ):
        return result
    indicators = state.raw.get("indicators") if isinstance(state.raw, dict) else None
    if not isinstance(indicators, dict):
        return result
    original = indicators.get("raw")
    vehicle_id = indicators.get("vehicle_type")
    # Exact ID only. No case folding, filename suffix stripping, fuzzy matching,
    # or fallback to cached processed/vehicle types. Parser provenance must agree.
    raw_type = original.get("type") if isinstance(original, dict) else None
    if (
        not isinstance(vehicle_id, str)
        or not _ID.fullmatch(vehicle_id)
        or not isinstance(raw_type, str)
        or raw_type.split("/")[-1] != vehicle_id
    ):
        result["status"] = "unconfirmed_vehicle"
        return result
    record = catalog["records"].get(vehicle_id)
    if record is None:
        result["status"] = "not_indexed"
        return result
    # Only configuration counts/codes cross the UI seam. Config speed/mass values
    # remain in the static evidence file, with no unit/conversion interpretation.
    visible = {
        key: record["static"][key]
        for key in (
            "type_code",
            "engine_entry_count",
            "propulsion_count",
            "crew_station_count",
            "crew_distribution_total",
        )
    }
    if catalog["schema_version"] == 2:
        visible["configuration"] = dict(record["configuration"])
    result.update(status="matched", vehicle={"id": vehicle_id, "blob_sha": record["blob_sha"], **visible})
    return result
