"""Current ready-rack reading/marker explanation for the existing ground card."""
from __future__ import annotations

import math
from typing import Any

from ..core.contracts import BattleState


def _count(value: Any) -> bool:
    # Bound to exact browser integers as well as finite nonnegative counts.
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and 0 <= value <= 2**53 - 1 and math.isfinite(value) and int(value) == value)


def snapshot_ground_ammo_explanation(state: BattleState, summary: dict[str, Any]) -> dict[str, str] | None:
    """Project one fixed code; do not inspect history, FSM state or output decisions.

    P1a controls freshness and the current count. Check original input types too:
    legacy parsing can coerce numeric strings and flag values before P1a sees them.
    Only these two current raw markers are read, never exported as a collection.
    """
    if summary.get("domain") != "ground":
        return None
    result = {"status": "source_unavailable"}
    if not any(source.get("id") == "vehicle" and source.get("status") == "ready"
               for source in summary["sources"]):
        return result
    fact = next(row for row in summary["facts"] if row["id"] == "ammo_first_stage")
    raw = state.raw if isinstance(state.raw, dict) else {}
    processed = raw.get("processed")
    count = fact["value"]
    if (fact["status"] != "available" or not _count(count) or not isinstance(processed, dict)
            or not _count(processed.get("ammo_first_stage"))):
        return {"status": "count_unknown"}
    flags = processed.get("flags", {})
    if not isinstance(flags, dict) or any(
        key in flags and not isinstance(flags[key], bool) for key in ("ammo_low", "ammo_empty")
    ):
        return {"status": "conflicting"}
    low, empty = flags.get("ammo_low") is True, flags.get("ammo_empty") is True
    if (count != processed["ammo_first_stage"] or (low and empty)
            or (empty and count > 0) or (low and count == 0)):
        code = "conflicting"
    elif count == 0:
        code = "empty_flagged" if empty else "zero_unconfirmed"
    else:
        code = "low_flagged" if low else "observed_count"
    return {"status": code}
