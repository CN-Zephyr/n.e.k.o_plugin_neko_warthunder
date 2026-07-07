"""Mode/domain boundary release gate tests."""

from __future__ import annotations

import contextlib
import io
import json


def test_domain_boundary_gate_passes_with_synthetic_states():
    from neko_warthunder.tools import domain_boundary_gate

    result = domain_boundary_gate.run_gate()

    assert result["status"] == "pass"
    assert result["failures"] == []
    assert set(result["results"]["air_emit_events"]) >= {
        "stall_risk",
        "high_aoa",
        "over_g",
        "low_alt_danger",
        "overspeed",
        "low_fuel",
    }
    assert set(result["results"]["ground_emit_events"]) >= {
        "ground_laser_warning",
        "ground_crew_loss",
        "ground_ammo_empty",
        "ground_ammo_low",
    }


def test_domain_boundary_gate_cli_outputs_json():
    from neko_warthunder.tools import domain_boundary_gate

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = domain_boundary_gate.main()

    payload = json.loads(output.getvalue())
    assert rc == 0
    assert payload["status"] == "pass"
    assert payload["failures"] == []
