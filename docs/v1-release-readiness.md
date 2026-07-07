# v1 Release Readiness

> 状态：准备发布候选前的离线门禁说明。本文不替代真机 smoke，只回答“现在代码能不能进入最后一轮真机验收”。

## 当前结论

- 离线逻辑基线：`444/444 passed`。
- `tools/free_text_gate.py` 已作为自由文本发布门禁，防止玩家名、hudmsg、combat.feed、awards 原文进入 prompt 或 `push_message.parts[].text`。
- `tools/replay_gate.py` 已作为 replay 降级发布门禁，证明 `replay=true` 帧不会产生 Detector candidate、prompt 或真实 `push_message`。
- `tools/ownership_replay_gate.py` 已作为第三方旧样本 ownership 门禁，证明手动 identity + 显式 opt-in 推断才能把旧 `combat.feed` 标为 owned kill/death，且干扰 combat feed 保持非我方。
- `tools/deferred_hud_gate.py` 已作为 deferred HUD notice 发布门禁，证明 `powertrain_failure` 当前只可观测、不播报、不泄露 raw HUD 文本。
- `tools/proximity_gate.py` 已作为 V2 proximity / objective awareness 门禁，证明 `proximity.events`、连续 `situation.enemies` / `nearest_air_threat`、`situation.ground_targets` 只生成 safe generic prompt，并覆盖 `tailing_risk` 持续后方威胁升级与 Arbiter gating。
- `tools/host_contract_gate.py` 已作为宿主边界门禁，宿主存在时确认核心区没有 `neko_warthunder` 专用发言逻辑、短回复裁剪或用户聊天静默窗口特判，并检查运行副本与独立插件仓库保持同步；宿主不存在时不阻塞独立插件仓库开发。
- 插件侧已预留通用宿主投递接口：真实 battle event push 会携带 `host_callback_contract_version=neko.callback.v1` 和结构化 `host_callback_contract`，只覆盖 `delivery`、`freshness`、`target` 等通用投递/新鲜度语义。短播报、用户聊天干扰压制和回复形态由插件内 `plugin_dialogue_policy` / `plugin_quiet_window_policy` 表达，不要求宿主核心为战雷插件写专用逻辑。核心回收后，默认只让危急动作类使用 `plugin_owned_urgent_output_enabled=true` 以 `ai_behavior=blind` 由插件确定短句直出，降低生死级提醒延迟；`spawn`、击杀/阵亡、过热、低油、普通接近、目标点和结算走 bounded `respond`，让猫娘按空/陆/海载具域在事实边界内自行组织短句；`plugin_owned_battle_output_enabled=false` 避免把普通战斗反馈模板化，`plugin_owned_blind_output_enabled=false` 仍保留为显式强制直出开关。
- `tools/release_readiness.py` 已作为 v1 RC 离线汇总入口。它不启动前后端，不依赖 War Thunder，只聚合可自动化门禁，并在 `release_scope` 中区分 offline gate 状态、free-text 真实播报 blocker、样本未证明项和下一步动作；`handoff` / `handoff_status` 会把 v1 发布状态与 V2 code/offline/live-evidence 状态合并成接手者可读结论。
- `tools/v2_readiness.py` 已作为 V2 proximity/objective 收口汇总入口。它会先跑离线 gate，再按需合并本地样本证据，输出 `v2_code_complete`、`v2_offline_gate_complete`、`v2_live_evidence_complete`，避免把缺真机样本误判为代码未完成。
- `tools/v2_release_matrix.py` 已作为 V2 能力矩阵入口。它会把每个 V2 能力拆成 code/offline/live-evidence/real-output-policy 行，帮助维护者确认哪些能力可以进入最终 dry_run smoke，哪些仍需保持 dry_run-first 等待真机证据。
- `tools/v2_output_policy_gate.py` 已作为 V2 真实输出策略门禁。它会证明 `enemy_on_six`、`tailing_risk`、`ground_target_nearby` 在缺少真机证据前默认真实输出关闭，只保留 dry_run 可观察；显式开启 `v2_live_verified_real_output_enabled=true` 后才允许真实 `push_message`。
- `tools/v2_completion_gate.py` 已作为 V2 完成度门禁。它把 readiness、能力矩阵和真实输出策略合并成一个 pass/fail 结论：V2 code/offline scope 可以完成，但 live-only 证据必须继续显式标记为 pending。
- `tools/final_smoke_packet.py` 已作为最终真机前交接包入口。它会输出 `go_no_go`、`handoff_status`、必跑命令、V2 live evidence 缺口、runtime focus checks、remaining live actions 和 dry_run / raw text 安全边界。跑真机前可用 `tools/final_smoke_evidence_gate.py --record-safe-transcript --reply-chars <count> --reply-lines 1 --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --output local_test_logs/safe_transcript_metrics.json` 记录无原文 metrics；跑完真机后可以用 `tools/live_monitor.py --json --output local_test_logs/live_monitor_final.json` 保存安全报告；填好无原文 metrics 后优先用交接包里的 `evidence_from_monitor_and_transcript` 命令，也就是 `tools/final_smoke_evidence_gate.py --from-live-monitor local_test_logs/live_monitor_final.json --safe-transcript local_test_logs/safe_transcript_metrics.json --output local_test_logs/final_smoke_evidence.json`，一条命令合并新鲜度 metadata、猫猫行数、字数、续写、聊天静默和 critical 替换观察；排障时仍可先用 `--safe-transcript-template` 生成模板，或先用 `--from-live-monitor ... --output ...` 预填，再用 `--safe-transcript ...` 补录；没有 metrics 时可用 `tools/final_smoke_evidence_gate.py local_test_logs/final_smoke_evidence.json --update --confirm-critical-replaced-stale-warning --confirm-user-chat-quiet-window --confirm-short-tts-single-line` 合并旧 warning 替换、聊天静默和单行短句确认；最终用 `tools/final_smoke_evidence_gate.py local_test_logs/final_smoke_evidence.json` 验收 P1 证据，或用 `release_readiness.py --final-smoke-evidence <path>` / `preflight.py --final-smoke-evidence <path>` 纳入统一复验。
- 真机前可先跑 `tools/final_smoke_evidence_gate.py --rehearsal-output-dir local_test_logs/final_smoke_rehearsal` 演练 monitor + metrics + evidence + gate 的文件链路；该输出带 `rehearsal_only=true`，只证明流程，不替代真机证据。
- `tools/rc_handoff_report.py` 已作为维护者 RC 交接报告入口。它会把 V1 release scope、V2 completion、final smoke go/no-go、安全边界和下一步 live evidence 动作合并成人类可读结论，适合给合作者汇报“V2 工程完成但真机证据仍 pending”。

## 推荐命令

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

- 真机 airport spawn / takeoff / respawn rollout 仍需要最终回归，尤其是 AGL 可用/缺失两条路径下的低空抑制和贴地滑跑超速抑制。
- `replay=true` 已有离线 gate，但真实 replay 样本仍需要补。
- `hudmsg` / `combat.feed` / `awards` 仍保持保守策略；正式自由文本播报前必须继续走 T-Safety 与真机 dry_run 验证。
- 热门喷气/攻击机载具 profile 已按三批 Datamine 候选补入；油温、发动机细项仍只把 Datamine 热模型作为 evidence，需真机样本校准后再决定是否细分阈值。
- recovery、复杂 HUD 播报不属于 v1 发布阻塞项；V2 proximity / objective awareness 的非真机依赖部分已完成，后方/六点钟和持续尾随风险 `tailing_risk` 已支持 `proximity.events` + `situation.enemies` 双路径验证，3000m 内任务目标点触发样本仍留到统一真机验证。

## 发布前最后一轮真机 Smoke

通过 `release_readiness --run` 后，再做一次聚焦真机 smoke：

1. 机场出生 / 复活 / 滑跑：记录 AGL 是否可用；AGL 可用时 `<=10m` 进入保护，`>=40m` 解除保护；AGL 缺失时用保护期 + 起落架放下/运动中兜底滑跑状态。
2. 保护期内不误报 `low_alt_danger`，贴地滑跑保护内不误报 `overspeed`，收轮后真实超速不应被兜底保护吞掉。
3. `stall_risk`、`you_died`、`low_fuel`、`overheat` 不被起飞保护误伤。
4. `dry_run=false` 下确认 `event_expired` / output backpressure / output freshness metadata 能减少旧事件晚播，并确认 `target_lanlan` 不走 fallback session，`battle_reply_contract=short_tts_line` / `live_reply_contract=short_tts_line` / `max_reply_chars=28` / `dialogue_policy_owner=plugin` / `plugin_dialogue_policy` / `plugin_recommended_reply` / `plugin_owned_output` / `host_callback_contract_version=neko.callback.v1` 未丢失。旧事件过期、背压、短句和用户聊天干扰策略都属于插件自身验收；宿主核心不作为本插件发布前提。
5. 如出现 replay/free-text 样本，确认 live monitor 显示 suppressed / blocked，且没有 unsafe raw 文本进入输出。

