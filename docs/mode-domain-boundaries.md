# 模式领域边界

更新时间：2026-07-08

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

数据层提供多类陆战状态，但插件只把真实激光告警提升为播报候选：

- `ground_laser_warning`：来自 `laser_warning`，提示可能被测距或锁定。

乘员减少、岗位失能/补位和一级弹药数量仍保留在 8112 DTO 与面板中，但不生成 Detector 候选，不进入仲裁和猫娘输出。激光告警只允许 `domain == "ground"` 触发，且不进入固定翼 `CRITICAL_RISK` 集合；提示词只能描述安全事实，不编敌情、锁定结果、击毁结果、载具损伤或玩家名。

## 提示词与输出边界

Detector 的 domain gate 只是第一层保险。所有会进入猫娘模型的战雷事件也必须把模式边界带到输出层：

- 事件 payload 应尽量保留 `domain`，不要在 Detector / Arbiter 中丢失。
- `NekoDispatcher.build_prompt()` 对带 `domain` 的事件写入 `当前模式` 合同。
- `push_message.metadata` 同步携带 `domain` 与 `domain_prompt_contract`，便于 host / live monitor / final smoke evidence 复核。
- 常驻 `WT_CONTEXT_INSTRUCTIONS` 明确：如果事件写了"当前模式"，模型必须只按该模式说话；没有写模式时不猜载具类型。

当前模式话术边界：

- `air`：空战 / 飞行；角色是后座或僚机；可用上机、升空、跟上、护住你等固定翼语境。
- `heli`：直升机 / 旋翼机；角色是机组搭档；可用起飞、贴地、悬停、看高度、跟上；不猜固定翼动作。
- `ground`：陆战 / 地面载具；角色是车组搭档；可用上车、出击、车组、装填、掩体、看路；不得串到升空、后座、云霄、机翼、拉杆等固定翼语境。
- `naval`：海战 / 舰艇；角色是舰桥观察员；可用上舰、出航、舰桥、航向、海面；不得串到空战或陆战语境。
- unknown：只做泛化出场招呼和打气，不猜载具类型。

这层边界解决的是“事件已经分域，但模型嘴上串模式”的问题。以后新增事件时，必须同时检查：

- 事件是否携带 `domain`。
- prompt 是否有对应 `当前模式` 合同。
- metadata 是否能反查同一份 domain contract。
- `tests/test_dispatcher_safety.py` 是否覆盖错误域词汇不会出现在目标模式 prompt 中。

## 已知未完成

- 海战目前没有独立的安全 / 态势事件矩阵。
- 直升机不应复用固定翼失速、迎角、超速、低油；后续如接 VRS 或旋翼/涡轴专项告警，应新增独立事件与话术。
