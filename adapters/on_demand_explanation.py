"""Session-scoped SDK read tool. No model calls, telemetry polling or battle output."""
from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

TOOL_PREFIX = "warthunder_get_current_facts_"
TOOL_DESCRIPTION = (
    "只读当前战争雷霆可信事实。仅在用户明确问当前状态、可用能力或播报策略时调用一次；"
    "不能操控、启用播报或解释未关联的历史事件；未知保持未知。"
)
TOOL_PARAMETERS = {"type": "object", "properties": {
    "view": {"type": "string", "enum": ["status", "capabilities", "output_policy"]}},
    "required": ["view"], "additionalProperties": False}
RESULT_NOTICE = (
    "这是读取时的快照，问当前状态须重新读取；未知不猜，旧值不作当前事实。"
    "开关不是具体事件未播原因；只解释本次返回，简短回答。"
)
MAX_ARGUMENT_BYTES = 128
MAX_RESULT_BYTES = 1200
COOLDOWN_SECONDS = 5.0
TIMEOUT_SECONDS = 2.0


def current_host_role() -> str:
    """Read the authoritative selection, never the last invocation's cached recipient.

    Avoid get_character_data/load_characters: those helpers may repair and save
    malformed configuration. Missing/invalid configuration must fail closed here.
    """
    try:
        from utils.config_manager import get_config_manager

        path = Path(get_config_manager(migrate=False).get_runtime_config_path("characters.json"))
        with path.open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            return ""
        data = json.loads(raw)
        role = data.get("当前猫娘")
        roles = data.get("猫娘")
        if isinstance(role, str) and isinstance(roles, dict) and role in roles:
            return role
    except Exception:
        pass
    return ""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _error(code: str) -> dict[str, Any]:
    # Never echo arguments, exception strings, role names or cached fact values.
    return {"output": {"status": "unavailable", "reason": code, "hint": "请查看插件面板。"},
            "is_error": True, "error": code}


def render_explanation(summary: dict[str, Any], view: str, now: float) -> dict[str, Any]:
    """Select views from P1a, keeping whole fields and their semantic limits."""
    body = {"version": 1, "view": view, "domain": summary["domain"], "status": summary["status"],
            "read_at_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
            "max_source_age_s": 5, "sources": copy.deepcopy(summary["sources"]),
            "limits": list(summary["limits"]), "notice": RESULT_NOTICE}
    if view == "status":
        body["facts"] = [{k: v for k, v in row.items() if k != "source"} for row in summary["facts"]]
    elif view == "capabilities":
        body["capabilities"] = list(summary["capabilities"])
    else:
        body["output"] = dict(summary["output"])
        body["reason_scope"] = "current_policy_only_not_event_cause"
    result = {"output": body, "is_error": False}
    if len(_json(result).encode("utf-8")) <= MAX_RESULT_BYTES:
        return result
    # Never slice JSON, numbers, units or limits. Oversized status becomes unknown.
    if "facts" in body:
        body["facts"] = [{"id": row["id"], "status": "unknown", "value": None} for row in body["facts"]]
        body["status"] = "unavailable"
        body["budget_degraded"] = True
        if len(_json(result).encode("utf-8")) <= MAX_RESULT_BYTES:
            return result
    return _error("RESULT_BUDGET_EXCEEDED")


class OnDemandExplanation:
    def __init__(self, owner: Any, facts: Callable[[], dict[str, Any]], role: Callable[[], str],
                 *, clock: Callable[[], float] = time.monotonic, wall_clock: Callable[[], float] = time.time):
        self.owner, self.facts, self.role = owner, facts, role
        self.clock, self.wall_clock = clock, wall_clock
        self._lock = threading.Lock()
        self._operation = threading.Lock()
        self._query = threading.Lock()
        self._enabled = False
        self._epoch = 0
        self._generation: str | None = None
        self._name: str | None = None
        self._bound_role: str | None = None
        self._status = "disabled"
        self._last_read_at: float | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"enabled": self._enabled, "status": self._status, "role": self._bound_role,
                    "tool_name": self._name, "cleanup_pending": bool(self._name and not self._enabled),
                    "supported": all(callable(getattr(self.owner, name, None)) for name in (
                        "register_llm_tool", "unregister_llm_tool")),
                    "cooldown_seconds": COOLDOWN_SECONDS, "timeout_seconds": TIMEOUT_SECONDS,
                    "max_result_bytes": MAX_RESULT_BYTES}

    def _close(self) -> None:
        with self._lock:
            self._enabled = False
            self._generation = None
            self._epoch += 1

    def _cleanup(self) -> bool:
        with self._lock:
            name = self._name
        if not name:
            return True
        unregister = getattr(self.owner, "unregister_llm_tool", None)
        try:
            if not callable(unregister):
                raise RuntimeError("unsupported")
            unregister(name)
        except Exception:
            with self._lock:
                self._status = "cleanup_required"
            return False
        with self._lock:
            self._name = self._bound_role = None
        return True

    def configure(self, enabled: bool) -> dict[str, Any]:
        if enabled is not True:
            self._close()  # Invalidate even if a concurrent registration is still returning.
        if not self._operation.acquire(blocking=False):
            return {"ok": False, "reason": "BUSY", "on_demand": self.snapshot()}
        try:
            self._close()
            with self._lock:
                epoch = self._epoch
            if not self._cleanup():
                return {"ok": False, "reason": "CLEANUP_REQUIRED", "on_demand": self.snapshot()}
            with self._lock:
                self._status = "disabled"
            if enabled is not True:
                return {"ok": True, "on_demand": self.snapshot()}
            register = getattr(self.owner, "register_llm_tool", None)
            if not self.snapshot()["supported"]:
                with self._lock:
                    self._status = "unsupported"
                return {"ok": False, "reason": "SDK_UNSUPPORTED", "on_demand": self.snapshot()}
            try:
                role = self.role()
            except Exception:
                role = ""
            if not isinstance(role, str) or not role.strip() or len(role) > 80 or any(ord(c) < 32 for c in role):
                with self._lock:
                    self._status = "role_unavailable"
                return {"ok": False, "reason": "ROLE_UNAVAILABLE", "on_demand": self.snapshot()}
            generation = uuid.uuid4().hex[:12]
            name = TOOL_PREFIX + generation
            with self._lock:
                cancelled = epoch != self._epoch
                if not cancelled:
                    self._name, self._bound_role, self._generation = name, role.strip(), generation
                    self._status = "registering"
            if cancelled:
                return {"ok": False, "reason": "DISABLED_DURING_REGISTRATION", "on_demand": self.snapshot()}
            async def handler(**arguments):
                # The current host rejects synchronous dynamic entries. Keep its
                # event loop free so disable/shutdown can invalidate a slow read.
                return await asyncio.to_thread(self.read, generation, arguments)
            try:
                accepted = register(name=name, description=TOOL_DESCRIPTION, parameters=copy.deepcopy(TOOL_PARAMETERS),
                                    handler=handler, role=role.strip(), timeout=TIMEOUT_SECONDS, reply_tail=False)
                if accepted is not True:
                    raise RuntimeError("registration rejected")
            except Exception:
                self._close()
                cleaned = self._cleanup()
                with self._lock:
                    self._status = "registration_failed" if cleaned else "cleanup_required"
                return {"ok": False, "reason": "REGISTRATION_FAILED", "on_demand": self.snapshot()}
            with self._lock:
                current = self._generation == generation
                if current:
                    self._enabled = True
                    self._status = "registration_requested"  # SDK IPC acceptance is not model-wire confirmation.
            if not current:
                self._cleanup()
                return {"ok": False, "reason": "DISABLED_DURING_REGISTRATION", "on_demand": self.snapshot()}
            return {"ok": True, "on_demand": self.snapshot()}
        finally:
            self._operation.release()

    def _current(self, generation: str) -> bool:
        with self._lock:
            return self._enabled and self._generation == generation

    def read(self, generation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self._current(generation):
            return _error("SESSION_DISABLED")
        try:
            valid = (set(arguments) == {"view"} and isinstance(arguments["view"], str)
                     and arguments["view"] in {"status", "capabilities", "output_policy"}
                     and len(_json(arguments).encode("utf-8")) <= MAX_ARGUMENT_BYTES)
        except (ValueError, TypeError, OverflowError):
            valid = False
        if not valid:
            return _error("INVALID_ARGUMENTS")
        if not self._query.acquire(blocking=False):
            return _error("BUSY")
        try:
            if not self._current(generation):
                return _error("SESSION_DISABLED")
            start = self.clock()
            with self._lock:
                if self._last_read_at is not None and start - self._last_read_at < COOLDOWN_SECONDS:
                    return _error("RATE_LIMITED")
                self._last_read_at = start
                bound_role = self._bound_role
            try:
                current_role = self.role()
                if current_role != bound_role:
                    self._close()
                    with self._lock:
                        self._status = "rebind_required"
                    return _error("ROLE_CHANGED")
                result = render_explanation(self.facts(), arguments["view"], self.wall_clock())
            except Exception:
                return _error("FACTS_UNAVAILABLE")
            try:
                role_unchanged = self.role() == bound_role
            except Exception:
                role_unchanged = False
            with self._lock:
                if not self._enabled or self._generation != generation:
                    return _error("SESSION_DISABLED")
                if not role_unchanged:
                    self._enabled = False
                    self._generation = None
                    self._status = "rebind_required"
                    return _error("ROLE_CHANGED")
                if self.clock() - start > TIMEOUT_SECONDS:
                    return _error("READ_TIMEOUT")
                self._status = "active"
                return result
        finally:
            self._query.release()
