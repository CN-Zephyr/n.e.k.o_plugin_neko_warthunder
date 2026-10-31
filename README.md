# neko_warthunder

2026-11-01：**v0.1.2 已发布**到 [GitHub Release](https://github.com/CN-Zephyr/n.e.k.o_plugin_neko_warthunder/releases/tag/v0.1.2) 与 N.E.K.O 插件市场，公开目录为 approved / stable / verification passed。源提交 cdc5063；正式下载包 hash、74 个提交源码文件和隔离安装 smoke 已核对。默认输出边界保持；本轮未安装或重启实际宿主，游戏/模型/TTS/Electron 验收缺口保留。详见[发布回执与已知限制](docs/release-v0.1.2.md)。

此前提示词优化轮（2026-11-01）：常驻场景、每事件要求、风格元数据与直出短句统一为不责怪、不嘲讽、不催战绩，紧急提醒保留必要动作。最新完整 **1571 passed**（新增41，定向142），Ruff、模式边界和发布默认值检查通过；模型语气/TTS尚未试听，真实输出边界不变。该轮同步与生效状态见[优化记录](docs/低压力陪伴提示词-20261101.md)，未 commit、push、发布或重建 RC。

此前 2026-10-30 完成聊天活动读取兼容修复，当轮完整 1530 passed；公开 SDK 与隔离跨进程验证、文件同步及未验收范围保留在[历史修复记录](docs/聊天活动读取修复-20261030.md)。

2026-10-29 历史现场边界修复：出生等待真实载具，显式 state 油温只读诊断和燃油估算时效已实现、review并备份同步实际宿主；当轮完整 **1499 passed**，聚焦226，Hosted UI累计546场景，源码/实际安装副本SDK启动重启通过。当时猫猫和游戏均保持关闭，独立8112数据处理已重载运行；2个持久配置/状态文件hash未变。既有过热温度归因仍待修复，未验收TTS/Electron，未新建RC/commit/push/发布。见 [修复记录](docs/现场采集边界修复-20261029.md)。


此前试用包安装记录（不含本次修复）：当时源码 RC已验包并安装到实际活跃的用户安装目录，官方同版本重装/重启和实际面板通过，见 [安装记录](docs/RC试用安装-20261029.md)。配置/状态保留；安装时为 dry-run、按需解释关闭，安装当时宿主主进程/其他插件保持。A2归因问题未修复，未正式发布。

A2 来源评审的显式 `/state` 油温只读切片已在本次实现，保持独立来源、最多8通道及原输出边界；既有过热候选温度归因仍未修复，列下一优先项。见 [本次修复](docs/现场采集边界修复-20261029.md)；原日期化评审保留当时结论。

此前 P2a 轮完成记录：2026-10-29：**P2a 陆战一级待发弹状态解释已实现、review、验证并备份同步宿主**，见 [实现记录](docs/P2a-陆战待发弹状态解释-20261029.md)。原陆战卡补七状态只读说明，不新增告警、模型调用或输出权限；完整回归 **1456 passed**（新增 48、聚焦 194），Hosted UI **516 场景**，源码/安装副本隔离 SDK 启动及重启通过。此前P2a同步轮未重载；本次试用包已重启战雷插件，跳过现场验收仍未验收、不阻塞研发。

War Thunder 猫娘副驾驶插件 v1。插件只消费本地数据层 HTTP `:8112`，把连续遥测整理成 Battle Awareness 事件，再经 Scenario / Arbiter / Safety / Dispatcher 决定是否让猫娘开口。

## 兼容性

- 插件 SDK：`>=0.1.0,<0.3.0`，推荐 `>=0.1.0,<0.2.0`。
- N.E.K.O 宿主：面板使用 Hosted TSX UI，需要 N.E.K.O `v0.8.0` 或更新版本。
- 显示环境：支持浅色/深色主题、桌面窗口、窄窗口和低高度窗口；主内容独立滚动，底部播报控制不会覆盖内容。
- 当前面板以简体中文为主要操作语言；插件名称与简介已提供 8 个宿主 locale，完整面板国际化不属于本轮范围。

## 当前状态（2026-10-29）

- **四域副驾驶体验补全：P1a/P1b 已实现、review 并同步宿主**；用户于 2026-10-27 决定本轮跳过剩余真机验收，未验项目不再阻塞后续开发，也不计为通过。R3 此前 RC 的构建、验包、实际宿主安装及 dry-run 启动/重启/浏览器面板已通过；该包不含后续直升机/海战增量，真实游戏与语音未终验。
- 最近完整 pytest：**1571 passed**（新增41，定向142）；本轮提示词与最终投递回归通过。旧 SDK/隔离跨进程、Hosted UI 546 场景均保留此前证据范围；本轮未调用模型/TTS，实际语气尚未试听。

此前 RC 构建与隔离验证见 [RC 验证记录](docs/RC离线验证-20261027.md)；实际安装和本轮 dry-run 证据见 [宿主验收记录](docs/RC宿主验收-20261027.md)。

- 四域可信事实摘要（P1a）已完成：复用现有 dashboard/状态卡，在概览呈现最多五项白名单事实、独立来源时效、未知/失效状态、能力与限制，并跳转活动页查看未播原因；不新增检测、模型调用、推送或持久化。舰艇/未知域仅地图事实，静态资料和未验证仪表不进入读数摘要。当前运行文件已 review、备份同步，配置/状态保留，见 [开发记录](docs/P1-四域可信事实摘要-20261029.md)。
- 陆战已注册 `ground_laser_warning`、`ground_crew_loss`、`ground_ammo_low`、`ground_ammo_empty`。乘员/弹药三项的真实输出共用默认关闭的 `ground_status_real_output_enabled`；激光沿用既有策略。岗位只读，不注册岗位 Detector。
- 状态面板已显示乘员、一级待发弹、稳定器、档位、岗位和 LWS 设备枚举；按独立载具采样年龄收起无效/过期数据。弹药/激光条件失效时撤销缓冲或失败重试的旧候选。
- 直升机概览/诊断新增只读状态卡：旋翼转速、离地高度 AGL、升降速度；缺失/非法值保持未知，沿用 5 秒载具采样时效。只展示仪表，不产生 VRS 或转速播报，见 [开发记录](docs/直升机只读状态卡-20261027.md)。
- VRS dry-run 已接入 `heli_vrs_risk`：消费已有 flags，已知且新鲜的直升机载具采样才确认；活动页显示仅记录/已阻断/已失效。真实模式在仲裁和 Dispatcher 硬阻断，无启用开关，见 [VRS 开发记录](docs/直升机VRS-dry-run-20261027.md)。
- 舰艇静态继承与改装声明解析已完成：734 个配置的 14 项基础字段保持直接声明且逐项未变；618 个配置的 14,313 个改装声明已关联公共定义，标注本地标量候选来源、前序/依赖、分层效果与显式空块。模板与缺失/循环分支有合成回归，本批未观察到文件继承指令或直接模板引用。已安装改装、模式、引擎合并及当前生效参数仍未知。 真实输出保持关闭，见 [本轮记录](docs/舰艇继承与改装解析-20261029.md)。
- 舰艇字段证据与独立采样边界已完成：v1.11 成功采样编号/时间/战局/生命绑定、失败与跨生命撤销和旧数据层兼容；高级详情显示状态/进度，不显示读数，语义和真实输出未开放。固定提交 datamine 与本地白名单审计分层记录，见 [本轮记录](docs/舰艇独立采样与字段证据-20261029.md)。
- 海战检测结果对照已完成：每次确认关联候选、实际仲裁原因和 dry-run 记录，普通模式也可查看；不按事件名猜测成功，不沿用旧确认，见 [开发记录](docs/海战检测结果对照-20261028.md)。
- 海战只读 dry-run 诊断卡已在概览/诊断显示来源状态、独立采样序号、出现/消失确认进度和未触发原因；刷新不累计检测，真实输出始终关闭，见 [诊断卡记录](docs/海战dry-run检测诊断卡-20261027.md)。
- 海战 `naval_map_contact` / `naval_air_contact` 已完成 dry-run 检测：两次不同成功地图采样确认，仅记录图标类别出现；真实输出双边界硬阻断，无启用开关，见 [态势事件记录](docs/海战态势事件-dry-run-20261027.md)。
- 海战域识别与字段边界已完善：有效 `ship/fleet` 才确认 naval；缺失/地图图标保留 unknown，仍显示通用地图卡；海战/未知域不消费飞行/陆战残留仪表，见 [域识别开发记录](docs/海战域识别与字段边界-20261027.md)。
- 海战只读地图态势卡已在概览/诊断展示可见敌友数量、敌方空中图标及最近敌方图标的平面距离/绝对方位；成功地图采样独立计龄并绑定生命，缺失/过期隐藏，不新增播报，见 [海战开发记录](docs/海战只读地图态势-20261027.md)。
- V2 proximity / objective awareness 的 code/offline scope 已完成，后方/尾随/目标点受限真实输出仍默认关闭，正式真机 evidence 待补；free-text 保持 `free_text_dry_run_only`，replay 静默，recovery 暂缓。
- 此前 P1b 同步记录：实际宿主已在此前 RC 安装上备份同步 P1b 轮入口、按需模块和面板 3 个运行文件，**63 个运行源码文件与当时源码一致**；配置/状态及宿主已有修改保留，安装副本真实 SDK 注册/回调/角色重绑/停用/重启通过。原用户会话未重载，按需解释仍默认关闭。本轮未重建 RC，旧包保留原始 hash；未 commit/push/发布。
- 逻辑入口已统一使用标准 pytest；文档审计从统一状态文档读取基线、排除明确的历史证据。前一轮完整 preflight 与 release-readiness 已在实际开发宿主上通过；verdict 为 `ready_for_final_live_smoke`，真实游戏与声音验收仍待完成。

当前事实以 [当前开发状态](docs/当前开发状态.md) 为统一入口；[实现计划](docs/实现计划-codex.md)、[待办](docs/待办事项.md)、[真机验收矩阵](docs/真机验证-checklist.md#剩余验收矩阵) 和 [发布准备](docs/v1-release-readiness.md) 使用同一口径。六月/七月 handoff 和样本结果属于历史证据。

## 总开发路线

[总开发计划](docs/实现计划-codex.md) 按可信观察、四域实用能力、发言时机、自然陪伴和低维护交付梳理全局；[能力差距矩阵](docs/副驾驶能力差距矩阵-20261029.md) 区分已实现、开发缺口、证据缺口与输出限制。P1a 有界只读摘要已实现；P1b 会话按需解释已实现，见 [实现记录](docs/P1b-按需解释入口实现-20261029.md)：默认关闭、显式启用绑定当前角色，三视图复用摘要，角色切换需显式重绑，采用评审预算/限流。普通回复沿用宿主设置，具体历史因果仍不开放；P2 [首项选型评审](docs/P2-首项实用能力选型评审-20261029.md) 已完成，其推荐 P2a 已按原卡只读方案实现/review/同步，见 [P2a 记录](docs/P2a-陆战待发弹状态解释-20261029.md)（无新增模型 token/告警）；原输出闸不变。

## 接手开发

从本独立插件仓库工作，先检查未提交修改与工作区 `WORKSPACE.md`。数据层运行合同通过 HTTP `:8112`；输出统一走 `adapters/neko_dispatcher.py`，不新增战雷专用宿主核心逻辑。当前 Python 命令统一使用 `uv run`。

每次启动默认 dry-run；真实输出门控、未知字段降级、隐私白名单和受保护 worktree 边界保持不变。`test_say` 是独立的显式开口动作，即使战斗仍 dry-run 也可能发声，安全暂停时仍会阻断；不能以“dry-run 下开口测试必须被拦”排查旧副本。

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
uv run python tools\replay_8112_server.py local_samples\data_process_20260630 --port 8112 --player-name "Player#123456" --end-offline
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
cd D:\Users\zheng\Desktop\code\N-E-K-O-Warthunder\N.E.K.O
uv run python -m plugin.neko_plugin_cli.cli check D:\Users\zheng\Desktop\code\N-E-K-O-Warthunder\project-N-E-K-O-Warthunder-8111-data-plugin
```

## 运行时启动注意（独立插件仓库）

实际开发宿主为相邻 `N.E.K.O/`，`plugin/plugins/neko_warthunder/` 当前是普通同步副本。源码变更需先 review/验证，再备份同步；保留宿主配置值、`.runtime_state.json` 等状态和已有宿主改动。不要为满足旧说明强行改成 junction，也不要覆盖 `N.E.K.O-warthuder/`。

手动启动前检查端口占用，在前台终端从宿主目录运行 `uv run python launcher.py`；按实际配置确认服务地址，默认主后端/插件服务/数据层端口通常为 48911/48916/8112。停止本次启动的服务后确认端口释放，不停止原有 external 数据层。

不要额外把 `PLUGIN_CONFIG_ROOT` 指向外层多仓库工作区，避免扫描出重复插件 ID。确认 `neko_warthunder` 只注册一次，Hosted UI context/actions 可用，且加载路径确为已同步的运行副本。`set_dry_run` 只覆盖本次会话，重启后回到保守默认。

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
