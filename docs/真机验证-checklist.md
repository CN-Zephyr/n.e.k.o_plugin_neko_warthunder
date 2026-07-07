# 真机验证 checklist

> 当前 M1/M2 主链路、Hosted UI、T4 集成测试、T-Safety output text sanitizer、T-FreeText-Gate free-text release gate、T-Release-Defaults-Gate 发布默认值门禁、T-Output-Freshness-Gate 输出新鲜度门禁、T-Host-Callback-Contract-Reservation 通用宿主 callback contract 预留、T-Host-Boundary-Gate 宿主无战雷专用发言逻辑边界门禁、T-Ownership-Replay-Gate 第三方样本 ownership 回放门禁、T-FreeText-Observe free-text blocked runtime observe、T-Replay-Gate replay degrade release gate、T-Deferred-HUD-Gate deferred HUD notice gate、T-Proximity-Gate proximity/objective awareness gate、T-Vehicle-Profile-ID-Audit 载具 id 口径门禁、T-V2-Readiness V2 收口汇总、T-V2-Release-Matrix V2 能力矩阵、T-V2-Output-Policy V2 真实输出策略门禁、T-V2-Completion-Gate V2 完成度门禁、T-Final-Smoke-Packet 最终真机 smoke 交接包、T-Final-Smoke-Evidence-Gate 最终真机 evidence 验收、T-RC-Handoff-Report 维护者交接报告、T-Release-Readiness 离线汇总入口、T-Observe runtime decision timeline、T-Live live monitor summary tool、T-Output output backpressure guard、T-Kill-Coalesce 多杀合并、L8 data-layer subprocess orchestration、identity Hosted UI/action 接缝、L9 起飞/滑跑保护、V2 proximity/objective awareness、真实战场事件队列 coalescing、事件过期丢弃、输出新鲜度 metadata、`target_lanlan` 目标会话透传、插件内短播报策略（`dialogue_policy_owner=plugin` / `plugin_dialogue_policy` / `short_tts_line` / `max_reply_chars=28`）、通用 delivery-only `host_callback_contract.version=neko.callback.v1` metadata、Hosted UI 信息架构整理、deferred HUD notice 可观测性与 `free_text_activity` dry-run-only 候选链路、Datamine profile 候选抽取/差异报告、固定翼全量补库、vehicle profile economy metadata 回填和结构过载/燃油/发动机惯性证据入库已完成；逻辑自检以 `442/442 passed` 为准。数据层 `v1.6` 已合并，真机验证目标从“等待字段”改为“验证 v1.6 / V2 DTO 接缝”。宿主核心区先冻结，不继续为本插件扩专用逻辑；战雷发言时机和回复形态收在插件内部。

> 2026-07-07 更新：模式边界已拆分，固定翼连续条件事件只允许 `domain == "air"`，陆战新增 `ground_laser_warning`、`ground_crew_loss`、`ground_ammo_empty`、`ground_ammo_low` 四类正式候选。下一轮陆战真机可观察这些候选是否只在 `domain == "ground"` 出现、是否不进固定翼 `CRITICAL_RISK`、是否不复用空战话术。

## 已完成的 Hosted UI Smoke

- 宿主可发现 `neko_warthunder` Hosted UI surface `main`。
- `dashboard` context 可返回面板状态。
- `set_dry_run` / `pause` / `resume` / `test_say` 可通过 Hosted UI action 调用。
- action 后 context 刷新符合预期。
- 未发现 `PLUGIN_UI_ACTION_FAILED`。

## 已完成的真机 dry_run Smoke（2026-06-21）

- 三个 health 均正常：主后端 `48911`、Hosted UI `48916`、数据层 `8112`。
- Hosted UI `dashboard` context 可持续返回 `dry_run`、连接状态、scenario、safety、observe last decision/output。
- T-Observe 普通模式已可通过 `observe.last_event` / `observe.last_decision` / `observe.last_output_status` 辅助判断链路停在哪一步；debug timeline 默认关闭。
- `pause` 已验证：`safety.status=paused`、`manual_paused=true`，风险事件被 Arbiter 以 `reason=paused` suppress。
- `resume` 已验证：`safety.status=running`、`manual_paused=false`，恢复后 `low_alt_danger` 可被 Arbiter allowed 并进入 dry_run dispatcher。
- `test_say` 已验证：宿主日志出现多条 `TRIGGER entry='test_say'`，未出现 `PLUGIN_UI_ACTION_FAILED`。
- `set_identity` 已通过 Hosted UI/action 链路接入；面板只支持手动填写/保存/清除玩家名，并会持久化后在下次启动恢复到数据层。
- 数值安全链路已观察到：`stall_risk`、`low_alt_danger`，并保留此前 `overspeed`、`low_fuel`、`you_died` dry_run 观察结论。
- 未发现 Traceback / ERROR / TTS push 报错。

## 已完成的真机 dry_run Smoke（2026-06-23）

- 三个 health 均正常：主后端 `48911`、Hosted UI `48916`、数据层 `8112`；测试结束后端口已关闭。
- 同日追加空战 dry_run 监控中，`:8111` 原生遥测和 `:8112` 数据层正常，插件日志链路正常；该轮 `48911` / `48916` 未监听，因此只作为运行主链路证据，不替代 Hosted UI smoke。
- Hosted UI context 持续返回 `dry_run=true`、`conn_state=in_battle`、scenario、safety、`observe.last_event`、`observe.last_decision`、`observe.last_output_status`。
- `spawn` 已进入 Arbiter allowed，并由 Dispatcher 走 dry_run。
- `overspeed_warn` / `overspeed_critical` 已由数据层 `processed.flags` 触发；插件生成 `overspeed/enter`，Arbiter allowed，Dispatcher dry_run 输出。
- `low_fuel` 已观察到 warning / critical dry_run 输出；后续重复低油在 `COMBAT_STRESS` / `CRITICAL_RISK` 下可被 scenario gate 丢弃。
- `low_alt_danger` 已观察到 warning / critical dry_run；重复 critical 命中时可被 cooldown 丢弃。
- `stall_risk` 已观察到 warning / critical dry_run；critical 可由 Arbiter 以 `reason=preempt` 放行。
- `overheat` 已观察到 warning / critical dry_run；后续重复 critical 命中可被 cooldown 丢弃，说明基础链路和 cooldown 都可解释。
- `you_died` 已观察到 `critical` 事件并 dry_run 输出；不把 `vehicle_valid` 跳变作为主路径。
- 追加空战监控确认坠毁类 `combat.feed` 可产生 `is_my_death=true`，插件生成 `you_died/enter/critical`，Arbiter 以 `preempt` 放行，Dispatcher 输出 dry_run。
- 手动 identity 接缝已验证：Hosted UI 设置玩家名后，数据层返回 `combat.self.source=manual`，并观察到 owned `combat.feed[].is_my_kill=true` / `is_my_death=true` 路径。
- `you_killed` 已由 owned combat.feed 产生并 dry_run 输出；此前 `SPAWNING` 门控问题已修复。
- 2026-06-28 空战 dry_run 复测确认：数据层能连续给出 `is_my_kill=true`，旧策略会在 `CRITICAL_RISK` 下把 `you_killed` 作为 `scenario_gated` 丢弃；现已改为 `kill_deferred_critical_risk` 延迟保留，危急解除后按 `kill_coalesced` 补播，下一轮需重启插件复测运行态。
- ownership 后补已修复：若 combat feed 先以未归属 / 自由文本形态出现，后续同一 feed id 变为 `is_my_kill=true` 或 `is_my_death=true`，Detector 仍会补发 `you_killed` / `you_died`；已播报过的 owned id 不会重复触发。仍建议在进战局前设置 `/api/identity`，减少数据层归属延迟。
- T-Observe 普通模式已能解释 allow / preempt / cooldown / dry_run 输出；debug timeline 仍默认关闭。
- 未发现 `PLUGIN_UI_ACTION_FAILED`、后端 Traceback、TTS/push 报错。
- 已知数据层问题：`/api/telemetry.telemetry` 字段为空，但 `processed.*` 可用；map/profile 轮询曾持续出现 `_merge_profile() missing ... army and family_rules`。该签名回归已补代码修复和测试；下次重启数据层后确认日志不再重复。

## 已完成的 kill/death 与真实 push Smoke（2026-06-23）

- 空战 owned kill：数据层返回 `domain=air`，`combat.feed` 出现 `is_my_kill=true`；用于确认 air combat.feed ownership 字段可用。
- 空战 owned death：数据层返回 `domain=air` 且新 `combat.feed` 出现 `is_my_death=true`；插件生成 `you_died`，Arbiter preempt，Dispatcher dry_run 输出。
- 陆战 owned kill：数据层返回 `domain=ground`，`combat.feed` 多条 `is_my_kill=true`；插件生成 `you_killed`，Arbiter allowed，Dispatcher dry_run 输出。
- 陆战 owned death：数据层返回 `combat.feed` 中 `is_my_death=true`；插件生成 `you_died`，Arbiter allowed，Dispatcher dry_run 输出。
- `dry_run=false` 真实 push：关闭 dry_run 后，`test_say`、`you_killed`、`you_died` 均进入 proactive bridge / `push_message` 链路；Hosted UI `observe.last_output_status` 显示 `dispatcher_pushed` / `push_message_accepted`。
- 现场确认猫娘实际开口；未发现 `PLUGIN_UI_ACTION_FAILED`、Traceback、TTS/push 报错。
- 记录边界：本节只记录聚合结论，不写 raw 玩家名、raw combat.feed 原文或 raw HUD 文本。

## 已完成的 L8 数据层生命周期自验证（2026-06-26）

- managed 模式：基线 `48916` / `8112` 均关闭；启动宿主后调用 `/plugins/refresh` 与 `/plugin/neko_warthunder/start`，插件自动拉起 `8112`，Hosted UI context 返回 `data_layer.mode=managed`、`started_by_plugin=true`、`health=true`。
- managed 关闭：调用 `/plugin/neko_warthunder/stop` 后，插件自己拉起的 `8112` 退出，`8112/health` 不再可连接。
- external 模式：手动预先启动 vendored `wt_server.py --port 8112` 后再启动插件，Hosted UI context 返回 `data_layer.mode=external`、`started_by_plugin=false`、`health=true`。
- external 关闭：调用 `/plugin/neko_warthunder/stop` 后，外部 `8112` 仍可访问且未被误杀。
- 测试结束后已清理本轮宿主与外部数据层进程，`48911` / `48916` / `8112` 均关闭。

待复核：

- replay 降级：插件侧离线合同已覆盖 Detector 静默、`detector_suppressed/replay` 观测记录和 `live_monitor` 的 `replay_degrade` 汇总；仍需真实 `replay=true` 样本验证。
- 油温/发动机细项：过热基础链路已过；油温 / 发动机温度数据库和 `powertrain_failure` 策略仍后置，`powertrain_failure` 暂不直接播报，但应在 T-Observe / live monitor 中显示为 `detector_suppressed/deferred_hud_notice`。

## 下一轮统一测试现场顺序

> 目标：先在 `dry_run=true` 下验证 v1.6 DTO 接缝和 T-Observe 解释能力；只有数值安全事件 dry_run 稳定后，才考虑 `dry_run=false`。

1. **离线门禁**：按 `docs/统一测试前-离线检查.md` 跑完逻辑测试、pytest、release defaults gate、output freshness gate、host boundary gate、free-text release gate、replay degrade gate、ownership replay gate、deferred HUD notice gate、proximity/objective awareness gate、V2 readiness summary、V2 release matrix、V2 output policy gate、V2 completion gate、RC handoff report、final smoke packet、plugin check、合成 replay；进入最终真机前可直接运行 `uv run python tools\release_readiness.py --run`。本地大样本 replay / offline report / live test plan 作为显式样本证据，只有需要纳入同一轮汇总时才加 `--include-local-sample`。host boundary gate 用于确认没有为战雷插件提交宿主核心专用发言逻辑。
2. **启动链路**：启动 N.E.K.O 宿主、Hosted UI、数据层 `:8112`，确认三项 health 正常。
   - 当前工作区通过 junction 挂载独立插件仓库；手动启动宿主时不要设置 `PLUGIN_CONFIG_ROOT` 指向外层工作区，避免重复扫到独立仓库目录或加载旧副本。若宿主没有发现 `neko_warthunder`，先检查 `N.E.K.O\plugin\plugins\neko_warthunder` 是否仍是指向独立仓库的 junction，再调用 `/plugins/refresh` 与 `/plugin/neko_warthunder/start`。
   - 若出现 `neko_warthunder_1`，或 `dry_run=true` 下 `test_say` 返回 `pushed=true`，说明运行副本没有对齐；先停止测试并修复运行路径。
   - Hosted UI 侧以 context `state_empty=false`、actions 包含 `set_dry_run` / `pause` / `resume` / `test_say` / `set_identity` 作为注册通过信号。
3. **打开面板**：确认 `dry_run=true`，观察 `connected` / `conn_state` / `in_battle` / `scenario` / `safety` / `observe.last_decision` / `observe.last_output_status`。
   - 面板应按连接状态、战场状态、安全控制、最近决策、最近输出分区显示，并使用中文化标签和常见中文状态值；如仍出现大量 `enabled` / `conn_state` / `scenario` / `safety.status` 等裸字段名，记录为 Hosted UI 文案回归。
4. **基础 action**：依次点 `pause`、`resume`、`test_say`，确认没有 `PLUGIN_UI_ACTION_FAILED`；`pause` 时风险事件应被 suppress，`resume` 后恢复。
5. **identity / owned combat 回归**：在 Hosted UI 设置游戏昵称，确认 `/api/identity` 与 `/api/telemetry.combat.self.source=manual`；击杀 / 死亡时确认 `is_my_kill=true` / `is_my_death=true` 仍能生成 `you_killed` / `you_died`，并由 T-Observe 解释 Arbiter / Dispatcher 输出。
6. **数值安全事件**：优先复测 `overheat` / `oil_overheat`、`overspeed_critical`、`stall_risk`、`low_alt_danger`、`low_fuel`；每次看 `observe.last_decision` 是否能解释 allow / drop / cooldown / scenario gate。
   - 起飞/复活低空保护：记录 `processed.radio_altitude_m` 或 `indicators.radio_altitude` 是否可用，但固定翼不要求必有 AGL。出生或机场起飞后 45s 内，`altitude_critical` 不应产生真实低空播报，`observe.last_decision.reason` 应能解释为 `takeoff_low_alt_grace`；若 AGL 可用，雷达高度 `<=10m` 应进入贴地滑跑保护，`>=40m` 应解除。
   - 贴地滑跑保护：AGL 保护激活时，跑道滑跑阶段的 `overspeed` 不应播报，原因应为 `takeoff_radio_altitude_grace`；AGL 缺失时，仅保护期内且起落架放下/运动中允许压制 `overspeed`，原因应为 `takeoff_runway_grace`。同窗口内 `stall_risk`、`you_died` 不应被该保护误伤。
   - 保护期后，若仍处于真实低空危险，`low_alt_danger` 应恢复正常 Arbiter / Dispatcher 链路；若离地后真实超速，`overspeed` 应恢复正常链路。
7. **V2 接近/目标态势**：观察 `proximity.events` / `situation.ground_targets`；空中接近应能生成 `air_threat_nearby`，后方 5/6/7 点钟或相对角度后向样本应能生成 `enemy_on_six`，短窗连续近距离后方样本应能保守升级为 `tailing_risk`；对地任务靠近目标点时应能生成 `ground_target_nearby`。输出只允许方位、钟点、网格、距离等 safe metadata，不允许 raw proximity 文本或目标 label。
8. **自由文本风险路径**：只在 `dry_run=true` 下观察 `combat.feed` / `hud_notices` / `awards`，确认 prompt / dry_run 输出不包含 raw 玩家名、raw HUD 文本或 awards 原文；`live_monitor` 顶部 `Summary` 应显示 free-text 状态，细节行应显示 `free_text=dry_run_only(...)`，并在 `FreeText detail` / `free_text_safety.source_details` 中给出逐源 `.../blocked`；Hosted UI / observe 中首次看到这些源时应出现 `detector_suppressed/free_text_blocked`，并可看到 `free_text_activity` 候选经过 Arbiter / Dispatcher dry_run 链路。`dry_run=false` 必须仍显示 `free_text_dry_run_only` 或不输出，不能真实播报 raw 文本。
9. **replay 降级**：若数据层返回 `replay=true`，确认 Detector 静默、last decision 能说明 suppressed / replay，`live_monitor` 显示 `replay=suppressed(detector_suppressed/replay)` 且 `output_blocked=True`，不触发真实输出。
10. **样本留存**：把现场抓包放到 `local_samples/` 或本地临时目录，保持 `.gitignore`；仓库只提交聚合统计和脱敏结论。
11. **真实开口**：只有前面 dry_run 通过后，才关闭 dry_run；`test_say`、generic kill/death 已在 2026-06-23 通过真实 push smoke。hudmsg / awards / 其他 free-text 仍需各自 dry_run 安全验证后再开放真实播报。
12. **用户聊天干扰**（`verify_user_chat_interference_quiet_window`）：真实链路测试时，在战雷样本回放或真机战斗 cue 进入队列后，手动给猫发一句日常话（例如“喵”或“你先等一下”）。插件侧应在真实 push metadata 中保留 `plugin_quiet_window_policy=suppress_non_urgent_during_user_input` 与 `dialogue_policy_owner=plugin`，并让 `you_died` / critical 事件带 bypass / interrupt 语义。观察重点是插件是否丢弃/延后普通 cue、是否让 death/critical 通过；不要把战雷专用核心 patch 当作插件发布前提。

每轮测完后，用 `docs/真机测试结果-template.md` 记录结果；只写聚合统计、安全摘要和结论，不写 raw 玩家名、raw HUD 文本、raw combat.feed 或 awards 原文。

### 现场速用版

| 顺序 | 用户操作 | 我方监控重点 | 通过标准 |
| --- | --- | --- | --- |
| 0 | 先跑离线门禁，或确认当天代码未变 | `tests/run_logic_tests.py`、pytest、`tools/vehicle_profile_id_audit.py`、`tools/release_defaults_gate.py`、`tools/output_freshness_gate.py`、`tools/host_contract_gate.py`、`tools/free_text_gate.py`、`tools/replay_gate.py`、`tools/ownership_replay_gate.py`、`tools/deferred_hud_gate.py`、`tools/proximity_gate.py`、`tools/v2_readiness.py --no-sample`、`tools/v2_release_matrix.py --no-sample`、`tools/v2_output_policy_gate.py`、`tools/v2_completion_gate.py --no-sample`、`tools/rc_handoff_report.py --no-sample`、`tools/final_smoke_packet.py`、`tools/release_readiness.py --run`、plugin check、`tools/live_monitor.py --count 1`；需要样本证据时显式运行 `tools/release_readiness.py --run --include-local-sample` 或单跑 `tools/sample_replay.py` / `tools/live_test_plan.py`；真机前先用 `tools/final_smoke_evidence_gate.py --safe-transcript-template --output local_test_logs\safe_transcript_metrics.json` 生成猫猫实际回复 metrics 模板；真机后保存 `tools/live_monitor.py --count 3 --interval 1 --json --output local_test_logs\live_monitor_final.json`，用 `tools/final_smoke_evidence_gate.py --from-live-monitor local_test_logs\live_monitor_final.json --output local_test_logs\final_smoke_evidence.json` 扫描整段 JSONL 并预填，填好无原文 metrics 后优先用 `tools/final_smoke_evidence_gate.py local_test_logs\final_smoke_evidence.json --safe-transcript local_test_logs\safe_transcript_metrics.json` 合并猫猫行数、字数、是否续写、聊天静默和 critical 替换观察；没有 metrics 时再用 `tools/final_smoke_evidence_gate.py local_test_logs\final_smoke_evidence.json --update --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --confirm-short-tts-single-line` 合并人工确认，最后用 `tools/final_smoke_evidence_gate.py` 或 `--final-smoke-evidence` 复验 | 离线基线仍为 `442/442 passed`，vehicle profile id audit / release defaults / output freshness / generic host callback contract reservation / host boundary / free-text / replay / ownership replay / deferred HUD / proximity/objective gates 通过，`v2_offline_gate_complete=true` 且 `v2_live_evidence_complete=false`（除非样本已覆盖），V2 release matrix 会列出每个能力的 code/offline/live-evidence/real-output-policy，V2 output policy gate 会证明后方/尾随/目标点事件在真机证据补齐前默认不真实推送，V2 completion gate 会输出 `v2_code_offline_complete_live_evidence_pending` 作为不夸大真机证据的收口结论，RC handoff report 会给出维护者可读的 V1/V2 交接摘要，默认 final packet 会提示 `go_no_go=review_required_run_offline_gate`；`release_readiness.py --run` 通过后再用 `tools/final_smoke_packet.py --offline-gates-passed` 得到 `go_no_go=go_dry_run_final_smoke`，runtime smoke 能显示 dry_run / paused / Hosted UI / 8112 状态、新鲜度/短播报 metadata，操作清单包含 P1/P2、V2 proximity/situation 后方样本、3000m 内任务目标点样本和 runtime output 复测项 |

推荐最终合成命令：`tools/final_smoke_evidence_gate.py --from-live-monitor local_test_logs\live_monitor_final.json --safe-transcript local_test_logs\safe_transcript_metrics.json --output local_test_logs\final_smoke_evidence.json`，对应交接包里的 `evidence_from_monitor_and_transcript`。

推荐 metrics 记录命令：`tools/final_smoke_evidence_gate.py --record-safe-transcript --reply-chars <count> --reply-lines 1 --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --output local_test_logs\safe_transcript_metrics.json`，对应交接包里的 `safe_transcript_record`，不保存回复原文。

推荐流程演练命令：`tools/final_smoke_evidence_gate.py --rehearsal-output-dir local_test_logs\final_smoke_rehearsal`，对应交接包里的 `evidence_rehearsal`，只证明 evidence 流程，不替代真机证据。
| 1 | 启动宿主、Hosted UI、数据层，打开面板 | `48911/health`、`48916/health`、`8112/health`、Hosted UI context/actions、`data_layer.mode` | 三个 health 正常；`state_empty=false`；actions 含 `set_dry_run` / `pause` / `resume` / `test_say` / `set_identity`；`data_layer.mode` 为 `managed` 或 `external` |
| 2 | 进战局前设置玩家名 | `/api/identity`、`combat.self.source`、`combat.player_name` | `combat.self.source=manual`，后续 kill/death ownership 围绕该昵称生效 |
| 3 | 保持 `dry_run=true`，打一轮常规空战或陆战 | `observe.last_event`、`observe.last_decision`、`observe.last_output_status`、`processed.flags` | 事件能解释为 allowed / preempt / cooldown / scenario_gated / dry_run 输出之一 |
| 3a | 机场起飞 / 复活后低空滑跑或刚离地 | `radio_altitude_m`、`gear_state` / `gears`、`low_alt_danger`、`overspeed`、`observe.last_decision.reason`、其他 critical 事件 | 45s 保护期内低空被 `takeoff_low_alt_grace` 压住；AGL 可用时 `<=10m` 进入贴地滑跑保护、`>=40m` 解除，滑跑超速被 `takeoff_radio_altitude_grace` 压住；AGL 缺失时只有起落架放下/运动中的滑跑超速被 `takeoff_runway_grace` 压住；失速、死亡不被误压；保护期后低空/超速恢复正常 |
| 4 | 触发或等待 owned kill / death | `combat.feed[].is_my_kill` / `is_my_death`、`you_killed` / `you_died`、`kill_deferred_critical_risk`、`kill_coalesced` | 生成 generic kill/death，不含 raw 玩家名；`CRITICAL_RISK` 中击杀不抢播、不丢弃，危急解除后补播；death / critical 仍可抢占 |
| 4a | 分别观察空战 / 陆战 kill-death 文案 | `domain`、`cause`、Dispatcher prompt / 实际输出 | 空战可说击落；陆战击杀说击毁 / 摧毁地面目标；陆战死亡不说被击落；坠毁说坠毁 |
| 5 | 观察 awards / hud_notices / combat.feed 自由文本源 | `free_text_safety.status`、`source_details`、prompt / dry_run 输出 | `free_text=dry_run_only(...)`，raw HUD / combat.feed / awards 原文不进入 prompt |
| 6 | 若出现 replay，继续观察不要手动触发输出 | `replay=true`、`detector_suppressed/replay`、`output_blocked` | replay 帧静默，`live_monitor` 显示 replay suppressed，不真实开口 |
| 7 | 条件允许时关闭 `dry_run`，复测数值安全或 generic kill/death | `push_message`、`last_output_status`、`output_backpressure`、`event_expired`、`event_age_seconds`、`event_expires_at`、`target_lanlan`、`coalesce_key=neko_warthunder:battle_event`、`battle_reply_contract=short_tts_line`、`live_reply_contract=short_tts_line`、`max_reply_chars=28`、`dialogue_policy_owner=plugin`、`plugin_dialogue_policy`、`plugin_recommended_reply`、`plugin_owned_output`、`ai_behavior`、`host_callback_contract_version=neko.callback.v1`、`kill_coalesced`、`repeated_event_collapsed` | 真实开口不刷屏；过期旧事件不真实 push；同类安全提示短窗折叠；击杀夸夸不被普通过载背压吃掉；目标会话不走 fallback session；插件侧通用 delivery contract 与插件内 dialogue policy metadata 完整；危急动作类默认显示 `mode=blind+plugin`；开局、击杀/阵亡、过热、低油、普通接近、目标点和结算应显示 `ai_behavior=respond`，可在事实边界内活泼即兴 |
| 7a | 真实开口或样本回放期间手动给猫发日常消息 | 聊天窗口、`plugin_quiet_window_policy` metadata、用户输入后的战斗 callback | 插件 metadata 应表达普通 cue 静默与 death/critical bypass 语义；插件侧不依赖宿主核心特判 |

现场优先级：

- 第一优先：replay=true、awards/free-text dry_run 安全合同。
- 第二优先：油温/发动机数据库补齐后的细项复测、powertrain_failure 是否继续不播。
- 第三优先：`dry_run=false` 数值安全事件真实开口延迟和刷屏情况。

## 剩余接缝

- NEKO 宿主加载与插件生命周期。
- 数据层 `:8112` v1.6 DTO 与插件解析（基础数值安全链路、identity/ownership、`you_killed` / `you_died` 已通过，剩余 replay/free-text 单项）。
- `dry_run` 决策链路是否能解释每一步（2026-06-23 已证明 always-on observe 摘要足够解释主要安全事件）。
- `push_message` 真实开口链路（generic kill/death 已通过，其他事件仍需按项验证）。
- T-Safety 已完成；generic kill/death 已通过真实输出 smoke，hudmsg / awards / 其他 free-text 在真机 dry_run 验证前仍不做真实播报。

## 接缝 1：插件能否被 NEKO 加载

1. 在 N.E.K.O 宿主仓库运行插件检查：

   ```powershell
   uv run python -m plugin.neko_plugin_cli.cli check D:\Users\zheng\Documents\Code\N-E-K-O-Warthunder\project-N-E-K-O-Warthunder-8111-data-plugin
   ```

   预期：`0 error`。

2. 在独立插件仓库运行逻辑自检：

   ```powershell
   uv run python tests/run_logic_tests.py
   uv run pytest -c tests\pytest.ini tests -q
   ```

   预期：`442/442 passed`。

   额外 free-text 去桩前门禁：

   ```powershell
   uv run python tools/free_text_gate.py
   ```

   预期：`status: pass`，且合成玩家名、HUD、combat.feed、awards raw 文本不出现在 prompt 或 `push_message.parts[].text`。

3. 启动宿主后启动插件，确认 `status` / Hosted UI context 可返回状态。

失败定位：

- 插件检查失败：优先看 `plugin.toml`、`__init__.py`、Hosted UI surface 声明。
- context/action 失败：优先看 `@ui.context` / `@ui.action` 与 action 是否为 async。

## 接缝 2：push_message 能否让猫开口

1. 插件启动后调用 `test_say`：

   ```text
   POST /plugin/neko_warthunder/hosted-ui/action/test_say
   body: {"args": {"text": "副驾驶测试，能听到我吗？"}}
   ```

2. 预期：猫娘开口；宿主日志无 `PLUGIN_UI_ACTION_FAILED`。

失败定位：

- 对比可用插件的 `push_message` 参数。
- 只改 `adapters/neko_dispatcher.py` 的输出接缝，不改 Detector / Scenario / Arbiter。

## 接缝 3：数据层 v1.6 DTO 验证

1. 启动数据层 `:8112` 并进入一次飞行。

2. 抓取样本：

   ```powershell
   New-Item -ItemType Directory -Force local_samples\live_current | Out-Null
   curl http://localhost:8112/api/telemetry > local_samples\live_current\telemetry_sample.json
   ```

   仓库内已有一份脱敏的 v1.6 形状样本 `contract/telemetry_sample.json`，用于合同测试。真机验证时另抓当前环境帧到 `.gitignore` 覆盖的 `local_samples/` 做对照；不要把 raw 玩家名、raw HUD 文本、raw combat.feed 或 awards 原文写回 tracked contract 文件。

   已留存的本地样本可先做离线覆盖率审计：

   ```powershell
   uv run python tools/sample_replay.py local_samples/data_process_20260620 tl0sr2
   ```

   当前样本的聚合回放结论见 `docs/样本回放-20260620.md`。该报告只记录统计和缺口，不提交原始抓包文本；`session_summary` 可直接给出已观察事件、dry_run 输出、分组 validation verdict、P1/P2 `live_test_plan` 和下一步补测项；若样本含 `replay=true`，`replay_degrade` 还会给出 suppressed / output blocked 合同。V2 proximity/objective 统计会显示当前本地样本已覆盖空中接近、situation 和 ground target items，但仍缺后方/六点钟样本，且没有 3000m 内任务目标点候选。需要机器可读结果时使用 `--json`，需要可交付 Markdown 汇报时使用 `tools/offline_report.py`；需要操作清单时使用 `tools/live_test_plan.py`。`sample_replay` / `offline_report` / `live_test_plan` 三个出口与 `session_summary.next_steps` 都会列出 T-Output 背压、T-Kill-Coalesce 多杀合并、V2 proximity 后方样本和 ground target 样本复测项；真机测试进行中用 `tools/live_monitor.py` 做只读安全摘要，先看 `Summary` 行，再查看 `free_text=dry_run_only(...)`、`FreeText detail` 和 JSON 的 `free_text_safety.source_details` 是否按预期出现；看 `Decision detail` / `Output detail` 解释 selected、dry_run、coalescing 或 backpressure。该报告包含 Team brief、Next test focus、Operator quick checklist 和 Next live-test plan，也可通过 `tools/preflight.py --run --report-output <path>` 在统一预检时保存并打印操作清单。

   重点看输出 `coverage:` 行里的 `is_my_kill_field` / `is_my_death_field` / `involves_me_field`、`is_my_kill_true` / `is_my_death_true` / `involves_me_true`、`combat_self_source`、`hud_notice_codes`、`hud_notice_severities`、`awards_items`、`proximity_events`、`proximity_rear_close_events`、`situation_frames`、`ground_target_items`、`ground_target_live_items`、`ground_target_close_live_items`、`replay_true`，以及 `coverage_gaps:` 行。如果 `coverage_gaps` 含 `combat_feed_missing_ownership_fields`，说明样本里完全没有新归属字段；如果含 `combat_feed_no_ownership_true_frames`，说明字段存在但样本没有命中我方击杀/死亡。两种情况都不能关闭 kill/death identity 验证项。若 `coverage_gaps` 含 `no_manual_identity_frames`，说明当前样本没有 `combat.self.source=manual`，不能关闭手动 `/api/identity` 接缝验证。若 `coverage_gaps` 含 `no_ground_target_close_candidates`，说明样本有任务目标数据，但没有进入 `ground_target_nearby` 的 3000m 触发阈值，应继续靠近目标点采样；若含 `no_ground_target_trigger`，说明已有 3000m 内任务目标候选但插件没有触发 `ground_target_nearby`，才应按插件侧触发问题排查。若含 `no_awards_items`、`no_overspeed_critical_flags`、`no_oil_overheat_notice_codes`、`no_powertrain_failure_notice_codes` 或 `hud_notice_severity_unknown`，说明当前样本还不能验证 awards、超速 critical、油温 notice、动力故障 notice 或 notice warning/critical 档位。

3. 必查字段：

   - 顶层 `replay` 是否存在。
   - `processed.flags` 是否能出现 `overspeed_warn` / `overspeed_critical`。
   - `combat.feed[]` 是否有稳定递增 `id`。
   - `combat.feed[]` 是否有 `is_my_kill` / `is_my_death`。
   - `combat.self` / `player_name` / `active_players` 是否符合 `/api/identity` 设定。
   - `hud_notices` 是否存在；`engine_overheat` / `oil_overheat` code 是否能触发 `overheat`，且 raw 文本不会直接进入 prompt。
   - `awards` 是否存在且不会绕过 T-Safety。

4. identity seam：

   ```text
   Hosted UI 面板输入你的游戏昵称，点击“设置玩家名”
   GET http://localhost:8112/api/identity
   Hosted UI 面板点击“清除玩家名”
   ```

   预期：设置后 `combat.self.source=manual`，`combat.player_name` 等于面板输入昵称；`combat.feed[]` 的 `is_my_kill` / `is_my_death` 能围绕该昵称生效。2026-06-23 已观察到该正向路径，并已确认 `you_killed` post-fix dry_run / push 输出。面板只支持手动填写玩家名；不提供 active players 候选点选。

5. replay seam：

   - 若 `/api/telemetry` 返回 `replay: true`，插件应进入降级或静默策略。
   - `tools/live_monitor.py` 应显示 `replay=suppressed(detector_suppressed/replay)`，并在 JSON 中给出 `telemetry.replay_degrade.output_blocked=true`。
   - 回放期间不要消费派生战斗数据，不要触发真实播报。

失败定位：

- flag 名不一致：改 `core/flag_codes.py`。
- 字段路径不一致：改 `adapters/telemetry_client.py`。
- 身份识别不稳定：先要求 `/api/identity` 手动设定，不依赖低置信度自动猜测。

## 接缝 4：端到端 dry_run

1. 保持 `dry_run=true`。
2. 进入飞行，触发数值安全事件：低空、失速、过热、低油、超速。
3. 查看日志中的 scenario / detector / arbiter / dispatcher 决策链路。
4. 预期：出现可解释的 `spoken(dry_run)` 或明确丢弃原因。

注意：

- overspeed 不再是数据层缺口；2026-06-23 已验证 warning/critical flag 能触发正确事件并进入 dry_run。
- 2026-06-21 已验证 pause / resume / test_say 基础链路；2026-06-23 已验证低空 / 失速 / 超速 / 过热 / 死亡 dry_run 基础链路。
- generic kill/death 已通过真机 dry_run 与真实 push；hudmsg / awards / 其他 free-text 在真机 dry_run 验证前只做 dry_run / audit，不做正式播报。

## 接缝 5：dry_run=false 真实开口

前置：

- 数值安全事件接缝已在 dry_run 下通过。
- T-Safety 与 free-text release gate 已完成；generic kill/death 已通过真机 dry_run 与真实 push。hudmsg / awards / 其他 free-text 还需要真机 dry_run 验证后，才允许测试真实播报。
- T-Output 已完成；真实开口测试时应观察 `dispatcher_suppressed / output_backpressure` 是否减少旧事件晚回复和多条消息堆积，同时确认击杀、death、critical 安全事件仍能通过。窗口 flush 不再刷新连续告警的事件时间戳；超过 `output_event_max_age_seconds` 的旧事件会记录为 `dispatcher_suppressed / event_expired` 且不真实 push；同类安全提示短窗重复会记录为 `dispatcher_suppressed / repeated_event_collapsed`。真实战场事件 push 会带 `coalesce_key=neko_warthunder:battle_event`。真实 push 与 `last_output_status` 会带 `event_age_seconds` / `event_expires_at` / `target_lanlan` / `battle_reply_contract=short_tts_line` / `live_reply_contract=short_tts_line` / `max_reply_chars=28` / `dialogue_policy_owner=plugin` / `plugin_dialogue_policy` / `plugin_recommended_reply` / `plugin_owned_output` / `host_callback_contract_version=neko.callback.v1`；若仍出现晚播、长回复或普通聊天串战雷上下文，先用这些字段区分插件侧及时直出、宿主队列滞后、fallback session 和插件内短播报策略是否丢失。`tools/live_monitor.py` 的 Summary / Observe 摘要会直接显示 `output_backpressure` / `event_expired` / `repeated_event_collapsed`。危急动作类默认应显示 `mode=blind+plugin`；开局、击杀/阵亡、过热、低油、普通接近、目标点和结算应走 `respond`，可按空/陆/海载具域活泼即兴，但不得报敌情、锁定、击杀或威胁。短句、旧事件过期、重复折叠和用户聊天干扰策略按插件内逻辑验收。
- T-Kill-Coalesce 已完成；多杀 / 连杀测试时应观察 `you_killed` 是否合并为 `kill_count` 单条输出，并确认 `CRITICAL_RISK` 中 owned kill 会记录 `kill_deferred_critical_risk`、危急解除后补播，且 `you_died` / critical 安全事件仍可抢占。

步骤：

1. 通过 Hosted UI 或 action 关闭 dry_run。
2. 先测试数值安全事件或 T-Safety-safe generic 事件真实开口。
3. 观察是否刷屏、滞后或抢占异常。
4. 再按 T-Safety 和 dry_run 结果决定是否开放 hudmsg / awards / 其他 free-text。

## 暂缓项

- recovery 继续暂缓。不要因为数据层 v1.6 合并就提前实现。
- L8 子进程最小编排已完成且已本地自验证。2026-06-26 确认插件托管启动时 `data_layer.mode=managed` 且插件 stop 会关掉该 `8112`；手动预先启动 `8112` 时 `data_layer.mode=external` 且插件 stop 不会误杀。
- 2026-06-25 已修正本地运行副本边界：`N.E.K.O\plugin\plugins\neko_warthunder` 改为指向独立插件仓库的 junction。复测确认宿主启动、`/plugins/refresh`、`/plugin/neko_warthunder/start`、Hosted UI context、`set_dry_run` / `pause` / `resume` / `test_say` 均可用；`dry_run=true` 下 `test_say` 正确返回 `pushed=false, blocked="dry_run"`。

