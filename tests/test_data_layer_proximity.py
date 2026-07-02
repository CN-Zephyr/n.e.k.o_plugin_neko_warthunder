"""Regression tests for vendored data-layer proximity helpers."""

from __future__ import annotations

import sys
from pathlib import Path


DATA_PROCESS = Path(__file__).resolve().parents[1] / "data_layer" / "data process"
if str(DATA_PROCESS) not in sys.path:
    sys.path.insert(0, str(DATA_PROCESS))


def test_proximity_thresholds_use_profile_without_type_error():
    from wt_proximity import resolve_proximity_thresholds

    profiles = {
        "_default": {"proximity_warn_m": 3000},
        "f-4f_kws_lv": {"proximity_warn_m": 5000},
    }

    assert resolve_proximity_thresholds(profiles, "air", "f-4f_kws_lv") == (
        5000,
        None,
    )


def test_vehicle_profile_exact_entries_keep_precise_overspeed_limits():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cfg, matched, source, family = _merge_profile(
        processor.profiles,
        "su_30mk2v_venezuela",
        "air",
        processor._family_rules,
    )

    assert matched is True
    assert source == "exact"
    assert family is None
    assert cfg["overspeed_warn_kmh"] == 1390
    assert cfg["overspeed_critical_kmh"] == 1540
    assert cfg["overspeed_warn_mach"] == 1.89
    assert cfg["overspeed_critical_mach"] == 2.1
    assert cfg["stall_warn_kmh"] == 182
    assert cfg["stall_critical_kmh"] == 158
    assert cfg["aoa_warn_deg"] == 19
    assert cfg["aoa_critical_deg"] == 22


def test_vehicle_profile_family_entries_cover_unlisted_variants():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cfg, matched, source, family = _merge_profile(
        processor.profiles,
        "su_30mka",
        "air",
        processor._family_rules,
    )

    assert matched is True
    assert source == "family"
    assert family == "Su-30"
    assert cfg["overspeed_warn_kmh"] == 1390
    assert cfg["overspeed_critical_kmh"] == 1540
    assert cfg["overspeed_warn_mach"] == 1.89
    assert cfg["overspeed_critical_mach"] == 2.1
    assert cfg["stall_warn_kmh"] == 182
    assert cfg["stall_critical_kmh"] == 158
    assert cfg["aoa_warn_deg"] == 19
    assert cfg["aoa_critical_deg"] == 22


def test_vehicle_profile_preserves_j15t_sample_calibrated_baseline():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cfg, matched, source, family = _merge_profile(
        processor.profiles,
        "j_15t",
        "air",
        processor._family_rules,
    )

    assert matched is True
    assert source == "exact"
    assert family is None
    assert cfg["overspeed_warn_kmh"] == 1350
    assert cfg["overspeed_critical_kmh"] == 1500
    assert cfg["overspeed_warn_mach"] == 2.16
    assert cfg["overspeed_critical_mach"] == 2.4
    assert cfg["stall_warn_kmh"] == 182
    assert cfg["stall_critical_kmh"] == 158
    assert cfg["aoa_warn_deg"] == 19
    assert cfg["aoa_critical_deg"] == 22


def test_vehicle_profile_splits_legacy_mirage_from_mirage_2000_family():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    legacy, matched, source, family = _merge_profile(
        processor.profiles,
        "mirage_3e",
        "air",
        processor._family_rules,
    )
    assert matched is True
    assert source == "exact"
    assert family is None
    assert legacy["overspeed_critical_kmh"] == 1460
    assert legacy["overspeed_critical_mach"] == 2.1
    assert legacy["stall_warn_kmh"] == 110
    assert legacy["stall_critical_kmh"] == 95
    assert legacy["aoa_critical_deg"] == 29

    modern, matched, source, family = _merge_profile(
        processor.profiles,
        "mirage_2000c_s5",
        "air",
        processor._family_rules,
    )
    assert matched is True
    assert source == "family"
    assert family == "Mirage 2000"
    assert modern["overspeed_critical_kmh"] == 1545
    assert modern["overspeed_critical_mach"] == 2.35
    assert modern["stall_warn_kmh"] == 110
    assert modern["stall_critical_kmh"] == 95
    assert modern["aoa_warn_deg"] == 19
    assert modern["aoa_critical_deg"] == 22


def test_vehicle_profile_covers_official_prefixed_jet_unit_ids():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cases = [
        ("fa_18a", "family", "F/A-18", {"overspeed_critical_kmh": 1477}),
        ("f_16a", "family", "F-16", {"stall_critical_kmh": 158, "aoa_critical_deg": 21}),
        (
            "a6m5_hei",
            "family",
            "A6M Zero",
            {
                "stall_critical_kmh": 142,
                "overspeed_critical_kmh": 777,
                "overspeed_critical_mach": 0.83,
                "aoa_critical_deg": 17,
            },
        ),
        ("fiat_g91_r3", "family", "G.91", {"aoa_warn_deg": 13}),
        ("md_460_saar", "family", "Super Mystere", {"aoa_warn_deg": 13}),
        ("hawk_209_indonesia", "family", "Hawk 209", {"aoa_warn_deg": 15}),
        ("a_4b", "family", "A-4 Skyhawk", {"overspeed_critical_mach": 0.92}),
        ("a_7e", "family", "A-7 Corsair II", {"overspeed_critical_mach": 0.92}),
        ("f1", "exact", None, {"overspeed_critical_kmh": 1500}),
    ]

    for vehicle_type, expected_source, expected_family, expected_values in cases:
        cfg, matched, source, family = _merge_profile(
            processor.profiles,
            vehicle_type,
            "air",
            processor._family_rules,
        )

        assert matched is True, vehicle_type
        assert source == expected_source, vehicle_type
        assert family == expected_family, vehicle_type
        for key, value in expected_values.items():
            assert cfg[key] == value, vehicle_type


def test_vehicle_profile_second_datamine_batch_keeps_modern_jet_candidates():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cases = [
        ("f_15c_msip2", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 25}),
        ("f_15e", "exact", None, {"overspeed_critical_mach": 2.55, "aoa_warn_deg": 21}),
        ("f_14b", "family", "F-14 Tomcat", {"stall_warn_kmh": 184, "stall_critical_kmh": 160}),
        ("mig_29_9_13", "family", "MiG-29", {"stall_critical_kmh": 158, "aoa_critical_deg": 24}),
        ("su_27sm", "family", "Su-27", {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
        ("su_33", "family", "Su-33", {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
        ("j_10a", "exact", None, {"stall_critical_kmh": 95, "aoa_critical_deg": 22}),
        ("j_10s", "family", "J-10", {"stall_critical_kmh": 95, "aoa_critical_deg": 22}),
        ("j_11b", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
        ("rafale_c_f3", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
        ("saab_jas39e", "exact", None, {"stall_critical_kmh": 95, "aoa_critical_deg": 22}),
        ("jas39d", "family", "JAS39 Gripen", {"stall_critical_kmh": 95, "aoa_critical_deg": 22}),
        ("ef_2000_typhoon_aesa", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 21}),
        ("ef_2000_tranche_4", "family", "Eurofighter Typhoon", {"stall_critical_kmh": 158, "aoa_critical_deg": 21}),
    ]

    for vehicle_type, expected_source, expected_family, expected_values in cases:
        cfg, matched, source, family = _merge_profile(
            processor.profiles,
            vehicle_type,
            "air",
            processor._family_rules,
        )

        assert matched is True, vehicle_type
        assert source == expected_source, vehicle_type
        assert family == expected_family, vehicle_type
        for key, value in expected_values.items():
            assert cfg[key] == value, vehicle_type


def test_vehicle_profile_third_datamine_batch_keeps_common_jet_candidates():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cases = [
        ("a-10c", "exact", None, {"overspeed_critical_kmh": 874, "aoa_critical_deg": 22}),
        ("a10a_late", "family", "A-10", {"stall_critical_kmh": 176, "overspeed_critical_mach": 0.8}),
        ("harrier_gr7", "family", "Harrier", {"stall_critical_kmh": 158, "aoa_critical_deg": 25}),
        ("sea_harrier_fa2", "family", "Sea Harrier", {"overspeed_critical_kmh": 1463, "aoa_critical_deg": 23}),
        ("av_8b_plus", "family", "AV-8 Harrier", {"overspeed_critical_mach": 1.1, "aoa_warn_deg": 21}),
        ("su_25sm3", "family", "Su-25", {"stall_critical_kmh": 174, "overspeed_critical_mach": 0.87}),
        ("f_5e", "family", "F-5", {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
        ("f_104s_asa", "family", "F-104 Starfighter", {"overspeed_critical_mach": 2.3, "aoa_critical_deg": 16}),
        ("mig_21_bis_finland", "family", "MiG-21", {"stall_critical_kmh": 94, "aoa_critical_deg": 30}),
        ("mig_23mld", "family", "MiG-23", {"stall_warn_kmh": 184, "overspeed_critical_mach": 2.4}),
        ("tornado_f3_late", "family", "Tornado", {"stall_critical_kmh": 160, "aoa_critical_deg": 20}),
        ("kfir_c7", "exact", None, {"stall_critical_kmh": 95, "aoa_critical_deg": 35}),
        ("kfir_canard", "exact", None, {"overspeed_critical_mach": 2.5, "aoa_critical_deg": 32}),
        ("yak_141", "family", "Yak-141", {"overspeed_critical_kmh": 1450, "aoa_critical_deg": 30}),
    ]

    for vehicle_type, expected_source, expected_family, expected_values in cases:
        cfg, matched, source, family = _merge_profile(
            processor.profiles,
            vehicle_type,
            "air",
            processor._family_rules,
        )

        assert matched is True, vehicle_type
        assert source == expected_source, vehicle_type
        assert family == expected_family, vehicle_type
        for key, value in expected_values.items():
            assert cfg[key] == value, vehicle_type
