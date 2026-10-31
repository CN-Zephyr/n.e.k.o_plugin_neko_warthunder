"""Readonly diagnostics follow real source validation and completed detector updates."""
from __future__ import annotations

import asyncio
import copy
import json
import threading

import pytest
from neko_warthunder.core.telemetry_freshness import naval_map_sample, naval_map_source
from neko_warthunder.detectors.discrete.naval_situation import NavalContactDetector
from test_helicopter_vrs import _evaluate, _runtime
from test_naval_events import _state


def _card(plugin):
    return asyncio.run(plugin.dashboard_context())["naval_detection"]


def _rows(card):
    return {row["event_id"]: (row["status"], row["hits"], row["required"]) for row in card["detectors"]}


@pytest.mark.parametrize("change,reason", [
    ("offline", "offline"), ("replay", "replay"), ("waiting", "waiting"), ("dead", "dead"),
    ("unknown", "unconfirmed_naval"), ("conflict", "unconfirmed_naval"),
    ("invalid_indicators", "unconfirmed_naval"), ("missing_battle", "missing_battle"),
    ("age", "unknown_age"), ("negative_age", "unknown_age"), ("timestamp", "unknown_age"),
    ("stale", "stale"), ("fast_stale", "stale"), ("counter", "unknown_sample"),
    ("life", "life_mismatch"), ("no_player", "no_player"),
    ("position", "invalid_position"), ("count", "invalid_counts"), ("air_count", "invalid_counts"),
])
def test_source_reasons_share_the_actual_detector_predicate(change, reason):
    cur = _state()
    if change == "offline":
        cur.connected = False
    elif change in {"replay", "dead"}:
        setattr(cur, change, True)
    elif change == "waiting":
        cur.in_battle = False
    elif change == "unknown":
        cur.domain = "unknown"
    elif change == "conflict":
        cur.domain_source = "conflicting_domain"
    elif change == "invalid_indicators":
        cur.raw["indicators"]["valid"] = False
    elif change == "missing_battle":
        cur.battle_id = None
    elif change in {"age", "negative_age", "stale"}:
        cur.raw["meta"]["map_objects"]["age_sec"] = {"age": None, "negative_age": -1, "stale": 6}[change]
    elif change == "timestamp":
        cur.timestamp = float("nan")
    elif change == "fast_stale":
        cur.age_seconds = 6
    elif change == "counter":
        cur.raw["meta"]["map_objects"]["count"] = True
    elif change == "life":
        cur.life_index = 2
    elif change == "no_player":
        cur.situation["has_player"] = False
    elif change == "position":
        cur.situation["player"]["x"] = float("inf")
    else:
        cur.situation["air_threat_count"] = None if change == "count" else 3
    source = naval_map_source(cur)
    assert source.reason == reason
    assert source.sample is None and naval_map_sample(cur) is None
    assert NavalContactDetector("naval_map_contact").diagnostic(source)["status"] == "blocked"


def test_progress_tracks_confirmation_hold_exit_and_rearming_through_plugin(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    expected = [(True, "confirming", 1), (True, "active", 2), (True, "active", 2),
                (False, "clearing", 1), (False, "absent", 0), (True, "confirming", 1), (True, "active", 2)]
    for count, (present, status, hits) in enumerate(expected, 1):
        _evaluate(plugin, moment, _state(count, 1000 + count, surface=present, air=False))
        card = _card(plugin)
        assert card["source_status"] == "ready" and card["map_sample_count"] == count
        assert card["real_output_enabled"] is False
        assert _rows(card) == {"naval_map_contact": (status, hits, 2), "naval_air_contact": ("absent", 0, 2)}
    assert plugin.pushed_messages == []


def test_repeated_ui_reads_and_cached_fast_polls_cannot_finish_confirmation(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    _evaluate(plugin, moment, _state())
    before = copy.deepcopy(plugin.state)
    for _ in range(10):
        assert _rows(_card(plugin))["naval_map_contact"] == ("confirming", 1, 2)
        _evaluate(plugin, moment, _state(1, 1001))
    assert plugin.state.raw == before.raw | {"timestamp": 1001}
    assert not any(row.get("event_id") in {"naval_map_contact", "naval_air_contact"}
                   for row in plugin.timeline.snapshot()["recent_timeline"])
    _evaluate(plugin, moment, _state(2, 1002))
    assert _rows(_card(plugin))["naval_map_contact"] == ("active", 2, 2)


def test_readonly_source_ages_without_resetting_or_advancing_detector(monkeypatch):
    plugin, moment = _runtime(monkeypatch)
    _evaluate(plugin, moment, _state())
    before = [det._progress for det in plugin.engine.detectors if isinstance(det, NavalContactDetector)]
    state_before = copy.deepcopy(plugin.state)
    moment[0] = 1006
    for _ in range(5):
        card = _card(plugin)
        assert card["source_status"] == "stale" and card["sample_age_seconds"] == 6.2
        assert all(row[0] == "blocked" and row[1] == 0 for row in _rows(card).values())
    assert plugin.state == state_before
    assert [det._progress for det in plugin.engine.detectors if isinstance(det, NavalContactDetector)] == before
    _evaluate(plugin, moment, _state(2, 1007))
    assert _rows(_card(plugin))["naval_map_contact"] == ("confirming", 1, 2)


@pytest.mark.parametrize("change", ["new_sample", "life", "battle", "rewind"])
def test_new_unprocessed_source_never_borrows_old_confirmation(monkeypatch, change):
    plugin, moment = _runtime(monkeypatch)
    for count in (5, 6):
        _evaluate(plugin, moment, _state(count))
    cur = _state(7)
    if change == "life":
        cur.life_index = cur.raw["meta"]["map_objects"]["life_index"] = 2
    elif change == "battle":
        cur.battle_id = "private-battle-sentinel"
    elif change == "rewind":
        cur.raw["meta"]["map_objects"]["count"] = 1
    plugin.state = cur  # A poll can publish its state just before engine.feed completes.
    assert set(_rows(_card(plugin)).values()) == {("pending", 0, 2)}
    _evaluate(plugin, moment, cur)
    expected = "active" if change == "new_sample" else "confirming"
    assert _rows(_card(plugin))["naval_map_contact"][0] == expected
    assert "private-battle-sentinel" not in json.dumps(_card(plugin))


@pytest.mark.parametrize("domain", ["air", "heli", "ground", "menu"])
def test_card_does_not_leak_into_other_domains(monkeypatch, domain):
    plugin, _ = _runtime(monkeypatch)
    plugin.state = _state()
    plugin.state.domain = domain
    assert _card(plugin) is None


def test_unconfirmed_generic_map_and_disabled_plugin_explain_why_no_detection(monkeypatch):
    plugin, _ = _runtime(monkeypatch)
    plugin.state = _state()
    plugin.state.domain = "unknown"
    assert _card(plugin)["source_status"] == "unconfirmed_naval"
    assert set(_rows(_card(plugin)).values()) == {("blocked", 0, 2)}
    plugin.state = _state()
    plugin.cfg.enabled = False
    assert _card(plugin)["detection_enabled"] is False
    assert set(_rows(_card(plugin)).values()) == {("disabled", 0, 2)}


def test_real_mode_and_output_switches_cannot_change_diagnostic_output_policy(monkeypatch):
    plugin, moment = _runtime(monkeypatch, dry_run=False)
    plugin.cfg.ground_status_real_output_enabled = plugin.cfg.v2_live_verified_real_output_enabled = True
    plugin.cfg.plugin_owned_battle_output_enabled = plugin.cfg.plugin_owned_urgent_output_enabled = True
    for count in (1, 2):
        _evaluate(plugin, moment, _state(count))
    card = _card(plugin)
    assert card["real_output_enabled"] is False
    assert set(_rows(card).values()) == {("active", 2, 2)}
    assert "private-sentinel" not in json.dumps(card)
    assert plugin.pushed_messages == []


def test_partial_detector_update_cannot_appear_as_completed_progress(monkeypatch):
    detector = NavalContactDetector("naval_map_contact")
    first, second = _state(), _state(2)
    detector.feed(first, first)
    reached, release = threading.Event(), threading.Event()
    original = detector._detect

    def paused(prev, cur):
        result = original(prev, cur)
        reached.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(detector, "_detect", paused)
    worker = threading.Thread(target=detector.feed, args=(first, second))
    worker.start()
    try:
        assert reached.wait(5)
        assert detector.diagnostic(naval_map_source(second))["status"] == "pending"
        assert detector.diagnostic(naval_map_source(first))["status"] == "confirming"
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert detector.diagnostic(naval_map_source(second))["status"] == "active"
