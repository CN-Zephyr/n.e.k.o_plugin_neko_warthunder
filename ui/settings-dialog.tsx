import { Alert, Button, ButtonGroup, Field, Input, Modal, Stack } from "@neko/plugin-ui"
import type { PluginSurfaceProps } from "@neko/plugin-ui"
import type { DashboardState, OnDemandState } from "./panel-state"

export const SettingsDialog = { View: Settings }

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

const onDemandLabels: Record<string, string> = {
  disabled: "已关闭", registering: "正在请求注册", registration_requested: "已请求注册，等待工具调用确认",
  active: "已收到工具调用", unsupported: "当前宿主 SDK 不支持", role_unavailable: "无法确认当前角色",
  registration_failed: "注册失败，继续使用面板", cleanup_required: "已阻止读取，工具清理待重试",
  rebind_required: "角色已变化，需要重新绑定",
}

function Settings({
  settingsOpen, setSettingsOpen, rememberBroadcastChoice, broadcastReady, setDryRun, t, dryRunError,
  onDemand, onDemandAvailable, onDemandBusy, setOnDemand, broadcastFrequency, broadcastCategories,
  setBroadcastFrequency, setBroadcastCategory, resetBroadcastPreferences, playerName, openIdentityModal,
  allyColor, setAllyColor, enemyColor, setEnemyColor, submitFactionColors, factionColorError, openOnboarding,
  broadcastPreferenceError,
}: {
  settingsOpen: boolean
  setSettingsOpen: (open: boolean) => void
  rememberBroadcastChoice: boolean
  broadcastReady: boolean
  setDryRun: (value?: boolean, remember?: boolean) => Promise<void>
  t: PluginSurfaceProps<DashboardState>["t"]
  dryRunError: string
  onDemand: OnDemandState
  onDemandAvailable: boolean
  onDemandBusy: boolean
  setOnDemand: (enabled: boolean) => Promise<void>
  broadcastFrequency: string
  broadcastCategories: Record<string, boolean>
  setBroadcastFrequency: (frequency: string) => Promise<void>
  setBroadcastCategory: (category: string, enabled: boolean) => Promise<void>
  resetBroadcastPreferences: () => Promise<void>
  playerName: string
  openIdentityModal: () => void
  allyColor: string
  setAllyColor: (color: string) => void
  enemyColor: string
  setEnemyColor: (color: string) => void
  submitFactionColors: (reset?: boolean) => Promise<void>
  factionColorError: string
  openOnboarding: () => void
  broadcastPreferenceError: string
}) {
  return (
    <Modal
      open={settingsOpen}
      title="设置"
      onClose={() => { setSettingsOpen(false) }}
      footer={<Button onClick={() => { setSettingsOpen(false) }}>完成</Button>}
    >
      <div className="wt-settings">
        <div className="wt-settings-row">
          <label>
            <input type="checkbox" checked={rememberBroadcastChoice} disabled={!broadcastReady}
              onChange={(event: Event) => { void setDryRun(undefined, (event.target as HTMLInputElement).checked) }} />
            {" "}{t("broadcast.remember_choice")}
          </label>
          <p>{t("broadcast.remember_choice_hint")}</p>
          {dryRunError ? <Alert tone="danger">{dryRunError}</Alert> : null}
        </div>
        <div className="wt-settings-row" role="region" aria-label="会话按需解释">
          <div className="wt-settings-copy">
            <h3>按需解释（本次会话）</h3>
            <p>{onDemandLabels[onDemand.status || "disabled"] || "暂不可用"}{onDemand.role ? ` · 绑定角色：${onDemand.role}` : ""}</p>
            <p>只查当前状态、可用能力和输出策略；不解释具体历史事件，不改变战斗播报。每次重启关闭，换角色需重新绑定。</p>
            <p>启用后工具定义和结果会增加对话 token；普通回答可能按宿主聊天设置发声。5 秒冷却、同时读取 1 次，不自动重试。</p>
          </div>
          <div className="wt-settings-control">
            <Stack>
              <Button disabled={!onDemandAvailable || onDemand.supported === false || onDemandBusy}
                onClick={() => setOnDemand(true)}>{onDemand.enabled || onDemand.status === "rebind_required" ? "重新绑定当前角色" : "本次会话启用并绑定当前角色"}</Button>
              <Button disabled={!onDemandAvailable || onDemandBusy || (!onDemand.enabled && !onDemand.cleanup_pending)}
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
  )
}
