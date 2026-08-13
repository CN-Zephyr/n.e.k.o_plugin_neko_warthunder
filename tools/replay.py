"""回放/仿真器：离线喂遥测帧序列，跑完整 scenario→detector→arbiter，打印猫会说什么。

无需 NEKO 宿主 / 游戏。两种数据源：
- 默认：内置合成场景（出生→巡航→濒临失速[critical 抢占]→低油→击杀→阵亡→重生→战斗结束）。
- 文件：`uv run python tools/replay.py path/to/frames.json`，frames.json = /api/telemetry 帧的 JSON 数组（真机抓的）。

用途：离线验证决策行为；将来用真机帧序列做回归 / 调参（看决策链路）。
"""

from __future__ import annotations

import json
import pathlib
import sys

from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.adapters.telemetry_client import parse_telemetry
from neko_warthunder.core import contracts as C
from neko_warthunder.core.arbiter import Arbiter
from neko_warthunder.core.contracts import WtConfig
from neko_warthunder.core.safety_guard import SafetyGuard
from neko_warthunder.core.scenario import ScenarioResolver
from neko_warthunder.detectors._base import DetectorEngine
from neko_warthunder.detectors.condition.flight_safety import build_condition_detectors
from neko_warthunder.detectors.discrete.lifecycle import build_discrete_detectors


def _alive(**kw) -> C.BattleState:
    d = dict(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=True)
    d.update(kw)
    return C.BattleState(**d)


def _oob() -> C.BattleState:
    return C.BattleState(connected=True, conn_state="not_in_battle", in_battle=False)


def _rep(state: C.BattleState, n: int) -> list[C.BattleState]:
    return [state for _ in range(n)]


def _synthetic() -> list[C.BattleState]:
    t: list[C.BattleState] = []
    t += _rep(_oob(), 2)
    t += _rep(_alive(ias_kmh=300), 8)                                                          # 出生 + 巡航
    t += _rep(_alive(ias_kmh=170, aoa_deg=19, altitude_m=500, flags={"stall_critical": True}), 4)  # 濒临失速(critical→抢占)
    t += _rep(_alive(ias_kmh=330), 6)                                                          # 改出
    t += _rep(_alive(ias_kmh=300, fuel_fraction=0.1, flags={"fuel_low": True}), 4)             # 低油(warning)
    t += [_alive(ias_kmh=300, combat={"player_name": "Me", "feed": [{"id": 1, "is_kill": True, "is_my_kill": True, "is_my_death": False, "involves_me": True, "killer": "Me", "victim": "Bandit", "victim_vehicle": "Spitfire"}]})]  # 击杀
    t += _rep(_alive(ias_kmh=300), 4)
    t += [C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False, combat={"player_name": "Me", "feed": [{"id": 2, "is_my_kill": False, "is_my_death": True, "involves_me": True, "killer": "Bandit", "killer_vehicle": "Yak-3", "action": "shot_down"}]})]  # 阵亡
    t += _rep(C.BattleState(connected=True, conn_state="in_battle", in_battle=True, vehicle_valid=False), 1)
    t += _rep(_alive(ias_kmh=250), 8)                                                          # 重生
    t += _rep(_alive(ias_kmh=300, mission_status="win"), 2)                                    # 战斗结束
    return t


def _load_frames(path: pathlib.Path) -> list[C.BattleState]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        data = [data]
    return [parse_telemetry(f) for f in data]


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        frames = _load_frames(pathlib.Path(argv[1]))
        print(f"# replay from file: {argv[1]} ({len(frames)} frames)\n")
    else:
        frames = _synthetic()
        print("# replay: 内置合成场景\n")

    cfg = WtConfig(player_name="Me", global_rate_limit_seconds=3, critical_preempt_cooldown_seconds=2, spawn_grace_seconds=6)
    resolver = ScenarioResolver()
    engine = DetectorEngine(list(build_condition_detectors()) + list(build_discrete_detectors(cfg.player_name)))
    arbiter = Arbiter(SafetyGuard(cfg))
    disp = NekoDispatcher(None)

    prev = C.BattleState()
    now = 1000.0
    last_scn = None
    spoken = 0
    for state in frames:
        scn = resolver.resolve(state, now, cfg.spawn_grace_seconds)
        cands = engine.feed(prev, state)
        chosen, chain = arbiter.decide(cands, scn, now)
        if cands or chosen or scn != last_scn:
            cand_ids = [f"{c.event_id}/{c.level}" for c in cands]
            head = f"t={now - 1000:5.1f}s  scn={scn:<14} cand={cand_ids}"
            if chosen is not None:
                spoken += 1
                print(head + f"  ==> 说: {chosen.event_id}/{chosen.level}")
                for line in disp.build_prompt(chosen).splitlines():
                    print(f"            {line}")
            elif cands:
                reasons = ",".join(f"{c['event_id']}:{c['result']}({c['reason']})" for c in chain)
                print(head + f"  [{reasons}]")
            else:
                print(head)
        prev = state
        now += 1.0
    print(f"\n# 共开口 {spoken} 次 / {len(frames)} 帧")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
