/** War Thunder 猫娘副驾驶 Hosted UI。 */

import {
  ActionButton,
  Button,
  ButtonGroup,
  Field,
  Input,
  Modal,
  Stack,
  StatusBadge,
  Tip,
  Warning,
  useEffect,
  useRef,
  useState,
  useToast,
} from "@neko/plugin-ui"
import type { HostedAction, PluginSurfaceProps } from "@neko/plugin-ui"
import { ActivityPage } from "./activity-page"
import { DiagnosticsPage } from "./diagnostics-page"
import { OverviewPage } from "./overview-page"
import { DIALOGUE_OPTIONS, DOMAIN_LABELS, mappedText, outputFailed, outputWasPushed, safetyIsPaused, safetyIsTripped } from "./panel-display"
import { EVENT_LABELS, formatTime } from "./panel-format"
import type { ActivityItem, ActivityKind, DashboardState, IdentityState, ObserveRecord, OnDemandState, PanelSummary } from "./panel-state"
import type { PanelTone } from "./panel-format"
import { PANEL_STYLES } from "./panel-styles"
import { SettingsDialog } from "./settings-dialog"
import { GROUND_SAMPLE_MAX_AGE_MS, VehicleCards } from "./vehicle-cards"

// 面板自动刷新间隔。取 6s：数据层轮询是 0.4s 级，面板只需跟上"看得出在变"，
// 太密会给宿主 context 通道添无谓压力。
const PANEL_REFRESH_INTERVAL_MS = 6000
const GROUND_PANEL_REFRESH_INTERVAL_MS = 2000

const AIR_ONLY_EVENTS = new Set([
  "stall_risk",
  "high_aoa",
  "over_g",
  "low_alt_danger",
  "overspeed",
  "low_fuel",
  "air_threat_nearby",
  "enemy_on_six",
  "tailing_risk",
])

const GROUND_ONLY_EVENTS = new Set(["ground_laser_warning", "ground_target_nearby"])

function actionById(actions: HostedAction[], id: string): HostedAction | undefined {
  return actions.find((action) => action.id === id || action.entry_id === id)
}

function unwrapActionResult(envelope: any): Record<string, any> {
  if (envelope && typeof envelope === "object") {
    if (envelope.result && typeof envelope.result === "object") return envelope.result
    return envelope
  }
  return {}
}

function currentPlayerName(identity: IdentityState): string {
  return String(identity.player_name || identity.saved_player_name || identity.self?.name || "").trim()
}

function derivePanelSummary(state: DashboardState): PanelSummary {
  const dataHealthy = state.data_layer?.health
  const dataLayerMode = String(state.data_layer?.mode || "unknown")
  const playerName = currentPlayerName(state.identity || {})

  if (dataHealthy === false && (dataLayerMode === "starting" || dataLayerMode === "unknown")) {
    return {
      kind: "waiting",
      tone: "info",
      title: "正在准备战雷数据服务",
      detail: "首次启动可能需要一点时间，准备完成后会自动开始检测战局。",
      modeLabel: "正在连接",
    }
  }
  if (dataHealthy === false) {
    return {
      kind: "error",
      tone: "danger",
      title: "暂时无法获取战雷数据",
      detail: "不会根据旧数据播报；可以在诊断页查看中断位置。",
      modeLabel: "连接异常",
    }
  }
  if (safetyIsTripped(state)) {
    return {
      kind: "safety",
      tone: "danger",
      title: "安全保护已暂时阻止播报",
      detail: "战局检测仍在继续，恢复前不会向猫娘提交新的提醒。",
      modeLabel: "安全保护",
    }
  }
  if (safetyIsPaused(state)) {
    return {
      kind: "paused",
      tone: "warning",
      title: "播报已暂停，仍在检测战局",
      detail: "新事件会继续记录，但暂时不会让猫娘开口。",
      modeLabel: "已暂停",
    }
  }
  if (!state.connected || !state.in_battle) {
    return {
      kind: "waiting",
      tone: "info",
      title: "等待 War Thunder 战局",
      detail: "数据服务已待命；进入战斗后会自动开始识别。",
      modeLabel: "等待战局",
    }
  }
  if (state.dry_run) {
    return {
      kind: "detect",
      tone: "warning",
      title: "正在检测战局，但战斗播报尚未开启",
      detail: `数据正常 · ${mappedText(state.domain, DOMAIN_LABELS)}中 · 播报未启动${playerName ? " · 昵称已设置" : " · 昵称未设置"}`,
      modeLabel: "播报未启动",
    }
  }
  if (!playerName) {
    return {
      kind: "identity",
      tone: "info",
      title: "战局已连接，建议设置战雷游戏昵称",
      detail: "基础播报可用；无线电互动和身份识别会受到限制。",
      modeLabel: "昵称未设置",
    }
  }
  return {
    kind: "live",
    tone: "success",
    title: "战斗播报已开启",
    detail: `数据正常 · ${mappedText(state.domain, DOMAIN_LABELS)}中 · 猫娘可在需要时回应`,
    modeLabel: "播报中",
  }
}

function eventAllowedForDomain(eventId: string, domain: string | undefined): boolean {
  if (domain === "ground" && AIR_ONLY_EVENTS.has(eventId)) return false
  if ((domain === "air" || domain === "heli") && GROUND_ONLY_EVENTS.has(eventId)) return false
  return true
}

function activityStatus(record: ObserveRecord): { status: string; tone: PanelTone; detail: string; kind: ActivityKind } {
  const stage = String(record.stage || "")
  const outcome = String(record.outcome || "")
  const reason = String(record.reason || "")

  if (stage === "game_context_entered") {
    return { status: "已连接", tone: "success", kind: "recorded", detail: "插件已连接战雷数据，开始等待或识别战局。" }
  }
  if (stage === "game_context_exited") {
    return { status: "已断开", tone: "warning", kind: "suppressed", detail: "战雷数据已离线，插件会等待下次连接。" }
  }
  if (outputWasPushed(record)) {
    return { status: "已交给猫娘", tone: "success", kind: "delivered", detail: "请求已经提交给猫娘，等待宿主继续处理。" }
  }
  if (reason === "heli_vrs_dry_run_only") {
    return { status: "直升机风险仅记录", tone: "info", kind: "suppressed", detail: "涡环风险目前只验证检测与决策，不产生语音播报。" }
  }
  if (reason === "naval_dry_run_only") {
    return { status: "海战态势仅记录", tone: "info", kind: "suppressed", detail: "海战地图图标事件目前仅作 dry-run 观察，真实输出保持关闭。" }
  }
  if (reason === "naval_contact_cleared") {
    return { status: "海战态势记录已失效", tone: "default", kind: "suppressed", detail: "地图接触、来源时效或生命已变化，旧记录已撤销。" }
  }
  if (reason === "heli_vrs_condition_cleared") {
    return { status: "直升机风险记录已失效", tone: "default", kind: "suppressed", detail: "最新数据已不再确认该等级的涡环风险，旧记录已撤销。" }
  }
  if (stage === "dispatcher_dry_run" || record.dry_run === true || outcome === "dry_run") {
    return { status: "仅记录", tone: "info", kind: "recorded", detail: "插件已识别该事件，当前不会提交语音。" }
  }
  if (outputFailed(record)) {
    return { status: "提交失败", tone: "danger", kind: "failed", detail: "本次请求没有成功提交，可以前往诊断页查看。" }
  }
  if (reason.startsWith("broadcast_category_disabled")) {
    return { status: "已按偏好关闭", tone: "default", kind: "suppressed", detail: "你在设置中关闭了这类普通播报；危急安全提醒仍会保留。" }
  }
  if (reason === "user_chat_quiet_window") {
    return { status: "对话保护中", tone: "warning", kind: "suppressed", detail: "你正在和猫娘对话，本次普通战场提醒没有插话。" }
  }
  if (reason === "battle_output_quiet_window" || reason === "output_backpressure") {
    return { status: "等待输出间隔", tone: "warning", kind: "suppressed", detail: "上一条请求仍在处理，本次普通提醒没有继续排队。" }
  }
  if (reason === "repeated_event_collapsed") {
    return { status: "重复提醒已合并", tone: "default", kind: "suppressed", detail: "相同提醒刚刚出现过，本次只保留一条。" }
  }
  if (reason.startsWith("takeoff_")) {
    return { status: "起飞保护中", tone: "info", kind: "suppressed", detail: "刚出生或起飞阶段的临时数据没有触发播报。" }
  }
  if (reason === "replay") {
    return { status: "回放静默", tone: "info", kind: "suppressed", detail: "当前数据来自回放，战斗事件不会提交给猫娘。" }
  }
  if (reason === "free_text_dry_run_only" || reason === "free_text_blocked") {
    return { status: "仅安全观察", tone: "info", kind: "recorded", detail: "检测到自由文本来源，但不会读取或播报原文。" }
  }
  if (reason === "ground_status_output_disabled") {
    return { status: "陆战状态未开启", tone: "info", kind: "suppressed", detail: "乘员减员、待发弹偏少或打空提醒默认只记录，允许陆战状态播报后才会出声。" }
  }
  if (reason === "ground_ammo_condition_cleared") {
    return { status: "弹药状态已变化", tone: "default", kind: "suppressed", detail: "当前待发弹状态已不再符合这条提醒，旧提醒已撤销。" }
  }
  if (reason === "ground_laser_condition_cleared") {
    return { status: "激光告警已失效", tone: "default", kind: "suppressed", detail: "最新数据已不再确认激光告警，旧提醒已撤销。" }
  }
  if (reason === "ground_crew_condition_cleared") {
    return { status: "减员提醒已失效", tone: "default", kind: "suppressed", detail: "当前仪表无法确认这条减员提醒，旧提醒已撤销。" }
  }
  if (reason === "v2_live_evidence_pending") {
    return { status: "等待真机验证", tone: "info", kind: "suppressed", detail: "该提醒仍处于验证阶段，本次只保留安全记录。" }
  }
  if (reason === "deferred_hud_notice") {
    return { status: "暂不播报", tone: "info", kind: "recorded", detail: "该状态目前只记录，不根据未确认字段生成语音。" }
  }
  if (stage.includes("safety") || stage === "test_say_blocked" || reason.includes("paused")) {
    return { status: "已被安全保护阻止", tone: "warning", kind: "suppressed", detail: "事件已记录，但安全保护阻止了本次输出。" }
  }
  if (stage.includes("cooldown") || reason === "cooldown_active") {
    return { status: "冷却中", tone: "warning", kind: "suppressed", detail: "相同提醒刚刚出现过，本次没有重复提交。" }
  }
  if (stage.includes("preempted") || outcome === "preempted") {
    return { status: "被更重要提醒替代", tone: "warning", kind: "suppressed", detail: "更重要的战场事件获得了优先处理。" }
  }
  if (reason.includes("expired") || outcome === "expired") {
    return { status: "已过时", tone: "default", kind: "suppressed", detail: "事件在提交前已经失去时效。" }
  }
  if (stage.includes("scenario_gated") || outcome === "suppressed" || outcome === "dropped") {
    return { status: "当前场景未输出", tone: "default", kind: "suppressed", detail: "事件已识别，但当前战场状态不适合播报。" }
  }
  if (outcome === "allowed" || outcome === "selected") {
    return { status: "已进入输出判断", tone: "info", kind: "recorded", detail: "事件已通过识别，正在等待后续输出判断。" }
  }
  return { status: "已识别", tone: "default", kind: "recorded", detail: "插件已经识别到这项战场活动。" }
}

function activityTitle(record: ObserveRecord): string {
  const eventId = String(record.event_id || "")
  const stage = String(record.stage || "")
  if (eventId) return EVENT_LABELS[eventId] || "战场事件"
  if (stage === "game_context_entered") return "战雷数据已连接"
  if (stage === "game_context_exited") return "战雷数据已断开"
  if (String(record.reason || "") === "replay") return "回放保护"
  if (stage.startsWith("test_say")) return "输出链路测试"
  return "运行状态"
}

function buildActivityItems(state: DashboardState, limit = 5): ActivityItem[] {
  const observe = state.observe || {}
  const records: ObserveRecord[] = []
  const seen = new Set<string>()
  const history = observe.recent_activity?.length ? observe.recent_activity : observe.recent_timeline || []
  const candidates = [
    ...history.slice().reverse(),
  ].filter(Boolean) as ObserveRecord[]

  for (const fallback of [observe.last_output_status, observe.last_decision, observe.last_event]) {
    if (!fallback) continue
    // last_event 只有事件名；已有带结果的历史记录时，不再凭它补一条“已识别”。
    if (!fallback.stage && !fallback.outcome && !fallback.reason
        && candidates.some((record) => record.event_id === fallback.event_id)) continue
    const duplicate = candidates.some((record) =>
      record.event_id === fallback.event_id
      && record.stage === fallback.stage
      && record.outcome === fallback.outcome
      && record.reason === fallback.reason
    )
    if (!duplicate) candidates.push(fallback)
  }

  for (const record of candidates) {
    const eventId = String(record.event_id || "")
    const stage = String(record.stage || "")
    if (!eventId && !stage.startsWith("test_say") && !stage.startsWith("game_context_") && record.reason !== "replay") continue
    if (eventId && !eventAllowedForDomain(eventId, state.domain)) continue
    const key = record.seq !== null && record.seq !== undefined
      ? `seq:${record.seq}`
      : `${eventId}:${stage}:${record.outcome || ""}:${record.reason || ""}`
    if (seen.has(key)) continue
    seen.add(key)
    records.push(record)
    if (records.length >= limit) break
  }

  return records.map((record, index) => {
    const status = activityStatus(record)
    return {
      key: `${record.seq || record.event_id || record.stage || "activity"}-${index}`,
      time: formatTime(record.ts),
      title: activityTitle(record),
      detail: status.detail,
      status: status.status,
      tone: status.tone,
      kind: status.kind,
    }
  })
}

export default function NekoWarthunderPanel(props: PluginSurfaceProps<DashboardState>) {
  const state = props.state || {}
  const identity = state.identity || {}
  const outputPolicy = state.output_policy || {}
  // The host authorizes actions against its entry list. A worker may advertise
  // them before the host has finished registering those entries.
  const registeredEntries = new Set((props.entries || []).map(entry => entry.id))
  const actions = (props.actions || []).filter(action => registeredEntries.has(action.entry_id || action.id))
  const setDryRunAction = actionById(actions, "set_dry_run")
  const setDialogueIntrusionModeAction = actionById(actions, "set_dialogue_intrusion_mode")
  const onDemandAction = actionById(actions, "set_on_demand_explanation")
  const setBroadcastFrequencyAction = actionById(actions, "set_broadcast_frequency")
  const setBroadcastCategoryAction = actionById(actions, "set_broadcast_category")
  const resetBroadcastPreferencesAction = actionById(actions, "reset_broadcast_preferences")
  const setIdentityAction = actionById(actions, "set_identity")
  const setFactionColorsAction = actionById(actions, "set_faction_colors")
  const completeOnboardingAction = actionById(actions, "complete_onboarding")
  const pauseAction = actionById(actions, "pause")
  const resumeAction = actionById(actions, "resume")
  const testSayAction = actionById(actions, "test_say")
  const toast = useToast()
  const onboardingRequired = state.onboarding?.required === true
  const [activeTab, setActiveTab] = useState("overview")
  const ground = state.domain === "ground" ? state.ground_status : null
  const groundAge = VehicleCards.useGroundSampleAge(ground)
  const hasGroundReadings = ground?.status === "ready" || ground?.status === "held"
  const groundStatus = hasGroundReadings
    ? groundAge === null ? "unavailable" : groundAge * 1000 >= GROUND_SAMPLE_MAX_AGE_MS ? "stale" : ground.status
    : ground?.status
  const groundForDisplay = { ...ground, status: groundStatus, sample_age_seconds: groundAge }
  const facts = state.trusted_facts
  const groundFactsUnavailable = facts?.domain === "ground" && hasGroundReadings
    && (groundStatus === "stale" || groundStatus === "unavailable")
  const factsForDisplay = groundFactsUnavailable ? {
    ...facts,
    status: "unavailable",
    sources: facts.sources.map(source => ({ ...source, status: groundStatus === "stale" ? "stale" : "unknown_age",
      age_seconds: groundAge })),
    facts: facts.facts.map(fact => ({ ...fact, status: "unavailable", value: null, total: null })),
  } : facts
  const actionReady = useRef(false)
  actionReady.current = !!testSayAction
  const retryBudget = useRef(3)
  const refreshInterval = useRef(PANEL_REFRESH_INTERVAL_MS)
  refreshInterval.current = state.domain === "ground" && (activeTab === "overview" || activeTab === "diagnostics")
    ? GROUND_PANEL_REFRESH_INTERVAL_MS : PANEL_REFRESH_INTERVAL_MS
  const [activityFilter, setActivityFilter] = useState("all")
  const [onboardingOpen, setOnboardingOpen] = useState(onboardingRequired)
  const [onboardingAutoOpened, setOnboardingAutoOpened] = useState(false)
  const [onboardingStep, setOnboardingStep] = useState(0)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [onDemandOverride, setOnDemandOverride] = useState<OnDemandState | null>(null)
  const [onDemandBusy, setOnDemandBusy] = useState(false)
  const onDemand = onDemandOverride || state.on_demand || {}
  useEffect(() => { setOnDemandOverride(null) }, [state.on_demand])
  const [identityOpen, setIdentityOpen] = useState(false)
  const [identityName, setIdentityName] = useState(currentPlayerName(identity))
  const [identityError, setIdentityError] = useState("")
  const [dryRunError, setDryRunError] = useState("")
  const [dialoguePolicyError, setDialoguePolicyError] = useState("")
  const [broadcastPreferenceError, setBroadcastPreferenceError] = useState("")
  const factionColors = state.faction_colors || {}
  const [allyColor, setAllyColor] = useState(factionColors.ally_color || "#174DFF")
  const [enemyColor, setEnemyColor] = useState(factionColors.enemy_color || "#FA0C00")
  const [factionColorError, setFactionColorError] = useState("")
  const summary = derivePanelSummary(state)
  const playerName = currentPlayerName(identity)
  // limit=5 的结果就是 limit=20 的前缀，算一次即可（该函数没有 memo，每次渲染都会全量跑）。
  const allActivityItems = buildActivityItems(state, 20)
  const activityItems = allActivityItems.slice(0, 5)
  const detectOnly = state.dry_run !== false
  const broadcastPaused = summary.kind === "paused" || summary.kind === "safety"
  const broadcastFrequency = outputPolicy.broadcast_frequency || "standard"
  const broadcastCategories = outputPolicy.broadcast_categories || {}

  useEffect(() => {
    if (!onboardingRequired || onboardingAutoOpened) return
    setOnboardingStep(0)
    setIdentityName(currentPlayerName(identity))
    setOnboardingOpen(true)
    setOnboardingAutoOpened(true)
  }, [onboardingRequired, onboardingAutoOpened])

  // 战局状态是连续变化的，面板承诺"按当前状态实时更新"，因此需要自己拉取：
  // 宿主只在挂载和显式 refresh 时取 context，没有推送。refresh 只读 dashboard
  // context，不触发任何输出，也不影响任何安全门控。
  // 面板不可见时暂停，避免后台标签页空转。
  useEffect(() => {
    let cancelled = false
    let refreshInFlight = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const hidden = () => document.hidden

    const stopTimer = () => {
      if (timer !== undefined) clearTimeout(timer)
      timer = undefined
    }

    const scheduleNext = () => {
      if (!cancelled && !hidden()) {
        const starting = !actionReady.current && retryBudget.current > 0
        if (starting) retryBudget.current -= 1
        if (actionReady.current) retryBudget.current = 3
        timer = setTimeout(() => { void tick() }, starting ? 750 : refreshInterval.current)
      }
    }

    const tick = async () => {
      stopTimer()
      if (cancelled || hidden() || refreshInFlight) return
      refreshInFlight = true
      try {
        await props.api.refresh()
      } catch {
        // A failed refresh leaves the last sample's deadline in effect.
      } finally {
        refreshInFlight = false
        scheduleNext()
      }
    }

    const onVisibilityChange = () => {
      if (hidden()) stopTimer()
      else void tick()
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    scheduleNext()
    return () => {
      cancelled = true
      stopTimer()
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [props.api])

  async function setDryRun(value?: boolean, remember?: boolean) {
    if (!setDryRunAction) {
      setDryRunError("播报模式暂时不可用")
      return
    }
    try {
      setDryRunError("")
      await props.api.call("set_dry_run", value === undefined ? { remember } : { value })
      if (value !== undefined) toast.success(value ? "战斗播报已关闭，继续检测和记录" : "战斗播报已开启")
      await props.api.refresh()
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setDryRunError(message)
      toast.error("播报模式切换失败")
    }
  }

  async function setOnDemand(enabled: boolean) {
    if (!onDemandAction || onDemandBusy) return
    setOnDemandBusy(true)
    try {
      const result = await props.api.call("set_on_demand_explanation", { enabled }) as any
      if (result?.on_demand) setOnDemandOverride(result.on_demand)
      if (result?.ok === true) toast.success(enabled ? "已请求为当前角色启用本次会话的按需解释" : "本次会话的按需解释已关闭")
      else if (result?.reason === "ROLE_UNAVAILABLE") toast.error("无法确认当前角色，按需解释未启用")
      else toast.error("按需解释未就绪，请查看状态或重试清理")
      await props.api.refresh()
    } catch {
      toast.error("按需解释设置失败，继续使用现有面板")
    } finally {
      setOnDemandBusy(false)
    }
  }

  async function setDialogueIntrusionMode(mode: string) {
    if (!setDialogueIntrusionModeAction) {
      setDialoguePolicyError("插话规则设置暂时不可用")
      return
    }
    try {
      setDialoguePolicyError("")
      await props.api.call("set_dialogue_intrusion_mode", { mode })
      toast.success("播报插话规则已更新")
      await props.api.refresh()
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setDialoguePolicyError(message)
      toast.error("插话规则更新失败")
    }
  }

  async function setBroadcastFrequency(frequency: string) {
    if (!setBroadcastFrequencyAction) {
      setBroadcastPreferenceError("播报频率设置暂时不可用")
      return
    }
    try {
      setBroadcastPreferenceError("")
      await props.api.call("set_broadcast_frequency", { frequency })
      toast.success("播报频率已更新")
      await props.api.refresh()
    } catch (error) {
      setBroadcastPreferenceError(error instanceof Error ? error.message : String(error))
      toast.error("播报频率更新失败")
    }
  }

  async function setBroadcastCategory(category: string, enabled: boolean) {
    if (!setBroadcastCategoryAction) {
      setBroadcastPreferenceError("播报类别设置暂时不可用")
      return
    }
    try {
      setBroadcastPreferenceError("")
      await props.api.call("set_broadcast_category", { category, enabled })
      toast.success(enabled ? "该类播报已开启" : "该类播报已关闭")
      await props.api.refresh()
    } catch (error) {
      setBroadcastPreferenceError(error instanceof Error ? error.message : String(error))
      toast.error("播报类别更新失败")
    }
  }

  async function resetBroadcastPreferences() {
    if (!resetBroadcastPreferencesAction) {
      setBroadcastPreferenceError("恢复推荐设置暂时不可用")
      return
    }
    try {
      setBroadcastPreferenceError("")
      await props.api.call("reset_broadcast_preferences", {})
      toast.success("已恢复推荐播报设置")
      await props.api.refresh()
    } catch (error) {
      setBroadcastPreferenceError(error instanceof Error ? error.message : String(error))
      toast.error("恢复推荐设置失败")
    }
  }

  // 打开设置时从后端同步一次；拖动取色器只改本地 state，点保存才提交。
  function openSettings() {
    setAllyColor(factionColors.ally_color || "#174DFF")
    setEnemyColor(factionColors.enemy_color || "#FA0C00")
    setFactionColorError("")
    setSettingsOpen(true)
  }

  async function submitFactionColors(reset = false) {
    if (!setFactionColorsAction) {
      setFactionColorError("敌我颜色设置暂时不可用")
      return
    }
    try {
      setFactionColorError("")
      const envelope = await props.api.call(
        "set_faction_colors",
        reset ? { reset: true } : { ally_color: allyColor, enemy_color: enemyColor },
      )
      const result = unwrapActionResult(envelope)
      const saved = result.faction_colors && typeof result.faction_colors === "object" ? result.faction_colors : {}
      if (saved.ally_color) setAllyColor(String(saved.ally_color))
      if (saved.enemy_color) setEnemyColor(String(saved.enemy_color))
      if (saved.applied === false) {
        toast.warning("颜色已保存，等待数据层连接后生效")
      } else if (saved.conflict) {
        toast.warning("敌我颜色过于接近，将无法区分阵营，接近提醒会暂停")
      } else {
        toast.success(reset ? "已恢复默认敌我颜色" : "敌我颜色已保存")
      }
      await props.api.refresh()
    } catch (error) {
      setFactionColorError(error instanceof Error ? error.message : String(error))
      toast.error("敌我颜色保存失败")
    }
  }

  async function submitIdentity(clear = false) {
    if (!setIdentityAction) {
      setIdentityError("游戏昵称设置暂时不可用")
      return false
    }
    const requestedName = clear ? "" : identityName.trim()
    if (!clear && !requestedName) {
      setIdentityError("请输入战雷游戏昵称")
      return false
    }
    try {
      setIdentityError("")
      const result = unwrapActionResult(await props.api.call("set_identity", { name: requestedName, clear }))
      const identityResult = result.identity && typeof result.identity === "object" ? result.identity : result
      if (identityResult.ok === false) {
        setIdentityError(String(identityResult.error || "游戏昵称保存失败"))
        return false
      }
      if (clear) setIdentityName("")
      setIdentityOpen(false)
      toast.success(clear ? "游戏昵称已清除" : "游戏昵称已保存，等待战局识别")
      await props.api.refresh()
      return true
    } catch (error) {
      setIdentityError(error instanceof Error ? error.message : String(error))
      toast.error("游戏昵称保存失败")
      return false
    }
  }

  function openOnboarding() {
    setOnboardingStep(0)
    setIdentityError("")
    setIdentityName(currentPlayerName(identity))
    setOnboardingOpen(true)
  }

  // 每次打开都重新同步：输入框只在挂载时初始化过一次，昵称可能已被数据层自动识别
  // 或在教程里保存过；identityError 也是持久 state，不清会把上次的失败提示带出来。
  function openIdentityModal() {
    setIdentityName(currentPlayerName(identity))
    setIdentityError("")
    setIdentityOpen(true)
  }

  async function completeOnboarding(skipped = false) {
    if (!completeOnboardingAction) {
      toast.error("教程状态暂时无法保存")
      return false
    }
    try {
      await props.api.call("complete_onboarding", { skipped })
      setOnboardingOpen(false)
      setOnboardingStep(0)
      await props.api.refresh()
      return true
    } catch (error) {
      toast.error("教程状态保存失败")
      return false
    }
  }

  async function saveIdentityAndContinueOnboarding() {
    const currentName = currentPlayerName(identity)
    if (currentName && identityName.trim() === currentName) {
      setOnboardingStep(1)
      return
    }
    if (await submitIdentity(false)) setOnboardingStep(1)
  }

  const bottomBar = (
    <footer className="wt-bottom">
      <div className="wt-bottom-mode">
        <div className="wt-emergency-control" data-state={detectOnly ? "disabled" : broadcastPaused ? "resume" : "stop"}>
          {detectOnly ? (
            <button type="button" className="wt-emergency-stop" title="战斗播报尚未启动" disabled>急停</button>
          ) : broadcastPaused ? (
            <ActionButton action={resumeAction} actionId="resume" tone="success">恢复</ActionButton>
          ) : (
            <ActionButton action={pauseAction} actionId="pause" tone="danger">急停</ActionButton>
          )}
        </div>
        <span className="wt-mode-detail">
          {detectOnly
            ? "战斗播报未启动"
            : broadcastPaused
              ? "新的战斗播报已暂停"
              : "立即暂停新的战斗播报"}
        </span>
      </div>
      <div className="wt-bottom-policy">
        <label className="wt-bottom-label" for="wt-dialogue-policy">播报插话规则</label>
        <select
          id="wt-dialogue-policy"
          className="wt-policy-select"
          value={outputPolicy.dialogue_intrusion_mode || "critical_only"}
          onChange={(event: any) => setDialogueIntrusionMode(event.target.value)}
        >
          {DIALOGUE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
    </footer>
  )

  const onboardingTitles = ["设置昵称", "认识按钮"]
  const onboardingFooter = (
    <ButtonGroup>
      {onboardingStep === 0 ? <Button onClick={() => { void completeOnboarding(true) }}>跳过教程</Button> : null}
      {onboardingStep > 0 ? <Button onClick={() => { setOnboardingStep(onboardingStep - 1) }}>上一步</Button> : null}
      {onboardingStep === 0 ? (
        <>
          <Button onClick={() => { setIdentityError(""); setOnboardingStep(1) }}>暂不设置</Button>
          <Button tone="primary" onClick={() => { void saveIdentityAndContinueOnboarding() }}>
            {playerName && identityName.trim() === playerName ? "下一步" : "保存昵称并继续"}
          </Button>
        </>
      ) : (
        <Button tone="primary" onClick={() => { void completeOnboarding(false) }}>知道了</Button>
      )}
    </ButtonGroup>
  )

  const onboardingContent = (
    <div className="wt-onboarding">
      {onboardingStep === 0 ? (
        <div className="wt-onboarding-copy">
          <h3>先设置你的战雷游戏昵称</h3>
          <p>猫娘用它识别你发送的固定无线电，以及本局击杀、死亡等归属。这个昵称只保存在插件配置中。</p>
          <div className="wt-onboarding-task">
            <div className="wt-onboarding-task-head">
              <div>
                <strong>游戏内显示昵称</strong>
                <p>请填写完整昵称；带有 #数字后缀时也要一起填写。</p>
              </div>
              <StatusBadge tone={playerName ? "success" : "info"} label={playerName ? "已设置" : "待设置"} />
            </div>
            <Field
              label="战雷游戏昵称"
              required
              help="不是邮箱、数字账号 ID、Steam 名称或联队标签。"
              error={identityError}
            >
              <Input
                value={identityName}
                placeholder="例如 Player#123456"
                invalid={!!identityError}
                onChange={setIdentityName}
              />
            </Field>
            <Tip>暂时不确定可以继续教程，之后随时从概览页或设置中补填。</Tip>
          </div>
        </div>
      ) : (
        <div className="wt-onboarding-copy">
          <h3>常用按钮都在固定位置</h3>
          <p>平时只需要认识下面几个按钮，战局和载具会自动识别。</p>
          <div className="wt-control-guide">
            <div className="wt-control-guide-row"><strong>开启 / 停止战斗播报</strong><span>位于概览页顶部。开启后可信事件可以提交给猫娘；停止后仍会检测和记录。</span></div>
            <div className="wt-control-guide-row"><strong>急停 / 恢复</strong><span>位于概览页底部左侧。需要立刻安静时使用，恢复后继续按原规则播报。</span></div>
            <div className="wt-control-guide-row"><strong>测试开口</strong><span>位于诊断页顶部，只检查猫娘接收和声音链路，不需要先进入战局。</span></div>
            <div className="wt-control-guide-row"><strong>刷新状态</strong><span>连接异常或等待战局时会出现在顶部，只重新读取当前状态，不会重启插件。</span></div>
            <div className="wt-control-guide-row"><strong>设置</strong><span>右上角齿轮可修改昵称、插话规则，也能重新打开本教程。</span></div>
          </div>
        </div>
      )}
    </div>
  )

  return (
    <div className="wt-panel">
      <style>{PANEL_STYLES}</style>
      <div className="wt-tabs" aria-label="副驾驶面板">
        <button type="button" aria-pressed={activeTab === "overview"} className={`wt-tab ${activeTab === "overview" ? "is-active" : ""}`} onClick={() => { setActiveTab("overview") }}>概览</button>
        <button type="button" aria-pressed={activeTab === "activity"} className={`wt-tab ${activeTab === "activity" ? "is-active" : ""}`} onClick={() => { setActiveTab("activity") }}>活动</button>
        <button type="button" aria-pressed={activeTab === "diagnostics"} className={`wt-tab ${activeTab === "diagnostics" ? "is-active" : ""}`} onClick={() => { setActiveTab("diagnostics") }}>诊断</button>
        <button type="button" className="wt-settings-trigger" aria-label="设置" title="设置" onClick={openSettings}>⚙︎</button>
      </div>
      <main className="wt-content">
        {activeTab === "overview" ? (
          <OverviewPage.View state={state} summary={summary} groundForDisplay={groundForDisplay}
            playerName={playerName} activityItems={activityItems} dryRunError={dryRunError}
            dialoguePolicyError={dialoguePolicyError} openIdentityModal={openIdentityModal}
            setDryRun={setDryRun} broadcastReady={!!setDryRunAction} />
        ) : activeTab === "activity" ? (
          <ActivityPage.View activityFilter={activityFilter} setActivityFilter={setActivityFilter} items={allActivityItems} />
        ) : (
          <DiagnosticsPage.View state={state} groundForDisplay={groundForDisplay} factsForDisplay={factsForDisplay}
            openActivity={() => setActiveTab("activity")} api={props.api} testSayAction={testSayAction} />
        )}
      </main>
      {activeTab === "overview" ? bottomBar : null}

      <Modal
        open={onboardingOpen}
        title={`新手教程 · ${onboardingTitles[onboardingStep]}`}
        onClose={() => { setOnboardingOpen(false) }}
        footer={onboardingFooter}
      >
        {onboardingContent}
      </Modal>

      <SettingsDialog.View settingsOpen={settingsOpen} setSettingsOpen={setSettingsOpen}
        rememberBroadcastChoice={state.remember_broadcast_choice === true} broadcastReady={!!setDryRunAction}
        setDryRun={setDryRun} t={props.t} dryRunError={dryRunError}
        onDemand={onDemand} onDemandAvailable={!!onDemandAction} onDemandBusy={onDemandBusy} setOnDemand={setOnDemand}
        broadcastFrequency={broadcastFrequency} broadcastCategories={broadcastCategories}
        setBroadcastFrequency={setBroadcastFrequency} setBroadcastCategory={setBroadcastCategory}
        resetBroadcastPreferences={resetBroadcastPreferences} playerName={playerName} openIdentityModal={openIdentityModal}
        allyColor={allyColor} setAllyColor={setAllyColor} enemyColor={enemyColor} setEnemyColor={setEnemyColor}
        submitFactionColors={submitFactionColors} factionColorError={factionColorError}
        openOnboarding={openOnboarding} broadcastPreferenceError={broadcastPreferenceError} />

      <Modal
        open={identityOpen}
        title="设置战雷游戏昵称"
        onClose={() => { setIdentityOpen(false) }}
        footer={(
          <ButtonGroup>
            {playerName ? <Button tone="warning" onClick={async () => { await submitIdentity(true) }}>清除昵称</Button> : null}
            <Button onClick={() => { setIdentityOpen(false) }}>取消</Button>
            <Button tone="primary" onClick={async () => { await submitIdentity(false) }}>保存昵称</Button>
          </ButtonGroup>
        )}
      >
        <Stack>
          <Field
            label="战雷游戏昵称"
            required
            help="不含联队标签，不是邮箱、数字账号 ID 或 Steam 名称；昵称带 #数字时请完整填写。"
            error={identityError}
          >
            <Input
              value={identityName}
              placeholder="例如 Player#123456"
              invalid={!!identityError}
              onChange={setIdentityName}
            />
          </Field>
          <Warning>昵称只用于识别你自己发送的固定无线电消息和本局归属，不会选择其他玩家。</Warning>
        </Stack>
      </Modal>
    </div>
  )
}
