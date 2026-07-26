"""RC documentation audit tests."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path


def _write_minimal_docs(root: Path, *, extra: str = "") -> None:
    from neko_warthunder.tools.rc_audit import AUDITED_FILES, REQUIRED_SNIPPETS

    corpus = "\n".join(REQUIRED_SNIPPETS) + "\n" + extra
    for rel in AUDITED_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(corpus, encoding="utf-8")


def test_rc_audit_passes_when_release_docs_match_current_state():
    from neko_warthunder.tools.rc_audit import audit_docs

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_minimal_docs(root)

        result = audit_docs(root)

    assert result["status"] == "pass"
    assert result["failures"] == []


def test_rc_audit_fails_on_stale_baseline():
    from neko_warthunder.tools.rc_audit import audit_docs

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_minimal_docs(root, extra="old baselines: 192/192 passed and 493/493 passed")

        result = audit_docs(root)

    assert result["status"] == "fail"
    assert {
        "kind": "stale_baseline",
        "file": "README.md",
        "detail": "192/192 passed",
    } in result["failures"]
    assert {
        "kind": "stale_baseline",
        "file": "README.md",
        "detail": "493/493 passed",
    } in result["failures"]


def test_rc_audit_fails_when_required_status_is_missing():
    from neko_warthunder.tools import rc_audit

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_minimal_docs(root)
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8").replace("ground_target_nearby", "")
        for rel in rc_audit.AUDITED_FILES:
            (root / rel).write_text(text, encoding="utf-8")

        result = rc_audit.audit_docs(root)

    assert result["status"] == "fail"
    assert {
        "kind": "missing_required_snippet",
        "file": "-",
        "detail": "ground_target_nearby",
    } in result["failures"]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_minimal_docs(root)
        status = root / "PROJECT_STATUS.md"
        status.write_text(
            status.read_text(encoding="utf-8").replace("532/532 passed", "outdated baseline"),
            encoding="utf-8",
        )

        result = rc_audit.audit_docs(root)

    assert {
        "kind": "missing_required_file_snippet",
        "file": "PROJECT_STATUS.md",
        "detail": "532/532 passed",
    } in result["failures"]


def test_rc_audit_cli_json_is_machine_readable():
    from neko_warthunder.tools import rc_audit

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_minimal_docs(root)
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            rc = rc_audit.main(["--plugin-root", str(root), "--json"])

    payload = json.loads(output.getvalue())
    assert rc == 0
    assert payload["status"] == "pass"
    assert "README.md" in payload["audited_files"]


def test_rc_audit_cli_text_reports_failures_without_raw_dump():
    from neko_warthunder.tools import rc_audit

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_minimal_docs(root, extra="ui/panel.tsx 未实现")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            rc = rc_audit.main(["--plugin-root", str(root)])

    text = output.getvalue()
    assert rc == 1
    assert "status: fail" in text
    assert "forbidden_phrase" in text
