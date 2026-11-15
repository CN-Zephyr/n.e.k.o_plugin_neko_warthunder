export const PANEL_STYLES = `
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
