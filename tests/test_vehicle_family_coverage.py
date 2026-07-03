"""Tests for vehicle family coverage reports."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _write_profiles(path: Path) -> None:
    profiles = {
        "_classes": {
            "modern_high_alpha_fighter": {"overspeed_critical_kmh": 1555},
            "heavy_modern_fighter": {"overspeed_critical_kmh": 1540},
        },
        "_families": [
            {"prefix": "f16", "label": "F-16", "class": "modern_high_alpha_fighter"},
            {"prefix": "f16c", "label": "F-16C", "class": "modern_high_alpha_fighter"},
            {"prefix": "falcon", "label": "F-16", "class": "modern_high_alpha_fighter"},
            {"prefix": "16c", "label": "F-16C alias", "class": "modern_high_alpha_fighter"},
            {"prefix": "su30", "label": "Su-30", "class": "heavy_modern_fighter"},
            {"prefix": "f4", "label": "F-4 Phantom II", "class": "heavy_modern_fighter"},
            {"prefix": "f4u", "label": "F4U Corsair", "class": "modern_high_alpha_fighter"},
            {"prefix": "f4f", "label": "F4F Wildcat", "class": "modern_high_alpha_fighter"},
            {"prefix": "ghost", "label": "Ghost", "class": "missing_class"},
        ],
        "f_16c_block_50": {
            "class": "modern_high_alpha_fighter",
            "stall_warn_kmh": 180,
            "stall_critical_kmh": 158,
            "aoa_warn_deg": 18,
            "aoa_critical_deg": 21,
            "overspeed_critical_kmh": 1555,
            "rank": 8,
            "country": "usa",
            "unit_class": "exp_fighter",
            "structure_overload_positive_n": 770000,
        },
        "f_16a": {
            "class": "modern_high_alpha_fighter",
            "stall_warn_kmh": 180,
            "stall_critical_kmh": 158,
            "aoa_warn_deg": 18,
            "aoa_critical_deg": 21,
            "overspeed_critical_kmh": 1555,
            "rank": 7,
            "country": "usa",
            "unit_class": "exp_fighter",
            "structure_overload_positive_n": 760000,
        },
        "su_30mkk": {
            "class": "heavy_modern_fighter",
            "overspeed_critical_mach": 2.1,
            "oil_temp_warn_c": 100,
            "oil_temp_critical_c": 110,
            "turbine_temp_warn_c": 790,
            "turbine_temp_critical_c": 830,
            "fuel_consumption_full_total": 0.88,
            "rank": 8,
            "country": "china",
            "unit_class": "exp_fighter",
        },
        "f-4e": {
            "class": "heavy_modern_fighter",
            "stall_warn_kmh": 180,
            "stall_critical_kmh": 158,
            "aoa_warn_deg": 18,
            "aoa_critical_deg": 21,
            "overspeed_critical_kmh": 1450,
            "rank": 7,
            "country": "usa",
            "unit_class": "exp_fighter",
            "structure_overload_positive_n": 770000,
        },
        "f4u-1a": {
            "class": "modern_high_alpha_fighter",
            "stall_warn_kmh": 160,
            "stall_critical_kmh": 140,
            "aoa_warn_deg": 16,
            "aoa_critical_deg": 20,
            "overspeed_critical_kmh": 800,
            "rank": 3,
            "country": "usa",
            "unit_class": "exp_fighter",
            "structure_overload_positive_n": 220000,
        },
        "f4f-4": {
            "class": "modern_high_alpha_fighter",
            "stall_warn_kmh": 150,
            "stall_critical_kmh": 130,
            "aoa_warn_deg": 16,
            "aoa_critical_deg": 20,
            "overspeed_critical_kmh": 750,
            "rank": 2,
            "country": "usa",
            "unit_class": "exp_fighter",
            "structure_overload_positive_n": 200000,
        },
    }
    path.write_text(json.dumps(profiles), encoding="utf-8")


def test_vehicle_family_coverage_reports_exact_and_family_counts(tmp_path):
    from vehicle_family_coverage import build_report

    profiles = tmp_path / "vehicle_profiles.json"
    _write_profiles(profiles)

    report = build_report(profiles_path=profiles)

    assert report["summary"]["exact_profiles"] == 6
    assert report["summary"]["families"] == 9
    assert report["summary"]["exact_coverage"]["economy_metadata"] == 6
    f16 = next(row for row in report["families"] if row["label"] == "F-16")
    assert f16["exact_count"] == 1
    assert f16["coverage"]["stall"] == 1
    assert f16["coverage"]["turbine_temperature"] == 0
    assert "F-16C" in f16["narrower_family_prefixes"]
    assert "has_narrower_family_prefixes" in f16["risks"]
    falcon = next(row for row in report["families"] if row["prefix"] == "falcon")
    assert falcon["sibling_family_exact_count"] == 1
    assert "alias_family_no_exact_matches" in falcon["risks"]
    infix = next(row for row in report["families"] if row["prefix"] == "16c")
    assert infix["infix_exact_count"] == 1
    assert "infix_family_no_exact_matches" in infix["risks"]


def test_vehicle_family_coverage_uses_runtime_longest_prefix_semantics(tmp_path):
    from vehicle_family_coverage import build_report

    profiles = tmp_path / "vehicle_profiles.json"
    _write_profiles(profiles)

    report = build_report(profiles_path=profiles)
    phantom = next(row for row in report["families"] if row["label"] == "F-4 Phantom II")
    corsair = next(row for row in report["families"] if row["label"] == "F4U Corsair")
    wildcat = next(row for row in report["families"] if row["label"] == "F4F Wildcat")

    assert phantom["exact_samples"] == ["f-4e"]
    assert phantom["shadowed_exact_count"] == 2
    assert set(phantom["shadowed_exact_samples"]) == {"f4u-1a", "f4f-4"}
    assert corsair["exact_samples"] == ["f4u-1a"]
    assert wildcat["exact_samples"] == ["f4f-4"]


def test_vehicle_family_coverage_flags_missing_class_and_empty_family(tmp_path):
    from vehicle_family_coverage import build_report

    profiles = tmp_path / "vehicle_profiles.json"
    _write_profiles(profiles)

    report = build_report(profiles_path=profiles)
    ghost = next(row for row in report["families"] if row["label"] == "Ghost")

    assert ghost["exact_count"] == 0
    assert "missing_class_template" in ghost["risks"]
    assert "no_exact_matches" in ghost["risks"]
    assert report["priority_gaps"][0]["label"] == "Ghost"


def test_vehicle_family_coverage_cli_outputs_json_and_text(tmp_path):
    import vehicle_family_coverage

    profiles = tmp_path / "vehicle_profiles.json"
    output_path = tmp_path / "reports" / "families.json"
    _write_profiles(profiles)

    json_output = io.StringIO()
    with contextlib.redirect_stdout(json_output):
        rc = vehicle_family_coverage.main(["--profiles", str(profiles), "--json", "--output", str(output_path)])

    assert rc == 0
    payload = json.loads(json_output.getvalue())
    assert payload["status"] == "pass"
    assert output_path.exists()

    text_output = io.StringIO()
    with contextlib.redirect_stdout(text_output):
        rc = vehicle_family_coverage.main(["--profiles", str(profiles)])

    assert rc == 0
    text = text_output.getvalue()
    assert "vehicle family coverage" in text
    assert "priority_gaps" in text
