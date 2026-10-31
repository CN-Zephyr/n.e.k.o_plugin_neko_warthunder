"""Distinct successful naval map samples through detection, arbitration and hard output denial."""
from __future__ import annotations

import copy

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core import contracts as C
from neko_warthunder.core.telemetry_freshness import naval_map_sample
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.discrete.naval_situation import NavalContactDetector
from test_helicopter_vrs import _evaluate, _runtime
from test_naval_dashboard import _service


def _state(count=1, now=1000, *, surface=True, air=True, **patch):
    payload = {
        "state": "in_battle", "in_battle": True, "domain": "naval", "timestamp": now,
        "battle_id": "synthetic-naval", "life_index": 1,
        "vehicle": {"valid": False}, "indicators": {"valid": True, "army": "ship"},
        "meta": {"fast": {"age_sec": 0}, "map_objects": {"age_sec": 0.2, "count": count, "life_index": 1}},
        "situation": {"has_player": True, "player": {"x": 0.5, "y": 0.5},
                      "enemy_count": int(surface) + int(air), "air_threat_count": int(air)},
        "chat": [{"msg": "private-sentinel"}],
    }
    payload.update(patch)
    return parse_telemetry(payload)


def _engine():
    return DetectorEngine([NavalContactDetector(event) for event in sorted(C.NAVAL_DRY_RUN_ONLY_EVENTS)])


def _event(event_id="naval_map_contact", count=2, now=1000):
    return C.BattleEvent(event_id, level="info", ts=now, payload={
        "domain": "naval", "battle_id": "synthetic-naval", "life_index": 1, "map_sample_count": count})


def test_source_service_and_parser_use_two_distinct_successful_map_polls(monkeypatch):
    service, _, moment = _service(monkeypatch)
    engine = _engine()
    for expected in ([], ["naval_air_contact", "naval_map_contact"]):
        service._poll_map(0)
        moment[0] += 0.1
        current = parse_telemetry(service.get_snapshot())
        assert [event.event_id for event in engine.feed(current, current)] == expected
        for _ in range(8):
            assert engine.feed(current, current) == []
    assert all(det.active for det in engine.detectors)


def test_zero_baseline_and_two_exit_samples_rearm_without_recovery_or_identity_tracking():
    engine, emitted = _engine(), []
    for count, present in enumerate([False, True, True, False, True, False, False, True, True], 1):
        cur = _state(count, 1000 + count, surface=present, air=False)
        emitted.extend(engine.feed(cur, cur))
    assert [(event.event_id, event.edge, event.level) for event in emitted] == [
        ("naval_map_contact", "enter", "info"), ("naval_map_contact", "enter", "info")]
    assert set(emitted[0].payload) == {"domain", "battle_id", "life_index", "map_sample_count"}


@pytest.mark.parametrize("patch", [
    {"domain": "air"}, {"domain": "heli"}, {"domain": "ground"}, {"domain": "unknown"},
    {"domain": "menu"}, {"dead": True}, {"replay": True}, {"in_battle": False}, {"state": "offline"},
    {"indicators": {"valid": False}}, {"battle_id": None}, {"life_index": 2},
    {"meta": {}}, {"situation": {"has_player": False}},
])
def test_unconfirmed_or_inactive_context_never_creates_naval_candidates(patch):
    engine = _engine()
    for count in (1, 2, 3):
        cur = _state(count, **patch)
        assert engine.feed(cur, cur) == []


@pytest.mark.parametrize("field,value", [
    ("age_sec", None), ("age_sec", -1), ("age_sec", 5.001), ("age_sec", float("nan")),
    ("count", None), ("count", True), ("count", 0), ("count", 1.5),
    ("life_index", True), ("life_index", 2),
])
def test_known_fresh_map_identity_is_required(field, value):
    cur = _state()
    cur.raw["meta"]["map_objects"][field] = value
    assert naval_map_sample(cur) is None


@pytest.mark.parametrize("value", [None, True, -1, 1.5, float("nan"), float("inf")])
def test_unknown_or_invalid_counts_do_not_mean_contact_or_clearance(value):
    cur = _state()
    cur.situation["air_threat_count"] = value
    assert naval_map_sample(cur) is None


def test_count_relationship_player_position_and_fast_age_are_checked():
    cur = _state()
    cur.situation["air_threat_count"] = 3
    assert naval_map_sample(cur) is None
    cur = _state()
    cur.situation["player"]["x"] = float("inf")
    assert naval_map_sample(cur) is None
    cur = _state()
    cur.age_seconds = 6
    assert naval_map_sample(cur) is None
    cur.age_seconds = "invalid"
    assert _engine().feed(cur, cur) == []


@pytest.mark.parametrize("change", ["rewind", "life", "battle", "unknown"])
def test_source_discontinuity_requires_new_confirmation(change):
    engine = _engine()
    for count in (5, 6):
        cur = _state(count)
        engine.feed(cur, cur)
    cur = _state(1 if change == "rewind" else 7)
    if change == "life":
        cur.life_index = cur.raw["meta"]["map_objects"]["life_index"] = 2
    elif change == "battle":
        cur.battle_id = "new-synthetic-battle"
    elif change == "unknown":
        cur.domain = "unknown"
        assert engine.feed(cur, cur) == []
        cur = _state(8)
    assert engine.feed(cur, cur) == []
    cur.raw["meta"]["map_objects"]["count"] += 1
    assert len(engine.feed(cur, cur)) == 2


@pytest.mark.parametrize("event_id", sorted(C.NAVAL_DRY_RUN_ONLY_EVENTS))
@pytest.mark.parametrize("dry_run", [True, False])
def test_complete_plugin_pipeline_observes_but_never_pushes(monkeypatch, event_id, dry_run):
    plugin, moment = _runtime(monkeypatch, dry_run=dry_run)
    for count in (1, 2, 3):
        _evaluate(plugin, moment, _state(count, 1000 + count,
                                       surface=event_id == "naval_map_contact", air=event_id == "naval_air_contact"))
    records = [row for row in plugin.timeline.snapshot()["recent_timeline"] if row.get("event_id") == event_id]
    assert any(row["stage"] == "detector_candidate" for row in records)
    reason = "dry_run_enabled" if dry_run else "naval_dry_run_only"
    assert any(row.get("reason") == reason for row in records)
    assert plugin.pushed_messages == []
    assert "private-sentinel" not in str(records)


@pytest.mark.parametrize("event_id", sorted(C.NAVAL_DRY_RUN_ONLY_EVENTS))
def test_real_dispatcher_denies_before_prompt_even_when_all_output_switches_are_enabled(monkeypatch, event_id):
    plugin, _ = _runtime(monkeypatch, dry_run=False)
    plugin.cfg.ground_status_real_output_enabled = plugin.cfg.v2_live_verified_real_output_enabled = True
    plugin.cfg.plugin_owned_battle_output_enabled = plugin.cfg.plugin_owned_urgent_output_enabled = True
    plugin.dispatcher.build_prompt = lambda *_: pytest.fail("No naval prompt/LLM call allowed")
    assert "reason=naval_dry_run_only" in plugin.dispatcher.push_event(_event(event_id), dry_run=False)
    assert plugin.pushed_messages == []


def test_real_naval_candidates_cannot_occupy_slot_or_cooldown(monkeypatch):
    plugin, _ = _runtime(monkeypatch, dry_run=False)
    nearby = C.BattleEvent("enemy_nearby", ts=1000, payload={"domain": "naval"})
    chosen, chain = plugin.arbiter.decide([_event(), _event("naval_air_contact"), nearby], C.IN_FLIGHT, 1000,
                                         current_state=_state(2))
    assert chosen is nearby
    assert len([row for row in chain if row.get("reason") == "naval_dry_run_only"]) == 2
    assert not C.NAVAL_DRY_RUN_ONLY_EVENTS.intersection(plugin.arbiter._last_fired)


@pytest.mark.parametrize("change", ["clear", "stale", "life", "battle", "counter", "unknown", "dead"])
def test_buffered_candidate_is_revoked_when_latest_source_no_longer_confirms_it(monkeypatch, change):
    plugin, _ = _runtime(monkeypatch)
    plugin.cfg.global_rate_limit_seconds = 2
    plugin.safety.mark_output(critical=False, now=999.5)
    chosen, _ = plugin.arbiter.decide([_event()], C.IN_FLIGHT, 1000, current_state=_state(2))
    assert chosen is None and plugin.arbiter._window_best is not None
    cur, now = _state(3, 1001), 1001
    if change == "clear":
        cur.situation.update(enemy_count=0, air_threat_count=0)
    elif change == "stale":
        now = 1010
    elif change == "life":
        cur.life_index = cur.raw["meta"]["map_objects"]["life_index"] = 2
    elif change == "battle":
        cur.battle_id = "new-synthetic-battle"
    elif change == "counter":
        cur.raw["meta"]["map_objects"]["count"] = 1
    elif change == "unknown":
        cur.domain = "unknown"
    else:
        cur.dead = True
    chosen, chain = plugin.arbiter.decide([], C.IN_FLIGHT, now, current_state=cur)
    assert chosen is None and plugin.arbiter._window_best is None
    assert any(row.get("reason") == "naval_contact_cleared" for row in chain)


def test_pending_retry_and_switch_to_real_cannot_leak_old_naval_observations(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    plugin.state = _state(2, 1000)
    plugin._pending_dispatch_event = _event()
    _evaluate(plugin, moment, _state(3, 1001, surface=False, air=False))
    assert plugin._pending_dispatch_event is None
    assert any(row.get("reason") == "naval_contact_cleared" for row in plugin.timeline.snapshot()["recent_timeline"])
    plugin.cfg.global_rate_limit_seconds = 2
    plugin.safety.mark_output(critical=False, now=1000.5)
    plugin.arbiter.decide([_event(now=1001)], C.IN_FLIGHT, 1001, current_state=_state(2, 1001))
    plugin.cfg.dry_run = False
    chosen, chain = plugin.arbiter.decide([], C.IN_FLIGHT, 1002, current_state=_state(3, 1002))
    assert chosen is None and plugin.arbiter._window_best is None
    assert any(row.get("reason") == "naval_dry_run_only" for row in chain)
    assert plugin.pushed_messages == []


def test_card_reads_do_not_advance_map_detection(monkeypatch):
    import asyncio
    plugin, _ = _runtime(monkeypatch)
    plugin.state = _state(1)
    before = copy.deepcopy(plugin.state.raw)
    for _ in range(5):
        dashboard = asyncio.run(plugin.dashboard_context())
        assert dashboard["output_policy"]["naval_dry_run_only_events"] == sorted(C.NAVAL_DRY_RUN_ONLY_EVENTS)
    assert plugin.engine.feed(plugin.state, plugin.state) == []
    assert plugin.state.raw == before


@pytest.mark.parametrize("later", [999, 1006])
def test_clock_rewind_or_long_unobserved_gap_cannot_complete_confirmation(later):
    engine = _engine()
    cur = _state(1, 1000)
    assert engine.feed(cur, cur) == []
    cur = _state(2, later)
    assert engine.feed(cur, cur) == []
    cur = _state(3, later + 1)
    assert len(engine.feed(cur, cur)) == 2
