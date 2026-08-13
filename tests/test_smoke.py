"""Repository smoke tests for the standalone plugin package."""

from __future__ import annotations

import json
import pathlib
import string
import tomllib

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _manifest() -> dict:
    return tomllib.loads((_ROOT / "plugin.toml").read_text(encoding="utf-8"))


def test_plugin_manifest_declares_expected_entrypoint_and_runtime():
    manifest = _manifest()

    assert manifest["plugin"]["id"] == "neko_warthunder"
    assert manifest["plugin"]["entry"] == "plugin.plugins.neko_warthunder:NekoWarthunderPlugin"
    assert manifest["plugin_runtime"]["enabled"] is True
    assert manifest["neko_warthunder"]["dry_run"] is True


def test_plugin_manifest_declares_hosted_ui_surface_and_files_exist():
    manifest = _manifest()
    panels = manifest["plugin"]["ui"]["panel"]

    assert manifest["plugin"]["ui"]["enabled"] is True
    assert panels == [
        {
            "id": "main",
            "title": "战雷猫娘副驾驶",
            "entry": "ui/panel.tsx",
            "context": "dashboard",
            "permissions": ["state:read", "action:call"],
        }
    ]
    assert (_ROOT / "__init__.py").is_file()
    assert (_ROOT / "ui" / "panel.tsx").is_file()


def test_plugin_manifest_locales_have_matching_keys_and_placeholders():
    manifest = _manifest()
    i18n = manifest["plugin"]["i18n"]
    locale_dir = _ROOT / i18n["locales_dir"]
    locale_names = {"en", "ja", "ko", "zh-CN", "zh-TW", "ru", "pt", "es"}
    formatter = string.Formatter()

    assert i18n["default_locale"] == "zh-CN"
    assert {path.stem for path in locale_dir.glob("*.json")} == locale_names

    bundles = {
        locale: json.loads((locale_dir / f"{locale}.json").read_text(encoding="utf-8"))
        for locale in locale_names
    }
    expected_keys = set(bundles[i18n["default_locale"]])
    assert expected_keys == {"name", "description"}

    for locale, bundle in bundles.items():
        assert set(bundle) == expected_keys, locale
        for key, value in bundle.items():
            assert isinstance(value, str) and value.strip(), f"{locale}:{key}"
            placeholders = {field for _, field, _, _ in formatter.parse(value) if field}
            default_placeholders = {
                field
                for _, field, _, _ in formatter.parse(bundles[i18n["default_locale"]][key])
                if field
            }
            assert placeholders == default_placeholders, f"{locale}:{key}"


def test_hosted_ui_panel_groups_operator_state_in_chinese():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    for section in ["当前战局", "最近活动", "活动记录", "播报插话规则", "运行链路", "高级详情"]:
        assert section in panel

    for label in [
        "战雷游戏昵称",
        "播报插话规则",
        "战雷客户端",
        "数据服务",
        "插件识别",
        "输出策略",
        "猫娘接收",
        "播报未启动",
        "急停",
        "安全保护",
    ]:
        assert label in panel


def test_hosted_ui_panel_serializes_background_refresh_and_handles_rejections():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    assert "let refreshInFlight = false" in panel
    assert "await props.api.refresh()" in panel
    assert "props.api.refresh().catch(() => undefined)" in panel
    assert "setTimeout(() => { void tick() }" in panel


def test_hosted_ui_panel_keeps_existing_actions_available():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    for action_id in [
        "set_dry_run",
        "set_dialogue_intrusion_mode",
        "set_broadcast_frequency",
        "set_broadcast_category",
        "reset_broadcast_preferences",
        "set_identity",
        "complete_onboarding",
        "pause",
        "resume",
        "test_say",
    ]:
        assert action_id in panel

    for label in [
        "开启战斗播报",
        "输出模式",
        "战斗播报",
        "急停",
        "恢复",
        "测试开口",
        "不打断当前对话",
        "仅危急情况可打断",
        "允许打断当前对话",
        "保存昵称",
        "清除昵称",
        "播报频率",
        "播报内容",
        "一般安全提醒",
        "固定无线电互动",
        "危急安全提醒和阵亡提醒始终开启",
        "恢复推荐播报设置",
        "不影响昵称、插话规则和播报开关",
    ]:
        assert label in panel

    assert 'props.api.call("set_broadcast_frequency", { frequency })' in panel
    assert 'props.api.call("set_broadcast_category", { category, enabled })' in panel
    assert 'props.api.call("reset_broadcast_preferences", {})' in panel
    assert 'const enabled = broadcastCategories[option.value] !== false' in panel


def test_hosted_ui_panel_keeps_normal_and_emergency_broadcast_controls_visible():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    assert 'const detectOnly = state.dry_run !== false' in panel
    assert "onClick={() => setDryRun(!detectOnly)}" in panel
    assert '{detectOnly ? "开启战斗播报" : "停止战斗播报"}' in panel
    assert 'const broadcastPaused = summary.kind === "paused" || summary.kind === "safety"' in panel
    assert 'className="wt-emergency-control"' in panel
    assert 'className="wt-emergency-stop"' in panel
    assert 'ActionButton action={pauseAction} actionId="pause" tone="danger">急停</ActionButton>' in panel
    assert 'ActionButton action={resumeAction} actionId="resume" tone="success">恢复</ActionButton>' in panel
    assert "立即暂停新的战斗播报" in panel
    assert 'className="wt-mode-toggle"' not in panel
    assert 'className="wt-test-sound-action"' in panel
    assert 'RefreshButton label="刷新状态"' in panel
    assert "重新检测" not in panel

    status_actions = panel.split("const statusActions = (", 1)[1].split("const bottomBar = (", 1)[0]
    diagnostics = panel.split("const diagnostics = (", 1)[1]
    assert "test_say" not in status_actions
    assert "pauseAction" not in status_actions
    assert "resumeAction" not in status_actions
    assert status_actions.index("刷新状态") < status_actions.index("开启战斗播报")
    assert "停止战斗播报" in status_actions
    assert 'className="wt-diagnostics-summary"' in diagnostics
    assert 'RefreshButton label="重新检查"' in diagnostics
    assert 'useClipboard()' in panel
    assert 'buildSafeDiagnosticSummary(state)' in panel
    assert 'copyDiagnosticSummary()' in diagnostics
    assert '"复制诊断摘要"' in diagnostics
    assert "不含昵称、聊天、HUD、目标、载具、URL、PID、错误原文" in panel
    safe_summary = panel.split("function buildSafeDiagnosticSummary", 1)[1].split("type AdvancedDetailItem", 1)[0]
    for unsafe_field in ["identity", "player_name", "last_error", "vehicle_type", "latest_proximity", "nearest_ground_target"]:
        assert unsafe_field not in safe_summary
    assert 'className="wt-diagnostic-check"' in diagnostics
    assert 'className="wt-advanced-details"' in diagnostics
    assert "系统已待命，等待进入战局" in panel
    assert "测试开口" in diagnostics
    advanced_safety = diagnostics.split('title="安全控制"', 1)[1].split("/>", 1)[0]
    assert "ButtonGroup" not in advanced_safety
    assert "pauseAction" not in advanced_safety
    assert "resumeAction" not in advanced_safety


def test_hosted_ui_panel_follows_theme_and_keeps_footer_in_layout():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    assert "color-scheme: light dark" in panel
    assert "@media (prefers-color-scheme: dark)" in panel
    assert "grid-template-rows: 72px minmax(0, 1fr) auto" in panel
    assert ".wt-content { min-height: 0; overflow-x: hidden; overflow-y: auto" in panel
    assert ".wt-bottom { position: fixed" not in panel
    assert "@media (max-width: 760px)" in panel


def test_hosted_ui_panel_exposes_safe_filterable_activity_history():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    assert 'recent_activity?: ObserveRecord[]' in panel
    assert 'const allActivityItems = buildActivityItems(state, 20)' in panel
    assert 'activeTab === "activity"' in panel
    assert '>活动</button>' in panel
    assert 'aria-label="筛选活动记录"' in panel
    for label in ["已提交", "仅记录", "未输出"]:
        assert label in panel
    for explanation in ["已按偏好关闭", "对话保护中", "重复提醒已合并", "回放静默"]:
        assert explanation in panel
    assert "不保存玩家昵称、聊天或 HUD 原文" in panel


def test_hosted_ui_panel_has_reopenable_first_run_onboarding_with_identity_setup():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    assert 'const onboardingRequired = state.onboarding?.required === true' in panel
    assert 'useState(onboardingRequired)' in panel
    assert 'props.api.call("complete_onboarding", { skipped })' in panel
    assert "if (!onboardingRequired || onboardingAutoOpened) return" in panel
    assert 'className="wt-settings-trigger"' in panel
    assert 'aria-label="设置"' in panel
    assert 'title="设置"' in panel
    assert '重新查看教程' in panel
    assert 'title={`新手教程 · ${onboardingTitles[onboardingStep]}`}' in panel
    assert 'const onboardingTitles = ["设置昵称", "认识按钮"]' in panel
    assert "先设置你的战雷游戏昵称" in panel
    assert 'label="战雷游戏昵称"' in panel
    assert "保存昵称并继续" in panel
    assert "saveIdentityAndContinueOnboarding" in panel
    assert "常用按钮都在固定位置" in panel
    assert "开启 / 停止战斗播报" in panel
    assert "急停 / 恢复" in panel
    assert "测试开口" in panel
    assert "刷新状态" in panel
    assert "右上角齿轮" in panel
    assert "进入任意一局 War Thunder" not in panel
    assert "确认插件识别到第一条活动" not in panel


def test_hosted_ui_panel_uses_truthful_output_and_identity_language():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    assert "已交给猫娘" in panel
    assert "已播报" not in panel
    assert "已开口" not in panel
    assert "不是邮箱、数字账号 ID 或 Steam 名称" in panel
    assert "不会选择其他玩家" in panel
    assert "function safetyIsTripped" in panel
    assert 'state.safety?.status === "tripped"' in panel
    assert 'dataLayerMode === "starting"' in panel
    assert "正在准备战雷数据服务" in panel
