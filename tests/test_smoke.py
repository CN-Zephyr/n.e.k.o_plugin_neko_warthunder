"""Repository smoke tests for the standalone plugin package."""

from __future__ import annotations

import pathlib
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


def test_hosted_ui_panel_groups_operator_state_in_chinese():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    for section in ["连接状态", "战场状态", "飞行诊断", "起飞保护", "接近感知", "安全控制", "最近决策", "最近输出", "玩家身份"]:
        assert section in panel

    for label in [
        "模拟模式",
        "场景",
        "风险等级",
        "雷达高度",
        "当前 flags",
        "当前压制",
        "接近事件数",
        "任务目标",
        "最近目标网格",
        "手动暂停",
        "自动暂停",
        "失败次数",
        "当前玩家",
    ]:
        assert label in panel


def test_hosted_ui_panel_keeps_existing_actions_available():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")

    for action_id in ["set_dry_run", "set_identity", "pause", "resume", "test_say"]:
        assert action_id in panel

    for label in ["急停", "恢复", "测试开口", "刷新状态", "保存", "清除"]:
        assert label in panel
