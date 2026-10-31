"""Client helper for the data-layer /api/faction_colors seam.

War Thunder lets players recolor allies/enemies on the minimap, and 8111
/map_obj.json only exposes colors. The plugin owns the configured colors and
forwards them to the data layer, which classifies map objects by them.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from .identity_client import IdentityFetcher, fetch_identity


def build_faction_colors_url(base_url: str, *, ally: str, enemy: str) -> str:
    query = urllib.parse.urlencode({"ally": ally, "enemy": enemy})
    return f"{base_url.rstrip('/')}/api/faction_colors?{query}"


def set_faction_colors(
    base_url: str,
    timeout: float,
    *,
    ally: str,
    enemy: str,
    fetcher: IdentityFetcher = fetch_identity,
) -> dict[str, Any]:
    data = fetcher(build_faction_colors_url(base_url, ally=ally, enemy=enemy), timeout)
    if not isinstance(data, dict) or data.get("error"):
        return {"ok": False, "error": "faction colors request failed"}
    result = dict(data)
    result.setdefault("ok", True)
    return result
