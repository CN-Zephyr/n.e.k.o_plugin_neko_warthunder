import { StatusBadge } from "@neko/plugin-ui"
import { EVENT_LABELS, formatTime, numberText } from "./panel-format"
import type { PanelTone } from "./panel-format"

export type NavalStatusState = {
  status?: string
  battlefield?: "naval"
  personal_combat?: { kills?: number; deaths?: number }
  sample_age_seconds?: number | null
  enemy_count?: number | null
  ally_count?: number | null
  air_contact_count?: number | null
  nearest_type?: string | null
  nearest_distance_m?: number | null
  nearest_bearing_deg?: number | null
}

export type NavalDetectionState = {
  source_status?: string
  sample_age_seconds?: number | null
  map_sample_count?: number | null
  detection_enabled?: boolean
  real_output_enabled?: boolean
  detectors?: { event_id: string; status: string; hits: number; required: number; result?: NavalDetectionResult | null }[]
}

type NavalResultRecord = { stage: string; reason: string; ts?: string; map_sample_count?: number }
type NavalDetectionResult = { candidate?: NavalResultRecord | null; decision?: NavalResultRecord | null; output?: NavalResultRecord | null }

export type NavalInstrumentFields = {
  source_status?: string
  response_age_seconds?: number | null
  sampling_status?: string
  sample_age_seconds?: number | null
  sample_count?: number | null
  sample_life_bound?: boolean
  fields?: { id: string; status: string }[]
}

export type NavalStaticReference = {
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

export const NavalCards = { MapStatusCard, NavalInstrumentFieldCard, NavalStaticReferenceCard, NavalDetectionCard }

function MapStatusCard(props: { naval: NavalStatusState; confirmedNaval: boolean }) {
  const naval = props.naval
  const navalBattlefield = naval.status === "ready" && naval.battlefield === "naval"
  const title = props.confirmedNaval || navalBattlefield ? "海战地图态势" : "地图态势（载具未确认）"
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
        {ready && naval.personal_combat ? <>
          <div className="wt-vehicle-stat"><dt>本局本人击毁</dt><dd>{value(naval.personal_combat.kills, " 次")}</dd></div>
          <div className="wt-vehicle-stat"><dt>本局本人阵亡</dt><dd>{value(naval.personal_combat.deaths, " 次")}</dd></div>
        </> : null}
      </dl>
      <p className="wt-vehicle-note">数量仅指地图已显示单位；图标不能确认舰种，距离不含高度。</p>
      <p className="wt-vehicle-note">{props.confirmedNaval
        ? "兵种字段确认海战；本卡只读，不触发播报。"
        : navalBattlefield ? "舰艇重生点提示当前为海战场景。本舰仪表不可用，专项观察待载具确认。"
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
