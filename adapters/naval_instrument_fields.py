"""Readonly transport-field inventory; no naval instrument values or inferred semantics."""
from __future__ import annotations

import math
from typing import Any

from ..core.contracts import BattleState

_FIELDS = (("speed", "speed", "speed"), ("heading", "heading_deg", "compass"),
           ("rpm", "rpm", "rpm"), ("throttle", "throttle", "throttle"))


def _finite(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _field_status(indicators: dict, original: dict, normalized_key: str, raw_key: str) -> str:
    normalized, raw = indicators.get(normalized_key), original.get(raw_key)
    if ((normalized is not None and not _finite(normalized))
            or (raw is not None and not _finite(raw))):
        return "invalid"
    if normalized is None:
        return "raw_only" if raw is not None else "missing"
    if raw_key not in original:
        return "normalized_only"
    if raw is None or normalized != raw:
        return "conflicting"
    return "observed_numeric"


def _positive_integer(value: Any) -> bool:
    return _finite(value) and value >= 1 and int(value) == value


def _sample_boundary(payload: dict, state: BattleState, army: str, now: float) -> tuple:
    meta = payload.get("meta")
    if not isinstance(meta, dict) or "naval_indicators" not in meta:
        return "legacy_response", None, None, False
    sample = meta["naval_indicators"]
    if not isinstance(sample, dict):
        return "invalid_sample", None, None, False
    if sample.get("status") != "ready":
        reason = sample.get("status")
        allowed = {"probe_failed", "replay", "dead", "waiting", "context_changed",
                   "invalid_source", "unknown_life", "unknown_age", "unavailable"}
        return reason if isinstance(reason, str) and reason in allowed else "invalid_sample", None, None, False
    if (not _positive_integer(sample.get("count"))
            or not _positive_integer(sample.get("life_index"))
            or not _positive_integer(payload.get("life_index"))
            or sample.get("battle_id") != state.battle_id
            or sample.get("battle_id") != payload.get("battle_id")
            or sample.get("life_index") != state.life_index
            or sample.get("life_index") != payload.get("life_index")
            or sample.get("army") != army):
        return "unbound_sample", None, None, False
    timestamp, reported_age = sample.get("sample_timestamp"), sample.get("age_sec")
    if (not _finite(timestamp) or not _finite(reported_age) or reported_age < 0
            or timestamp <= 0 or timestamp > state.timestamp or timestamp > now):
        return "unknown_sample_age", None, None, False
    age = max(reported_age, now - timestamp)
    if age > 5.0:
        return "stale_sample", round(age, 3), None, False
    return "ready", round(age, 3), sample["count"], True


def snapshot_naval_instrument_fields(state: BattleState, now: float) -> dict[str, Any] | None:
    if state.domain != "naval" and not (state.domain == "unknown" and (state.in_battle or state.situation)):
        return None
    payload = state.raw if isinstance(state.raw, dict) else {}
    indicators = payload.get("indicators")
    indicators = indicators if isinstance(indicators, dict) else {}
    original = indicators.get("raw", {})
    age = None
    if not state.connected or state.conn_state == "offline":
        status = "offline"
    elif state.replay:
        status = "replay"
    elif not state.in_battle or state.conn_state != "in_battle":
        status = "waiting"
    elif state.dead:
        status = "dead"
    elif (state.domain != "naval" or state.domain_source != "indicators_army"
          or indicators.get("valid") is not True or indicators.get("army") not in ("ship", "fleet")):
        status = "unconfirmed_naval"
    elif (not isinstance(state.battle_id, str) or not state.battle_id or not _finite(state.life_index)
          or state.life_index < 1 or int(state.life_index) != state.life_index):
        status = "unknown_life"
    elif (not isinstance(original, dict)
          or ("valid" in original and original["valid"] is not True)
          or ("army" in original and original["army"] != indicators.get("army"))):
        status = "invalid_source"
    elif (not all(_finite(value) for value in (state.timestamp, state.age_seconds, now))
          or state.timestamp <= 0 or now <= 0 or state.age_seconds < 0 or state.timestamp > now):
        status = "unknown_age"
    else:
        # Fast-loop attempts are not independent successful instrument samples.
        # Response age alone cannot establish current-life sample ownership.
        # Validate the dedicated metadata below; never borrow vehicle/map evidence.
        age = round(max(state.age_seconds, now - state.timestamp), 3)
        status = "stale" if max(state.age_seconds, now - state.timestamp) > 5.0 else "response_only"
    sampling, sample_age, count, bound = "unavailable", None, None, False
    if status == "response_only":
        sampling, sample_age, count, bound = _sample_boundary(payload, state, indicators.get("army"), now)
        if bound and (original.get("valid") is not True or original.get("army") != indicators.get("army")):
            sampling, sample_age, count, bound = "invalid_sample", None, None, False
    fields = [{"id": name, "status": (_field_status(indicators, original, normalized, raw)
                                      if status == "response_only" and sampling in {"ready", "legacy_response"}
                                      else "unavailable")}
              for name, normalized, raw in _FIELDS]
    return {"source_status": status, "response_age_seconds": age, "fields": fields,
            "sampling_status": sampling, "sample_age_seconds": sample_age, "sample_count": count,
            "instrument_values_enabled": False, "real_output_enabled": False,
            "sample_life_bound": bound, "naval_semantics_verified": False}
