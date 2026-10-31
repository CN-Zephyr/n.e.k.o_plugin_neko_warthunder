# D-B2｜BattleEvent 字典与当前事件边界

> 更新：2026-10-27。当前事件数值、类别、冷却与注册以 `core/contracts.py` 和 Detector 构造函数为准；下文逐事件原始阈值是早期设计参考，插件实际只消费数据层 flags。当前能力、输出闸和真机缺口见 [统一状态](当前开发状态.md) 与 [D-B5](D-B5-event-field-requirements.md)。
> 用途：定义 v1 的**统一语义事件模型**——理解层（StateEvaluator）唯一对外产出口
> 关联：D-B5 v0.2（事件→数据层来源映射）/ D-B1（Scenario 门控）/ D-B3（ConditionDetector）/ D-B4（仲裁）

## v0.2 边界更新（汇合后）

- 已重画边界：消费数据层 `/api/processed.flags` 作为"条件已成立"信号，详见 **D-B5 v0.2 映射表（权威）**。本字典的 severity/priority/cooldown/scenario/抢占/去重仍是**我们这层**的职责，不变。
- **`steep_dive` 已删除**（v1 砍、留 v2）：本文相关条目作废。
- **`overspeed` 来源改为数据层 flag `overspeed_warn` / `overspeed_critical`**，不再由我们算阈值。数据层 v1.6 已提供，插件侧已接入；后续重点是真机验证触发节奏、critical 档位和 Arbiter 抢占语义。
- **`overheat` 除数据层 flag 外，也可消费 `hud_notices.feed[].code=engine_overheat/oil_overheat`**。HUD notice 只使用安全 code，不把 raw 文本带入 prompt；`powertrain_failure` 暂不直接提升为播报事件。
- 各连续事件"来源 Detector/信号"统一改读上游 flag（见 D-B3 v0.2 / D-B5 映射）；下方各条仍写原始字段，仅作 payload/语义参考。
- **两级 severity 已实现**：warning/critical 取事件目录的两个 severity 档；只有事件本身具备抢占资格时才可抢占，不以 critical 字样单独判断。

## 0. 字段语义约定（先钉死，免得各事件理解不一）

- **BattleEvent 是统一语义事件模型**：连续派生 / 带 id 的离散事实（combat.feed / hud_notices）/ 生命周期 三类来源，**产出后形状一致**，下游只认它。`TelemetrySnapshot` 不进字典（它是输入，不是事件）。
- **severity（0–10）**：事件内部的紧迫档位；抢占资格由事件目录的 preempt 与 level 共同决定，`CRITICAL_RISK` 由明确的危急 flag 集合驱动，不能只用 severity 数字判断。
- **priority（0–10）**：同一仲裁窗口内多个候选竞争时谁先开口（高者胜）。与 severity 相关但不等同：生命周期事件可能 severity 低、priority 高（"必须说"）。
- **是否允许抢占**：true = 可绕过全局限流/冷却**立即开口**（仅留给生死危急与阵亡）；false = 严格受限流约束。
- **cooldown**：同一事件的冷却基准；负值的去重语义由各 Detector 兑现，不统一解释成每局一次。`low_fuel` 使用 `once_per_battle`，spawn/death/battle-end 则依据各自生命周期和事件游标；Arbiter 只在 `cd > 0` 时检查时间冷却。
- **re-arm 条件**：退出后"算作新一次事件"需满足的条件——连续派生类需退出阈值保持一段时间（配合迟滞）；离散类按新的 feed/notice id / 新一次生命周期跳变。
- **payload**：该事件**携带的派生上下文（具体标量子集）**，供 handler 拼"事实行"。**不是整个 snapshot**，只是这次事件相关的几个派生值。
- **提示意图**：只描述"要让猫娘传达什么"，Detector 不写具体台词；最终输出由 dispatcher 统一管理。危急动作类默认走 bounded `respond`，由宿主生成受短播报合同约束的回复并进入 TTS；只有显式兼容开关开启时才由插件以 `blind+plugin` 固定短句直出。开局、击杀/阵亡、过热、低油、普通接近、目标点和结算默认同样走 bounded `respond`，让猫娘在事实边界内自行组织短句。
- 当前数值已由事件目录采用；早期逐事件阈值描述仅作设计参考，不能用来重算数据层告警。

## 1. 当前事件目录数值（2026-10-27）

以下从当前 `core/contracts.py` 对照整理；cooldown 是标准频率基准，实际仍受场景、开关、频率、新鲜度、全局限流与投递结果约束。目录中存在条目不等于已注册 Detector。

| event_id | category | severity warning/critical | priority | preempt | cooldown 基准 |
|---|---|---|---|---|---|
| `stall_risk` | `safety_critical` | 2/8 | 9 | 可抢占 | 15s |
| `high_aoa` | `safety_critical` | 2/8 | 9 | 可抢占 | 10s |
| `over_g` | `safety_critical` | 2/8 | 9 | 可抢占 | 10s |
| `low_alt_danger` | `safety_critical` | 7/9 | 9 | 可抢占 | 10s |
| `overspeed` | `safety_critical` | 6/7 | 8 | 可抢占 | 15s |
| `overheat` | `safety_important` | 5/6 | 6 | 否 | 30s |
| `low_fuel` | `safety_minor` | 3/4 | 4 | 否 | 检测器语义去重 |
| `ground_laser_warning` | `safety_important` | 6/7 | 7 | 否 | 10s |
| `ground_crew_loss` | `safety_important` | 5/7 | 6 | 否 | 20s |
| `ground_gunner_disabled` | `safety_important` | 5/5 | 6 | 否 | 20s |
| `ground_driver_disabled` | `safety_important` | 5/5 | 6 | 否 | 20s |
| `ground_ammo_empty` | `safety_important` | 5/5 | 5 | 否 | 25s |
| `ground_ammo_low` | `safety_minor` | 2/2 | 3 | 否 | 45s |
| `heli_vrs_risk` | `safety_important` | 5/7 | 6 | 否 | 20s |
| `ground_target_nearby` | `map_awareness` | 2/2 | 2 | 否 | 35s |
| `enemy_nearby` | `map_awareness` | 2/2 | 2 | 否 | 25s |
| `air_threat_nearby` | `map_awareness` | 3/3 | 3 | 否 | 20s |
| `enemy_on_six` | `map_awareness` | 4/4 | 4 | 否 | 20s |
| `tailing_risk` | `map_awareness` | 5/5 | 5 | 否 | 25s |
| `free_text_activity` | `map_awareness` | 1/1 | 1 | 否 | 25s |
| `player_radio_command` | `player_command` | 2/2 | 3 | 否 | 10s |
| `you_killed` | `combat_kill` | 3/3 | 5 | 否 | 8s |
| `you_died` | `lifecycle` | 8/8 | 10 | 可抢占 | 检测器语义去重 |
| `spawn` | `lifecycle` | 1/1 | 5 | 否 | 检测器语义去重 |
| `battle_end` | `lifecycle` | 1/1 | 6 | 否 | 检测器语义去重 |

- 抢占仍需事件 `level == "critical"`；激光 critical 不因等级自动进入固定翼危急集合。
- `ground_gunner_disabled` / `ground_driver_disabled` 是兼容目录，当前不注册 Detector。
- 乘员减员、待发弹偏少/打空已注册，真实输出默认关闭；激光沿用原策略。free-text 与受限 V2 输出仍有独立闸门。
- `heli_vrs_risk` 仅 dry-run，真实模式在仲裁与 Dispatcher 硬阻断，无启用开关、不进入危急集合。参数用于离线观察，见 [VRS 开发记录](直升机VRS-dry-run-20261027.md)。
- 数据源、确认帧数与域边界见 [D-B5 当前映射](D-B5-event-field-requirements.md)，剩余真机验收见 [统一状态](当前开发状态.md)。

## 2. 早期逐事件语义参考（不作为当前阈值或触发配置）

### A 组 · 连续派生

#### `stall_risk` 低速/接近失速
- 中文说明：空速过低 + 大迎角，濒临失速。
- 来源 Detector / 信号：`stall_risk` detector（`IAS, km/h` + `AoA, deg`，辅以 `Vy`/`H`/`flaps`/`gear`）。
- 触发条件摘要：低 IAS 且高 AoA（进入阈值），经 confirm 窗口；降落（gear/flaps + 低高度）作上下文豁免。
- 允许 Scenario：IN_FLIGHT、COMBAT_STRESS（触发后入 CRITICAL_RISK）。
- 被抑制 Scenario：SPAWNING（grace）、OUT_OF_BATTLE、DEAD、BATTLE_ENDED。
- severity 8 / priority 9 / 抢占 是 / cooldown 15s。
- re-arm：退出阈值（IAS 回升、AoA 正常）保持 ≥3s 后可再触发。
- payload：`ias_kmh`、`aoa_deg`、`radio_altitude_m`（AGL，若数据层提供）、`altitude_m`（MSL/海拔事实）、`vertical_speed_ms`。
- 缺字段降级：无 `AoA` → IAS+下沉粗判（误判↑）；无 `IAS` → 砍。
- 误判风险：高（逐机失速速度不同、AoA 抖动、降落正常低速）。
- 提示意图：警示濒临失速，促使加速/松杆改出。

#### `high_aoa` 攻角过大
- 中文说明：飞控/Betty 类 `critical angle` 风险，迎角过大但不等同于低速失速。
- 来源信号：数据层 flag `aoa_high` / `aoa_critical`（阈值来自 vehicle profile / datamine 候选）。
- 触发条件摘要：AoA 高于阈值，数据层先分 warning/critical；插件按边沿触发。
- 允许 Scenario：IN_FLIGHT、COMBAT_STRESS（critical 后入 CRITICAL_RISK）。
- 被抑制 Scenario：SPAWNING、OUT_OF_BATTLE、DEAD、BATTLE_ENDED。
- severity 8 / priority 9 / 抢占 是 / cooldown 10s。
- re-arm：AoA 回落并保持退出窗口后可再触发。
- payload：`aoa_deg`、`ias_kmh`、`g_now`。
- 误判风险：中（各机飞控保护/可用迎角差异大，需继续真机校准）。
- 提示意图：警示攻角过大，提示松杆/改出，避免继续硬拉。

#### `over_g` 过载过大
- 中文说明：飞控/Betty 类 `over-g` 风险，机体结构或飞控限制可能被突破。
- 来源信号：数据层 flag `over_g` / `over_g_critical`（优先使用 profile 中 `instructor_g_limit_*`；缺少时才回退 `g_limit_*_candidate` 并按当前燃油比例插值）。
- 触发条件摘要：当前 `Ny/load_factor` 超过 warning/critical 阈值；正/负过载均可触发。
- 允许 Scenario：IN_FLIGHT、COMBAT_STRESS（critical 后入 CRITICAL_RISK）。
- 被抑制 Scenario：SPAWNING、OUT_OF_BATTLE、DEAD、BATTLE_ENDED。
- severity 8 / priority 9 / 抢占 是 / cooldown 10s。
- re-arm：过载回落并保持退出窗口后可再触发。
- payload：`g_now`、`ias_kmh`、`aoa_deg`。
- 误判风险：中（游戏模式、飞控保护、挂载/燃油对结构限制影响明显；Instructor G 限制优先，避免结构候选误报正常高 G 机动）。
- 提示意图：警示过载过大，提示松杆/回正，避免继续硬拉。

#### `low_alt_danger` 低空危险
- 中文说明：离地过近且持续下沉，撞地风险。
- 来源信号：`low_alt_danger` detector（`H, m` + `Vy, m/s`，辅以 `IAS`/`pitch`/`gear`）。
- 触发条件摘要：低高度 + 较大负 Vy，经 confirm；降落进近（gear + 受控下降）作上下文豁免。
- 允许 Scenario：IN_FLIGHT、COMBAT_STRESS（→CRITICAL_RISK）。
- 被抑制 Scenario：SPAWNING、OUT_OF_BATTLE、DEAD、BATTLE_ENDED。
- severity 9 / priority 9 / 抢占 是 / cooldown 10s。
- re-arm：高度回升过退出线 或 Vy 转正 保持 ≥2s。
- payload：`radio_altitude_m`（AGL，优先用于离地/低空判断和提示）、`altitude_m`（MSL/海拔事实，仅作上下文）、`vertical_speed_ms`、`ias_kmh`。
- 缺字段降级：只有 `H` 无 `Vy` → 用历史差分算下降率（更糙）。
- 误判风险：高且结构性——`H`/`altitude_m` 是海拔非离地（AGL），山区/丘陵易误判；插件侧已统一优先 `radio_altitude_m`。当 AGL 不可用时，仍需把 `altitude_m` 视为降级上下文，并通过起飞/滑跑保护、confirm 窗口和场景门控压误判。
- 提示意图：警示离地过近且在下沉，促使立即拉起。

#### `overspeed` 超速
- 中文说明：表速超出安全包线，结构/操纵面损坏风险。
- 来源信号：**数据层 flag `overspeed_warn` / `overspeed_critical`**；我们读 flag 翻转，不自己算阈值。数据层 v1.6 已提供，后续需验证字段名和触发节奏。
- 触发条件摘要：上游 overspeed flag 进入（false→true），经 confirm。
- 允许 Scenario：IN_FLIGHT、COMBAT_STRESS（→CRITICAL_RISK）。
- 被抑制 Scenario：SPAWNING、OUT_OF_BATTLE、DEAD、BATTLE_ENDED。
- severity 7 / priority 8 / 抢占 是 / cooldown 15s。
- re-arm：IAS 回落过退出线保持 ≥3s。
- payload：`ias_kmh`、`mach`、`altitude_m`、`flaps_state`、`gear_state`。
- 缺字段降级：有 `IAS` 即可；无 `IAS` → 砍。
- 误判风险：中（never-exceed 逐机不同，喷气/螺旋桨差异大）。
- 提示意图：警示超速，提示收油门/改出，避免结构损坏。

#### `overheat` 发动机过热
- 中文说明：水温/油温/排气温持续超红线，发动机受损风险（慢性）。
- 来源信号：`overheat` flag detector（`engine_overheat*` / `oil_overheat*`）或 `hud_notices.feed[].code=engine_overheat/oil_overheat` 的安全 code-only 离散通知。
- 触发条件摘要：任一温度持续超阈值 N 秒（confirm 窗口偏长，避免瞬时尖峰）。
- 允许 Scenario：IN_FLIGHT、COMBAT_STRESS。
- 被抑制 Scenario：SPAWNING、OUT_OF_BATTLE、DEAD、BATTLE_ENDED、**CRITICAL_RISK（危急时压住次要）**。
- severity 6 / priority 6 / **抢占 否** / cooldown 30s。
- re-arm：温度回落过退出线保持 ≥10s。
- payload：`temp_kind`（water/oil/head）、`temp_c`、`throttle_pct`。
- 缺字段降级：有任一温度即可；全无 → 砍。
- 误判风险：中（红线逐机不同；液冷/气冷/喷气看不同字段）。
- 提示意图：提示发动机过热，建议收油门/开散热。
- ✅ 与 D-B1 一致性：本字典把 overheat 归"重要提醒"、**不触发 CRITICAL_RISK**。已回填 D-B1（CRITICAL_RISK 集合收窄为 `{stall_risk, low_alt_danger, overspeed}`，overheat 进 D-B1 第 4 节"安全·重要提醒"列）。

#### ~~`steep_dive` 高速俯冲~~（v0.2 已删除）
- **v1 删除**：与 `low_alt_danger`/`overspeed` 重叠、severity 最低、数据层也未提供。危险俯冲已被低空/超速覆盖。留待 v2 视真机数据再评估（如"预测性拉起"）。

#### `low_fuel` 低油
- 中文说明：燃油比例偏低，需关注返航/续航。
- 来源信号：`low_fuel` detector（`Mfuel, kg` / `Mfuel0, kg` → fuel_frac）。
- 触发条件摘要：fuel_frac 低于阈值（经 confirm，避免抖动）。
- 允许 Scenario：**仅 IN_FLIGHT**。
- 被抑制 Scenario：COMBAT_STRESS、CRITICAL_RISK、SPAWNING、OUT_OF_BATTLE、DEAD、BATTLE_ENDED。
- severity 3 / priority 4 / 抢占 否 / cooldown：每局 1–2 次。
- re-arm：补油（frac 回升）或新一局。
- payload：`fuel_frac`、`fuel_kg`、`est_minutes`（可选，若能由耗油速率估算）。
- 缺字段降级：有 `Mfuel` 无 `Mfuel0` → 绝对值粗判（差）。
- 误判风险：低；"多少算低"是产品口味。
- 提示意图：提醒油量偏低，注意返航/规划。

### B 组 · combat.feed 离散

#### `you_killed` 击杀
- 中文说明：玩家击落/摧毁了敌方单位。
- 来源信号：`/api/telemetry.combat.feed[]` 中未播报过的 `id`，且 `is_my_kill == true`。
- 触发条件摘要：数据层已完成身份归属判定；插件按已播报 owned id 去重并消费 ownership flag，允许同一 feed id 从未归属后补为 owned kill 时补触发。
- 允许 Scenario：SPAWNING、IN_FLIGHT；`COMBAT_STRESS` / `CRITICAL_RISK` 下不立即播报，但允许 Arbiter 延迟保留 owned kill，待压力解除后合并补一句。
- 被抑制 Scenario：OUT_OF_BATTLE、DEAD、BATTLE_ENDED。
- SPAWNING 说明：只放行数据层已归属的 owned kill；飞行安全事件仍由 spawn grace 压制，避免刚进场误报。
- severity 3 / priority 5 / 抢占 否 / cooldown 8s（**多杀合并**：短窗内多条合成一次"连杀 N"；`COMBAT_STRESS` / `CRITICAL_RISK` 下延迟保留，压力解除后补播）。
- re-arm：新的 combat.feed 击杀 id。
- payload：`target_name`（可选）、`target_vehicle`（可选）、`killstreak_count`。
- 缺字段降级：不可降级（无 `is_my_kill == true` 即无事件）。不回退到 raw hudmsg 文本匹配。
- 误判风险：中（主要取决于数据层 ownership flag 与玩家身份 seam；插件侧不再做多语言文本解析）。
- 提示意图：按空/陆/海载具域临场确认战果；可轻夸、调侃或收住，但不套固定夸夸，不复读 raw 玩家名。

#### `you_died` 死亡（与生命周期合一）
- 中文说明：玩家被击落/坠毁/阵亡。
- 来源信号：`/api/telemetry.combat.feed[]` 中未播报过的 `id`，且 `is_my_death == true`。
- 触发条件摘要：数据层已完成死亡归属判定；插件按已播报 owned id 去重并消费 ownership flag，允许同一 feed id 从未归属后补为 owned death 时补触发。`vehicle_valid` 翻转只用于 Scenario 存活态，不作为 `you_died` 主路径。
- 允许 Scenario：DEAD（死亡瞬间触发并进入 DEAD）。
- 被抑制 Scenario：OUT_OF_BATTLE、SPAWNING、BATTLE_ENDED。
- severity 8 / priority 10 / **抢占 是**（重要时刻不应被限流吞掉）/ cooldown：每次死亡 1 次。
- re-arm：新一次死亡（重生后再死）。
- payload：`cause`（shot_down/crashed/unknown）、`by_name`（可选）、`own_vehicle`。
- 缺字段降级：不可降级（无 `is_my_death == true` 即无死亡事件）。不回退到 `valid` 翻转播报死亡。
- 误判风险：中（主要取决于数据层 ownership flag；插件侧避免 valid 翻转造成的离场/观战误报）。
- 提示意图：阵亡安慰/共情，简短。

### C 组 · 生命周期

#### `spawn` 出生/进入战斗
- 中文说明：玩家进场或重生进入载具。
- 来源信号：`/state.valid` false→true + `/indicators.type` + `/mission`（进行中）。
- 触发条件摘要：进入 SPAWNING（出生/重生）时发一次。
- 允许 Scenario：SPAWNING。
- 被抑制 Scenario：其余全部。
- severity 1 / priority 5 / 抢占 否 / cooldown：每次出生 1 次。
- re-arm：新一次出生（valid false→true）。
- payload：`vehicle_name`。
- 缺字段降级：无 mission 时仅用 valid 翻转粗发。
- 误判风险：中（加载/换机/重生都触发跳变，需 mission 区分）。
- 提示意图：出场打招呼/就位陪伴。

#### `battle_end` 战斗结束
- 中文说明：本局判定结束（胜/负/撤离）。
- 来源信号：`/mission.json` status（win/fail/left）或 `/hudmsg events[]`。
- 触发条件摘要：进入 BATTLE_ENDED 时发一次。
- 允许 Scenario：BATTLE_ENDED。
- 被抑制 Scenario：其余全部。
- severity 1 / priority 6 / 抢占 否 / cooldown：每局 1 次。
- re-arm：新一局。
- payload：`result`（win/lose/left）、`session_kills`、`session_deaths`。
- 缺字段降级：无 mission → valid 长时间 false + 无在战 兜底（糙、可能漏胜负）。
- 误判风险：中（区分"局结束"vs"我死了但局还在"，依赖 mission）。
- 提示意图：战斗结束小结/情绪收尾。

---

## 3. 跨事件去重 / 重叠规则

- ~~steep_dive 去重~~：steep_dive 已于 v0.2 删除，此规则作废。
- **you_died 去重**：以 `combat.feed` 新 id 为准；同一 id 只产一次死亡事件。`valid` 翻转只影响 Scenario，不参与死亡事件合并。
- **多杀合并**：you_killed 在 cooldown 窗内的多条合成一次"连杀 N"，避免连珠炮。
- **危急互斥靠 priority**：同窗多个危急（如 stall + low_alt）只播 priority 最高者，其余压入冷却（由 D-B4 仲裁）。

## 4. 与其它文档衔接 + 开放项

- 触发条件的**具体阈值/迟滞/confirm 窗口**在 D-B3（ConditionDetector）定义，本字典只给摘要。
- 第 1 节矩阵的"允许/抑制 Scenario"与 D-B1 第 4 节门控矩阵一致（overheat 回填 ✅ 已完成）。
- payload 字段须能从**数据层 `/api/telemetry`** 字段派生（见 D-B5 v0.2 映射）；落不到的（如 you_killed 的 `victim_vehicle`、you_died 的 `killer_vehicle`）标"可选"，缺则降级。
- 当前已采用代码中的 severity/priority/cooldown；逐机告警阈值由数据层 profile 管理。后续真机校准另行评估，不能把本文早期汇合期草案当作未落地实现。
- 未决：① `/api/identity` 自动选择/展示体验是否需要继续增强；② est_minutes 估算是否 v1 做。多杀合并已在插件侧轻量实现。

## 海战地图观察事件（2026-10-27）

| 事件 | 含义 | category / priority / severity | cooldown / 时效 | 输出 |
|---|---|---|---|---|
| naval_map_contact | 地图出现敌方水面/地面图标类别 | map_awareness / 3 / 2 | 30s / 4s | 仅 dry-run，非抢占 |
| naval_air_contact | 地图出现敌方空中图标类别 | map_awareness / 3 / 2 | 30s / 4s | 仅 dry-run，非抢占 |

不确认具体敌舰、空袭、距离、锁定或航向；不新增 recovery/心跳或真实输出开关。来源与生命周期绑定见 D-B5，实际海战未验。

## 海战检测结果对照（2026-10-28）

BattleEvent 新增仅用于本地诊断的可选 trace_id；仅海战观察接收合法的 32 位十六进制随机标识，不含战局/生命/玩家身份。该字段不进入 payload、to_dict() 投递序列化、repr 或事件相等性；原事件含义、优先级、冷却与阈值不变。 真实输出继续双边界硬关闭，见 [结果对照记录](海战检测结果对照-20261028.md)。
