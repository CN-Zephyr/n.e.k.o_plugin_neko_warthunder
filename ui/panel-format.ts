export type PanelTone = "primary" | "success" | "warning" | "danger" | "info" | "default"

export const EVENT_LABELS: { [key: string]: string } = {
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

export function numberText(value: unknown, unit = "", digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  return `${value.toFixed(digits)}${unit}`
}

export function formatTime(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "最近"
  const date = new Date(typeof value === "number" && value < 1_000_000_000_000 ? value * 1000 : value)
  if (Number.isNaN(date.getTime())) return "最近"
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}
