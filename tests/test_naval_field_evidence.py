"""Aggregate-only sample evidence: never claim that a naval marker verifies live semantics."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("naval_field_evidence", TOOLS / "naval_field_evidence.py")
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


def test_whitelist_aggregate_preserves_zero_and_rejects_coercion_without_private_data(tmp_path):
    naval = {"valid": True, "army": "ship", "speed": 0, "compass": -0.5,
             "rpm": True, "throttle": "0.6", "name": "private-sentinel", "flooding": 44}
    (tmp_path / "indicators.jsonl").write_text(json.dumps(naval) + "\nnot-json\n", encoding="utf-8")
    (tmp_path / "hudmsg.jsonl").write_text("private-sentinel", encoding="utf-8")
    (tmp_path / "gamechat.jsonl").write_text("private-sentinel", encoding="utf-8")
    result = evidence.audit_samples(tmp_path)
    assert result["scanned_files"] == 1 and result["scanned_rows"] == 2
    assert result["malformed_rows"] == 1 and result["naval_marked_rows"] == {"ship": 1, "fleet": 0}
    assert result["fields"]["speed"] == result["fields"]["heading"] == {"observed_numeric": 1}
    assert result["fields"]["rpm"] == result["fields"]["throttle"] == {"invalid": 1}
    encoded = json.dumps(result)
    assert all(s not in encoded for s in ("private-sentinel", "-0.5", "0.6", "flooding", str(tmp_path)))
    assert result["naval_semantics_verified"] is result["live_acceptance_verified"] is False


@pytest.mark.parametrize("original,normalized,count", [
    ({"valid": True, "army": "fleet", "speed": 2}, {"valid": True, "army": "fleet", "speed": 3}, 1),
    ({"valid": 1, "army": "fleet"}, {"valid": True, "army": "fleet"}, 0),
    ({"valid": True, "army": "fleet"}, {"valid": True, "army": "tank"}, 0),
    ({"valid": True, "army": "SHIP"}, {"valid": True, "army": "SHIP"}, 0),
])
def test_serialized_fields_require_matching_strict_original_provenance(tmp_path, original, normalized, count):
    (tmp_path / "processed_8112.jsonl").write_text(json.dumps({
        "indicators": {**normalized, "raw": original}, "chat": [{"msg": "private-sentinel"}],
    }) + "\n", encoding="utf-8")
    result = evidence.audit_samples(tmp_path)
    assert result["naval_marked_rows"]["fleet"] == count
    if count:
        assert result["fields"]["speed"] == {"conflicting": 1}
    assert "private-sentinel" not in json.dumps(result)


@pytest.mark.parametrize("mode", ["records", "line"])
def test_partial_scan_is_explicit_and_never_claims_complete_file_hash(tmp_path, mode):
    text = '{}\n{}\n' if mode == "records" else 'x' * (1024 * 1024 + 5)
    (tmp_path / "indicators.jsonl").write_text(text, encoding="utf-8")
    report = evidence.audit_samples(tmp_path, max_records=1)
    assert report["status"] == "partial" and report["scanned_rows"] <= 1
    assert "sha256" not in report["files"][0]


def test_empty_evidence_is_a_coverage_gap_not_a_claim_of_unsupported_game_fields(tmp_path):
    report = evidence.audit_samples(tmp_path)
    assert report["status"] == "complete" and report["scanned_files"] == 0
    assert report["provenance"] == "unverified_local_files"
    assert report["naval_marked_rows"] == {"ship": 0, "fleet": 0}
