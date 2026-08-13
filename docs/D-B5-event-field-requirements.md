# D-B5｜事件 → 输入字段需求清单（v1 + 已接入 V2 / 多载具域）

> 状态：v0.3（2026-07-10 真机同步）· 范围：v1 主链路 + 已接入的陆战/无线电/V2 态势边界；插件不直接解析 map/PNG
> 用途：① 事件 → 数据层来源(flag/字段) 映射；② DTO 直接采用数据层接口文档
> 关联：数据层 `../data_layer/data_process/后端接口文档.md`（插件内 vendored）

## v0.2 边界更新（汇合后 · 权威，取代下方 v0.1 原始字段假设）

合作者数据层已自带"逐机阈值 → 告警 flags"（`/api/processed`，端口 `:8112`）。据此重画边界（已拍板）：

- **数据层负责**：原始事实（`/api/state`、`/api/indicators`）+ 逐机阈值判定（`/api/processed.flags`/`alerts`/`level`，两级 warning/critical）。
- **我们负责**：消费其 flags 作为"条件已成立"信号；消费 `hud_notices` / `combat.feed` 这类带 id 的边沿事实；只做 边沿 / debounce / 去重 / 迟滞 / re-arm / cooldown / Scenario 门控 / 仲裁 / 提示意图。
- **DTO 不再自定义**：直接采用数据层 `/api/telemetry` 结构（见其 `后端接口文档.md`）。下方 §1~§7 的"原始字段需求"**降级为参考**（仅用于校验数据层字段是否齐全）。

### 事件 → 数据层来源 映射（v1 + V2 已接入部分）

| 我们的事件 | 数据层来源 | 我们做什么 | payload 取值 |
|---|---|---|---|
| `stall_risk` | flags `stall_warning`/`stall_critical` | 边沿+debounce+迟滞+cooldown；不把高 AoA 混成失速播报 | ias_kmh, aoa_deg, radio_altitude_m（若有）, altitude_m |
| `high_aoa` | flags `aoa_high` / `aoa_critical` | 独立飞控告警；不复用失速话术 | aoa_deg, ias_kmh, g_now |
| `over_g` | flags `over_g` / `over_g_critical` | 独立飞控告警；数据层优先按 profile 的 Instructor G 限制计算，缺少时回退 datamine 结构候选 | g_now, ias_kmh, aoa_deg |
| `overspeed` | flags `overspeed_warn` / `overspeed_critical`（数据层 v1.6 已提供，插件侧待验证） | 同上 | ias_kmh, mach |
| `overheat` | flags `engine_overheat`/`engine_overheat_critical`（OR `oil_overheat*`）；或 `hud_notices.feed[].code=engine_overheat/oil_overheat` | flags 走边沿+debounce；hud_notices 按 id 去重（不抢占） | temp_c；或 safe notice code |
| `low_fuel` | flags `fuel_low`/`fuel_critical` | 同上（仅 IN_FLIGHT） | fuel_fraction, fuel_remaining_sec |
| `low_alt_danger` | flags `altitude_low`/`altitude_critical` + `radio_altitude_m`（AGL，优先） | 同上；`altitude_m` 仅作为 MSL/海拔上下文，不作为优先离地判断 | radio_altitude_m, altitude_m, climb_ms |
| `ground_gunner_disabled` | flag `gunner_disabled` | 兼容目录项；数据层保留状态，但插件不注册 Detector、不播报 | gunner_state, domain |
| `ground_driver_disabled` | flag `driver_disabled` | 兼容目录项；数据层保留状态，但插件不注册 Detector、不播报 | driver_state, domain |
| `spawn` | `state` not_in_battle→in_battle / 新 `vehicle_type` | 边沿一次 | vehicle_type |
| `you_died` | `combat.feed[].is_my_death == true` | 已播报 owned id 去重；同 id 后补 ownership 可补触发；不回退到 `vehicle_valid` 死亡播报 | cause, killer_name, killer_vehicle |
| `you_killed` | `combat.feed[].is_my_kill == true` | 已播报 owned id 去重；同 id 后补 ownership 可补触发；多杀合并 | victim, victim_vehicle |
| `battle_end` | `mission_status` / `state` | 边沿一次 | result, my{kills,deaths} |
| `enemy_nearby` | `proximity.events[]` | V2：按 id 去重；按域门控，空战普通近敌是低优先级，陆战/海战近敌可作为交战观察信号 | distance_m, compass, clock, target_type, domain |
| `air_threat_nearby` | `proximity.events[].is_air == true` OR `situation.nearest_air_threat` / `situation.enemies[]` 空中目标进入 5000m | V2：边沿事实按 id 去重，连续态势按距离段/钟点去重；可在 IN_FLIGHT / COMBAT_STRESS 下提示 | distance_m, compass, clock, relative_deg |
| `enemy_on_six` | `proximity.events[]` OR `situation.enemies[]` 中 `clock in 5/6/7` 或后向 `relative_deg` 且进入 5000m | V2：低置信后方威胁，不等同完整尾随判定 | distance_m, clock, relative_deg |
| `tailing_risk` | 连续近距离后方 `proximity.events[]` OR 连续近距离后方 `situation.enemies[]` | V2+：保守持续后方威胁；不是完整 `being_tailed` | distance_m, clock, relative_deg |
| `player_radio_command` | `chat[]` + `combat.self.source=manual` | 只接收手动身份匹配的自己发出的固定无线电口令；按 chat id 去重；不把 sender/msg/raw text 放进事件 payload | command, point, domain, source |

### 本次拍板
- **overspeed → 合作者补进 `vehicle_profiles`**（never-exceed 逐机），我们消费其 flag。
- **steep_dive → v1 删除**（与 low_alt/overspeed 重叠、最弱、数据层也没做；留 v2）。

### 给合作者的 TODO（汇合产出）
- `overspeed_warn` / `overspeed_critical` 已由数据层 v1.6 提供；2026-06-23 真机 dry_run 已验证字段名、触发节奏和 Arbiter 优先级基础链路。
- `combat.feed`、`hud_notices`、ownership flag 已由数据层 v1.6 提供；插件侧已用真机 dry_run 验证 owned kill/death 字段可出现。2026-06-28 发现 `you_killed` 在 `CRITICAL_RISK` 下会被旧策略 scenario-gated，现已改为延迟保留并在危急解除后补播；后续仍需复测 id 单调性和 T-Safety prompt 合同。
- `/api/identity` 已作为 player_name 注入方式；插件侧 Hosted UI/context/action seam 已完成，2026-06-23 真机已验证它能驱动 `combat.self.source=manual` 与 `is_my_kill` / `is_my_death` owned 路径。
- 固定无线电互动已消费 `/api/telemetry.chat[]`，且 2026-07-10 已用两条自己发送的固定无线电完成真机 dry-run：chat id 递增、sender 与手动 identity 匹配、`进攻 D 点` 被标准化为 `attack_point/D`，raw sender/msg 未进入 payload/prompt。仍需由队友发送同口令，补“只接收自己”的反例验证。
- 固定口令标准化已覆盖 `收到 -> affirmative`、`拒绝 -> negative`、`干得好/干得漂亮 -> well_done`；仍只处理手动 identity 匹配的自己消息。
- 2026-07-10 陆战真机确认：`crew_current/crew_total` 可作为乘员损失事实；岗位字段不是布尔值。数据层现按 `0` 正常、`1` 无人补位、`2` 正在补位处理，`3` 只透传。
- 数据层已把 LWS 收紧为仅 `lws == 1` 告警，并为一级弹药增加正数基线、负数无效处理和同局重生重置；离线回归 `457 passed`，下一步是真机 dry-run 复验。
- 输出策略进一步收缩：乘员、岗位和一级弹药只作为 DTO/面板事实，不生成猫娘播报候选；陆战状态播报只保留真实激光告警。

### 待你确认
- **两级 severity**：数据层已给 warning/critical 两级。建议顺势采用两级（critical→高 severity+可抢占；warning→中 severity），**推翻早期"v1 单级"暂定**。待你点头。

---

## v1 核心原则

v1 的核心**不是“敌情感知”**，而是先做 **飞行安全 + 发动机状态 + 生命周期 + 带 id 的离散事件（combat.feed / hud_notices）**。

v1 事件范围（9 个）：低速/失速、超速、过热、低油、低空危险、出生、死亡、击杀、战斗结束。`steep_dive` 已删除，留待 v2 视真机数据再评估。

“敌机接近”已在 V2 通过数据层聚合后的 `proximity.events` 边沿事实和 `situation.enemies` 连续空中敌方几何接入；保守的持续后方威胁 `tailing_risk` 已通过短窗连续近距离后方事件/帧接入。真正的高置信 `being_tailed` 仍暂缓，因为它需要更可靠的相对速度、持续性与误判控制。

## 0. 关键决策（已确认）

1. **“敌机接近 / 被敌机尾随”从 v1 砍掉，标记 v2。** 现在 V2 已消费数据层聚合后的 `proximity.events`，但插件仍不直接解析 map；完整 `being_tailed` 仍暂缓。见第 5 节。
2. **`/mission.json` 纳入必需采集集合。** 生命周期/场景判断只靠 `/state.valid` 翻转太不稳，battle_end / spawn / DEAD 或 OUT_OF_BATTLE 需要 mission 作为交叉确认；`you_died` 事件仍以 `combat.feed[].is_my_death` 为主。

## 1. 字段来源约定（键名均待抓包确认）

- 运动学（高度/空速/马赫/迎角/G/垂速）：以 `/state` 为准（键带单位、语义清晰）。
- 载具身份/航向：`/indicators`（`type` / `army` / `compass`）。
- 姿态（俯仰/横滚）：`/indicators`（`tangage` / `bank`）。
- 发动机温度/油量/油门：`/state`（`water temp 1, C` 等）。
- 战斗离散事件：`/api/telemetry.combat.feed[]`（带递增 `id`、`is_my_kill`、`is_my_death`、`involves_me` 等 ownership 字段）。
- HUD 技术通知：`/api/telemetry.hud_notices.feed[]`（只消费安全 code，不把 raw 文本进 prompt）。
- 生命周期：`/state.valid` + `/indicators.type` + `/mission.json`。
- `/state` 与 `/indicators` 字段重叠（都有速度/高度/温度）：D-A5 反推时须为每个信号指定**唯一权威端点**，不要两头取。

---

## 2. A 组 · 连续派生事件（StateEvaluator 产出）

### A1 低速 / 接近失速 `stall_risk`
- 类型：连续派生
- 必须字段：`IAS, km/h`、`AoA, deg`（均 `/state`）
- 推荐字段：`H, m`、`Vy, m/s`、`Ny`、`flaps, %`、`gear, %`、`throttle 1, %`
- 缺字段降级：无 `AoA` → 用 `IAS`+`Vy`（下沉）+高油门粗判（误判↑）；无 `IAS` → 砍
- 抓包要求：“接近失速”持续若干秒多帧采样，记录进入瞬间；同时采降落进近样本作为反例；标注载具
- 误判风险：高——失速速度逐机不同；`AoA` 单帧抖动需 debounce；降落低速属正常

### A2 超速 `overspeed`
- 类型：连续派生
- 必须字段：`IAS, km/h`（`/state`）
- 推荐字段：`M`、`TAS, km/h`、`H, m`、`flaps, %`、`gear, %`（放襟翼/起落架时超速更易撕裂）
- 缺字段降级：有 `IAS` 即可粗做；无 `IAS` → 砍
- 抓包要求：高速平飞 + 俯冲增速样本各采；标注是否喷气
- 误判风险：中——never-exceed 逐机不同，喷气/螺旋桨阈值差异大

### A3 发动机过热 `overheat`
- 类型：连续派生
- 必须字段：`water temp 1, C` 或 `oil temp 1, C`（`/state`；喷气可能是 `head temp, C`）
- 推荐字段：`throttle 1, %`、`RPM 1`、多发各缸温度、温度时间趋势（持续 N 秒）
- 缺字段降级：有任一温度即可；全无 → 砍
- 抓包要求：分别采液冷/气冷/喷气三类样本，确认温度字段名与数量（多发有 ` 1`/` 2` 后缀）
- 误判风险：中——红线逐机不同；不同发动机看不同温度字段

### A4 低油 `low_fuel`
- 类型：连续派生
- 必须字段：`Mfuel, kg` + `Mfuel0, kg`（`/state`，算 fuel_frac）
- 推荐字段：耗油速率（历史差分）、滞空时间
- 缺字段降级：有 `Mfuel` 无 `Mfuel0` → 只能用绝对值粗判（差）；两者齐备最好
- 抓包要求：记录满油与低油两帧，确认两个字段都在
- 误判风险：低——量较确定；“多少算低”是产品口味，非数据问题

### A5 低空危险 `low_alt_danger`
- 类型：连续派生
- 必须字段：`H, m`、`Vy, m/s`（`/state`，负=下降）
- 推荐字段：`IAS, km/h`、`tangage`（俯仰）、`AoA, deg`、`gear, %`（降落低空属正常）
- 缺字段降级：有 `H`+`Vy` 即可；只有 `H` → 用历史差分算下降率（更糙）
- 抓包要求：低空掠地 + 正常降落进近样本各采
- 误判风险：高且结构性——`/state.H` / `altitude_m` 是**海拔高度，不是离地高度（AGL）**；地形起伏会致误判。若数据层提供 `radio_altitude_m` 或 `indicators.radio_altitude`，插件侧必须优先用 AGL；没有 AGL 时才把 MSL 作为降级上下文，并接受山区误判。

### ~~A6 高速俯冲 `steep_dive`~~（v1 已删除）
- 结论：与 `overspeed` / `low_alt_danger` 重叠，且容易把正常战术俯冲误判成告警。
- v1 不实现、不适配 DTO、不进入 Arbiter；后续如真机样本证明需要预测性拉起，再作为 v2 重新评估。

---

## 3. B 组 · combat.feed 离散事件

> 共同最大难点已经从“插件侧文本匹配”转为“数据层 ownership flag 是否稳定”。v1.6 中 `combat.feed[]` 应提供 `is_my_kill` / `is_my_death` / `involves_me`，插件侧只消费这些布尔字段，不再解析 raw hudmsg 文本来判断关于我。

### B1 击杀 `you_killed`
- 类型：combat.feed 离散
- 必须字段：`combat.feed[].id`、`combat.feed[].is_my_kill == true`
- 推荐字段：`victim`、`victim_vehicle`、`victim_is_ai`、`assist_name`
- 缺字段降级：不可降级——无 `is_my_kill == true` 即无此事件；不回退到 raw hudmsg 文本匹配
- 抓包要求：采多条真实击杀/助攻文本并确认 `combat.feed` id 单调递增、`is_my_kill` 只在我的击杀时为 true；2026-06-23 已观察到 `is_my_kill=true` 正向路径，`SPAWNING` gate 问题已修复；2026-06-28 又补 `CRITICAL_RISK` 延迟保留策略；2026-07-05 修复同一 feed id 从未归属后补为 `is_my_kill=true` 时不补触发的问题，下一轮需复测危急期间击杀不会抢播也不会丢失
- 误判风险：中——主要取决于数据层 ownership flag 与 `/api/identity` seam；插件侧不再承担多语言文本解析。手动 identity seam 已有真机正向证据。

### B2 被击落 / 死亡 `you_died`
- 类型：combat.feed 离散（进入 DEAD 的主事件）
- 必须字段：`combat.feed[].id`、`combat.feed[].is_my_death == true`
- 推荐字段：`killer` / `killer_name`、`killer_vehicle`、`action` / `cause`、`killer_is_ai`
- 缺字段降级：不可降级——无 `is_my_death == true` 即无死亡事件；不回退到 `valid` 翻转播报死亡
- 抓包要求：采“被击落”“自己坠机”“主动离场/切观战”三类样本，确认只有真实死亡时 `is_my_death` 为 true；2026-06-23 已观察到 `is_my_death=true` 与 `you_died` dry_run 正向路径
- 误判风险：中——主要取决于 ownership flag；插件侧避免 valid 翻转导致离场/观战误报。手动 identity seam 已有真机正向证据。

---

## 4. C 组 · 生命周期事件

### C1 出生 / 进入战斗 `spawn`
- 类型：生命周期
- 必须字段：`/state.valid` false→true、`/indicators.type`（载具出现/变化）、`/mission.json` 状态
- 推荐字段：`/indicators.army`
- 缺字段降级：无 mission 时仅用 `valid` 翻转可粗做（区分能力下降）
- 抓包要求：采“加载完成入场”“死亡后重生”“中途换载具”三种过渡的连续帧 + 对应 mission.json
- 误判风险：中——加载/换机/重生都触发 valid 或 type 变化，需组合 mission 区分

### C2 战斗结束 `battle_end`
- 类型：生命周期 / hudmsg events
- 必须字段：`/mission.json` status（win/fail/left）或 `/hudmsg` `events[]`（对局结束）
- 推荐字段：结算/胜负信息
- 缺字段降级：无 mission → 用 `valid` 长时间 false + 无在战 兜底（糙）
- 抓包要求：采一局完整结束（胜/负各一）的 mission.json 与 hudmsg events
- 误判风险：中——区分“这局结束”vs“我死了但局还在”

### C3 存活态下降（valid 路径）
- 类型：Scenario 存活态信号（不直接产 `you_died`）
- 必须字段：`/state.valid` true→false
- 推荐字段：`combat.feed[].is_my_death`、`mission_status`（是否仍在对局）
- 缺字段降级：只允许用于 `DEAD` / `OUT_OF_BATTLE` 等 Scenario 判断，不允许降级成死亡播报
- 抓包要求：采“被击落瞬间”“主动离场”“切观战”三种 valid 翻转，确认哪些只应影响 Scenario
- 误判风险：高——valid 变 false 的原因不止死亡，因此不作为 `you_died` 事件源

---

## 5. D 组 · V2 接近 / 目标态势感知

### D1 敌机接近 `enemy_nearby` — v2
- 当前实现：插件不直接消费 `/map_obj.json` / `/map_info.json`；普通 `enemy_nearby` 消费数据层在 `/api/telemetry.proximity.events[]` 中给出的 edge 事实，空中威胁/后方威胁同时消费 `proximity.events[]` 与 `/api/telemetry.situation.enemies[]` / `nearest_air_threat` 连续安全摘要。
- 去重：按 `id` 单调去重；同一 proximity id 不重复播。
- 输出：只使用 safe metadata（距离、方位、钟点、类别），不复读 raw 文本或玩家名。
- 事件拆分：普通 proximity 目标为 `enemy_nearby`，空中目标为 `air_threat_nearby`，后向钟点 / 相对角度为 `enemy_on_six`，连续近距离后方 proximity 事件或 situation 帧保守升级为 `tailing_risk`。
- 门控：`enemy_nearby` 按域分流。空战/未知域下仍是低优先级 map awareness，COMBAT_STRESS 下抑制；陆战/海战域下视为近敌交战观察信号，COMBAT_STRESS 下可放行。脱战压力不读 raw 文本：空战/直升机用 `situation.nearest_air_threat` / `situation.enemies[]` + `proximity.thresholds_m.vs_air`，陆战/海战用 `situation.enemies[]` + `proximity.thresholds_m.vs_ground`。`air_threat_nearby` / `enemy_on_six` / `tailing_risk` 可进入 IN_FLIGHT / COMBAT_STRESS 队列；CRITICAL_RISK / DEAD / SPAWNING 仍按 Arbiter 压制。
- 样本状态：2026-06-20 样本经 `sample_replay` 合并 side-stream proximity 和连续 `situation.enemies` 后，已有 `proximity_events=5317`、`proximity_air_events=5300`、`proximity_rear_events=49`、`situation_rear_air_threat_live_items=1906`，并可触发 `enemy_on_six=149` / `tailing_risk=44`；目标点仍缺 3000m 内触发样本。

### D2 任务目标点接近 `ground_target_nearby` — v2
- 当前实现：插件消费 `/api/telemetry.situation.ground_targets[]`，只取最近且在阈值内的任务目标点。
- 去重：按 `kind` / `grid` / 距离段去重，避免飞向同一目标时刷屏。
- 适用范围：仅空军/直升机域使用；陆战/海战不把任务点态势转成播报。
- 输出：只使用 safe metadata（目标类型、网格、距离、方位），不复读 `label` 或 raw 文本。
- 门控：`ground_target_nearby` 是低优先级 map awareness，IN_FLIGHT 可进入窗口；COMBAT_STRESS 下抑制；CRITICAL_RISK / DEAD / SPAWNING 仍按 Arbiter 压制。
- 样本状态：2026-06-20 样本已有 ground target item，但尚未形成近距离触发样本；下一轮真机对地任务中补测。

### D3 持续后方威胁 `tailing_risk` / 被敌机尾随 `being_tailed` — v2+
- 已完成：`tailing_risk` 作为保守升级事件，在短窗内连续出现近距离后方 `proximity.events` 或连续 `situation.enemies` 后方帧时触发。它只说明“后方威胁持续接近”，不声明完整尾随判定。
- 仍暂缓：高置信 `being_tailed` 需要敌我相对位置 + 速度矢量 + 持续性。即便有 map，误判率也高，继续不作为当前事件。

---

## 6. 给合作者的采集清单（字段并集 = 直接照此抓）

- `/state` 必采键（待确认）：`valid`、`H, m`、`IAS, km/h`、`TAS, km/h`、`M`、`AoA, deg`、`Ny`、`Vy, m/s`、`Mfuel, kg`、`Mfuel0, kg`、`water temp 1, C`、`oil temp 1, C`、`head temp, C`、`throttle 1, %`、`RPM 1`、`flaps, %`、`gear, %`（多发注意 ` 2`/` 3` 后缀）
- `/indicators` 必采键：`valid`、`type`、`army`、`compass`、`tangage`、`bank`、`speed`（与 state 对比取舍）
- `combat.feed[]`：带递增 `id`、`is_my_kill`、`is_my_death`、`involves_me`、`killer/victim`、载具与 AI 标记；实测新对局 id 是否归零或单调。
- `hud_notices.feed[]`：带递增 `id`、稳定 `code`、`severity`；raw 文本只进 audit/debug，不进 prompt。
- `/mission.json`：必采（C 组生命周期交叉确认）
- 玩家自我身份：通过 `/api/identity` 设置/清除权威昵称，并记录它如何反映到 `combat.self` 与 ownership flag。
- 分载具类型各采一套：液冷螺旋桨 / 气冷螺旋桨 / 喷气（温度与发动机字段差异大）

## 7. 反推 DTO 的提示

- 上述“必须字段”的并集 = `TelemetrySnapshot` 的最小事实字段集候选。
- A 组全部是派生，**不进** `TelemetrySnapshot`（只进 BattleState / BattleEvent）。
- 待 D-A5 解决：① `/state` vs `/indicators` 重叠信号指定唯一权威端点；② 多发/机型字段差异 → snapshot 用“发动机数组”还是“固定 ` 1`”要定型。
