"""Output freshness release-gate tests."""

from __future__ import annotations

import contextlib
import io
import json


def test_output_freshness_gate_passes_required_contracts():
    from neko_warthunder.tools import output_freshness_gate

    result = output_freshness_gate.run_gate()

    assert result["status"] == "pass"
    assert result["failures"] == []
    assert [case["name"] for case in result["cases"]] == [
        "real_push_contract",
        "expired_event_drop",
        "backpressure_lower_priority",
        "higher_priority_preempts",
        "death_bypasses_backpressure",
        "critical_safety_bypasses_backpressure",
        "dry_run_side_effect_free",
        "context_target_session",
    ]
    real_push = result["cases"][0]
    assert real_push["event_age_seconds"] == 3.0
    assert real_push["event_expires_at"] == 101.0
    assert real_push["target_lanlan"] == "Lanlan"
    assert real_push["reply_contract"] == "short_tts_line"
    assert real_push["replace_pending"] is True
    assert real_push["interrupt_battle_event"] is True
    assert real_push["interrupt_pending"] is True
    assert real_push["reply_style_contract"]
    assert real_push["host_callback_contract_version"] == "neko.callback.v1"
    assert result["policy"]["real_battle_push_requires_coalesce_key"] is True
    assert result["policy"]["real_battle_push_requires_pending_replace_metadata"] is True
    assert result["policy"]["real_battle_push_requires_generic_host_callback_contract"] is True
    assert result["policy"]["death_event_bypasses_backpressure"] is True
    assert result["policy"]["critical_safety_event_bypasses_backpressure"] is True
    assert result["policy"]["expired_events_must_not_push"] is True


def test_output_freshness_gate_renders_text_summary():
    from neko_warthunder.tools import output_freshness_gate

    text = output_freshness_gate.render_text(output_freshness_gate.run_gate())

    assert "# neko_warthunder output freshness gate" in text
    assert "status: pass" in text
    assert "real battle output must be fresh" in text
    assert "real_push_contract" in text
    assert "expired_event_drop" in text
    assert "short_tts_line" in text


def test_output_freshness_gate_json_cli():
    from neko_warthunder.tools import output_freshness_gate

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = output_freshness_gate.main(["--json"])

    payload = json.loads(output.getvalue())
    assert rc == 0
    assert payload["status"] == "pass"
    assert payload["cases"][0]["reply_contract"] == "short_tts_line"
