"""Fake clocks for specific plugin modules without touching the standard library."""

from __future__ import annotations

import time
from importlib import import_module
from types import SimpleNamespace


def patch_module_clock(monkeypatch, module, **overrides):
    clock = SimpleNamespace(**{**vars(time), **overrides})
    monkeypatch.setattr(module, "time", clock)


def patch_runtime_clock(monkeypatch, entrypoint, wall_clock):
    """Keep the evaluator and its dashboard projections on the same test clock."""
    patch_module_clock(monkeypatch, entrypoint, time=wall_clock)
    for name in ("dashboard_telemetry", "ground_dashboard", "naval_dashboard"):
        module = import_module(f"{entrypoint.__package__}.adapters.{name}")
        patch_module_clock(monkeypatch, module, time=wall_clock)
