"""Tests for vehicle profile id maintenance audit."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_vehicle_profile_id_audit_passes_with_vetted_runtime_ids(tmp_path):
    from neko_warthunder.tools import vehicle_profile_id_audit as audit

    profiles = tmp_path / "vehicle_profiles.json"
    vetted = tmp_path / "vehicle_profile_vetted_ids.json"
    aliases = tmp_path / "vehicle_profile_identity_aliases.json"
    _write_json(
        profiles,
        {
            "_default": {},
            "sb_2m_100": {"_tested": True, "class": "prop_bomber"},
            "a-10c": {"class": "attacker"},
            "a_10c": {"class": "attacker"},
        },
    )
    _write_json(vetted, {"ids": [{"vehicle_type": "sb_2m_100", "source": "live_indicator"}]})
    _write_json(
        aliases,
        {
            "aliases": [
                {
                    "canonical": "a_10c",
                    "aliases": ["a-10c"],
                    "source": "https://wiki.warthunder.com/unit/a_10c",
                    "status": "keep_until_live_vehicle_type_confirmed",
                }
            ]
        },
    )

    report = audit.build_report(profiles_path=profiles, vetted_ids_path=vetted, reviewed_aliases_path=aliases)

    assert report["status"] == "pass"
    assert report["summary"]["exact_profiles"] == 3
    assert report["summary"]["vetted_ids"] == 1
    assert report["summary"]["compact_alias_groups"] == 1
    assert report["summary"]["reviewed_alias_groups"] == 1
    assert report["summary"]["unreviewed_alias_groups"] == 0
    assert report["errors"] == []
    assert report["warnings"] == []
    assert report["reviewed_alias_groups"][0]["canonical"] == "a_10c"
    assert report["policy"]["network_access"] is False
    assert report["policy"]["runtime_authority"] == "/api/processed.vehicle_type"


def test_vehicle_profile_id_audit_fails_when_vetted_id_is_not_protected(tmp_path):
    from neko_warthunder.tools import vehicle_profile_id_audit as audit

    profiles = tmp_path / "vehicle_profiles.json"
    vetted = tmp_path / "vehicle_profile_vetted_ids.json"
    aliases = tmp_path / "vehicle_profile_identity_aliases.json"
    _write_json(
        profiles,
        {
            "_default": {},
            "sb_2m_100": {"class": "prop_bomber"},
            "bad id": {},
        },
    )
    _write_json(
        vetted,
        {
            "ids": [
                {"vehicle_type": "sb_2m_100"},
                {"vehicle_type": "missing_vehicle"},
            ]
        },
    )
    _write_json(
        aliases,
        {
            "aliases": [
                {
                    "canonical": "missing_canonical",
                    "aliases": ["missing_alias"],
                }
            ]
        },
    )

    report = audit.build_report(profiles_path=profiles, vetted_ids_path=vetted, reviewed_aliases_path=aliases)
    codes = {item["code"] for item in report["errors"]}

    assert report["status"] == "fail"
    assert "invalid_exact_key_shape" in codes
    assert "vetted_id_not_marked_tested" in codes
    assert "vetted_id_missing_profile" in codes
    assert "reviewed_alias_missing_canonical" in codes
    assert "reviewed_alias_missing_profile" in codes


def test_vehicle_profile_id_audit_cli_outputs_json_and_return_code(tmp_path):
    from neko_warthunder.tools import vehicle_profile_id_audit as audit

    profiles = tmp_path / "vehicle_profiles.json"
    vetted = tmp_path / "vehicle_profile_vetted_ids.json"
    aliases = tmp_path / "vehicle_profile_identity_aliases.json"
    output_path = tmp_path / "report.json"
    _write_json(profiles, {"_default": {}, "j_15t": {"_tested": True}})
    _write_json(vetted, {"ids": [{"vehicle_type": "j_15t"}]})
    _write_json(aliases, {"aliases": []})

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = audit.main(
            [
                "--profiles",
                str(profiles),
                "--vetted-ids",
                str(vetted),
                "--reviewed-aliases",
                str(aliases),
                "--json",
                "--output",
                str(output_path),
            ]
        )

    payload = json.loads(stdout.getvalue())
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload["status"] == "pass"
    assert written["summary"]["tested_profiles"] == 1
