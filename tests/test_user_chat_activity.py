"""Public memory records must reach the final noninterrupting output policy."""
import asyncio
from types import SimpleNamespace

import pytest
from neko_warthunder.adapters.neko_dispatcher import NekoDispatcher
from neko_warthunder.core.contracts import BattleEvent
from test_status_reporting import _plugin_for_action_tests


def _raw(voice=True):
    return {"type": "user_message", "lanlan": "Lanlan", "_ts": 100.0,
            "is_voice": voice, "content": "PRIVATE_TEST_ACTIVITY"}


def _dump_record(payload):
    return SimpleNamespace(dump=lambda: payload)


def _plugin(record):
    plugin = _plugin_for_action_tests()
    plugin._last_user_chat_at = 0.0
    plugin._last_user_context_seen_at = 0.0
    plugin._last_user_chat_mode = "unknown"
    calls = []

    def get(*, bucket_id, limit, timeout):
        calls.append((bucket_id, limit, timeout))
        return [] if record is None else [record]

    plugin.ctx = SimpleNamespace(bus=SimpleNamespace(memory=SimpleNamespace(get=get)))
    return plugin, calls


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("shape", ["dict", "sdk", "host_wrapped", "sdk_wrapped"])
def test_public_records_refresh_mode_without_retaining_content(shape, voice):
    raw = _raw(voice)
    record = {
        "dict": raw,
        "sdk": _dump_record(raw),
        "host_wrapped": _dump_record({"value": _dump_record({"type": "user_message", "raw": raw})}),
        "sdk_wrapped": _dump_record({"value": _dump_record(raw)}),
    }[shape]
    plugin, calls = _plugin(record)

    assert plugin._refresh_user_chat_activity(target_lanlan="Lanlan") == ("voice" if voice else "text")
    assert calls == [("Lanlan", 1, 0.25)]
    assert plugin._last_user_chat_at == 100.0
    assert "PRIVATE_TEST_ACTIVITY" not in repr(vars(plugin))
    assert "PRIVATE_TEST_ACTIVITY" not in repr(plugin.timeline.snapshot())


@pytest.mark.parametrize("timestamp", [float("inf"), -float("inf"), float("nan"), 0, -1, "bad"])
def test_invalid_timestamp_cannot_poison_activity(timestamp):
    plugin, _ = _plugin(_dump_record({**_raw(), "_ts": timestamp}))
    assert plugin._refresh_user_chat_activity(target_lanlan="Lanlan") == "unknown"
    assert plugin._last_user_chat_at == 0.0


@pytest.mark.parametrize("record", [
    None,
    {**_raw(), "lanlan": "Other"},
    {**_raw(), "type": "assistant_message"},
    {**_raw(), "lanlan": "Other", "raw": _raw()},
    {"type": "assistant_message", "raw": _raw()},
])
def test_invalid_or_conflicting_context_is_not_reinterpreted(record):
    plugin, _ = _plugin(record)
    assert plugin._refresh_user_chat_activity(target_lanlan="Lanlan") == "unknown"
    assert plugin._last_user_chat_at == 0.0


@pytest.mark.parametrize("stage", ["get", "dump"])
def test_optional_bus_failures_preserve_previous_activity(stage):
    def fail(**kwargs):
        raise TimeoutError("synthetic failure")

    plugin, _ = _plugin(SimpleNamespace(dump=fail))
    if stage == "get":
        plugin.ctx.bus.memory.get = fail
    plugin._last_user_chat_at = 99.0
    plugin._last_user_chat_mode = "text"
    assert plugin._refresh_user_chat_activity(target_lanlan="Lanlan") == "text"
    assert plugin._last_user_chat_at == 99.0


def test_cyclic_public_wrapper_is_bounded():
    wrapper = {}
    wrapper["value"] = wrapper
    plugin, _ = _plugin(wrapper)
    assert plugin._refresh_user_chat_activity(target_lanlan="Lanlan") == "unknown"


def test_async_owner_loop_does_not_create_a_sync_bus_request():
    plugin, calls = _plugin(_raw())

    async def check():
        return plugin._refresh_user_chat_activity(target_lanlan="Lanlan")

    assert asyncio.run(check()) == "unknown"
    assert calls == []


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("intrusion", ["no_interrupt", "critical_only", "allow_interrupt"])
def test_refreshed_activity_reaches_final_kill_delivery(voice, intrusion):
    plugin, calls = _plugin(_dump_record({"value": _dump_record({"raw": _raw(voice)})}))
    plugin.cfg.target_lanlan = "Lanlan"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin.cfg.dialogue_intrusion_mode = intrusion
    plugin.cfg.output_backpressure_seconds = 0.0
    plugin.cfg.battle_output_quiet_window_seconds = 0.0
    result = NekoDispatcher(plugin, clock=lambda: 105.0).push_event(
        BattleEvent("you_killed", ts=104.0), dry_run=False,
    )
    if intrusion == "allow_interrupt":
        assert calls == []
        assert plugin.pushed_messages[0]["ai_behavior"] == "respond"
    elif voice:
        assert "reason=user_chat_quiet_window" in result
        assert plugin.pushed_messages == []
    else:
        assert plugin.pushed_messages[0]["ai_behavior"] == "read"
        assert plugin.pushed_messages[0]["target_lanlan"] == "Lanlan"


@pytest.mark.parametrize("intrusion", ["no_interrupt", "critical_only"])
def test_critical_alert_preserves_intrusion_policy(intrusion):
    plugin, calls = _plugin(_dump_record(_raw()))
    plugin.cfg.target_lanlan = "Lanlan"
    plugin.cfg.user_chat_quiet_window_seconds = 20.0
    plugin.cfg.dialogue_intrusion_mode = intrusion
    result = NekoDispatcher(plugin, clock=lambda: 105.0).push_event(
        BattleEvent("stall_risk", ts=104.0, level="critical", payload={"domain": "air"}), dry_run=False,
    )
    if intrusion == "no_interrupt":
        assert "reason=user_chat_quiet_window" in result
        assert plugin.pushed_messages == []
    else:
        assert calls == []
        assert plugin.pushed_messages[0]["ai_behavior"] == "respond"
