# Host Core Reuse and Plugin Boundary

本文整理战雷插件接入主程序通用核心时的口径。

结论：

主程序已有可复用核心，不需要为战雷新增专用 host core。战雷侧应复用通用通道、队列、路由、上下文注入、显示/播报和 delivery 结果语义；所有会影响猫娘正常回复用户的战雷策略必须留在插件侧。

## 边界原则

- 主核心只负责接收、排队、路由、注入、投递、回执和通用状态暴露。
- 主核心不理解战雷事件语义，不判断战雷战况，不生成战雷专用提示词。
- 主核心不根据 `neko_warthunder`、`battle_reply_contract`、`host_callback_contract` 等业务 metadata 改写猫娘回复。
- 主核心不负责战雷短句、截断、防复读、quiet window、战术优先级、fallback 文案或事件仲裁。
- 战雷插件决定说什么、何时说、怎么说；主程序只回答能不能送到、送到哪里、是否过期、结果是什么。

## 主程序已有可复用核心

### `push_message v2`

可复用程度：高。

现有能力：

- `visibility`: `chat` / `hud`
- `ai_behavior`: `respond` / `read` / `blind`
- `parts`: text / image / audio / video / ui_action
- `metadata`
- `priority`
- `coalesce_key`
- `target_lanlan`

战雷插件应继续使用：

- 带确定短句的实时战况 cue：`visibility=["chat"]`, `ai_behavior="blind"`，由插件短句直出，降低 LLM 延迟并避免污染普通聊天上下文
- 显式实验/兼容模式下的普通 cue：`visibility=[]`, `ai_behavior="respond"`，同时携带 `plugin_recommended_reply`
- 只进上下文不打断：`ai_behavior="read"`
- 插件自有文本直显、不进 LLM：`visibility=["chat"]`, `ai_behavior="blind"`
- 同类战况替换：`coalesce_key="neko_warthunder:battle_event"`

### `ProactiveDeliveryManager`

可复用程度：高。

现有能力：

- priority 排序
- 显式 `coalesce_key` 合并
- playback/text gate
- min-gap pacing
- batched release
- global TTL stale drop
- internal delivery ack future
- retract pending cue

战雷需要补齐的是通用字段，不是战雷特判：

- per-message `expires_at`
- per-message `max_age_seconds`
- 显式 `replace_pending`
- 插件可见 delivery status

### `append_context`

可复用程度：高，但需要 SDK 化。

主程序内部已有能力：

- `source`
- `role`
- `text`
- `audience`
- `timing=now/when_ready`
- `lifetime=current_session/next_session/session_family`
- `request_id` 去重
- `ordering_key`
- source token budget
- text/voice `prime_context` 对偶
- pending ready flush

战雷侧用途：

- 注入一段安全泛化的战况背景。
- 注入持续态势摘要，而不是立即要求猫娘回复。
- 在 session 未 ready 时排队，ready 后再补上下文。

缺口：

- 插件 SDK 还没有稳定公开的 `ctx.append_context(...)`。
- source budget 目前是 host 内部硬编码，不是插件声明式注册。

### Plugin-owned mirror / passthrough

可复用程度：中高，但需要干净 API。

主程序内部已有基础：

- `passthrough_to_chat_bubble`: 前端显示插件文本，不进入 LLM 上下文。
- `mirror_assistant_output`: 作为 assistant line 镜像输出。
- `mirror_assistant_speech`: 镜像输出并走 TTS。

战雷侧用途：

- 插件完全拥有某句输出时，主程序只展示/播报。
- 适合调试、播报、或未来插件自生成的 deterministic cue。

缺口：

- 目前这些主要是 `LLMSessionManager` 内部方法。
- 需要插件 SDK 暴露成清晰的 passthrough/mirror API。
- 需要明确是否写入聊天历史、是否进 LLM context、是否触发 TTS。

### Event bridge / route

可复用程度：高。

主程序已经能把插件 `proactive_message` 转成 LLM callback，并保留：

- `metadata`
- `priority`
- `coalesce_key`
- `visibility`
- `ai_behavior`
- `target_lanlan`

战雷只需要它按通用语义转发，不需要它理解战雷。

## 战雷插件必须内置的逻辑

以下都属于会影响猫娘正常回复用户的策略，不应放主核心：

- 战况事件仲裁。
- 场景机和风险等级判断。
- 安全事件优先级。
- 输出 backpressure。
- `dry_run` / real output release gate。
- replay degrade。
- free-text safety gate。
- ownership / player identity 判断。
- kill coalescing。
- tactical freshness windows。
- quiet window 判断和 bypass 条件。
- prompt facts / intent 生成。
- 短 TTS 风格要求。
- 回复长度限制。
- fallback 文案。
- 防复读。
- 是否 respond/read/blind。
- 是否合并、替换、过期、丢弃。
- 是否使用 plugin-owned mirror/passthrough。

## 主核心应补齐的通用接口

### Delivery ack/status

建议状态：

- `queued`
- `delivered`
- `coalesced`
- `expired`
- `blocked`
- `dropped`
- `passthrough_sent`
- `passthrough_unavailable`

战雷插件需要知道：

- cue 是否进入 host queue。
- cue 是否被同 key 新 cue 替换。
- cue 是否因过期被丢弃。
- cue 是否真正投递到 LLM / chat / HUD / TTS。

### Per-message expiry

建议字段：

- `expires_at`
- `max_age_seconds`

语义：

- host 只按通用时间语义判断是否过期。
- host 不理解 `stall_risk`、`you_died` 等事件名。
- 插件负责给不同事件计算不同 freshness。

### `replace_pending`

建议语义：

- `replace_pending=true` 且 `coalesce_key` 相同：新消息替换旧 pending。
- 替换结果应通过 ack/status 返回 `coalesced` 或 `replaced`。
- 不应默认按 source 合并，必须显式 key。

### Activity/session snapshot

建议只读 API：

- 当前是否 user input active。
- 当前是否 assistant speaking / generating。
- session 是否 ready。
- 最近 user activity age。
- 最近 assistant playback age。
- 当前 lanlan/session 标识。

主核心只暴露 snapshot，不替插件判断 quiet window。

### Source budget registration

建议插件声明：

- source name
- max tokens
- default audience
- default lifetime
- 是否允许 bare prime

战雷需要的 source 例子：

- `game.realtime_context`
- `game.postgame`
- `proactive.callback`
- `warthunder.battle_cue`
- `warthunder.situation_summary`

## 需要从主核心迁出或收口的内容

以下不应作为长期通用核心保留：

- `_WARTHUNDER_*` 常量。
- 基于 `neko_warthunder` 的 quiet window 过滤。
- 基于 `battle_reply_contract` 的短句截断。
- 基于 `live_reply_contract` / `battle_reply_contract` 的回复 shape。
- 任何识别战雷事件名的 host 逻辑。
- 任何识别直播业务 metadata 的 host 逻辑。

这些应迁回插件侧，或变成完全通用字段：

- `expires_at`
- `max_age_seconds`
- `replace_pending`
- `coalesce_key`
- `priority`
- `ai_behavior`
- `visibility`
- `plugin-owned passthrough`

## 战雷当前已满足的插件侧准备

战雷插件已经具备：

- `host_callback_contract_version="neko.callback.v1"` 预约字段。
- 通用 `host_callback_contract` block。
- `delivery.coalesce_key`
- `delivery.replace_pending`
- `delivery.expires_at`
- `delivery.max_age_seconds`
- `quiet_window.policy`
- `freshness.event_age_seconds`
- `target.lanlan`
- legacy metadata 兼容字段。
- 插件侧 stale drop。
- 插件侧 output backpressure。
- 插件侧 free-text safety。
- 插件侧 replay degrade。
- 插件侧 dry-run-first release posture。

## 推荐落地顺序

1. 保留并稳定 `push_message v2` 作为唯一实时 cue 通道。
2. 给 `push_message` 增加通用 delivery options：`expires_at`、`max_age_seconds`、`replace_pending`。
3. 把 `ProactiveDeliveryManager` 的 internal ack 包装成插件可见 delivery status。
4. 暴露插件 SDK 级 `append_context`。
5. 暴露只读 activity/session snapshot。
6. 暴露 plugin-owned passthrough/mirror API。
7. 把 source budget 从 host 硬编码改成插件注册。
8. 移除 host 内部 `neko_warthunder` / `neko_live` 策略特判。

最终目标：

直播插件、战雷插件、Minecraft 插件等都只依赖同一组通用核心接口；各自业务策略留在各自插件里。
