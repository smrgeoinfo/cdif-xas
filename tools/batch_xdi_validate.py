#!/usr/bin/env python3
"""Batch-run xdi_validator against a directory of XDI files and write
structured reports.

The bundled xdi_validator (see api/xdi_precheck.py's acknowledgement
block) runs the XDI/1.0 spec check per file. This script iterates a
directory of *.xdi files, runs the validator on each, and emits three
reports:

  batch_validation_report.txt   Human-readable summary. Distribution of
                                error counts, field-error frequency,
                                one example per unique error signature.

  batch_validation_report.csv   Per-file table. Columns: filename,
                                valid, error_count, signature_id,
                                error_fields (semicolon-joined). Load
                                into Excel / pandas for spreadsheet
                                analysis.

  batch_validation_report.json  Raw structured data — the full field
                                error dict per file, plus aggregates.
                                For programmatic consumers.

Usage:
    python tools/batch_xdi_validate.py <input-dir> [--out <out-dir>]

Examples:
    # Report alongside the XDI files (default)
    python tools/batch_xdi_validate.py \\
        "C:/GithubC/CDIF/XAS-CDIF/exampleData/XDI format of collection 203"

    # Custom output directory
    python tools/batch_xdi_validate.py path/to/xdi/dir --out /tmp/reports

The three report files are always named
batch_validation_report.{txt,csv,json} in the output directory.
Existing files are overwritten. Reports are written alongside the
input files by default so a scanned collection carries its own
validation record without polluting the caller's working directory.

Requires: xdi-validator (installed via `uv sync` alongside the rest of
the project's dependencies).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path


def _import_validator():
    try:
        from xdi_validator import validate, XDIEndOfHeaderMissingError
    except ImportError:
        sys.exit(
            "xdi_validator is not installed. Run `uv sync` in the "
            "cdif-xas-UKDS repo, or `pip install xdi-validator`."
        )
    return validate, XDIEndOfHeaderMissingError


def _summarize(err_dict: dict) -> tuple[int, dict]:
    """xdi_validator returns {'Namespace.field': [msg, ...], ...}."""
    if not err_dict:
        return 0, {}
    total = sum(len(v) if isinstance(v, list) else 1 for v in err_dict.values())
    return total, err_dict


def _validate_one(path: Path, validate, EofExc) -> tuple[int, dict]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            errs, _ = validate(f)
        return _summarize(errs)
    except EofExc as e:
        return -1, {"__eof_missing__": [str(e)]}
    except Exception as e:
        return -2, {"__exception__": [f"{type(e).__name__}: {e}"]}


def _signature_id(fields: list[str]) -> str:
    """Deterministic 8-char id for a set of failing field paths."""
    canonical = "|".join(sorted(fields))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:8]


def _run(input_dir: Path, out_dir: Path) -> int:
    validate, EofExc = _import_validator()

    files = sorted(input_dir.glob("*.xdi"))
    if not files:
        sys.exit(f"No *.xdi files found in {input_dir}")

    print(f"Validating {len(files)} XDI files under {input_dir.name}", flush=True)

    per_file = []               # dicts: name, path, error_count, field_errors, signature_id
    field_counter = Counter()   # field-name -> file count
    bucket_counter = Counter()  # error_count -> file count
    signatures = {}             # signature_id -> {fields, example_file, count}

    for f in files:
        count, errs = _validate_one(f, validate, EofExc)
        fields = list(errs.keys())
        sig = _signature_id(fields)

        per_file.append({
            "filename": f.name,
            "path": str(f),
            "valid": count == 0,
            "error_count": count,
            "signature_id": sig,
            "field_errors": errs,
        })

        bucket_counter[count] += 1
        for field in fields:
            field_counter[field] += 1
        if sig not in signatures:
            signatures[sig] = {"fields": fields, "example_file": f.name, "count": 0}
        signatures[sig]["count"] += 1

    out_dir.mkdir(parents=True, exist_ok=True)

    txt_path = out_dir / "batch_validation_report.txt"
    csv_path = out_dir / "batch_validation_report.csv"
    json_path = out_dir / "batch_validation_report.json"

    _write_txt(txt_path, input_dir, files, bucket_counter, field_counter,
               signatures, per_file)
    _write_csv(csv_path, per_file)
    _write_json(json_path, input_dir, files, bucket_counter, field_counter,
                signatures, per_file)

    print(f"\nWrote:")
    for p in (txt_path, csv_path, json_path):
        print(f"  {p}  ({p.stat().st_size} bytes)")
    return 0


def _write_txt(path: Path, input_dir: Path, files, buckets, fields,
               signatures, per_file) -> None:
    lines = []
    lines.append("XDI/1.0 batch validation report")
    lines.append(f"Input directory: {input_dir}")
    lines.append(f"Files scanned:   {len(files)}")
    lines.append("")
    lines.append("=" * 70)
    lines.append("DISTRIBUTION OF ERROR COUNT PER FILE")
    lines.append("=" * 70)
    for count in sorted(buckets):
        label = (
            "VALID (0 errors)" if count == 0 else
            "EOF marker missing" if count == -1 else
            "parser exception" if count == -2 else
            f"{count} errors"
        )
        lines.append(f"  {label:30s}: {buckets[count]} file(s)")

    lines.append("")
    lines.append("=" * 70)
    lines.append("FIELD ERROR DISTRIBUTION (across all files)")
    lines.append("=" * 70)
    for field, n in sorted(fields.items(), key=lambda kv: -kv[1]):
        pct = 100 * n / len(files) if files else 0
        lines.append(f"  {field:40s}: {n:4d} files ({pct:5.1f}%)")

    lines.append("")
    lines.append("=" * 70)
    lines.append("UNIQUE FIELD-ERROR SIGNATURES")
    lines.append("=" * 70)
    for sig_id, info in sorted(signatures.items(), key=lambda kv: -kv[1]["count"]):
        lines.append(f"\n  signature {sig_id} — {info['count']} file(s)")
        lines.append(f"    example: {info['example_file']}")
        example = next(
            (r for r in per_file if r["signature_id"] == sig_id), None
        )
        if example:
            for field, msgs in example["field_errors"].items():
                msg = msgs[0] if isinstance(msgs, list) and msgs else str(msgs)
                lines.append(f"      {field}: {msg[:140]}")
    lines.append(f"\n  {len(signatures)} unique signature(s) across "
                 f"{len(files)} file(s)")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, per_file) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "valid", "error_count",
                         "signature_id", "error_fields"])
        for row in per_file:
            writer.writerow([
                row["filename"],
                row["valid"],
                row["error_count"],
                row["signature_id"],
                ";".join(sorted(row["field_errors"].keys())),
            ])


def _write_json(path: Path, input_dir: Path, files, buckets, fields,
                signatures, per_file) -> None:
    payload = {
        "input_dir": str(input_dir),
        "file_count": len(files),
        "error_count_distribution": {str(k): v for k, v in buckets.items()},
        "field_error_frequency": dict(fields),
        "unique_signatures": {
            sig_id: {
                "fields": info["fields"],
                "example_file": info["example_file"],
                "file_count": info["count"],
            }
            for sig_id, info in signatures.items()
        },
        "per_file": per_file,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input_dir", type=Path,
                    help="Directory containing *.xdi files to validate")
    ap.add_argument("--out", type=Path, default=None,
                    help="Directory for the three report files "
                         "(default: same as input_dir — reports "
                         "written alongside the XDI files)")
    args = ap.parse_args(argv)

    if not args.input_dir.is_dir():
        sys.exit(f"Not a directory: {args.input_dir}")

    input_dir = args.input_dir.resolve()
    out_dir = args.out.resolve() if args.out else input_dir
    return _run(input_dir, out_dir)


if __name__ == "__main__":
    sys.exit(main())
