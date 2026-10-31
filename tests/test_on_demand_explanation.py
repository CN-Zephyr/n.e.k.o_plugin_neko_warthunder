"""Session lifecycle, adversarial calls and actual P1a/dashboard reuse."""
from __future__ import annotations

import asyncio
import copy
import json
import sys
import threading
import types

import pytest
from neko_warthunder.adapters.on_demand_explanation import (
    MAX_RESULT_BYTES,
    OnDemandExplanation,
    current_host_role,
    render_explanation,
)
from test_trusted_facts import make_plugin, summary


@pytest.mark.parametrize("data,expected", [
    ({"当前猫娘": "RoleA", "猫娘": {"RoleA": {}}}, "RoleA"),
    ({"当前猫娘": "Missing", "猫娘": {"RoleA": {}}}, ""),
    ({"当前猫娘": None, "猫娘": {"RoleA": {}}}, ""),
    ({"当前猫娘": "RoleA", "猫娘": []}, ""),
    ([], ""),
])
def test_host_selection_is_read_fresh_without_repair_or_cached_caller(monkeypatch, tmp_path, data, expected):
    path = tmp_path / "characters.json"
    calls = []
    manager = types.SimpleNamespace(get_runtime_config_path=lambda name: path)
    def get_manager(**kwargs):
        calls.append(kwargs)
        return manager
    monkeypatch.setitem(sys.modules, "utils.config_manager", types.SimpleNamespace(get_config_manager=get_manager))
    path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    assert current_host_role() == expected
    assert path.read_bytes() == before and calls == [{"migrate": False}]
    path.write_text('{"当前猫娘":"RoleB","猫娘":{"RoleB":{}}}', encoding="utf-8")
    assert current_host_role() == "RoleB"
    path.write_text("invalid-private-sentinel", encoding="utf-8")
    assert current_host_role() == ""
    path.unlink()
    assert current_host_role() == ""


def setup(monkeypatch, domain="ground"):
    plugin, moment = make_plugin(monkeypatch, domain)
    handlers, registrations, removed = {}, [], []
    role = ["SyntheticRole"]
    clock = [100.0]

    def register(**kwargs):
        registrations.append(kwargs)
        handlers[kwargs["name"]] = kwargs["handler"]
        return True

    def unregister(name):
        removed.append(name)
        handlers.pop(name, None)
        return True

    plugin.register_llm_tool, plugin.unregister_llm_tool = register, unregister
    controller = OnDemandExplanation(plugin, lambda: summary(plugin), lambda: role[0],
        clock=lambda: clock[0], wall_clock=lambda: moment[0])
    plugin._on_demand = controller
    return types.SimpleNamespace(plugin=plugin, controller=controller, handlers=handlers, role=role, clock=clock,
                                 moment=moment, registrations=registrations, removed=removed)


def enable(env):
    result = env.controller.configure(True)
    assert result["ok"] is True
    handler = env.handlers[result["on_demand"]["tool_name"]]
    assert asyncio.iscoroutinefunction(handler)
    return lambda **args: asyncio.run(handler(**args))


def test_default_closed_registers_nothing_and_ignores_saved_configuration(monkeypatch):
    env = setup(monkeypatch)
    assert env.controller.snapshot()["enabled"] is False
    for _ in range(5):
        asyncio.run(env.plugin.dashboard_context())
    assert env.registrations == [] and env.handlers == {}
    assert env.plugin.config_updates == [] and not env.plugin._runtime_state_path.exists()


@pytest.mark.parametrize("domain", ["air", "ground", "heli", "naval"])
@pytest.mark.parametrize("view", ["status", "capabilities", "output_policy"])
def test_views_reuse_real_summary_and_keep_battle_output_untouched(monkeypatch, domain, view):
    env = setup(monkeypatch, domain)
    before_state = copy.deepcopy(env.plugin.state)
    before_cfg = copy.deepcopy(env.plugin.cfg.to_dict())
    before_timeline = env.plugin.timeline.snapshot()
    call = enable(env)
    reg = env.registrations[0]
    assert reg["role"] == env.role[0] and reg["timeout"] == 2 and reg["reply_tail"] is False
    assert reg["parameters"]["additionalProperties"] is False
    result = call(view=view)
    assert result["is_error"] is False and result["output"]["domain"] == domain
    assert result["output"]["view"] == view
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= MAX_RESULT_BYTES
    assert env.controller.snapshot()["status"] == "active"
    if view == "status":
        assert result["output"]["facts"] == [{k:v for k,v in row.items() if k != "source"}
                                              for row in summary(env.plugin)["facts"]]
    elif view == "output_policy":
        assert result["output"]["output"] == summary(env.plugin)["output"]
        assert result["output"]["reason_scope"] == "current_policy_only_not_event_cause"
    else:
        assert result["output"]["capabilities"] == summary(env.plugin)["capabilities"]
    assert env.plugin.state == before_state and env.plugin.cfg.to_dict() == before_cfg
    assert env.plugin.timeline.snapshot() == before_timeline
    assert env.plugin.pushed_messages == env.plugin.config_updates == []


@pytest.mark.parametrize("args", [{}, {"view":"history"}, {"view":[]}, {"view":True}, {"view":None},
    {"view":"status","enabled":True}, {"view":"status","role":"forged"},
    {"view":"status","_ctx":{"lanlan_name":"forged"}}, {"view":"private-sentinel"*1000}])
def test_rejects_unknown_large_and_forged_inputs_without_echoing_them(monkeypatch, args):
    env = setup(monkeypatch)
    call = enable(env)
    response = call(**args)
    assert response["error"] == "INVALID_ARGUMENTS"
    assert "private-sentinel" not in json.dumps(response)
    assert call(view="status")["is_error"] is False  # Invalid arguments do not read or spend cooldown.


def test_global_cooldown_survives_rebinding_and_is_shared_by_views(monkeypatch):
    env = setup(monkeypatch)
    first = enable(env)
    assert first(view="status")["is_error"] is False
    assert first(view="capabilities")["error"] == "RATE_LIMITED"
    env.clock[0] += 4.999
    assert first(view="output_policy")["error"] == "RATE_LIMITED"
    second = enable(env)
    assert env.registrations[0]["name"] != env.registrations[1]["name"]
    assert first(view="status")["error"] == "SESSION_DISABLED"
    assert second(view="status")["error"] == "RATE_LIMITED"
    env.clock[0] += 0.001
    assert second(view="status")["is_error"] is False


@pytest.mark.parametrize("role", [None, "", " ", "x"*81, "bad\nrole"])
def test_unknown_role_never_falls_back_to_global(monkeypatch, role):
    env = setup(monkeypatch)
    env.role[0] = role
    result = env.controller.configure(True)
    assert result["reason"] == "ROLE_UNAVAILABLE"
    assert env.registrations == [] and not result["on_demand"]["enabled"]


def test_role_change_blocks_read_and_requires_explicit_rebind(monkeypatch):
    env = setup(monkeypatch)
    old = enable(env)
    env.role[0] = "NewRole"
    assert old(view="status")["error"] == "ROLE_CHANGED"
    assert env.controller.snapshot()["status"] == "rebind_required"
    assert old(view="status")["error"] == "SESSION_DISABLED"
    new = enable(env)
    assert env.registrations[-1]["role"] == "NewRole"
    env.clock[0] += 5
    assert new(view="status")["is_error"] is False
    assert old(view="status")["error"] == "SESSION_DISABLED"


@pytest.mark.parametrize("invalidator,error", [("disable","SESSION_DISABLED"), ("rebind","SESSION_DISABLED"),
                                                ("role","ROLE_CHANGED"), ("timeout","READ_TIMEOUT")])
def test_late_results_do_not_escape_after_invalidation(monkeypatch, invalidator, error):
    env = setup(monkeypatch)
    call = enable(env)
    real = env.controller.facts

    def delayed():
        result = real()
        if invalidator == "disable":
            env.controller.configure(False)
        elif invalidator == "rebind":
            enable(env)
        elif invalidator == "role":
            env.role[0] = "OtherRole"
        else:
            env.clock[0] += 2.001
        return result

    env.controller.facts = delayed
    response = call(view="status")
    assert response["error"] == error and "facts" not in response["output"]


def test_nonblocking_single_concurrent_read_and_shutdown_invalidation(monkeypatch):
    env = setup(monkeypatch)
    call = enable(env)
    entered, release = threading.Event(), threading.Event()
    result = []
    real = env.controller.facts

    def slow():
        entered.set()
        assert release.wait(3)
        return real()

    env.controller.facts = slow
    worker = threading.Thread(target=lambda: result.append(call(view="status")))
    worker.start()
    try:
        assert entered.wait(3)
        assert call(view="capabilities")["error"] == "BUSY"
        env.controller.configure(False)
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and result[0]["error"] == "SESSION_DISABLED"


def test_disable_during_registration_cannot_publish_a_live_binding(monkeypatch):
    env = setup(monkeypatch)
    captured = []

    def register(**kwargs):
        captured.append(kwargs["handler"])
        assert env.controller.configure(False)["ok"] is False  # Invalidates immediately, operation is busy.
        return True

    env.plugin.register_llm_tool = register
    assert env.controller.configure(True)["reason"] == "DISABLED_DURING_REGISTRATION"
    assert asyncio.run(captured[0](view="status"))["error"] == "SESSION_DISABLED"
    assert env.controller.snapshot()["enabled"] is False


def test_disable_while_role_lookup_is_pending_cannot_enable_later(monkeypatch):
    env = setup(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    def slow_role():
        entered.set()
        assert release.wait(3)
        return "SyntheticRole"
    env.controller.role = slow_role
    results = []
    worker = threading.Thread(target=lambda: results.append(env.controller.configure(True)))
    worker.start()
    try:
        assert entered.wait(3)
        env.controller.configure(False)
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert results[0]["reason"] == "DISABLED_DURING_REGISTRATION"
    assert env.registrations == [] and env.controller.snapshot()["enabled"] is False


def test_registration_partial_failure_and_cleanup_failure_stay_closed(monkeypatch):
    env = setup(monkeypatch)
    captured = []

    def register(**kwargs):
        captured.append(kwargs["handler"])
        raise RuntimeError("private-sentinel")

    def unregister(_):
        raise RuntimeError("private-sentinel")

    env.plugin.register_llm_tool, env.plugin.unregister_llm_tool = register, unregister
    result = env.controller.configure(True)
    assert result["reason"] == "REGISTRATION_FAILED" and result["on_demand"]["status"] == "cleanup_required"
    assert "private-sentinel" not in json.dumps(result)
    assert asyncio.run(captured[0](view="status"))["error"] == "SESSION_DISABLED"
    assert env.controller.configure(True)["reason"] == "CLEANUP_REQUIRED"
    env.plugin.unregister_llm_tool = lambda _: True
    assert env.controller.configure(False)["ok"] is True
    assert env.controller.snapshot()["status"] == "disabled"


def test_old_sdk_gracefully_refuses_enable_without_touching_facts(monkeypatch):
    env = setup(monkeypatch)
    env.plugin.register_llm_tool = None
    env.controller.facts = lambda: pytest.fail("must not read")
    assert env.controller.configure(True)["reason"] == "SDK_UNSUPPORTED"
    assert env.controller.configure(False)["ok"] is True


@pytest.mark.parametrize("change", ["stale", "replay", "dead", "unknown_age", "new_life"])
def test_each_call_reprojects_invalid_sources_and_never_reuses_old_values(monkeypatch, change):
    env = setup(monkeypatch, "naval" if change == "new_life" else "ground")
    call = enable(env)
    assert any(row["value"] is not None for row in call(view="status")["output"]["facts"])
    env.clock[0] += 5
    if change == "stale":
        env.moment[0] += 6
    elif change in {"replay","dead"}:
        setattr(env.plugin.state, change, True)
    elif change == "unknown_age":
        env.plugin.state.age_seconds = None
    else:
        env.plugin.state.life_index = 2
    result = call(view="status")
    assert result["is_error"] is False
    assert all(row["value"] is None for row in result["output"]["facts"])


def test_budget_downgrades_whole_fields_instead_of_slicing_json(monkeypatch):
    env = setup(monkeypatch)
    card = summary(env.plugin)
    for fact in card["facts"]:
        fact["value"] = 10**1000
    rendered = render_explanation(card, "status", 1000)
    assert len(json.dumps(rendered,ensure_ascii=False,separators=(",",":")).encode()) <= MAX_RESULT_BYTES
    assert rendered["output"]["budget_degraded"] is True
    assert all(row["value"] is None for row in rendered["output"]["facts"])
    assert rendered["output"]["limits"] == card["limits"]
    assert "".join("9" for _ in range(100)) not in json.dumps(rendered)


def test_facts_failure_does_not_echo_exceptions_or_retry(monkeypatch):
    env = setup(monkeypatch)
    call = enable(env)

    def failed():
        raise RuntimeError("private-sentinel")

    env.controller.facts = failed
    result = call(view="status")
    assert result["error"] == "FACTS_UNAVAILABLE" and "private-sentinel" not in json.dumps(result)
    assert call(view="status")["error"] == "RATE_LIMITED"


def test_panel_entry_uses_same_session_controller_and_never_persists(monkeypatch):
    env = setup(monkeypatch)
    before = copy.deepcopy(env.plugin.cfg.to_dict())
    enabled = asyncio.run(env.plugin.set_on_demand_explanation(enabled=True))
    assert enabled["ok"] is True
    assert asyncio.run(env.plugin.dashboard_context())["on_demand"]["enabled"] is True
    assert asyncio.run(env.plugin.set_on_demand_explanation(enabled=False))["ok"] is True
    assert env.plugin.cfg.to_dict() == before and env.plugin.config_updates == env.plugin.pushed_messages == []
    assert not env.plugin._runtime_state_path.exists()
