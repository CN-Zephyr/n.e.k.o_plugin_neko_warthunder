# neko_warthunder offline readiness report

- sample root: `local_samples\data_process_20260620`
- files: `14`
- frames: `10443`
- status: `needs_more_samples`

## Team brief

- ready: -
- blocked: `numeric_safety:needs_more_samples`, `ownership:needs_more_samples`, `free_text_safety:dry_run_only`, `replay_degrade:needs_more_samples`, `profile_calibration:needs_more_samples`
- next: `capture_replay_true_sample`, `trigger_overspeed_critical`, `use_v16_combat_feed_ownership_fields`

## Observed outputs

- `low_alt_danger/enter/critical`
- `low_alt_danger/enter/warning`
- `low_fuel/enter/warning`
- `overheat/enter/critical`
- `overheat/enter/warning`
- `overspeed/enter/warning`
- `spawn/enter/warning`
- `stall_risk/enter/critical`
- `stall_risk/enter/warning`

## Next test focus

- `capture_replay_true_sample`
- `free_text_dry_run_only`
- `runtime_output_backpressure`
- `kill_coalescing`
- `overspeed_critical`
- `profile_oil_overheat`
- `profile_powertrain_failure`
- `profile_hud_notice_severity`

## Validation checks

| check | status | detail |
| --- | --- | --- |
| free_text_safety | dry_run_only | `awards=1932/blocked`, `combat_feed=2314/blocked`, `hud_notices=636/blocked` |
| numeric_safety | needs_more_samples | `overspeed_critical` |
| ownership | needs_more_samples | `ownership_fields` |
| profile_calibration | needs_more_samples | `oil_overheat`, `powertrain_failure`, `hud_notice_severity` |
| replay_degrade | needs_more_samples | `replay_true` |

## Coverage gaps

- `no_replay_true_frames`
- `no_overspeed_critical_flags`
- `combat_feed_missing_ownership_fields`
- `no_oil_overheat_notice_codes`
- `no_powertrain_failure_notice_codes`
- `hud_notice_severity_unknown`

## Next validation steps

- `capture_replay_true_sample`
- `trigger_overspeed_critical`
- `use_v16_combat_feed_ownership_fields`
- `capture_oil_overheat_notice`
- `wait_for_powertrain_profile_or_sample`
- `verify_hud_notice_severity_mapping`
- `verify_output_backpressure`
- `verify_kill_coalescing`
- `verify_user_chat_interference_quiet_window`

## Operator quick checklist

| 顺序 | 用户操作 | 我方监控重点 | 通过标准 |
| --- | --- | --- | --- |
| 0 | 先跑离线门禁，或确认当天代码未变。 | tests/run_logic_tests.py、pytest、host boundary gate、plugin check、sample/live plan。 | 离线基线通过，操作清单包含 P1/P2 待测项；宿主边界检查证明不需要提交战雷专用核心补丁。 |
| 1 | 启动宿主、Hosted UI、数据层，打开面板。 | 48911/health、48916/health、8112/health、Hosted UI context/actions。 | 三项 health 正常，context 非空，actions 可调用。 |
| 2 | 进战局前设置玩家名。 | /api/identity、combat.self.source、combat.player_name。 | combat.self.source=manual，后续 ownership 围绕该昵称生效。 |
| 3 | 保持 `dry_run=true`，打一轮常规空战或陆战。 | observe.last_event、observe.last_decision、observe.last_output_status、processed.flags。 | 事件能解释为 allowed / preempt / cooldown / scenario_gated / dry_run 输出之一。 |
| 4 | 触发或等待 owned kill / death。 | combat.feed[].is_my_kill / is_my_death、you_killed / you_died。 | 生成 generic kill/death，不含 raw 玩家名；death / critical 仍可抢占。 |
| 5 | 观察 awards / hud_notices / combat.feed 自由文本源。 | free_text_safety.status、source_details、prompt / dry_run 输出。 | free_text=dry_run_only，raw HUD / combat.feed / awards 原文不进入 prompt。 |
| 6 | 若出现 replay，继续观察不要手动触发输出。 | replay=true、detector_suppressed/replay、output_blocked。 | replay 帧静默，live_monitor 显示 replay suppressed，不真实开口。 |
| 7 | 条件允许时关闭 `dry_run`，复测数值安全或 generic kill/death。 | push_message、last_output_status、output_backpressure、event_expired、repeated_event_collapsed、event_age_seconds、event_expires_at、target_lanlan、battle_reply_contract、live_reply_contract、max_reply_chars、kill_coalesced、plugin_owned_output。 | 真实开口不刷屏，旧回复晚到减少，过期旧事件不真实 push，同类安全提示短窗折叠，击杀夸夸不被普通过载背压吃掉，目标会话不走 fallback session，短播报合同不丢失。 |
| 7a | 真实开口或样本回放期间手动给猫发日常消息。 | 聊天窗口、用户输入后约 10 秒内的战雷 callback、battle_event metadata。 | 危急动作类默认以 `blind+plugin` 短句直出，不混入这轮日常回复；`spawn`、击杀/阵亡、过热、低油、普通接近、目标点和结算走 bounded `respond`；critical 危险仍可按插话策略插队。 |
| 8 | 若出现动力故障 HUD 技术通知，不急着判断成播报事件。 | powertrain_failure、deferred_hud_notice、detector_suppressed、raw HUD 是否被阻断。 | 只显示 deferred 可观测记录，不真实开口，不泄漏 raw HUD 文本。 |

## Next live-test plan

| priority | area | status | action |
| --- | --- | --- | --- |
| P1 | 回放降级 | needs_more_samples | capture_replay_true_sample |
| P1 | 自由文本安全 | dry_run_only | run_free_text_dry_run_safety_check |
| P1 | 击杀/死亡归属 | needs_more_samples | use_v16_combat_feed_ownership_fields |
| P2 | 数值安全事件 | needs_more_samples | trigger_overspeed_critical |
| P2 | 油温/动力故障校准 | needs_more_samples | capture_oil_overheat_notice |
| P2 | 油温/动力故障校准 | needs_more_samples | wait_for_powertrain_profile_or_sample |
| P2 | 油温/动力故障校准 | needs_more_samples | verify_hud_notice_severity_mapping |
| P2 | T-Output 真实开口背压 | needs_live_review | verify_output_backpressure |
| P2 | T-Kill-Coalesce 多杀合并 | needs_live_review | verify_kill_coalescing |
| P2 | 用户聊天干扰静默窗 | needs_live_review | verify_user_chat_interference_quiet_window |

## Remaining live-test scope

- `numeric_safety:needs_more_samples`
- `ownership:needs_more_samples`
- `free_text_safety:dry_run_only`
- `replay_degrade:needs_more_samples`
- `profile_calibration:needs_more_samples`

## Safety notes

- Raw player names, HUD text, combat feed text, and awards text are not included.
- free_text_safety=dry_run_only means the sample contains free-text sources, but real speech remains blocked.
