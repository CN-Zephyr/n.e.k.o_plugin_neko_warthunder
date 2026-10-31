"""Current documentation claims must agree without rewriting historical evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from neko_warthunder.tools import rc_audit


def _write_docs(root: Path, count: int = 812) -> None:
    for rel in rc_audit.AUDITED_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(rc_audit.REQUIRED_SNIPPETS) + f"\n{count} passed\n",
                        encoding="utf-8")
    (root / rc_audit.BASELINE_DOCUMENT).write_text(
        f"# 当前状态\n| 完整 pytest | **{count} passed**，2026-10-27 | 完整测试 |\n",
        encoding="utf-8",
    )


def _append(root: Path, text: str, rel: str = "README.md") -> None:
    with (root / rel).open("a", encoding="utf-8") as stream:
        stream.write("\n" + text + "\n")


@pytest.mark.parametrize("count", [789, 812, 1041])
def test_rc_audit_reads_baseline_from_status_document(tmp_path, count):
    _write_docs(tmp_path, count)
    result = rc_audit.audit_docs(tmp_path)
    assert result["status"] == "pass"
    assert result["pytest_baseline"] == count
    assert result["baseline_source"] == rc_audit.BASELINE_DOCUMENT


@pytest.mark.parametrize("claim", ["622/622 passed", "493 passed", "813 passed", "812/813 passed"])
def test_rc_audit_rejects_any_conflicting_current_count(tmp_path, claim):
    _write_docs(tmp_path)
    _append(tmp_path, claim)
    result = rc_audit.audit_docs(tmp_path)
    assert result["status"] == "fail"
    assert {"kind": "stale_baseline", "file": "README.md",
            "detail": f"{claim}; expected 812 passed"} in result["failures"]


@pytest.mark.parametrize("row", ["", "| 完整 pytest | 0 passed |",
                                      "| 完整 pytest | 811/812 passed |",
                                      "| 完整 pytest | 812 passed / 813 passed |",
                                      "| 完整 pytest | 812 passed |\n| 完整 pytest | 812 passed |"])
def test_rc_audit_rejects_missing_or_ambiguous_baseline(tmp_path, row):
    _write_docs(tmp_path)
    (tmp_path / rc_audit.BASELINE_DOCUMENT).write_text(row, encoding="utf-8")
    result = rc_audit.audit_docs(tmp_path)
    assert result["status"] == "fail"
    assert result["pytest_baseline"] is None
    assert any(item["kind"] == "missing_current_baseline" for item in result["failures"])


def test_rc_audit_requires_current_baseline_in_status(tmp_path):
    _write_docs(tmp_path)
    (tmp_path / "PROJECT_STATUS.md").write_text("# 当前状态\n", encoding="utf-8")
    result = rc_audit.audit_docs(tmp_path)
    assert {"kind": "missing_required_baseline", "file": "PROJECT_STATUS.md",
            "detail": "Expected 812 passed"} in result["failures"]


def test_rc_audit_keeps_required_capability_checks(tmp_path):
    _write_docs(tmp_path)
    for rel in rc_audit.AUDITED_FILES:
        path = tmp_path / rel
        path.write_text(path.read_text(encoding="utf-8").replace("ground_target_nearby", ""),
                        encoding="utf-8")
    result = rc_audit.audit_docs(tmp_path)
    assert {"kind": "missing_required_snippet", "file": "-",
            "detail": "ground_target_nearby"} in result["failures"]


def test_rc_audit_preserves_historical_files_and_sections(tmp_path):
    _write_docs(tmp_path)
    historical = "docs/样本回放-20260620.md"
    (tmp_path / historical).write_text("575 passed\nui/panel.tsx 未实现", encoding="utf-8")
    _append(tmp_path, "## 历史证据\n622/622 passed\n### 旧基线\n493 passed\n"
                      "## 当前验证\n812/812 passed\n历史记录：575 passed")
    result = rc_audit.audit_docs(tmp_path)
    assert result["status"] == "pass"
    assert result["historical_files_skipped"] == [historical]


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_rc_audit_does_not_treat_fenced_headings_as_history(tmp_path, fence):
    _write_docs(tmp_path)
    _append(tmp_path, f"{fence}text\n## 历史\n{fence}\n900 passed")
    result = rc_audit.audit_docs(tmp_path)
    assert result["status"] == "fail"
    assert any("900 passed" in item["detail"] for item in result["failures"])


def test_rc_audit_returns_to_current_section_and_checks_mixed_claims(tmp_path):
    _write_docs(tmp_path)
    _append(tmp_path, "## 历史\n575 passed\n## 当前\n历史 575 passed，当前 812 passed")
    result = rc_audit.audit_docs(tmp_path)
    assert result["status"] == "fail"
    assert any("575 passed" in item["detail"] for item in result["failures"])


def test_rc_audit_keeps_current_claims_in_mixed_history_heading(tmp_path):
    _write_docs(tmp_path)
    _append(tmp_path, "## 当前与历史对照\n900 passed")
    result = rc_audit.audit_docs(tmp_path)
    assert result["status"] == "fail"
    assert any("900 passed" in item["detail"] for item in result["failures"])


def test_rc_audit_reports_missing_files(tmp_path):
    _write_docs(tmp_path)
    (tmp_path / rc_audit.BASELINE_DOCUMENT).unlink()
    result = rc_audit.audit_docs(tmp_path)
    assert {"kind": "missing_file", "file": rc_audit.BASELINE_DOCUMENT,
            "detail": rc_audit.BASELINE_DOCUMENT} in result["failures"]


def test_rc_audit_cli_json_is_machine_readable(tmp_path, capsys):
    _write_docs(tmp_path, 1041)
    assert rc_audit.main(["--plugin-root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert payload["pytest_baseline"] == 1041
    assert "README.md" in payload["audited_files"]


def test_rc_audit_cli_text_reports_failures_without_raw_dump(tmp_path, capsys):
    _write_docs(tmp_path)
    _append(tmp_path, "ui/panel.tsx 未实现\nprivate unrelated content")
    assert rc_audit.main(["--plugin-root", str(tmp_path)]) == 1
    text = capsys.readouterr().out
    assert "status: fail" in text
    assert "forbidden_phrase" in text
    assert "private unrelated content" not in text
