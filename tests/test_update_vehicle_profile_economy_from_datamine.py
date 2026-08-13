"""Tests for Datamine economy/rank metadata profile updates."""

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


def _write_datamine_fixture(root: Path) -> None:
    _write_json(
        root / "char.vromfs.bin_u" / "config" / "wpcost.blkx",
        {
            "a_10c": {
                "rank": 7,
                "economicRankArcade": 31,
                "economicRankHistorical": 32,
                "economicRankSimulation": 33,
                "country": "country_usa",
                "unitClass": "exp_assault",
                "unitMoveType": "air",
                "weapons": {"huge": "ignored"},
                "modifications": {"huge": "ignored"},
            },
            "su_30mkk": {
                "rank": 8,
                "economicRankArcade": 37,
                "economicRankHistorical": 37,
                "economicRankSimulation": 37,
                "country": "country_china",
                "unitClass": "exp_fighter",
                "unitMoveType": "air",
            },
            "us_m1_abrams": {
                "rank": 7,
                "economicRankHistorical": 35,
                "country": "country_usa",
                "unitClass": "exp_tank",
                "unitMoveType": "tank",
            },
        },
    )


def test_update_profiles_adds_small_economy_metadata_to_existing_air_profiles(tmp_path):
    import update_vehicle_profile_economy_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(
        profiles,
        {
            "_default": {},
            "a-10c": {"class": "subsonic_attacker_jet"},
            "a_10c": {"class": "subsonic_attacker_jet"},
            "su_30mkk": {"class": "heavy_modern_fighter"},
        },
    )
    _write_datamine_fixture(tmp_path)

    report = updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert report["air_records"] == 2
    assert report["matched_records"] == 2
    assert report["updated"] == 3
    assert data["a-10c"]["rank"] == 7
    assert data["a-10c"]["economic_rank_realistic"] == 32
    assert data["a-10c"]["economic_rank_arcade"] == 31
    assert data["a-10c"]["economic_rank_simulation"] == 33
    assert data["a-10c"]["country"] == "usa"
    assert data["a-10c"]["unit_class"] == "exp_assault"
    assert data["a-10c"]["unit_move_type"] == "air"
    assert data["a_10c"]["rank"] == 7
    assert data["su_30mkk"]["country"] == "china"
    assert "weapons" not in data["a-10c"]
    assert "modifications" not in data["a-10c"]


def test_update_profiles_skips_non_air_and_does_not_create_new_aliases(tmp_path):
    import update_vehicle_profile_economy_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(profiles, {"_default": {}, "us_m1_abrams": {}, "a-10c": {}})
    _write_datamine_fixture(tmp_path)

    updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert "rank" not in data["us_m1_abrams"]
    assert "su_30mkk" not in data
    assert data["a-10c"]["rank"] == 7


def test_update_profiles_preserves_existing_metadata_by_default(tmp_path):
    import update_vehicle_profile_economy_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(profiles, {"_default": {}, "su_30mkk": {"rank": 6, "country": "ussr"}})
    _write_datamine_fixture(tmp_path)

    report = updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert data["su_30mkk"]["rank"] == 6
    assert data["su_30mkk"]["country"] == "ussr"
    assert data["su_30mkk"]["economic_rank_realistic"] == 37
    assert report["fields_preserved"] == 2


def test_update_profiles_can_overwrite_existing_metadata(tmp_path):
    import update_vehicle_profile_economy_from_datamine as updater

    profiles = tmp_path / "vehicle_profiles.json"
    _write_json(profiles, {"_default": {}, "su_30mkk": {"rank": 6, "country": "ussr"}})
    _write_datamine_fixture(tmp_path)

    updater.update_profiles(profiles_path=profiles, datamine_root=tmp_path, overwrite_existing=True)
    data = json.loads(profiles.read_text(encoding="utf-8"))

    assert data["su_30mkk"]["rank"] == 8
    assert data["su_30mkk"]["country"] == "china"
