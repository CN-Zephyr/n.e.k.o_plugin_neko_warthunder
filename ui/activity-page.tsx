import { StatusBadge } from "@neko/plugin-ui"
import type { ActivityItem } from "./panel-state"

export const ActivityPage = { View: Activity }

function Activity({ activityFilter, setActivityFilter, items }: {
  activityFilter: string
  setActivityFilter: (filter: string) => void
  items: ActivityItem[]
}) {
  const filteredActivityItems = activityFilter === "all" ? items : items.filter(
    (item) => item.kind === activityFilter || (activityFilter === "suppressed" && item.kind === "failed"),
  )
  const activityFilters = [
    { value: "all", label: "全部" },
    { value: "delivered", label: "已提交" },
    { value: "recorded", label: "仅记录" },
    { value: "suppressed", label: "未输出" },
  ]
  return (
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

}
