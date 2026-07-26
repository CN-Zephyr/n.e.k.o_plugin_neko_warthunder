"""Data-layer capture privacy tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_capture_module():
    data_process = Path(__file__).resolve().parents[1] / "data_layer" / "data process"
    spec = importlib.util.spec_from_file_location(
        "wt_capture_test_module",
        data_process / "wt_capture.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capture_advances_chat_cursor_without_persisting_raw_chat(tmp_path):
    module = _load_capture_module()
    raw_chat = "private chat must never be persisted"
    payload = json.dumps(
        [{"id": 7, "sender": "Pilot", "msg": raw_chat}],
        ensure_ascii=False,
    ).encode("utf-8")
    original_fetch = module._fetch_text
    module._fetch_text = lambda _url: (True, 200, payload)
    capturer = module.Capturer(
        "http://127.0.0.1:8111",
        None,
        str(tmp_path),
    )

    try:
        capturer._snap_gamechat()
        summary = capturer.finalize()
    finally:
        module._fetch_text = original_fetch

    assert capturer._last_chat == 7
    assert summary["counts"]["gamechat_seen"] == 1
    assert not list(tmp_path.rglob("gamechat*"))
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl"}
    )
    assert raw_chat not in persisted
    assert "Pilot" not in persisted
