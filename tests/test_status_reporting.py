"""Status reporting should stay lightweight under the live polling loop."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
import tempfile
import threading
import time
import types

from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.contracts import BattleEvent, BattleState, WtConfig
from neko_warthunder.core.safety_guard import SafetyGuard
from neko_warthunder.core.scenario import ScenarioResolver


def _runtime_plugin_class():
    if "plugin.sdk.plugin" not in sys.modules:
        plugin_mod = types.ModuleType("plugin")
        sdk_mod = types.ModuleType("plugin.sdk")
        plugin_sdk_mod = types.ModuleType("plugin.sdk.plugin")

        class NekoPluginBase:
            def __init__(self, ctx):
                self.ctx = ctx

        def identity_decorator(*_args, **_kwargs):
            def wrap(obj):
                return obj

            return wrap

        plugin_sdk_mod.NekoPluginBase = NekoPluginBase
        plugin_sdk_mod.neko_plugin = lambda cls: cls
        plugin_sdk_mod.plugin_entry = identity_decorator
        plugin_sdk_mod.lifecycle = identity_decorator
        plugin_sdk_mod.message = identity_decorator
        plugin_sdk_mod.ui = types.SimpleNamespace(
            context=identity_decorator,
            action=identity_decorator,
        )
        plugin_sdk_mod.Ok = lambda value=None: value
        plugin_sdk_mod.Err = lambda value=None: value
        plugin_sdk_mod.SdkError = Exception

        sys.modules["plugin"] = plugin_mod
        sys.modules["plugin.sdk"] = sdk_mod
        sys.modules["plugin.sdk.plugin"] = plugin_sdk_mod

    module_name = "neko_warthunder.__runtime_under_test__"
    if module_name in sys.modules:
        module = sys.modules[module_name]
        if hasattr(module, "NekoWarthunderPlugin"):
            return module.NekoWarthunderPlugin
        del sys.modules[module_name]

    plugin_dir = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(module_name, plugin_dir / "__init__.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.NekoWarthunderPlugin


def _plugin_for_report_tests():
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    plugin.cfg = WtConfig()
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.timeline = RuntimeTimeline()
    plugin.data_layer_manager = types.SimpleNamespace(
        configure=lambda *_args, **_kwargs: None,
        observe_health=lambda *_args, **_kwargs: None,
        snapshot=lambda: {"mode": "external"},
    )
    plugin.state = BattleState(connected=True, conn_state="in_battle", in_battle=True, scenario="IN_FLIGHT")
    plugin._state_lock = threading.Lock()
    plugin._status_report_min_interval_seconds = 10.0
    plugin._last_status_report_at = 0.0
    plugin._last_status_report_snapshot = None
    plugin.reported_statuses = []

    def report_status(payload):
        plugin.reported_statuses.append(payload)

    plugin.report_status = report_status
    return plugin


def _plugin_for_action_tests():
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    plugin.cfg = WtConfig()
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.timeline = RuntimeTimeline()
    plugin.data_layer_manager = types.SimpleNamespace(
        configure=lambda *_args, **_kwargs: None,
        observe_health=lambda *_args, **_kwargs: None,
        snapshot=lambda: {"mode": "external"},
    )
    plugin.state = BattleState()
    plugin._state_lock = threading.Lock()
    # 默认落到临时目录：运行时 fallback 会写插件根，测试忘记覆盖 _runtime_state_path
    # 就会把 .runtime_state.json（含玩家昵称）泄漏进仓库——历史上确实发生过。
    # 需要断言落盘内容的测试仍可覆盖成自己的 tmp_path。
    plugin._runtime_state_path = pathlib.Path(tempfile.mkdtemp(prefix="wt-runtime-state-")) / ".runtime_state.json"
    plugin.pushed_messages = []
    plugin.config_updates = []

    class FakeConfig:
        async def update(self, payload):
            plugin.config_updates.append(payload)

    plugin.config = FakeConfig()
    plugin.logger = types.SimpleNamespace(
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
    )

    def push_message(**kwargs):
        plugin.pushed_messages.append(kwargs)

    plugin.push_message = push_message
    return plugin


def test_status_report_is_deduped_between_unchanged_poll_ticks():
    plugin = _plugin_for_report_tests()

    plugin._report(now=100.0)
    plugin._report(now=100.4)

    assert len(plugin.reported_statuses) == 1


def test_status_report_emits_immediately_when_snapshot_changes():
    plugin = _plugin_for_report_tests()

    plugin._report(now=100.0)
    plugin.state = BattleState(connected=True, conn_state="in_battle", in_battle=True, scenario="CRITICAL_RISK")
    plugin._report(now=100.4)

    assert len(plugin.reported_statuses) == 2
    assert plugin.reported_statuses[-1]["scenario"] == "CRITICAL_RISK"


def test_tick_refreshes_data_layer_health_from_telemetry_connection():
    plugin = _plugin_for_report_tests()
    observed = []
    plugin.client = types.SimpleNamespace(poll=lambda: BattleState(connected=False, conn_state="offline"))
    plugin.data_layer_manager = types.SimpleNamespace(observe_health=observed.append)
    plugin._sync_game_context = lambda *_args: None
    plugin._evaluate = lambda *_args: None
    plugin._report = lambda *_args: None

    plugin._tick()

    assert observed == [False]


def _plugin_for_game_context_tests():
    plugin = _plugin_for_report_tests()
    plugin._instructions_injected = False
    plugin.pushed_contexts = []

    class FakeDispatcher:
        def push_context(self, text):
            plugin.pushed_contexts.append(text)
            return True

    plugin.dispatcher = FakeDispatcher()
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    return plugin


def test_urgent_output_migration_marker_write_failure_does_not_abort_startup():
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    warnings: list[str] = []
    plugin.logger = types.SimpleNamespace(warning=warnings.append)
    plugin._save_runtime_state = lambda _patch: (_ for _ in ()).throw(OSError("read only"))

    asyncio.run(
        plugin._migrate_urgent_output_tts_default(
            {},
            {},
            config_loaded=True,
        )
    )

    assert warnings == ["urgent output TTS migration flag persist failed: OSError"]


def test_startup_refuses_to_overlap_a_previous_poll_thread():
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    calls: list[str] = []

    async def reload_config():
        calls.append("reload")

    plugin._reload_config = reload_config
    plugin._thread = types.SimpleNamespace(is_alive=lambda: True)
    plugin.logger = types.SimpleNamespace(warning=lambda message: calls.append(message))
    plugin.data_layer_manager = types.SimpleNamespace(
        start_if_needed=lambda: calls.append("data_layer_start")
    )

    result = asyncio.run(plugin.startup())

    assert isinstance(result, Exception)
    assert calls[0] == "reload"
    assert "data_layer_start" not in calls
    assert any("previous poll thread" in item for item in calls)


def test_user_context_refresh_cannot_move_chat_activity_backwards():
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    record = types.SimpleNamespace(
        timestamp=50.0,
        raw={
            "type": "user_message",
            "lanlan": "target",
            "is_voice": True,
            "_ts": 50.0,
        },
    )
    plugin.ctx = types.SimpleNamespace(
        bus=types.SimpleNamespace(
            memory=types.SimpleNamespace(get_sync=lambda *_args, **_kwargs: [record])
        )
    )
    plugin.timeline = None
    plugin._last_user_context_seen_at = 40.0
    plugin._last_user_chat_at = 100.0
    plugin._last_user_chat_mode = "text"

    assert plugin._refresh_user_chat_activity(target_lanlan="target") == "text"
    assert plugin._last_user_context_seen_at == 40.0
    assert plugin._last_user_chat_at == 100.0
    assert plugin._last_user_chat_mode == "text"


def test_game_context_is_not_active_for_offline_state():
    plugin = _plugin_for_game_context_tests()

    plugin._sync_game_context(BattleState(), BattleState(connected=True, conn_state="offline"))

    assert plugin.pushed_contexts == []
    assert plugin._instructions_injected is False


def test_game_context_enters_when_telemetry_goes_online_once():
    from neko_warthunder.core.instructions import WT_CONTEXT_INSTRUCTIONS

    plugin = _plugin_for_game_context_tests()

    plugin._sync_game_context(BattleState(), BattleState(connected=True, conn_state="not_in_battle"))
    plugin._sync_game_context(
        BattleState(connected=True, conn_state="not_in_battle"),
        BattleState(connected=True, conn_state="in_battle", in_battle=True),
    )

    assert plugin.pushed_contexts == [WT_CONTEXT_INSTRUCTIONS]
    assert plugin._instructions_injected is True
    stages = [item["stage"] for item in plugin.timeline.snapshot()["recent_timeline"]]
    assert "game_context_entered" in stages

    failed_plugin = _plugin_for_game_context_tests()
    failed_plugin.dispatcher.push_context = lambda _text: False
    failed_plugin._sync_game_context(BattleState(), BattleState(connected=True, conn_state="not_in_battle"))
    assert failed_plugin._instructions_injected is False


def test_game_context_exits_when_telemetry_goes_offline_once():
    from neko_warthunder.core.instructions import WT_CONTEXT_INSTRUCTIONS, WT_RESTORE_INSTRUCTIONS

    plugin = _plugin_for_game_context_tests()

    plugin._sync_game_context(BattleState(), BattleState(connected=True, conn_state="in_battle", in_battle=True))
    plugin._sync_game_context(
        BattleState(connected=True, conn_state="in_battle", in_battle=True),
        BattleState(connected=False, conn_state="offline", in_battle=False),
    )
    plugin._sync_game_context(BattleState(connected=False, conn_state="offline"), BattleState())

    assert plugin.pushed_contexts == [WT_CONTEXT_INSTRUCTIONS, WT_RESTORE_INSTRUCTIONS]
    assert plugin._instructions_injected is False
    stages = [item["stage"] for item in plugin.timeline.snapshot()["recent_timeline"]]
    assert "game_context_exited" in stages


def test_replay_tick_records_suppressed_decision_without_output():
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    plugin.cfg = WtConfig()
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    plugin.dispatcher = types.SimpleNamespace(push_event=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError))
    plugin.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)

    prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True)
    cur = BattleState(
        connected=True,
        conn_state="in_battle",
        in_battle=True,
        vehicle_valid=True,
        replay=True,
        flags={
            "stall_critical": True,
            "altitude_critical": True,
            "overspeed_critical": True,
            "fuel_critical": True,
        },
        combat={
            "feed": [
                {"id": 100, "is_my_kill": True, "victim": "ReplayVictim"},
                {"id": 101, "is_my_death": True, "killer": "ReplayKiller"},
            ]
        },
        hud_notices=[{"id": 7, "code": "engine_overheat", "severity": "critical", "text": "replay overheat"}],
    )

    plugin._evaluate(prev, cur)

    observe = plugin.timeline.snapshot()
    assert observe["last_decision"]["stage"] == "detector_suppressed"
    assert observe["last_decision"]["outcome"] == "suppressed"
    assert observe["last_decision"]["reason"] == "replay"
    assert observe["last_output_status"] is None
    assert observe["last_event"] is None


def _plugin_for_runtime_evaluate_tests(*, clock_values: list[float], dry_run: bool = False):
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    plugin.cfg = WtConfig(dry_run=dry_run)
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=20)
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    plugin.pushed_events = []
    plugin.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)

    def push_event(event, **_kwargs):
        plugin.pushed_events.append(event)
        return f"pushed(event={event.event_id}/{event.edge})"

    plugin.dispatcher = types.SimpleNamespace(push_event=push_event)

    module = sys.modules[Plugin.__module__]
    clock_iter = iter(clock_values)
    original_time = module.time.time
    module.time.time = lambda: next(clock_iter)

    return plugin, module, original_time


def test_new_battle_id_resets_cross_battle_runtime_state_once():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 101.0])
    reset_counts = {"engine": 0, "resolver": 0, "arbiter": 0}

    def wrap_reset(name, original):
        def counted_reset():
            reset_counts[name] += 1
            return original()

        return counted_reset

    plugin.engine.reset = wrap_reset("engine", plugin.engine.reset)
    plugin.resolver.reset = wrap_reset("resolver", plugin.resolver.reset)
    plugin.arbiter.reset = wrap_reset("arbiter", plugin.arbiter.reset)

    try:
        same_prev = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="ground",
            battle_id="battle-1",
            life_index=1,
        )
        same_cur = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="ground",
            battle_id="battle-1",
            life_index=2,
        )
        plugin._evaluate(same_prev, same_cur)
        assert reset_counts == {"engine": 0, "resolver": 0, "arbiter": 0}

        next_battle = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="ground",
            battle_id="battle-2",
            life_index=1,
        )
        plugin._evaluate(same_cur, next_battle)

        assert reset_counts == {"engine": 1, "resolver": 1, "arbiter": 1}
        boundary_records = [
            item
            for item in plugin.timeline.snapshot()["recent_timeline"]
            if item.get("stage") == "battle_boundary"
        ]
        assert len(boundary_records) == 1
        assert boundary_records[0]["reason"] == "new_battle_id"
        assert boundary_records[0]["outcome"] == "reset"
    finally:
        module.time.time = original_time


def test_takeoff_low_alt_grace_suppresses_low_altitude_event_only():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 110.0, 112.0])
    try:
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False, domain="air")
        spawn = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="air")
        plugin._evaluate(prev, spawn)
        plugin.pushed_events.clear()

        low_alt_1 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            flags={"altitude_critical": True},
            altitude_m=38.0,
            climb_ms=-3.0,
        )
        low_alt_2 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            flags={"altitude_critical": True},
            altitude_m=35.0,
            climb_ms=-4.0,
        )
        plugin._evaluate(spawn, low_alt_1)
        plugin._evaluate(low_alt_1, low_alt_2)

        assert plugin.pushed_events == []
        decision = plugin.timeline.snapshot()["last_decision"]
        assert decision["stage"] == "detector_suppressed"
        assert decision["reason"] == "takeoff_low_alt_grace"
    finally:
        module.time.time = original_time


def test_takeoff_low_alt_grace_does_not_suppress_stall_critical():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 110.0, 112.0])
    try:
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False, domain="air")
        spawn = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="air")
        plugin._evaluate(prev, spawn)
        plugin.pushed_events.clear()

        stall_1 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            flags={"stall_critical": True},
            aoa_deg=22.0,
            ias_kmh=160.0,
        )
        stall_2 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            flags={"stall_critical": True},
            aoa_deg=23.0,
            ias_kmh=150.0,
        )
        plugin._evaluate(spawn, stall_1)
        plugin._evaluate(stall_1, stall_2)

        assert [event.event_id for event in plugin.pushed_events] == ["stall_risk"]
    finally:
        module.time.time = original_time


def test_takeoff_radio_altitude_grace_suppresses_overspeed_until_airborne():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 150.0, 152.0])
    try:
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False, domain="air")
        spawn = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=0.0,
        )
        plugin._evaluate(prev, spawn)
        plugin.pushed_events.clear()

        fast_roll_1 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=6.0,
            flags={"overspeed_critical": True},
            ias_kmh=1200.0,
        )
        fast_roll_2 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=7.0,
            flags={"overspeed_critical": True},
            ias_kmh=1210.0,
        )
        plugin._evaluate(spawn, fast_roll_1)
        plugin._evaluate(fast_roll_1, fast_roll_2)

        assert plugin.pushed_events == []
        decision = plugin.timeline.snapshot()["last_decision"]
        assert decision["stage"] == "detector_suppressed"
        assert decision["reason"] == "takeoff_radio_altitude_grace"
        assert decision["event_id"] == "overspeed"
    finally:
        module.time.time = original_time


def test_takeoff_runway_grace_suppresses_overspeed_without_radio_altitude_when_gear_down():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 110.0, 112.0])
    try:
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False, domain="air")
        spawn = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="air")
        plugin._evaluate(prev, spawn)
        plugin.pushed_events.clear()

        fast_roll_1 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=None,
            flags={"overspeed_critical": True},
            ias_kmh=1200.0,
            raw={"indicators": {"gear_state": "down"}},
        )
        fast_roll_2 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=None,
            flags={"overspeed_critical": True},
            ias_kmh=1210.0,
            raw={"indicators": {"gear_state": "down"}},
        )
        plugin._evaluate(spawn, fast_roll_1)
        plugin._evaluate(fast_roll_1, fast_roll_2)

        assert plugin.pushed_events == []
        decision = plugin.timeline.snapshot()["last_decision"]
        assert decision["stage"] == "detector_suppressed"
        assert decision["reason"] == "takeoff_runway_grace"
        assert decision["event_id"] == "overspeed"
    finally:
        module.time.time = original_time


def test_takeoff_runway_grace_does_not_suppress_airspawn_overspeed_without_gear_down():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 110.0, 112.0])
    try:
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False, domain="air")
        spawn = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="air")
        plugin._evaluate(prev, spawn)
        plugin.pushed_events.clear()

        fast_air_1 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=None,
            flags={"overspeed_critical": True},
            ias_kmh=1200.0,
            raw={"indicators": {"gear_state": "up"}},
        )
        fast_air_2 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=None,
            flags={"overspeed_critical": True},
            ias_kmh=1210.0,
            raw={"indicators": {"gear_state": "up"}},
        )
        plugin._evaluate(spawn, fast_air_1)
        plugin._evaluate(fast_air_1, fast_air_2)

        assert [event.event_id for event in plugin.pushed_events] == ["overspeed"]
    finally:
        module.time.time = original_time


def test_takeoff_radio_altitude_grace_releases_after_exit_height():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 150.0, 152.0])
    try:
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False, domain="air")
        spawn = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=0.0,
        )
        plugin._evaluate(prev, spawn)
        plugin.pushed_events.clear()

        airborne_1 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=45.0,
            flags={"overspeed_critical": True},
            ias_kmh=1200.0,
        )
        airborne_2 = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            domain="air",
            radio_altitude_m=48.0,
            flags={"overspeed_critical": True},
            ias_kmh=1210.0,
        )
        plugin._evaluate(spawn, airborne_1)
        plugin._evaluate(airborne_1, airborne_2)

        assert [event.event_id for event in plugin.pushed_events] == ["overspeed"]
    finally:
        module.time.time = original_time


def test_status_includes_data_layer_process_snapshot():
    plugin = _plugin_for_report_tests()
    plugin.data_layer_manager = types.SimpleNamespace(
        snapshot=lambda: {
            "mode": "managed",
            "pid": 4321,
            "started_by_plugin": True,
            "health": True,
        }
    )

    result = plugin.status()

    assert result["data_layer"] == {
        "mode": "managed",
        "pid": 4321,
        "started_by_plugin": True,
        "health": True,
    }


def test_dashboard_context_includes_data_layer_process_snapshot():
    plugin = _plugin_for_report_tests()
    plugin.data_layer_manager = types.SimpleNamespace(snapshot=lambda: {"mode": "managed", "pid": 4321})
    plugin.state.domain = "air"
    plugin.state.radio_altitude_m = 8.0
    plugin.state.altitude_m = 1067.0
    plugin.state.ias_kmh = 120.0
    plugin.state.flags = {"altitude_low": True}
    plugin.state.proximity_events = [
        {
            "id": 3,
            "kind": "enter",
            "type": "fighter",
            "category": "enemy_air",
            "is_air": True,
            "distance_m": 1400,
            "compass": "N",
            "clock": 12,
            "text": "raw proximity text",
        }
    ]
    plugin.state.situation = {
        "has_player": True,
        "enemy_count": 2,
        "ally_count": 1,
        "air_threat_count": 1,
        "ground_targets": [
            {
                "kind": "bombing_point",
                "label": "raw objective label",
                "grid": "B4",
                "distance_m": 2400,
                "bearing_deg": 90,
                "relative_deg": -20,
            }
        ],
    }
    plugin._takeoff_radio_altitude_grace_active = True

    result = asyncio.run(plugin.dashboard_context())

    assert result["data_layer"] == {"mode": "managed", "pid": 4321}
    assert result["telemetry"]["radio_altitude_m"] == 8.0
    assert result["telemetry"]["altitude_m"] == 1067.0
    assert result["telemetry"]["flags"] == {"altitude_low": True}
    assert result["takeoff_protection"]["active"] is True
    assert result["takeoff_protection"]["enter_m"] == 10.0
    assert result["takeoff_protection"]["exit_m"] == 40.0
    assert result["takeoff_protection"]["suppresses"] == ["low_alt_danger", "overspeed"]
    assert result["output_policy"]["v2_live_verified_real_output_enabled"] is False
    assert result["output_policy"]["v2_live_evidence_gated_events"] == [
        "enemy_on_six",
        "tailing_risk",
        "ground_target_nearby",
    ]
    assert result["output_policy"]["dialogue_intrusion_mode"] == "critical_only"
    assert result["output_policy"]["critical_bypass_quiet_window"] is True
    assert result["awareness"]["proximity_event_count"] == 1
    assert result["awareness"]["latest_proximity"]["target_type"] == "fighter"
    assert result["awareness"]["latest_proximity"]["distance_m"] == 1400
    assert result["awareness"]["situation"] == {
        "has_player": True,
        "enemy_count": 2,
        "ally_count": 1,
        "air_threat_count": 1,
        "ground_target_count": 1,
    }
    assert result["awareness"]["nearest_ground_target"] == {
        "kind": "bombing_point",
        "grid": "B4",
        "distance_m": 2400,
        "bearing_deg": 90,
        "relative_deg": -20,
    }
    assert "raw proximity text" not in repr(result["awareness"])
    assert "raw objective label" not in repr(result["awareness"])


def test_manual_pause_suppresses_detected_event_before_dispatcher():
    Plugin = _runtime_plugin_class()
    plugin = object.__new__(Plugin)
    plugin.cfg = WtConfig(dry_run=False)
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.safety.pause()
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    plugin.dispatcher = types.SimpleNamespace(push_event=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError))
    plugin.logger = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)

    prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True, domain="air")
    cur = BattleState(
        connected=True,
        conn_state="in_battle",
        in_battle=True,
        vehicle_valid=True,
        domain="air",
        flags={"fuel_low": True},
        fuel_fraction=0.05,
    )

    plugin._evaluate(prev, cur)

    observe = plugin.timeline.snapshot()
    assert observe["last_decision"]["outcome"] == "suppressed"
    assert observe["last_decision"]["reason"] == "paused"
    assert observe["last_output_status"] is None


def test_powertrain_failure_notice_is_observed_as_deferred_without_speech():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 101.0])
    try:
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True)
        cur = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            hud_notices=[{"id": 42, "code": "powertrain_failure", "severity": "critical", "text": "raw engine failure"}],
        )

        plugin._evaluate(prev, cur)
        plugin._evaluate(cur, cur)

        observe = plugin.timeline.snapshot()
        assert plugin.pushed_events == []
        assert observe["last_decision"]["stage"] == "detector_suppressed"
        assert observe["last_decision"]["outcome"] == "suppressed"
        assert observe["last_decision"]["reason"] == "deferred_hud_notice"
        assert observe["last_decision"]["event_id"] == "powertrain_failure"
        records = [
            item
            for item in observe["recent_timeline"]
            if item.get("event_id") == "powertrain_failure" and item.get("reason") == "deferred_hud_notice"
        ]
        assert len(records) == 1
        assert records[0]["stage"] == "detector_suppressed"
        assert records[0]["outcome"] == "suppressed"
        assert records[0]["level"] == "critical"
        assert records[0]["message"] == "hud_notice/powertrain_failure/deferred"
        assert "raw engine failure" not in repr(observe)
    finally:
        module.time.time = original_time


def test_free_text_sources_are_observed_as_blocked_and_dry_run_candidate_without_speech():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(clock_values=[100.0, 101.0], dry_run=True)
    try:
        plugin.resolver._prev_alive = True
        raw = {
            "awards": {"feed": [{"id": 1, "text": "raw award text"}]},
            "combat": {"feed": [{"id": 10, "is_my_kill": False, "text": "raw combat feed text"}]},
            "hud_notices": {"feed": [{"id": 20, "code": "generic_notice", "text": "raw hud notice text"}]},
            "hudmsg": "raw hudmsg text",
            "hud_events": [{"id": 30, "text": "raw hud event text"}],
        }
        prev = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True)
        cur = BattleState(
            connected=True,
            conn_state="in_battle",
            in_battle=True,
            vehicle_valid=True,
            combat=raw["combat"],
            hud_notices=raw["hud_notices"]["feed"],
            hud_events=raw["hud_events"],
            raw=raw,
        )

        plugin._evaluate(prev, cur)
        plugin._evaluate(cur, cur)

        observe = plugin.timeline.snapshot()
        records = [item for item in observe["recent_timeline"] if item.get("reason") == "free_text_blocked"]
        candidates = [item for item in observe["recent_timeline"] if item.get("event_id") == "free_text_activity"]
        assert plugin.pushed_events
        assert {event.event_id for event in plugin.pushed_events} == {"free_text_activity"}
        assert len(records) == 5
        assert {item["source"] for item in records} == {
            "awards",
            "combat_feed",
            "hud_notices",
            "hudmsg",
            "hud_events",
        }
        assert any(item["stage"] == "detector_candidate" for item in candidates)
        assert any(item["stage"] == "arbiter_allowed" and item["reason"] == "selected" for item in candidates)
        assert observe["last_decision"]["event_id"] == "free_text_activity"
        assert "raw award text" not in repr(observe)
        assert "raw combat feed text" not in repr(observe)
        assert "raw hud notice text" not in repr(observe)
        assert "raw hudmsg text" not in repr(observe)
        assert "raw hud event text" not in repr(observe)
    finally:
        module.time.time = original_time


def test_test_say_is_allowed_by_explicit_user_action_during_dry_run():
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = True

    result = asyncio.run(plugin.test_say("hello"))

    assert result["pushed"] is True
    assert plugin.pushed_messages


def test_test_say_is_blocked_by_manual_pause():
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = False
    plugin.safety.pause()

    result = asyncio.run(plugin.test_say("hello"))

    assert result["pushed"] is False
    assert result["blocked"] == "paused"
    assert plugin.pushed_messages == []


def test_test_say_push_is_audited_when_allowed():
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = False
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=10)

    result = asyncio.run(plugin.test_say("hello"))

    status = plugin.timeline.snapshot()["last_output_status"]
    assert result["pushed"] is True
    assert plugin.pushed_messages
    assert status["stage"] == "test_say_pushed"
    assert status["kind"] == "test_say"
    assert status["ai_behavior"] == "respond"


def test_chat_message_starts_quiet_window_without_storing_text():
    plugin = _plugin_for_action_tests()
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    plugin._last_user_chat_at = 0.0

    result = plugin.on_chat_message(text="raw private chat should not be stored", sender="human")

    assert result == {"status": "observed"}
    assert plugin._last_user_chat_at > 0
    assert plugin._last_user_chat_mode == "text"
    snapshot = plugin.timeline.snapshot()
    assert "raw private chat" not in repr(snapshot)
    assert snapshot["recent_timeline"][-1]["reason"] == "user_chat_quiet_window_started"


def test_suppressed_dispatch_restores_output_rate_limit_clock():
    plugin = _plugin_for_action_tests()
    plugin.cfg = WtConfig(
        dry_run=False,
        global_rate_limit_seconds=12.0,
        user_chat_quiet_window_seconds=20.0,
    )
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.arbiter = Arbiter(plugin.safety)
    # ts 必须贴近 _evaluate 内部的 time.time()：本用例验证的是"投递被压制后要还原
    # 限流时钟"，不是新鲜度；用占位的 ts=1.0 会让事件老到被 Arbiter 判为必然过期。
    event_ts = time.time()
    plugin.engine = types.SimpleNamespace(
        feed=lambda _prev, _cur: [BattleEvent("overheat", ts=event_ts)],
        reset=lambda: None,
    )
    plugin.resolver = types.SimpleNamespace(
        resolve=lambda _cur, _now, _grace: "IN_FLIGHT",
        reset=lambda: None,
        current_stress_reasons=lambda _now: frozenset(),
    )
    dispatch_results = []

    def suppress_dispatch(event, *, dry_run):
        dispatch_results.append((event.event_id, dry_run))
        return "suppressed(event=overheat/enter, reason=user_chat_quiet_window)"

    plugin.dispatcher = types.SimpleNamespace(push_event=suppress_dispatch)
    plugin._record_blocked_free_text_sources = lambda _cur: None
    plugin._record_deferred_hud_notices = lambda _cur: None
    plugin._suppress_takeoff_grace = lambda candidates, _cur, _now: candidates
    plugin._annotate_runtime_context = lambda candidates, _cur, _now: candidates

    plugin._evaluate(BattleState(), BattleState(connected=True, in_battle=True))

    assert dispatch_results == [("overheat", False)]
    assert plugin.safety.rate_limit_remaining() == 0.0
    assert "overheat" not in plugin.arbiter._last_fired


def test_dry_run_does_not_mark_once_per_battle_event_delivered():
    plugin, module, original_time = _plugin_for_runtime_evaluate_tests(
        clock_values=[100.0],
        dry_run=True,
    )
    plugin.cfg = WtConfig(dry_run=True, global_rate_limit_seconds=12.0)
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.arbiter = Arbiter(plugin.safety)
    event = BattleEvent("low_fuel", ts=100.0)
    marked: list[str] = []
    pushed: list[tuple[BattleEvent, bool]] = []
    plugin.engine = types.SimpleNamespace(
        feed=lambda _prev, _cur: [event],
        reset=lambda: None,
        mark_delivered=marked.append,
    )
    plugin.resolver = types.SimpleNamespace(
        resolve=lambda _cur, _now, _grace: "IN_FLIGHT",
        reset=lambda: None,
        current_stress_reasons=lambda _now: frozenset(),
    )
    def push_event(selected: BattleEvent, *, dry_run: bool) -> str:
        pushed.append((selected, dry_run))
        return (
            "dry_run(event=low_fuel/enter/warning)" if dry_run else "pushed()"
        )

    plugin.dispatcher = types.SimpleNamespace(push_event=push_event)
    plugin._record_blocked_free_text_sources = lambda _cur: None
    plugin._record_deferred_hud_notices = lambda _cur: None
    plugin._suppress_takeoff_grace = lambda candidates, _cur, _now: candidates
    plugin._annotate_runtime_context = lambda candidates, _cur, _now: candidates

    try:
        plugin._evaluate(BattleState(), BattleState(connected=True, in_battle=True))
    finally:
        module.time.time = original_time

    assert pushed == [(event, True)]
    assert marked == []
    assert plugin.safety.rate_limit_remaining(100.0) == 0.0
    assert "low_fuel" not in plugin.arbiter._last_fired


def test_enabling_real_output_rearms_uncommitted_once_per_battle_event():
    plugin = _plugin_for_action_tests()
    plugin.cfg = WtConfig(dry_run=True)
    plugin._session_dry_run_override = None
    rearmed: list[bool] = []
    plugin.engine = types.SimpleNamespace(
        rearm_uncommitted_once_per_battle=lambda: rearmed.append(True)
    )

    asyncio.run(plugin.set_dry_run(False))

    assert plugin.cfg.dry_run is False
    assert rearmed == [True]


def test_failed_dispatch_restores_arbiter_and_retries_selected_edge():
    plugin = _plugin_for_action_tests()
    plugin.cfg = WtConfig(dry_run=False, global_rate_limit_seconds=12.0)
    plugin.safety = SafetyGuard(plugin.cfg)
    plugin.arbiter = Arbiter(plugin.safety)
    event = BattleEvent("overheat", ts=0.0)
    feeds = iter([[event], []])
    plugin.engine = types.SimpleNamespace(
        feed=lambda _prev, _cur: next(feeds),
        reset=lambda: None,
    )
    plugin.resolver = types.SimpleNamespace(
        resolve=lambda _cur, _now, _grace: "IN_FLIGHT",
        reset=lambda: None,
        current_stress_reasons=lambda _now: frozenset(),
    )
    attempts: list[str] = []

    def flaky_dispatch(selected, *, dry_run):
        attempts.append(selected.event_id)
        if len(attempts) == 1:
            raise RuntimeError("temporary host failure")
        return f"pushed(event={selected.event_id}/{selected.edge})"

    plugin.dispatcher = types.SimpleNamespace(push_event=flaky_dispatch)
    plugin._record_blocked_free_text_sources = lambda _cur: None
    plugin._record_deferred_hud_notices = lambda _cur: None
    plugin._suppress_takeoff_grace = lambda candidates, _cur, _now: candidates
    plugin._annotate_runtime_context = lambda candidates, _cur, _now: candidates
    plugin._pending_dispatch_event = None
    state = BattleState(connected=True, in_battle=True)

    plugin._evaluate(BattleState(), state)

    assert attempts == ["overheat"]
    assert plugin._pending_dispatch_event is event
    assert "overheat" not in plugin.arbiter._last_fired
    assert plugin.safety.rate_limit_remaining() == 0.0

    plugin._evaluate(state, state)

    assert attempts == ["overheat", "overheat"]
    assert plugin._pending_dispatch_event is None
    assert plugin.arbiter._last_fired["overheat"][1] == "warning"


def test_user_context_refresh_keeps_only_safe_text_activity_metadata():
    plugin = _plugin_for_action_tests()
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=10)
    plugin._last_user_chat_at = 0.0
    plugin._last_user_chat_mode = "unknown"
    plugin._last_user_context_seen_at = 0.0
    private_text = "raw private chat should never enter plugin state or timeline"
    record = types.SimpleNamespace(
        timestamp=123.0,
        raw={
            "type": "user_message",
            "content": private_text,
            "lanlan": "Lanlan",
            "is_voice": False,
            "_ts": 123.0,
        },
    )
    memory = types.SimpleNamespace(get_sync=lambda *_args, **_kwargs: [record])
    plugin.ctx = types.SimpleNamespace(bus=types.SimpleNamespace(memory=memory))

    mode = plugin._refresh_user_chat_activity(target_lanlan="Lanlan")

    assert mode == "text"
    assert plugin._last_user_chat_at == 123.0
    assert plugin._last_user_chat_mode == "text"
    assert private_text not in repr(vars(plugin))
    assert private_text not in repr(plugin.timeline.snapshot())
    status = plugin.timeline.snapshot()["recent_timeline"][-1]
    assert status["input_mode"] == "text"
    assert status["target_lanlan"] == "Lanlan"


def test_user_context_refresh_rejects_another_character_activity():
    plugin = _plugin_for_action_tests()
    plugin._last_user_chat_at = 0.0
    plugin._last_user_chat_mode = "unknown"
    plugin._last_user_context_seen_at = 0.0
    record = types.SimpleNamespace(
        timestamp=123.0,
        raw={"type": "user_message", "lanlan": "Other", "is_voice": False, "_ts": 123.0},
    )
    memory = types.SimpleNamespace(get_sync=lambda *_args, **_kwargs: [record])
    plugin.ctx = types.SimpleNamespace(bus=types.SimpleNamespace(memory=memory))

    mode = plugin._refresh_user_chat_activity(target_lanlan="Lanlan")

    assert mode == "unknown"
    assert plugin._last_user_chat_at == 0.0


def test_set_identity_persists_player_name_to_runtime_state(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    module = sys.modules[plugin.__class__.__module__]
    original_request = module.request_set_identity

    def fake_request(base_url, timeout, *, name=None, clear=False):
        return {
            "ok": True,
            "requested": name,
            "player_name": "" if clear else name,
            "self": {"name": "" if clear else name, "source": "manual", "confidence": 1.0},
        }

    module.request_set_identity = fake_request
    try:
        result = asyncio.run(plugin.set_identity("CN-Zephyr"))
    finally:
        module.request_set_identity = original_request

    identity = result["identity"]
    assert identity["ok"] is True
    assert identity["persisted"] is True
    assert json.loads(plugin._runtime_state_path.read_text(encoding="utf-8")) == {"player_name": "CN-Zephyr"}
    assert plugin.cfg.player_name == "CN-Zephyr"
    assert plugin.state.combat["player_name"] == "CN-Zephyr"


def test_runtime_state_migrates_to_external_data_without_touching_legacy(tmp_path):
    plugin = _plugin_for_action_tests()
    legacy = tmp_path / "plugin" / ".runtime_state.json"
    primary = tmp_path / "storage" / "data" / ".runtime_state.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"player_name": "legacy"}', encoding="utf-8")
    plugin._legacy_runtime_state_path = legacy
    plugin._runtime_state_path = primary

    plugin._save_runtime_state({"broadcast_frequency": "normal"})

    assert json.loads(primary.read_text(encoding="utf-8")) == {
        "broadcast_frequency": "normal",
        "player_name": "legacy",
    }
    assert legacy.read_text(encoding="utf-8") == '{"player_name": "legacy"}'


def test_runtime_state_uses_new_sdk_data_path_when_available(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._legacy_runtime_state_path = tmp_path / "plugin" / ".runtime_state.json"
    plugin.data_path = lambda *parts: tmp_path / "storage" / "data" / pathlib.Path(*parts)

    assert plugin._resolve_runtime_state_path() == tmp_path / "storage" / "data" / ".runtime_state.json"


def test_startup_log_error_code_excludes_runner_paths():
    Plugin = _runtime_plugin_class()
    raw = r"all_data_layer_runners_failed: C:\Users\tester\python.exe: FileNotFoundError"

    assert Plugin._diagnostic_error_code(raw) == "all_data_layer_runners_failed"


def test_dashboard_identity_uses_saved_player_name_before_combat_frame():
    plugin = _plugin_for_action_tests()
    plugin.cfg = WtConfig(player_name="CN-Zephyr")
    plugin.state = BattleState(combat={})

    payload = plugin._dashboard_payload(plugin.state)

    assert payload["identity"]["player_name"] == "CN-Zephyr"
    assert payload["identity"]["saved_player_name"] == "CN-Zephyr"


def test_dashboard_requires_onboarding_only_after_first_plugin_start(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"

    before_start = plugin._dashboard_payload(plugin.state)
    plugin._startup_completed = True
    after_start = plugin._dashboard_payload(plugin.state)

    assert before_start["onboarding"] == {
        "completed": False,
        "required": False,
        "trigger": "first_plugin_start",
    }
    assert after_start["onboarding"] == {
        "completed": False,
        "required": True,
        "trigger": "first_plugin_start",
    }


def test_complete_onboarding_persists_first_start_dismissal(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    plugin._startup_completed = True

    result = asyncio.run(plugin.complete_onboarding(skipped=True))
    payload = plugin._dashboard_payload(plugin.state)
    saved = json.loads(plugin._runtime_state_path.read_text(encoding="utf-8"))

    assert result["onboarding"]["completed"] is True
    assert result["onboarding"]["skipped"] is True
    assert payload["onboarding"]["required"] is False
    assert saved["onboarding_completed_v1"] is True
    assert saved["onboarding_skipped_v1"] is True


def test_set_dialogue_intrusion_mode_persists_no_interrupt_policy(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"

    result = asyncio.run(plugin.set_dialogue_intrusion_mode("no_interrupt"))

    assert result["mode"] == "no_interrupt"
    assert result["critical_bypass_quiet_window"] is False
    assert plugin.cfg.dialogue_intrusion_mode == "no_interrupt"
    assert plugin.cfg.user_chat_quiet_window_seconds == 60.0
    assert plugin.cfg.battle_output_quiet_window_seconds == 30.0
    saved = json.loads(plugin._runtime_state_path.read_text(encoding="utf-8"))
    assert saved["dialogue_intrusion_mode"] == "no_interrupt"


def test_set_dialogue_intrusion_mode_persists_critical_only_policy(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"

    result = asyncio.run(plugin.set_dialogue_intrusion_mode("critical_only"))

    assert result["mode"] == "critical_only"
    assert result["critical_bypass_quiet_window"] is True
    assert plugin.cfg.dialogue_intrusion_mode == "critical_only"


def test_reload_config_uses_saved_dialogue_mode_and_refreshes_heartbeat_in_place(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin.engine = plugin._build_engine()
    original_engine = plugin.engine
    heartbeat_detectors = [
        detector
        for detector in plugin.engine.detectors
        if getattr(detector, "id", "")
        in {"stall_risk", "high_aoa", "over_g", "low_alt_danger", "overspeed"}
    ]
    other_condition_detectors = [
        detector
        for detector in plugin.engine.detectors
        if hasattr(detector, "critical_heartbeat_seconds") and detector not in heartbeat_detectors
    ]
    assert heartbeat_detectors
    assert all(detector.critical_heartbeat_seconds == 5.0 for detector in heartbeat_detectors)
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    plugin._runtime_state_path.write_text(json.dumps({"dialogue_intrusion_mode": "no_interrupt"}), encoding="utf-8")

    class EmptyConfig:
        async def dump(self, timeout=5.0):
            return {"neko_warthunder": {"critical_preempt_cooldown_seconds": 0}}

    plugin.config = EmptyConfig()

    asyncio.run(plugin._reload_config())

    assert plugin.cfg.dialogue_intrusion_mode == "no_interrupt"
    assert plugin.cfg.user_chat_quiet_window_seconds == 60.0
    assert plugin.cfg.battle_output_quiet_window_seconds == 30.0
    assert plugin.engine is original_engine
    assert all(detector.critical_heartbeat_seconds == 0.0 for detector in heartbeat_detectors)
    assert all(detector.critical_heartbeat_seconds == 0.0 for detector in other_condition_detectors)


def test_reload_config_migrates_legacy_urgent_output_tts_default(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"

    class LegacyConfig:
        def __init__(self):
            self.set_calls = []

        async def dump(self, timeout=5.0):
            return {"neko_warthunder": {"plugin_owned_urgent_output_enabled": True}}

        async def set(self, path, value, timeout=5.0):
            self.set_calls.append((path, value))

    plugin.config = LegacyConfig()
    asyncio.run(plugin._reload_config())

    saved = json.loads(plugin._runtime_state_path.read_text(encoding="utf-8"))
    assert plugin.cfg.plugin_owned_urgent_output_enabled is False
    assert plugin.config.set_calls == [("neko_warthunder.plugin_owned_urgent_output_enabled", False)]
    assert saved["urgent_output_tts_default_migrated_v1"] is True


def test_reload_config_retries_urgent_output_tts_migration_after_persist_failure(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"

    class FailingLegacyConfig:
        async def dump(self, timeout=5.0):
            return {"neko_warthunder": {"plugin_owned_urgent_output_enabled": True}}

        async def set(self, path, value, timeout=5.0):
            raise RuntimeError("write unavailable")

    plugin.config = FailingLegacyConfig()
    asyncio.run(plugin._reload_config())

    assert plugin.cfg.plugin_owned_urgent_output_enabled is False
    assert not plugin._runtime_state_path.exists()


def test_reload_config_preserves_explicit_urgent_output_tts_opt_in_after_migration(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    plugin._runtime_state_path.write_text(
        json.dumps({"urgent_output_tts_default_migrated_v1": True}),
        encoding="utf-8",
    )

    class OptedInConfig:
        async def dump(self, timeout=5.0):
            return {"neko_warthunder": {"plugin_owned_urgent_output_enabled": True}}

        async def set(self, path, value, timeout=5.0):
            raise AssertionError("completed migration must not overwrite an explicit choice")

    plugin.config = OptedInConfig()
    asyncio.run(plugin._reload_config())

    assert plugin.cfg.plugin_owned_urgent_output_enabled is True


def test_dashboard_reports_dialogue_intrusion_policy(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    plugin.cfg = WtConfig(dialogue_intrusion_mode="no_interrupt")

    payload = plugin._dashboard_payload(plugin.state)

    assert payload["output_policy"]["dialogue_intrusion_mode"] == "no_interrupt"
    assert payload["output_policy"]["critical_bypass_quiet_window"] is False


def test_broadcast_preference_actions_persist_and_report_dashboard_state(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"

    frequency_result = asyncio.run(plugin.set_broadcast_frequency("quiet"))
    category_result = asyncio.run(plugin.set_broadcast_category("radio", False))
    payload = plugin._dashboard_payload(plugin.state)
    saved = json.loads(plugin._runtime_state_path.read_text(encoding="utf-8"))

    assert frequency_result["broadcast_frequency"] == "quiet"
    assert category_result["broadcast_categories"]["radio"] is False
    assert payload["output_policy"]["broadcast_frequency"] == "quiet"
    assert payload["output_policy"]["broadcast_categories"]["radio"] is False
    assert payload["output_policy"]["critical_safety_always_enabled"] is True
    assert saved["broadcast_frequency"] == "quiet"
    assert saved["broadcast_categories"]["radio"] is False

    reset_result = asyncio.run(plugin.reset_broadcast_preferences())
    reset_payload = plugin._dashboard_payload(plugin.state)
    reset_saved = json.loads(plugin._runtime_state_path.read_text(encoding="utf-8"))

    assert reset_result["broadcast_frequency"] == "standard"
    assert all(reset_result["broadcast_categories"].values())
    assert reset_payload["output_policy"]["broadcast_frequency"] == "standard"
    assert all(reset_payload["output_policy"]["broadcast_categories"].values())
    assert reset_saved["broadcast_frequency"] == "standard"
    assert all(reset_saved["broadcast_categories"].values())


def test_reload_config_uses_saved_broadcast_preferences(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    plugin._runtime_state_path.write_text(
        json.dumps({"broadcast_frequency": "active", "broadcast_categories": {"awareness": False}}),
        encoding="utf-8",
    )

    class EmptyConfig:
        async def dump(self, timeout=5.0):
            return {}

    plugin.config = EmptyConfig()
    asyncio.run(plugin._reload_config())

    assert plugin.cfg.broadcast_frequency == "active"
    assert plugin.cfg.broadcast_categories["awareness"] is False
    assert plugin.cfg.broadcast_categories["radio"] is True


def test_set_identity_clear_persists_empty_player_name(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin.cfg = WtConfig(player_name="CN-Zephyr")
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    module = sys.modules[plugin.__class__.__module__]
    original_request = module.request_set_identity

    def fake_request(base_url, timeout, *, name=None, clear=False):
        return {"ok": True, "requested": "", "player_name": "", "self": {"name": "", "source": "auto"}}

    module.request_set_identity = fake_request
    try:
        result = asyncio.run(plugin.set_identity(clear=True))
    finally:
        module.request_set_identity = original_request

    assert result["identity"]["persisted"] is True
    assert json.loads(plugin._runtime_state_path.read_text(encoding="utf-8")) == {"player_name": ""}
    assert plugin.cfg.player_name == ""


def test_reload_config_uses_runtime_state_player_name_when_profile_missing(tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / ".runtime_state.json"
    plugin._runtime_state_path.write_text(json.dumps({"player_name": "CN-Zephyr"}), encoding="utf-8")

    class EmptyConfig:
        async def dump(self, timeout=5.0):
            return {}

    plugin.config = EmptyConfig()

    asyncio.run(plugin._reload_config())

    assert plugin.cfg.player_name == "CN-Zephyr"


def test_config_change_restarts_running_data_layer_when_url_changes():
    plugin = _plugin_for_action_tests()
    plugin._startup_completed = True
    calls = []

    class Manager:
        def configure(self, cfg):
            calls.append(("configure", cfg.data_layer_url))

        def snapshot(self):
            return {"mode": "managed", "health": True}

        def stop(self):
            calls.append(("stop", None))
            return {"mode": "stopped", "health": False}

        def start_if_needed(self):
            calls.append(("start", None))
            return {"mode": "managed", "health": True}

    plugin.data_layer_manager = Manager()
    plugin._restore_identity_to_data_layer = lambda: calls.append(("identity", None)) or {"ok": True}

    async def reload_config():
        plugin._apply_config(
            WtConfig(
                data_layer_url="http://127.0.0.1:8113",
                data_layer_auto_start=True,
            )
        )

    plugin._reload_config = reload_config

    result = asyncio.run(plugin.on_config_change())

    assert calls == [
        ("configure", "http://127.0.0.1:8113"),
        ("stop", None),
        ("start", None),
        ("identity", None),
    ]
    assert result["data_layer"] == {"mode": "managed", "health": True}
    assert result["identity"] == {"ok": True}
