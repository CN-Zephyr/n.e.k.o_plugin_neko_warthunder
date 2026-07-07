# 模式领域边界

更新时间：2026-07-07

## 目标

插件不能把固定翼空战逻辑套到陆战、海战或直升机。数据层已经提供 `domain` / `vehicle_class` 等分类线索，插件侧也必须保留领域保险丝，防止旧样本、异常帧、第三方回放或数据层回退把空战 flag 混入其他模式。

## 固定翼连续条件事件

以下事件只允许 `BattleState.domain == "air"` 的固定翼空战触发：

- `stall_risk`
- `high_aoa`
- `over_g`
- `low_alt_danger`
- `overspeed`
- `low_fuel`

非空战域，包括 `ground`、`naval`、`heli`、`unknown`，即使带有上述 flag，也必须静默并 reset detector 状态。

`overheat` 暂按通用技术通知保留：它可来自数据层温度 flag 或安全 HUD notice code，但不触发 `CRITICAL_RISK`，也不抢占当前对话。

## 起飞保护

起飞/滑跑保护只允许固定翼空战启用：

- 只在 `domain == "air"` 时读取 `radio_altitude_m` 贴地迟滞。
- 只在 `domain == "air"` 时用起落架 / 滑跑状态压制 `low_alt_danger` 或 `overspeed`。
- 陆战、海战、直升机、未知域不显示也不执行起飞保护。

## 交战压力

`COMBAT_STRESS` 的进入条件按模式分开：

- 空战 / 直升机：受创、持续高 G、近距离空中威胁。
- 陆战：受创、近距离地面目标接触。
- 海战：受创、较长窗口内的近距离水面目标接触。

陆战 / 海战不使用高 G 作为交战压力代理。

## 陆战已接事件

数据层已提供、插件已提升为正式播报候选的陆战事件：

- `ground_laser_warning`：来自 `laser_warning`，提示可能被测距或锁定。
- `ground_crew_loss`：来自 `crew_loss` / `crew_critical`，提示车组受损。
- `ground_ammo_empty`：来自 `ammo_empty`，提示一级弹药打空、装填节奏变慢。
- `ground_ammo_low`：来自 `ammo_low`，提示一级弹药偏少。

这些事件只允许 `domain == "ground"` 触发，且不进入固定翼 `CRITICAL_RISK` 集合。它们的提示词只能描述安全事实，不编敌情、锁定结果、击毁结果、载具损伤或玩家名。

## 已知未完成

- 海战目前没有独立的安全 / 态势事件矩阵。
- 直升机不应复用固定翼失速、迎角、超速、低油；后续如接 VRS 或旋翼/涡轴专项告警，应新增独立事件与话术。
