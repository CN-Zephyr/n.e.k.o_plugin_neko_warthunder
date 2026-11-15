import type { DashboardState, ObserveRecord } from "./panel-state"

export const DOMAIN_LABELS: { [key: string]: string } = {
  air: "空战",
  heli: "直升机",
  ground: "陆战",
  naval: "海战",
  menu: "菜单",
  unknown: "未知模式",
}

export const CONN_STATE_LABELS: { [key: string]: string } = {
  offline: "离线",
  not_in_battle: "已连接·未进战局",
  in_battle: "战局中",
}

export const SCENARIO_LABELS: { [key: string]: string } = {
  OUT_OF_BATTLE: "战斗外",
  SPAWNING: "出生/进场",
  IN_FLIGHT: "战斗中",
  COMBAT_STRESS: "交战中",
  CRITICAL_RISK: "危急状态",
  DEAD: "已阵亡",
  BATTLE_ENDED: "战斗结束",
}

export const DATA_LAYER_LABELS: { [key: string]: string } = {
  managed: "插件托管",
  external: "外部运行",
  starting: "正在启动",
  missing: "未连接",
  failed: "启动失败",
  stopped: "已停止",
  disabled: "未启用",
  unknown: "未知",
}

export const RISK_LEVEL_LABELS: { [key: string]: string } = {
  info: "信息",
  normal: "正常",
  warning: "注意",
  danger: "危险",
  critical: "危急",
}

export const SAFETY_STATUS_LABELS: { [key: string]: string } = {
  running: "正常",
  paused: "已手动暂停",
  tripped: "已自动急停",
  ok: "正常",
}

export const DIALOGUE_OPTIONS = [
  { value: "no_interrupt", label: "不打断当前对话" },
  { value: "critical_only", label: "仅危急情况可打断" },
  { value: "allow_interrupt", label: "允许打断当前对话" },
]

export const DIALOGUE_LABELS: { [key: string]: string } = Object.fromEntries(
  DIALOGUE_OPTIONS.map((item) => [item.value, item.label]),
)

export function text(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-"
  if (typeof value === "boolean") return value ? "是" : "否"
  return String(value)
}

export function percentText(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  return `${Math.round(value * 100)}%`
}

export function flagsText(flags: Record<string, boolean> | undefined): string {
  if (!flags) return "-"
  const active = Object.keys(flags).filter((key) => flags[key])
  return active.length ? active.join(", ") : "无"
}

export function listText(values: string[] | undefined): string {
  return values && values.length ? values.join(", ") : "无"
}

export function mappedText(value: unknown, labels: { [key: string]: string } = {}): string {
  const raw = text(value)
  return labels[raw] || raw
}

export function safetyIsTripped(state: DashboardState): boolean {
  return state.safety?.status === "tripped" || state.safety?.auto_paused === true
}

export function safetyIsPaused(state: DashboardState): boolean {
  return state.safety?.status === "paused" || state.safety?.manual_paused === true
}

export function outputWasPushed(record: ObserveRecord | null | undefined): boolean {
  return record?.stage === "dispatcher_pushed"
    || record?.stage === "test_say_pushed"
    || record?.pushed === true
    || record?.outcome === "pushed"
}

export function outputFailed(record: ObserveRecord | null | undefined): boolean {
  return record?.stage?.includes("failed") === true || record?.outcome === "failed"
}
