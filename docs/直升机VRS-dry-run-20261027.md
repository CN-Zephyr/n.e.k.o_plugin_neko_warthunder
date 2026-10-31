# 直升机 VRS dry-run 开发记录（2026-10-27）

后续阶段：已完成 [海战只读地图态势](海战只读地图态势-20261027.md)。本文保留当时测试与同步结果，当前统一基线见 [当前开发状态](当前开发状态.md)。

结论：`heli_vrs_risk` 的 Detector→Arbiter→Dispatcher dry-run 链路及活动页解释已完成，review、验证通过后已备份同步宿主。真实输出硬禁用，没有启用开关。未 commit、push、重建 RC 或发布。

## 范围与成本

按用户“继续下一阶段”，沿用此前讨论的第二步 VRS dry-run。实施前已说明只消费现有 flags、记录候选和决策，不新增采集/依赖/LLM 调用，不接转速告警。参数用于离线观察，未经真机校准。

| 方案 | 成本与边界 | 本轮 |
|---|---|---|
| 保守 dry-run | 增加 1 个固定大小的 Detector 状态及常数级时效检查；复用现有最多 20 条活动摘要；新增轮询/后台进程/依赖/配置/持久状态/LLM 调用均为零 | 已实施 |
| 完整真实播报/抢占 | 需另定语音、优先级、场景、校准与 token 成本 | 未实施 |
| 延后 | 维持只读仪表，但缺少 VRS 候选与仲裁证据 | 未采用 |

只改插件的事件合同、Detector、Arbiter、Dispatcher 硬阻断和活动展示；宿主核心、数据层阈值、Scenario 危急集合及原有配置未改。VRS payload 只有 `domain=heli`，不包含原始玩家名、聊天、HUD 或提示原文。

## 事件策略

- 输入是数据层 `vrs_warning/vrs_critical`，不根据仪表值重算阈值；连续 2 次有效观测确认、2 次解除后重武装，warning→critical 可升级；无 recovery/持续心跳。
- 仅在线、在战、存活、非回放的直升机，必须有已知 fast/vehicle 年龄及有效时间戳；载具采样上限 5 秒，仲裁时继续计算缓存流逝时间。
- 暂定 `safety_important`、priority 6、severity 5/7、20 秒冷却、4 秒事件时效；不抢占、不进入 `CRITICAL_RISK`。
- 真实模式在仲裁前过滤，不能占用单槽或消耗 VRS 冷却；直接调用 Dispatcher 也先硬阻断，不能构建输出 prompt 或调用模型。
- 条件解除、来源不可确认/过期、跨域、阵亡或 critical 降级时撤销旧候选/重试；切到真实模式同样清除 VRS 缓冲。
- 活动页区分仅记录、真实输出阻断、旧记录失效。只读状态卡读取仍不推进检测或触发播报。

## Review 与验证

Review 检查完整事件路径、时效与模式/生命边界、真实输出绕过、活动原因优先级及陆战回归。修正了新事件集成 fixture 缺失，以及通用 dry-run 文案盖住 VRS 失效原因的问题。

| 检查 | 实际结果 | 边界 |
|---|---|---|
| 聚焦回归 | 90 passed | VRS、仪表、域边界、标签与陆战待发弹 |
| 完整 pytest | 867 passed，新增 33 项 | [日志](../../archive/heli-vrs-20261027-171819/pytest-full.log) |
| Ruff、域边界、发布默认值、宿主合同 | 通过 | 未重跑整套 preflight/release-readiness |
| Hosted UI | 类型/编译，30 状态 × 3 宽度 = 90 场景通过 | 新活动原因及旧仪表、陆战、颜色回归；原生 Electron 未验 |
| 真实 SDK / Hosted UI | 源码副本、实际安装路径均通过首次启动/重启 | 合成 HTTP VRS 数据、隔离配置/状态，观察到 `dispatcher_dry_run/pushed=false`；不是实际战局/TTS |

[Review](../../archive/heli-vrs-20261027-171819/review-report.json)、[UI](../../archive/heli-vrs-20261027-171819/panel-report.json)、[源码 SDK](../../archive/heli-vrs-20261027-171819/sdk-source-report.json)、[宿主 SDK](../../archive/heli-vrs-20261027-171819/sdk-host-report.json) 与 [交付报告](../../archive/heli-vrs-20261027-171819/development-report.json) 保留本轮证据。SDK harness 仅在隔离配置里将出生保护和全局间隔设为零以观察链路，实际宿主配置未改。

## 同步、恢复与剩余范围

- Review 后备份同步 `N.E.K.O/plugin/plugins/neko_warthunder` 的 9 个运行文件，新增 `core/telemetry_freshness.py`；57 个运行源码文件一致，66 个受保护文件 hash 不变，原配置/状态和两处宿主已有修改保留；源码与宿主 HEAD 未变，旧 worktree 未覆盖。
- 备份见 [host-before](../../archive/heli-vrs-20261027-171819/host-before/)，清单见 [同步报告](../../archive/heli-vrs-20261027-171819/sync-report.json) 和 [同步前记录](../../archive/heli-vrs-20261027-171819/sync-before.json)。回滚时先停插件并确认无后续变更，再恢复原有 8 文件、撤去新增模块；无需迁移配置或状态。本轮未执行回滚。
- 本次 worker、合成 HTTP 服务与临时监听已退出，无关已有进程保留，见 [进程与端口审计](../../archive/heli-vrs-20261027-171819/process-audit.json)。
- 真机验收按用户决定跳过；H02 的实际 VRS、原生 Electron 和真实声音未验。真实输出、转速告警、Recovery、海战未开展；旧 RC 保留原 hash，不包含直升机这两轮增量。
