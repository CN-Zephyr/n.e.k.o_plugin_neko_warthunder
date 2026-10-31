# 模式领域边界

更新时间：2026-10-27。当前阶段/证据见 [当前开发状态](当前开发状态.md)。

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

陆战仅在 `domain == "ground"` 下生成以下状态候选：

| 事件 | 来源与确认 | 真实输出策略 |
|---|---|---|
| `ground_laser_warning` | `laser_warning`，由 LWS 状态 1 派生；1 帧进入/2 帧退出 | 沿用现有策略，不进入固定翼 `CRITICAL_RISK` 集合 |
| `ground_crew_loss` | `crew_loss/crew_critical`，连续 2 帧确认 | 乘员/弹药专用开关默认关闭，dry_run 可见 |
| `ground_ammo_low` | 数据层 `ammo_low`，有效正数且连续 2 帧确认 | 同上，只描述一级待发弹 |
| `ground_ammo_empty` | 正数基线后降 0 的 `ammo_empty`，连续 2 帧确认 | 同上，补弹后重新武装 |

专用开关为 `ground_status_real_output_enabled`，同时在仲裁和 Dispatcher 边界执行。关闭时这些候选不能占槽挤掉可播报的接近提醒。激光与弹药条件消失时撤销失效缓冲/重试，不补播旧状态。

炮手/驾驶员仍只读，不生成岗位 Detector；LWS 枚举与乘员、待发弹、稳定器、档位、岗位在面板显示，超过 5 秒或断线/阵亡/回放/载具无效时隐藏旧值。激光不等于确认导弹来袭，待发弹不等于全车余弹。

`ground_target_nearby` 名字中的 ground 指空/直升机任务目标点，**不是陆战占领点事件**。陆战/海战普通 `enemy_nearby` 可在 COMBAT_STRESS 作为交战观察信号放行；空战普通近敌与任务点仍按低优先级门控。

## 直升机只读仪表

概览/诊断仅在 `domain == "heli"` 显示旋翼转速、离地高度 AGL 和升降速度；数据来自既有 processed 映射，负升降速度保留为下降，未知不当零。卡片复用陆战的独立载具采样时效与失效隐藏，不新增轮询、VRS/转速事件或真实输出。实现与已验边界见 [开发记录](直升机只读状态卡-20261027.md)。

## 直升机 VRS 观察

`heli_vrs_risk` 消费 `vrs_warning/vrs_critical`，仅在有新鲜载具采样的直升机存活态产生 dry-run 候选。真实模式在仲裁与 Dispatcher 硬阻断，没有启用开关；不复用固定翼抢占/危急场景。条件解除、来源失效或 critical 降级撤销旧记录，见 [VRS 开发记录](直升机VRS-dry-run-20261027.md)。

## 海战确认域与字段边界

v1.10 源码合同只由有效兵种确认域：air/tank/ship/fleet 白名单在顶层和加工层共享，直升机标记只在 air 下生效。无效/缺失/未知兵种及仅有 Player 图标均为 unknown，不兜底海战，也不凭 aircraft 图标确认固定翼。ship/fleet 只代表已接受的兼容代码，当前游戏字段仍未验。

HTTP 消费侧复核 naval 的有效 ship/fleet 证据；旧 naval 声明缺证据或与其他域冲突时降为 unknown，domain_source 只保留白名单代码。海战/未知域不消费飞行/陆战/直升机仪表、flags/profile；源头不输出跨域加工缓存，未知接近事件两侧清理。乘员和运动信号只用于已有明确语义的域，缺失速度不当静止残骸，舰艇自动重生模型尚未实现。

确认 naval 在概览/诊断显示海战地图卡；unknown 显示“地图态势（载具未确认）”。两者复用成功采样年龄/生命编号、5 秒时效和尺度边界，地图图标不确认舰种。读取卡片不推进检测或发起轮询/LLM/播报，独立 dry-run detector 见下节。字段矩阵见 [二期记录](海战域识别与字段边界-20261027.md)，[一期记录](海战只读地图态势-20261027.md) 保留历史实现。

## 海战地图态势 dry-run

naval_map_contact / naval_air_contact 仅在已确认 naval、存活非回放、有当前生命的新鲜成功地图采样及有效聚合计数时确认。2 次不同成功样本进入，2 次有效消失样本重武装；重复缓存不推进，来源失效、战局/生命变化、计数回退、时钟回退或超过 5 秒的未观测间隔重新确认。

两类事件真实模式在仲裁与 Dispatcher 硬阻断，无启用开关、不抢占；失效图标、旧生命、来源过期/回退撤销缓冲与重试。只表示图标类别出现，不确认敌舰/空袭/锁定或距离，见 [开发记录](海战态势事件-dry-run-20261027.md)。

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

- 海战已有两类地图观察 dry-run 事件；完整安全/真实输出矩阵和舰艇仪表/重生模型仍未完成。
- VRS 已有仅 dry-run 的独立事件；真实播报与旋翼/涡轴其他专项告警仍未开展，不能复用固定翼失速、迎角、超速、低油。
