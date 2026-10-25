"""Exercise documented gate entry points without pytest's package bootstrap."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest


@pytest.mark.parametrize("script,args", [
    ("release_defaults_gate.py", ["--json"]),
    ("free_text_gate.py", ["--json"]),
    ("output_freshness_gate.py", ["--json"]),
    ("replay_gate.py", ["--json"]),
    ("ownership_replay_gate.py", ["--json"]),
    ("deferred_hud_gate.py", ["--json"]),
    ("domain_boundary_gate.py", ["--json"]),
    ("v2_output_policy_gate.py", ["--json"]),
    ("proximity_gate.py", []),
])
def test_gate_cli_works_in_a_fresh_interpreter(script, args, tmp_path):
    tool = pathlib.Path(__file__).resolve().parent.parent / "tools" / script
    completed = subprocess.run(
        [sys.executable, str(tool), *args], cwd=tmp_path, capture_output=True,
        text=True, encoding="utf-8", timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "pass"
