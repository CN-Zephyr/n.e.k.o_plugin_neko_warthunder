/** War Thunder 猫娘副驾驶 Hosted UI。 */

import {
  ActionButton,
  Alert,
  Button,
  ButtonGroup,
  Field,
  Input,
  Modal,
  RefreshButton,
  Stack,
  StatusBadge,
  Tip,
  Warning,
  useEffect,
  useClipboard,
  useState,
  useToast,
} from "@neko/plugin-ui"
import type { HostedAction, PluginSurfaceProps } from "@neko/plugin-ui"

type PanelTone = "primary" | "success" | "warning" | "danger" | "info" | "default"

type SafetyState = {
  status?: string
  manual_paused?: boolean
  auto_paused?: boolean
  failures?: number
}

type IdentityState = {
  player_name?: string | null
  saved_player_name?: string | null
  self?: {
    name?: string | null
    source?: string | null
    confidence?: number | null
  } | null
}

type DataLayerState = {
  mode?: string
  url?: string
  pid?: number | null
  started_by_plugin?: boolean
  health?: boolean
  last_error?: string | null
}

type TelemetryState = {
  age_seconds?: number | null
  ias_kmh?: number | null
  mach?: number | null
  altitude_m?: number | null
  radio_altitude_m?: number | null
  climb_ms?: number | null
  fuel_fraction?: number | null
  flags?: Record<string, boolean>
}

type FlightDiagnosticsState = {
  oil: { status: string; max_c: number | null; observed_channels: number; unavailable_channels: number }
  fuel_estimate: { status: string; burn_kgs: number | null; remaining_sec: number | null;
    age_sec: number | null; max_age_sec: number | null }
}

const FLIGHT_SOURCE_LABELS: Record<string, string> = {
  ready: "可用", partial: "部分通道可用", waiting: "等待有效数据", stale: "已过期，收起估算",
  unavailable: "暂无有效数据", unknown_age: "来源时间未知", invalid_clock: "来源时钟异常",
  offline: "离线", dead: "已阵亡", replay: "回放中",
}

type TrustedFactsState = {
  version: number
  readonly: boolean
  domain: string
  status: string
  sources: { id: string; status: string; age_seconds: number | null; life_binding: string }[]
  facts: { id: string; source: string; status: string; value: number | boolean | null; total?: number | null }[]
  capabilities: string[]
  limits: string[]
  output: { mode: string; ground_status_enabled: boolean; v2_enabled: boolean }
}

type OnDemandState = {
  enabled?: boolean
  status?: string
  role?: string | null
  supported?: boolean
  cleanup_pending?: boolean
}

type GroundStatusState = {
  status?: string
  sample_age_seconds?: number | null
  crew_current?: number | null
  crew_total?: number | null
  ammo_first_stage?: number | null
  gun_stabilizer?: boolean | null
  gear_position?: number | null
  gunner_state?: number | null
  driver_state?: number | null
  laser_warning_state?: number | null
}

type HelicopterStatusState = {
  status?: string
  sample_age_seconds?: number | null
  rotor_rpm?: number | null
  radio_altitude_m?: number | null
  vario_ms?: number | null
}

type NavalStatusState = {
  status?: string
  sample_age_seconds?: number | null
  enemy_count?: number | null
  ally_count?: number | null
  air_contact_count?: number | null
  nearest_type?: string | null
  nearest_distance_m?: number | null
  nearest_bearing_deg?: number | null
}

type NavalDetectionState = {
  source_status?: string
  sample_age_seconds?: number | null
  map_sample_count?: number | null
  detection_enabled?: boolean
  real_output_enabled?: boolean
  detectors?: { event_id: string; status: string; hits: number; required: number; result?: NavalDetectionResult | null }[]
}

type NavalResultRecord = { stage: string; reason: string; ts?: string; map_sample_count?: number }
type NavalDetectionResult = { candidate?: NavalResultRecord | null; decision?: NavalResultRecord | null; output?: NavalResultRecord | null }

type NavalInstrumentFields = {
  source_status?: string
  response_age_seconds?: number | null
  sampling_status?: string
  sample_age_seconds?: number | null
  sample_count?: number | null
  sample_life_bound?: boolean
  fields?: { id: string; status: string }[]
}

type NavalStaticReference = {
  status: string
  source?: { repository: string; ref: string; version: string } | null
  indexed_files: number
  vehicle?: { id: string; blob_sha: string; type_code?: string | null; engine_entry_count?: number | null; propulsion_count?: number | null;
    crew_station_count?: number | null; crew_distribution_total?: number | null;
    configuration?: { status: string; base_status: string; declared_count: number; common_definition_count: number;
      local_override_count: number; template_reference_count: number; explicit_empty_block_count: number;
      missing_common_definition_count: number; missing_dependency_count: number; cycle_node_count: number;
      missing_template_count: number; uninterpreted_effect_value_count: number } } | null
  field_mapping: { id: string; raw_key: string; normalized_key: string; static_paths: string[]; relation: string }[]
}

type TakeoffProtectionState = {
  active?: boolean
  radio_altitude_m?: number | null
  radio_altitude_available?: boolean
  enter_m?: number | null
  exit_m?: number | null
  low_alt_grace_seconds?: number | null
  suppresses?: string[]
}

type ObserveRecord = {
  seq?: number | null
  ts?: number | string | null
  trace_id?: string | null
  event_id?: string | null
  stage?: string | null
  outcome?: string | null
  reason?: string | null
  scenario?: string | null
  safety_status?: string | null
  dry_run?: boolean | null
  pushed?: boolean | null
}

type ObserveState = {
  last_event?: ObserveRecord | null
  last_decision?: ObserveRecord | null
  last_output_status?: ObserveRecord | null
  recent_activity?: ObserveRecord[]
  recent_timeline?: ObserveRecord[]
  observability_enabled?: boolean
}

type AwarenessState = {
  proximity_event_count?: number
  latest_proximity?: {
    kind?: string | null
    target_type?: string | null
    category?: string | null
    is_air?: boolean | null
    distance_m?: number | null
    compass?: string | null
    clock?: number | null
  } | null
  situation?: {
    enemy_count?: number | null
    ally_count?: number | null
    air_threat_count?: number | null
    ground_target_count?: number | null
  }
  nearest_ground_target?: {
    kind?: string | null
    grid?: string | null
    distance_m?: number | null
    bearing_deg?: number | null
    relative_deg?: number | null
  } | null
}

type OutputPolicyState = {
  ground_status_real_output_enabled?: boolean
  dialogue_intrusion_mode?: string | null
  user_chat_quiet_window_seconds?: number | null
  battle_output_quiet_window_seconds?: number | null
  critical_bypass_quiet_window?: boolean | null
  broadcast_frequency?: string | null
  broadcast_categories?: Record<string, boolean>
  critical_safety_always_enabled?: boolean
}

type OnboardingState = {
  completed?: boolean
  required?: boolean
  trigger?: string
}

type FactionColorsState = {
  ally_color?: string
  enemy_color?: string
  default_ally_color?: string
  default_enemy_color?: string
}

type DashboardState = {
  enabled?: boolean
  dry_run?: boolean
  connected?: boolean
  conn_state?: string
  in_battle?: boolean
  game_context_active?: boolean
  dead?: boolean
  domain?: string
  domain_label?: string | null
  domain_source?: string
  vehicle_type?: string | null
  profile_matched?: boolean | null
  profile_source?: string | null
  profile_family?: string | null
  scenario?: string
  level?: string
  onboarding?: OnboardingState
  identity?: IdentityState
  faction_colors?: FactionColorsState
  data_layer?: DataLayerState
  telemetry?: TelemetryState
  flight_diagnostics?: FlightDiagnosticsState | null
  trusted_facts?: TrustedFactsState
  on_demand?: OnDemandState
  ground_status?: GroundStatusState | null
  ground_ammo_explanation?: { status: string } | null
  helicopter_status?: HelicopterStatusState | null
  naval_status?: NavalStatusState | null
  map_status?: NavalStatusState | null
  naval_detection?: NavalDetectionState | null
  naval_instrument_fields?: NavalInstrumentFields | null
  naval_static_reference?: NavalStaticReference | null
  takeoff_protection?: TakeoffProtectionState
  output_policy?: OutputPolicyState
  awareness?: AwarenessState
  safety?: SafetyState
  observe?: ObserveState
}

type PanelSummary = {
  kind: "error" | "safety" | "paused" | "waiting" | "detect" | "identity" | "live"
  tone: PanelTone
  title: string
  detail: string
  modeLabel: string
}

type ActivityItem = {
  key: string
  time: string
  title: string
  detail: string
  status: string
  tone: PanelTone
  kind: ActivityKind
}

type ActivityKind = "delivered" | "recorded" | "suppressed" | "failed"

const DOMAIN_LABELS: Record<string, string> = {
  air: "空战",
  heli: "直升机",
  ground: "陆战",
  naval: "海战",
  menu: "菜单",
  unknown: "未知模式",
}

// 面板自动刷新间隔。取 6s：数据层轮询是 0.4s 级，面板只需跟上"看得出在变"，
// 太密会给宿主 context 通道添无谓压力。
const PANEL_REFRESH_INTERVAL_MS = 6000

const CONN_STATE_LABELS: Record<string, string> = {
  offline: "离线",
  not_in_battle: "已连接·未进战局",
  in_battle: "战局中",
}

const SCENARIO_LABELS: Record<string, string> = {
  OUT_OF_BATTLE: "战斗外",
  SPAWNING: "出生/进场",
  IN_FLIGHT: "战斗中",
  COMBAT_STRESS: "交战中",
  CRITICAL_RISK: "危急状态",
  DEAD: "已阵亡",
  BATTLE_ENDED: "战斗结束",
}

const DATA_LAYER_LABELS: Record<string, string> = {
  managed: "插件托管",
  external: "外部运行",
  starting: "正在启动",
  missing: "未连接",
  failed: "启动失败",
  stopped: "已停止",
  disabled: "未启用",
  unknown: "未知",
}

const RISK_LEVEL_LABELS: Record<string, string> = {
  info: "信息",
  normal: "正常",
  warning: "注意",
  danger: "危险",
  critical: "危急",
}

const SAFETY_STATUS_LABELS: Record<string, string> = {
  running: "正常",
  paused: "已手动暂停",
  tripped: "已自动急停",
  ok: "正常",
}

const DIALOGUE_OPTIONS = [
  { value: "no_interrupt", label: "不打断当前对话" },
  { value: "critical_only", label: "仅危急情况可打断" },
  { value: "allow_interrupt", label: "允许打断当前对话" },
]

const DIALOGUE_LABELS: Record<string, string> = Object.fromEntries(
  DIALOGUE_OPTIONS.map((item) => [item.value, item.label]),
)

const BROADCAST_FREQUENCY_OPTIONS = [
  { value: "quiet", label: "安静" },
  { value: "standard", label: "标准" },
  { value: "active", label: "活跃" },
]

const BROADCAST_CATEGORY_OPTIONS = [
  { value: "safety", label: "一般安全提醒", detail: "过热、低燃油等；危急提醒始终保留" },
  { value: "combat", label: "战果播报", detail: "确认击毁等个人战果" },
  { value: "radio", label: "固定无线电互动", detail: "回应你自己发送的固定无线电消息" },
  { value: "awareness", label: "态势感知", detail: "附近威胁和目标方位" },
  { value: "lifecycle", label: "开场与收尾", detail: "进入战斗和战斗结束" },
]

const EVENT_LABELS: Record<string, string> = {
  ground_crew_loss: "乘员减员",
  ground_ammo_low: "待发弹偏少",
  heli_vrs_risk: "直升机涡环风险",
  naval_map_contact: "海战水面/地面图标出现",
  naval_air_contact: "海战空中图标出现",
  ground_ammo_empty: "待发弹打空",
  spawn: "进入战斗",
  battle_end: "战斗结束",
  you_killed: "确认击毁",
  you_died: "载具损失",
  player_radio_command: "固定无线电消息",
  ground_laser_warning: "激光告警",
  stall_risk: "失速风险",
  high_aoa: "高迎角风险",
  over_g: "过载风险",
  low_alt_danger: "低空风险",
  overspeed: "超速风险",
  overheat: "过热警告",
  low_fuel: "低燃油",
  air_threat_nearby: "附近空中威胁",
  enemy_on_six: "六点钟方向威胁",
  tailing_risk: "持续尾随风险",
  ground_target_nearby: "附近地面目标",
  hud_notice: "战场通知",
  free_text_activity: "战场文字活动",
}

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

const PANEL_STYLES = `
  :root {
    color-scheme: light dark;
    --wt-bg: #ffffff;
    --wt-surface: #ffffff;
    --wt-surface-hover: #f4f8fd;
    --wt-text: #172033;
    --wt-muted: #68758b;
    --wt-muted-soft: #748198;
    --wt-border: #dfe5ee;
    --wt-control-border: #ccd6e4;
    --wt-status-warning-bg: #fff9eb;
    --wt-status-warning-border: #f0a52a;
    --wt-status-info-bg: #f4f9ff;
    --wt-status-info-border: #9ec8f7;
    --wt-status-success-bg: #f4fbf6;
    --wt-status-success-border: #8bcda0;
    --wt-status-danger-bg: #fff6f6;
    --wt-status-danger-border: #ee8c8c;
    --wt-emergency-bg: #fff7f7;
    --wt-emergency-hover: #fdeaea;
    --wt-bottom-bg: rgba(255, 255, 255, 0.98);
    --wt-modal-shadow: 0 18px 44px rgba(23, 32, 51, 0.18);
  }
  body { background: var(--wt-bg); color: var(--wt-text); font-size: 15px; }
  .wt-panel, .wt-panel * { letter-spacing: 0; }
  .wt-panel { display: grid; grid-template-rows: 72px minmax(0, 1fr) auto; width: 100%; height: 100vh; min-height: 0; overflow: hidden; background: var(--wt-bg); color: var(--wt-text); }
  .wt-tabs { display: flex; gap: 52px; height: 72px; padding: 0 32px; border-bottom: 1px solid var(--wt-border); }
  .wt-sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
  .wt-tab { position: relative; min-width: 90px; border: 0; background: transparent; color: var(--wt-text); font: inherit; font-size: 18px; cursor: pointer; }
  .wt-tab.is-active { color: #2589f5; font-weight: 700; }
  .wt-tab.is-active::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: #2589f5; }
  .wt-settings-trigger { display: inline-grid; place-items: center; align-self: center; width: 38px; height: 38px; margin-left: auto; border: 1px solid var(--wt-control-border); border-radius: 6px; padding: 0; background: var(--wt-surface); color: var(--wt-muted); font: inherit; font-size: 22px; line-height: 1; cursor: pointer; }
  .wt-settings-trigger:hover { background: var(--wt-surface-hover); color: var(--wt-text); }
  .wt-content { min-height: 0; overflow-x: hidden; overflow-y: auto; padding: 32px; scrollbar-gutter: stable; }
  /* 基础样式只承载布局；语义配色一律由 data-tone 给出，与本文件其余组件
     (wt-health / wt-activity-row / wt-diagnostics-summary) 保持同一套机制。 */
  .wt-status { display: flex; align-items: center; justify-content: space-between; gap: 28px; min-height: 126px; padding: 26px 28px; border: 1px solid var(--wt-status-warning-border); border-radius: 8px; background: var(--wt-status-warning-bg); }
  .wt-status[data-tone="warning"] { border-color: var(--wt-status-warning-border); background: var(--wt-status-warning-bg); }
  .wt-status[data-tone="info"] { border-color: var(--wt-status-info-border); background: var(--wt-status-info-bg); }
  .wt-status[data-tone="success"] { border-color: var(--wt-status-success-border); background: var(--wt-status-success-bg); }
  .wt-status[data-tone="danger"] { border-color: var(--wt-status-danger-border); background: var(--wt-status-danger-bg); }
  .wt-status-copy { min-width: 0; }
  .wt-status-heading { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 9px; }
  .wt-status-title { margin: 0 0 9px; font-size: 22px; line-height: 1.35; font-weight: 760; }
  .wt-status-heading .wt-status-title { margin: 0; }
  .wt-mode-chip { display: inline-flex; align-items: center; min-height: 28px; border: 1px solid var(--wt-control-border); border-radius: 999px; padding: 3px 10px; background: var(--wt-surface); color: var(--wt-muted); font-size: 13px; font-weight: 700; white-space: nowrap; }
  .wt-mode-chip[data-mode="live"] { border-color: #82bf95; color: #257641; }
  .wt-mode-chip[data-mode="detect"] { border-color: #e5aa43; color: #a66700; }
  .wt-status-detail { margin: 0; color: var(--wt-muted); font-size: 15px; line-height: 1.6; }
  .wt-status-actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; flex: 0 0 auto; }
  .wt-panel .neko-button { min-height: 44px; border-radius: 6px; padding: 9px 18px; background: var(--wt-surface); box-shadow: none; font-size: 15px; }
  .wt-panel .neko-button:hover { transform: none; box-shadow: none; background: var(--wt-surface-hover); }
  .wt-panel .wt-primary-action { min-width: 140px; border-color: #2589f5; background: #2589f5; color: #ffffff; }
  .wt-panel .wt-primary-action:hover { background: #1579e8; }
  .wt-panel .wt-link-action { min-height: auto; padding: 3px 0; border: 0; background: transparent; color: #2589f5; }
  .wt-panel .neko-action-control { display: inline-flex; }
  .wt-panel .neko-action-control .neko-button { width: 100%; }
  .wt-overview-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.08fr); gap: 0; margin-top: 34px; }
  .wt-column { min-width: 0; padding: 0 40px 0 8px; }
  .wt-column + .wt-column { padding: 0 0 0 44px; border-left: 1px solid var(--wt-border); }
  .wt-section-title { margin: 0 0 28px; font-size: 21px; line-height: 1.4; font-weight: 740; }
  .wt-battle-main { padding: 10px 0 28px; border-bottom: 1px solid var(--wt-border); }
  .wt-battle-title { margin: 0; font-size: 19px; font-weight: 720; }
  .wt-battle-meta { margin: 8px 0 0; color: var(--wt-muted-soft); font-size: 15px; line-height: 1.55; }
  .wt-health { display: grid; grid-template-columns: 30px minmax(0, 1fr); gap: 16px; padding: 28px 0; border-bottom: 1px solid var(--wt-border); }
  .wt-health-mark { width: 26px; height: 26px; margin-top: 1px; border: 2px solid #2aa052; border-radius: 50%; }
  .wt-health[data-tone="warning"] .wt-health-mark { border-color: #d98b00; }
  .wt-health[data-tone="danger"] .wt-health-mark { border-color: #d94747; }
  .wt-health-title { margin: 0; font-size: 18px; font-weight: 700; }
  .wt-health-detail { margin: 8px 0 0; color: var(--wt-muted-soft); font-size: 15px; line-height: 1.55; }
  .wt-vehicle-status { margin: 22px 0 0; padding: 18px 20px; border: 1px solid var(--wt-border); border-radius: 8px; background: var(--wt-surface); }
  .wt-naval-results { margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--wt-border); font-weight: 400; }
  .wt-naval-results ol { margin: 8px 0 0; padding: 0; list-style: none; }
  .wt-naval-results li + li { margin-top: 10px; }
  .wt-naval-results strong { display: block; margin-bottom: 4px; font-size: 12px; }
  .wt-vehicle-heading { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
  .wt-vehicle-heading h3 { margin: 0; font-size: 17px; }
  .wt-vehicle-detail, .wt-vehicle-note { color: var(--wt-muted-soft); font-size: 13px; line-height: 1.6; }
  .wt-vehicle-detail { margin: 10px 0 0; }
  .wt-vehicle-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px 16px; margin: 18px 0; }
  .wt-vehicle-stat { min-width: 0; }
  .wt-vehicle-stat dt { margin: 0 0 5px; color: var(--wt-muted-soft); font-size: 13px; }
  .wt-vehicle-stat dd { margin: 0; color: var(--wt-text); font-size: 17px; font-weight: 650; overflow-wrap: anywhere; }
  .wt-vehicle-note { margin: 6px 0 0; }
  .wt-identity { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 28px 0 8px; }
  .wt-identity-name { margin: 0; font-size: 18px; font-weight: 700; }
  .wt-identity-meta { margin: 7px 0 0; color: var(--wt-muted-soft); font-size: 15px; }
  .wt-activity-head { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 16px; }
  .wt-panel .neko-badge { border-radius: 999px; background: var(--wt-surface); box-shadow: none; }
  .wt-panel .neko-badge::before { display: none; }
  .wt-activity-list { display: grid; }
  .wt-activity-row { position: relative; display: grid; grid-template-columns: 64px 22px minmax(0, 1fr) auto; gap: 14px; align-items: center; min-height: 94px; }
  .wt-activity-row::before { content: ""; position: absolute; left: 87px; top: 0; bottom: 0; width: 1px; background: var(--wt-border); }
  .wt-activity-time { color: var(--wt-muted-soft); font-size: 15px; font-variant-numeric: tabular-nums; }
  .wt-activity-mark { position: relative; z-index: 1; width: 16px; height: 16px; border: 3px solid var(--wt-bg); border-radius: 50%; background: #2589f5; box-shadow: 0 0 0 1px var(--wt-control-border); }
  .wt-activity-row[data-tone="warning"] .wt-activity-mark { background: #e69a13; }
  .wt-activity-row[data-tone="danger"] .wt-activity-mark { background: #e05252; }
  .wt-activity-row[data-tone="success"] .wt-activity-mark { background: #2aa052; }
  .wt-activity-title { margin: 0; font-size: 18px; font-weight: 700; }
  .wt-activity-detail { margin: 6px 0 0; color: var(--wt-muted-soft); font-size: 15px; line-height: 1.45; }
  .wt-empty { padding: 32px 0; color: var(--wt-muted-soft); text-align: center; }
  .wt-activity-page { display: grid; gap: 24px; }
  .wt-activity-page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }
  .wt-activity-page-head h2 { margin: 0 0 6px; font-size: 21px; }
  .wt-activity-page-head p { margin: 0; color: var(--wt-muted-soft); font-size: 14px; line-height: 1.5; }
  .wt-activity-filter { display: inline-flex; flex-wrap: wrap; gap: 4px; padding: 3px; border: 1px solid var(--wt-control-border); border-radius: 7px; background: var(--wt-surface); }
  .wt-activity-filter-button { min-height: 34px; border: 0; border-radius: 5px; padding: 6px 13px; background: transparent; color: var(--wt-muted); font: inherit; font-size: 13px; cursor: pointer; }
  .wt-activity-filter-button:hover { background: var(--wt-surface-hover); color: var(--wt-text); }
  .wt-activity-filter-button.is-active { background: #2589f5; color: #ffffff; font-weight: 700; }
  .wt-activity-page-note { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 12px 0; border-block: 1px solid var(--wt-border); color: var(--wt-muted-soft); font-size: 13px; }
  .wt-activity-page-list { max-width: 1120px; }
  .wt-bottom { z-index: 20; display: grid; grid-template-columns: minmax(440px, 1.25fr) minmax(320px, 1fr); gap: 28px; align-items: center; min-height: 76px; padding: 12px 32px; border-top: 1px solid var(--wt-border); background: var(--wt-bottom-bg); }
  .wt-bottom-mode { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .wt-emergency-control { display: inline-flex; flex: 0 0 auto; }
  .wt-emergency-stop, .wt-emergency-control .neko-button { min-width: 76px; min-height: 34px; border-radius: 6px; padding: 5px 14px; font-size: 14px; font-weight: 750; }
  .wt-emergency-stop { border: 1px solid #e05252; background: var(--wt-emergency-bg); color: #d74a4a; font-family: inherit; cursor: pointer; }
  .wt-emergency-stop:hover:not(:disabled) { background: var(--wt-emergency-hover); }
  .wt-emergency-stop:disabled { border-color: var(--wt-control-border); background: var(--wt-surface); color: var(--wt-muted-soft); cursor: not-allowed; opacity: 0.62; }
  .wt-emergency-control[data-state="stop"] .neko-button { border-color: #e05252; background: var(--wt-emergency-bg); color: #d74a4a; }
  .wt-emergency-control[data-state="stop"] .neko-button:hover { background: var(--wt-emergency-hover); }
  .wt-emergency-control[data-state="resume"] .neko-button { border-color: #66ad7a; background: var(--wt-status-success-bg); color: #278044; }
  .wt-mode-detail { min-width: 0; color: var(--wt-muted-soft); font-size: 13px; line-height: 1.4; }
  .wt-bottom-policy { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 16px; align-items: center; }
  .wt-bottom-label { font-weight: 700; white-space: nowrap; }
  .wt-policy-select { width: 100%; min-height: 44px; border: 1px solid var(--wt-control-border); border-radius: 6px; padding: 8px 12px; background: var(--wt-surface); color: var(--wt-text); font: inherit; }
  .wt-diagnostics { display: grid; gap: 24px; }
  .wt-diagnostics-summary { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 24px; align-items: center; padding: 20px 22px; border: 1px solid var(--wt-status-info-border); border-radius: 8px; background: var(--wt-status-info-bg); }
  .wt-diagnostics-summary[data-tone="success"] { border-color: var(--wt-status-success-border); background: var(--wt-status-success-bg); }
  .wt-diagnostics-summary[data-tone="warning"] { border-color: var(--wt-status-warning-border); background: var(--wt-status-warning-bg); }
  .wt-diagnostics-summary[data-tone="danger"] { border-color: var(--wt-status-danger-border); background: var(--wt-status-danger-bg); }
  .wt-diagnostics-summary h2 { margin: 0 0 7px; font-size: 19px; }
  .wt-diagnostics-summary p { margin: 0; color: var(--wt-muted); font-size: 14px; line-height: 1.55; }
  .wt-diagnostics-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
  .wt-diagnostics-section-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
  .wt-diagnostics-section-head h2 { margin: 0 0 5px; font-size: 18px; }
  .wt-diagnostics-section-head p { margin: 0; color: var(--wt-muted-soft); font-size: 14px; }
  .wt-diagnostic-checks { border-top: 1px solid var(--wt-border); }
  .wt-diagnostic-check { border-bottom: 1px solid var(--wt-border); }
  .wt-diagnostic-check > summary { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto auto; gap: 14px; align-items: center; min-height: 72px; padding: 10px 4px; list-style: none; cursor: pointer; }
  .wt-diagnostic-check > summary::-webkit-details-marker { display: none; }
  .wt-diagnostic-index { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: var(--wt-status-info-bg); color: #2589f5; font-size: 13px; font-weight: 700; }
  .wt-diagnostic-check[data-tone="success"] .wt-diagnostic-index { background: var(--wt-status-success-bg); color: #278044; }
  .wt-diagnostic-check[data-tone="warning"] .wt-diagnostic-index { background: var(--wt-status-warning-bg); color: #a66700; }
  .wt-diagnostic-check[data-tone="danger"] .wt-diagnostic-index { background: var(--wt-status-danger-bg); color: #d94747; }
  .wt-diagnostic-copy { min-width: 0; }
  .wt-diagnostic-copy h3 { margin: 0 0 4px; font-size: 16px; }
  .wt-diagnostic-copy p { margin: 0; color: var(--wt-muted-soft); font-size: 14px; line-height: 1.45; }
  .wt-diagnostic-more { color: #2589f5; font-size: 13px; white-space: nowrap; }
  .wt-diagnostic-check[open] .wt-diagnostic-more { color: var(--wt-muted-soft); }
  .wt-diagnostic-help { margin: 0 0 14px 52px; padding: 12px 14px; border-left: 3px solid var(--wt-control-border); background: var(--wt-surface); color: var(--wt-muted); font-size: 14px; line-height: 1.55; }
  .wt-diagnostic-help strong { color: var(--wt-text); }
  .wt-advanced-details { border-top: 1px solid var(--wt-border); }
  .wt-advanced-details > summary { display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 62px; cursor: pointer; }
  .wt-advanced-details > summary strong { font-size: 16px; }
  .wt-advanced-details > summary span { color: var(--wt-muted-soft); font-size: 13px; }
  .wt-advanced-content { display: grid; gap: 16px; max-width: 1120px; margin: 0 auto; padding: 8px 0 12px; }
  .wt-advanced-intro { margin: 0; padding: 12px 14px; border-left: 3px solid var(--wt-status-info-border); background: var(--wt-status-info-bg); color: var(--wt-muted); font-size: 13px; line-height: 1.55; }
  .wt-advanced-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
  .wt-advanced-group { min-width: 0; border: 1px solid var(--wt-border); border-radius: 8px; padding: 16px 18px 10px; background: var(--wt-surface); }
  .wt-advanced-group-head { padding-bottom: 13px; border-bottom: 1px solid var(--wt-border); }
  .wt-advanced-group-head h3 { margin: 0; font-size: 15px; line-height: 1.4; }
  .wt-advanced-group-head p { margin: 4px 0 0; color: var(--wt-muted-soft); font-size: 12px; line-height: 1.45; }
  .wt-advanced-list { margin: 0; }
  .wt-advanced-field { display: grid; grid-template-columns: minmax(96px, 0.9fr) minmax(0, 1.1fr); gap: 14px; align-items: start; padding: 9px 0; border-top: 1px solid var(--wt-border); }
  .wt-advanced-field:first-child { border-top: 0; }
  .wt-advanced-field dt { color: var(--wt-muted-soft); font-size: 13px; line-height: 1.45; }
  .wt-advanced-field dd { min-width: 0; margin: 0; color: var(--wt-text); font-size: 13px; font-weight: 650; line-height: 1.45; text-align: right; overflow-wrap: anywhere; }
  .wt-advanced-field[data-empty="true"] dd { color: var(--wt-muted-soft); font-weight: 500; }
  .wt-panel .neko-card { border-radius: 8px; background: var(--wt-surface); box-shadow: none; backdrop-filter: none; }
  .wt-panel .neko-heading { font-size: 16px; }
  .wt-panel .neko-text { font-size: 14px; }
  .wt-panel .neko-modal { border-radius: 8px; box-shadow: var(--wt-modal-shadow); }
  .wt-panel .neko-input, .wt-panel .neko-select { border-radius: 6px; }
  .wt-settings { display: grid; }
  .wt-settings-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(180px, auto); gap: 24px; align-items: center; padding: 18px 0; border-top: 1px solid var(--wt-border); }
  .wt-settings-row:first-child { padding-top: 0; border-top: 0; }
  .wt-settings-row:last-child { padding-bottom: 0; }
  .wt-settings-copy h3 { margin: 0 0 6px; font-size: 16px; }
  .wt-settings-copy p { margin: 0; color: var(--wt-muted-soft); font-size: 14px; line-height: 1.5; }
  .wt-settings-control { display: flex; justify-content: flex-end; }
  .wt-settings-control.is-wide { width: min(100%, 430px); }
  .wt-color-row { display: flex; gap: 16px; }
  .wt-color-row input[type="color"] { width: 72px; height: 36px; padding: 2px; cursor: pointer; }
  .wt-frequency-control { display: grid; grid-template-columns: repeat(3, minmax(72px, 1fr)); width: 100%; }
  .wt-category-list { display: grid; width: 100%; border-top: 1px solid var(--wt-border); }
  .wt-category-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 18px; align-items: center; min-height: 58px; border-bottom: 1px solid var(--wt-border); }
  .wt-category-row strong { display: block; margin-bottom: 3px; font-size: 14px; }
  .wt-category-row span { color: var(--wt-muted-soft); font-size: 13px; line-height: 1.4; }
  .wt-toggle-button { min-width: 70px; }
  .wt-onboarding { display: grid; gap: 22px; }
  .wt-onboarding-copy h3 { margin: 0 0 10px; font-size: 20px; line-height: 1.4; }
  .wt-onboarding-copy > p { margin: 0; color: var(--wt-muted); font-size: 15px; line-height: 1.65; }
  .wt-onboarding-task { display: grid; gap: 16px; margin-top: 22px; padding: 18px; border: 1px solid var(--wt-control-border); border-radius: 6px; background: var(--wt-surface); }
  .wt-onboarding-task-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
  .wt-onboarding-task-head strong { display: block; margin-bottom: 5px; font-size: 16px; }
  .wt-onboarding-task-head p { margin: 0; color: var(--wt-muted-soft); font-size: 14px; line-height: 1.55; }
  .wt-control-guide { display: grid; margin-top: 22px; border-top: 1px solid var(--wt-border); }
  .wt-control-guide-row { display: grid; grid-template-columns: minmax(150px, 190px) minmax(0, 1fr); gap: 20px; padding: 15px 0; border-bottom: 1px solid var(--wt-border); }
  .wt-control-guide-row strong { font-size: 15px; }
  .wt-control-guide-row span { color: var(--wt-muted-soft); font-size: 14px; line-height: 1.55; }
  @media (prefers-color-scheme: dark) {
    :root {
      --wt-bg: #16181d;
      --wt-surface: #22252b;
      --wt-surface-hover: #2a2e35;
      --wt-text: #f1f3f6;
      --wt-muted: #b3bac7;
      --wt-muted-soft: #9da6b5;
      --wt-border: #3a3f48;
      --wt-control-border: #4a515d;
      --wt-status-warning-bg: #2a2418;
      --wt-status-warning-border: #9b6c20;
      --wt-status-info-bg: #182534;
      --wt-status-info-border: #37658f;
      --wt-status-success-bg: #19271e;
      --wt-status-success-border: #3f7950;
      --wt-status-danger-bg: #2d1d20;
      --wt-status-danger-border: #8b484f;
      --wt-emergency-bg: #2d1d20;
      --wt-emergency-hover: #3a2327;
      --wt-bottom-bg: rgba(22, 24, 29, 0.98);
      --wt-modal-shadow: 0 20px 48px rgba(0, 0, 0, 0.42);
    }
  }
  @media (max-height: 620px) and (min-width: 761px) {
    .wt-panel { grid-template-rows: 58px minmax(0, 1fr) auto; }
    .wt-tabs { height: 58px; }
    .wt-content { padding: 22px 28px; }
    .wt-status { min-height: 104px; padding: 18px 24px; }
    .wt-overview-grid { margin-top: 26px; }
    .wt-activity-row { min-height: 80px; }
    .wt-bottom { min-height: 64px; padding: 9px 28px; }
  }
  @media (max-width: 760px) {
    .wt-panel { grid-template-rows: 54px minmax(0, 1fr) auto; }
    .wt-tabs { height: 54px; padding: 0 18px; gap: 26px; }
    .wt-tab { min-width: 64px; }
    .wt-settings-trigger { width: 36px; height: 36px; font-size: 20px; }
    .wt-content { padding: 20px 18px 24px; }
    .wt-status { align-items: flex-start; flex-direction: column; padding: 18px; }
    .wt-status-actions { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
    .wt-overview-grid { grid-template-columns: 1fr; }
    .wt-column { padding: 0; }
    .wt-column + .wt-column { margin-top: 28px; padding: 28px 0 0; border-top: 1px solid var(--wt-border); border-left: 0; }
    .wt-activity-row { grid-template-columns: 50px 18px minmax(0, 1fr); }
    .wt-activity-row::before { left: 67px; }
    .wt-activity-row .neko-badge { grid-column: 3; margin-bottom: 8px; }
    .wt-activity-page-head { align-items: flex-start; flex-direction: column; gap: 14px; }
    .wt-activity-page-note { align-items: flex-start; flex-direction: column; gap: 4px; }
    .wt-bottom { grid-template-columns: 1fr; gap: 8px; padding: 10px 18px; }
    .wt-bottom-mode { align-items: flex-start; flex-wrap: wrap; }
    .wt-mode-detail { flex-basis: 100%; }
    .wt-bottom-policy { grid-template-columns: 1fr; gap: 5px; }
    .wt-diagnostics-summary { grid-template-columns: 1fr; gap: 14px; }
    .wt-diagnostics-actions { justify-content: flex-start; }
    .wt-diagnostics-section-head { align-items: flex-start; flex-direction: column; gap: 6px; }
    .wt-diagnostic-check > summary { grid-template-columns: 30px minmax(0, 1fr) auto; gap: 10px; }
    .wt-diagnostic-check > summary .neko-badge { grid-column: 2; justify-self: start; }
    .wt-diagnostic-more { grid-column: 3; grid-row: 1 / span 2; }
    .wt-diagnostic-help { margin-left: 40px; }
    .wt-advanced-details > summary { align-items: flex-start; flex-direction: column; justify-content: center; gap: 3px; }
    .wt-advanced-grid { grid-template-columns: 1fr; }
    .wt-advanced-group { padding-inline: 14px; }
    .wt-settings-row { grid-template-columns: 1fr; gap: 10px; }
    .wt-settings-control { justify-content: flex-start; }
    .wt-settings-control.is-wide { width: 100%; }
    .wt-onboarding-task-head { display: grid; }
    .wt-control-guide-row { grid-template-columns: 1fr; gap: 6px; }
  }
  @media (max-width: 360px) {
    .wt-tabs { padding-inline: 10px; gap: 10px; }
    .wt-tab { min-width: 52px; font-size: 16px; }
    .wt-settings-trigger { width: 34px; height: 34px; }
  }
`

function actionById(actions: HostedAction[], id: string): HostedAction | undefined {
  return actions.find((action) => action.id === id || action.entry_id === id)
}

function text(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-"
  if (typeof value === "boolean") return value ? "是" : "否"
  return String(value)
}

function numberText(value: unknown, unit = "", digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  return `${value.toFixed(digits)}${unit}`
}

function percentText(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  return `${Math.round(value * 100)}%`
}

function flagsText(flags: Record<string, boolean> | undefined): string {
  if (!flags) return "-"
  const active = Object.keys(flags).filter((key) => flags[key])
  return active.length ? active.join(", ") : "无"
}

function listText(values: string[] | undefined): string {
  return values && values.length ? values.join(", ") : "无"
}

function mappedText(value: unknown, labels: Record<string, string> = {}): string {
  const raw = text(value)
  return labels[raw] || raw
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

function formatTime(value: ObserveRecord["ts"]): string {
  if (value === null || value === undefined || value === "") return "最近"
  const date = new Date(typeof value === "number" && value < 1_000_000_000_000 ? value * 1000 : value)
  if (Number.isNaN(date.getTime())) return "最近"
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

function currentPlayerName(identity: IdentityState): string {
  return String(identity.player_name || identity.saved_player_name || identity.self?.name || "").trim()
}

function safetyIsTripped(state: DashboardState): boolean {
  return state.safety?.status === "tripped" || state.safety?.auto_paused === true
}

function safetyIsPaused(state: DashboardState): boolean {
  return state.safety?.status === "paused" || state.safety?.manual_paused === true
}

function outputWasPushed(record: ObserveRecord | null | undefined): boolean {
  return record?.stage === "dispatcher_pushed"
    || record?.stage === "test_say_pushed"
    || record?.pushed === true
    || record?.outcome === "pushed"
}

function outputFailed(record: ObserveRecord | null | undefined): boolean {
  return record?.stage?.includes("failed") === true || record?.outcome === "failed"
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

function battleStatus(state: DashboardState): { title: string; detail: string; tone: PanelTone } {
  if (state.dead) return { title: "本次载具已损失", detail: "等待重生后会自动重新识别载具与战局。", tone: "warning" }
  if (state.level === "critical" || state.level === "danger") {
    return { title: "检测到需要立即关注的战场状态", detail: "具体事件会出现在最近活动中。", tone: "danger" }
  }
  if (state.level === "warning") {
    return { title: "检测到需要关注的战场状态", detail: "系统会根据播报模式决定是否提交提醒。", tone: "warning" }
  }
  return { title: "当前状态正常，没有需要提醒的风险", detail: "系统正在检测战局，只在可信事件出现时记录或提醒。", tone: "success" }
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

function groundStationText(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) return "暂无数据"
  const labels: Record<number, string> = { 0: "正常", 1: "岗位空缺", 2: "正在补位" }
  return labels[value] || `待确认（${value}）`
}

function TrustedFactsCard(props: { facts: TrustedFactsState; openActivity: () => void }) {
  const summary = props.facts
  const statuses: Record<string, string> = {
    ready: "事实已读取", partial: "部分事实可用", unavailable: "等待可信数据", offline: "连接已断开",
    waiting: "等待进场", dead: "已阵亡，收起旧事实", replay: "回放期间不展示事实",
    stale: "来源已过期", no_player: "缺少自身位置", unknown_age: "采样时间未知", invalid_clock: "采样时间异常",
  }
  const capabilities: Record<string, string> = {
    flight_safety: "飞行安全提醒", owned_combat: "我方战果反馈", air_awareness: "有限空中态势",
    ground_status: "乘员与待发弹状态", laser_warning: "激光告警观察", heli_instruments: "直升机仪表",
    vrs_dry_run: "VRS 仅检测记录", map_observation: "地图可见图标观察", naval_dry_run: "海战图标仅检测记录",
    static_reference: "舰艇静态资料参考", generic_map: "通用地图观察",
  }
  const limits: Record<string, string> = {
    agl_not_msl: "离地高度与海拔分开显示。", v2_gated: "后方、尾随和任务点提醒沿用 V2 输出开关。",
    ready_rack_only: "一级待发弹不代表全车余弹。", roles_readonly: "岗位状态只读，尚无岗位播报。",
    laser_not_missile: "激光告警不等于已确认导弹来袭。", vrs_no_speech: "VRS 只记录，不真实播报。",
    no_rotor_alarm: "旋翼转速不生成告警。", map_icons_only: "地图只反映可见图标，不确认敌舰、空袭或锁定。",
    naval_values_hidden: "舰艇仪表语义未验证，暂不显示读数。", static_not_effective: "静态声明不代表当前安装或生效参数。",
    domain_unconfirmed: "载具域未确认，不借用其他域的仪表。",
  }
  const labels: Record<string, string> = {
    ias_kmh: "指示空速", mach: "马赫数", radio_altitude_m: "离地高度（AGL）", altitude_m: "海拔高度（MSL）",
    fuel_fraction: "燃油余量", crew_current: "乘员", ammo_first_stage: "一级待发弹", laser_warning_state: "激光告警器",
    gun_stabilizer: "火炮稳定器", gear_position: "档位", rotor_rpm: "旋翼转速", vario_ms: "升降速度",
    enemy_count: "敌方可见图标", ally_count: "友方可见图标", air_contact_count: "敌方空中图标",
    nearest_distance_m: "最近敌方图标平面距离", nearest_bearing_deg: "图标绝对方位",
  }
  const valueText = (fact: TrustedFactsState["facts"][number]) => {
    if (fact.status !== "available") return fact.status === "unknown" ? "未知" : "暂不可用"
    if (fact.id === "gun_stabilizer" && typeof fact.value === "boolean") return fact.value ? "开启" : "关闭"
    if (typeof fact.value !== "number" || !Number.isFinite(fact.value)) return "未知"
    if (fact.id === "crew_current") return typeof fact.total === "number" ? `${fact.value} / ${fact.total} 人` : "未知"
    if (fact.id === "laser_warning_state") return groundLaserText(fact.value)
    if (fact.id === "gear_position") return fact.value === 0 ? "空挡" : `${fact.value > 0 ? "前进" : "倒车"} ${Math.abs(fact.value)} 挡`
    if (fact.id === "fuel_fraction") return `${(fact.value * 100).toFixed(1)}%`
    const units: Record<string, string> = { ias_kmh: " km/h", radio_altitude_m: " m", altitude_m: " m",
      ammo_first_stage: " 发", rotor_rpm: " rpm", vario_ms: " m/s", nearest_distance_m: " m", nearest_bearing_deg: "°" }
    return numberText(fact.value, units[fact.id] || "", fact.id.endsWith("count") || fact.id === "ammo_first_stage" ? 0 : 1)
  }
  const modes: Record<string, string> = { disabled: "检测已停用", paused: "战斗播报已暂停", dry_run: "战斗播报仅记录",
    existing_policy: "战斗播报仍受现有仲裁、偏好与开关约束" }
  return (
    <section className="wt-vehicle-status" role="region" aria-label="可信事实摘要" data-trusted-domain={summary.domain} data-trusted-status={summary.status}>
      <div className="wt-vehicle-heading">
        <h3>可信事实摘要 · {mappedText(summary.domain, DOMAIN_LABELS)}</h3>
        <StatusBadge tone={summary.status === "ready" ? "success" : "info"} label={statuses[summary.status] || "等待可信数据"} />
      </div>
      <p className="wt-vehicle-detail">可帮助：{summary.capabilities.map(code => capabilities[code]).filter(Boolean).join("、") || "等待确认载具域"}。以下仅为只读事实，不代表提醒已触发。</p>
      {summary.sources.map(source => (
        <p className="wt-vehicle-note" key={source.id} data-trusted-source={source.status}>
          来源：{source.id === "map" ? "地图采样" : "载具采样"} · {statuses[source.status] || "等待数据"}
          {typeof source.age_seconds === "number" && Number.isFinite(source.age_seconds) ? ` · ${source.age_seconds.toFixed(1)} 秒前` : " · 时间未知"}
          {source.life_binding === "sample" ? " · 已核对当前出场" : " · 独立出场归属未确认"}
        </p>
      ))}
      <dl className="wt-vehicle-grid">
        {summary.facts.filter(fact => labels[fact.id]).map(fact => (
          <div key={fact.id} className="wt-vehicle-stat" data-trusted-fact={fact.id} data-trusted-fact-status={fact.status}>
            <dt>{labels[fact.id]}</dt><dd>{valueText(fact)}</dd>
          </div>
        ))}
      </dl>
      <p className="wt-vehicle-note">{summary.limits.map(code => limits[code]).filter(Boolean).join(" ")}</p>
      <p className="wt-vehicle-note">本摘要不发声。{modes[summary.output.mode] || "输出策略未知"}。
        {summary.domain === "ground" ? `乘员/弹药真实输出开关：${summary.output.ground_status_enabled ? "开启" : "关闭"}；激光沿用原策略。` : ""}
        {summary.domain === "air" ? `受限 V2 真实输出开关：${summary.output.v2_enabled ? "开启" : "关闭"}。` : ""}
      </p>
      <Button className="wt-link-action" onClick={props.openActivity}>查看活动与未播原因</Button>
    </section>
  )
}

function groundLaserText(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isInteger(value)) return "暂无数据"
  const labels: Record<number, string> = { [-1]: "无设备", 0: "待机", 1: "正在告警", 2: "设备损坏" }
  return labels[value] || `待确认（${value}）`
}

function GroundStatusCard(props: {
  ground: GroundStatusState; dryRun: boolean; realOutput: boolean; explanation?: { status: string } | null
}) {
  const ground = props.ground
  const states: Record<string, { label: string; detail: string; tone: PanelTone }> = {
    ready: { label: "已读取", detail: "显示最近一次采样的载具状态。", tone: "success" },
    waiting: { label: "等待进场", detail: "进入陆战后显示当前载具状态。", tone: "info" },
    unavailable: { label: "等待数据", detail: "暂未取得有效载具数据，未知值不会当作零。", tone: "info" },
    stale: { label: "数据过期", detail: "等待新的载具采样，暂不显示旧车状态。", tone: "warning" },
    offline: { label: "已断开", detail: "数据连接已断开，等待恢复。", tone: "warning" },
    dead: { label: "已阵亡", detail: "阵亡期间收起旧车状态，重生后重新读取。", tone: "info" },
    replay: { label: "回放已暂停", detail: "回放期间不显示可能失真的载具状态。", tone: "info" },
  }
  const summary = states[ground.status || "unavailable"] || states.unavailable
  const ready = ground.status === "ready"
  const crew = ready && Number.isInteger(ground.crew_current) && Number.isInteger(ground.crew_total)
    && typeof ground.crew_current === "number" && typeof ground.crew_total === "number"
    && ground.crew_total > 0 && ground.crew_current >= 0 && ground.crew_current <= ground.crew_total
    ? `${ground.crew_current} / ${ground.crew_total} 人` : "暂无数据"
  const ammo = ready && typeof ground.ammo_first_stage === "number" && Number.isInteger(ground.ammo_first_stage)
    && ground.ammo_first_stage >= 0
    ? `${ground.ammo_first_stage} 发` : "暂无数据"
  const gear = ready && typeof ground.gear_position === "number" && Number.isInteger(ground.gear_position)
    ? ground.gear_position > 0 ? `前进 ${ground.gear_position} 挡`
      : ground.gear_position < 0 ? `倒车 ${Math.abs(ground.gear_position)} 挡` : "空挡"
    : "暂无数据"
  const stabilizer = ready && typeof ground.gun_stabilizer === "boolean"
    ? ground.gun_stabilizer ? "开启" : "关闭" : "暂无数据"
  const explanations: Record<string, string> = {
    source_unavailable: "当前来源不可用于解释，等待新数据。",
    count_unknown: "当前一级待发弹数量未知，不能当作零发。",
    conflicting: "当前数量或标记无法一致解释，暂不作判断。",
    zero_unconfirmed: "当前读数为 0，未取得一致的耗尽标记；不能据此判定全车无弹。",
    empty_flagged: "当前读数为 0，数据层给出待发弹耗尽标记；不代表全车无弹或已经播报。",
    low_flagged: "当前读到待发弹，数据层给出偏少标记；不能据此推算满弹容量或剩余开火次数。",
    observed_count: "当前已读到待发弹，未取得一致的偏少或耗尽标记；不代表弹量充足或已补满。",
  }
  const explanationCode = ready && Object.prototype.hasOwnProperty.call(explanations, props.explanation?.status || "")
    ? props.explanation!.status : "source_unavailable"
  const rows = [
    { key: "crew", label: "乘员", value: crew },
    { key: "ammo", label: "一级待发弹", value: ammo },
    { key: "stabilizer", label: "火炮稳定器", value: stabilizer },
    { key: "gear", label: "档位", value: gear },
    { key: "gunner", label: "炮手岗位", value: ready ? groundStationText(ground.gunner_state) : "暂无数据" },
    { key: "driver", label: "驾驶员岗位", value: ready ? groundStationText(ground.driver_state) : "暂无数据" },
    { key: "laser", label: "激光告警器", value: ready ? groundLaserText(ground.laser_warning_state) : "暂无数据" },
  ]
  return (
    <section className="wt-vehicle-status" role="region" aria-label="陆战状态">
      <div className="wt-vehicle-heading">
        <h3>陆战状态</h3>
        <StatusBadge tone={summary.tone} label={summary.label} />
      </div>
      <p className="wt-vehicle-detail">{summary.detail}</p>
      <p className="wt-vehicle-note">
        {typeof ground.sample_age_seconds === "number" && Number.isFinite(ground.sample_age_seconds) && ground.sample_age_seconds >= 0
          ? `最近载具采样：${ground.sample_age_seconds.toFixed(1)} 秒前` : "载具采样时间未知"}
      </p>
      <dl className="wt-vehicle-grid">
        {rows.map((row) => <div key={row.key} className="wt-vehicle-stat"><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
      </dl>
      <p className="wt-vehicle-note">一级待发弹不代表全车弹药；未知岗位状态保留编号。</p>
      <p className="wt-vehicle-note" data-ammo-explanation={explanationCode}>
        待发弹说明：{explanations[explanationCode]} 检测候选与输出结果请在活动页对照。
      </p>
      {ready && ground.laser_warning_state === 1 && (
        <p className="wt-vehicle-note" role="status">最近采样检测到激光告警，注意观察并寻找掩体；不能据此确认导弹来袭。</p>
      )}
      <p className="wt-vehicle-note">乘员与弹药提醒：{!props.dryRun && props.realOutput ? "已允许播报" : "仅记录"}。</p>
    </section>
  )
}

function HelicopterStatusCard(props: { helicopter: HelicopterStatusState }) {
  const helicopter = props.helicopter
  const states: Record<string, { label: string; detail: string; tone: PanelTone }> = {
    ready: { label: "已读取", detail: "显示最近一次采样的直升机仪表数据。", tone: "success" },
    waiting: { label: "等待进场", detail: "进入直升机战局后显示当前载具状态。", tone: "info" },
    unavailable: { label: "等待数据", detail: "暂未取得有效载具数据，未知值不会当作零。", tone: "info" },
    stale: { label: "数据过期", detail: "等待新的载具采样，暂不显示旧仪表数据。", tone: "warning" },
    offline: { label: "已断开", detail: "数据连接已断开，等待恢复。", tone: "warning" },
    dead: { label: "已阵亡", detail: "阵亡期间收起旧仪表数据，重生后重新读取。", tone: "info" },
    replay: { label: "回放已暂停", detail: "回放期间不显示可能失真的载具状态。", tone: "info" },
  }
  const summary = states[helicopter.status || "unavailable"] || states.unavailable
  const ready = helicopter.status === "ready"
  const instrument = (value: number | null | undefined, unit: string, signed = false) =>
    ready && typeof value === "number" && Number.isFinite(value) && (signed || value >= 0)
      ? numberText(value, ` ${unit}`, 1) : "暂无数据"
  const rows = [
    { key: "rotor", label: "旋翼转速", value: instrument(helicopter.rotor_rpm, "rpm") },
    { key: "agl", label: "离地高度（AGL）", value: instrument(helicopter.radio_altitude_m, "m") },
    { key: "vario", label: "升降速度", value: instrument(helicopter.vario_ms, "m/s", true) },
  ]
  return (
    <section className="wt-vehicle-status" role="region" aria-label="直升机状态">
      <div className="wt-vehicle-heading">
        <h3>直升机状态</h3>
        <StatusBadge tone={summary.tone} label={summary.label} />
      </div>
      <p className="wt-vehicle-detail">{summary.detail}</p>
      <p className="wt-vehicle-note">
        {typeof helicopter.sample_age_seconds === "number" && Number.isFinite(helicopter.sample_age_seconds)
          && helicopter.sample_age_seconds >= 0
          ? `最近载具采样：${helicopter.sample_age_seconds.toFixed(1)} 秒前` : "载具采样时间未知"}
      </p>
      <dl className="wt-vehicle-grid">
        {rows.map((row) => <div key={row.key} className="wt-vehicle-stat"><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
      </dl>
      <p className="wt-vehicle-note">升降速度为负表示下降；离地高度不等于海拔高度。</p>
      <p className="wt-vehicle-note">仅显示仪表数据，不触发旋翼转速或涡环风险播报。</p>
    </section>
  )
}

function MapStatusCard(props: { naval: NavalStatusState; confirmedNaval: boolean }) {
  const naval = props.naval
  const title = props.confirmedNaval ? "海战地图态势" : "地图态势（载具未确认）"
  const states: Record<string, { label: string; detail: string; tone: PanelTone }> = {
    ready: { label: "已读取", detail: "显示本次生命内最近成功采样的地图态势。", tone: "success" },
    waiting: { label: "等待进场", detail: "进入战局并取得自身地图位置后显示态势。", tone: "info" },
    unavailable: { label: "等待数据", detail: "等待本次生命的新地图采样，未知值不会当作零。", tone: "info" },
    no_player: { label: "自身位置未知", detail: "地图尚未定位自身，暂不显示相对态势。", tone: "info" },
    stale: { label: "数据过期", detail: "等待新的地图采样，暂不显示旧图标数据。", tone: "warning" },
    offline: { label: "已断开", detail: "数据连接已断开，等待恢复。", tone: "warning" },
    dead: { label: "已阵亡", detail: "阵亡期间收起地图态势，重生后重新采样。", tone: "info" },
    replay: { label: "回放已暂停", detail: "回放期间不显示可能失真的地图态势。", tone: "info" },
  }
  const summary = states[naval.status || "unavailable"] || states.unavailable
  const ready = naval.status === "ready"
  const value = (n: number | null | undefined, unit: string, decimals = 0) =>
    ready && typeof n === "number" && Number.isFinite(n) && n >= 0 ? numberText(n, unit, decimals) : "暂无数据"
  const kinds: Record<string, string> = { aircraft: "空中图标", ground_model: "水面 / 地面图标" }
  const rows = [
    { key: "enemy", label: "可见敌方单位", value: value(naval.enemy_count, " 个") },
    { key: "ally", label: "可见友方单位", value: value(naval.ally_count, " 个") },
    { key: "air", label: "其中敌方空中图标", value: value(naval.air_contact_count, " 个") },
    { key: "kind", label: "最近敌方图标", value: ready ? kinds[naval.nearest_type || ""] || "暂无数据" : "暂无数据" },
    { key: "distance", label: "地图平面距离", value: value(naval.nearest_distance_m, " m") },
    { key: "bearing", label: "绝对方位（正北 0°）", value: value(naval.nearest_bearing_deg, "°", 1) },
  ]
  return (
    <section className="wt-vehicle-status" role="region" aria-label={title}>
      <div className="wt-vehicle-heading">
        <h3>{title}</h3>
        <StatusBadge tone={summary.tone} label={summary.label} />
      </div>
      <p className="wt-vehicle-detail">{summary.detail}</p>
      <p className="wt-vehicle-note">
        {typeof naval.sample_age_seconds === "number" && Number.isFinite(naval.sample_age_seconds) && naval.sample_age_seconds >= 0
          ? `最近地图采样：${naval.sample_age_seconds.toFixed(1)} 秒前` : "地图采样时间未知"}
      </p>
      <dl className="wt-vehicle-grid">
        {rows.map(row => <div key={row.key} className="wt-vehicle-stat"><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
      </dl>
      <p className="wt-vehicle-note">数量仅指地图已显示单位；图标不能确认舰种，距离不含高度。</p>
      <p className="wt-vehicle-note">{props.confirmedNaval
        ? "兵种字段确认海战；本卡只读，不触发播报。"
        : "尚未确认载具域，仅显示通用地图态势，不触发专项播报。"}</p>
    </section>
  )
}

function NavalInstrumentFieldCard(props: { inventory: NavalInstrumentFields }) {
  const sources: Record<string, string> = {
    response_only: "基础响应可用；字段盘点还需核对独立采样状态，字段存在不等于舰艇语义已验证。",
    offline: "连接已断开，等待恢复后再盘点。",
    waiting: "等待进入战局后盘点字段。",
    replay: "回放期间暂停字段盘点。",
    dead: "阵亡期间不沿用字段可用性，等待新响应。",
    unconfirmed_naval: "缺少有效海战兵种证据，暂不盘点舰艇字段。",
    unknown_life: "战局或生命标识未知，暂不盘点字段。",
    invalid_source: "原始来源结构或兵种证据不一致，等待可靠响应。",
    unknown_age: "响应时间未知或无效，暂不盘点字段。",
    stale: "基础遥测响应超过 5 秒，暂不展示旧字段状态。",
  }
  const labels: Record<string, { name: string; path: string }> = {
    speed: { name: "速度候选字段", path: "indicators.speed" },
    heading: { name: "罗盘候选字段", path: "indicators.heading_deg" },
    rpm: { name: "转速候选字段", path: "indicators.rpm" },
    throttle: { name: "控制量候选字段", path: "indicators.throttle" },
  }
  const states: Record<string, string> = { observed_numeric: "响应含数值，语义待验", normalized_only: "仅规范化数值，来源待核",
    raw_only: "仅原始键，尚未规范化", missing: "未提供数值", invalid: "格式无效", conflicting: "原始与规范化不一致", unavailable: "来源未就绪" }
  const age = props.inventory.response_age_seconds
  const samples: Record<string, string> = {
    ready: "独立成功采样已绑定当前战局与生命；这不证明舰艇物理语义。",
    legacy_response: "旧数据层未提供独立采样证据；仅盘点当前响应，生命绑定未知。",
    probe_failed: "仪表或战局探针请求失败，旧采样不可用。",
    context_changed: "采集中战局、生命或载具域变化，等待下一次成功采样。",
    invalid_source: "采样来源未通过严格校验，暂不盘点字段。",
    unbound_sample: "采样不属于当前战局、生命或兵种，旧字段已隐藏。",
    unknown_sample_age: "独立采样时间无效，旧字段已隐藏。",
    stale_sample: "独立成功采样超过 5 秒，旧字段已隐藏。",
    invalid_sample: "独立采样元数据无效，旧字段已隐藏。",
    unknown_age: "采样时钟无效，等待可靠采样。",
    unknown_life: "采样生命未知，等待可靠采样。",
    dead: "阵亡期间暂停采样盘点。", replay: "回放期间暂停采样盘点。",
    waiting: "等待进入战局后成功采样。", unavailable: "尚无可用的独立采样。",
  }
  const sampleAge = props.inventory.sample_age_seconds
  const sampleCount = props.inventory.sample_count
  return <section className="wt-vehicle-status" role="region" aria-label="舰艇仪表字段边界">
    <div className="wt-vehicle-heading"><h3>舰艇仪表字段边界</h3><StatusBadge tone="info" label="仪表值未启用" /></div>
    <p className="wt-vehicle-detail" data-naval-instrument-source={props.inventory.source_status || "unknown"}>
      {sources[props.inventory.source_status || ""] || "等待字段盘点来源。"}
    </p>
    <p className="wt-vehicle-note">{typeof age === "number" && Number.isFinite(age) && age >= 0
      ? `基础遥测响应年龄 ${age.toFixed(1)} 秒` : "基础遥测响应时间未知"}</p>
    <p className="wt-vehicle-detail" data-naval-instrument-sampling={props.inventory.sampling_status || "unavailable"}>
      {samples[props.inventory.sampling_status || "unavailable"] || samples.unavailable}
    </p>
    {props.inventory.sample_life_bound === true && typeof sampleAge === "number" && Number.isFinite(sampleAge)
      && typeof sampleCount === "number" && Number.isSafeInteger(sampleCount) && sampleCount > 0
      ? <p className="wt-vehicle-note">成功采样序号 {sampleCount} · 采样年龄 {sampleAge.toFixed(1)} 秒</p> : null}
    <dl className="wt-vehicle-grid">{(props.inventory.fields || []).map(row => {
      const label = labels[row.id]
      if (!label) return null
      return <div className="wt-vehicle-stat" key={row.id} data-naval-instrument-field={row.id}>
        <dt>{label.name}</dt><dd><StatusBadge tone={row.status === "invalid" || row.status === "conflicting" ? "warning" : "info"}
          label={states[row.status] || "状态未知"} /><p className="wt-vehicle-note">{label.path}</p></dd>
      </div>
    })}</dl>
    <p className="wt-vehicle-note">四项仅盘点响应字段；舰艇单位、量纲、符号与范围仍待样本确认，不显示仪表读数。</p>
    <p className="wt-vehicle-note">基础响应、地图与载具采样不能替代仪表独立成功采样。生命绑定只跟随已确认生命周期，不新增舰艇重生推断；舰员、舰炮弹药、舰体/进水和温度仍待专用合同。</p>
    <p className="wt-vehicle-note">查看本卡不推进检测或触发播报；两类海战事件真实输出保持关闭。</p>
  </section>
}

function NavalStaticReferenceCard(props: { reference: NavalStaticReference }) {
  const ref = props.reference
  const reasons: Record<string, string> = {
    catalog_unavailable: "静态资料不可用，不沿用或猜测舰艇参数。",
    sample_unavailable: "尚无当前生命的有效仪表采样；仅展示资料范围，不关联旧载具。",
    unconfirmed_vehicle: "缺少一致的精确型号来源，不进行模糊匹配。",
    not_indexed: "当前型号未收录；资料缺失不代表游戏不支持。",
    matched: "当前采样的型号与静态资料精确匹配；本机游戏版本、改装与配置语义仍未验证。",
  }
  const relations: Record<string, string> = {
    configuration_not_reading: "速度配置不等于当前航速，单位与对应关系待验",
    no_direct_static_mapping: "静态资料没有当前航向的直接映射",
    structure_not_reading: "推进器结构不等于当前转速，不能把单值分配给多机",
    model_not_control: "加速模型不等于当前控制量或车钟",
  }
  const count = (value?: number | null) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? String(value) : "未收录"
  const vehicle = ref.vehicle
  const configuration = vehicle?.configuration
  const configurationLabels: Record<string, string> = { none_declared: "未声明改装项", declarations_resolved: "声明引用已解析", partial: "声明解析存在缺口" }
  return <section className="wt-vehicle-status" role="region" aria-label="舰艇静态资料与实时边界">
    <div className="wt-vehicle-heading"><h3>舰艇静态资料与实时边界</h3><StatusBadge tone="info" label="静态配置 · 非实时" /></div>
    <p className="wt-vehicle-detail" data-naval-static-status={ref.status}>{reasons[ref.status] || reasons.catalog_unavailable}</p>
    {ref.source ? <p className="wt-vehicle-note">Datamine {ref.source.version} · 提交 {ref.source.ref.slice(0, 10)} ·
      收录 {ref.indexed_files} 个舰艇目录配置（含 AI/场景单位，不等同可玩舰艇数）。</p> : null}
    {vehicle ? <dl className="wt-vehicle-grid">
      <div className="wt-vehicle-stat"><dt>精确型号 / 静态类型</dt><dd data-naval-static-vehicle>{vehicle.id}<p className="wt-vehicle-note">{vehicle.type_code || "类型未收录"}</p></dd></div>
      <div className="wt-vehicle-stat"><dt>配置发动机条目 / 推进器</dt><dd>{count(vehicle.engine_entry_count)} / {count(vehicle.propulsion_count)}</dd></div>
      <div className="wt-vehicle-stat"><dt>配置舰员分区</dt><dd>{count(vehicle.crew_station_count)}</dd></div>
      <div className="wt-vehicle-stat"><dt>配置分区舰员合计（非实时）</dt><dd>{count(vehicle.crew_distribution_total)}</dd></div>
    </dl> : null}
    {vehicle ? <div data-naval-configuration-status={configuration?.status || "legacy"}>
      <p className="wt-vehicle-detail">{configuration ? configurationLabels[configuration.status] || "声明状态未知" : "旧资料库暂无改装解析"} · 当前生效参数未知</p>
      {configuration ? <p className="wt-vehicle-note">基础字段：{configuration.base_status === "direct_fields" ? "文件直接声明" : "含未解析继承指令"}；
        改装声明 {count(configuration.declared_count)} 项，公共定义 {count(configuration.common_definition_count)} 项，本地非空声明 {count(configuration.local_override_count)} 项，
        模板引用 {count(configuration.template_reference_count)} 处，显式空块 {count(configuration.explicit_empty_block_count)} 处。</p> : null}
      {configuration?.status === "partial" ? <p className="wt-vehicle-note">缺失公共定义 {count(configuration.missing_common_definition_count)}，缺失前序/依赖 {count(configuration.missing_dependency_count)}，
        循环节点 {count(configuration.cycle_node_count)}，缺失模板 {count(configuration.missing_template_count)}；完整声明证据见离线开发报告。</p> : null}
      <p className="wt-vehicle-note">公共与本地效果块分别保留，未模拟空块合并或效果叠加；已安装改装、模式、外部武器模板及引擎生效规则未验证，不能据此计算当前或满改参数。</p>
    </div> : null}
    <dl>{ref.field_mapping.map(row => <div key={row.id} data-naval-static-mapping={row.id}>
      <dt><strong>{row.normalized_key}</strong></dt>
      <dd className="wt-vehicle-note">{relations[row.relation] || "尚无已验证的直接映射"}。</dd>
    </div>)}</dl>
    <p className="wt-vehicle-note">静态配置不能补出当前舰员、航速、转速、操纵量、损伤或进水；不显示配置速度/质量的未确认单位，不生成阈值、阵亡或重生判断。真实输出保持关闭。</p>
  </section>
}

function NavalResultComparison(props: { result?: NavalDetectionResult | null }) {
  const summary = (kind: string, record?: NavalResultRecord | null): { label: string; detail: string; tone: PanelTone } => {
    if (!record) return { label: kind === "candidate" ? "尚无可关联候选" : kind === "decision" ? "尚无仲裁结果" : "尚无记录结果",
      detail: kind === "candidate" ? "仅关联本次有效确认，不沿用旧生命、旧确认或失效来源的结果。" : "等待此候选到达这一阶段。", tone: "default" }
    if (kind === "candidate") return { label: "候选已生成", detail: typeof record.map_sample_count === "number"
      ? `确认采样序号 ${record.map_sample_count}；这不表示已进入记录或播报。` : "这不表示已进入记录或播报。", tone: "info" }
    if (record.stage === "dispatcher_dry_run") return { label: "仅 dry-run 记录", detail: "此候选已走到记录阶段，没有提交语音。", tone: "info" }
    if (record.stage === "dispatcher_failed") return { label: "记录阶段失败", detail: "该候选的记录阶段未完成，真实输出仍关闭。", tone: "warning" }
    if (record.stage === "dispatcher_pushed") return { label: "异常投递记录", detail: "记录与海战禁播策略不一致，需要检查运行版本。", tone: "danger" }
    const reasons: Record<string, { label: string; detail: string; tone: PanelTone }> = {
      selected: { label: "已通过仲裁", detail: "已选中此候选；后续是否完成以记录结果为准。", tone: "info" },
      naval_dry_run_only: { label: "真实输出已阻断", detail: "海战态势仅作观察，全局 dry-run 关闭也不会播报。", tone: "info" },
      naval_contact_cleared: { label: "候选已失效", detail: "接触、来源时效或生命已变化，旧候选已撤销。", tone: "default" },
      rate_limited: { label: "限流等待中", detail: "候选仍在单槽窗口等待，尚未到达记录阶段。", tone: "warning" },
      cooldown_active: { label: "冷却中", detail: "同类事件仍在冷却，本次没有进入记录。", tone: "warning" },
      lost_in_window: { label: "被其他候选替代", detail: "单槽窗口保留了其他候选，本次没有进入记录。", tone: "default" },
      preempted_by_critical: { label: "被危急提醒替代", detail: "更高优先级事件获得处理，本次没有进入记录。", tone: "default" },
      scenario_gated: { label: "当前场景拦截", detail: "当前场景不允许此类普通态势候选进入记录。", tone: "default" },
      expired_before_flush: { label: "候选已过期", detail: "等待期间超过事件有效期，本次没有进入记录。", tone: "default" },
      broadcast_category_disabled: { label: "类别偏好已关闭", detail: "设置中关闭了这类普通态势候选。", tone: "default" },
      broadcast_category_disabled_on_flush: { label: "类别偏好已关闭", detail: "等待期间关闭了这类普通态势候选。", tone: "default" },
      paused: { label: "手动暂停拦截", detail: "安全暂停阻止了这次候选继续处理。", tone: "warning" },
      tripped: { label: "自动暂停拦截", detail: "安全暂停阻止了这次候选继续处理。", tone: "warning" },
    }
    return reasons[record.reason] || { label: "已有阶段记录", detail: "原因尚未收录，不能据此判断已完成 dry-run 记录。", tone: "default" }
  }
  const steps = [{ key: "candidate", title: "候选", record: props.result?.candidate },
    { key: "decision", title: "仲裁", record: props.result?.decision }, { key: "output", title: "记录", record: props.result?.output }]
  return <div className="wt-naval-results" aria-label="本次确认的结果对照">
    <ol>{steps.map(step => {
      const value = summary(step.key, step.record)
      return <li key={step.key} data-naval-result={step.key}>
        <strong>{step.title}</strong><StatusBadge tone={value.tone} label={value.label} />
        <p className="wt-vehicle-note">{value.detail}</p>
        {step.record?.ts ? <p className="wt-vehicle-note">记录时间 {formatTime(step.record.ts)}</p> : null}
      </li>
    })}</ol>
  </div>
}

function NavalDetectionCard(props: { detection: NavalDetectionState }) {
  const detection = props.detection
  const sources: Record<string, string> = {
    ready: "来源可用：兵种已确认海战，地图采样有效。",
    offline: "连接已断开，等待数据层恢复。",
    replay: "回放期间暂停海战检测。",
    waiting: "尚未进入战局，等待进场。",
    dead: "已阵亡，等待重生后的新采样。",
    unconfirmed_naval: "尚未取得有效的海战兵种证据，地图图标不能确认载具域。",
    missing_battle: "战局标识未知，暂不连接前后采样。",
    unknown_age: "采样时间未知或无效，等待新数据。",
    stale: "地图或基础遥测已超过 5 秒有效期，旧进度暂不展示。",
    unknown_sample: "成功采样计数或生命标识未知，不能累计确认。",
    life_mismatch: "地图来自上一次生命，等待重生后的新采样。",
    no_player: "地图尚未定位自身，不能确认有效态势。",
    invalid_position: "自身地图坐标无效，等待新采样。",
    invalid_counts: "敌方图标数量未知或不一致，不能当作零或触发依据。",
  }
  const progress: Record<string, { label: string; detail: string; tone: PanelTone }> = {
    pending: { label: "等待检测", detail: "当前采样尚未处理，等待下一次检测轮询。", tone: "info" },
    blocked: { label: "来源未就绪", detail: "来源恢复后重新确认，见上方来源说明。", tone: "warning" },
    disabled: { label: "检测已暂停", detail: "插件已停用，启用后才会继续检测。", tone: "info" },
    absent: { label: "未发现图标", detail: "当前采样没有此类图标，等待出现。", tone: "info" },
    confirming: { label: "出现确认中", detail: "等待下一次独立成功地图采样；缓存刷新不累计。", tone: "info" },
    active: { label: "出现已确认", detail: "本次出现已生成候选；持续存在不重复触发，记录结果见活动页。", tone: "success" },
    clearing: { label: "消失确认中", detail: "再确认一次消失后重新待命；此时不生成出现候选。", tone: "info" },
  }
  const ready = detection.source_status === "ready"
  const age = detection.sample_age_seconds
  return (
    <section className="wt-vehicle-status" role="region" aria-label="海战 dry-run 检测诊断">
      <div className="wt-vehicle-heading">
        <h3>海战 dry-run 检测诊断</h3>
        <StatusBadge tone="info" label="真实输出关闭" />
      </div>
      <p className="wt-vehicle-detail" data-naval-source={detection.source_status || "unknown"}>
        {sources[detection.source_status || ""] || "等待来源诊断数据。"}
      </p>
      <p className="wt-vehicle-note">
        {typeof age === "number" && Number.isFinite(age) && age >= 0 ? `地图采样年龄 ${age.toFixed(1)} 秒` : "地图采样时间未知"}
        {ready && typeof detection.map_sample_count === "number" ? ` · 成功采样序号 ${detection.map_sample_count}` : ""}
      </p>
      <dl className="wt-vehicle-grid">
        {(detection.detectors || []).map(row => {
          const summary = progress[row.status] || progress.blocked
          return <div className="wt-vehicle-stat" key={row.event_id} data-naval-detector={row.event_id}>
            <dt>{EVENT_LABELS[row.event_id] || "海战图标检测"}</dt>
            <dd>
              <StatusBadge tone={summary.tone} label={summary.label} />
              <p className="wt-vehicle-detail">{row.status === "clearing" ? "消失确认" : "出现确认"} {row.hits}/{row.required}</p>
              <p className="wt-vehicle-note">{summary.detail}</p>
              <NavalResultComparison result={row.result} />
            </dd>
          </div>
        })}
      </dl>
      <p className="wt-vehicle-note">两项海战事件仅作 dry-run 记录，关闭全局 dry-run 也不会真实输出。查看本卡不累计采样，不触发播报。</p>
    </section>
  )
}

export default function NekoWarthunderPanel(props: PluginSurfaceProps<DashboardState>) {
  const state = props.state || {}
  const safety = state.safety || {}
  const identity = state.identity || {}
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
  const actions = Array.isArray(props.actions) ? props.actions : []
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
  const clipboard = useClipboard()
  const onboardingRequired = state.onboarding?.required === true
  const [activeTab, setActiveTab] = useState("overview")
  const [activityFilter, setActivityFilter] = useState("all")
  const [onboardingOpen, setOnboardingOpen] = useState(onboardingRequired)
  const [onboardingAutoOpened, setOnboardingAutoOpened] = useState(false)
  const [onboardingStep, setOnboardingStep] = useState(0)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [onDemandOverride, setOnDemandOverride] = useState<OnDemandState | null>(null)
  const [onDemandBusy, setOnDemandBusy] = useState(false)
  const onDemand = onDemandOverride || state.on_demand || {}
  const onDemandLabels: Record<string, string> = {
    disabled: "已关闭", registering: "正在请求注册", registration_requested: "已请求注册，等待工具调用确认",
    active: "已收到工具调用", unsupported: "当前宿主 SDK 不支持", role_unavailable: "无法确认当前角色",
    registration_failed: "注册失败，继续使用面板", cleanup_required: "已阻止读取，工具清理待重试",
    rebind_required: "角色已变化，需要重新绑定",
  }
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
  const filteredActivityItems = activityFilter === "all"
    ? allActivityItems
    : allActivityItems.filter((item) => item.kind === activityFilter || (activityFilter === "suppressed" && item.kind === "failed"))
  const currentBattleStatus = battleStatus(state)
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

    const hidden = () =>
      typeof document !== "undefined" && (document as { hidden?: boolean }).hidden === true

    const tick = async () => {
      if (cancelled) return
      if (!hidden() && !refreshInFlight) {
        refreshInFlight = true
        try {
          await props.api.refresh()
        } catch {
          // 刷新失败只影响这一拍：下一拍照常重试，不打断面板。
        } finally {
          refreshInFlight = false
        }
      }
      if (!cancelled) {
        timer = setTimeout(() => { void tick() }, PANEL_REFRESH_INTERVAL_MS)
      }
    }

    timer = setTimeout(() => { void tick() }, PANEL_REFRESH_INTERVAL_MS)
    return () => {
      cancelled = true
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [props.api])

  async function setDryRun(value: boolean) {
    if (!setDryRunAction) {
      setDryRunError("播报模式暂时不可用")
      return
    }
    try {
      setDryRunError("")
      await props.api.call("set_dry_run", { value })
      toast.success(value ? "战斗播报已关闭，继续检测和记录" : "战斗播报已开启")
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

  function handleTestResult(envelope: any) {
    const result = unwrapActionResult(envelope)
    // 后端 test_say 声明 refresh_context=False，动作按钮也传 refresh={false}，
    // 好让这里先处理结果再刷新；但它确实写了 timeline，不刷新的话诊断页第 5 步
    // "猫娘接收"会一直停在"尚未测试"，与这里弹出的成功提示自相矛盾。
    void props.api.refresh().catch(() => undefined)
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

  const statusActions = (
    <div className="wt-status-actions">
      {summary.kind === "identity" ? (
        <Button onClick={openIdentityModal}>设置游戏昵称</Button>
      ) : null}
      {summary.kind === "waiting" || summary.kind === "error" ? (
        <RefreshButton label="刷新状态" />
      ) : null}
      <Button
        className="wt-primary-action"
        tone="primary"
        onClick={() => setDryRun(!detectOnly)}
      >
        {detectOnly ? "开启战斗播报" : "停止战斗播报"}
      </Button>
    </div>
  )

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

  const overview = (
    <div>
      <section className="wt-status" data-tone={summary.tone}>
        <div className="wt-status-copy">
          <div className="wt-status-heading">
            <h2 className="wt-status-title">{summary.title}</h2>
            <span className="wt-mode-chip" data-mode={detectOnly ? "detect" : "live"}>
              输出模式 · {detectOnly ? "播报未启动" : "战斗播报"}
            </span>
          </div>
          <p className="wt-status-detail">{summary.detail}</p>
        </div>
        {statusActions}
      </section>
      {dryRunError ? <Alert tone="danger">{dryRunError}</Alert> : null}

      <div className="wt-overview-grid">
        <section className="wt-column">
          <h2 className="wt-section-title">当前战局</h2>
          {state.in_battle ? (
            <div className="wt-battle-main">
              <p className="wt-battle-title">{mappedText(state.domain, DOMAIN_LABELS)} · {text(state.vehicle_type)}</p>
              <p className="wt-battle-meta">{mappedText(state.scenario, SCENARIO_LABELS)} · 战斗中</p>
            </div>
          ) : (
            <div className="wt-battle-main">
              <p className="wt-battle-title">尚未检测到战局</p>
              <p className="wt-battle-meta">进入 War Thunder 战斗后自动显示当前模式和载具。</p>
            </div>
          )}

          <div className="wt-health" data-tone={currentBattleStatus.tone}>
            <span className="wt-health-mark" />
            <div>
              <p className="wt-health-title">{currentBattleStatus.title}</p>
              <p className="wt-health-detail">{currentBattleStatus.detail}</p>
            </div>
          </div>

          {state.trusted_facts ? <TrustedFactsCard facts={state.trusted_facts} openActivity={() => setActiveTab("activity")} /> : null}

          <div className="wt-identity">
            <div>
              <p className="wt-identity-name">{playerName || "尚未设置战雷游戏昵称"}</p>
              <p className="wt-identity-meta">{playerName ? "已保存，等待本局身份匹配" : "设置后可识别自己发送的固定无线电消息"}</p>
            </div>
            <Button className="wt-link-action" onClick={openIdentityModal}>{playerName ? "修改" : "设置"}</Button>
          </div>
          {state.domain === "ground" ? <GroundStatusCard
            ground={state.ground_status || {}} dryRun={detectOnly}
            explanation={state.ground_ammo_explanation}
            realOutput={outputPolicy.ground_status_real_output_enabled === true}
          /> : null}
          {state.domain === "heli" ? <HelicopterStatusCard helicopter={state.helicopter_status || {}} /> : null}
          {state.domain === "naval" ? <MapStatusCard naval={state.naval_status || {}} confirmedNaval={true} /> : null}
          {state.map_status ? <MapStatusCard naval={state.map_status} confirmedNaval={false} /> : null}
          {state.naval_detection ? <NavalDetectionCard detection={state.naval_detection} /> : null}
        </section>

        <section className="wt-column">
          <div className="wt-activity-head">
            <h2 className="wt-section-title">最近活动</h2>
            <StatusBadge tone={summary.tone} label={summary.modeLabel} />
          </div>
          {activityItems.length ? (
            <div className="wt-activity-list">
              {activityItems.map((item) => (
                <div key={item.key} className="wt-activity-row" data-tone={item.tone}>
                  <span className="wt-activity-time">{item.time}</span>
                  <span className="wt-activity-mark" />
                  <div>
                    <p className="wt-activity-title">{item.title}</p>
                    <p className="wt-activity-detail">{item.detail}</p>
                  </div>
                  <StatusBadge tone={item.tone} label={item.status} />
                </div>
              ))}
            </div>
          ) : (
            <div className="wt-empty">识别到可信事件后，这里会显示它为什么播报或没有播报。</div>
          )}
        </section>
      </div>

      {dialoguePolicyError ? <Alert tone="danger">{dialoguePolicyError}</Alert> : null}
    </div>
  )

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

  const diagnostics = (
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
          <ActionButton
            className="wt-test-sound-action"
            action={testSayAction}
            actionId="test_say"
            values={{ text: "副驾驶面板测试：能听到我吗？" }}
            refresh={false}
            onResult={handleTestResult}
            onError={() => { toast.error("测试请求提交失败") }}
          >
            测试开口
          </ActionButton>
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

          {state.domain === "ground" ? <GroundStatusCard
            ground={state.ground_status || {}} dryRun={detectOnly}
            explanation={state.ground_ammo_explanation}
            realOutput={outputPolicy.ground_status_real_output_enabled === true}
          /> : null}
          {state.domain === "heli" ? <HelicopterStatusCard helicopter={state.helicopter_status || {}} /> : null}
          {state.domain === "naval" ? <MapStatusCard naval={state.naval_status || {}} confirmedNaval={true} /> : null}
          {state.map_status ? <MapStatusCard naval={state.map_status} confirmedNaval={false} /> : null}
          {state.naval_detection ? <NavalDetectionCard detection={state.naval_detection} /> : null}

          {state.naval_instrument_fields ? <NavalInstrumentFieldCard inventory={state.naval_instrument_fields} /> : null}
          {state.naval_static_reference ? <NavalStaticReferenceCard reference={state.naval_static_reference} /> : null}

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

  const activityFilters = [
    { value: "all", label: "全部" },
    { value: "delivered", label: "已提交" },
    { value: "recorded", label: "仅记录" },
    { value: "suppressed", label: "未输出" },
  ]
  const activity = (
    <div className="wt-activity-page">
      <header className="wt-activity-page-head">
        <div>
          <h2>活动记录</h2>
          <p>查看插件识别了什么，以及它为什么提交、仅记录或没有输出。</p>
        </div>
        <div className="wt-activity-filter" role="group" aria-label="筛选活动记录">
          {activityFilters.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={`wt-activity-filter-button ${activityFilter === filter.value ? "is-active" : ""}`}
              aria-pressed={activityFilter === filter.value}
              onClick={() => { setActivityFilter(filter.value) }}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </header>
      <div className="wt-activity-page-note">
        <span>只保留最近 20 条安全摘要，不保存玩家昵称、聊天或 HUD 原文。</span>
        <span>当前显示 {filteredActivityItems.length} 条</span>
      </div>
      {filteredActivityItems.length ? (
        <div className="wt-activity-list wt-activity-page-list">
          {filteredActivityItems.map((item) => (
            <div key={item.key} className="wt-activity-row" data-tone={item.tone}>
              <span className="wt-activity-time">{item.time}</span>
              <span className="wt-activity-mark" />
              <div>
                <p className="wt-activity-title">{item.title}</p>
                <p className="wt-activity-detail">{item.detail}</p>
              </div>
              <StatusBadge tone={item.tone} label={item.status} />
            </div>
          ))}
        </div>
      ) : (
        <div className="wt-empty">当前筛选下还没有活动记录。</div>
      )}
    </div>
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
        {activeTab === "overview" ? overview : activeTab === "activity" ? activity : diagnostics}
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

      <Modal
        open={settingsOpen}
        title="设置"
        onClose={() => { setSettingsOpen(false) }}
        footer={<Button onClick={() => { setSettingsOpen(false) }}>完成</Button>}
      >
        <div className="wt-settings">
          <div className="wt-settings-row" role="region" aria-label="会话按需解释">
            <div className="wt-settings-copy">
              <h3>按需解释（本次会话）</h3>
              <p>{onDemandLabels[onDemand.status || "disabled"] || "暂不可用"}{onDemand.role ? ` · 绑定角色：${onDemand.role}` : ""}</p>
              <p>只查当前状态、可用能力和输出策略；不解释具体历史事件，不改变战斗播报。每次重启关闭，换角色需重新绑定。</p>
              <p>启用后工具定义和结果会增加对话 token；普通回答可能按宿主聊天设置发声。5 秒冷却、同时读取 1 次，不自动重试。</p>
            </div>
            <div className="wt-settings-control">
              <Stack>
                <Button disabled={!onDemandAction || onDemand.supported === false || onDemandBusy}
                  onClick={() => setOnDemand(true)}>{onDemand.enabled || onDemand.status === "rebind_required" ? "重新绑定当前角色" : "本次会话启用并绑定当前角色"}</Button>
                <Button disabled={!onDemandAction || onDemandBusy || (!onDemand.enabled && !onDemand.cleanup_pending)}
                  onClick={() => setOnDemand(false)}>停用并清理按需解释</Button>
              </Stack>
            </div>
          </div>
          <div className="wt-settings-row">
            <div className="wt-settings-copy">
              <h3>播报频率</h3>
              <p>调整非危急提醒的间隔；危急提醒不会被延迟。</p>
            </div>
            <div className="wt-settings-control is-wide">
              <ButtonGroup className="wt-frequency-control">
                {BROADCAST_FREQUENCY_OPTIONS.map((option) => (
                  <Button
                    key={option.value}
                    tone={broadcastFrequency === option.value ? "primary" : "default"}
                    onClick={() => { void setBroadcastFrequency(option.value) }}
                  >
                    {option.label}
                    {broadcastFrequency === option.value ? (
                      <span className="wt-sr-only">（当前选择）</span>
                    ) : null}
                  </Button>
                ))}
              </ButtonGroup>
            </div>
          </div>
          <div className="wt-settings-row">
            <div className="wt-settings-copy">
              <h3>播报内容</h3>
              <p>只保留你想听的内容。危急安全提醒和阵亡提醒始终开启。</p>
            </div>
            <div className="wt-settings-control is-wide">
              <div className="wt-category-list">
                {BROADCAST_CATEGORY_OPTIONS.map((option) => {
                  const enabled = broadcastCategories[option.value] !== false
                  return (
                    <div className="wt-category-row" key={option.value}>
                      <div>
                        <strong>{option.label}</strong>
                        <span>{option.detail}</span>
                      </div>
                      <Button
                        className="wt-toggle-button"
                        tone={enabled ? "primary" : "default"}
                        onClick={() => { void setBroadcastCategory(option.value, !enabled) }}
                      >
                        {enabled ? "已开启" : "已关闭"}
                      </Button>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
          <div className="wt-settings-row">
            <div className="wt-settings-copy">
              <h3>恢复推荐播报设置</h3>
              <p>恢复标准频率并开启全部普通播报类别，不影响昵称、插话规则和播报开关。</p>
            </div>
            <div className="wt-settings-control">
              <Button onClick={() => { void resetBroadcastPreferences() }}>恢复推荐设置</Button>
            </div>
          </div>
          <div className="wt-settings-row">
            <div className="wt-settings-copy">
              <h3>战雷游戏昵称</h3>
              <p>{playerName ? `当前为 ${playerName}` : "用于识别你自己发送的固定无线电消息和本局归属。"}</p>
            </div>
            <div className="wt-settings-control">
              <Button onClick={() => { setSettingsOpen(false); openIdentityModal() }}>{playerName ? "修改昵称" : "设置昵称"}</Button>
            </div>
          </div>
          <div className="wt-settings-row">
            <div className="wt-settings-copy">
              <h3>小地图敌我颜色</h3>
              <p>8111 只提供图标颜色，插件按颜色区分队友和敌人。在游戏设置里改过颜色时，请在这里改成相同的颜色。</p>
            </div>
            <div className="wt-settings-control is-wide">
              <Stack>
                <div className="wt-color-row">
                  <Field label="队友">
                    <Input type="color" value={allyColor} onChange={setAllyColor} />
                  </Field>
                  <Field label="敌人">
                    <Input type="color" value={enemyColor} onChange={setEnemyColor} />
                  </Field>
                </div>
                <ButtonGroup>
                  <Button onClick={() => { void submitFactionColors(true) }}>恢复默认</Button>
                  <Button tone="primary" onClick={() => { void submitFactionColors(false) }}>保存颜色</Button>
                </ButtonGroup>
                {factionColorError ? <Alert tone="danger">{factionColorError}</Alert> : null}
              </Stack>
            </div>
          </div>
          <div className="wt-settings-row">
            <div className="wt-settings-copy">
              <h3>新手教程</h3>
              <p>重新查看昵称填写和常用按钮说明。</p>
            </div>
            <div className="wt-settings-control">
              <Button onClick={() => { setSettingsOpen(false); openOnboarding() }}>重新查看教程</Button>
            </div>
          </div>
          {broadcastPreferenceError ? <Alert tone="danger">{broadcastPreferenceError}</Alert> : null}
        </div>
      </Modal>

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
