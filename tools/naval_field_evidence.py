"""Manual offline audit of naval-marked samples; emits aggregate evidence, never readings/raw text.

Local files are untrusted observations, not proof of gameplay or physical semantics.
Only indicators.jsonl and processed_8112.jsonl are scanned; no HUD/chat streams.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import _bootstrap as _bootstrap  # noqa: F401
from neko_warthunder.adapters.naval_instrument_fields import _FIELDS, _field_status
from neko_warthunder.data_layer.data_process.wt_telemetry import WarThunderClient

_NAMES = {"indicators.jsonl", "processed_8112.jsonl"}
_MAX_LINE_BYTES = 1024 * 1024


def audit_samples(root: Path, *, max_records: int = 100000) -> dict:
    if max_records < 1:
        raise ValueError("max_records must be positive")
    report = {
        "status": "complete", "provenance": "unverified_local_files",
        "scanned_files": 0, "scanned_rows": 0, "malformed_rows": 0,
        "naval_marked_rows": {"ship": 0, "fleet": 0}, "files": [],
        "fields": {name: {} for name, _, _ in _FIELDS},
        "naval_semantics_verified": False, "live_acceptance_verified": False,
        "instrument_values_enabled": False, "real_output_enabled": False,
    }
    client = WarThunderClient()
    for path in sorted(root.rglob("*.jsonl")):
        if path.name not in _NAMES or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            continue
        digest, rows, naval_rows = hashlib.sha256(), 0, 0
        with path.open("rb") as stream:
            while True:
                line = stream.readline(_MAX_LINE_BYTES + 1)
                if not line:
                    break
                if len(line) > _MAX_LINE_BYTES or report["scanned_rows"] >= max_records:
                    report["status"] = "partial"
                    break
                digest.update(line)
                rows += 1
                report["scanned_rows"] += 1
                try:
                    entry = json.loads(line)
                except (ValueError, UnicodeError, RecursionError):
                    report["malformed_rows"] += 1
                    continue
                if not isinstance(entry, dict):
                    report["malformed_rows"] += 1
                    continue
                # Two supported envelopes: direct indicators, or telemetry.indicators.
                raw = entry.get("indicators") if path.name == "processed_8112.jsonl" else entry
                if not isinstance(raw, dict):
                    continue
                # Serialized Indicators contains a raw source, unlike raw /indicators.
                normalized = raw if "raw" in raw else None
                original = raw.get("raw") if normalized is not None else raw
                if (not isinstance(original, dict) or original.get("valid") is not True
                        or original.get("army") not in ("ship", "fleet")):
                    continue
                if normalized is not None and (raw.get("valid") is not True or raw.get("army") != original["army"]):
                    continue
                try:
                    normalized = normalized if normalized is not None else asdict(client._parse_indicators(original))
                except (ValueError, TypeError, OverflowError):
                    report["malformed_rows"] += 1
                    continue
                naval_rows += 1
                report["naval_marked_rows"][original["army"]] += 1
                for name, normalized_key, raw_key in _FIELDS:
                    status = _field_status(normalized, original, normalized_key, raw_key)
                    counts = report["fields"][name]
                    counts[status] = counts.get(status, 0) + 1
        report["scanned_files"] += 1
        # Hash only the consumed prefix; never label a partial digest as a full-file hash.
        report["files"].append({"consumed_prefix_sha256": digest.hexdigest(),
                                "scanned_rows": rows, "naval_marked_rows": naval_rows})
        if report["status"] == "partial":
            break
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path(__file__).resolve().parents[1] / "local_samples")
    parser.add_argument("--max-records", type=int, default=100000)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.samples.is_dir():
        parser.error("sample directory is unavailable")
    report = audit_samples(args.samples, max_records=args.max_records)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.out:
        args.out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
