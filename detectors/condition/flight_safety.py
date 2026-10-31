"""连续派生检测器（电平 flag → 边沿）：stall / overheat / low_fuel / low_alt / overspeed。

flag 名来自 core/flag_codes.py（接缝集中）。payload 取数据层已派生的数值，仅作"事实行"上下文。
overspeed 消费数据层 v1.6 的 overspeed_warn / overspeed_critical，不在插件侧重算阈值。
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import BattleState
from ...core.flag_codes import CONDITION_FLAG_GROUPS
from ...core.telemetry_freshness import helicopter_sample_is_fresh
from .._base import ConditionDetector


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _is_fixed_wing_air(s: BattleState) -> bool:
    return (s.domain or "").lower() == "air"


def _is_ground(s: BattleState) -> bool:
    return (s.domain or "").lower() == "ground"


def _is_fresh_helicopter(s: BattleState) -> bool:
    # Detector 使用该快照的观察时刻，兼容离线样本时钟；仲裁时再按运行时刻复验。
    return helicopter_sample_is_fresh(s, s.timestamp + (s.age_seconds or 0.0))


def _pl_stall(s: BattleState) -> dict[str, Any]:
    return _drop_none(
        {
            "domain": s.domain,
            "ias_kmh": s.ias_kmh,
            "aoa_deg": s.aoa_deg,
            "altitude_m": s.altitude_m,
            "radio_altitude_m": s.radio_altitude_m,
        }
    )


def _pl_high_aoa(s: BattleState) -> dict[str, Any]:
    return _drop_none({"domain": s.domain, "aoa_deg": s.aoa_deg, "ias_kmh": s.ias_kmh, "g_now": s.g_now})


def _pl_over_g(s: BattleState) -> dict[str, Any]:
    return _drop_none({"domain": s.domain, "g_now": s.g_now, "ias_kmh": s.ias_kmh, "aoa_deg": s.aoa_deg})


def _pl_overheat(s: BattleState) -> dict[str, Any]:
    temperatures = (
        ("water_temp_c", s.water_temp_c),
        ("head_temp_c", s.head_temp_c),
        ("turbine_temp_c", s.turbine_temp_c),
        ("oil_temp_c", s.oil_temp_c),
    )
    source, temp = next(((name, value) for name, value in temperatures if value is not None), (None, None))
    return _drop_none({"domain": s.domain, "temp_c": temp, "temp_source": source})


def _pl_low_fuel(s: BattleState) -> dict[str, Any]:
    return _drop_none({"domain": s.domain, "fuel_fraction": s.fuel_fraction})


def _pl_low_alt(s: BattleState) -> dict[str, Any]:
    return _drop_none(
        {
            "domain": s.domain,
            "altitude_m": s.altitude_m,
            "radio_altitude_m": s.radio_altitude_m,
            "climb_ms": s.climb_ms,
            "ias_kmh": s.ias_kmh,
        }
    )


def _pl_overspeed(s: BattleState) -> dict[str, Any]:
    return _drop_none({"domain": s.domain, "ias_kmh": s.ias_kmh, "mach": s.mach})


def _pl_ground_laser(s: BattleState) -> dict[str, Any]:
    return _drop_none({"domain": s.domain})


def _pl_helicopter_vrs(s: BattleState) -> dict[str, Any]:
    return {"domain": "heli"}


def _pl_ground_crew_loss(s: BattleState) -> dict[str, Any]:
    return _drop_none({"domain": s.domain, "crew_current": s.crew_current, "crew_total": s.crew_total})


def _pl_ground_ammo(s: BattleState) -> dict[str, Any]:
    return _drop_none({"domain": s.domain, "ammo_first_stage": s.ammo_first_stage})


def _is_ground_ammo_low(s: BattleState) -> bool:
    # 阈值由数据层负责；这里只排除无效计数和与打空矛盾的输入。
    return bool(_is_ground(s) and s.connected and s.conn_state == "in_battle"
                and s.is_alive() and s.ammo_first_stage is not None
                and s.ammo_first_stage > 0 and not s.flag("ammo_empty"))


# 危急持续期心跳间隔，默认对齐 critical_preempt_cooldown_seconds=5。
#
# 这个值必须落在一个很窄的区间里，样本实测给出了两端：
#  · 下界——要 ≥ 抢占冷却，否则重发落在冷却窗内被 Arbiter 丢弃，白白消耗掉这一次机会；
#  · 上界——要 ≤ 危急条件的典型持续时长，否则条件早就结束了才轮到重发。
#    实测两段完整对局(2303 / 4969 帧)里 critical 段最长只有 6.9s
#    (low_alt_danger)，stall_risk 6.3s、high_aoa 3.4s、low_fuel 3.0s。
#
# 取 8s 时该机制在真实飞行中永不触发；取 5s 可救回样本里真实出现过的一次
# "低空告警刚播完 5.9s 后进入失速、整段无提示"。已播报过的同一条仍会被
# Dispatcher 的 repeat-collapse(30s 窗)折叠，因此不会刷屏。
_CRITICAL_HEARTBEAT_SECONDS = 5.0


def build_condition_detectors(
    critical_heartbeat_seconds: float = _CRITICAL_HEARTBEAT_SECONDS,
) -> list[ConditionDetector]:
    g = CONDITION_FLAG_GROUPS
    heartbeat = max(0.0, float(critical_heartbeat_seconds or 0.0))
    return [
        ConditionDetector(
            "stall_risk",
            g["stall_risk"],
            confirm_enter=2,
            confirm_exit=3,
            payload_fn=_pl_stall,
            predicate=_is_fixed_wing_air,
            critical_heartbeat_seconds=heartbeat,
        ),
        ConditionDetector(
            "high_aoa",
            g["high_aoa"],
            confirm_enter=1,
            confirm_exit=2,
            payload_fn=_pl_high_aoa,
            predicate=_is_fixed_wing_air,
            critical_heartbeat_seconds=heartbeat,
        ),
        ConditionDetector(
            "over_g",
            g["over_g"],
            confirm_enter=1,
            confirm_exit=2,
            payload_fn=_pl_over_g,
            predicate=_is_fixed_wing_air,
            critical_heartbeat_seconds=heartbeat,
        ),
        ConditionDetector(
            "low_alt_danger",
            g["low_alt_danger"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_low_alt,
            predicate=_is_fixed_wing_air,
            critical_heartbeat_seconds=heartbeat,
        ),
        ConditionDetector(
            "overspeed",
            g["overspeed"],
            confirm_enter=2,
            confirm_exit=3,
            payload_fn=_pl_overspeed,
            predicate=_is_fixed_wing_air,
            critical_heartbeat_seconds=heartbeat,
        ),
        ConditionDetector("overheat", g["overheat"], confirm_enter=3, confirm_exit=4, payload_fn=_pl_overheat),
        ConditionDetector(
            "low_fuel",
            g["low_fuel"],
            confirm_enter=1,
            confirm_exit=2,
            payload_fn=_pl_low_fuel,
            predicate=_is_fixed_wing_air,
            # EVENT_CATALOG 给 low_fuel 的 cooldown 是 -1（每局一次）；油量在阈值
            # 附近抖动时不该反复催返航。warning→critical 升级不受影响。
            once_per_battle=True,
        ),
        ConditionDetector(
            "ground_laser_warning",
            g["ground_laser_warning"],
            confirm_enter=1,
            confirm_exit=2,
            payload_fn=_pl_ground_laser,
            predicate=_is_ground,
        ),
        ConditionDetector(
            "heli_vrs_risk",
            g["heli_vrs_risk"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_helicopter_vrs,
            predicate=_is_fresh_helicopter,
        ),
        # 乘员数与一级弹药有真机录像佐证（2026-07-22 豹2A7V：4→2→1、15→9→12）。
        # 检测始终运行以便 dry_run/时间线可观察；真实输出由 Dispatcher 按
        # ground_status_real_output_enabled 门控，默认关闭。
        # 乘员降到 1 时数据层同帧进入阵亡态并清空告警，因此实际只会以
        # crew_loss（部分减员）进入，不与 you_died 的 ground_crew 兜底重复。
        ConditionDetector(
            "ground_crew_loss",
            g["ground_crew_loss"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_ground_crew_loss,
            predicate=_is_ground,
        ),
        # 数据层只在本次出生先见正数基线、再从正数降到 0 时锁存 ammo_empty，
        # 补弹回正数即解除；confirm_enter=2 再压一层单帧脏值。
        ConditionDetector(
            "ground_ammo_empty",
            g["ground_ammo_empty"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_ground_ammo,
            predicate=_is_ground,
        ),
        # ammo_low 使用本次出生观测到的最大待发弹量，不等同弹架容量或全车余弹。
        ConditionDetector(
            "ground_ammo_low",
            g["ground_ammo_low"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_ground_ammo,
            predicate=_is_ground_ammo_low,
        ),
    ]
