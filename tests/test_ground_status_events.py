"""陆战乘员与待发弹：检测、域门控与默认关闭的真实输出。"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest
from neko_warthunder.adapters.neko_dispatcher import GROUND_STATUS_GATED_EVENTS, NekoDispatcher
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.core import contracts as C
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.contracts import BattleEvent, WtConfig
from neko_warthunder.core.safety_guard import SafetyGuard
from neko_warthunder.core.scenario import ScenarioResolver
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from test_status_reporting import _plugin_for_action_tests

_ROOT = Path(__file__).resolve().parent.parent


def _ground(flags: dict | None = None, **kwargs) -> C.BattleState:
    return C.BattleState(in_battle=True, vehicle_valid=True, domain="ground", flags=flags or {}, **kwargs)


def _feed(engine: DetectorEngine, frames: list[C.BattleState]) -> list[BattleEvent]:
    events: list[BattleEvent] = []
    for prev, cur in zip(frames, frames[1:]):
        events.extend(engine.feed(prev, cur))
    return events


def _engine() -> DetectorEngine:
    return DetectorEngine(list(build_condition_detectors()))


# ------------------------------------------------------------------ 检测
def test_partial_crew_loss_emits_warning_after_two_frames():
    # 2026-07-22 豹2A7V：4 人减到 2 人，数据层给 crew_loss
    hurt = _ground({"crew_loss": True}, crew_current=2, crew_total=4)
    engine = _engine()

    assert engine.feed(_ground(crew_current=4, crew_total=4), hurt) == []
    events = engine.feed(hurt, hurt)

    assert [(e.event_id, e.edge, e.level) for e in events] == [("ground_crew_loss", "enter", "warning")]
    assert events[0].payload == {"domain": "ground", "crew_current": 2, "crew_total": 4}


def test_single_frame_crew_flicker_does_not_emit():
    full = _ground(crew_current=4, crew_total=4)
    hurt = _ground({"crew_loss": True}, crew_current=3, crew_total=4)

    assert _feed(_engine(), [full, hurt, full, full]) == []


def test_ammo_empty_emits_once_and_rearms_after_resupply():
    full = _ground(ammo_first_stage=12)
    empty = _ground({"ammo_empty": True}, ammo_first_stage=0)
    engine = _engine()

    events = _feed(engine, [full, empty, empty, empty, empty])
    assert [(e.event_id, e.edge) for e in events] == [("ground_ammo_empty", "enter")]
    assert events[0].payload == {"domain": "ground", "ammo_first_stage": 0}

    # 补弹回正数后重新武装，下一次打空再提醒一次
    again = _feed(engine, [empty, full, full, empty, empty])
    assert [(e.event_id, e.edge) for e in again] == [("ground_ammo_empty", "enter")]


@pytest.mark.parametrize("domain", ["air", "helicopter", "naval", ""])
def test_ground_status_events_stay_silent_outside_ground(domain):
    flags = {"crew_loss": True, "ammo_empty": True, "ammo_low": True}
    cur = C.BattleState(in_battle=True, vehicle_valid=True, domain=domain, flags=flags,
                        crew_current=2, crew_total=4, ammo_first_stage=0)
    prev = C.BattleState(in_battle=True, vehicle_valid=True, domain=domain)

    events = _feed(_engine(), [prev, cur, cur, cur])

    assert not {e.event_id for e in events} & GROUND_STATUS_GATED_EVENTS


def test_station_state_flags_still_emit_nothing():
    flags = {"gunner_disabled": True, "driver_disabled": True}
    cur = _ground(flags, gunner_state=1, driver_state=1)

    assert _feed(_engine(), [_ground(), cur, cur, cur]) == []


# ------------------------------------------------------------------ Dispatcher 门控
class _FakePlugin:
    def __init__(self, cfg: WtConfig | None = None) -> None:
        self.cfg = cfg or WtConfig()
        self.calls: list[dict] = []

    def push_message(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _crew_event() -> BattleEvent:
    return BattleEvent("ground_crew_loss", payload={"domain": "ground", "crew_current": 2, "crew_total": 4})


@pytest.mark.parametrize("event_id", sorted(GROUND_STATUS_GATED_EVENTS))
def test_real_output_is_suppressed_by_default(event_id):
    plugin = _FakePlugin()
    timeline = RuntimeTimeline()
    event = BattleEvent(event_id, payload={"domain": "ground"})

    result = NekoDispatcher(plugin, timeline=timeline).push_event(event, dry_run=False)

    assert result == f"suppressed(event={event_id}/enter, reason=ground_status_output_disabled)"
    assert plugin.calls == []
    assert timeline.snapshot()["last_output_status"]["reason"] == "ground_status_output_disabled"


def test_dry_run_keeps_ground_status_observable():
    plugin = _FakePlugin()

    result = NekoDispatcher(plugin).push_event(_crew_event(), dry_run=True)

    assert result.startswith("dry_run(event=ground_crew_loss/")
    assert plugin.calls == []


def test_enabled_switch_allows_real_push_with_ground_prompt():
    plugin = _FakePlugin(WtConfig(ground_status_real_output_enabled=True))

    result = NekoDispatcher(plugin).push_event(_crew_event(), dry_run=False)

    assert result.startswith("pushed(")
    assert plugin.calls[0]["metadata"]["event_id"] == "ground_crew_loss"
    assert "陆战" in plugin.calls[0]["metadata"]["domain_prompt_contract"]


def test_laser_warning_is_not_affected_by_ground_status_switch():
    plugin = _FakePlugin()

    result = NekoDispatcher(plugin).push_event(
        BattleEvent("ground_laser_warning", payload={"domain": "ground"}), dry_run=False
    )

    assert result.startswith("pushed(")


# ------------------------------------------------------------------ 配置
def test_switch_defaults_off_in_config_and_plugin_toml():
    raw = tomllib.loads((_ROOT / "plugin.toml").read_text(encoding="utf-8"))

    assert WtConfig().ground_status_real_output_enabled is False
    assert raw["neko_warthunder"]["ground_status_real_output_enabled"] is False
    assert WtConfig.from_mapping({"ground_status_real_output_enabled": True}).ground_status_real_output_enabled


def test_dashboard_and_panel_expose_ground_status_gate():
    source = (_ROOT / "__init__.py").read_text(encoding="utf-8")
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    assert '"ground_status_real_output_enabled": self.cfg.ground_status_real_output_enabled' in source
    assert '"ground_status_output_disabled"' in panel


@pytest.mark.parametrize("event_id", sorted(GROUND_STATUS_GATED_EVENTS))
def test_disabled_ground_status_cannot_displace_live_proximity_warning(event_id, monkeypatch):
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = False
    plugin.cfg.spawn_grace_seconds = 0
    plugin.cfg.dialogue_intrusion_mode = "allow_interrupt"
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    plugin.dispatcher = NekoDispatcher(plugin, timeline=plugin.timeline, clock=lambda: 100.4)
    module = sys.modules[type(plugin).__module__]
    monkeypatch.setattr(module.time, "time", lambda: 100.4)
    flag = {"ground_crew_loss": "crew_loss", "ground_ammo_empty": "ammo_empty", "ground_ammo_low": "ammo_low"}[event_id]
    ammo = 3 if event_id == "ground_ammo_low" else 0
    first = _ground({flag: True}, connected=True, conn_state="in_battle", timestamp=100.0, ammo_first_stage=ammo)
    plugin._evaluate(first, first)
    second = _ground({flag: True}, connected=True, conn_state="in_battle", timestamp=100.4, ammo_first_stage=ammo,
                     proximity_events=[{"id": 1, "kind": "enter", "category": "enemy_ground",
                                        "distance_m": 300, "clock": 12}])

    plugin._evaluate(first, second)

    assert [call["metadata"]["event_id"] for call in plugin.pushed_messages] == ["enemy_nearby"]
    assert event_id not in plugin.arbiter._last_fired


@pytest.mark.parametrize("event_id", sorted(GROUND_STATUS_GATED_EVENTS))
def test_disabling_ground_status_releases_its_buffered_slot(event_id):
    cfg = WtConfig(dry_run=False, ground_status_real_output_enabled=True, global_rate_limit_seconds=1)

    safety = SafetyGuard(cfg)
    arbiter = Arbiter(safety)
    safety.mark_output(critical=False, now=100)
    chosen, _ = arbiter.decide([BattleEvent(event_id, ts=100)], C.IN_FLIGHT, 100)
    assert chosen is None
    cfg.ground_status_real_output_enabled = False

    chosen, _ = arbiter.decide([BattleEvent("enemy_nearby", ts=101)], C.IN_FLIGHT, 101)

    assert chosen is not None and chosen.event_id == "enemy_nearby"


@pytest.mark.parametrize(("dry_run", "enabled"), [(True, False), (False, True)])
def test_ground_status_is_arbitrated_when_observing_or_enabled(dry_run, enabled):
    cfg = WtConfig(dry_run=dry_run, ground_status_real_output_enabled=enabled)

    chosen, _ = Arbiter(SafetyGuard(cfg)).decide([_crew_event()], C.IN_FLIGHT, 100)

    assert chosen is not None and chosen.event_id == "ground_crew_loss"
