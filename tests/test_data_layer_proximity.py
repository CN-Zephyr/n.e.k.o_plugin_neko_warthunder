"""Regression tests for vendored data-layer proximity helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path


DATA_PROCESS = Path(__file__).resolve().parents[1] / "data_layer" / "data process"
if str(DATA_PROCESS) not in sys.path:
    sys.path.insert(0, str(DATA_PROCESS))


def _vehicle(**overrides):
    data = {
        "fuel_kg": None,
        "fuel_full_kg": None,
        "ias_kmh": 500,
        "aoa_deg": 0,
        "altitude_m": 1000,
        "load_factor": 1,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _indicators(**overrides):
    data = {
        "vehicle_type": "su_30mk2v_venezuela",
        "army": "air",
        "is_helicopter": False,
        "throttle": 1.0,
        "gear_state": None,
        "gears": None,
        "water_temperature": None,
        "head_temperature": None,
        "turbine_temperature": None,
        "oil_temperature": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


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
    assert cfg["turbine_temp_warn_c"] == 790
    assert cfg["turbine_temp_critical_c"] == 830
    assert cfg["oil_temp_warn_c"] == 100
    assert cfg["oil_temp_critical_c"] == 110
    assert cfg["turbine_temp_warn_c"] == 790
    assert cfg["turbine_temp_critical_c"] == 830
    assert cfg["oil_temp_warn_c"] == 100
    assert cfg["oil_temp_critical_c"] == 110


def test_vehicle_profile_default_does_not_apply_thermal_thresholds_to_unknowns():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cfg, matched, source, family = _merge_profile(
        processor.profiles,
        "unknown_future_vehicle",
        "air",
        processor._family_rules,
    )

    assert matched is False
    assert source == "default"
    assert family is None
    for key in (
        "water_temp_warn_c",
        "water_temp_critical_c",
        "head_temp_warn_c",
        "head_temp_critical_c",
        "turbine_temp_warn_c",
        "turbine_temp_critical_c",
        "oil_temp_warn_c",
        "oil_temp_critical_c",
    ):
        assert key not in cfg


def test_su30mk2v_turbine_threshold_no_longer_warns_at_live_788_sample():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    below = processor.process(
        _vehicle(ias_kmh=900),
        _indicators(turbine_temperature=788.1),
        timestamp=1000.0,
    )
    assert "engine_overheat" not in below.flags
    assert "engine_overheat_critical" not in below.flags

    warning = processor.process(
        _vehicle(ias_kmh=900),
        _indicators(turbine_temperature=790.0),
        timestamp=1001.0,
    )
    assert warning.flags["engine_overheat"] is True


def test_su30_oil_threshold_uses_datamine_exact_profile():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    warning = processor.process(
        _vehicle(ias_kmh=900),
        _indicators(oil_temperature=101.0),
        timestamp=1000.0,
    )

    assert warning.flags["oil_overheat"] is True


def test_non_su30_modern_jet_does_not_inherit_su30_thermal_thresholds():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cfg, matched, source, family = _merge_profile(
        processor.profiles,
        "mig_29_9_13",
        "air",
        processor._family_rules,
    )

    assert matched is True
    assert source == "exact"
    assert family is None
    assert cfg["turbine_temp_warn_c"] == 920
    assert cfg["turbine_temp_critical_c"] == 970
    assert cfg["oil_temp_warn_c"] == 100


def test_selected_modern_jets_use_datamine_thermal_profiles():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cases = [
        ("f_15e", {"turbine_temp_warn_c": 1040, "turbine_temp_critical_c": 1100, "oil_temp_warn_c": 100, "oil_temp_critical_c": 105}),
        ("rafale_c_f3", {"turbine_temp_warn_c": 900, "turbine_temp_critical_c": 1015, "oil_temp_warn_c": 100, "oil_temp_critical_c": 105}),
        ("saab_jas39e", {"turbine_temp_warn_c": 950, "turbine_temp_critical_c": 990, "oil_temp_warn_c": 96, "oil_temp_critical_c": 102}),
        ("fa_18c_late", {"turbine_temp_warn_c": 830, "turbine_temp_critical_c": 850, "oil_temp_warn_c": 96, "oil_temp_critical_c": 102}),
        ("j_11b", {"turbine_temp_warn_c": 920, "turbine_temp_critical_c": 970, "oil_temp_warn_c": 100, "oil_temp_critical_c": 110}),
    ]

    for vehicle_type, expected_values in cases:
        cfg, matched, source, family = _merge_profile(
            processor.profiles,
            vehicle_type,
            "air",
            processor._family_rules,
        )

        assert matched is True, vehicle_type
        assert source == "exact", vehicle_type
        assert family is None, vehicle_type
        for key, value in expected_values.items():
            assert cfg[key] == value, vehicle_type


def test_prop_thermal_thresholds_remain_available_from_class_and_exact_entry():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cfg, matched, source, family = _merge_profile(
        processor.profiles,
        "ki_61_1a_otsu_china",
        "air",
        processor._family_rules,
    )

    assert matched is True
    assert source == "exact"
    assert family is None
    assert cfg["water_temp_warn_c"] == 114
    assert cfg["water_temp_critical_c"] == 117
    assert cfg["oil_temp_warn_c"] == 110
    assert cfg["oil_temp_critical_c"] == 115


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
    assert source == "exact"
    assert family is None
    assert modern["overspeed_critical_kmh"] == 1545
    assert modern["overspeed_critical_mach"] == 2.35
    assert modern["stall_warn_kmh"] == 109.5
    assert modern["stall_critical_kmh"] == 95.2
    assert modern["aoa_warn_deg"] == 18.7
    assert modern["aoa_critical_deg"] == 22


def test_vehicle_profile_covers_official_prefixed_jet_unit_ids():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cases = [
        ("fa_18a", "exact", None, {"overspeed_critical_kmh": 1477}),
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
        ("fiat_g91_r3", "exact", None, {"aoa_warn_deg": 13}),
        ("md_460_saar", "exact", None, {"aoa_warn_deg": 17}),
        ("hawk_209_indonesia", "exact", None, {"aoa_warn_deg": 13.6}),
        ("a_4b", "exact", None, {"overspeed_critical_mach": 0.92}),
        ("a_7e", "exact", None, {"overspeed_critical_mach": 1.12}),
        ("f1", "exact", None, {"overspeed_critical_kmh": 1365}),
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


def test_vehicle_profile_backfills_existing_fm_alias_entries():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cases = [
        ("f6f-5", {"stall_critical_kmh": 185.8, "overspeed_critical_kmh": 803, "aoa_critical_deg": 15.8}),
        ("a-10c", {"empty_mass_kg": 11590, "turbine_temp_warn_c": 785, "oil_temp_warn_c": 100}),
        ("a-10a_early", {"empty_mass_kg": 11520, "turbine_temp_warn_c": 785, "oil_temp_warn_c": 100}),
    ]

    for vehicle_type, expected_values in cases:
        cfg, matched, source, family = _merge_profile(
            processor.profiles,
            vehicle_type,
            "air",
            processor._family_rules,
        )

        assert matched is True, vehicle_type
        assert source == "exact", vehicle_type
        assert family is None, vehicle_type
        for key, value in expected_values.items():
            assert cfg[key] == value, vehicle_type


def test_vehicle_profile_uses_finer_performance_classes():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    cases = [
        ("f-86f-2", "transonic_jet"),
        ("mig-21_bis", "early_supersonic_jet"),
        ("a-10c", "subsonic_attacker_jet"),
        ("su_24m", "supersonic_attacker_jet"),
        ("f_16c_block_50", "modern_high_alpha_fighter"),
        ("su_30mk2v_venezuela", "heavy_modern_fighter"),
    ]

    for vehicle_type, expected_class in cases:
        assert processor.profiles[vehicle_type]["class"] == expected_class


def test_vehicle_profile_second_datamine_batch_keeps_modern_jet_candidates():
    from wt_processor import TelemetryProcessor, _merge_profile

    processor = TelemetryProcessor()

    cases = [
        ("f_15c_msip2", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 25}),
        ("f_15e", "exact", None, {"overspeed_critical_mach": 2.55, "aoa_warn_deg": 21}),
        ("f_14b", "exact", None, {"stall_warn_kmh": 184, "stall_critical_kmh": 160}),
        ("mig_29_9_13", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 24}),
        ("su_27sm", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
        ("su_33", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
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
        ("harrier_gr7", "exact", None, {"stall_critical_kmh": 158, "aoa_critical_deg": 25}),
        ("sea_harrier_fa2", "exact", None, {"overspeed_critical_kmh": 1463, "aoa_critical_deg": 23}),
        ("av_8b_plus", "exact", None, {"overspeed_critical_mach": 1.1, "aoa_warn_deg": 21.2}),
        ("su_25sm3", "exact", None, {"stall_critical_kmh": 173.8, "overspeed_critical_mach": 0.87}),
        ("f_5e", "family", "F-5", {"stall_critical_kmh": 158, "aoa_critical_deg": 22}),
        ("f_104s_asa", "family", "F-104 Starfighter", {"overspeed_critical_mach": 2.3, "aoa_critical_deg": 16}),
        ("mig_21_bis_finland", "exact", None, {"stall_critical_kmh": 93.8, "aoa_critical_deg": 30}),
        ("mig_23mld", "exact", None, {"stall_warn_kmh": 184, "overspeed_critical_mach": 2.4}),
        ("tornado_f3_late", "exact", None, {"stall_critical_kmh": 160, "aoa_critical_deg": 20}),
        ("kfir_c7", "exact", None, {"stall_critical_kmh": 95, "aoa_critical_deg": 35}),
        ("kfir_canard", "exact", None, {"overspeed_critical_mach": 2.5, "aoa_critical_deg": 32}),
        ("yak_141", "exact", None, {"overspeed_critical_kmh": 1450, "aoa_critical_deg": 30}),
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
