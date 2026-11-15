import { StatusBadge, useEffect, useRef, useState } from "@neko/plugin-ui"
import { NavalCards } from "./naval-cards"
import { DOMAIN_LABELS, mappedText } from "./panel-display"
import { numberText, formatTime } from "./panel-format"
import type { PanelTone } from "./panel-format"
import type { DashboardState, GroundStatusState, HelicopterStatusState, TrustedFactsState } from "./panel-state"

export const GROUND_SAMPLE_MAX_AGE_MS = 5000

export const VehicleCards = { TrustedFactsCard, VehicleStatusCards, useGroundSampleAge }

function VehicleStatusCards({ state, ground, dryRun }: {
  state: DashboardState
  ground: GroundStatusState
  dryRun: boolean
}) {
  return (
    <>
      {state.domain === "ground" ? <GroundStatusCard
        ground={ground} dryRun={dryRun}
        explanation={state.ground_ammo_explanation}
        realOutput={state.output_policy?.ground_status_real_output_enabled === true}
      /> : null}
      {state.domain === "heli" ? <HelicopterStatusCard helicopter={state.helicopter_status || {}} /> : null}
      {state.domain === "naval" ? <NavalCards.MapStatusCard naval={state.naval_status || {}} confirmedNaval={true} /> : null}
      {state.map_status ? <NavalCards.MapStatusCard naval={state.map_status} confirmedNaval={false} /> : null}
      {state.naval_detection ? <NavalCards.NavalDetectionCard detection={state.naval_detection} /> : null}
    </>
  )
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

function useGroundSampleAge(ground: GroundStatusState | null | undefined): number | null {
  const sample = useRef<{
    ground: GroundStatusState; timestamp: number | null; sampledAt: number | null
  } | null>(null)
  const [, refreshClock] = useState(0)
  const now = performance.now()
  if (!ground) {
    sample.current = null
  } else if (ground !== sample.current?.ground) {
    const age = ground.sample_age_seconds
    const timestamp = typeof ground.sample_timestamp === "number" && Number.isFinite(ground.sample_timestamp)
      && ground.sample_timestamp > 0 ? ground.sample_timestamp : null
    let sampledAt = typeof age === "number" && Number.isFinite(age) && age >= 0 ? now - age * 1000 : null
    // The same telemetry can arrive in several dashboard responses. Keep its earliest deadline.
    const previous = sample.current
    if (timestamp !== null && previous?.timestamp === timestamp && previous.sampledAt !== null && sampledAt !== null) {
      sampledAt = Math.min(previous.sampledAt, sampledAt)
    }
    sample.current = { ground, timestamp, sampledAt }
  }

  const sampledAt = sample.current?.sampledAt ?? null
  const expiresAt = sampledAt === null ? null : sampledAt + GROUND_SAMPLE_MAX_AGE_MS
  const pendingExpiry = expiresAt !== null && now < expiresAt ? expiresAt : null
  useEffect(() => {
    if (pendingExpiry === null) return
    const update = () => refreshClock(value => value + 1)
    const onVisibilityChange = () => { if (!document.hidden) update() }
    const timer = setTimeout(update, Math.max(0, pendingExpiry - performance.now() + 1))
    document.addEventListener("visibilitychange", onVisibilityChange)
    return () => {
      clearTimeout(timer)
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [pendingExpiry])
  return sampledAt === null ? null : (now - sampledAt) / 1000
}

function GroundStatusCard(props: {
  ground: GroundStatusState; dryRun: boolean; realOutput: boolean; explanation?: { status: string } | null
}) {
  const ground = props.ground
  const states: Record<string, { label: string; detail: string; tone: PanelTone }> = {
    ready: { label: "已读取", detail: "显示最近一次采样的载具状态。", tone: "success" },
    held: { label: "暂用上次数据", detail: "本次仪表采集失败，显示仍在有效期内的上一次采样。", tone: "warning" },
    waiting: { label: "等待进场", detail: "进入陆战后显示当前载具状态。", tone: "info" },
    unavailable: { label: "等待数据", detail: "暂未取得有效载具数据，未知值不会当作零。", tone: "info" },
    stale: { label: "数据过期", detail: "等待新的载具采样，暂不显示旧车状态。", tone: "warning" },
    offline: { label: "已断开", detail: "数据连接已断开，等待恢复。", tone: "warning" },
    dead: { label: "已阵亡", detail: "阵亡期间收起旧车状态，重生后重新读取。", tone: "info" },
    replay: { label: "回放已暂停", detail: "回放期间不显示可能失真的载具状态。", tone: "info" },
  }
  const summary = states[ground.status || "unavailable"] || states.unavailable
  const ready = ground.status === "ready" || ground.status === "held"
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
  const moduleDamage = (value: boolean | null | undefined, damaged: string) => {
    if (!ready || typeof value !== "boolean") return "暂无数据"
    return value ? damaged : "未报告损伤"
  }
  const explanations: Record<string, string> = {
    source_unavailable: "当前来源不可用于解释，等待新数据。",
    count_unknown: "当前一级待发弹数量未知，不能当作零发。",
    conflicting: "当前数量或标记无法一致解释，暂不作判断。",
    zero_unconfirmed: "当前读数为 0，未取得一致的耗尽标记；不能据此判定全车无弹。",
    empty_flagged: "当前读数为 0，数据层给出待发弹耗尽标记；不代表全车无弹或已经播报。",
    low_flagged: "当前读到待发弹，数据层给出偏少标记；不能据此推算满弹容量或剩余开火次数。",
    observed_count: "当前已读到待发弹，未取得一致的偏少或耗尽标记；不代表弹量充足或已补满。",
  }
  const explanationCode = ground.status === "ready" && Object.prototype.hasOwnProperty.call(explanations, props.explanation?.status || "")
    ? props.explanation!.status : "source_unavailable"
  const rows = [
    { key: "crew", label: "乘员", value: crew },
    { key: "ammo", label: "一级待发弹", value: ammo },
    { key: "stabilizer", label: "火炮稳定器", value: stabilizer },
    { key: "gear", label: "档位", value: gear },
    { key: "speed", label: "车速", value: ready && typeof ground.speed_kmh === "number" && Number.isFinite(ground.speed_kmh)
      ? numberText(ground.speed_kmh, " km/h", 1) : "暂无数据" },
    { key: "rpm", label: "发动机转速", value: ready && typeof ground.engine_rpm === "number"
      && Number.isFinite(ground.engine_rpm) && ground.engine_rpm >= 0 ? numberText(ground.engine_rpm, " rpm") : "暂无数据" },
    { key: "gunner", label: "炮手岗位", value: ready ? groundStationText(ground.gunner_state) : "暂无数据" },
    { key: "driver", label: "驾驶员岗位", value: ready ? groundStationText(ground.driver_state) : "暂无数据" },
    { key: "laser", label: "激光告警器", value: ground.status === "ready" ? groundLaserText(ground.laser_warning_state) : "暂无数据" },
    { key: "track", label: "履带", value: moduleDamage(ground.track_broken, "已断裂") },
    { key: "h_drive", label: "炮塔横向驱动", value: moduleDamage(ground.h_drive_dead, "已损毁") },
    { key: "breach", label: "炮闩", value: moduleDamage(ground.breach_dead, "已损毁") },
    { key: "barrel", label: "炮管", value: moduleDamage(ground.barrel_dead, "已损毁") },
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
      {ground.status === "ready" && ground.laser_warning_state === 1 && (
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
