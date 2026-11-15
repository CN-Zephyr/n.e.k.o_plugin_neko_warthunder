"""Read the current role from compatible N.E.K.O hosts without changing their config."""

from __future__ import annotations

import json
from pathlib import Path


def current_host_role() -> str:
    """Read the authoritative selection, never the last invocation's cached recipient.

    Avoid get_character_data/load_characters: those helpers may repair and save
    malformed configuration. Missing/invalid configuration must fail closed here.
    """
    try:
        from utils.config_manager import get_config_manager

        manager = get_config_manager(migrate=False)
        config_path = getattr(manager, "get_runtime_config_path", None)
        if not callable(config_path):
            return ""
        path = Path(config_path("characters.json"))
        with path.open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            return ""
        data = json.loads(raw)
        role = data.get("当前猫娘")
        roles = data.get("猫娘")
        if isinstance(role, str) and isinstance(roles, dict) and role in roles:
            return role if role.strip() else ""
    except Exception:
        pass
    return ""
