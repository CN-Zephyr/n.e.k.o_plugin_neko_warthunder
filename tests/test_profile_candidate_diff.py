"""Tests for profile-vs-Datamine candidate diff reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def test_profile_candidate_diff_reports_missing_and_different_fields(tmp_path):
    from profile_candidate_diff import build_report

    profiles = {
        "_default": {
            "stall_warn_kmh": 250,
            "stall_critical_kmh": 200,
            "aoa_warn_deg": 14,
            "aoa_critical_deg": 18,
            "overspeed_warn_kmh": 750,
            "overspeed_critical_kmh": 850,
        },
        "f_16c_block_50": {
            "class": "modern_jet",
            "stall_warn_kmh": 250,
            "stall_critical_kmh": 200,
            "aoa_warn_deg": 26,
            "aoa_critical_deg": 32,
            "overspeed_warn_kmh": 1400,
            "overspeed_critical_kmh": 1555,
        },
    }
    profiles_path = tmp_path / "profiles.json"
    profiles_path.write_text(json.dumps(profiles), encoding="utf-8")
    candidate_report = {
        "source": "unit-test",
        "ref": "test",
        "results": [
            {
                "vehicle": "f_16c_block_50",
                "stall": {"stall_critical_kmh": 158, "stall_warn_kmh": 181.7},
                "aoa": {"aoa_critical_deg": 21, "aoa_warn_deg": 17.8},
                "overspeed": {
                    "overspeed_critical_kmh": 1555,
                    "overspeed_warn_kmh": 1399.5,
                    "overspeed_critical_mach": 2.2,
                },
                "overheat": {"engine_temperature_evidence": [{"engine": "EngineType0"}]},
            }
        ],
    }

    report = build_report(profiles_path=profiles_path, candidate_report=candidate_report)
    row = report["vehicles"][0]

    assert row["action"] == "add_or_review_missing_candidate_fields"
    assert row["counts"]["diff"] == 4
    assert row["counts"]["missing_current"] == 1
    assert row["overheat_evidence"]["policy"] == "report_only_not_threshold"


def test_profile_candidate_diff_accepts_tolerated_values(tmp_path):
    from profile_candidate_diff import build_report

    profiles = {
        "_default": {"stall_warn_kmh": 180, "stall_critical_kmh": 160},
        "a6m5_hei": {"class": "ww2_prop_fighter", "stall_warn_kmh": 181, "stall_critical_kmh": 158},
    }
    profiles_path = tmp_path / "profiles.json"
    profiles_path.write_text(json.dumps(profiles), encoding="utf-8")
    candidate_report = {
        "source": "unit-test",
        "ref": "test",
        "results": [{"vehicle": "a6m5_hei", "stall": {"stall_critical_kmh": 158.3, "stall_warn_kmh": 181.9}}],
    }

    report = build_report(profiles_path=profiles_path, candidate_report=candidate_report)

    assert report["vehicles"][0]["action"] == "candidate_matches_current_profile"
    assert report["vehicles"][0]["counts"] == {"match": 2, "diff": 0, "missing_current": 0}
