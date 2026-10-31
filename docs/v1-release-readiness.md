# v1 Release Readiness

v0.1.2 版本范围：四域只读能力、遥测可靠性、聊天避让及低压力陪伴提示词已纳入源码；默认输出边界保持。版本验证与已知限制见[版本记录](release-v0.1.2.md)，正式发布状态以 GitHub Release 与插件市场为准。

此前提示词优化轮（2026-11-01）：常驻场景、每事件要求、风格元数据与直出短句统一为不责怪、不嘲讽、不催战绩，紧急提醒保留必要动作。最新完整 **1571 passed**（新增41，定向142），Ruff、模式边界和发布默认值检查通过；模型语气/TTS尚未试听，真实输出边界不变。该轮同步与生效状态见[优化记录](低压力陪伴提示词-20261101.md)，未 commit、push、发布或重建 RC。

此前 2026-10-30 完成聊天活动读取兼容修复，当轮完整 1530 passed；公开 SDK 与隔离跨进程验证、文件同步及未验收范围保留在[历史修复记录](聊天活动读取修复-20261030.md)。

2026-10-29 历史现场边界修复：出生等待真实载具，显式 state 油温只读诊断和燃油估算时效已实现、review并备份同步实际宿主；当轮完整 **1499 passed**，聚焦226，Hosted UI累计546场景，源码/实际安装副本SDK启动重启通过。当时猫猫和游戏均保持关闭，独立8112数据处理已重载运行；2个持久配置/状态文件hash未变。既有过热温度归因仍待修复，未验收TTS/Electron，未新建RC/commit/push/发布。见 [修复记录](现场采集边界修复-20261029.md)。


> 状态：准备发布候选前的离线门禁说明。本文不替代真机 smoke，只回答“现在代码能不能进入最后一轮真机验收”。

实际宿主安装与本轮 dry-run 证据见 [宿主验收记录](RC宿主验收-20261027.md)。

## 当前结论

- 此前试用 RC已包含直升机/海战/P1a/P1b/P2a，通过官方release check（含测试）、验包与隔离SDK，并安装到实际user目录重装/重启及面板通过，见 [试用安装记录](RC试用安装-20261029.md)。保留配置/状态，当前dry-run、按需解释关闭；非正式发布，已知过热温度归因问题尚未修复。
- 当前总路线为 **四域副驾驶体验补全**，最近完成现场边界修复；此前功能阶段为 P2a；A2来源/展示评审已完成，下一研发先修归因，原生 state 油温只读本次已完成，见 [总计划](实现计划-codex.md)。用户跳过的真机项仍未验收、不阻塞研发；当前试用包不等于实际游戏/TTS/Electron或正式发布验收。
- 最近完整 pytest：**1571 passed**（新增41，定向142）；本轮提示词与最终投递回归通过。旧 SDK/隔离跨进程、Hosted UI 546 场景均保留此前证据范围；本轮未调用模型/TTS，实际语气尚未试听。

此前 RC 离线构建与隔离验证见 [RC 验证记录](RC离线验证-20261027.md)。此前舰艇静态资料与字段映射已另行 review、验证并同步宿主，见 [静态资料记录](舰艇静态资料与实时字段映射-20261029.md)，未重建包；此前 [VRS dry-run](直升机VRS-dry-run-20261027.md) 的真实输出仍硬禁用。

- 此前完整 preflight 与 release-readiness（包含现有本地样本）在实际开发宿主上通过，当时 verdict 为 `ready_for_final_live_smoke`；P2a功能轮通过完整pytest/UI/SDK，后续本次试用交付已重跑官方release check并构建安装新RC，未重跑整套聚合。证据见 [统一状态](当前开发状态.md#已验证的基线)；剩余游戏/TTS/Electron现场项仍跳过、未验收。
- `tools/rc_audit.py` 已改为统一文档基线与历史边界审计；逻辑入口已改用标准 pytest 并通过完整套件。详见 [发布前工具复核](待办事项.md#发布前工具复核)。
- 陆战四类状态事件均已注册，乘员/待发弹三项真实输出默认关闭；激光保留原有策略，岗位只读。[真机验收矩阵](真机验证-checklist.md#剩余验收矩阵) 的剩余现场项本轮跳过、未验收；如恢复复验，不要求所有陆战状态都保持无候选。
- `tools/free_text_gate.py` 已作为自由文本发布门禁，防止玩家名、hudmsg、combat.feed、awards 原文进入 prompt 或 `push_message.parts[].text`。
- `tools/replay_gate.py` 已作为 replay 降级发布门禁，证明 `replay=true` 帧不会产生 Detector candidate、prompt 或真实 `push_message`。
- `tools/ownership_replay_gate.py` 已作为第三方旧样本 ownership 门禁，证明手动 identity + 显式 opt-in 推断才能把旧 `combat.feed` 标为 owned kill/death，且干扰 combat feed 保持非我方。
- `tools/deferred_hud_gate.py` 已作为 deferred HUD notice 发布门禁，证明 `powertrain_failure` 当前只可观测、不播报、不泄露 raw HUD 文本。
- `tools/domain_boundary_gate.py` 已作为 mode/domain 发布门禁，证明固定翼安全事件只在 `domain == "air"` 触发，陆战状态事件只在 `domain == "ground"` 触发；输出层也同步保留 `domain_prompt_contract`，用于 final smoke 人工确认模型没有把陆战说成空战、把直升机说成固定翼或把海战说成陆战。
- `tools/proximity_gate.py` 已作为 V2 proximity / objective awareness 门禁，证明 `proximity.events`、连续 `situation.enemies` / `nearest_air_threat`、`situation.ground_targets` 只生成 safe generic prompt，并覆盖 `tailing_risk` 持续后方威胁升级与 Arbiter gating。
- `tools/host_contract_gate.py` 已作为宿主边界门禁，宿主存在时确认核心区没有 `neko_warthunder` 专用发言逻辑、短回复裁剪或用户聊天静默窗口特判，并检查运行副本与独立插件仓库保持同步；宿主不存在时不阻塞独立插件仓库开发。
- 插件侧已预留通用宿主投递接口：真实 battle event push 会携带 `host_callback_contract_version=neko.callback.v1` 和结构化 `host_callback_contract`，只覆盖 `delivery`、`freshness`、`target` 等通用投递/新鲜度语义。短播报、用户聊天干扰压制和回复形态由插件内 `plugin_dialogue_policy` / `plugin_quiet_window_policy` 表达，不要求宿主核心为战雷插件写专用逻辑。危急动作类默认同样走 bounded `respond`，确保猫娘回复进入 TTS；`plugin_owned_urgent_output_enabled=false`、`plugin_owned_battle_output_enabled=false` 和 `plugin_owned_blind_output_enabled=false` 避免把战斗反馈变成只显示文字的直出气泡，仍保留显式开启直出的兼容能力。
- `tools/release_readiness.py` 已作为 v1 RC 离线汇总入口。它不启动前后端，不依赖 War Thunder，只聚合可自动化门禁，并在 `release_scope` 中区分 offline gate 状态、free-text 真实播报 blocker、样本未证明项和下一步动作；`handoff` / `handoff_status` 会把 v1 发布状态与 V2 code/offline/live-evidence 状态合并成接手者可读结论。
- `tools/v2_readiness.py` 已作为 V2 proximity/objective 收口汇总入口。它会先跑离线 gate，再按需合并本地样本证据，输出 `v2_code_complete`、`v2_offline_gate_complete`、`v2_live_evidence_complete`，避免把缺真机样本误判为代码未完成。
- `tools/v2_release_matrix.py` 已作为 V2 能力矩阵入口。它会把每个 V2 能力拆成 code/offline/live-evidence/real-output-policy 行，帮助维护者确认哪些能力可以进入最终 dry_run smoke，哪些仍需保持 dry_run-first 等待真机证据。
- `tools/v2_output_policy_gate.py` 已作为 V2 真实输出策略门禁。它会证明 `enemy_on_six`、`tailing_risk`、`ground_target_nearby` 在缺少真机证据前默认真实输出关闭，只保留 dry_run 可观察；显式开启 `v2_live_verified_real_output_enabled=true` 后才允许真实 `push_message`。
- `tools/v2_completion_gate.py` 已作为 V2 完成度门禁。它把 readiness、能力矩阵和真实输出策略合并成一个 pass/fail 结论：V2 code/offline scope 可以完成，但 live-only 证据必须继续显式标记为 pending。
- `tools/final_smoke_packet.py` 已作为最终真机前交接包入口。它会输出 `go_no_go`、`handoff_status`、必跑命令、V2 live evidence 缺口、runtime focus checks、remaining live actions 和 dry_run / raw text 安全边界。跑真机前可用 `tools/final_smoke_evidence_gate.py --record-safe-transcript --reply-chars <count> --reply-lines 1 --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --output local_test_logs/safe_transcript_metrics.json` 记录无原文 metrics；跑完真机后可以用 `tools/live_monitor.py --json --output local_test_logs/live_monitor_final.json` 保存安全报告；填好无原文 metrics 后优先用交接包里的 `evidence_from_monitor_and_transcript` 命令，也就是 `tools/final_smoke_evidence_gate.py --from-live-monitor local_test_logs/live_monitor_final.json --safe-transcript local_test_logs/safe_transcript_metrics.json --confirm-mode-domain-boundary --output local_test_logs/final_smoke_evidence.json`，一条命令合并新鲜度 metadata、猫猫行数、字数、续写、聊天静默、critical 替换观察和 mode/domain 边界确认；排障时仍可先用 `--safe-transcript-template` 生成模板，或先用 `--from-live-monitor ... --output ...` 预填，再用 `--safe-transcript ...` 补录；没有 metrics 时可用 `tools/final_smoke_evidence_gate.py local_test_logs/final_smoke_evidence.json --update --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --confirm-short-tts-single-line --confirm-mode-domain-boundary` 合并旧 warning 替换、聊天静默、单行短句和 mode/domain 边界确认；最终用 `tools/final_smoke_evidence_gate.py local_test_logs/final_smoke_evidence.json` 验收 P1 证据，或用 `release_readiness.py --final-smoke-evidence <path>` / `preflight.py --final-smoke-evidence <path>` 纳入统一复验。
- 真机前可先跑 `tools/final_smoke_evidence_gate.py --rehearsal-output-dir local_test_logs/final_smoke_rehearsal` 演练 monitor + metrics + evidence + gate 的文件链路；该输出带 `rehearsal_only=true`，只证明流程，不替代真机证据。
- `tools/rc_handoff_report.py` 已作为维护者 RC 交接报告入口。它会把 V1 release scope、V2 completion、final smoke go/no-go、安全边界和下一步 live evidence 动作合并成人类可读结论，适合给合作者汇报“V2 工程完成但真机证据仍 pending”。
- `tools/package_artifact_gate.py` 已作为构建后分发包门禁。它检查包身份、运行必需文件、8 个 locale、压缩包路径安全和开发文件排除；首轮检查发现并推动清理了误入包内的 `.ruff_cache`。该门禁只验证实际构建产物，不属于源码侧 `preflight` 聚合，也不替代真机 smoke。
- `tools/build_release_candidate.py` 已作为统一 RC 构建入口：调用宿主官方 release check，随后执行包内容门禁、官方 payload verify 和隔离临时安装 smoke，全部通过后才原子发布最终文件；默认不覆盖已有产物，也不接触真实插件安装目录。

## 推荐命令

以下是复验入口；前一轮完整聚合、历史 RC 与本轮摘要检查结果分别记录在统一状态文档中。

只看计划：

```powershell
uv run python tools\release_readiness.py
```

执行离线 RC 门禁：

```powershell
uv run python tools\release_readiness.py --run
```

默认 `--run` 是快门禁：即使本机存在 ignored 的 `local_samples/` 大样本，也不会自动跑样本报告。需要把样本证据一起纳入时显式运行：

```powershell
uv run python tools\release_readiness.py --run --include-local-sample
```

机器可读输出：

```powershell
uv run python tools\release_readiness.py --json
uv run python tools\release_readiness.py --run --json
uv run python tools\release_readiness.py --run --include-local-sample --json
```

最终真机前交接包：
```powershell
uv run python tools\final_smoke_packet.py
uv run python tools\final_smoke_packet.py --json
```

维护者 RC 交接报告：
```powershell
uv run python tools\rc_handoff_report.py --no-sample
uv run python tools\rc_handoff_report.py --no-sample --json
```

默认输出会提示 `go_no_go=review_required_run_offline_gate`。只有在本轮已经跑过并通过
`uv run python tools\release_readiness.py --run` 后，才使用：

```powershell
uv run python tools\final_smoke_packet.py --offline-gates-passed
uv run python tools\final_smoke_packet.py --offline-gates-passed --json
uv run python tools\rc_handoff_report.py --offline-gates-passed
```

完整真机前预检仍可使用：

```powershell
uv run python tools\preflight.py --run
```

构建并验证 `.neko-plugin`：

```powershell
uv run python tools\build_release_candidate.py
```

## RC gap summary

```powershell
uv run python tools\rc_gap_summary.py local_samples\data_process_20260620 tl0sr2
uv run python tools\rc_gap_summary.py local_samples\data_process_20260620 tl0sr2 --json
```

This output separates `sample_unproven_items`, `blocked_release_items`, `remaining_gaps`, and `next_actions` without raw telemetry text.

## Release Readiness 覆盖项

- `tests/run_logic_tests.py`
- `pytest -c tests/pytest.ini tests -q`
- `tools/free_text_gate.py`
- `tools/replay_gate.py`
- `tools/host_contract_gate.py`
- `tools/ownership_replay_gate.py`
- `tools/replay.py`
- `tools/v2_output_policy_gate.py`
- `tools/v2_completion_gate.py`
- `tools/rc_handoff_report.py`
- `tools/final_smoke_packet.py`
- 宿主存在时：host boundary gate（边界用途，确认没有战雷专用核心发言补丁）
- 可选：宿主存在时运行 `plugin check`
- 可选：加 `--include-local-sample` 时运行 `sample_replay`、`offline_report`、`live_test_plan` 等本地样本检查

## 已知限制

- `gunner_state/driver_state` 已按多值合同修复，但当前产品策略不为任何岗位状态生成猫娘播报。
- LWS 已改为仅 `lws == 1` 触发；仍需带 LWS 载具完成待机、真实受照和设备损坏真机样本复验。
- 一级待发弹偏少/打空已生成候选，真实输出受默认关闭的乘员/弹药开关控制；耗尽、补弹和同车重生完整序列仍待真机验收。
- 自己的固定无线电已验证；队友同口令不触发仍缺真机反例。

- 真机 airport spawn / takeoff / respawn rollout 仍需要最终回归，尤其是 AGL 可用/缺失两条路径下的低空抑制和贴地滑跑超速抑制。
- `replay=true` 已有离线 gate，但真实 replay 样本仍需要补。
- `hudmsg` / `combat.feed` / `awards` 仍保持保守策略；正式自由文本播报前必须继续走 T-Safety 与真机 dry_run 验证。
- 热门喷气/攻击机载具 profile 已按三批 Datamine 候选补入；油温、发动机细项仍只把 Datamine 热模型作为 evidence，需真机样本校准后再决定是否细分阈值。
- recovery、复杂 HUD 播报不属于 v1 发布阻塞项；V2 proximity / objective awareness 的非真机依赖部分已完成，后方/六点钟和持续尾随风险 `tailing_risk` 已支持 `proximity.events` + `situation.enemies` 双路径验证，七月已有近目标点样本覆盖记录，需先核对归档与当前正式 evidence，仅补缺失域/场景；不能沿用六月单份捕获缺口推导全局从未覆盖，见 [样本口径](副驾驶能力差距矩阵-20261029.md#样本与现场证据口径)。

## 发布前最后一轮真机 Smoke

以下仅供用户以后恢复现场验收时使用，本轮不执行、不阻塞研发。届时通过 `release_readiness --run` 后，再做聚焦真机 smoke：

1. 机场出生 / 复活 / 滑跑：记录 AGL 是否可用；AGL 可用时 `<=10m` 进入保护，`>=40m` 解除保护；AGL 缺失时用保护期 + 起落架放下/运动中兜底滑跑状态。
2. 保护期内不误报 `low_alt_danger`，贴地滑跑保护内不误报 `overspeed`，收轮后真实超速不应被兜底保护吞掉。
3. `stall_risk`、`you_died`、`low_fuel`、`overheat` 不被起飞保护误伤。
4. `dry_run=false` 下确认 `event_expired` / output backpressure / output freshness metadata 能减少旧事件晚播，并确认 `target_lanlan` 不走 fallback session，`battle_reply_contract=short_tts_line` / `live_reply_contract=short_tts_line` / `max_reply_chars=28` / `dialogue_policy_owner=plugin` / `plugin_dialogue_policy` / `plugin_recommended_reply` / `plugin_owned_output` / `host_callback_contract_version=neko.callback.v1` 未丢失。旧事件过期、背压、短句和用户聊天干扰策略都属于插件自身验收；宿主核心不作为本插件发布前提。
5. 分别观察空战、直升机、陆战、海战或合成事件 prompt：事件文本和 metadata 中应有相同的 `当前模式` / `domain_prompt_contract`，陆战出场与战果不应出现升空、后座、云霄、机翼、拉杆等空战词。
6. 如出现 replay/free-text 样本，确认 live monitor 显示 suppressed / blocked，且没有 unsafe raw 文本进入输出。


剩余项目与通过条件统一见 [真机验收矩阵](真机验证-checklist.md#剩余验收矩阵)，结果使用 [模板](真机测试结果-template.md)。包校验、隔离安装、开发宿主 SDK smoke 和实际声音是不同证据，不相互代替。
