"""Read and update plugin preferences stored outside the installed package."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_STATE_LOCK = threading.Lock()


def load_runtime_state(path: Path, legacy: Path, warn: Callable[[str], Any] | None) -> dict[str, Any]:
    for candidate in dict.fromkeys((path, legacy)):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            if warn is not None:
                warn(f"runtime state load failed: {type(exc).__name__}")
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def save_runtime_state(
    path: Path, load_current: Callable[[], dict[str, Any]], patch: dict[str, Any],
) -> None:
    # Keep the read, merge and atomic replacement under the same lock.
    with _STATE_LOCK:
        current = load_current()
        current.update(patch)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
