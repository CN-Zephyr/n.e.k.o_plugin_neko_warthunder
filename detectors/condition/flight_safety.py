"""连续派生检测器（电平 flag → 边沿）：stall / overheat / low_fuel / low_alt / overspeed。

flag 名来自 core/flag_codes.py（接缝集中）。payload 取数据层已派生的数值，仅作"事实行"上下文。
overspeed 消费数据层 v1.6 的 overspeed_warn / overspeed_critical，不在插件侧重算阈值。
"""

from __future__ import annotations

import math
from typing import Any

from ...core.contracts import BattleEvent, BattleState
from ...core.flag_codes import CONDITION_FLAG_GROUPS
from ...core.telemetry_freshness import (
    GROUND_SAMPLE_MAX_AGE_SECONDS,
    ground_indicator_source,
    helicopter_sample_is_fresh,
    legacy_ground_replay_segment,
    legacy_ground_sample_age,
    modern_ground_replay_boundaries,
)
from .._base import ConditionDetector


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _is_fixed_wing_air(s: BattleState) -> bool:
    return (s.domain or "").lower() == "air"


def _is_ground(s: BattleState) -> bool:
    return (s.domain or "").lower() == "ground"


class GroundConditionDetector(ConditionDetector):
    """Advance the existing condition FSM once per successful tank observation."""

    _sample_key: tuple[str | None, int | None, int | float] | None = None
    _sample_time: float | None = None
    _has_source_metadata: bool | None = None
    _replay_segment: tuple[int, int] | None = None
    _replay_boundaries: tuple[int, int, int] | None = None

    def reset(self) -> None:
        super().reset()
        self._sample_key = self._sample_time = None
        self._has_source_metadata = None
        self._replay_segment = None
        self._replay_boundaries = None

    def feed(self, prev: BattleState, cur: BattleState) -> BattleEvent | None:
        if not _is_ground(cur):
            # An offline response can be followed by the same cached legacy frame.
            if self._has_source_metadata is False:
                self.reset_transient()
            else:
                self.reset()
            return None
        source = ground_indicator_source(cur)
        has_metadata = source is not None
        if self._has_source_metadata is not None and self._has_source_metadata != has_metadata:
            self.reset()
        self._has_source_metadata = has_metadata
        replay_segment = None
        if source is not None:
            if not cur.connected or cur.conn_state != "in_battle" or not cur.is_alive():
                self.reset_transient()
                return None
            if source.status == "held":
                self.reset_confirmation()
                return None
            if source.status != "ready":
                self.reset_transient()
                return None
            boundaries = modern_ground_replay_boundaries(cur)
            previous_boundaries = self._replay_boundaries
            self._replay_boundaries = boundaries
            if boundaries is not None and previous_boundaries is not None:
                if boundaries[0] != previous_boundaries[0]:
                    self.reset_transient()
                    self._sample_key = self._sample_time = None
                elif boundaries[2] != previous_boundaries[2]:
                    self.reset_transient()
                elif boundaries[1] != previous_boundaries[1]:
                    self.reset_confirmation()
            key, timestamp = source.key, source.timestamp
        else:
            # Older 8112 responses share the fast snapshot timestamp with the instrument payload.
            age = legacy_ground_sample_age(cur)
            if age is None and not cur.raw:
                return super().feed(prev, cur)
            if (age is None or age >= GROUND_SAMPLE_MAX_AGE_SECONDS or not cur.connected
                    or cur.conn_state != "in_battle" or not cur.is_alive()):
                self.reset_transient()
                return None
            timestamp = cur.timestamp
            key = cur.battle_id, cur.life_index, timestamp
            replay_segment = legacy_ground_replay_segment(cur)
            if replay_segment != self._replay_segment:
                self.reset_transient()
                if (replay_segment is not None and self._replay_segment is not None
                        and replay_segment[0] != self._replay_segment[0]):
                    # A new pass can intentionally rewind the recorded timestamps.
                    self._sample_key = self._sample_time = None
                self._replay_segment = replay_segment
            if replay_segment is not None and cur.raw["meta"].get("replay_ground_held") is True:
                self.reset_transient()
                return None
        previous = self._sample_key
        if previous is not None and key is not None:
            if (key[0] == previous[0] and key[1] is not None and previous[1] is not None and key[1] < previous[1]):
                return None
            if key[:2] == previous[:2] and key[2] <= previous[2]:
                return None
            if (key[:2] != previous[:2] or (timestamp is not None and self._sample_time is not None
                    and not 0 <= timestamp - self._sample_time <= GROUND_SAMPLE_MAX_AGE_SECONDS)):
                self.reset_transient()
        if (source is None and cur.life_key is None and _is_ground(prev)
                and prev.vehicle_type and cur.vehicle_type and prev.vehicle_type != cur.vehicle_type):
            self.reset_transient()
        self._sample_key, self._sample_time = key, timestamp
        event = super().feed(prev, cur)
        if event is not None:
            if source is None:
                event.legacy_ground_life = cur.life_key
                event.legacy_ground_unidentified = cur.life_key is None
                event.legacy_ground_replay_segment = replay_segment
            else:
                event.ground_sample = source.key
                event.ground_replay_boundaries = boundaries
        return event


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
    payload = _drop_none({"domain": s.domain})
    groups = CONDITION_FLAG_GROUPS["overheat"]
    codes = [critical for _, critical in groups if s.flag(critical)]
    if not codes:
        codes = [warning for warning, _ in groups if s.flag(warning)]
    if len(codes) != 1:
        return payload

    code = codes[0]
    fields = ("oil_temp_c",) if code.startswith("oil_") else ("water_temp_c", "head_temp_c", "turbine_temp_c")
    temperatures = {field: value for field in fields if (value := getattr(s, field)) is not None
                    and math.isfinite(value)}
    processed = s.raw.get("processed") if isinstance(s.raw, dict) else None
    alerts = processed.get("alerts") if isinstance(processed, dict) else None
    if isinstance(alerts, list):
        matching = [alert for alert in alerts if isinstance(alert, dict) and alert.get("code") == code]
        if len(matching) > 1:
            return payload
        if matching:
            alert = matching[0]
            source, temperature = alert.get("temp_source"), alert.get("value")
            # Legacy alerts carry a value but may not identify the temperature channel.
            temperatures = {field: value for field, value in temperatures.items()
                            if (source is None or field == source) and type(temperature) in (int, float)
                            and value == temperature}
    if len(temperatures) == 1:
        source, temperature = next(iter(temperatures.items()))
        payload.update(temp_c=temperature, temp_source=source)
    return payload


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
        GroundConditionDetector(
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
        GroundConditionDetector(
            "ground_crew_loss",
            g["ground_crew_loss"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_ground_crew_loss,
            predicate=_is_ground,
        ),
        # 数据层只在本次出生先见正数基线、再从正数降到 0 时锁存 ammo_empty，
        # 补弹回正数即解除；confirm_enter=2 再压一层单帧脏值。
        GroundConditionDetector(
            "ground_ammo_empty",
            g["ground_ammo_empty"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_ground_ammo,
            predicate=_is_ground,
        ),
        # ammo_low 使用本次出生观测到的最大待发弹量，不等同弹架容量或全车余弹。
        GroundConditionDetector(
            "ground_ammo_low",
            g["ground_ammo_low"],
            confirm_enter=2,
            confirm_exit=2,
            payload_fn=_pl_ground_ammo,
            predicate=_is_ground_ammo_low,
        ),
    ]
