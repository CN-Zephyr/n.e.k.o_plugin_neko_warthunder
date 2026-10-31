"""Aggregate naval map-presence edges; no target identity, range or threat inference."""
from __future__ import annotations

from uuid import uuid4

from ...core.contracts import NAVAL_DRY_RUN_ONLY_EVENTS, BattleEvent, BattleState
from ...core.telemetry_freshness import NavalMapSource, naval_map_sample
from .._base import DiscreteDetector


class NavalContactDetector(DiscreteDetector):
    def __init__(self, event_id: str):
        if event_id not in NAVAL_DRY_RUN_ONLY_EVENTS:
            raise ValueError("unsupported naval observation event")
        self.id = event_id
        self.reset()

    def reset(self) -> None:
        self._sample_key: tuple[str, int, int] | None = None
        self._sample_time = 0.0
        self._present = False
        self._enter_hits = self._exit_hits = 0
        self._trace_id: str | None = None
        self._publish_progress()

    def _publish_progress(self) -> None:
        # One immutable value: a UI read cannot observe half of a detector update.
        self._progress = (self._sample_key, self._present, self._enter_hits, self._exit_hits, self._trace_id)

    def diagnostic(self, source: NavalMapSource) -> dict:
        key, active, entering, leaving, trace_id = self._progress
        status, hits = "blocked", 0
        if source.sample is not None:
            if key != source.sample[:3]:
                status = "pending"
            elif active:
                status, hits = ("clearing", leaving) if leaving else ("active", 2)
            else:
                status, hits = ("confirming", entering) if entering else ("absent", 0)
        result = {"event_id": self.id, "status": status, "hits": hits, "required": 2}
        if status in {"active", "clearing"} and trace_id is not None:
            result["trace_id"] = trace_id
        return result

    @property
    def active(self) -> bool:
        return self._present

    def detect(self, prev: BattleState, cur: BattleState) -> BattleEvent | None:
        try:
            return self._detect(prev, cur)
        finally:
            self._publish_progress()

    def _detect(self, prev: BattleState, cur: BattleState) -> BattleEvent | None:
        sample = naval_map_sample(cur)
        if sample is None:
            self.reset()
            return None
        battle, life, count, surface, air, sample_time = sample
        key = battle, life, count
        if self._sample_key is not None:
            if key[:2] != self._sample_key[:2] or count < self._sample_key[2]:
                self.reset()
            elif key == self._sample_key:
                return None  # A fresh fast poll is not another successful map observation.
            elif sample_time < self._sample_time or sample_time - self._sample_time > 5.0:
                self.reset()  # Do not join confirmations across an unobserved outage/clock rewind.
        self._sample_key = key
        self._sample_time = sample_time
        present = surface if self.id == "naval_map_contact" else air
        if not present:
            self._enter_hits = 0
            if self._present:
                self._exit_hits += 1
                if self._exit_hits >= 2:
                    self._present = False
                    self._exit_hits = 0
            return None
        self._exit_hits = 0
        if self._present:
            return None
        self._enter_hits += 1
        if self._enter_hits < 2:
            return None
        self._present = True
        self._enter_hits = 0
        self._trace_id = uuid4().hex
        return BattleEvent(self.id, level="info", ts=cur.timestamp,
                           payload={"domain": "naval", "battle_id": battle,
                                    "life_index": life, "map_sample_count": count}, trace_id=self._trace_id)
