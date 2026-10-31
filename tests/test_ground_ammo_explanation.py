"""P2a traverses parser/P1a/dashboard without changing detection or output."""
from __future__ import annotations

import asyncio
import copy
import json

import pytest
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from test_ground_ammo_low import _ammo_outputs, _evaluate, _runtime
from test_ground_dashboard import _plugin
from wt_processor import TelemetryProcessor


def _explanation(plugin):
    return asyncio.run(plugin.dashboard_context())["ground_ammo_explanation"]


@pytest.mark.parametrize(("count", "flags", "expected"), [
    (0, {}, "zero_unconfirmed"), (0, {"ammo_empty": True}, "empty_flagged"),
    (3, {"ammo_low": True}, "low_flagged"), (12, {}, "observed_count"),
    (12, {"ammo_low": False, "ammo_empty": False}, "observed_count"),
    (0, {"ammo_low": True}, "conflicting"), (3, {"ammo_empty": True}, "conflicting"),
    (0, {"ammo_low": True, "ammo_empty": True}, "conflicting"),
    (3, {"ammo_low": True, "ammo_empty": True}, "conflicting"),
    (3, {"ammo_low": "false"}, "conflicting"), (0, {"ammo_empty": 1}, "conflicting"),
    (3, {"ammo_empty": None}, "conflicting"), (3, [], "conflicting"),
    (3, None, "conflicting"), (3, False, "conflicting"),
    (3, {"unrelated_private_marker": "private-sentinel"}, "observed_count"),
])
def test_current_reading_and_only_strict_current_markers(monkeypatch, count, flags, expected):
    plugin, _ = _plugin(monkeypatch, processed={"ammo_first_stage": count, "flags": flags})
    before = copy.deepcopy(plugin.state.raw)
    result = _explanation(plugin)
    assert result == {"status": expected}
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 512
    assert plugin.state.raw == before
    assert not plugin.pushed_messages and not plugin.config_updates


@pytest.mark.parametrize("count", [None, -1, 1.5, True, "3", float("nan"), float("inf"), 2**53, 10**100])
def test_invalid_or_oversized_counts_do_not_become_an_explanation(monkeypatch, count):
    plugin, _ = _plugin(monkeypatch, processed={"ammo_first_stage": count, "flags": {"ammo_empty": True}})
    assert _explanation(plugin) == {"status": "count_unknown"}


@pytest.mark.parametrize("processed", [None, [], False, {"flags": {"ammo_empty": True}}])
def test_missing_processed_or_count_is_unknown(monkeypatch, processed):
    plugin, _ = _plugin(monkeypatch, processed=processed)
    assert _explanation(plugin) == {"status": "count_unknown"}


@pytest.mark.parametrize("patch", [
    {"dead": True}, {"replay": True}, {"state": "offline"}, {"in_battle": False},
    {"vehicle": {"valid": False}}, {"meta": {"vehicle": {"age_sec": 8}}},
    {"meta": {}}, {"meta": {"fast": {"age_sec": -1}, "vehicle": {"age_sec": 0}}},
    {"timestamp": 1001},
])
def test_source_failure_suppresses_current_markers(monkeypatch, patch):
    plugin, _ = _plugin(monkeypatch, **patch)
    plugin.state.raw["processed"]["flags"] = {"ammo_empty": True}
    assert _explanation(plugin) == {"status": "source_unavailable"}


@pytest.mark.parametrize("domain", ["air", "heli", "naval", "unknown", "menu"])
def test_other_domains_do_not_get_ground_explanations(monkeypatch, domain):
    plugin, _ = _plugin(monkeypatch, domain=domain)
    assert _explanation(plugin) is None


def test_partial_p1a_still_allows_usable_ammo_but_fresh_response_does_not_refresh_source(monkeypatch):
    plugin, moment = _plugin(monkeypatch, processed={"ammo_first_stage": 3})
    assert asyncio.run(plugin.dashboard_context())["trusted_facts"]["status"] == "partial"
    assert _explanation(plugin)["status"] == "observed_count"
    moment[0] += 6
    assert _explanation(plugin)["status"] == "source_unavailable"


@pytest.mark.parametrize(("dry_run", "enabled"), [(True, False), (True, True), (False, False), (False, True)])
def test_dashboard_reads_preserve_fsm_delivery_and_policy_through_resupply(monkeypatch, dry_run, enabled):
    plugin, moment = _runtime(monkeypatch, enabled=enabled, dry_run=dry_run)
    processor = TelemetryProcessor()
    observations = []
    for now, ammo in [(1000, 12), (1001, 0), (1002, 0), (1003, 12), (1004, 12)]:
        _evaluate(plugin, moment, processor, ammo, now,
                  meta={"fast": {"age_sec": 0}, "vehicle": {"age_sec": 0}})
        before = copy.deepcopy((plugin.state.raw, [vars(d) for d in plugin.engine.detectors],
                                plugin.timeline.snapshot(), plugin.pushed_messages, plugin.config_updates))
        summary_before = plugin._on_demand_facts()
        for _ in range(3):
            result = asyncio.run(plugin.dashboard_context())
            assert result["trusted_facts"] == summary_before
            assert result["output_policy"]["ground_status_real_output_enabled"] is enabled
        observations.append(result["ground_ammo_explanation"]["status"])
        after = (plugin.state.raw, [vars(d) for d in plugin.engine.detectors],
                 plugin.timeline.snapshot(), plugin.pushed_messages, plugin.config_updates)
        assert after == before
        assert "private-sentinel" not in json.dumps(result["ground_ammo_explanation"])
    assert observations == ["observed_count", "empty_flagged", "empty_flagged", "observed_count", "observed_count"]
    assert len(_ammo_outputs(plugin)) == int(enabled and not dry_run)
    # New life, with a cold zero and no marker, cannot inherit the old explanation.
    plugin.state = parse_telemetry({"state": "in_battle", "in_battle": True, "domain": "ground",
        "timestamp": 1004, "life_index": 2, "vehicle": {"valid": True},
        "meta": {"fast": {"age_sec": 0}, "vehicle": {"age_sec": 0}},
        "processed": {"ammo_first_stage": 0, "flags": {}}})
    assert _explanation(plugin)["status"] == "zero_unconfirmed"
