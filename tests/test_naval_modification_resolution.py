"""Declaration inheritance must never manufacture installed/effective parameters."""

import asyncio
import copy
import hashlib
import importlib
import json

import pytest
from test_naval_static_reference import _current, _evaluate, _manifest, _reference, _runtime, builder, static

resolution = importlib.import_module("naval_modification_resolution")
_atoms, resolve_modifications = resolution._atoms, resolution.resolve_modifications


@pytest.fixture(autouse=True)
def clear_cache():
    static._load_catalog.cache_clear()
    yield
    static._load_catalog.cache_clear()


def resolve(local, common=None, templates=None, **unit):
    return resolve_modifications(
        {"modifications": local, **unit}, {"modifications": common or {}, "templates": templates or {}}
    )


def test_common_empty_reference_local_override_and_explicit_empty_blocks_are_distinct():
    result = resolve(
        {"engine": {"prevModification": "screw", "disableModEffects": {}}, "screw": {}},
        {
            "engine": {
                "prevModification": "hull",
                "invertEnableLogic": True,
                "effects": {"mulMaxSpeed": 0.93},
                "disableModEffects": {"repair": True},
            },
            "screw": {},
        },
    )
    engine = result["modifications"]["engine"]
    assert engine["metadata_candidates"]["prevModification"] == ["screw"]
    assert engine["metadata_origins"] == {"invertEnableLogic": "common", "prevModification": "unit"}
    block = engine["blocks"]["disableModEffects"]
    assert block["layers"]["unit"]["atoms"] == {}
    assert block["layers"]["common"]["atoms"] == {"repair": True}
    assert block["merge_status"] == "not_simulated"
    assert result["summary"]["missing_dependency_count"] == 0
    assert result["summary"]["explicit_empty_block_count"] == 1
    assert result["effective_parameters"] is None
    assert all(
        result["summary"][k] is False
        for k in ("effective_parameters_available", "installed_state_known", "engine_composition_verified")
    )


def test_missing_references_and_cycles_never_auto_add_common_modifications():
    result = resolve({"a": {"prevModification": "b"}, "b": {"reqModification": ["a", "outside"]}}, {"outside": {}})
    summary = result["summary"]
    assert summary["status"] == "partial"
    assert summary["cycle_node_count"] == 2 and summary["missing_dependency_count"] == 1
    assert summary["missing_common_definition_count"] == 2
    assert set(result["modifications"]) == {"a", "b"}


def test_overlapping_cycles_count_all_participating_nodes_and_invalid_targets_are_missing():
    result = resolve(
        {
            "a": {"prevModification": ["b", "c"]},
            "b": {"prevModification": "a"},
            "c": {"prevModification": ["b", "bad"]},
            "bad": True,
        }
    )
    assert result["summary"]["cycle_node_count"] == 3
    assert result["summary"]["missing_dependency_count"] == 1


def test_template_reference_keeps_external_weapon_copy_unresolved_and_counts_invalid_effects():
    result = resolve(
        {"gun": {}},
        {"gun": {"modUpgradeType": "new_gun", "modOverdriveType": "absent"}},
        {
            "new_gun": {
                "copyWeaponMod": True,
                "upgradeEffect": {"factor": 0.9, "references": ["private-sentinel"]},
                "effects": [],
            }
        },
    )
    assert result["summary"]["external_weapon_template_count"] == 1
    assert result["summary"]["missing_template_count"] == 1
    assert result["summary"]["invalid_declaration_count"] == 1
    assert result["summary"]["uninterpreted_effect_value_count"] == 2
    assert "private-sentinel" not in json.dumps(result)
    assert result["effective_parameters"] is None


@pytest.mark.parametrize("value", [None, True, [True], {}, "../private-sentinel"])
def test_invalid_local_scalar_never_falls_back_to_valid_common(value):
    result = resolve({"engine": {"prevModification": value}}, {"engine": {"prevModification": "screw"}})
    assert result["modifications"]["engine"]["metadata_candidates"]["prevModification"] is None
    assert result["modifications"]["engine"]["metadata_origins"]["prevModification"] == "unit"
    assert result["summary"]["status"] == "partial"


@pytest.mark.parametrize("directive", ["include", "_include", "extends", "_extends", "inherit", "_use", "baseFile"])
def test_file_inheritance_directives_are_explicitly_unresolved(directive):
    result = resolve({}, **{directive: "private-sentinel"})
    assert result["summary"]["base_status"] == "unresolved_directives"
    assert result["summary"]["status"] == "partial"
    assert "private-sentinel" not in json.dumps(result)


@pytest.mark.parametrize("local", [None, [], {"bad/path": {}}, {"bad": True}, {str(i): {} for i in range(257)}])
def test_invalid_modification_container_is_reported_without_fabricating_zero_effect(local):
    result = resolve(local)
    assert result["summary"]["status"] == "partial"
    assert result["summary"]["invalid_declaration_count"] > 0
    assert result["effective_parameters"] is None


def test_effect_atom_report_is_bounded_and_does_not_coerce_uninterpreted_values():
    values = {f"v{i}": i for i in range(2100)}
    values.update(other=[1], text="private-sentinel", nan=float("nan"), enabled=True)
    result = _atoms(values)
    assert len(result["atoms"]) == 2048 and result["uninterpreted_values"] >= 56
    assert "private-sentinel" not in json.dumps(result, allow_nan=False)


def _build_v2(tmp_path):
    unit = {"modifications": {"engine": {"effects": {"speed": 123.45}}}}
    manifest = _manifest(tmp_path, unit)
    raw = json.dumps({"modifications": {"engine": {"effects": {"speed": 0.93}}}, "templates": {}}).encode()
    path = tmp_path / "modifications.blkx"
    path.write_bytes(raw)
    manifest["modification_source"] = {
        "path": static.MODIFICATION_SOURCE,
        "source_bytes": len(raw),
        "blob_sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
    }
    return manifest, path


def test_hash_verified_v2_self_manifest_and_runtime_projection_exclude_effect_values(tmp_path, monkeypatch):
    manifest, definitions = _build_v2(tmp_path)
    report = {}
    catalog = builder.build_catalog(tmp_path, manifest, modifications_file=definitions, resolution_report=report)
    assert catalog == builder.build_catalog(tmp_path, catalog, modifications_file=definitions)
    assert catalog["schema_version"] == 2 and static.validate_catalog(catalog)
    assert "123.45" in json.dumps(report) and "123.45" not in json.dumps(catalog)
    catalog["records"]["us_destroyer_fletcher"] = catalog["records"].pop("example_ship")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(static, "CATALOG_PATH", path)
    result = _reference()
    assert result["vehicle"]["configuration"]["declared_count"] == 1
    assert result["effective_parameters_available"] is False
    result["vehicle"]["configuration"]["declared_count"] = 100
    assert _reference()["vehicle"]["configuration"]["declared_count"] == 1
    plugin, moment = _runtime(monkeypatch)
    # The real entrypoint may import a second package namespace in SDK fixtures.
    # Inject into its actual projection globals, then verify the dashboard seam.
    projection = plugin.dashboard_context.__globals__["snapshot_naval_static_reference"]
    monkeypatch.setitem(projection.__globals__, "_load_catalog", lambda: catalog)
    _evaluate(plugin, moment, _current())
    dashboard = asyncio.run(plugin.dashboard_context())["naval_static_reference"]
    assert dashboard["vehicle"]["configuration"]["declared_count"] == 1
    assert dashboard["effective_parameters_available"] is False
    assert "123.45" not in json.dumps(dashboard)
    assert plugin.pushed_messages == plugin.config_updates == []


@pytest.mark.parametrize("change", ["hash", "size", "path", "missing-file", "missing-descriptor"])
def test_unverified_common_definitions_cannot_build_v2(tmp_path, change):
    manifest, path = _build_v2(tmp_path)
    if change == "hash":
        manifest["modification_source"]["blob_sha"] = "b" * 40
    if change == "size":
        manifest["modification_source"]["source_bytes"] += 1
    if change == "path":
        manifest["modification_source"]["path"] = "other"
    if change == "missing-file":
        path = None
    if change == "missing-descriptor":
        del manifest["modification_source"]
        manifest["schema_version"] = 2
        path = None  # A broken v2 manifest must not silently rebuild as legacy v1.
    with pytest.raises(ValueError):
        builder.build_catalog(tmp_path, manifest, modifications_file=path)


@pytest.mark.parametrize(
    "key,value",
    [
        ("effective_parameters_available", True),
        ("installed_state_known", 1),
        ("engine_composition_verified", True),
        ("declared_count", True),
        ("declared_count", -1),
        ("status", "effective"),
        ("base_status", "fully_inherited"),
        ("private", "private-sentinel"),
        ("template_reference_count", 999),
        ("common_definition_count", 99),
        ("status", "none_declared"),
        ("base_status", "unresolved_directives"),
        ("missing_dependency_count", 1),
    ],
)
def test_corrupt_resolution_summary_disables_entire_catalog(tmp_path, key, value):
    manifest, path = _build_v2(tmp_path)
    catalog = builder.build_catalog(tmp_path, manifest, modifications_file=path)
    catalog["records"]["example_ship"]["configuration"][key] = value
    assert not static.validate_catalog(catalog)


def test_legacy_catalog_remains_readonly_without_claiming_resolution(tmp_path, monkeypatch):
    catalog = builder.build_catalog(tmp_path, _manifest(tmp_path))
    catalog["records"]["us_destroyer_fletcher"] = catalog["records"].pop("example_ship")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(static, "CATALOG_PATH", path)
    result = _reference()
    assert result["catalog_schema_version"] == 1
    assert "configuration" not in result["vehicle"]
    assert result["effective_parameters_available"] is False


def test_resolution_does_not_mutate_input_declarations():
    unit = {"modifications": {"a": {"prevModification": ["b"], "effects": {"nested": {"v": 1}}}}}
    definitions = {"modifications": {"a": {}}, "templates": {}}
    before = copy.deepcopy((unit, definitions))
    resolve_modifications(unit, definitions)
    assert (unit, definitions) == before


def test_special_metadata_remains_explicitly_uninterpreted_without_exposing_values():
    result = resolve(
        {"a": {"turn_it_off": "private-sentinel", "rcostAddParam": 1}}, {"a": {"image": "private-sentinel"}}
    )
    assert result["modifications"]["a"]["other_declaration_keys"] == {
        "common": ["image"],
        "unit": ["rcostAddParam", "turn_it_off"],
    }
    assert "private-sentinel" not in json.dumps(result)
    assert result["effective_parameters"] is None
