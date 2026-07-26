# neko_warthunder

War Thunder 猫娘副驾驶插件 v1。插件只消费本地数据层 HTTP `:8112`，把连续遥测整理成 Battle Awareness 事件，再经 Scenario / Arbiter / Safety / Dispatcher 决定是否让猫娘开口。

## 兼容性

- 插件 SDK：`>=0.1.0,<0.3.0`，推荐 `>=0.1.0,<0.2.0`。
- N.E.K.O 宿主：面板使用 Hosted TSX UI，需要 N.E.K.O `v0.8.0` 或更新版本。
- 显示环境：支持浅色/深色主题、桌面窗口、窄窗口和低高度窗口；主内容独立滚动，底部播报控制不会覆盖内容。
- 当前面板以简体中文为主要操作语言；插件名称与简介已提供 8 个宿主 locale，完整面板国际化不属于本轮范围。

## 当前状态

- M1 scaffold + M2 Battle Awareness 主链路已实现。
- T1A Hosted UI Integration + T1B Minimal Panel 已完成，surface/context/action smoke 已通过。
- T4 集成测试已完成；T-Safety output text sanitizer 已完成；T-Observe runtime decision timeline 已完成轻量实现；T-Safe-Activity 默认安全活动摘要与筛选页已完成；T-Safe-Diagnostics 白名单诊断摘要与一键复制已完成；T-Live live monitor summary tool 已完成；T-Output output backpressure guard 已完成；T-Output-Freshness-Gate 输出新鲜度门禁已完成；T-Vehicle-Profile-ID-Audit 载具 id 口径门禁已完成；T-Host-Callback-Contract-Reservation 通用宿主 callback contract 预留已完成；T-Host-Contract-Gate 宿主短播报/用户聊天静默兼容门禁已完成（仅作为本地兼容/实验检查，不要求为本插件写入宿主专用核心逻辑）；T-Ownership-Replay-Gate 第三方样本 ownership 回放门禁已完成；T-Kill-Coalesce 多杀合并已完成；L8 data-layer subprocess orchestration 已完成最小编排；`/api/identity` Hosted UI/action 接缝已完成；Hosted UI 设置页已加入安静/标准/活跃三档非危急播报频率，以及一般安全、战果、固定无线电、态势感知、开场收尾五类偏好开关，并支持一键恢复标准频率和全部普通类别；critical 安全和阵亡提醒始终保留；V2 proximity / objective awareness 非真机依赖部分已完成，并新增 `tools/v2_readiness.py` / `tools/v2_release_matrix.py` / `tools/v2_output_policy_gate.py` / `tools/v2_completion_gate.py` / `tools/rc_handoff_report.py` 作为 V2 收口汇总、能力矩阵、真实输出策略、完成度门禁和 RC 交接报告入口；当前逻辑自检以 `536/536 passed` 为准。
- 2026-06-21 / 2026-06-23 真机 smoke 已通过：Hosted UI context/action、pause/resume 安全门、spawn、overspeed warning/critical、low_fuel warning/critical、low_alt warning/critical、stall warning/critical、overheat warning/critical、identity manual seam、owned kill/death ownership、`you_killed` / `you_died` dry_run 决策链路、`dry_run=false` 真实 push 输出均正常。
- 数据层 `v1.6` 已合并到当前独立插件仓库，包含 `overspeed_warn` / `overspeed_critical`、增强 `combat.feed`、`is_my_kill` / `is_my_death`、`/api/identity`、`replay: true` 降级、`hud_notices`、`awards`。
- 数据层字段缺口不再是“等待字段补齐”；插件侧已分项接入 `v1.6` DTO，剩余重点是真机 / 样本接缝验证。
- 插件侧已按 `combat.feed[].is_my_kill` / `combat.feed[].is_my_death` 生成 `you_killed` / `you_died`，击杀/死亡 prompt 已按 `domain` / `cause` 使用 generic 空/陆/海措辞，不复读 raw victim 玩家名；已提供面板 `set_identity` action 调用数据层 `/api/identity` 设置/清除玩家名，并会把首次手动玩家名持久化到插件配置、下次启动自动恢复到数据层；玩家名 UI 只支持手动填写，`active_players` 仅保留为安全摘要/调试数据；在 `replay=true` 时静默 Detector 输出。
- 插件侧已接入 `hud_notices.feed[].code` 中的 `engine_overheat` / `oil_overheat`，可映射为现有 `overheat` 事件；raw HUD 文本不进入 prompt。
- 陆战已从“复用空战安全逻辑”拆出，猫娘状态播报只保留真实 `ground_laser_warning`，且仅在 `domain == "ground"` 时触发，不进入固定翼 `CRITICAL_RISK` 集合。乘员、岗位和一级弹药数据继续保留在 8112 DTO/面板中，但不生成播报候选；输出层仍把 `domain` 写入 prompt 和 `push_message.metadata.domain_prompt_contract`，避免空战 / 直升机 / 陆战 / 海战串话。
- V2 接近/目标态势感知已接入双路径：`enemy_nearby` 仍消费数据层边沿事实 `proximity.events`；`air_threat_nearby` / `enemy_on_six` / `tailing_risk` 同时消费 `proximity.events` 和连续态势摘要 `situation.nearest_air_threat` / `situation.enemies`，按距离、钟点和相对角度生成安全 generic 事件；`ground_target_nearby` 消费 `situation.ground_targets`。普通接近和任务目标点在 COMBAT_STRESS 下被压住，空中威胁/后方威胁/持续尾随风险可进入队列，critical 安全事件仍优先。Hosted UI context / 面板暴露安全态势摘要，不暴露 raw 文本或目标 label。
- `T-Safety: output text sanitizer` 已实现，位于 `NekoDispatcher` / prompt builder 前；prompt 和 `push_message.parts[].text` 只能使用 safe / generic 文案，且已覆盖 hudmsg / combat.feed / awards 常见自由文本字段族。
- `tools/free_text_gate.py` 已纳入离线 preflight，作为 hudmsg / combat.feed / awards 去桩前的发布门禁：合成恶意玩家名、HUD、combat feed、award payload 后，验证 prompt 与 `push_message.parts[].text` 不含 raw 文本；这些路径在真机 dry_run 安全验证前仍保持 dry_run-only。
- `tools/release_defaults_gate.py` 已纳入离线 preflight，作为发布默认值门禁：确认默认 `dry_run=true`、debug timeline 关闭、`v2_live_verified_real_output_enabled=false`，且输出背压 / 事件过期 / 多杀合并 / 起飞滑跑保护等保守默认仍开启。
- 运行态已补 `detector_suppressed/free_text_blocked` 与 `free_text_activity`：真机中首次看到 `awards`、`combat.feed`、`hud_notices`、`hudmsg` 或 `hud_events` 时，会记录安全来源和计数摘要，并在 dry_run 下形成可追踪候选；`dry_run=false` 仍由 Dispatcher 以 `free_text_dry_run_only` 压住，不播报、不保留 raw 文本到 observe、不让 raw 文本进入 prompt。
- `tools/replay_gate.py` 已纳入离线 preflight，作为 `replay=true` 降级发布门禁：合成带 critical flags、owned combat.feed、HUD notices、awards 的 replay 帧后，验证 Detector 不产出 candidate、Dispatcher 不构造 prompt、也不调用 `push_message`。
- `tools/ownership_replay_gate.py` 已纳入离线 preflight / release readiness，作为第三方旧样本 ownership 门禁：用手动 identity + 显式 opt-in 推断旧 `combat.feed` 的 owned kill/death，并验证叠加干扰项不会把非我方 combat feed 当成本人战果。
- `tools/deferred_hud_gate.py` 已纳入离线 preflight，作为 `powertrain_failure` 等 deferred HUD 技术通知的发布门禁：验证它们当前只可观测、不生成播报 candidate / prompt / push，且 raw HUD 文本不泄露。
- `tools/proximity_gate.py` 已纳入离线 preflight，作为 V2 接近/目标态势发布门禁：合成 proximity / situation DTO 后，验证 Detector / Arbiter / Dispatcher / `push_message.parts[].text` 的安全泛化输出和门控关系，覆盖 `tailing_risk` 持续后方威胁升级。
- `tools/host_contract_gate.py` 已纳入离线 preflight / release readiness，作为本地宿主兼容门禁：宿主存在时静态验证 `short_tts_line` 短播报合同、跨 chunk 字数闸、`neko_warthunder:battle_event` 用户聊天静默窗口、pending callback / hot-swap mirror 的 `coalesce_key` 旧事件替换、hot-swap extra reply metadata 保留、各 callback delivery call site，以及“用户聊天干扰下 death 替换旧 warning”的组合回归用例；宿主不存在时不阻塞插件独立仓库开发。注意：该门禁用于本地宿主兼容验证，不代表插件要求把 `neko_warthunder` 专用逻辑写进宿主核心；当前核心区先冻结，后续应由宿主提供不带插件名特判的通用 callback contract 接口。
- `docs/host-callback-contract-reservation.md` 记录了插件侧预留的通用宿主接口：真实战场输出会在 metadata 中同时保留旧 flat 字段和 `host_callback_contract.version=neko.callback.v1` 结构化块，覆盖 `delivery.coalesce_key`、`delivery.replace_pending`、`delivery.interrupt_pending`、`delivery.expires_at`、`reply.mode=short_tts_line`、`reply.max_chars=28`、`reply.single_turn`、`quiet_window.policy`、`quiet_window.bypass` 和 `freshness`。未来宿主只应消费这组通用语义，不应 special-case `neko_warthunder`。
- `tools/v2_output_policy_gate.py` 已纳入离线 preflight，作为 V2 真实输出策略门禁：`enemy_on_six`、`tailing_risk`、`ground_target_nearby` 在缺少真机证据前默认只允许 dry_run 可观察，真实 `push_message` 会被 `v2_live_evidence_pending` 压住；只有显式开启 `v2_live_verified_real_output_enabled=true` 后才允许真实推送。
- `tools/v2_completion_gate.py` 已纳入离线 preflight，作为 V2 完成度门禁：证明 V2 code/offline scope、安全输出合同和真实输出保护均已闭环，同时明确 `v2_live_evidence_complete=false` 时不得声称后方威胁、持续尾随或目标点真机证据完成。
- `tools/rc_handoff_report.py` 已纳入离线 preflight / release readiness，作为维护者 RC 交接报告：合并 v1 release scope、V2 completion、final smoke go/no-go、安全边界和剩余 live evidence 缺口，方便在不启动前后端、不依赖 War Thunder 的情况下给合作者交接。
- `tools/release_readiness.py` 已作为离线汇总入口：不启动前后端、不依赖 War Thunder，默认只聚合 logic tests、pytest、RC 文档审计、vehicle profile id audit、release defaults gate、output freshness gate、host contract gate、free-text gate、replay gate、ownership replay gate、deferred HUD gate、mode/domain boundary gate、proximity gate、V2 readiness summary、V2 release matrix、final smoke packet、synthetic replay，以及宿主存在时的本地宿主兼容检查 / plugin check；需要把本地大样本报告也纳入时显式加 `--include-local-sample`。`release_scope` 会直接列出 `ship_status`、free-text 真实播报 blocker、样本未证明项和下一步动作，`handoff` / `handoff_status` 会合并 v1 发布状态与 V2 live evidence 缺口；通过后再进入最后一轮真机 smoke。
- `T-Observe` 已接入 Hosted UI `observe` context：普通模式保留最近一次事件/决策/输出摘要，debug 模式才返回内存 ring buffer timeline。
- 战雷上下文注入已改为遥测状态驱动：插件启动时不再立刻把猫娘切进战雷副驾驶语境；只有 `:8112 /api/telemetry` 从 `offline` 进入可用状态后才通过 `read` 注入战雷上下文，断开或回到 `offline` 后再通过 `read` 注入恢复日常聊天信号。状态面板会暴露 `game_context_active`，便于真机确认“插件启用”和“战雷语境启用”不是同一个开关。
- `T-Output` 已在真实 `push_message` 前接入输出背压：`output_backpressure_seconds` 窗口内压住同优先级或更低优先级事件，避免主机回复队列堆积；`you_killed`、`you_died` 和 critical 安全事件可通过，避免击杀夸夸被普通过载提示吃掉。危急动作类默认走 bounded `respond`，由宿主生成受 28 字短播报合同约束的回复并进入 TTS；仅显式开启 `plugin_owned_urgent_output_enabled` 时才使用 `blind+plugin` 固定短句兼容模式。`spawn`、击杀/阵亡、过热、低油、普通接近、目标点和战斗结束同样走 bounded `respond`，允许猫娘在短话范围内带一点情绪、玩笑或陪伴感，但不得编敌情、方位、锁定、击杀、威胁、损伤；态势/目标类只能说已观测到的方位、距离和目标类型，缺项别补。输出会带统一 `coalesce_key=neko_warthunder:battle_event`、事件年龄 / 过期时间 metadata（`event_age_seconds` / `event_expires_at`）、可解析到的 `target_lanlan`、短播报合同（`battle_reply_contract=short_tts_line` / `live_reply_contract=short_tts_line` / `max_reply_chars=28`），以及通用 `host_callback_contract` 预留块，方便真机排查 fallback session / 晚播来源；`output_event_max_age_seconds` 默认 8s，但低空/超速/接近/后方威胁/目标点等强时效战术提示会使用更短的新鲜度窗口，`you_killed` 使用 30s 专用窗口以覆盖脱战后合并补播，真实 push 前直接丢弃过期旧事件；同类安全提示短窗重复会记录为 `repeated_event_collapsed`，减少连续“松杆/过载”刷屏。
- `you_killed` 已接入轻量多杀合并：owned kill 会合成一条带 `kill_count` 的 generic prompt；合并窗口按最近一次击杀滚动，连续战果先不抢话，等安静满 `kill_coalesce_window_seconds` 后再输出，并用 3 倍窗口作为最长等待兜底，避免长连杀永远不播；`CRITICAL_RISK` 下 owned kill 不抢播也不丢弃，会记录 `kill_deferred_critical_risk` 并在危急解除后按 `kill_coalesced` 补播；`COMBAT_STRESS` 下会按压力来源和载具域处理，空战/直升机或 `damage` 压力继续等，陆战/海战纯 `maneuver` 压力可在合并窗口后输出；死亡/critical 抢占仍可清空待播击杀。
- L9 调参已接入起飞/滑跑保护：离地/低空判断仍优先使用 `radio_altitude_m`（AGL），`altitude_m` 只作海拔事实展示；但固定翼可能不稳定提供 AGL，因此出生/机场起飞仍保留 `takeoff_low_alt_grace_seconds=45` 的低空保护。AGL 可用时按 `takeoff_radio_altitude_enter_m=10` / `takeoff_radio_altitude_exit_m=40` 做贴地迟滞；AGL 不可用时，滑跑超速只在保护期内且起落架放下/运动中时压制，避免空中出生或收轮后真实超速被误压。不压 `stall_risk`、`overheat`、`low_fuel`、`you_died`。
- Hosted UI 面板已完成 RC 信息架构整理和中文化：概览负责日常状态与播报控制，诊断负责解释运行链路，设置负责昵称和教程；重复的插话规则入口已删除，概览底栏保留唯一常驻控制。连接状态、战场状态、安全控制、最近决策、最近输出分区清晰，主要状态标签、风险等级、场景、数据层模式和身份识别来源均显示中文。
- 首次启动教程已精简为两步：先在教程内直接保存战雷游戏昵称，再说明开启/停止播报、急停/恢复、测试开口、刷新状态和设置入口的用途；用户可以跳过，也可以从设置中重新打开教程。
- `tools/live_monitor.py` 的 Summary / Observe 摘要会保留 `kill_coalesced` 决策原因，并在输出被压住、过期丢弃或重复折叠时直接显示 `output_backpressure` / `event_expired` / `repeated_event_collapsed`；`observe.last_output_status` 还会带 `event_age_seconds` / `event_expires_at` / `target_lanlan` / `battle_reply_contract` / `live_reply_contract` / `max_reply_chars` / `plugin_owned_output` 等输出元数据。Decision detail / Output detail 会把 `selected`、`dry_run_enabled`、`kill_coalesced`、`output_backpressure`、`event_expired` 等原因翻译成中文可读解释，方便下一轮真机判断“没播/晚播”是合并、背压、过期丢弃、重复折叠、fallback session、短播报合同未被宿主消费，还是其他门控导致。
- kill/death ownership 已完成真机 dry_run 与 `dry_run=false` 真实 push 验证；2026-06-23 已验证手动 identity 会反映到 `combat.self.source=manual`，空战 / 陆战 owned combat.feed 均可产生 `is_my_kill=true` 或 `is_my_death=true`，插件可生成 `you_killed` / `you_died` 并经 Arbiter / Dispatcher 输出。hudmsg / awards 等其他自由文本真实播报仍需单独 dry_run 安全验证。stall/low_alt/overheat/overspeed/low_fuel 等数值安全事件不被 T-Safety 阻塞，且本轮已观察到 dry_run 正向链路。
- recovery 已评估并暂缓；当前不要打开 `wants_recovery`。

## 给 Codex 的启动指令

```text
你将接手独立插件仓库 project-N-E-K-O-Warthunder-8111-data-plugin。

先读：
- PROJECT_STATUS.md
- docs/handoff-20260715.md
- docs/实现计划-codex.md
- docs/真机验证-checklist.md
- docs/统一测试前-离线检查.md
- docs/真机测试结果-template.md
- docs/样本回放-20260620.md
- docs/待办事项.md
- docs/mode-domain-boundaries.md
- docs/D-B1-scenario-model.md ~ docs/D-B5-event-field-requirements.md
- data_layer/data process/后端接口文档.md

当前状态：
- Hosted UI 完成。
- T4 集成测试完成。
- 逻辑自检与 pytest 当前均为 524 个通过用例；`tests/run_logic_tests.py` 已兼容当前简单参数化隔离用例。
- v1 RC 离线汇总入口：`uv run python tools\release_readiness.py --run`。
- 数据层 v1.6 已合并，插件侧已分项接入 kill/death、identity、replay 静默和 overheat HUD notice，仍需真机接缝验证。
- 合作者 2026-06-20 真实样本已做离线 replay 聚合报告；`tools/sample_replay.py` 现在会输出 `session_summary`、分组 validation verdict、P1/P2 `live_test_plan`、V2 proximity/situation/ground target 覆盖率、逐能力 `capability_evidence` 和 `--json` 机器可读结果，并在样本含 `replay=true` 时证明 Detector suppressed / output blocked。当前 `sample_replay` 会合并 `records/*/proximity.jsonl*` 旁路流并统计连续 `situation.enemies` 空中/后方证据；2026-06-20 本地样本重放后已观察到 `proximity_events=5317`、`proximity_air_events=5300`、`proximity_rear_events=49`、`situation_rear_air_threat_live_items=1906`，并可触发 `enemy_on_six=149` / `tailing_risk=44`，不再把“无 proximity 后方边沿”误报成“无后方态势证据”；目标点样本仍尚未进入 `ground_target_nearby` 的 3000m 触发阈值；`tools/v2_readiness.py` 会汇总 V2 离线 gate、已实现事件、安全输出合同和本地样本证据，明确区分 `v2_offline_gate_complete` 与 `v2_live_evidence_complete`；`tools/v2_release_matrix.py` 会把 `enemy_nearby`、`air_threat_nearby`、`enemy_on_six`、`tailing_risk`、`ground_target_nearby` 拆成 code/offline/live-evidence/real-output-policy 能力矩阵，并显示每项能力的 observed/triggered 计数，明确哪些能力只差真机证据且保持 dry_run-first；`tools/final_smoke_packet.py` 会生成最后一轮真机 smoke 的 go/no-go、必跑命令、V2 缺口、逐能力矩阵、runtime focus checks、remaining live actions 和安全边界，`tools/final_smoke_evidence_gate.py` 会验收 smoke 后的 evidence JSON，也可用 `--from-live-monitor local_test_logs\live_monitor_final.json --output local_test_logs\final_smoke_evidence.json` 从安全 monitor JSON/JSONL 扫描 fresh pushed metadata 并预填新鲜度/短播报草稿；猫猫实际回复可先用 `--safe-transcript-template --output local_test_logs\safe_transcript_metrics.json` 生成无原文 metrics 模板，再用 `--safe-transcript local_test_logs\safe_transcript_metrics.json` 合并行数、字数、是否续写、用户聊天静默和 critical 替换观察；没有结构化 metrics 时仍可用 `--update --confirm-*` 显式合并人工确认的旧 warning 替换、用户聊天静默和短句单行结果；`release_readiness.py` / `preflight.py` 也可用 `--final-smoke-evidence <path>` 把该 evidence gate 纳入统一复验；`tools/rc_handoff_report.py` 会生成维护者可读 RC 交接报告，把 V1 offline gate、V2 code/offline 完成度、live evidence pending、安全边界和下一步动作放在一起；`tools/offline_report.py` 可生成安全 Markdown 或 compact JSON，并在 Markdown / JSON 中提供 Team brief、Next test focus、V2 capability evidence、Operator quick checklist 与 Next live-test plan，列出已观察事件、dry_run 输出、模块 readiness、剩余真机范围和下一步缺口；`tools/rc_gap_summary.py` 可生成机器可读 RC 缺口摘要，把 sample-unproven 项和真正 blocked release 项分开；`sample_replay` / `offline_report` / `live_test_plan` 三个出口都会带上 T-Output 背压与 T-Kill-Coalesce 多杀合并复测项，且 `next_steps` 也会列出这两个现场动作；`tools/live_test_plan.py` 可把待测项展开成 Operator quick checklist 和“操作 / 监控 / 通过 / 失败 / 数据层缺口”的真机操作清单；`tools/live_monitor.py` 可在真机测试中安全汇总 health、Hosted UI context、telemetry ownership 计数、free-text dry_run-only 状态与逐源 blocked 摘要、replay 降级状态、T-Observe last decision/output、新鲜度/短播报 metadata 和日志异常计数，并可用 `--output` 自动创建目录保存安全 JSON；`tools/preflight.py` dry-run 输出现在带 Quick read，`--run --report-output <path>` 可在统一预检时一并运行 runtime smoke、保存报告，并在通过/失败时给出下一步操作提示。
- 最终真机 smoke 的推荐 evidence 入口是交接包中的 `evidence_from_monitor_and_transcript`：`--from-live-monitor` 与 `--safe-transcript` 可在一条命令里合成 `local_test_logs\final_smoke_evidence.json`，分步命令只作为排障/补录路径。
- `safe_transcript_metrics.json` 推荐由交接包里的 `safe_transcript_record` 生成：`--record-safe-transcript --reply-chars <count>` 只记录数字和确认 flag，不保存猫猫回复原文。
- 真机前可先跑交接包里的 `evidence_rehearsal`：`--rehearsal-output-dir local_test_logs\final_smoke_rehearsal` 只演练证据流程，输出带 `rehearsal_only=true`，不能替代最终真机 evidence。
- 2026-07-15 离线 RC 包：`D:\Users\zheng\Desktop\code\N-E-K-O-Warthunder\dist\neko_warthunder-0.1.0-20260715-offline-rc.neko-plugin`，文件 SHA256 `7255DA8636F7B5B5880EB5CDDBE05DABC694EAAECA2429AC6EE51D3FC0BB82EA`；inspect、payload verify、`tools/package_artifact_gate.py` 内容边界和临时安装 smoke 均通过，包含播报偏好、推荐设置恢复、安全活动中心和白名单诊断摘要，`.ruff_cache`、`local_samples` 等开发/样本内容已从包中排除。该包跳过了本轮真机证据，只能标记为 offline RC，不能标记为最终公开发布。
- 2026-07-07 交接包：`D:\Users\zheng\Documents\Code\N-E-K-O-Warthunder\dist\neko_warthunder-0.1.0.neko-plugin`，SHA256 `960C20E35D2A516A96D2C3BD408123C3577505156DD527786C89BDDBCF828F6F`；release check / inspect / payload hash verify 已通过，包内不包含 `local_samples`、`local_test_logs`、captures、records、maps、tests、docs 或 tools。
- 真机 smoke 已完成多轮；2026-06-23 已观察到 `overspeed_warn` / `overspeed_critical`、`low_fuel`、`low_alt_danger`、`stall_risk`、`overheat`、`you_killed`、`you_died` 进入 Arbiter / Dispatcher，并验证手动 identity、owned combat.feed 归属字段和 `dry_run=false` 真实 push 输出。
- T-Observe 已完成轻量实现；真机 dry_run 已验证 `observe.last_decision` / `observe.last_output_status` 能解释 allow / preempt / cooldown / dry_run 输出。
- T-Safety 与 free-text release gate 已完成；kill/death 的安全 generic 输出已通过真机 `dry_run=false` smoke，hudmsg / awards / 其他 free-text 正式播报前仍需 dry_run 安全验证。
- L9 已接入起飞/滑跑保护、真实战场事件队列 coalescing、事件过期丢弃和 Hosted UI 中文化；V2 proximity / objective awareness 已完成离线 gate。下一轮真机统一复测机场起飞/复活、`proximity.events` 与 `situation.enemies` 双路径后方/六点钟样本、持续尾随风险 `tailing_risk`、任务目标点 `ground_target_nearby`、旧提示替换/过期丢弃、replay 与 free-text dry_run 安全。
- 数据库/profile 已从三批热门机型扩展为本地 Datamine 批量补库：`vehicle_profiles.json` 当前 1469 个 exact 条目、283 条 family、13 个 class 模板、约 1.76MB，覆盖固定翼 FM 可直接抽取的 stall / AoA / VNE/MNE / `Temperature.Load*` 候选，并补入质量、结构过载力、空/满油 G 候选、Instructor G 限制、燃油消耗和发动机惯性等只读证据字段。`char.vromfs.bin_u/config/wpcost.blkx` 的小型官方元数据也已回填到现有 exact profile：`rank`、`economic_rank_arcade`、`economic_rank_realistic`、`economic_rank_simulation`、`country`、`unit_class`、`unit_move_type` 覆盖 1377/1469；`economicRank*` 只按经济元数据保存，不宣称等同 UI BR，且不会导入 cost tables、reward multipliers、weapons、modifications 等大块经济/武器数据。通用层仍按飞模性能段维护：`transonic_jet`、`early_supersonic_jet`、`subsonic_attacker_jet`、`supersonic_attacker_jet`、`modern_high_alpha_fighter`、`heavy_modern_fighter` 等细分 class 已替代一部分旧粗桶；旧 class 名仍保留兼容。最新维护回填了已有 FM-stem / compact-id 别名条目，并用 unit `model` / `fmFile` 辅助 class 推断，不新增重复 alias profile，也不覆盖 `_tested` 实机校准阈值；当前 exact 条目中质量证据 1469/1469、最大燃油质量 1464/1469、结构/G 证据 1425/1469、燃油/惯性证据 1200/1469、油温候选 1345/1469、涡轮温度候选 480/1469。`tools/vehicle_family_coverage.py` 已可生成只读 vehicle family coverage 报告，列出 exact/family/class 覆盖、前缀风险和优先缺口；`tools/vehicle_profile_id_audit.py` 已把 Wiki `/unit/<gameId>` 候选、8112 `vehicle_type` 裁判、实机 vetted id 和已复核 alias 纳入离线门禁，当前 8 个 vetted id、4 组 reviewed alias、0 个 unreviewed alias warning。本轮已修正 Hampden、G.50、CR.42、MB.150、Mystere、Gripen、Draken 等 family 前缀与真实 `vehicle_type` 的错位。温度阈值已从 `_default` 移出，避免未知载具继承错误过热线；直升机/UAV 不混入固定翼 profile。`tools/datamine_profile_candidates.py` 只读抽取候选，`tools/update_vehicle_profiles_from_datamine.py` 从本地 gszabi99 checkout 批量补齐 exact profile，`tools/update_vehicle_profile_economy_from_datamine.py` 回填 vehicle profile economy metadata，`tools/profile_candidate_diff.py` 对比当前 `vehicle_profiles.json`；报告写入 ignored 的 `local_test_logs/`，不提交素材或报告。
- recovery 暂缓。

边界：
- 运行时不要把 `data_layer/` 当 Python 包 import；插件与数据层唯一运行数据边界是 HTTP :8112。
- L8 只负责可选启动/关闭自己拉起的 8112 数据层进程；已经存在的外部 :8112 服务不可接管或杀掉。
- vendored `data_layer/data process/` 源码与 profile JSON 可以作为显式数据层合同/profile 维护项更新，但不能把数据层内部模块耦合进插件主链路。
- 输出只走 adapters/neko_dispatcher.py。
- 不为本插件继续扩宿主核心专用逻辑；宿主侧能力后续应走通用 callback contract 接口。
- dry_run 默认开启，真机确认前不要关闭。
- Detector / Scenario / Arbiter 不承担文本过滤职责。

优先顺序：
1. L9 下一轮真机先复测机场起飞/复活阶段：记录 `radio_altitude_m` 是否可用，但不要把它当固定翼必备字段。保护期内不应播 `low_alt_danger`；AGL 可用时 `<=10m` 进入贴地滑跑保护、`>=40m` 解除；AGL 不可用时，保护期内且起落架放下/运动中才压制滑跑 `overspeed`，收轮后真实超速应恢复正常。失速、死亡等关键事件仍应能触发。同时观察真实开口时 `coalesce_key` / `event_expired` / `event_age_seconds` / `target_lanlan` 是否减少旧低空/超速提示晚到，`battle_reply_contract=short_tts_line` / `live_reply_contract=short_tts_line` / `max_reply_chars=28` / `host_callback_contract_version=neko.callback.v1` 是否进入 `last_output_status` 和真实 push metadata，并确认没有走宿主 fallback session。
2. 继续 M3 剩余验证：replay 真实样本验证、awards/free-text dry_run 安全合同、油温/动力故障字段策略；现场用 `tools/live_monitor.py` 先看 `Summary` 行，再看 `replay=suppressed(detector_suppressed/replay)`、输出阻断状态，以及 `FreeText detail` 中的 `awards=.../blocked` 等逐源摘要。
3. 继续真机 checklist，补 replay、awards/free-text dry_run 接缝；identity/ownership、`you_killed`、`you_died`、`low_fuel` 和真实 push 已有真机正向证据。
4. kill/death/hudmsg/combat.feed/awards 去桩前确认 T-Safety 合同与 `tools/free_text_gate.py` 仍覆盖 prompt / `push_message.parts[].text`。
5. L8 子进程最小编排已完成；2026-06-26 本地自验证确认 `data_layer.mode=managed/external` 可区分来源，插件 stop 会关闭 managed `8112`，不会误杀 external `8112`。
```

## 验证入口

从独立插件仓库 root 运行：

```powershell
uv run python tools\preflight.py --run
uv run python tools\release_readiness.py --run
uv run python tools\build_release_candidate.py
```

`build_release_candidate.py` 调用宿主官方 release check 构建包，再依次执行 `package_artifact_gate.py`、官方 payload hash verify 和隔离临时安装 smoke；只有全部通过才发布到 `dist`。它不替代源码侧 preflight，也不替代真机 smoke。已有同名文件时需显式加 `--force`，跳过重复 pytest 时需显式加 `--skip-tests`。

本地大样本汇总是可选慢检查，按需运行：

```powershell
uv run python tools\release_readiness.py --run --include-local-sample
```

把本地实机素材伪装成 `:8112` 数据层、让宿主/插件按真实轮询路径消费时，先在插件仓库启动样本回放服务，再启动 N.E.K.O 宿主和插件：

```powershell
uv run python tools\replay_8112_server.py local_samples\data_process_20260630 --port 8112 --player-name CN-Zephyr --end-offline
```

这个入口只打印帧数、索引、identity source 等摘要，不打印 raw combat.feed、HUD、chat 或 awards 文本。默认会把帧时间戳刷新成当前时间，避免真实输出新鲜度门禁把历史样本当旧事件丢弃；推荐非循环喂素材时加 `--end-offline`，样本播完后改为安全 offline/menu 帧，避免重启插件时反复消费最后一帧战斗事件；需要复现原始时间戳时再加 `--preserve-timestamps`。

旧样本缺少 `combat.feed[].is_my_*` 归属字段时，可在离线回放中显式指定身份并打开旧样本归属推断；需要给猫叠加聊天 / HUD / awards / 非我方 combat feed 干扰时，再打开干扰层：

```powershell
uv run python tools\replay_8112_server.py local_samples\data_process_20260620\captures\capture_20260620_191510\processed_8112.jsonl --port 8112 --player-name tl0sr2 --infer-ownership-from-player-name --inject-interference --speed 2 --end-offline
```

`--inject-interference` 仅用于本地压力测试：它会把 prompt 注入式 HUD、伪聊天、awards 原文和非我方 combat feed 噪声叠到样本上，用来验证 free-text 仍只走 observe / dry_run-only，不应进入真实播报。

单项排障时再分别运行：

```powershell
uv run python tests/run_logic_tests.py
uv run pytest -c tests\pytest.ini tests -q
uv run python tools\free_text_gate.py
uv run python tools\replay_gate.py
uv run python tools\proximity_gate.py
uv run python tools\v2_output_policy_gate.py
uv run python tools\v2_completion_gate.py --no-sample
uv run python tools\rc_handoff_report.py --no-sample
```

从 N.E.K.O 宿主仓库内做插件检查时，使用宿主路径：

```powershell
cd D:\Users\zheng\Documents\Code\N-E-K-O-Warthunder\N.E.K.O
uv run python -m plugin.neko_plugin_cli.cli check D:\Users\zheng\Documents\Code\N-E-K-O-Warthunder\project-N-E-K-O-Warthunder-8111-data-plugin
```

## 运行时启动注意（独立插件仓库）

本仓库是独立插件仓库；当前工作区里 `N.E.K.O\plugin\plugins\neko_warthunder` 必须是指向本仓库的 junction。手动启动宿主时，不要额外设置 `PLUGIN_CONFIG_ROOT` 指向外层工作区，否则宿主可能同时扫到 junction 和独立仓库目录，产生重复插件（例如 `neko_warthunder_1`）或加载旧副本。

```powershell
cd D:\Users\zheng\Documents\Code\N-E-K-O-Warthunder\N.E.K.O
uv run python launcher.py
```

如果 `GET http://127.0.0.1:48916/plugins` 没有列出 `neko_warthunder`，先调用：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:48916/plugins/refresh
Invoke-RestMethod -Method Post http://127.0.0.1:48916/plugin/neko_warthunder/start
```

若 `plugins/refresh` 看到 `neko_warthunder_1`，或把 `project-N-E-K-O-Warthunder-8111-data-plugin` 当成另一份插件，先检查 junction 与启动环境，不要继续真机测试。运行态烟测通过的判据是：只启动 `neko_warthunder`，Hosted UI context 返回 `state_empty=false`，actions 可见，且 `dry_run=true` 时 `test_say` 返回 `pushed=false, blocked="dry_run"`。

## 目录

```text
neko_warthunder/
├─ core/         contracts / scenario / arbiter / safety_guard / instructions
├─ adapters/     telemetry_client（拉 :8112）/ neko_dispatcher（唯一输出口）
├─ detectors/    condition（flag 边沿 FSM）/ discrete（按 id/跳变去重）
├─ contract/     真实 /api/telemetry 样本与契约检查
├─ ui/           Hosted UI 中文化面板，按连接/战场/安全/最近决策/最近输出分区
├─ i18n/         8 个宿主 locale 的插件名称与简介；面板正文当前仍以中文为主
├─ tests/        契约 / Detector / Arbiter / Scenario / integration 测试
├─ docs/         D-B1~B5 / 实现计划 / 待办事项 / 真机验证 checklist / recovery 测试方案
└─ data_layer/   合作者数据层，vendored，只通过 HTTP 消费
```

## 关键约束

- 数据层代码只作为 vendored 目录保存，插件侧不要修改、不要 import。
- `you_killed` / `you_died` 已消费 `combat.feed[].is_my_kill` / `combat.feed[].is_my_death`，2026-06-23 已完成陆战 dry_run 与 `dry_run=false` 真实 push 验证，空战 owned kill feed 也有正向证据。
- `tools/replay.py` 的内置合成场景已覆盖 v1.6 ownership 形状下的 `you_killed` / `you_died`。
- `overspeed` 已接入 `processed.flags` 中的 `overspeed_warn` / `overspeed_critical`；2026-06-23 真机 dry_run 已观察到 warning/critical flag、事件生成、Arbiter 放行和 Dispatcher dry_run。
- `low_alt_danger` 已增加起飞/滑跑保护：`takeoff_low_alt_grace_seconds` 默认 45s；若数据层提供 `radio_altitude_m`，插件按 `<=10m` 进入、`>=40m` 解除的 AGL 迟滞保护。离地判断统一优先 `radio_altitude_m`，有 AGL 时 prompt 不再复述 `altitude_m` 海拔；AGL 不可用时，滑跑超速兜底仅在保护期内且起落架放下/运动中生效，避免固定翼机场滑跑被误当空中超速，同时不吞掉收轮后的真实超速。
- 过热/炸缸真机 smoke 中，游戏 UI 已出现油温/发动机异常；插件侧已补 `hud_notices.feed[].code=engine_overheat/oil_overheat` 到 `overheat` 的映射，2026-06-23 已观察到 `overheat` dry_run 基础链路。2026-07-02 Su-30 真机样本与 gszabi99 FM `Temperature.Load*` 表已用于小批量 exact/family 温度阈值校准；Datamine 温度不得进入 `_default` 泛化，未真机验证条目也不得标 `_tested`。`powertrain_failure` 暂不直接提升为播报事件，但会以 `detector_suppressed/deferred_hud_notice` 记录到 T-Observe / live monitor，方便现场判断“识别到了但当前策略不播”。
- `replay: true` 已在 Detector 层静默并 reset，避免回放数据触发真实播报；运行态 observe 会记录 `detector_suppressed/replay`，`tools/live_monitor.py` 会汇总 `replay_degrade.status` 与 `output_blocked`，方便统一测试时解释“为什么没播”。后续仍需要真实 replay 样本验证。
- `/api/identity` 是 player_name 的主路径；插件侧 Hosted UI/context/action 接缝已完成，面板只支持手动填写玩家名并持久化到插件配置；2026-06-23 真机已验证手动身份会反映到 `combat.self.source=manual`，并能驱动 `is_my_kill` / `is_my_death` owned combat.feed 标记；`you_killed` post-fix dry_run 与 `dry_run=false` push 已通过陆战验证。
- `hud_notices` / `awards` 来自自由文本解析，真实播报前受 T-Safety 阻塞。
- V2 后方/尾随/目标点事件在真机证据补齐前受 `v2_live_verified_real_output_enabled=false` 保护：dry_run 仍可观察，真实输出默认被压住。

