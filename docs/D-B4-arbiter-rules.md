# D-B4｜提示仲裁规则（Arbiter，v1 · RB 空战）

> 状态：v0.2（汇合后）· 范围：v1 RB 空战，9 个事件，消费数据层 flags
> 用途：定义**唯一仲裁者**——把"本 tick 的候选 BattleEvent + 当前 Scenario"收敛成"这一刻到底开不开口、说哪一条"
> 关联：D-B1（Scenario 门控矩阵）/ D-B2（severity/priority/cooldown/抢占/类别）/ D-B3（候选来源）/ D-B5（事件→数据层映射）

## 0. 定位

Arbiter = **猫这一张嘴的总闸**。所有 Detector 产出的候选都汇到这里，由它**统一**决定开不开口、说哪条。铁律：**每次仲裁至多产出 1 条**输出（→ `neko_dispatcher` → `push_message`）。它不拼台词、不判危险（那是 Detector），只做"该不该说、说哪条、抢不抢"。

## 1. 输入 / 输出 / 状态

- **输入**：本 tick 的候选 `BattleEvent[]`（来自 D-B3 各 Detector，含 `event_id/edge/payload`）+ 当前 `Scenario`（D-B1 解析器给）+ Arbiter 自己的历史状态。
- **输出**：0 或 1 条 `BattleEvent` → dispatcher。危急/动作 cue 保留稳定短句；`spawn`、击杀/阵亡、过热、低油、普通接近、目标点和战斗结束走有边界的 `respond`，允许猫娘在短话范围内带一点情绪、玩笑或陪伴感，但不得编敌情、方位、锁定、击杀、威胁或损伤。态势/目标类只报观测到的方位、距离和目标类型，缺项不能补。
- **状态（跨 tick 记忆）**：`_last_output_at`（全局限流时钟）、`per_event_last_fired_at`（各事件 cooldown）、`_window`（当前窗口缓冲：最高分候选 + flush 计时）、`_kill_window`（击杀合并缓冲：第一杀时间 + 最近一杀时间 + `kill_count`）、`_last_critical_at`（防抢占风暴）、`seen_discrete_ids`（离散去重）。

## 2. severity 两级映射 + 抢占资格（先钉死，否则 overheat 会乱抢占）

数据层给两级 flag（`_warning` / `_critical`）。映射规则：

- 数据层 **`_critical`** → 该事件取**高 severity 档**；数据层 **`_warning`** → **中 severity 档**。
- ⚠️ **抢占资格 ≠ 数据层 critical**。抢占资格 = **我们的危急集合 `{stall_risk, low_alt_danger, overspeed}` ∪ `{you_died}`，且数据层报 critical 级**——两条件都满足才抢占。
- 因此：`overheat`/`low_fuel` 即便数据层报 `_critical`，**也只抬高 severity、绝不抢占**（它们是慢性/提醒，不属危急集合）。

## 3. 仲裁流水线（每 tick 跑一遍）

```text
候选 BattleEvent[]
  │
  ▼ [1] Scenario 门控   查 D-B1 矩阵(当前Scenario × 事件类别) → 抑制者直接丢(记 scenario_gated)
  ▼ [2] 去重 / 合并     event cooldown 内丢；多杀合并；kill/death 按已播报 owned feed id 去重；离散按 id 去重
  ▼ [3] 分流           抢占资格(见§2) → 抢占通道；其余 → 限流通道
  ├─ 抢占通道(critical) ─ [4] 抢占判定 → 立即开口(下方 §4-2)
  └─ 限流通道(warning/普通) ─ [5] 窗口择优(留最高 priority 1 个) → [6] 全局限流 flush
  │
  ▼ [7] 单一出口        至多 1 条 → dispatcher.push_message
```

## 4. 十条规则（逐条对应你的需求）

### 4-1 Scenario 门控规则
- **流水线第一步**。每个候选按 `event_id` 查类别（D-B2：生命周期 / 安全·危急 / 安全·重要提醒 / 安全·一般提醒 / 战斗·击杀 / 陪伴闲聊），再查 D-B1 第 4 节矩阵"当前 Scenario × 类别"。
- 矩阵判"抑制" → 候选**当场丢弃**（dry_run 记 `scenario_gated`）。门控在最前，省掉后续一切计算。
- 例外：`CRITICAL_RISK` 下的 owned `you_killed` 不立即播报，但也不当场丢弃；它进入 kill coalescing buffer，记录 `kill_deferred_critical_risk`，待危急解除后再按窗口规则 flush。这样击杀不会打断生死级安全提醒，也不会因为危急状态被永久吞掉。

### 4-2 critical 是否抢占、怎么抢占
- **抢占资格**：见 §2（危急集合 ∪ you_died，且数据层 critical）。
- **怎么抢**：① **绕过全局限流**（`_last_output_at` 不拦它）；② **清空当前 warning 窗口缓冲**（被抢的 warning **丢弃、不补播**，避免抢占后补一串）；③ 仍受 Scenario 门控（但危急安全本就只在 IN_FLIGHT/COMBAT_STRESS 触发→入 CRITICAL_RISK）；④ 立即交给 dispatcher，默认走 bounded `respond` 短播报并进入 TTS，只有显式兼容开关才使用插件短句 `blind+plugin`。
- **防抢占风暴**：两次 critical 之间至少隔 `critical_preempt_cooldown`（草稿 5s），**除非新 critical 的 priority 严格更高**（如 `you_died`(10) 可立刻打断正在播的 `stall_risk`(9)）。
- **多 critical 同 tick**：按 priority 取最高 1 个（low_alt/stall=9、overspeed=8、you_died=10）。

### 4-3 warning 是否排队、怎么排队
- warning / 一般提醒 / 战斗 / 陪伴 **不抢占**，走"**单槽窗口**"（沿用 neko_roast `live_events` 的"冷却期缓冲、到点 flush 最高分"）：
  - 不是 FIFO 无限堆积，而是**当前窗口只保留 priority 最高的 1 个候选**（O(1)），其余即时丢弃。
  - 窗口长度 = `global_rate_limit`（与限流对齐，flush 出来不会反被限流判回）。
  - 空闲态（冷却已过、无开窗）第一条**即时**开口（保留即时反应）；冷却期内才缓冲择优。
  - 被 critical 抢占 → 当前窗口候选丢弃、不补播。

### 4-4 同一窗口多个事件如何选一个
- 排序键：**priority（D-B2）降序** → severity 降序 → 后到优先（更新鲜）。取**第 1 个**，其余丢。
- critical 不进窗口（直接抢占）；只有 warning/普通进窗口择优。

### 4-5 同类事件 cooldown / 去重
- **cooldown 归 Arbiter**（D-B3 已定）：同 `event_id` 在其 cooldown（D-B2）内的新候选直接丢（记 `cooldown_drop`）。
- **re-arm 归 Detector**：保证"同一次持续状态"只产 1 个 enter 候选，Arbiter 不会反复收到。
- **离散去重**：`you_killed` 多杀合并成"连杀 N"；合并窗口按**最近一次击杀**滚动，连续战果先不急着夸，等安静满 `kill_coalesce_window_seconds` 后再合并输出；同时保留最长等待上限（当前为窗口的 3 倍），避免连续战果永远不播。空战/直升机在 `COMBAT_STRESS` 下按 `maneuver` / `air_contact` / `damage` 等压力源继续等；陆战/海战只在 `surface_contact` / `damage` 压力源下等脱战，不再强制拉长到固定 24s。`CRITICAL_RISK` 下的 owned kill 延迟保留，压力解除后再 flush；`you_died` 只消费 `combat.feed[].is_my_death == true` 的新 id；`vehicle_valid` 翻转只影响 Scenario 存活态，不参与死亡事件合并。

### 4-6 SPAWNING grace 如何抑制误报
- 主防线 = **Scenario 门控**：SPAWNING 下安全类(危急/重要/一般)全抑制（D-B1），放行 `spawn` 与数据层已归属的 owned `you_killed`。刚出生在跑道的假 stall/假 low_alt 候选在第 [1] 步即被丢；真实 owned kill 不再因为 grace 被误压。
- 双保险（可选）：出生后 `grace` 秒内不 arm 危急 Detector。grace 秒数待抓包定。

### 4-7 COMBAT_STRESS 如何压低油 / 闲聊 / 击杀夸夸
- = Scenario 门控：COMBAT_STRESS 下 **安全·一般提醒(low_fuel)=抑制、陪伴闲聊=抑制**；放行危急 + 重要提醒(overheat)。
- owned `you_killed` 先进入 kill coalescing buffer。若当前压力来源和击杀域匹配，则等场景回到 `IN_FLIGHT` 等稳定状态后合并补一句：空战/直升机匹配 `maneuver` / `air_contact` / `damage`，陆战/海战匹配 `surface_contact` / `damage`。若没有对应域压力证据，则按配置窗口合并，不再套空战缠斗的长等待。这样空战缠斗不会被夸夸打断，陆战/海战也能在近敌或受击时等真正脱战。
- `enemy_nearby` 按域分流：空战普通近敌仍是低优先级 map awareness，`COMBAT_STRESS` 下压制；陆战/海战近敌是交战观察信号，`COMBAT_STRESS` 下可放行。`ground_target_nearby` 仍是空/直升机域的任务点提示，压力态下按低优先级压制。

### 4-8 DEAD / BATTLE_ENDED 如何压掉普通事件
- = Scenario 门控：
  - **DEAD**：只放行死亡安慰（+安慰后闲聊）；安全/战斗全抑制。
  - **BATTLE_ENDED**：只放行结束小结（+闲聊）；安全/战斗全抑制。

### 4-9 单次输出最多说几条
- **至多 1 条**（猫只有一张嘴）。critical 抢占也只 1 条；多杀已合并为 1 条；critical 与 warning 同时 → critical 赢、warning 丢。**不存在一次说两条。**

### 4-10 dry_run 下如何记录决策链路
- `dry_run`（默认开）：完整跑仲裁，但 dispatcher **短路不真 push**。
- 每个候选记一条**判决链路**到 audit（+ 面板可见），形如：
  `candidate(event_id) → scenario_gate[pass|drop:reason] → dedup/cooldown[pass|drop] → class[critical|warning] → preempt[yes|no] → window[selected|dropped:lost_to X] → rate_limit[pass|blocked] → FINAL[spoken|suppressed:reason]`
- 用途：真机灌 `/api/telemetry` 样本时，逐条看"为什么说/为什么没说"，据此调阈值/冷却/优先级。

## 5. 参数（草稿初值，待 G3 真机校准）

- `global_rate_limit_sec`（warning 最小开口间隔）≈ 12（neko_roast 用 20，空战更快，调小）
- `window_len_sec` = `global_rate_limit_sec`（对齐）
- `critical_preempt_cooldown_sec` ≈ 5（防抢占风暴；更高 priority 可破例）
- `per_event cooldown` / `severity` / `priority` 取 D-B2
- `max_per_arbitration` = 1（硬上限）
- `spawn_grace_sec` 待抓包定

## 6. 与 neko_roast 复用 + 衔接 + 开放项

- **复用**：Arbiter ≈ neko_roast 的 `safety_guard.before_output`（限流）+ `live_events` 单槽窗口择优 + `output_cooldown_remaining` 对齐——**这些可照搬**。
- **新增（neko_roast 没有）**：§4-2 的 **critical 抢占** + 抢占风暴防护。这是空战相对直播的关键增量。
- **衔接**：Arbiter 输出 → `neko_dispatcher`（唯一出口，照搬 neko_roast，去掉头像）；常驻战雷场景上下文走 `instructions`。
- **开放项**：① 各参数真机校准（G3）；② recovery（生死级"好险拉回来了"）走限流通道、低 priority、可被丢，是否单独给小额度待定；③ `spawn_grace_sec` 待抓包。

---

> Track B 建模到此完成（D-B1~B5 全）。数据层 v1.6 已合并，T-Safety 已完成。下一步不再是等待补 overspeed/hudmsg，而是用真实 `/api/telemetry` 验证 v1.6 DTO 接缝，并保证自由文本正式播报始终通过 T-Safety prompt 合同。
