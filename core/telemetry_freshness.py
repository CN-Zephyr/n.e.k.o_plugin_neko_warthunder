"""Source validation shared by detection, arbitration and readonly diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import NAVAL_DRY_RUN_ONLY_EVENTS, BattleEvent, BattleState

GROUND_SAMPLE_MAX_AGE_SECONDS = 5.0


@dataclass(frozen=True)
class GroundIndicatorSource:
    status: str
    age_seconds: float | None = None
    timestamp: float | None = None
    key: tuple[str, int, int] | None = None


def legacy_ground_sample_age(state: BattleState, now: float | None = None) -> float | None:
    """Age a recorded tank sample by its fast snapshot time on older 8112 responses."""
    raw = state.raw if isinstance(state.raw, dict) else {}
    indicators = raw.get("indicators")
    timestamp = state.timestamp
    if (not isinstance(indicators, dict) or indicators.get("valid") is not True
            or indicators.get("army") != "tank" or type(timestamp) not in (int, float)
            or not 0 < timestamp < math.inf):
        return None
    age = state.age_seconds
    recorded_age = age if type(age) in (int, float) and 0 <= age < math.inf else 0.0
    if now is None:
        return recorded_age
    if type(now) not in (int, float) or not timestamp <= now < math.inf:
        return None
    return max(recorded_age, now - timestamp)


def legacy_ground_replay_segment(state: BattleState) -> tuple[int, int] | None:
    """Read the playback pass and continuous span, independently of recorded life identity."""
    meta = state.raw.get("meta") if isinstance(state.raw, dict) else None
    marker = meta.get("replay_ground_segment") if isinstance(meta, dict) else None
    if isinstance(marker, list) and len(marker) == 2 and all(type(value) is int and value >= 0 for value in marker):
        return marker[0], marker[1]
    return None


def modern_ground_replay_boundaries(state: BattleState) -> tuple[int, int, int] | None:
    meta = state.raw.get("meta") if isinstance(state.raw, dict) else None
    marker = meta.get("replay_ground_boundaries") if isinstance(meta, dict) else None
    if (isinstance(marker, list) and len(marker) == 3
            and all(type(value) is int and value >= 0 for value in marker) and marker[2] <= marker[1]):
        return marker[0], marker[1], marker[2]
    return None


def ground_indicator_source(state: BattleState, now: float | None = None) -> GroundIndicatorSource | None:
    """Validate the per-source metadata. None denotes an older data service."""
    raw = state.raw if isinstance(state.raw, dict) else {}
    meta = raw.get("meta")
    if not isinstance(meta, dict) or "ground_indicators" not in meta:
        return None
    sample = meta["ground_indicators"]
    indicators = raw.get("indicators")
    if (not isinstance(sample, dict) or sample.get("status") not in ("ready", "held")
            or not isinstance(indicators, dict) or indicators.get("valid") is not True
            or indicators.get("army") != "tank"):
        return GroundIndicatorSource("unavailable")
    count, life, battle = sample.get("count"), sample.get("life_index"), sample.get("battle_id")
    if (not isinstance(battle, str) or not battle or battle != state.battle_id
            or type(life) is not int or life < 1 or life != state.life_index
            or type(count) is not int or count < 1):
        return GroundIndicatorSource("unavailable")
    timestamp, age = sample.get("sample_timestamp"), sample.get("age_sec")
    if (type(timestamp) not in (int, float) or not 0 < timestamp < math.inf
            or type(age) not in (int, float) or not 0 <= age < math.inf):
        return GroundIndicatorSource("unavailable")
    if now is not None:
        if not timestamp <= now < math.inf:
            return GroundIndicatorSource("unavailable")
        age = max(age, now - timestamp)
    status = "stale" if age >= GROUND_SAMPLE_MAX_AGE_SECONDS else sample["status"]
    return GroundIndicatorSource(status, age, timestamp, (battle, life, count))


def helicopter_sample_is_fresh(state: BattleState | None, now: float) -> bool:
    """Require a live helicopter backed by a known, fresh vehicle sample."""
    if state is None or not (state.connected and state.conn_state == "in_battle"
                            and state.is_alive() and not state.replay
                            and (state.domain or "").lower() == "heli"):
        return False
    raw = state.raw if isinstance(state.raw, dict) else {}
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    vehicle = meta.get("vehicle") if isinstance(meta.get("vehicle"), dict) else {}
    ages = (state.age_seconds, vehicle.get("age_sec"))
    values = (*ages, state.timestamp, now)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return False
    fast_age, vehicle_age = ages
    if fast_age < 0 or vehicle_age < 0 or state.timestamp <= 0:
        return False
    elapsed = max(0.0, now - state.timestamp - fast_age)
    return max(fast_age, vehicle_age + elapsed, elapsed) <= 5.0


def helicopter_vrs_active(state: BattleState | None, now: float) -> bool:
    return bool(helicopter_sample_is_fresh(state, now)
                and (state.flag("vrs_warning") or state.flag("vrs_critical")))


NavalMapSample = tuple[str, int, int, bool, bool, float]


@dataclass(frozen=True)
class NavalMapSource:
    reason: str
    sample: NavalMapSample | None = None
    sample_age_seconds: float | None = None


def naval_map_source(state: BattleState | None, now: float | None = None) -> NavalMapSource:
    """Explain the exact detection predicate without advancing it or exposing raw telemetry."""
    if state is None or not state.connected or state.conn_state == "offline":
        return NavalMapSource("offline")
    if state.replay:
        return NavalMapSource("replay")
    if state.conn_state != "in_battle" or not state.in_battle:
        return NavalMapSource("waiting")
    if state.dead:
        return NavalMapSource("dead")
    if state.domain != "naval" or state.domain_source != "indicators_army":
        return NavalMapSource("unconfirmed_naval")
    if not state.battle_id:
        return NavalMapSource("missing_battle")
    raw = state.raw if isinstance(state.raw, dict) else {}
    indicators = raw.get("indicators")
    if not (isinstance(indicators, dict) and indicators.get("valid") is True
            and indicators.get("army") in ("ship", "fleet")):
        return NavalMapSource("unconfirmed_naval")
    if not state.is_alive():
        return NavalMapSource("no_player")
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    sample = meta.get("map_objects") if isinstance(meta.get("map_objects"), dict) else {}
    situation = state.situation if isinstance(state.situation, dict) else {}
    player = situation.get("player") if isinstance(situation.get("player"), dict) else {}

    def finite(value):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)

    fast, age = state.age_seconds, sample.get("age_sec")
    if not all(finite(value) for value in (fast, age, state.timestamp)):
        return NavalMapSource("unknown_age")
    if now is None:
        now = state.timestamp + fast
    if not finite(now):
        return NavalMapSource("unknown_age")
    if fast < 0 or age < 0 or state.timestamp <= 0:
        return NavalMapSource("unknown_age")
    elapsed = max(0.0, now - state.timestamp - fast)
    sample_age = round(age + elapsed, 3) if math.isfinite(age + elapsed) else None
    if max(fast, age + elapsed, elapsed) > 5.0:
        return NavalMapSource("stale", sample_age_seconds=sample_age)
    life, count, sampled_life = state.life_index, sample.get("count"), sample.get("life_index")
    if not all(finite(value) and value >= 1 and int(value) == value for value in (life, count, sampled_life)):
        return NavalMapSource("unknown_sample", sample_age_seconds=sample_age)
    if life != sampled_life:
        return NavalMapSource("life_mismatch", sample_age_seconds=sample_age)
    if situation.get("has_player") is not True:
        return NavalMapSource("no_player", sample_age_seconds=sample_age)
    if not all(finite(player.get(key)) and 0 <= player[key] <= 1 for key in ("x", "y")):
        return NavalMapSource("invalid_position", sample_age_seconds=sample_age)
    enemy, air = situation.get("enemy_count"), situation.get("air_threat_count")
    if not all(finite(value) and value >= 0 and int(value) == value for value in (enemy, air)) or air > enemy:
        return NavalMapSource("invalid_counts", sample_age_seconds=sample_age)
    sample = state.battle_id, int(life), int(count), enemy > air, air > 0, state.timestamp + fast - age
    return NavalMapSource("ready", sample, sample_age)


def naval_map_sample(state: BattleState | None, now: float | None = None) -> NavalMapSample | None:
    return naval_map_source(state, now).sample


def naval_contact_still_active(event: BattleEvent, state: BattleState | None, now: float) -> bool:
    sample = naval_map_sample(state, now)
    if event.event_id not in NAVAL_DRY_RUN_ONLY_EVENTS or sample is None:
        return False
    battle, life, count, surface, air, _ = sample
    payload = event.payload
    source_count = payload.get("map_sample_count")
    return bool(payload.get("domain") == "naval" and payload.get("battle_id") == battle
                and isinstance(payload.get("life_index"), int) and not isinstance(payload.get("life_index"), bool)
                and payload.get("life_index") == life
                and isinstance(source_count, int) and not isinstance(source_count, bool) and 1 <= source_count <= count
                and (surface if event.event_id == "naval_map_contact" else air))
