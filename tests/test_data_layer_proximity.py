"""Regression tests for vendored data-layer proximity helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path


DATA_PROCESS = Path(__file__).resolve().parents[1] / "data_layer" / "data process"
if str(DATA_PROCESS) not in sys.path:
    sys.path.insert(0, str(DATA_PROCESS))

from wt_server import TelemetryService  # noqa: E402
from wt_telemetry import (  # noqa: E402
    ConnectionState,
    HudMessage,
    Indicators,
    MapInfo,
    VehicleState,
)


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


def test_failed_chat_drain_does_not_block_hud_incremental_polling():
    class DrainClient:
        def __init__(self) -> None:
            self.hud_calls = 0
            self.chat_calls = 0

        def incremental_cursor_state(self):
            return {}

        def reset_hud_cursors(self):
            return None

        def reset_chat_cursor(self):
            return None

        def get_hud_with_status(self):
            self.hud_calls += 1
            return True, []

        def get_chat_with_status(self):
            self.chat_calls += 1
            return False, []

        def get_mission(self):
            return "running", None

    client = DrainClient()
    service = TelemetryService(client)

    service._poll_events(service._battle_generation)
    assert client.hud_calls == 2
    assert client.chat_calls == 1
    assert service._hud_drain_pending is False
    assert service._chat_drain_pending is True

    service._poll_events(service._battle_generation)
    assert client.hud_calls == 3
    assert client.chat_calls == 2


def test_terminal_mission_recovers_events_after_failed_initial_hud_drain():
    class DrainClient:
        def __init__(self) -> None:
            self.hud_calls = 0
            self.last_evt = 40
            self.last_dmg = 20
            self.in_battle = True

        def get_indicators_with_status(self):
            if self.in_battle:
                return (
                    True,
                    ConnectionState.IN_BATTLE,
                    Indicators(valid=True, army="tank"),
                    MapInfo(valid=True),
                )
            return (
                True,
                ConnectionState.NOT_IN_BATTLE,
                Indicators(valid=False),
                MapInfo(valid=False),
            )

        def get_state_with_status(self):
            return True, VehicleState(valid=True)

        def incremental_cursor_state(self):
            return {
                "last_evt": self.last_evt,
                "last_dmg": self.last_dmg,
                "last_chat": 0,
            }

        def reset_hud_cursors(self):
            self.last_evt = 0
            self.last_dmg = 0

        def restore_hud_cursors(self, state):
            self.last_evt = state["last_evt"]
            self.last_dmg = state["last_dmg"]

        def reset_chat_cursor(self):
            return None

        def get_hud_with_status(self):
            self.hud_calls += 1
            if self.hud_calls == 1:
                assert (self.last_evt, self.last_dmg) == (0, 0)
                return False, []
            if self.hud_calls == 2:
                assert (self.last_evt, self.last_dmg) == (40, 20)
                self.last_evt = 41
                return True, [HudMessage(id=41, kind="event")]
            return True, []

        def get_chat_with_status(self):
            return True, []

        def get_mission(self):
            return "success", {"completed": True}

    class SummaryTracker:
        def __init__(self):
            self.kills = 0

        def reset(self):
            self.kills = 0

        def feed(self, hud):
            self.kills += len(hud)

        def get_summary(self):
            return {"player_name": "pilot", "my": {"kills": self.kills, "deaths": 0}}

    client = DrainClient()
    service = TelemetryService(client)
    service.tracker = SummaryTracker()
    service._mission_status = "running"
    service._mission_objectives = {"completed": False}
    service._combat = {"player_name": "pilot", "my": {"kills": 0, "deaths": 0}}

    service._poll_events(service._battle_generation)
    assert service._hud_drain_pending is True
    assert service._hud_recovery_cursor == {"last_evt": 40, "last_dmg": 20}
    assert service._pending_terminal_status == "success"
    assert service._mission_status == "running"
    assert service._mission_objectives == {"completed": False}
    assert service._combat["my"] == {"kills": 0, "deaths": 0}

    service._poll_events(service._battle_generation)
    assert service._hud_drain_pending is False
    assert service._hud_recovery_cursor is None
    assert service._mission_status == "success"
    assert service._mission_objectives == {"completed": True}
    assert service._combat["my"] == {"kills": 1, "deaths": 0}

    # If the fast group confirms exit before the HUD retry, preserve the real
    # terminal result without claiming an unverifiable K/D until the next battle starts.
    exit_client = DrainClient()
    exit_service = TelemetryService(exit_client)
    exit_service.tracker = SummaryTracker()
    exit_service._state = ConnectionState.IN_BATTLE
    exit_service._battle_id = "ending-battle"
    exit_service._mission_status = "running"
    exit_service._mission_objectives = {"completed": False}
    exit_service._combat = {"player_name": "pilot", "my": {"kills": 0, "deaths": 0}}

    exit_service._poll_events(exit_service._battle_generation)
    exit_client.in_battle = False
    exit_service._poll_fast()
    ended = exit_service.get_snapshot()
    assert ended["state"] == "not_in_battle"
    assert ended["mission_status"] == "success"
    assert ended["mission_objectives"] == {"completed": True}
    assert ended["combat"] is None

    exit_client.in_battle = True
    exit_service._poll_fast()
    next_battle = exit_service.get_snapshot()
    assert next_battle["mission_status"] is None
    assert next_battle["mission_objectives"] is None
    assert next_battle["combat"] is None


def _assert_no_fixed_wing_derivatives(result):
    assert result.fuel_kg is None
    assert result.fuel_fraction is None
    assert result.fuel_burn_rate_kgs is None
    assert result.fuel_remaining_sec is None
    assert result.afterburner_active is False
    assert result.afterburner_elapsed_sec == 0.0
    assert result.afterburner_max_sec is None
    assert result.ias_kmh is None
    assert result.aoa_deg is None
    assert result.altitude_m is None
    assert result.radio_altitude_m is None
    assert result.g_now is None
    assert result.g_max is None
    assert result.g_min is None


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


def test_ground_role_state_flags_follow_confirmed_multistate_contract():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    normal = processor.process(
        _vehicle(),
        _indicators(
            army="tank",
            vehicle_type="germ_pzkpfw_VI_ausf_h1_tiger",
            crew_total=5,
            crew_current=5,
            gunner_state=0,
            driver_state=0,
        ),
        timestamp=100.0,
    )
    assert "gunner_disabled" not in normal.flags
    assert "driver_disabled" not in normal.flags

    unavailable = processor.process(
        _vehicle(),
        _indicators(
            army="tank",
            vehicle_type="germ_pzkpfw_VI_ausf_h1_tiger",
            crew_total=5,
            crew_current=5,
            gunner_state=1,
            driver_state=2,
        ),
        timestamp=101.0,
    )
    assert unavailable.flags["gunner_disabled"] is True
    assert unavailable.flags["driver_disabled"] is True

    unknown = processor.process(
        _vehicle(),
        _indicators(
            army="tank",
            vehicle_type="germ_pzkpfw_VI_ausf_h1_tiger",
            crew_total=5,
            crew_current=1,
            gunner_state=3,
            driver_state=3,
        ),
        timestamp=102.0,
    )
    assert "gunner_disabled" not in unknown.flags
    assert "driver_disabled" not in unknown.flags


def test_ground_lws_warns_only_for_active_illumination_state():
    from wt_processor import TelemetryProcessor

    for index, lws in enumerate((-1, 0, 2, 3)):
        result = TelemetryProcessor().process(
            _vehicle(),
            _indicators(army="tank", vehicle_type="test_tank", lws=lws),
            timestamp=100.0 + index,
        )
        assert "laser_warning" not in result.flags

    active = TelemetryProcessor().process(
        _vehicle(),
        _indicators(army="tank", vehicle_type="test_tank", lws=1),
        timestamp=110.0,
    )
    assert active.flags["laser_warning"] is True


def test_ground_keeps_dto_fields_without_consuming_residual_flight_data():
    from wt_processor import TelemetryProcessor

    result = TelemetryProcessor().process(
        _vehicle(
            fuel_kg=1,
            fuel_full_kg=100,
            ias_kmh=2000,
            aoa_deg=40,
            altitude_m=10,
            load_factor=15,
            mach=3,
        ),
        _indicators(
            army="tank",
            vehicle_type="germ_pzkpfw_VI_ausf_h1_tiger",
            throttle=1.2,
            radio_altitude=5,
            crew_total=5,
            crew_current=5,
            first_stage_ammo=6,
            stabilizer=1,
            gear=3,
            gear_neutral=1,
            gunner_state=0,
            driver_state=0,
            lws=1,
        ),
        timestamp=100.0,
    )

    assert result.vehicle_class == "ground"
    assert result.crew_total == 5
    assert result.crew_current == 5
    assert result.ammo_first_stage == 6
    assert result.gun_stabilizer is True
    assert result.gear_position == 2
    assert result.gunner_state == 0
    assert result.driver_state == 0
    assert result.flags == {"laser_warning": True}
    _assert_no_fixed_wing_derivatives(result)


def test_naval_and_unknown_ignore_residual_flight_data():
    from wt_processor import TelemetryProcessor

    for army, expected_class in (("ship", "naval"), ("unsupported", "unknown")):
        result = TelemetryProcessor().process(
            _vehicle(
                fuel_kg=1,
                fuel_full_kg=100,
                ias_kmh=2000,
                aoa_deg=40,
                altitude_m=10,
                load_factor=15,
                mach=3,
            ),
            _indicators(
                army=army,
                vehicle_type="su_30mk2v_venezuela",
                throttle=1.2,
                radio_altitude=5,
            ),
            timestamp=100.0,
        )

        assert result.vehicle_class == expected_class
        assert result.flags == {}
        assert result.alerts == []
        assert result.level == "info"
        _assert_no_fixed_wing_derivatives(result)


def test_ground_ammo_requires_positive_baseline_and_resets_on_unavailable_data():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    for timestamp, ammo in ((100.0, -1), (101.0, 0), (102.0, 6)):
        result = processor.process(
            _vehicle(),
            _indicators(army="tank", vehicle_type="test_tank", first_stage_ammo=ammo),
            timestamp=timestamp,
        )
        assert "ammo_empty" not in result.flags

    empty = processor.process(
        _vehicle(),
        _indicators(army="tank", vehicle_type="test_tank", first_stage_ammo=0),
        timestamp=103.0,
    )
    assert empty.flags["ammo_empty"] is True

    processor.process(
        _vehicle(),
        _indicators(army="tank", vehicle_type="test_tank", first_stage_ammo=-1),
        timestamp=104.0,
    )
    after_unavailable = processor.process(
        _vehicle(),
        _indicators(army="tank", vehicle_type="test_tank", first_stage_ammo=0),
        timestamp=105.0,
    )
    assert "ammo_empty" not in after_unavailable.flags


def test_same_match_respawn_resets_processor_and_suppresses_first_frame():
    import time

    from wt_server import TelemetryService
    from wt_telemetry import ConnectionState, Indicators, MapInfo, VehicleState

    current_indicators = Indicators(
        valid=True,
        army="tank",
        vehicle_type="test_tank",
        speed=6.0,
        crew_total=4,
        crew_current=4,
        first_stage_ammo=0,
        gunner_state=0,
        driver_state=0,
        lws=-1,
    )

    class FakeClient:
        def get_indicators_with_status(self):
            return True, ConnectionState.IN_BATTLE, current_indicators, MapInfo(valid=True)

        def get_state_with_status(self):
            return True, VehicleState(valid=True, ias_kmh=0, load_factor=1)

    service = TelemetryService(FakeClient())
    service._state = ConnectionState.IN_BATTLE
    service._battle_entry_ts = time.time() - 60
    service._battle_id = "battle-1"
    service._life_index = 1
    service._life_entry_ts = time.time() - 60
    service._dead = True
    service._dead_inert_seen = True
    service._last_deaths = 1
    service._combat = {"my": {"deaths": 1}}

    service.processor.process(
        VehicleState(valid=True, load_factor=1),
        Indicators(
            valid=True,
            army="tank",
            vehicle_type="test_tank",
            first_stage_ammo=6,
        ),
        timestamp=time.time() - 1,
    )
    assert service.processor._ammo_baseline_seen is True

    service._poll_fast()

    assert service._dead is False
    assert service._processed is None
    assert service.processor._ammo_baseline_seen is False
    assert service._life_entry_ts is not None
    assert time.time() - service._life_entry_ts < 1
    snapshot = service.get_snapshot()
    assert snapshot["battle_id"] == "battle-1"
    assert snapshot["life_index"] == 2
    assert snapshot["confirmed_respawns"] == 1


def test_battle_identity_survives_respawn_and_changes_after_confirmed_exit():
    from neko_warthunder.adapters.telemetry_client import parse_telemetry
    from wt_server import TelemetryService
    from wt_telemetry import ConnectionState, Indicators, MapInfo, VehicleState

    class BoundaryClient:
        in_battle = True

        def get_indicators_with_status(self):
            if self.in_battle:
                return (
                    True,
                    ConnectionState.IN_BATTLE,
                    Indicators(valid=True, army="tank", speed=0.0),
                    MapInfo(valid=True),
                )
            return (
                True,
                ConnectionState.NOT_IN_BATTLE,
                Indicators(valid=False),
                MapInfo(valid=False),
            )

        def get_state_with_status(self):
            return True, VehicleState(valid=True)

    client = BoundaryClient()
    service = TelemetryService(client)
    service._poll_fast()
    first = service.get_snapshot()
    battle_id = first["battle_id"]
    assert isinstance(battle_id, str) and battle_id
    assert first["life_index"] == 1
    assert first["confirmed_respawns"] == 0

    service._combat = {"my": {"deaths": 1}}
    with service._lock:
        assert not service._update_dead_state_locked(
            Indicators(valid=True, army="tank", speed=0.0, crew_current=0, crew_total=4),
            {"ias_kmh": 0.0},
            10.0,
        )
        assert service._update_dead_state_locked(
            Indicators(valid=True, army="tank", speed=8.0, crew_current=4, crew_total=4),
            {"ias_kmh": 0.0},
            11.0,
        )

    respawned = service.get_snapshot()
    assert respawned["battle_id"] == battle_id
    assert respawned["life_index"] == 2
    assert respawned["confirmed_respawns"] == 1

    parsed = parse_telemetry(respawned)
    assert parsed.battle_id == battle_id
    assert parsed.life_index == 2
    assert parsed.confirmed_respawns == 1

    client.in_battle = False
    service._poll_fast()
    assert service.get_snapshot()["battle_id"] is None

    client.in_battle = True
    service._poll_fast()
    next_battle = service.get_snapshot()
    assert next_battle["battle_id"] != battle_id
    assert next_battle["life_index"] == 1


def test_death_entry_cannot_respawn_from_stale_full_crew_in_the_same_frame():
    from wt_server import TelemetryService
    from wt_telemetry import Indicators

    class DummyClient:
        pass

    service = TelemetryService(DummyClient())
    service._battle_id = "battle-1"
    service._life_index = 1
    service._combat = {"my": {"deaths": 1}}

    with service._lock:
        respawned = service._update_dead_state_locked(
            Indicators(
                valid=True,
                army="tank",
                speed=0.0,
                crew_current=4,
                crew_total=4,
            ),
            {"ias_kmh": 0.0},
            100.0,
        )

    assert respawned is False
    assert service._dead is True
    assert service._life_index == 1


def test_ground_respawn_requires_a_prior_depleted_crew_frame_before_full_crew_recovery():
    from wt_server import TelemetryService
    from wt_telemetry import Indicators

    class DummyClient:
        pass

    service = TelemetryService(DummyClient())
    service._battle_id = "battle-1"
    service._life_index = 1
    service._combat = {"my": {"deaths": 1}}

    with service._lock:
        assert service._update_dead_state_locked(
            Indicators(valid=True, army="tank", speed=0.0, crew_current=1, crew_total=4),
            {"ias_kmh": 0.0},
            100.0,
        ) is False
        assert service._update_dead_state_locked(
            Indicators(valid=True, army="tank", speed=0.0, crew_current=4, crew_total=4),
            {"ias_kmh": 0.0},
            101.0,
        ) is True

    assert service._dead is False
    assert service._life_index == 2


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


def test_fixed_wing_low_altitude_prefers_radio_altitude_when_available():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    result = processor.process(
        _vehicle(altitude_m=1200, ias_kmh=500),
        _indicators(radio_altitude=50.0, gear_state="up"),
        timestamp=100.0,
    )

    assert result.radio_altitude_m == 50.0
    assert result.altitude_m == 1200
    assert result.flags["altitude_critical"] is True


def test_fixed_wing_low_altitude_falls_back_to_msl_without_radio_altitude():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    high_msl = processor.process(
        _vehicle(altitude_m=1200, ias_kmh=500),
        _indicators(radio_altitude=None, gear_state="up"),
        timestamp=100.0,
    )
    low_msl = processor.process(
        _vehicle(altitude_m=80, ias_kmh=500),
        _indicators(radio_altitude=None, gear_state="up"),
        timestamp=101.0,
    )

    assert high_msl.radio_altitude_m is None
    assert "altitude_low" not in high_msl.flags
    assert "altitude_critical" not in high_msl.flags
    assert low_msl.flags["altitude_critical"] is True


def test_ka50_indicators_are_classified_as_helicopter_despite_gears_placeholder():
    from wt_processor import TelemetryProcessor
    from wt_telemetry import WarThunderClient

    raw = {
        "valid": True,
        "army": "air",
        "type": "ka_50",
        "speed": 63.347168,
        "vario": -8.188931,
        "gears": 0.5,
        "prop_rpm": 266.340637,
        "radio_altitude": 470.016876,
        "rpm": 14538.244141,
        "water_temperature_hour": 825.791626,
        "water_temperature_min": 825.791626,
    }
    indicators = WarThunderClient()._parse_indicators(raw)

    assert indicators.is_helicopter is True

    result = TelemetryProcessor().process(
        _vehicle(ias_kmh=228, altitude_m=1995, load_factor=1.68),
        indicators,
        timestamp=100.0,
    )

    assert result.vehicle_class == "heli"
    assert result.rotor_rpm == 266.340637
    assert result.radio_altitude_m == 470.016876
    assert "stall_warning" not in result.flags
    assert "altitude_low" not in result.flags


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


def test_su30_over_g_prefers_instructor_limit_over_datamine_structure_candidate():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    normal_turn = processor.process(
        _vehicle(load_factor=6.5, fuel_kg=3769, fuel_full_kg=9400, ias_kmh=900),
        _indicators(throttle=0.8),
        timestamp=1000.0,
    )
    warning = processor.process(
        _vehicle(load_factor=10.5, fuel_kg=3769, fuel_full_kg=9400, ias_kmh=900),
        _indicators(throttle=0.8),
        timestamp=1001.0,
    )
    critical = processor.process(
        _vehicle(load_factor=13.1, fuel_kg=3769, fuel_full_kg=9400, ias_kmh=900),
        _indicators(throttle=0.8),
        timestamp=1002.0,
    )

    assert "over_g" not in normal_turn.flags
    assert "over_g_critical" not in normal_turn.flags
    assert warning.flags["over_g"] is True
    assert "over_g_critical" not in warning.flags
    assert critical.flags["over_g_critical"] is True


def test_fuel_time_estimate_does_not_trigger_low_fuel_when_fraction_is_healthy():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    first = processor.process(
        _vehicle(fuel_kg=4000, fuel_full_kg=9400, ias_kmh=1280),
        _indicators(throttle=1.1),
        timestamp=1000.0,
    )
    early = processor.process(
        _vehicle(fuel_kg=3769, fuel_full_kg=9400, ias_kmh=1280),
        _indicators(throttle=1.1),
        timestamp=1015.87,
    )
    stable = processor.process(
        _vehicle(fuel_kg=2980, fuel_full_kg=9400, ias_kmh=1280),
        _indicators(throttle=1.1),
        timestamp=1070.0,
    )

    assert first.fuel_remaining_sec is None
    assert early.fuel_remaining_sec is not None
    assert early.fuel_remaining_sec <= 300
    assert "fuel_low" not in early.flags
    assert stable.fuel_remaining_sec is not None
    assert stable.fuel_remaining_sec <= 300
    assert "fuel_low" not in stable.flags


def test_low_fuel_follows_fraction_even_before_time_estimate_exists():
    from wt_processor import TelemetryProcessor

    processor = TelemetryProcessor()

    result = processor.process(
        _vehicle(fuel_kg=1300, fuel_full_kg=9400, ias_kmh=900),
        _indicators(throttle=0.8),
        timestamp=1000.0,
    )

    assert result.fuel_fraction == 0.1383
    assert result.fuel_remaining_sec is None
    assert result.flags["fuel_low"] is True
    assert "fuel_critical" not in result.flags


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
