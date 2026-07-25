#!/usr/bin/env python3
"""Batch-validate a directory of CDIF-XAS JSON-LD files against the
bundled xasDocument JSON Schema and SHACL rules.

Emits three reports into the output directory (default: same as input):
  batch_validation_report.txt   Human-readable summary.
  batch_validation_report.csv   filename, schema_errors, shacl_violations, ok.
  batch_validation_report.json  Full structured detail (first 20 errs/file).

Requires pyshacl for SHACL. Install with `uv pip install pyshacl` or
skip SHACL with --schema-only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = REPO_ROOT / "resources" / "cdifXASDocumentResolvedSchema.json"
DEFAULT_SHACL = REPO_ROOT / "resources" / "xasDocumentRules.shacl"
MAX_ERRORS_IN_JSON = 20


def _load_schema(path):
    from jsonschema import Draft202012Validator
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    return Draft202012Validator(schema)


def _validate_schema(validator, doc):
    errs = []
    for e in validator.iter_errors(doc):
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errs.append(f"{loc}: {e.message}")
    return errs


def _validate_shacl(shacl_bytes, doc):
    import pyshacl
    import rdflib
    data = rdflib.Graph()
    data.parse(data=json.dumps(doc), format="json-ld")
    shacl = rdflib.Graph()
    shacl.parse(data=shacl_bytes, format="turtle")
    conforms, _, results_text = pyshacl.validate(
        data_graph=data,
        shacl_graph=shacl,
        inference="none",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    if conforms:
        return 0, []
    blocks = [b.strip() for b in results_text.split("\n\n") if b.strip()]
    violations = [b for b in blocks if "Violation" in b or "Warning" in b]
    condensed = []
    for v in violations:
        first = next((ln for ln in v.splitlines() if "Message:" in ln),
                     v.splitlines()[0])
        condensed.append(first.strip())
    return len(condensed), condensed


def _process_one(jsonld, schema_validator, shacl_bytes):
    result = {
        "filename": jsonld.name,
        "schema_errors": None,
        "shacl_violations": None,
        "schema_error_list": [],
        "shacl_violation_list": [],
        "ok": False,
        "parse_error": None,
    }
    try:
        with open(jsonld, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        result["parse_error"] = f"{type(e).__name__}: {e}"
        return result
    schema_errs = _validate_schema(schema_validator, doc)
    result["schema_errors"] = len(schema_errs)
    result["schema_error_list"] = schema_errs[:MAX_ERRORS_IN_JSON]
    if shacl_bytes is not None:
        n, viols = _validate_shacl(shacl_bytes, doc)
        result["shacl_violations"] = n
        result["shacl_violation_list"] = viols[:MAX_ERRORS_IN_JSON]
    result["ok"] = (result["schema_errors"] == 0
                    and (result["shacl_violations"] in (0, None)))
    return result


def _write_reports(out_dir, per_file, shacl_enabled):
    from collections import Counter
    txt = out_dir / "batch_validation_report.txt"
    csv_path = out_dir / "batch_validation_report.csv"
    js = out_dir / "batch_validation_report.json"
    ok = [r for r in per_file if r["ok"]]
    bad = [r for r in per_file if not r["ok"]]

    lines = [
        "CDIF-XAS batch validation report",
        f"Files:                {len(per_file)}",
        f"Fully valid:          {len(ok)}",
        f"With any violation:   {len(bad)}",
        "",
        "=" * 70,
        "PER-FILE COUNTS",
        "=" * 70,
        f"{'filename':<48s}  {'schema':>7s}  {'shacl':>7s}",
    ]
    for r in per_file:
        s = ("n/a" if r["schema_errors"] is None else str(r["schema_errors"]))
        sh = ("skip" if not shacl_enabled else
              ("n/a" if r["shacl_violations"] is None else str(r["shacl_violations"])))
        lines.append(f"  {r['filename']:<46s}  {s:>7s}  {sh:>7s}")

    lines += ["", "=" * 70, "TOP AGGREGATED SCHEMA ERROR PATHS", "=" * 70]
    path_counter = Counter()
    for r in per_file:
        for e in r["schema_error_list"]:
            path_counter[e.split(":", 1)[0]] += 1
    for path, n in path_counter.most_common(20):
        lines.append(f"  {n:4d}  {path}")

    if shacl_enabled:
        lines += ["", "=" * 70, "TOP AGGREGATED SHACL MESSAGES", "=" * 70]
        sh_counter = Counter()
        for r in per_file:
            for v in r["shacl_violation_list"]:
                sh_counter[v] += 1
        for msg, n in sh_counter.most_common(20):
            lines.append(f"  {n:4d}  {msg[:120]}")

    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "schema_errors", "shacl_violations", "ok", "parse_error"])
        for r in per_file:
            w.writerow([
                r["filename"],
                "" if r["schema_errors"] is None else r["schema_errors"],
                "" if r["shacl_violations"] is None else r["shacl_violations"],
                r["ok"],
                r["parse_error"] or "",
            ])
    js.write_text(json.dumps({
        "count": len(per_file),
        "fully_valid": len(ok),
        "with_violation": len(bad),
        "shacl_enabled": shacl_enabled,
        "per_file": per_file,
    }, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    ap.add_argument("--shacl", type=Path, default=DEFAULT_SHACL)
    ap.add_argument("--schema-only", action="store_true")
    args = ap.parse_args(argv)

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        sys.exit(f"Not a directory: {input_dir}")
    out_dir = (args.out or input_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.schema.exists():
        sys.exit(f"Schema not found: {args.schema}")

    files = sorted(f for f in input_dir.glob("*.jsonld")
                   if not f.name.startswith("batch_"))
    if not files:
        sys.exit(f"No *.jsonld files found in {input_dir}")

    schema_validator = _load_schema(args.schema)
    shacl_bytes = None
    if not args.schema_only:
        try:
            import pyshacl  # noqa: F401
        except ImportError:
            sys.exit("pyshacl not installed. `uv pip install pyshacl` or --schema-only.")
        if not args.shacl.exists():
            sys.exit(f"SHACL file not found: {args.shacl}")
        shacl_bytes = args.shacl.read_bytes()

    print(f"Validating {len(files)} JSON-LD file(s)")
    print(f"  input : {input_dir}")
    print(f"  schema: {args.schema.name}")
    if shacl_bytes is not None:
        print(f"  shacl : {args.shacl.name}")
    print()

    per_file = []
    for i, f in enumerate(files, 1):
        r = _process_one(f, schema_validator, shacl_bytes)
        s = ("n/a" if r["schema_errors"] is None else str(r["schema_errors"]))
        sh = ("skip" if shacl_bytes is None else
              ("n/a" if r["shacl_violations"] is None else str(r["shacl_violations"])))
        mark = "OK" if r["ok"] else "  "
        print(f"[{i}/{len(files)}] {mark}  {f.name:<50s}  "
              f"schema={s:>4s} shacl={sh:>4s}", flush=True)
        per_file.append(r)

    _write_reports(out_dir, per_file, shacl_enabled=shacl_bytes is not None)
    ok = sum(1 for r in per_file if r["ok"])
    print(f"\nDone. {ok}/{len(files)} fully valid.")
    print(f"Reports in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
