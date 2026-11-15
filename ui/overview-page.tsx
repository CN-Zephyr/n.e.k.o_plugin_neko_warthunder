import { Alert, Button, RefreshButton, StatusBadge } from "@neko/plugin-ui"
import { DOMAIN_LABELS, SCENARIO_LABELS, mappedText, text } from "./panel-display"
import type { ActivityItem, DashboardState, GroundStatusState, PanelSummary } from "./panel-state"
import type { PanelTone } from "./panel-format"
import { VehicleCards } from "./vehicle-cards"

export const OverviewPage = { View: Overview }

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

function Overview({
  state, summary, groundForDisplay, playerName, activityItems, dryRunError, dialoguePolicyError,
  openIdentityModal, setDryRun, broadcastReady,
}: {
  state: DashboardState
  summary: PanelSummary
  groundForDisplay: GroundStatusState
  playerName: string
  activityItems: ActivityItem[]
  dryRunError: string
  dialoguePolicyError: string
  openIdentityModal: () => void
  setDryRun: (value: boolean) => Promise<void>
  broadcastReady: boolean
}) {
  const detectOnly = state.dry_run !== false
  const currentBattleStatus = battleStatus(state)
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
        disabled={!broadcastReady}
        onClick={() => setDryRun(!detectOnly)}
      >
        {detectOnly ? "开启战斗播报" : "停止战斗播报"}
      </Button>
    </div>
  )

  return (
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

          <div className="wt-identity">
            <div>
              <p className="wt-identity-name">{playerName || "尚未设置战雷游戏昵称"}</p>
              <p className="wt-identity-meta">{playerName ? "已保存，等待本局身份匹配" : "设置后可识别自己发送的固定无线电消息"}</p>
            </div>
            <Button className="wt-link-action" onClick={openIdentityModal}>{playerName ? "修改" : "设置"}</Button>
          </div>
          <VehicleCards.VehicleStatusCards state={state} ground={groundForDisplay} dryRun={detectOnly} />
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

}
