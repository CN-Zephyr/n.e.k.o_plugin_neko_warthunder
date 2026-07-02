"""Tests for read-only War Thunder Datamine candidate extraction."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def test_extracts_stall_aoa_overspeed_candidates_from_fm():
    from datamine_profile_candidates import extract_candidates

    fm = {
        "Aerodynamics": {
            "WingPlane": {
                "FlapsPolar0": {"alphaCritHigh": 29.0},
                "FlapsPolar1": {"alphaCritHigh": 31.0},
                "Strength": {"VNE": 1555.0, "MNE": 2.2},
            }
        },
        "Autopilot": {"Pitch": {"AoaLimits": [-15.0, 21.0]}},
        "Passport": {
            "Alt": {
                "stallSpeed": [1000.0, 158.04],
                "stallSpeedLanding": [1000.0, 139.68],
            }
        },
    }

    report = extract_candidates("f_16c_block_50", unit={"fmFile": "fm/f_16c_block_50.blk"}, fm=fm)

    assert report["stall"]["stall_critical_kmh"] == 158
    assert report["stall"]["stall_warn_kmh"] == 181.7
    assert report["aoa"]["autopilot_aoa_limits"] == [-15.0, 21.0]
    assert report["aoa"]["aoa_critical_deg"] == 21
    assert report["aoa"]["aoa_warn_deg"] == 17.8
    assert report["overspeed"]["overspeed_critical_kmh"] == 1555
    assert report["overspeed"]["overspeed_warn_mach"] == 1.98


def test_overheat_stays_evidence_not_threshold():
    from datamine_profile_candidates import extract_candidates

    fm = {
        "EngineType0": {
            "Main": {"Type": "Radial", "IsWaterCooled": False},
            "Temperature": {
                "WaterBoilingTemperature": 280.0,
                "OilBoilingTemperature": 360.0,
                "OilThermostatSetPoint": 30.0,
                "Mode0": {"WaterTemperature": 118.0, "OilTemperature": 35.0},
                "Mode1": {"WaterTemperature": 170.749, "OilTemperature": 66.6824},
            },
        }
    }

    report = extract_candidates("a6m5_hei", unit={"overheatBlk": "gameData/FlightModels/dm/overheat.blk"}, fm=fm)

    overheat = report["overheat"]
    assert "overheat_warn_c" not in overheat
    assert "overheat_critical_c" not in overheat
    assert overheat["overheat_blk"] == "gameData/FlightModels/dm/overheat.blk"
    assert overheat["engine_temperature_evidence"][0]["engine_type"] == "Radial"
    assert overheat["engine_temperature_evidence"][0]["max_mode_water_temperature_c"] == 170.7
    assert overheat["engine_temperature_evidence"][0]["max_mode_oil_temperature_c"] == 66.7


def test_extracts_fm_candidates_when_unit_file_is_absent():
    from datamine_profile_candidates import extract_candidates

    fm = {
        "Aerodynamics": {"WingPlane": {"FlapsPolar0": {"alphaCritHigh": 17.0}}},
        "Passport": {"Alt": {"stallSpeed": [1000.0, 142.106]}},
    }

    report = extract_candidates("a6m5_hei", unit=None, fm=fm)

    assert report["datamine"] == {}
    assert report["stall"]["stall_critical_kmh"] == 142.1
    assert report["aoa"]["aoa_critical_deg"] == 17
