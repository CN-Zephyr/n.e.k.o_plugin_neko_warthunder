"""Offline gate for third-party sample identity and ownership replay.

This gate exercises the local replay helper plus the real DetectorEngine. It
proves that legacy combat.feed samples can be reviewed with an explicit manual
identity, that ownership inference is opt-in, and that injected interference
does not become owned kill/death speech.
"""

from __future__ import annotations

import pathlib as _pathlib
import sys as _sys

_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from _common import ensure_package, run_gate_cli  # noqa: E402

from typing import Any

_BASE = ensure_package(__file__)

from neko_warthunder.adapters.telemetry_client import parse_telemetry  # noqa: E402
from neko_warthunder.core.contracts import BattleState  # noqa: E402
from neko_warthunder.detectors._base import DetectorEngine  # noqa: E402
from neko_warthunder.detectors.discrete.lifecycle import build_discrete_detectors  # noqa: E402
from neko_warthunder.tools.replay_8112_server import ReplayState  # noqa: E402


def _frame() -> dict[str, Any]:
    return {
        "state": "in_battle",
        "timestamp": 10.0,
        "in_battle": True,
        "domain": "air",
        "vehicle": {"valid": True, "ias_kmh": 360.0},
        "indicators": {"valid": True, "vehicle_type": "ki_61_1a_otsu_china", "army": "air"},
        "processed": {"flags": {}, "level": "info", "ias_kmh": 360.0},
        "combat": {
            "player_name": "unknown",
            "feed": [
                {"id": 1, "is_kill": True, "killer": "tl0sr2", "victim": "I-153"},
                {"id": 2, "is_kill": True, "killer": "Other", "victim": "tl0sr2 (crashed)", "action": "shot_down"},
                {"id": 3, "is_kill": True, "killer": "Other", "victim": "Yak-1"},
            ],
        },
        "meta": {"fast": {"age_sec": 1.0}},
    }


def run_gate() -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    cases = [
        _case_manual_identity_and_inference(failures),
        _case_inference_is_opt_in(failures),
        _case_wrong_identity_does_not_claim_ownership(failures),
    ]
    return {
        "status": "pass" if not failures else "fail",
        "cases": cases,
        "failures": failures,
        "policy": {
            "manual_identity_required_for_legacy_inference": True,
            "legacy_ownership_inference_is_opt_in": True,
            "interference_combat_feed_must_stay_unowned": True,
            "detector_must_only_use_is_my_flags": True,
            "raw_text_printed": False,
        },
    }


def _case_manual_identity_and_inference(failures: list[dict[str, str]]) -> dict[str, Any]:
    state = _state(
        player_name="tl0sr2",
        infer=True,
        inject_interference=True,
        clock_values=[100.0, 109.0, 109.0],
    )
    payload = state.current_payload()
    events = _detect(payload, player_name="tl0sr2")
    feed = payload["combat"]["feed"]
    event_ids = [event.event_id for event in events]
    owned_kills = [item for item in feed if item.get("is_my_kill") is True]
    owned_deaths = [item for item in feed if item.get("is_my_death") is True]
    unowned_noise = [item for item in feed if item.get("id", 0) >= 900_000]

    _expect(failures, "manual_identity_inference", "identity_source", payload["combat"]["self"]["source"], "manual")
    _expect(failures, "manual_identity_inference", "owned_kill_count", len(owned_kills), 1)
    _expect(failures, "manual_identity_inference", "owned_death_count", len(owned_deaths), 1)
    _expect(failures, "manual_identity_inference", "noise_count", len(unowned_noise), 1)
    if unowned_noise:
        _expect(failures, "manual_identity_inference", "noise.is_my_kill", unowned_noise[0].get("is_my_kill"), False)
        _expect(failures, "manual_identity_inference", "noise.is_my_death", unowned_noise[0].get("is_my_death"), False)
    _expect(failures, "manual_identity_inference", "you_killed_events", event_ids.count("you_killed"), 1)
    _expect(failures, "manual_identity_inference", "you_died_events", event_ids.count("you_died"), 1)
    return {
        "name": "manual_identity_inference",
        "identity_source": payload["combat"]["self"]["source"],
        "owned_kills": len(owned_kills),
        "owned_deaths": len(owned_deaths),
        "noise_items": len(unowned_noise),
        "events": event_ids,
    }


def _case_inference_is_opt_in(failures: list[dict[str, str]]) -> dict[str, Any]:
    state = _state(player_name="tl0sr2", infer=False, inject_interference=True, clock_values=[100.0, 109.0, 109.0])
    payload = state.current_payload()
    event_ids = [event.event_id for event in _detect(payload, player_name="tl0sr2")]
    _expect(failures, "inference_opt_in", "you_killed_events", event_ids.count("you_killed"), 0)
    _expect(failures, "inference_opt_in", "you_died_events", event_ids.count("you_died"), 0)
    return {"name": "inference_opt_in", "events": event_ids}


def _case_wrong_identity_does_not_claim_ownership(failures: list[dict[str, str]]) -> dict[str, Any]:
    state = _state(player_name="CN-Zephyr", infer=True, inject_interference=False, clock_values=[100.0, 101.0, 101.0])
    payload = state.current_payload()
    event_ids = [event.event_id for event in _detect(payload, player_name="CN-Zephyr")]
    _expect(failures, "wrong_identity", "you_killed_events", event_ids.count("you_killed"), 0)
    _expect(failures, "wrong_identity", "you_died_events", event_ids.count("you_died"), 0)
    return {"name": "wrong_identity", "events": event_ids}


def _state(*, player_name: str, infer: bool, inject_interference: bool, clock_values: list[float]) -> ReplayState:
    values = iter(clock_values)
    return ReplayState(
        [_frame()],
        player_name=player_name,
        infer_ownership_from_player_name=infer,
        inject_interference=inject_interference,
        clock=lambda: next(values),
    )


def _detect(payload: dict[str, Any], *, player_name: str) -> list[Any]:
    engine = DetectorEngine(build_discrete_detectors(player_name))
    return engine.feed(BattleState(connected=True, in_battle=True, vehicle_valid=True), parse_telemetry(payload))


def _expect(failures: list[dict[str, str]], case: str, target: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        failures.append({"case": case, "target": target, "reason": f"expected {expected!r}, got {actual!r}"})


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "# neko_warthunder ownership replay gate",
        f"status: {payload['status']}",
        "policy: manual identity is required; legacy ownership inference is opt-in; interference stays unowned",
    ]
    for case in payload.get("cases") or []:
        lines.append(f"- {case['name']}: events={','.join(case.get('events') or []) or '-'}")
        if case.get("identity_source"):
            lines.append(
                "  ownership: "
                f"kills={case.get('owned_kills', 0)} deaths={case.get('owned_deaths', 0)} noise={case.get('noise_items', 0)}"
            )
    if payload.get("failures"):
        lines.append("failures:")
        for failure in payload["failures"]:
            lines.append(f"- {failure['case']}.{failure['target']}: {failure['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    return run_gate_cli(
        description="Check third-party sample identity and ownership replay behavior.",
        run_gate=run_gate,
        render_text=render_text,
        argv=argv,
        json_kwargs={"indent": 2},
    )


if __name__ == "__main__":
    raise SystemExit(main())
