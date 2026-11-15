"""Small client helpers for the data-layer /api/identity seam.

The data layer owns raw player identity facts. The plugin only forwards the
manual identity request and exposes a small metadata summary to Hosted UI.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from .text_safety import sanitize_display_name

ActionRequester = Callable[[str, float, dict[str, Any]], dict[str, Any] | None]
ACTION_HEADER = "X-Neko-Warthunder-Action"


def post_action(url: str, timeout: float, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                ACTION_HEADER: "1",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def set_identity(
    base_url: str,
    timeout: float,
    *,
    name: str | None = None,
    clear: bool = False,
    fetcher: ActionRequester = post_action,
) -> dict[str, Any]:
    name = (name or "").strip()
    payload = {"clear": True} if clear or not name else {"name": name}
    data = fetcher(f"{base_url.rstrip('/')}/api/identity", timeout, payload)
    if not isinstance(data, dict) or data.get("error"):
        return {"ok": False, "error": "identity request failed"}
    result = dict(data)
    result.setdefault("ok", True)
    return result


def identity_summary_from_combat(combat: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(combat, dict):
        combat = {}
    self_info = combat.get("self") if isinstance(combat.get("self"), dict) else None
    active_players = combat.get("active_players") if isinstance(combat.get("active_players"), list) else []
    return {
        "player_name": combat.get("player_name"),
        "self": _identity_self_summary(self_info),
        "requested": combat.get("requested"),
        "active_players_count": len(active_players),
        "active_players": _active_player_summaries(active_players),
    }


def _identity_self_summary(self_info: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(self_info, dict):
        return None
    return {
        "name": self_info.get("name"),
        "source": self_info.get("source"),
        "confidence": self_info.get("confidence"),
    }


def _active_player_summaries(active_players: list[Any], *, limit: int = 12) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in active_players[:limit]:
        if not isinstance(item, dict):
            continue
        safe = sanitize_display_name(item.get("name"), fallback="player")
        summary: dict[str, Any] = {
            "display_name": safe.text,
            "selectable": safe.level == "safe",
        }
        if safe.level == "safe":
            summary["name"] = safe.text
        result.append(summary)
    return result
