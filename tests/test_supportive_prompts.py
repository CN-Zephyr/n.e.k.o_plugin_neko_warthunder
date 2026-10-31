"""Supportive tone survives final delivery without weakening output gates."""

from types import SimpleNamespace

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.core.contracts import BattleEvent, WtConfig
from neko_warthunder.core.instructions import WT_CONTEXT_INSTRUCTIONS, WT_RESTORE_INSTRUCTIONS


class RecordingPlugin:
    def __init__(self):
        self.cfg = WtConfig()
        self.cfg.dialogue_intrusion_mode = "allow_interrupt"
        self.calls = []

    def push_message(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.parametrize("domain", ["air", "ground", "heli", "naval"])
@pytest.mark.parametrize("event_id,extra", [
    ("spawn", {}),
    ("you_died", {"cause": "destroyed"}),
    ("you_killed", {}),
    ("you_killed", {"trade_death": True}),
    ("battle_end", {"result_kind": "victory"}),
    ("battle_end", {"result_kind": "defeat"}),
    ("battle_end", {"result_kind": "unknown"}),
])
def test_final_respond_delivery_carries_supportive_boundary(domain, event_id, extra):
    plugin = RecordingPlugin()
    result = NekoDispatcher(plugin).push_event(
        BattleEvent(event_id, payload={"domain": domain, **extra}), dry_run=False,
    )

    assert result.startswith("pushed(")
    call, = plugin.calls
    assert call["ai_behavior"] == "respond"
    text = call["parts"][0]["text"]
    assert "轻松陪伴，不责怪、不嘲讽、不催战绩" in text
    assert "插件不指定情绪或措辞" not in text
    assert "不反问、不续聊" in text
    assert "28字内" in text
    assert "calm, non-judgmental" in call["metadata"]["reply_style_contract"]
    if event_id == "you_died":
        assert "不评价操作" in text
        assert "不复盘" in text
    if event_id == "battle_end" and extra["result_kind"] == "unknown":
        assert "不误判胜负" in text


@pytest.mark.parametrize("event_id,expected,level", [
    ("stall_risk", "加速改出", "critical"),
    ("high_aoa", "松杆改出", "critical"),
    ("over_g", "松杆回正", "critical"),
    ("low_alt_danger", "立即拉起", "critical"),
    ("overspeed", "收油减速", "critical"),
    ("ground_laser_warning", "找掩体", "critical"),
    ("ground_crew_loss", "注意掩护", "warning"),
    ("ground_gunner_disabled", "炮手失能", "warning"),
    ("ground_driver_disabled", "机动受限", "warning"),
    ("ground_ammo_empty", "一级弹药已空", "warning"),
    ("ground_ammo_low", "待发弹偏少", "warning"),
])
def test_opt_in_direct_lines_keep_facts_and_actions_without_panic(event_id, expected, level):
    plugin = RecordingPlugin()
    # Explicitly opt in only in this isolated test; production defaults stay off.
    plugin.cfg.plugin_owned_blind_output_enabled = True
    plugin.cfg.ground_status_real_output_enabled = True
    result = NekoDispatcher(plugin).push_event(BattleEvent(event_id, level=level), dry_run=False)

    assert result.startswith("pushed(")
    call, = plugin.calls
    assert call["ai_behavior"] == "blind"
    text = call["parts"][0]["text"]
    assert expected in text
    assert len(text) <= 28
    for pressure in ("要撞地", "别硬拼", "别贪", "快失速", "控节奏"):
        assert pressure not in text


def test_persistent_context_limits_persona_and_preserves_exit():
    assert "即使人设傲娇" in WT_CONTEXT_INSTRUCTIONS
    assert "不把毒舌、嫌弃或贬低对准玩家" in WT_CONTEXT_INSTRUCTIONS
    assert "不擅自复盘" in WT_CONTEXT_INSTRUCTIONS
    assert "不命令玩家冷静" in WT_CONTEXT_INSTRUCTIONS
    assert "不为柔和语气省略必要动作" in WT_CONTEXT_INSTRUCTIONS
    assert "{MASTER_NAME}" in WT_CONTEXT_INSTRUCTIONS
    assert "恢复日常聊天状态" in WT_RESTORE_INSTRUCTIONS


def test_text_chat_passive_event_keeps_supportive_boundary_without_proactive_reply():
    plugin = RecordingPlugin()
    plugin.cfg.dialogue_intrusion_mode = "critical_only"
    plugin._last_user_chat_at = 100.0
    plugin._last_user_chat_mode = "text"
    plugin.ctx = SimpleNamespace(_current_lanlan="test-role")
    result = NekoDispatcher(plugin, clock=lambda: 101.0).push_event(
        BattleEvent("you_killed", ts=101.0, payload={"domain": "air"}), dry_run=False,
    )

    assert result.startswith("pushed(")
    call, = plugin.calls
    assert call["ai_behavior"] == "read"
    assert "不责怪、不嘲讽、不催战绩" in call["parts"][0]["text"]
    assert "不要为它主动开口" in call["parts"][0]["text"]
