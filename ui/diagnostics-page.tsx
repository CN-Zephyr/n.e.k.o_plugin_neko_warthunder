import { ActionButton, Button, RefreshButton, StatusBadge, useClipboard, useToast } from "@neko/plugin-ui"
import type { HostedAction, HostedApi } from "@neko/plugin-ui"
import { NavalCards } from "./naval-cards"
import {
  CONN_STATE_LABELS, DATA_LAYER_LABELS, DIALOGUE_LABELS, DOMAIN_LABELS, RISK_LEVEL_LABELS, SAFETY_STATUS_LABELS,
  SCENARIO_LABELS, flagsText, listText, mappedText, outputFailed, outputWasPushed, percentText, safetyIsPaused,
  safetyIsTripped, text,
} from "./panel-display"
import { numberText } from "./panel-format"
import type { PanelTone } from "./panel-format"
import type { DashboardState, GroundStatusState, TrustedFactsState } from "./panel-state"
import { VehicleCards } from "./vehicle-cards"

export const DiagnosticsPage = { View: Diagnostics }

const FLIGHT_SOURCE_LABELS: Record<string, string> = {
  ready: "可用", partial: "部分通道可用", waiting: "等待有效数据", stale: "已过期，收起估算",
  unavailable: "暂无有效数据", unknown_age: "来源时间未知", invalid_clock: "来源时钟异常",
  offline: "离线", dead: "已阵亡", replay: "回放中",
}

function diagnosticCode(value: unknown): string {
  const raw = text(value)
  return raw !== "-" && /^[A-Za-z0-9_.:/-]{1,96}$/.test(raw) ? raw : "-"
}

function buildSafeDiagnosticSummary(state: DashboardState): string {
  const safety = state.safety || {}
  const dataLayer = state.data_layer || {}
  const outputPolicy = state.output_policy || {}
  const decision = state.observe?.last_decision
  const output = state.observe?.last_output_status
  const enabledCategories = ["safety", "combat", "radio", "awareness", "lifecycle"]
    .filter((category) => outputPolicy.broadcast_categories?.[category] !== false)
    .join(",")

  return [
    "N.E.K.O 战雷副驾驶安全诊断摘要",
    "format=neko_warthunder.safe_diagnostics.v1",
    `generated_at=${new Date().toISOString()}`,
    `plugin enabled=${text(state.enabled)} connected=${text(state.connected)} game_context=${text(state.game_context_active)}`,
    `battle in_battle=${text(state.in_battle)} dead=${text(state.dead)} domain=${diagnosticCode(state.domain)} scenario=${diagnosticCode(state.scenario)} level=${diagnosticCode(state.level)}`,
    `data health=${text(dataLayer.health)} mode=${diagnosticCode(dataLayer.mode)}`,
    `policy dry_run=${text(state.dry_run)} safety=${diagnosticCode(safety.status)} manual_paused=${text(safety.manual_paused)} auto_paused=${text(safety.auto_paused)}`,
    `speech dialogue=${diagnosticCode(outputPolicy.dialogue_intrusion_mode)} frequency=${diagnosticCode(outputPolicy.broadcast_frequency)} categories=${enabledCategories || "none"}`,
    `decision event=${diagnosticCode(decision?.event_id)} stage=${diagnosticCode(decision?.stage)} outcome=${diagnosticCode(decision?.outcome)} reason=${diagnosticCode(decision?.reason)}`,
    `output event=${diagnosticCode(output?.event_id)} stage=${diagnosticCode(output?.stage)} outcome=${diagnosticCode(output?.outcome)} reason=${diagnosticCode(output?.reason)} pushed=${text(output?.pushed)}`,
    "privacy=不含昵称、聊天、HUD、目标、载具、URL、PID、错误原文或 prompt/payload 原文",
  ].join("\n")
}

type AdvancedDetailItem = {
  key: string
  label: string
  value: string
}

function AdvancedDetailGroup({
  title,
  description,
  items,
}: {
  title: string
  description: string
  items: AdvancedDetailItem[]
}) {
  return (
    <section className="wt-advanced-group">
      <header className="wt-advanced-group-head">
        <h3>{title}</h3>
        <p>{description}</p>
      </header>
      <dl className="wt-advanced-list">
        {items.map((item) => (
          <div key={item.key} className="wt-advanced-field" data-empty={item.value === "-" ? "true" : "false"}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function unwrapActionResult(envelope: any): Record<string, any> {
  if (envelope && typeof envelope === "object") {
    if (envelope.result && typeof envelope.result === "object") return envelope.result
    return envelope
  }
  return {}
}

function diagnosticStatus(state: DashboardState, kind: string): { label: string; tone: PanelTone; detail: string } {
  const output = state.observe?.last_output_status
  if (kind === "game") {
    return state.in_battle
      ? { label: "正常", tone: "success", detail: `已检测到${mappedText(state.domain, DOMAIN_LABELS)}` }
      : { label: "未进战局", tone: "info", detail: "系统已待命，进入战局后会自动开始识别" }
  }
  if (kind === "data") {
    const mode = String(state.data_layer?.mode || "unknown")
    if (state.data_layer?.health === false && (mode === "starting" || mode === "unknown")) {
      return { label: "准备中", tone: "info", detail: "8112 数据服务正在启动或等待首次健康检查" }
    }
    return state.data_layer?.health === false
      ? { label: "异常", tone: "danger", detail: "8112 数据服务暂时不可用" }
      : { label: "正常", tone: "success", detail: "数据服务可用" }
  }
  if (kind === "plugin") {
    if (!state.connected) return { label: "等待连接", tone: "info", detail: "插件尚未收到战雷数据" }
    return state.in_battle
      ? { label: "正常", tone: "success", detail: "插件正在接收并识别战局数据" }
      : { label: "已待命", tone: "success", detail: "插件连接正常，等待战局数据" }
  }
  if (kind === "policy") {
    if (safetyIsTripped(state)) {
      return { label: "安全保护", tone: "danger", detail: "自动保护阻止新的输出" }
    }
    if (safetyIsPaused(state)) return { label: "已暂停", tone: "warning", detail: "事件只记录，不提交语音" }
    if (state.dry_run) return { label: "播报未启动", tone: "info", detail: "按当前选择，事件只记录、不提交语音" }
    return { label: "正常", tone: "success", detail: "允许提交可信提醒" }
  }
  if (outputWasPushed(output)) {
    return { label: "已接收", tone: "success", detail: "最近一次请求已交给猫娘" }
  }
  if (outputFailed(output)) {
    return { label: "异常", tone: "danger", detail: "最近一次提交失败" }
  }
  return { label: "尚未测试", tone: "info", detail: "当前没有已提交的语音请求" }
}

function diagnosticOverview(state: DashboardState): { title: string; detail: string; tone: PanelTone } {
  const dataMode = String(state.data_layer?.mode || "unknown")
  const output = state.observe?.last_output_status
  if (state.data_layer?.health === false && dataMode !== "starting" && dataMode !== "unknown") {
    return { title: "数据服务暂时不可用", detail: "战雷数据在进入插件前已经中断，请先重新检查；仍未恢复时再重载插件。", tone: "danger" }
  }
  if (outputFailed(output)) {
    return { title: "最近一次输出没有成功", detail: "战局识别仍可能正常，可以展开“猫娘接收”查看原因并重新测试。", tone: "danger" }
  }
  if (safetyIsTripped(state)) {
    return { title: "安全保护已暂停新的输出", detail: "事件仍会继续识别和记录；处理安全保护后再恢复播报。", tone: "danger" }
  }
  if (safetyIsPaused(state)) {
    return { title: "战斗播报已临时暂停", detail: "数据链路仍然工作，返回概览页点击“恢复”即可继续输出。", tone: "warning" }
  }
  if (!state.in_battle) {
    return { title: "系统已待命，等待进入战局", detail: "数据服务和插件连接正常；当前未进战局不是故障。", tone: "info" }
  }
  if (state.dry_run) {
    return { title: "战局识别正常，战斗播报尚未开启", detail: "事件会被检测和记录，但不会提交给猫娘；可在概览页主动开启。", tone: "info" }
  }
  return { title: "运行链路正常", detail: "战雷数据、插件识别和输出策略均可用。", tone: "success" }
}

function diagnosticGuidance(state: DashboardState, kind: string): string {
  if (kind === "game") {
    return state.in_battle
      ? "无需处理。载具或模式变化后，这里会自动更新。"
      : "启动 War Thunder 并进入一局战斗；机库、菜单和观战准备阶段不会被当作正在战斗。"
  }
  if (kind === "data") {
    return state.data_layer?.health === false
      ? "先点击“重新检查”。如果仍显示异常，再使用宿主提供的“重载”按钮重新启动插件。"
      : "无需处理。数据服务负责把本机 8111 遥测整理为插件可消费的 8112 数据。"
  }
  if (kind === "plugin") {
    return state.connected
      ? "无需处理。未进入战局时保持待命是正常状态。"
      : "确认数据服务正常后重新检查；若仍未连接，再重载插件。"
  }
  if (kind === "policy") {
    if (safetyIsTripped(state)) return "先处理安全保护原因，再返回概览页恢复播报。"
    if (safetyIsPaused(state)) return "返回概览页点击“恢复”。"
    if (state.dry_run) return "这是用户选择，不是故障。需要语音提醒时，在概览页点击“开启战斗播报”。"
    return "无需处理。可信事件可以按当前插话规则提交给猫娘。"
  }
  const output = state.observe?.last_output_status
  if (outputFailed(output)) return "点击“测试开口”复验声音链路；失败时再查看高级详情中的最近输出原因。"
  if (outputWasPushed(output)) return "最近一次请求已成功交给猫娘，无需处理。"
  return "点击“测试开口”可独立验证猫娘接收和声音输出，不需要先进入战局或开启战斗播报。"
}

function Diagnostics({ state, groundForDisplay, factsForDisplay, openActivity, api, testSayAction }: {
  state: DashboardState
  groundForDisplay: GroundStatusState
  factsForDisplay: TrustedFactsState | null | undefined
  openActivity: () => void
  api: HostedApi
  testSayAction?: HostedAction
}) {
  const detectOnly = state.dry_run !== false
  const clipboard = useClipboard()
  const toast = useToast()
  const safety = state.safety || {}
  const dataLayer = state.data_layer || {}
  const telemetry = state.telemetry || {}
  const flightDiagnostics = state.flight_diagnostics
  const takeoffProtection = state.takeoff_protection || {}
  const outputPolicy = state.output_policy || {}
  const awareness = state.awareness || {}
  const latestProximity = awareness.latest_proximity || {}
  const situation = awareness.situation || {}
  const nearestGroundTarget = awareness.nearest_ground_target || {}
  const observe = state.observe || {}

  function handleTestResult(envelope: any) {
    const result = unwrapActionResult(envelope)
    // 后端 test_say 声明 refresh_context=False，动作按钮也传 refresh={false}，
    // 好让这里先处理结果再刷新；但它确实写了 timeline，不刷新的话诊断页第 5 步
    // "猫娘接收"会一直停在"尚未测试"，与这里弹出的成功提示自相矛盾。
    void api.refresh().catch(() => undefined)
    if (result.pushed) {
      toast.success("测试请求已交给猫娘")
      return
    }
    if (result.blocked === "dry_run") {
      // 兼容内存里仍在跑旧版后端的情况：旧版 test_say 在 dry_run 下返回
      // blocked="dry_run"，当前版本只会返回 SafetyGuard 的 tripped/paused/running。
      // 确认不再有旧版共存后可删除本分支。
      toast.warning("当前运行版本仍限制测试开口，请重载插件后再试")
      return
    }
    if (result.blocked) {
      toast.warning("测试请求已被暂停或安全保护阻止")
      return
    }
    toast.info("测试请求已完成")
  }

  async function copyDiagnosticSummary() {
    const copied = await clipboard.write(buildSafeDiagnosticSummary(state))
    if (copied) toast.success("安全诊断摘要已复制")
    else toast.error("复制失败，请检查系统剪贴板权限")
  }

  const gameStep = diagnosticStatus(state, "game")
  const dataStep = diagnosticStatus(state, "data")
  const pluginStep = diagnosticStatus(state, "plugin")
  const policyStep = diagnosticStatus(state, "policy")
  const nekoStep = diagnosticStatus(state, "neko")
  const diagnosticsOverview = diagnosticOverview(state)
  const diagnosticChecks = [
    { key: "game", index: 1, title: "战雷客户端", ...gameStep },
    { key: "data", index: 2, title: "数据服务", ...dataStep },
    { key: "plugin", index: 3, title: "插件识别", ...pluginStep },
    { key: "policy", index: 4, title: "输出策略", ...policyStep },
    { key: "neko", index: 5, title: "猫娘接收", ...nekoStep },
  ]

  return (
    <div className="wt-diagnostics">
      <section className="wt-diagnostics-summary" data-tone={diagnosticsOverview.tone} aria-live="polite">
        <div>
          <h2>{diagnosticsOverview.title}</h2>
          <p>{diagnosticsOverview.detail}</p>
        </div>
        <div className="wt-diagnostics-actions">
          <RefreshButton label="重新检查" />
          <Button onClick={() => { void copyDiagnosticSummary() }}>
            {clipboard.copied ? "已复制" : "复制诊断摘要"}
          </Button>
          {testSayAction ? <ActionButton
            className="wt-test-sound-action"
            action={testSayAction}
            actionId="test_say"
            values={{ text: "副驾驶面板测试：能听到我吗？" }}
            refresh={false}
            onResult={handleTestResult}
            onError={() => { toast.error("测试请求提交失败") }}
          >
            测试开口
          </ActionButton> : (
            <Button className="wt-test-sound-action" disabled>测试开口（动作未就绪）</Button>
          )}
        </div>
      </section>

      <section>
        <div className="wt-diagnostics-section-head">
          <div>
            <h2>运行链路</h2>
            <p>展开任一步即可查看它的含义和建议操作。</p>
          </div>
          <span className="wt-mode-detail">按当前状态实时更新</span>
        </div>
        <div className="wt-diagnostic-checks">
          {diagnosticChecks.map((item) => (
            <details key={item.key} className="wt-diagnostic-check" data-tone={item.tone} open={item.tone === "danger" || item.tone === "warning"}>
              <summary>
                <span className="wt-diagnostic-index">{item.index}</span>
                <div className="wt-diagnostic-copy">
                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                </div>
                <StatusBadge tone={item.tone} label={item.label} />
                <span className="wt-diagnostic-more">详情</span>
              </summary>
              <p className="wt-diagnostic-help"><strong>建议：</strong>{diagnosticGuidance(state, item.key)}</p>
            </details>
          ))}
        </div>
      </section>

      <details className="wt-advanced-details">
        <summary>
          <strong>高级详情</strong>
          <span>原始状态与维护字段</span>
        </summary>
        <div className="wt-advanced-content">
          {factsForDisplay ? <VehicleCards.TrustedFactsCard facts={factsForDisplay} openActivity={openActivity} /> : null}
          <p className="wt-advanced-intro">维护信息不会影响正常使用。排查问题时，优先查看有明确数值或错误内容的字段。</p>
          <div className="wt-advanced-grid">
            <AdvancedDetailGroup
              title="连接状态"
              description="插件与本机数据服务是否正常通信"
              items={[
                { key: "enabled", label: "插件启用", value: text(state.enabled) },
                { key: "connected", label: "数据连接", value: state.connected ? "已连接" : "未连接" },
                { key: "conn_state", label: "连接阶段", value: mappedText(state.conn_state, CONN_STATE_LABELS) },
                { key: "context", label: "战雷上下文", value: state.game_context_active ? "已注入" : "未注入" },
                { key: "mode", label: "数据层模式", value: mappedText(dataLayer.mode, DATA_LAYER_LABELS) },
                { key: "health", label: "数据层健康", value: text(dataLayer.health) },
                { key: "pid", label: "数据层 PID", value: text(dataLayer.pid) },
                { key: "error", label: "最近错误", value: text(dataLayer.last_error) },
              ]}
            />
            <AdvancedDetailGroup
              title="战场状态"
              description="当前识别到的战局、载具与风险上下文"
              items={[
                { key: "battle", label: "战斗内", value: text(state.in_battle) },
                { key: "dead", label: "阵亡状态", value: text(state.dead) },
                { key: "domain", label: "模式", value: mappedText(state.domain, DOMAIN_LABELS) },
                { key: "vehicle", label: "载具", value: text(state.vehicle_type) },
                { key: "profile_source", label: "数据库来源", value: text(state.profile_source) },
                { key: "profile_family", label: "载具族", value: text(state.profile_family) },
                { key: "profile_matched", label: "数据库匹配", value: text(state.profile_matched) },
                { key: "scenario", label: "场景", value: mappedText(state.scenario, SCENARIO_LABELS) },
                { key: "level", label: "风险等级", value: mappedText(state.level, RISK_LEVEL_LABELS) },
              ]}
            />
          </div>

          <VehicleCards.VehicleStatusCards state={state} ground={groundForDisplay} dryRun={detectOnly} />

          {state.naval_instrument_fields ? <NavalCards.NavalInstrumentFieldCard inventory={state.naval_instrument_fields} /> : null}
          {state.naval_static_reference ? <NavalCards.NavalStaticReferenceCard reference={state.naval_static_reference} /> : null}

          {state.domain === "air" || state.domain === "heli" ? (
            <div className="wt-advanced-grid">
              <AdvancedDetailGroup
                title="飞行诊断"
                description="用于判断飞行状态和遥测新鲜度"
                items={[
                  { key: "radio_altitude", label: "雷达高度", value: numberText(telemetry.radio_altitude_m, "m") },
                  { key: "altitude", label: "海拔高度", value: numberText(telemetry.altitude_m, "m") },
                  { key: "ias", label: "指示空速", value: numberText(telemetry.ias_kmh, "km/h") },
                  { key: "mach", label: "马赫数", value: numberText(telemetry.mach, "", 2) },
                  { key: "climb", label: "垂直速度", value: numberText(telemetry.climb_ms, "m/s", 1) },
                  { key: "fuel", label: "燃油比例", value: percentText(telemetry.fuel_fraction) },
                  ...(state.domain === "air" ? [
                    { key: "oil_state", label: "原生油温状态", value: mappedText(flightDiagnostics?.oil.status, FLIGHT_SOURCE_LABELS) },
                    { key: "oil_max", label: "已观测通道最高油温", value: numberText(flightDiagnostics?.oil.max_c, "°C", 1) },
                    { key: "oil_channels", label: "有效 / 不可用通道", value: `${text(flightDiagnostics?.oil.observed_channels)} / ${text(flightDiagnostics?.oil.unavailable_channels)}` },
                    { key: "oil_source", label: "油温来源与边界", value: "/state 明确 C 单位；仅已观测通道，生命绑定未确认" },
                    { key: "fuel_estimate_status", label: "耗油估算状态", value: mappedText(flightDiagnostics?.fuel_estimate.status, FLIGHT_SOURCE_LABELS) },
                    { key: "fuel_burn", label: "估算耗油率", value: numberText(flightDiagnostics?.fuel_estimate.burn_kgs, "kg/s", 3) },
                    { key: "fuel_remaining", label: "估算剩余时间", value: numberText(flightDiagnostics?.fuel_estimate.remaining_sec, "s", 0) },
                    { key: "fuel_change_age", label: "距燃油变化 / 基线", value: numberText(flightDiagnostics?.fuel_estimate.age_sec, "s", 1) },
                    { key: "fuel_max_age", label: "估算有效期", value: numberText(flightDiagnostics?.fuel_estimate.max_age_sec, "s", 1) },
                  ] : []),
                  { key: "flags", label: "当前标记", value: flagsText(telemetry.flags) },
                  { key: "age", label: "数据延迟", value: numberText(telemetry.age_seconds, "s", 1) },
                ]}
              />
              <AdvancedDetailGroup
                title="起飞保护"
                description="避免刚起飞时产生不必要的风险播报"
                items={[
                  { key: "active", label: "保护状态", value: takeoffProtection.active ? "生效" : "未生效" },
                  { key: "available", label: "雷达高度可用", value: text(takeoffProtection.radio_altitude_available) },
                  { key: "agl", label: "当前离地高度", value: numberText(takeoffProtection.radio_altitude_m, "m") },
                  { key: "enter", label: "进入阈值", value: numberText(takeoffProtection.enter_m, "m") },
                  { key: "exit", label: "解除阈值", value: numberText(takeoffProtection.exit_m, "m") },
                  { key: "grace", label: "时间保护", value: numberText(takeoffProtection.low_alt_grace_seconds, "s") },
                  { key: "suppresses", label: "当前压制", value: listText(takeoffProtection.suppresses) },
                ]}
              />
            </div>
          ) : null}

          <div className="wt-advanced-grid">
            <AdvancedDetailGroup
              title="接近感知"
              description="附近目标与威胁的聚合结果"
              items={[
                { key: "count", label: "接近事件数", value: text(awareness.proximity_event_count) },
                { key: "kind", label: "最近类型", value: text(latestProximity.kind) },
                { key: "target", label: "目标类型", value: text(latestProximity.target_type) },
                { key: "distance", label: "距离", value: numberText(latestProximity.distance_m, "m") },
                { key: "compass", label: "方位", value: text(latestProximity.compass) },
                { key: "enemy", label: "敌方单位", value: text(situation.enemy_count) },
                { key: "air", label: "空中威胁", value: text(situation.air_threat_count) },
                { key: "ground", label: "任务目标", value: text(situation.ground_target_count) },
                { key: "grid", label: "最近目标网格", value: text(nearestGroundTarget.grid) },
                { key: "ground_distance", label: "最近目标距离", value: numberText(nearestGroundTarget.distance_m, "m") },
              ]}
            />
            <AdvancedDetailGroup
              title="安全控制"
              description="决定战斗事件是否允许提交给猫娘"
              items={[
                { key: "safety", label: "安全门状态", value: mappedText(safety.status, SAFETY_STATUS_LABELS) },
                { key: "manual", label: "手动暂停", value: text(safety.manual_paused) },
                { key: "auto", label: "自动暂停", value: text(safety.auto_paused) },
                { key: "failures", label: "失败次数", value: text(safety.failures) },
                { key: "dry_run", label: "战斗播报", value: state.dry_run ? "未启动" : "已启动" },
                { key: "dialogue", label: "插话策略", value: mappedText(outputPolicy.dialogue_intrusion_mode, DIALOGUE_LABELS) },
                { key: "user_window", label: "用户对话保护", value: numberText(outputPolicy.user_chat_quiet_window_seconds, "s") },
                { key: "battle_window", label: "播报间隔保护", value: numberText(outputPolicy.battle_output_quiet_window_seconds, "s") },
              ]}
            />
          </div>

          <div className="wt-advanced-grid">
            <AdvancedDetailGroup
              title="最近决策"
              description="插件最近一次如何处理识别到的事件"
              items={[
                { key: "event", label: "最近事件", value: text(observe.last_event?.event_id) },
                { key: "decision_event", label: "决策事件", value: text(observe.last_decision?.event_id) },
                { key: "decision_stage", label: "决策阶段", value: text(observe.last_decision?.stage) },
                { key: "decision_outcome", label: "决策结果", value: text(observe.last_decision?.outcome) },
                { key: "decision_reason", label: "原因", value: text(observe.last_decision?.reason) },
                { key: "decision_scenario", label: "当时场景", value: mappedText(observe.last_decision?.scenario, SCENARIO_LABELS) },
              ]}
            />
            <AdvancedDetailGroup
              title="最近输出"
              description="最后一次播报请求的实际结果"
              items={[
                { key: "output_event", label: "输出事件", value: text(observe.last_output_status?.event_id) },
                { key: "output_stage", label: "输出阶段", value: text(observe.last_output_status?.stage) },
                { key: "output_outcome", label: "输出结果", value: text(observe.last_output_status?.outcome) },
                { key: "output_reason", label: "原因", value: text(observe.last_output_status?.reason) },
                { key: "output_safety", label: "安全门", value: mappedText(observe.last_output_status?.safety_status, SAFETY_STATUS_LABELS) },
                {
                  key: "output_dry_run",
                  label: "当时播报状态",
                  value: observe.last_output_status?.dry_run === true
                    ? "未启动"
                    : observe.last_output_status?.dry_run === false ? "已启动" : "-",
                },
              ]}
            />
          </div>
        </div>
      </details>
    </div>
  )

}
