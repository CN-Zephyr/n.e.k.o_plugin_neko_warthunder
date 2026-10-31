"""Drive telemetry failures through the data layer and the full plugin evaluator."""

from __future__ import annotations

import importlib
import sys

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.runtime_timeline import RuntimeTimeline
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.contracts import COMBAT_STRESS, IN_FLIGHT, SPAWNING, BattleState
from neko_warthunder.core.scenario import ScenarioResolver
from neko_warthunder.detectors.discrete.lifecycle import SpawnDetector
from test_status_reporting import _plugin_for_action_tests


@pytest.mark.parametrize("domain", ["air", "ground"])
def test_state_only_outage_cannot_create_spawn_or_replay_persistent_feed(domain, monkeypatch):
    server = importlib.import_module("neko_warthunder.data_layer.data_process.wt_server")
    moment = [1000.0]

    class Client:
        state_ok = True

        def get_indicators_with_status(self):
            return (True, server.ConnectionState.IN_BATTLE,
                    server.Indicators(valid=True, army="tank" if domain == "ground" else domain,
                                      vehicle_type="synthetic-vehicle"),
                    server.MapInfo(valid=True))

        def get_state_with_status(self):
            return self.state_ok, server.VehicleState(valid=self.state_ok, ias_kmh=400)

    client = Client()
    service = server.TelemetryService(client)
    service._state = server.ConnectionState.IN_BATTLE
    service._battle_entry_ts = service._life_entry_ts = 100.0
    service._battle_id = "synthetic-battle"
    service._life_index = 1
    service._combat = {"feed": [{"id": 7, "is_my_kill": True}]}
    plugin = _plugin_for_action_tests()
    plugin.cfg.dry_run = True
    plugin.resolver = ScenarioResolver()
    plugin.arbiter = Arbiter(plugin.safety)
    plugin.engine = plugin._build_engine()
    plugin.timeline = RuntimeTimeline(observability_enabled=True, max_events=100)
    plugin.dispatcher = NekoDispatcher(plugin, timeline=plugin.timeline)
    module = sys.modules[type(plugin).__module__]
    monkeypatch.setattr(module.time, "time", lambda: moment[0])
    monkeypatch.setattr(server.time, "time", lambda: moment[0])
    previous = BattleState()
    scenarios = []
    for now, healthy in [(1000, True), (1007, True), (1067, False), (1068, True)]:
        moment[0] = now
        client.state_ok = healthy
        service._poll_fast()
        current = parse_telemetry(service.get_snapshot())
        assert (current.battle_id, current.life_index, current.dead) == ("synthetic-battle", 1, False)
        plugin._evaluate(previous, current)
        scenarios.append(current.scenario)
        previous = current

    assert scenarios == [SPAWNING, COMBAT_STRESS, IN_FLIGHT, IN_FLIGHT]
    assert plugin.resolver.seconds_since_spawn(1068) == 68
    candidates = [item["event_id"] for item in plugin.timeline.snapshot()["recent_timeline"]
                  if item.get("stage") == "detector_candidate"]
    assert "spawn" not in candidates
    assert "you_died" not in candidates
    assert candidates.count("you_killed") == 1


def test_confirmed_life_change_still_starts_spawn_grace():
    resolver = ScenarioResolver()
    first = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True,
                        battle_id="synthetic-battle", life_index=1)
    resolver.resolve(first, 1000, 6)
    assert resolver.resolve(first, 1007, 6) == IN_FLIGHT
    second = BattleState(**{**first.__dict__, "life_index": 2})

    assert resolver.resolve(second, 1010, 6) == SPAWNING


def test_confirmed_death_and_new_life_still_emit_respawn():
    detector = SpawnDetector()
    first = BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True,
                        battle_id="synthetic-battle", life_index=1)
    assert detector.feed(first, first) is None
    dead = BattleState(**{**first.__dict__, "dead": True})
    detector.feed(first, dead)
    second = BattleState(**{**first.__dict__, "life_index": 2})

    event = detector.feed(dead, second)

    assert event is not None and event.event_id == "spawn"
    assert event.payload["respawn"] is True


def test_first_valid_vehicle_in_a_known_life_still_emits_spawn():
    detector = SpawnDetector()
    waiting = BattleState(connected=True, conn_state="in_battle", in_battle=True,
                          battle_id="synthetic-battle", life_index=1)
    alive = BattleState(**{**waiting.__dict__, "vehicle_valid": True})

    assert detector.feed(waiting, alive).event_id == "spawn"
    assert detector.feed(alive, alive) is None
