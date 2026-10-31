"""Static configuration provenance, deterministic extraction and readonly live boundaries."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from neko_warthunder.adapters import naval_static_reference as static
from neko_warthunder.adapters.naval_instrument_fields import snapshot_naval_instrument_fields
from test_helicopter_vrs import _evaluate, _runtime
from test_naval_instrument_sampling import _sample_state

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("build_naval_static_catalog", TOOLS / "build_naval_static_catalog.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture(autouse=True)
def clear_catalog_cache():
    static._load_catalog.cache_clear()
    yield
    static._load_catalog.cache_clear()


def _current(vehicle_id="us_destroyer_fletcher"):
    current = _sample_state()
    current.raw["indicators"]["vehicle_type"] = vehicle_id
    current.raw["indicators"]["raw"]["type"] = "ships/" + vehicle_id
    return current


def _reference(current=None, now=1000):
    current = current or _current()
    return static.snapshot_naval_static_reference(current, snapshot_naval_instrument_fields(current, now))


def _unit():
    return {
        "type": "typeDestroyer",
        "moveType": "ship",
        "expClass": "exp_destroyer",
        "maxFwdSpeed": 80,
        "maxRevSpeed": 5,
        "ShipPhys": {
            "mass": {"Empty": 100},
            "engines": {
                "maxSpeed": 18,
                "maxReverseSpeed": 7,
                "engine": [{"propeller": "propeller_01"}, {"propeller": "propeller_02"}],
            },
        },
        "tank_crew": {
            "minCrewMemberAliveCount": 3,
            "minCrewMemberRepairCount": 4,
            "sailor1": {"crew": 5},
            "sailor2": {"crew": 6},
        },
        "private_text": "private-sentinel",
    }


def _manifest(tmp_path, unit=None):
    raw = json.dumps(_unit() if unit is None else unit).encode()
    (tmp_path / "example_ship.blkx").write_bytes(raw)
    sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    return {
        "repository": static.REPOSITORY,
        "directory": static.DIRECTORY,
        "ref": "a" * 40,
        "version": "2.59.0.92",
        "entries": [{"name": "example_ship.blkx", "sha": sha, "size": len(raw)}],
    }


def test_static_extraction_keeps_distinct_config_sources_and_configuration_counts():
    result = builder.extract_static(_unit())
    assert result["forward_speed_config"] == 80 and result["engine_forward_speed_config"] == 18
    assert result["engine_entry_count"] == result["propulsion_count"] == 2
    assert result["crew_station_count"] == 2 and result["crew_distribution_total"] == 11
    assert result["min_alive_crew_config"] == 3
    assert "private-sentinel" not in json.dumps(result)
    assert "unit" not in result and "speed" not in result and "crew_current" not in result


@pytest.mark.parametrize("value", [None, True, "12", [], {}, float("nan"), float("inf"), 10**500])
def test_static_numbers_reject_coercions_without_becoming_live_zero(value):
    unit = _unit()
    unit["ShipPhys"]["mass"]["Empty"] = value
    unit["ShipPhys"]["engines"]["maxSpeed"] = value
    unit["tank_crew"]["sailor2"]["crew"] = value
    result = builder.extract_static(unit)
    assert result["mass_empty_config"] is result["engine_forward_speed_config"] is None
    assert result["crew_distribution_total"] is None
    json.dumps(result, allow_nan=False)


def test_distinct_propeller_count_is_not_assumed_equal_to_engine_entries():
    unit = _unit()
    unit["ShipPhys"]["engines"]["engine"][1]["propeller"] = "propeller_01"
    result = builder.extract_static(unit)
    assert result["engine_entry_count"] == 2 and result["propulsion_count"] == 1
    del unit["ShipPhys"]["engines"]["engine"][1]["propeller"]
    assert builder.extract_static(unit)["propulsion_count"] is None


@pytest.mark.parametrize(
    "unit", [{}, {"ShipPhys": []}, {"tank_crew": []}, {"ShipPhys": {"engines": {"engine": [True]}}}]
)
def test_missing_or_different_ship_structure_is_unknown_not_zero(unit):
    result = builder.extract_static(unit)
    assert result["crew_distribution_total"] is result["propulsion_count"] is None
    assert all(value is None for key, value in result.items() if key != "engine_entry_count")


def test_hash_verified_build_is_deterministic_and_self_manifest_rebuilds_identically(tmp_path):
    manifest = _manifest(tmp_path)
    first = builder.build_catalog(tmp_path, manifest)
    assert static.validate_catalog(first)
    assert first == builder.build_catalog(tmp_path, first)
    assert first["coverage"]["parsed_files"] == 1
    assert "private-sentinel" not in json.dumps(first)


def test_cli_digest_matches_actual_output_bytes_on_every_platform(tmp_path, monkeypatch, capsys):
    manifest = _manifest(tmp_path)
    manifest_path, output = tmp_path / "manifest.json", tmp_path / "catalog.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["builder", "--source-dir", str(tmp_path),
                                    "--manifest", str(manifest_path), "--out", str(output)])
    builder.main()
    report = json.loads(capsys.readouterr().out)
    raw = output.read_bytes()
    assert report["catalog_bytes"] == len(raw)
    assert report["catalog_sha256"] == hashlib.sha256(raw).hexdigest()
    assert b"\r\n" not in raw


@pytest.mark.parametrize("change", ["hash", "size", "ref", "name", "duplicate", "missing", "directory", "repo"])
def test_incomplete_or_unpinned_source_cannot_produce_a_catalog(tmp_path, change):
    manifest = _manifest(tmp_path)
    if change == "hash":
        manifest["entries"][0]["sha"] = "b" * 40
    if change == "size":
        manifest["entries"][0]["size"] += 1
    if change == "ref":
        manifest["ref"] = "master"
    if change == "name":
        manifest["entries"][0]["name"] = "../example_ship.blkx"
    if change == "duplicate":
        manifest["entries"] *= 2
    if change == "missing":
        (tmp_path / "example_ship.blkx").unlink()
    if change == "directory":
        manifest["directory"] = "elsewhere"
    if change == "repo":
        manifest["repository"] = "other/repo"
    with pytest.raises((ValueError, OSError)):
        builder.build_catalog(tmp_path, manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("source", []),
        ("records", []),
        ("coverage", {}),
        ("records", {}),
    ],
)
def test_corrupt_schema_disables_reference_instead_of_accepting_partial_data(tmp_path, field, value, monkeypatch):
    catalog = builder.build_catalog(tmp_path, _manifest(tmp_path))
    catalog[field] = value
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(static, "CATALOG_PATH", path)
    assert _reference()["status"] == "catalog_unavailable"


@pytest.mark.parametrize("scenario", ["missing", "malformed", "too-large", "private-source"])
def test_unavailable_or_unsafe_catalog_never_leaks_source_data(tmp_path, scenario, monkeypatch):
    path = tmp_path / "catalog.json"
    if scenario == "malformed":
        path.write_text("{bad", encoding="utf-8")
    if scenario == "too-large":
        path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    if scenario == "private-source":
        catalog = builder.build_catalog(tmp_path, _manifest(tmp_path))
        catalog["source"]["private"] = "private-sentinel"
        path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(static, "CATALOG_PATH", path)
    result = _reference()
    assert result["status"] == "catalog_unavailable" and result["vehicle"] is None
    assert "private-sentinel" not in json.dumps(result)


@pytest.mark.parametrize("vehicle_id,engines", [("us_destroyer_fletcher", 2), ("us_pt6", 3)])
def test_packaged_static_examples_match_exactly_but_do_not_verify_live_semantics(vehicle_id, engines):
    result = _reference(_current(vehicle_id))
    assert result["status"] == "matched" and result["vehicle"]["id"] == vehicle_id
    assert result["vehicle"]["engine_entry_count"] == engines
    assert result["source"]["ref"] == "af0cce561a73704e30c1df66eff06209bcc3f035"
    assert result["source"]["version"] == "2.59.0.92"
    assert (
        result["game_version_verified"] is result["live_values_enriched"] is result["naval_semantics_verified"] is False
    )
    assert result["real_output_enabled"] is False and len(result["field_mapping"]) == 4
    assert set(result["vehicle"]) == {
        "id",
        "blob_sha",
        "type_code",
        "engine_entry_count",
        "propulsion_count",
        "crew_station_count",
        "crew_distribution_total",
        "configuration",
    }


@pytest.mark.parametrize(
    "vehicle_id",
    [
        "US_DESTROYER_FLETCHER",
        "us_destroyer_fletcher.blkx",
        "../us_pt6",
        "fletcher",
        "private-sentinel",
        None,
        True,
        [],
    ],
)
def test_unknown_or_noncanonical_identity_is_never_fuzzily_matched_or_echoed(vehicle_id):
    current = _current()
    current.raw["indicators"]["vehicle_type"] = vehicle_id
    result = _reference(current)
    assert result["vehicle"] is None
    assert "private-sentinel" not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    ["raw-type", "no-raw-type", "old-life", "old-battle", "stale", "failed", "legacy", "unknown", "dead", "replay"],
)
def test_current_instrument_provenance_is_required_to_associate_a_static_vehicle(change):
    current = _current()
    sample = current.raw["meta"]["naval_indicators"]
    if change == "raw-type":
        current.raw["indicators"]["raw"]["type"] = "ships/us_pt6"
    if change == "no-raw-type":
        del current.raw["indicators"]["raw"]["type"]
    if change == "old-life":
        sample["life_index"] = 2
    if change == "old-battle":
        sample["battle_id"] = "other"
    if change == "stale":
        sample["sample_timestamp"] = 994
    if change == "failed":
        sample["status"] = "probe_failed"
    if change == "legacy":
        del current.raw["meta"]["naval_indicators"]
    if change == "unknown":
        current.domain = "unknown"
    if change in {"dead", "replay"}:
        setattr(current, change, True)
    assert _reference(current)["vehicle"] is None


def test_known_naval_but_unindexed_id_never_uses_generic_or_fuzzy_profile():
    result = _reference(_current("unindexed_ship"))
    assert result["status"] == "not_indexed" and result["vehicle"] is None


@pytest.mark.parametrize("domain", ["air", "heli", "ground", "menu"])
def test_static_catalog_never_promotes_other_domains(domain):
    current = _current()
    current.domain = domain
    assert _reference(current) is None


def test_catalog_read_is_cached_and_returned_data_cannot_mutate_source_or_field_mapping():
    first = _reference()
    first["vehicle"]["engine_entry_count"] = 999
    first["field_mapping"][0]["static_paths"].clear()
    second = _reference()
    assert second["vehicle"]["engine_entry_count"] == 2
    assert second["field_mapping"][0]["static_paths"]
    assert static._load_catalog.cache_info().misses == 1 and static._load_catalog.cache_info().hits >= 1


def test_dashboard_static_reference_is_readonly_and_never_changes_detection_or_dispatch(monkeypatch):
    plugin, moment = _runtime(monkeypatch, dry_run=False)
    _evaluate(plugin, moment, _current())
    state = copy.deepcopy(plugin.state)
    detectors = copy.deepcopy([d.__dict__ for d in plugin.engine.detectors])
    timeline, config = plugin.timeline.snapshot(), plugin.cfg.to_dict()
    for _ in range(5):
        result = asyncio.run(plugin.dashboard_context())["naval_static_reference"]
        assert result["status"] == "matched" and result["real_output_enabled"] is False
        assert "forward_speed_config" not in json.dumps(result)
    assert plugin.state == state
    assert [d.__dict__ for d in plugin.engine.detectors] == detectors
    assert plugin.timeline.snapshot() == timeline and plugin.cfg.to_dict() == config
    assert plugin.pushed_messages == plugin.config_updates == []
