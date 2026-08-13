"""Tests for bulk vehicle profile updates from local Datamine files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _minimal_fm() -> dict:
    return {
        "Aerodynamics": {
            "WingPlane": {
                "FlapsPolar0": {"alphaCritHigh": 29.0},
                "Strength": {"VNE": 1540.0, "MNE": 2.1, "CritOverload": [-550000.0, 1450000.0]},
            }
        },
        "Mass": {"EmptyMass": 17520.0, "MaxFuelMass0": 9400.0},
        "Instructor": {"loadFactorLimit": [-5.0, 12.0], "limitOverload": True},
        "Autopilot": {"Pitch": {"AoaLimits": [-15.0, 22.0]}},
        "Passport": {"Alt": {"stallSpeed": [1000.0, 158.04]}},
        "EngineType0": {
            "Main": {
                "Type": "Jet",
                "IsWaterCooled": False,
                "FuelConsumptionOnIdle": 0.35,
                "FuelConsumptionOnHalfThr": 0.9,
                "FuelConsumptionOnFullThr": 1.8,
                "FuelConsumptionOnWEP": 3.2,
                "EngineInertiaMoment": 439.0,
            },
            "Temperature": {
                "Load0": {"WaterTemperature": 600.0, "OilTemperature": 70.0},
                "Load1": {"WaterTemperature": 740.0, "OilTemperature": 85.0, "WorkTime": 3600.0},
                "Load2": {"WaterTemperature": 790.0, "OilTemperature": 95.0, "WorkTime": 1800.0},
                "Load3": {"WaterTemperature": 805.0, "OilTemperature": 100.0, "WorkTime": 900.0},
                "Load4": {"WaterTemperature": 815.0, "OilTemperature": 110.0, "WorkTime": 300.0},
                "Load5": {"WaterTemperature": 830.0, "OilTemperature": 120.0, "WorkTime": 30.0},
            },
        },
    }


def _write_datamine_fixture(root: Path) -> None:
    flightmodels = root / "aces.vromfs.bin_u" / "gamedata" / "flightmodels"
    _write_json(
        flightmodels / "su_30mkk.blkx",
        {"type": "typeFighter", "fmFile": "fm/su_30mkk.blk", "overheatBlk": "gameData/FlightModels/DM/overheat.blk"},
    )
    _write_json(flightmodels / "fm" / "su_30mkk.blkx", _minimal_fm())
    _write_json(flightmodels / "ah_1g.blkx", {"type": "typeFighter", "helicopter": {}, "fmFile": "fm/ah_1g.blk"})
    _write_json(flightmodels / "fm" / "ah_1g.blkx", _minimal_fm())


def test_update_profiles_adds_missing_exact_aircraft_from_datamine(tmp_path):
    import update_vehicle_profiles_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(profiles, {"_default": {"stall_warn_kmh": 250}})
    _write_datamine_fixture(tmp_path)

    report = updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert report["created"] == 1
    assert data["su_30mkk"]["class"] == "heavy_modern_fighter"
    assert data["su_30mkk"]["overspeed_critical_kmh"] == 1540
    assert data["su_30mkk"]["overspeed_critical_mach"] == 2.1
    assert data["su_30mkk"]["aoa_critical_deg"] == 22
    assert data["su_30mkk"]["turbine_temp_warn_c"] == 790
    assert data["su_30mkk"]["oil_temp_warn_c"] == 100
    assert data["su_30mkk"]["empty_mass_kg"] == 17520
    assert data["su_30mkk"]["max_fuel_mass_kg"] == 9400
    assert data["su_30mkk"]["structure_overload_positive_n"] == 1450000
    assert data["su_30mkk"]["g_limit_positive_empty_candidate"] == 8.44
    assert data["su_30mkk"]["g_limit_positive_full_fuel_candidate"] == 5.49
    assert data["su_30mkk"]["instructor_g_limit_positive"] == 12
    assert data["su_30mkk"]["fuel_consumption_wep_total"] == 3.2
    assert data["su_30mkk"]["engine_inertia_moment_max"] == 439
    assert "ah_1g" not in data


def test_update_profiles_preserves_existing_fields_by_default(tmp_path):
    import update_vehicle_profiles_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(
        profiles,
        {
            "_default": {"stall_warn_kmh": 250},
            "su_30mkk": {"overspeed_critical_kmh": 1500, "stall_warn_kmh": 180},
        },
    )
    _write_datamine_fixture(tmp_path)

    report = updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert report["updated"] == 1
    assert data["su_30mkk"]["overspeed_critical_kmh"] == 1500
    assert data["su_30mkk"]["stall_warn_kmh"] == 180
    assert data["su_30mkk"]["class"] == "heavy_modern_fighter"
    assert data["su_30mkk"]["turbine_temp_critical_c"] == 830
    assert data["su_30mkk"]["structure_overload_negative_n"] == -550000


def test_update_profiles_backfills_existing_fm_stem_alias_without_creating_new_alias(tmp_path):
    import update_vehicle_profiles_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(
        profiles,
        {
            "_default": {"stall_warn_kmh": 250},
            "fm_base": {"class": "ww2_prop_fighter"},
        },
    )
    flightmodels = tmp_path / "aces.vromfs.bin_u" / "gamedata" / "flightmodels"
    _write_json(flightmodels / "unit_alias.blkx", {"type": "typeFighter", "fmFile": "fm/fm_base.blk"})
    _write_json(flightmodels / "fm" / "fm_base.blkx", _minimal_fm())

    report = updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert report["created"] == 1
    assert report["updated"] == 1
    assert data["unit_alias"]["stall_critical_kmh"] == 158
    assert data["fm_base"]["stall_critical_kmh"] == 158
    assert data["fm_base"]["overspeed_critical_mach"] == 2.1
    assert "fm-base" not in data


def test_update_profiles_adds_evidence_to_tested_entries_without_replacing_thresholds(tmp_path):
    import update_vehicle_profiles_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(
        profiles,
        {
            "_default": {"stall_warn_kmh": 250},
            "su_30mkk": {
                "_tested": True,
                "overspeed_critical_kmh": 1500,
                "stall_warn_kmh": 180,
            },
        },
    )
    _write_datamine_fixture(tmp_path)

    updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert data["su_30mkk"]["overspeed_critical_kmh"] == 1500
    assert data["su_30mkk"]["stall_warn_kmh"] == 180
    assert "turbine_temp_critical_c" not in data["su_30mkk"]
    assert data["su_30mkk"]["structure_overload_positive_n"] == 1450000
    assert data["su_30mkk"]["g_limit_positive_empty_candidate"] == 8.44
    assert data["su_30mkk"]["fuel_consumption_full_total"] == 1.8


def test_update_profiles_drops_suspect_jet_ias_without_mach(tmp_path):
    import update_vehicle_profiles_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(
        profiles,
        {
            "_default": {"overspeed_critical_kmh": 850},
            "_classes": {"heavy_modern_fighter": {"overspeed_critical_kmh": 1500}},
        },
    )
    flightmodels = tmp_path / "aces.vromfs.bin_u" / "gamedata" / "flightmodels"
    fm = _minimal_fm()
    fm["Aerodynamics"]["WingPlane"]["Strength"] = {"VNE": 850.0}
    _write_json(flightmodels / "f_14b.blkx", {"type": "typeFighter", "fmFile": "fm/f_14b.blk"})
    _write_json(flightmodels / "fm" / "f_14b.blkx", fm)

    updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert data["f_14b"]["class"] == "heavy_modern_fighter"
    assert "overspeed_critical_kmh" not in data["f_14b"]


def test_update_profiles_uses_fm_identity_for_performance_class_aliases(tmp_path):
    import update_vehicle_profiles_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(
        profiles,
        {
            "_default": {"stall_warn_kmh": 250},
            "su_24m": {"class": "modern_jet"},
        },
    )
    flightmodels = tmp_path / "aces.vromfs.bin_u" / "gamedata" / "flightmodels"
    fm = _minimal_fm()
    fm["Aerodynamics"]["WingPlane"]["Strength"] = {"VNE": 1100.0, "MNE": 0.92}
    _write_json(
        flightmodels / "nt_su_24m.blkx",
        {"model": "su_24m", "type": "typeStormovik", "fmFile": "fm/su_24m.blk"},
    )
    _write_json(flightmodels / "fm" / "su_24m.blkx", fm)

    report = updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert report["created"] == 1
    assert data["nt_su_24m"]["class"] == "supersonic_attacker_jet"
    assert data["su_24m"]["class"] == "supersonic_attacker_jet"
