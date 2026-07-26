# 实现计划（Codex 交接）：neko_warthunder v1

> 面向接手者的当前计划。本文以当前独立插件仓库为准，不再沿用“等待数据层补字段”的旧前提。

## 实现状态（2026-07-15）

### 2026-07-15 RC/UI 同步

- 当前工作分支为 `agent/isolate-cross-domain-runtime-state`，基线提交 `34f94cc` 已包含新版概览/诊断面板和两步首次使用教程；当前工作区继续补齐了独立活动页与安全活动摘要。先前宿主集成 PR `Project-N-E-K-O/N.E.K.O#2371` 已合并，当前专属 `warthuder` 分支用于后续插件同步维护。
- 面板维护已收口：安全暂停/自动保护与输出成功/失败判断统一，死样式和受控下拉框冗余属性已清理，设置弹窗中的重复“播报插话规则”已删除，概览底栏保留唯一常驻入口。
- 正式 pytest 基线为 `539 passed`。`tests/run_logic_tests.py` 已支持当前简单 `pytest.mark.parametrize` 隔离用例，一键逻辑自检与 pytest 统一为 `539/539`。
- **T-Safe-Activity 已完成**：运行时新增默认可见、最多 20 条的安全活动摘要；面板新增活动页和结果筛选。该通道不包含 raw text，也不打开 debug timeline。
- **R1 RC 稳定化已完成**：preflight/release-readiness 全部通过，独立源码与宿主面板副本一致。当前进入 R2 dry-run 真机证据补齐；未验证 V2/free-text 真实输出继续关闭。
- 最新交接入口：`docs/handoff-20260715.md`。

### 2026-07-10 真机同步

- 当时 `HEAD` 为 `4004873`，本地 `main` 领先 `origin/main` 1 个提交；该段保留为 2026-07-10 历史快照，当前状态以上方 2026-07-15 同步为准。运行目录 `N.E.K.O/` 不属于插件源码，不得加入提交。
- 打包版宿主 `D:\NEKO` 已验证能从 `C:\Users\zheng\AppData\Local\N.E.K.O\plugins` 发现并启动 `neko_warthunder`；现有 `:8112` 被正确识别为 external 数据层。
- 正式陆战娱乐模式本机验证为 `map_info.valid=true`、`in_battle=true`、`domain=ground`；退出战局后恢复 `not_in_battle/menu`。用户侧曾出现的“数据层健康但菜单态”未在本机复现，仍需受影响环境样本。
- 自己发送的固定无线电已两次真机 dry-run 成功，`进攻 D 点` 标准化为 `player_radio_command / attack_point / D`；手动 identity 匹配生效，raw sender/msg 不进入安全 payload。队友同口令不触发仍待真机反例。
- 陆战 P0 已修复：岗位状态改为多值合同，LWS 仅状态 `1` 告警，一级弹药增加正数基线和同车重生 reset/出生保护；状态 `3` 仍只透传。
- 可靠陆战事实：`crew_current/crew_total` 与真实乘员损失一致，但按当前产品策略只用于 DTO/面板，不生成猫娘播报。
- 当前顺序已更新为：RC 稳定化/全离线门禁 -> 队友无线电与 replay/free-text/V2/LWS dry-run 证据 -> 重新导包/安装 -> 最终小范围真实输出终验。

- M1 scaffold 已实现。
- M2 Battle Awareness 理解/决策主链路已实现。
- T1A Hosted UI Integration 已完成。
- T1B Minimal Panel 已完成。
- T4 集成测试已完成。
- Hosted UI surface/context/action smoke 已通过。
- T-Safety output text sanitizer 已完成。
- T-FreeText-Gate free-text release gate 已完成：`tools/free_text_gate.py` 使用合成恶意玩家名、HUD、combat feed、award payload 验证 prompt 与 `push_message.parts[].text` 不含 raw 文本，并已纳入 `tools/preflight.py`。
- T-FreeText-Observe 已完成：运行态首次看到 `awards` / `combat.feed` / `hud_notices` / `hudmsg` / `hud_events` 时记录 `detector_suppressed/free_text_blocked` 安全摘要；同时新增 `free_text_activity` dry-run-only 候选，用于验证 Detector / Arbiter / Dispatcher 决策链。`dry_run=false` 仍以 `free_text_dry_run_only` 阻断真实输出，不保留 raw 文本到 observe，也不让 raw 文本进入 prompt。
- T-Replay-Gate replay degrade release gate 已完成：`tools/replay_gate.py` 使用合成 `replay=true` 帧验证 Detector 不产出 candidate、Dispatcher 不构造 prompt、也不调用 `push_message`，并已纳入 `tools/preflight.py`。
- T-Deferred-HUD-Gate deferred HUD notice gate 已完成：`tools/deferred_hud_gate.py` 验证 `powertrain_failure` 当前只记录为可观测的 deferred 技术通知，不生成 Detector candidate / Dispatcher prompt / `push_message`，且 raw HUD 文本不泄露。
- 模式/领域边界已完成当前插件侧拆分：固定翼连续条件事件只允许 `domain == "air"` 触发；陆战状态播报只保留 `ground_laser_warning`。乘员、岗位和一级弹药 flags 不注册 Detector，仅用于 DTO/面板。输出层继续通过 Detector payload、Dispatcher prompt 和 `push_message.metadata.domain_prompt_contract` 保留模式合同。
- V2 proximity / objective awareness 非真机依赖部分已完成：`proximity.events` / `situation` 已进入 BattleState，DiscreteDetector 按 id 去重生成 `enemy_nearby` / `air_threat_nearby` / `enemy_on_six`，短窗连续近距离后方事件会保守升级为 `tailing_risk`，并从 `situation.ground_targets` 生成低优先级 `ground_target_nearby`。Arbiter 按低优先级门控，Dispatcher 只输出 safe generic 文案，Hosted UI context / 面板显示安全态势摘要。
- T-Proximity-Gate proximity / objective awareness gate 已完成：`tools/proximity_gate.py` 使用合成 proximity / situation DTO 验证 Detector / Arbiter / Dispatcher / `push_message.parts[].text` 的安全输出和门控关系，并已纳入 `tools/preflight.py` / `tools/release_readiness.py`。
- T-V2-Readiness V2 收口汇总已完成：`tools/v2_readiness.py` 将 proximity/objective 离线门禁和可选本地样本证据合并成一个安全报告，明确区分 `v2_offline_gate_complete` 与 `v2_live_evidence_complete`，避免把真机样本缺口误写成代码未完成。
- T-V2-Release-Matrix V2 能力矩阵已完成：`tools/v2_release_matrix.py` 将 `enemy_nearby`、`air_threat_nearby`、`enemy_on_six`、`tailing_risk`、`ground_target_nearby` 拆成 code/offline/live-evidence/real-output-policy 行，明确哪些能力已经代码/离线完成、哪些只差真机证据且保持 dry_run-first。
- T-V2-Output-Policy V2 真实输出策略门禁已完成：`tools/v2_output_policy_gate.py` 验证 `enemy_on_six`、`tailing_risk`、`ground_target_nearby` 在 `v2_live_verified_real_output_enabled=false` 时只允许 dry_run 可观察，真实 `push_message` 默认被 `v2_live_evidence_pending` 压住；显式开启后才允许真实推送。
- T-V2-Completion-Gate V2 完成度门禁已完成：`tools/v2_completion_gate.py` 汇总 readiness、能力矩阵和真实输出策略，给出 `v2_code_offline_complete_live_evidence_pending` 这类不夸大真机证据的收口结论。
- T-Final-Smoke-Packet 最终真机 smoke 交接包已完成：`tools/final_smoke_packet.py` 输出 `go_no_go`、`handoff_status`、必跑命令、V2 live evidence 缺口、runtime focus checks、remaining live actions 和 dry_run / raw text 安全边界；`tools/final_smoke_evidence_gate.py` 用于验收 smoke 后的 P1 evidence JSON，可用 `--from-live-monitor` 从安全 monitor JSON/JSONL 预填草稿，也可用 `--safe-transcript-template` / `--safe-transcript` 合并无原文的猫猫回复 metrics，并可通过 `--final-smoke-evidence` 接入 release/preflight 统一复验。
- T-Release-Readiness v1 RC 离线汇总入口已完成：`tools/release_readiness.py` 不启动前后端、不依赖 War Thunder，默认只聚合可自动化快门禁；本地大样本报告需显式加 `--include-local-sample`。`release_scope` 会拆分 `ship_status`、`real_output_blockers`、`sample_unproven_items` 与 `next_actions`；通过后再进入最后一轮真机 smoke。
- T-RC-Handoff-Report 维护者交接报告已完成：`tools/rc_handoff_report.py` 聚合 V1 release scope、V2 completion、final smoke go/no-go、安全边界和 remaining live actions，给出“V1 离线可交接 / V2 code+offline 完成 / live evidence pending”的人类可读报告。
- T-Package-Artifact-Gate 分发包内容门禁已完成：`tools/package_artifact_gate.py` 验证包身份、运行必需文件、路径安全和开发文件排除；本轮据此发现并清除了误入包内的 `.ruff_cache`。
- T-RC-Builder 原子 RC 构建入口已完成：`tools/build_release_candidate.py` 串联宿主官方 release check、分发包内容门禁、官方 payload verify 和隔离临时安装 smoke，全部通过后才发布最终文件；默认不覆盖已有包，也不写入真实插件目录。
- T-Observe runtime decision timeline 已完成轻量实现：普通模式只保留最近摘要，debug 模式使用内存 ring buffer。
- 最后一次完整 pytest 基线为 `539 passed`；逻辑自检为 `539/539 passed`。播报偏好、频率设置和安全活动中心已完成离线实现，数据层 P0、UI 隔离、package artifact gate 和统一 RC 构建演练已有通过记录；聚焦真机 dry-run 按当前决定延期。
- 播报偏好阶段已完成：设置页提供安静/标准/活跃三档非危急节奏，以及一般安全、战果、固定无线电、态势感知、开场收尾五类开关；可一键恢复标准频率和全部普通类别，且不会改动昵称、插话规则、`dry_run` 或播报启停状态；critical 安全和阵亡提醒不允许被偏好关闭。
- 安全诊断摘要已完成：诊断页可复制版本化白名单摘要，只包含连接、模式、安全控制、播报偏好和最近决策/输出代码；不包含身份、聊天/HUD、目标、载具、URL/PID、异常原文或 prompt/payload 原文，概览主界面不变。
- 离线 readiness 与真机监控工具链已补齐：`tools/sample_replay.py` 负责样本覆盖率与 `session_summary`，并能用 candidate/chosen/output 计数证明 `replay=true` 样本被静默，同时统计 V2 proximity/situation/ground-target 覆盖率、后方近距样本、`tailing_risk` 触发和 3000m 内任务目标点候选；`tools/offline_report.py` 负责安全 Markdown / JSON 汇报，并输出 Next test focus；`tools/live_test_plan.py` 负责把 P1/P2 待测项展开为下一轮真机 Operator quick checklist 和“操作 / 监控 / 通过 / 失败 / 数据层缺口”清单，包含 `fly_closer_to_ground_target_sample`；`sample_replay` / `offline_report` / `live_test_plan` 三个出口都会带上 T-Output 背压、T-Kill-Coalesce 多杀合并和 V2 proximity 后方样本复测项，`next_steps` 也会列出这些现场动作但状态仍按样本/数据缺口判定；`tools/live_monitor.py` 负责真机测试时安全汇总 health、context、telemetry ownership 计数、free-text dry_run-only 状态与逐源 blocked 摘要、replay 降级状态、T-Observe 摘要、`selected` / `dry_run_enabled` / `free_text_blocked` / `kill_coalesced` / `output_backpressure` / `event_expired` 等可行动原因与日志异常计数；`tools/preflight.py` 已把 runtime smoke 纳入门禁，dry-run 会先打印 Quick read，`--run` 通过/失败时会直接提示继续 dry_run 真机验证或停止排障。
- 数据层 `v1.6` 已合并，包含：
  - `overspeed_warn` / `overspeed_critical`
  - enhanced `combat.feed`
  - `is_my_kill` / `is_my_death`
  - `/api/identity`
  - `replay: true` 回放降级
  - `hud_notices`
  - `awards`
- 真机/数据层/真实开口接缝仍未完整验证；2026-06-23 已完成数值安全与 owned kill/death smoke，覆盖超速 warning/critical、低油 warning/critical、低空 warning/critical、失速 warning/critical、过热 warning/critical、手动 identity、air/ground owned combat.feed 归属、`you_killed` / `you_died` dry_run，以及 `dry_run=false` 真实 push 输出。
- recovery 仍暂缓，不打开 `wants_recovery`。

## 当前边界

- 插件与数据层唯一数据边界是 HTTP `:8112`，主入口是 `/api/telemetry`；L8 只负责可选启动/关闭自己拉起的 vendored 数据层进程。
- 运行时不把 `data_layer/` 当 Python 包 import；插件主链路与数据层唯一运行数据边界是 HTTP :8112。vendored `data_layer/data process/` 源码与 profile JSON 可以作为显式数据层合同/profile 维护项更新，后续仍以整包合并或明确的数据层维护任务为主。
- 输出只走 `adapters/neko_dispatcher.py`。
- dry_run 默认开启；真机确认前不要关闭。
- Detector / Scenario / Arbiter 只处理事件语义，不承担自由文本过滤职责。
- 不可信自由文本只能在 `NekoDispatcher` / prompt builder 前完成 sanitize 后进入 prompt；raw 玩家名、hudmsg、combat.feed、awards 原文只进 audit/debug。

## 成本变更讨论门禁

凡是插件内改动会引入或明显增加以下任一成本，都必须先讨论再实现，不直接落代码：

- 计算成本：新增高频轮询、复杂扫描、CPU/内存占用、常驻缓存、后台进程或更大的运行态状态。
- Token 成本：新增 prompt 内容、上下文注入、额外 LLM 调用、更多 `push_message` 或更长回复合同。
- 依赖成本：新增 Python/Node 依赖、外部服务、平台工具、数据文件或需要安装/打包的新组件。
- 核心逻辑成本：改变 Detector / Scenario / Arbiter / Dispatcher 的主路径、事件优先级、真实输出策略、去重/coalescing、宿主接口边界或数据层契约。
- 维护成本：新增长期门禁、复杂配置、需要人工持续校准的数据库/profile、跨仓库同步要求。

讨论输出不能只是普通说明文，必须列出需要拍板的点：

- 是否真的要做：当前痛点、已有证据、如果不做会怎样。
- 成本类别和上限：CPU/内存、token、依赖、核心复杂度分别会增加什么，预期上限是多少。
- 可选方案：至少列出保守方案、完整方案和不做/延后方案。
- 默认开关：是否默认关闭、是否只在 dry_run/debug/local sample 下启用、是否需要真机证据后再打开。
- 边界影响：是否触碰宿主核心、数据层、输出真实播报、隐私/raw text、现有插件接口。
- 验收方式：离线测试、样本回放、真机观察项、通过/失败判据。
- 回滚方式：如何关闭、删除或降级，是否会留下状态/缓存/配置兼容问题。
- 需要谁拍板：维护者/组长需要明确同意的选项和阈值。

## 分层状态

- L0 plugin scaffold / contracts：完成；`contract/telemetry_sample.json` 已补脱敏 v1.6 形状样本，真机验证时仍可另抓当前环境帧到 `.gitignore` 忽略的 `local_samples/` 做对照。
- L1 telemetry client：完成基础解析；已纳入 `hud_notices.feed` 与 `replay`，仍需要验证 data-layer `v1.6` 其他新字段。
- L2 BattleState：完成基础装配；已纳入 v1.6 DTO seam 和 V2 `proximity` / `situation` 字段。
- L3 Scenario：完成；`replay: true` 已在 DetectorEngine 静默并 reset，且 T-Observe 会记录 `detector_suppressed/replay`，T-Live 会显示 `replay=suppressed(detector_suppressed/replay)` 与输出阻断状态；仍需真实 replay 样本验证。
- L4 Detector：已实现主链路；`overspeed` 已在真机 dry_run 中验证 `overspeed_warn` / `overspeed_critical`；`low_fuel` 已在真机 dry_run 中验证 warning / critical；`low_alt_danger`、`stall_risk`、`overheat` 均已观察到 warning / critical 基础链路；`you_killed` / `you_died` 已消费 `combat.feed[].is_my_kill` / `combat.feed[].is_my_death`，按已播报 owned feed id 去重并允许同 id 后补 ownership 补触发，离线 replay 合成场景也已覆盖该形状；V2 `ProximityDetector` 已消费 data-layer `proximity.events` 并按 id 去重。
- L4-Domain：完成当前空/陆分界。固定翼条件 detector 通过 domain predicate 只读空战帧；陆战状态 detector 只读取 `laser_warning` 并输出 `ground_laser_warning`，非 `ground` 域静默 reset。乘员、岗位和弹药 flags 不产生候选。Detector 产出的其他事件继续携带 `domain`，供 Dispatcher 和 evidence 使用。
- L5 Arbiter：完成；`SPAWNING` 仍压制飞行安全误报，但已允许 owned combat kill 事件通过，避免真实击杀在出生 grace 内被误压。后续 M3 适配时要保持 cooldown、优先级、Scenario 门控语义不变。
- L6 Dispatcher / instructions：完成基础输出；T-Safety 已在 prompt builder 前接入，prompt / `push_message.parts[].text` 不允许包含 unsafe raw。Dispatcher 会按 `domain` 写入 `当前模式` 合同：空战=后座/僚机，直升机=机组搭档，陆战=车组搭档，海战=舰桥观察员；同一合同也进入 `push_message.metadata.domain_prompt_contract`，用于 live monitor / final smoke evidence 复核模型是否串模式。
- T-FreeText-Gate：完成；`tools/free_text_gate.py` 是 hudmsg / combat.feed / awards 去桩前的离线发布门禁，preflight 默认执行。
- T-Replay-Gate：完成；`tools/replay_gate.py` 是 `replay=true` 降级安全的离线发布门禁，preflight 默认执行。
- T-Proximity-Gate：完成；`tools/proximity_gate.py` 是 V2 proximity / objective awareness 的离线发布门禁，preflight / release readiness 默认执行。
- T-V2-Output-Policy：完成；`tools/v2_output_policy_gate.py` 是 V2 真机证据未齐前的真实输出保护门禁，preflight / release readiness 默认执行。
- T-V2-Completion-Gate：完成；`tools/v2_completion_gate.py` 是 V2 code/offline 完成度的单一 pass/fail 收口门禁，preflight / release readiness 默认执行。
- T-RC-Handoff-Report：完成；`tools/rc_handoff_report.py` 是维护者/合作者交接报告入口，preflight / release readiness 默认执行，不替代 final live smoke。
- L7 safety guard + Hosted UI：完成；Hosted UI 已按概览/活动/诊断/设置四类任务收口，新手教程负责昵称与关键按钮说明。安全状态和输出结果使用统一 helper，重复插话规则入口与死样式已删除，常见标签/状态值使用中文显示。
- V2 proximity / objective awareness：完成非真机依赖部分；普通接近 `enemy_nearby` 和任务目标点 `ground_target_nearby` 为低优先级，COMBAT_STRESS 下被压住；`air_threat_nearby`、`enemy_on_six` 与保守持续后方威胁 `tailing_risk` 可在 IN_FLIGHT / COMBAT_STRESS 下进入提示队列；CRITICAL_RISK / SPAWNING / DEAD 等场景仍按 Arbiter 门控丢弃。Dispatcher 不复读 raw proximity 文本或目标 label，只使用方位、钟点、距离、网格等安全 metadata。
- T-Observe runtime decision timeline：完成轻量实现；Hosted UI context 暴露 `observe.last_event` / `last_decision` / `last_output_status`，debug timeline 默认关闭。
- T-Output output backpressure guard：完成轻量实现；真实 `push_message` 前会在 `output_backpressure_seconds` 窗口内压住同优先级或更低优先级事件，减少主机回复队列堆积；`you_killed`、`you_died` 和 critical 安全事件仍可通过，避免击杀夸夸被普通过载背压吃掉。Arbiter 窗口 flush 不再刷新连续告警的事件时间戳，避免旧低空/超速提示被伪装成新事件。危急动作类默认走 bounded `respond` 并进入宿主 TTS；仅显式开启兼容开关时才以插件短句 `blind+plugin` 直出。开局、击杀/阵亡、过热、低油、普通接近、目标点和结算走 bounded `respond`。真实战场输出统一带 `coalesce_key=neko_warthunder:battle_event`；`output_event_max_age_seconds` 会在真实 push 前丢弃过期旧事件，同类安全提示短窗重复会记录为 `repeated_event_collapsed`，减少死亡后补播旧低空/超速提示和连续“松杆/过载”刷屏。真实输出还会附带 `event_age_seconds` / `event_expires_at`、可解析到的 `target_lanlan`、短播报 metadata（`battle_reply_contract=short_tts_line` / `live_reply_contract=short_tts_line` / `max_reply_chars=28`）、`plugin_owned_output`、`dialogue_policy_owner=plugin` / `plugin_dialogue_policy` / `plugin_quiet_window_policy` 和通用 delivery-only `host_callback_contract.version=neko.callback.v1` 预留块，用于下一轮真机判断晚播到底来自插件过期保护、重复折叠、宿主队列、fallback session，还是插件自身输出策略。宿主核心区先冻结，不为战雷插件写专用发言特判。
- T-Kill-Coalesce 多杀合并：完成轻量实现；`you_killed` 会在 `kill_coalesce_window_seconds` 窗口内合并为一条 `kill_count` 事件；`CRITICAL_RISK` 下 owned kill 会延迟保留为 `kill_deferred_critical_risk`，危急解除后再 flush；死亡 / critical 抢占仍会清空待播击杀。
- L8 数据层并入：vendored 数据层已合并；插件侧最小子进程编排已完成，支持 `data_layer_auto_start`、managed/external 判定、shutdown 只关闭自己拉起的进程，并通过 Hosted UI/status 暴露 `data_layer` 状态；2026-06-26 已本地自验证 managed/external 生命周期边界。
- L9 真机调参：进行中；已完成起飞/复活保护。离地/低空判断优先使用 `radio_altitude_m`，`altitude_m` 只作为 MSL/海拔事实；但固定翼不假定必有 AGL，`takeoff_low_alt_grace_seconds=45` 仍作为低空保护主兜底。`takeoff_radio_altitude_enter_m=10` / `takeoff_radio_altitude_exit_m=40` 用于 AGL 可用时的贴地迟滞；AGL 缺失时，滑跑超速只在保护期内且起落架放下/运动中时压制，不影响收轮后真实超速，也不影响失速、死亡、过热或低油事件。已补真实 push TTL 过期丢弃与通用 `host_callback_contract` 预留，减少插件侧旧事件推送，并为后续宿主通用队列 coalescing 留好接口。T-Live 只读监控工具可用于下一轮真机统一测试归档。

## T-Safety：output text sanitizer

状态：已完成。

目标：防止猫娘复读不良玩家 ID、hudmsg、combat.feed、awards 原文，避免辱骂、涉政、擦边、仇恨、广告、联系方式、奇怪符号或 prompt injection 文本进入猫娘输出。

放置位置：`NekoDispatcher` / prompt builder 前。

关键策略：

- raw 只进 audit/debug。
- safe 才能进 prompt。
- 默认 generic 文案，不朗读陌生玩家名。
- 不确定时宁可不读原文。
- 不做复杂 NLP，不做大模型审核。

当前阻塞关系：

- T-Safety 本身不再阻塞；它已经作为输出安全前置层落地。
- kill/death/hudmsg/combat.feed/awards 正式播报仍需真机 dry_run 验证和对应去桩。
- 不阻塞 stall/low_alt/overheat/low_fuel/overspeed 等数值安全事件。

已覆盖测试：

- sanitizer 单测。
- dispatcher prompt 测试。
- `push_message.parts[].text` 不包含 unsafe raw 的合同测试。
- hudmsg / combat.feed / awards 常见自由文本字段族即使内容看似普通，也默认 blocked，不进入 safe prompt payload。
- `tools/free_text_gate.py` 已作为额外离线门禁，覆盖 prompt、真实 `push_message.parts[].text` 和 sanitizer safe payload 三层；该门禁通过前不得开放 hudmsg / combat.feed / awards 真实播报。

## M3：适配数据层 v1.6 DTO

数据层 v1.6 已合并，M3 的当前定义是插件侧适配和验证：

- `overspeed`：读取 `processed.flags` 中的 `overspeed_warn` / `overspeed_critical`；2026-06-23 已真机 dry_run 验证 warning/critical 事件链路。
- `you_killed`：已监听 `combat.feed[]` 中 `is_my_kill == true` 的未播报 owned id；同 id 后补 ownership 时可补触发。短窗多杀已在 Arbiter 合并为单条 `kill_count` 输出；危急场景中不抢播、不丢弃，待 `CRITICAL_RISK` 解除后补播。
- `you_died`：已监听 `combat.feed[]` 中 `is_my_death == true` 的未播报 owned id；同 id 后补 ownership 时可补触发。不再把 `vehicle_valid` 跳变当作唯一可靠死亡信号。
- `player_name`：通过 `/api/identity` 或启动参数建立权威身份；插件侧 Hosted UI/context/action seam 已完成，面板只支持手动填写、保存和清除玩家名，并会持久化后在启动时恢复到数据层。2026-06-23 真机已验证 `combat.self.source=manual` 与 `is_my_kill` / `is_my_death` owned 路径。`you_killed` 候选曾被 `SPAWNING` 门控压住，已修复；post-fix dry_run 与 `dry_run=false` push 已通过陆战验证。
- `you_killed` / `you_died` 输出事实：已按 `domain` / `cause` 分流空战、直升机、陆战、海战与坠毁措辞，避免陆战击杀出现“击落坦克”，并避免 prompt 复读 raw victim 玩家名。地面战果和地面状态 prompt 必须使用车组 / 装填 / 掩体 / 看路等陆战语境，不得串到升空 / 后座 / 云霄等固定翼语境。
- `replay: true`：已在 DetectorEngine 静默并 reset，避免回放触发真实播报；T-Observe 会把原因记录为 `detector_suppressed/replay`，`tools/live_monitor.py` 会汇总为 `replay_degrade.status=suppressed` / `output_blocked=true`；仍需真实 replay 样本验证。
- `overheat`：已接入 `hud_notices.feed[].code` 中的 `engine_overheat` / `oil_overheat`，以 code-only safe payload 生成现有 `overheat`；`powertrain_failure` 暂不直接播报，但会以 `detector_suppressed/deferred_hud_notice` 记录到 T-Observe / live monitor。
- `hud_notices` / `awards`：属于自由文本风险路径，真实播报前必须先过 T-Safety。

## 真机验证

真机 checklist 从“等字段”改为“验证 v1.6 DTO 接缝”。见 `docs/真机验证-checklist.md`。2026-06-23 已完成数值安全 dry_run、owned kill/death dry_run、以及 kill/death `dry_run=false` push smoke；每轮测完后，用 `docs/真机测试结果-template.md` 记录聚合统计、安全摘要和结论；不要提交 raw 玩家名、raw HUD 文本、raw combat.feed 或 awards 原文。

需要重点确认：

- `/api/telemetry` 是否返回 `replay`。
- `/api/telemetry.processed.flags` 是否出现 `overspeed_warn` / `overspeed_critical`（2026-06-23 已通过真机 dry_run）。
- `/api/telemetry.combat.feed[]` 是否含稳定递增 id、`is_my_kill`、`is_my_death`。
- `/api/identity` 是否能由 Hosted UI 面板设置/清除权威 player_name，并反映到 `combat.self` 与 kill/death 归属标记（2026-06-23 已有真机正向证据；`you_killed` 不再被 `SPAWNING` gate 压住）。
- `hud_notices` 中的技术 code 是否能触发安全事件；raw notice 文本、`awards` 是否只进入 debug/audit 或被 T-Safety 阻断，不直接进入 prompt。
- T-Observe 的 `observe.last_decision` / `observe.last_output_status` 是否能解释未播、晚播、dry_run 输出或 dispatcher 失败。

## 推进顺序

1. **R1 RC 稳定化（已完成）**：独立源码与宿主集成面板副本一致；`tests/run_logic_tests.py`、pytest、`tools/preflight.py --run` 和 `tools/release_readiness.py --run` 全部通过。
2. **R2 无线电与安全反例**：真机验证队友发送同一固定口令不会产生 `player_radio_command`；继续保持 raw sender/msg 不进入 observe/prompt。补 replay 真实样本和 awards/free-text dry_run blocked 摘要。
3. **R2 V2/L9 证据**：将已有后方/六点钟与持续尾随录制纳入正式 evidence gate，并补 3000m 内目标点样本；同时复测机场起飞/复活、AGL 可用/缺失、滑跑超速保护、失速/死亡不被误压。
4. **R2 输出链路**：用 T-Observe/T-Live 确认 `event_expired`、critical 替换、用户聊天静默、`target_lanlan`、短单行回复合同和通用 callback metadata；信息确实不足时才扩 debug timeline。
5. **R3 最终 RC smoke**：安装新包，先 dry-run 保存安全 evidence，再做已经批准的小范围 `dry_run=false` 终验。V2 后方/尾随/目标点与 free-text 未通过各自真机证据前继续保持真实输出关闭。

## 已知坑 / 不要回退

- 不要把 `data_layer/` 当 Python 包 import；`data process` 目录名带空格。
- 不要把自由文本过滤塞进 Detector / Scenario / Arbiter。
- 不要复活旧的 `vehicle_valid` 作为 `you_died` 主路径。
- 不要把 recovery 作为 v1 当前任务；它只保留测试方案和 TODO。
- 不要沿用旧的 pre-T-Safety / pre-free-text-gate / pre-identity / pre-T-Output / pre-T-Kill-Coalesce / pre-L8 / pre-L9-takeoff-grace / pre-output-coalescing / pre-event-expiry / pre-T-UI2 / pre-deferred-hud-notice / pre-radio-altitude / pre-V2-proximity / pre-rc-docs-audit / pre-tailing-risk / pre-free-text-observe / pre-v2-evidence-refinement / pre-release-scope / pre-release-json-cleanliness / pre-v2-readiness / pre-final-smoke-packet / pre-release-defaults-gate / pre-v2-completion-gate / pre-free-text-activity / pre-critical-risk-kill-defer / pre-output-freshness-metadata / pre-output-freshness-gate / pre-host-contract-gate / pre-ownership-replay-gate / pre-final-smoke-evidence-gate / pre-host-callback-contract-reservation / pre-datamine-profile-batches / pre-vehicle-profile-id-audit / pre-domain-runtime-isolation / pre-UI-redesign / pre-package-artifact-gate / pre-rc-builder / pre-broadcast-preferences / pre-safe-activity 测试数量；当前最后一次完整 pytest 为 `539 passed`。
- 不要在父仓库 `N.E.K.O` 里提交这个独立插件仓库。

