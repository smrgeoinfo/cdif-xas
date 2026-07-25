#!/usr/bin/env python3
"""Batch-generate CDIF-XAS JSON-LD for every *.xdi file in a directory.

Runs the same pipeline as /cdif -> /map -> /frame (bypassing the HTTP
layer), and writes one JSON-LD file per input XDI into an output
directory. Output filename mirrors the input stem (foo.xdi -> foo.jsonld).

The pipeline uses shared side-effect files under resources/ (cdif_skos.json,
cdif_dds.jsonld, cdif_dds_framed.jsonld), so processing is serial by
construction.

Usage:
    python tools/batch_generate_cdif.py <input-dir> <output-dir>

Example (the driving case):
    python tools/batch_generate_cdif.py \\
        "C:/GithubC/CDIF/XAS-CDIF/exampleData" \\
        "C:/GithubC/CDIF/XAS-CDIF/exampleMetadata"

For each file, one of three outcomes lands in the output directory:

  <stem>.jsonld            successful end-to-end run (framed CDIF-XAS)
  (skipped, no file)       XDI pre-check killed generation (e.g., missing
                           # --- header end line — parser can't proceed).
                           Reason logged and captured in the summary.
  <stem>.error.txt         pipeline started but failed mid-way. File
                           contains a short traceback so the failure is
                           inspectable without rerunning.

A batch_generation_report.{txt,csv,json} triplet is written into the
output dir alongside the JSON-LD files.

Prereqs: Java (rmlmapper), the CDIF-XAS venv (uv sync). Run from the
repo root or pass CDIF_XAS_RESOURCES_DIR explicitly.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import traceback
from pathlib import Path


def _import_pipeline():
    """Late import so the module import failure surfaces a clean message."""
    try:
        from api.cdi import generate_cdi
        from api.cdif import generate_cdif
        from api.Mapper import map as rml_map, frame as rml_frame
    except ImportError as e:
        sys.exit(
            f"Cannot import pipeline modules: {e}\n"
            "Run from the cdif-xas-UKDS repo root (or set PYTHONPATH), "
            "and make sure `uv sync` has populated .venv."
        )
    return generate_cdi, generate_cdif, rml_map, rml_frame


def _resources_dir(repo_root: Path) -> Path:
    import os
    return Path(os.environ.get(
        "CDIF_XAS_RESOURCES_DIR",
        str(repo_root / "resources"),
    ))


def _process_one(
    xdi: Path,
    out_dir: Path,
    resources_dir: Path,
    skos_json_path: Path,
    framed_path: Path,
    generate_cdi, generate_cdif, rml_map, rml_frame,
) -> dict:
    """Returns a dict describing outcome for the report."""
    stem = xdi.stem
    dst_jsonld = out_dir / f"{stem}.jsonld"
    dst_error = out_dir / f"{stem}.error.txt"

    # Clean any stale error marker from a prior run
    if dst_error.exists():
        dst_error.unlink()

    result = {
        "filename": xdi.name,
        "stem": stem,
        "output_file": None,
        "status": "unknown",
        "error": None,
    }

    try:
        # 1. /cdif — parse XDI to rdflib graph, serialize to JSON-LD dict,
        #    write to resources/cdif_skos.json
        graph = generate_cdi(
            f"file:///{xdi.as_posix()}",
            str(resources_dir),
            "xas",
            include_data=False,
        )
        cdi_jsonld = graph.serialize(format="json-ld")
        pp_data = generate_cdif(cdi_jsonld)
        skos_json_path.write_text(
            json.dumps(pp_data, indent=2), encoding="utf-8"
        )

        # 2. /map — run rmlmapper, writes resources/cdif_dds.jsonld
        rml_map("Data Description Structure")

        # 3. /frame — writes resources/cdif_dds_framed.jsonld
        rml_frame("Data Description Structure")

        # 4. Copy the framed artifact to the per-file destination
        shutil.copyfile(framed_path, dst_jsonld)

        result["output_file"] = dst_jsonld.name
        result["status"] = "ok"
        return result
    except Exception as e:
        tb = traceback.format_exc()
        dst_error.write_text(
            f"{type(e).__name__}: {e}\n\n{tb}", encoding="utf-8"
        )
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"
        return result


def _write_reports(out_dir: Path, per_file: list[dict]) -> None:
    txt_path = out_dir / "batch_generation_report.txt"
    csv_path = out_dir / "batch_generation_report.csv"
    json_path = out_dir / "batch_generation_report.json"

    ok = [r for r in per_file if r["status"] == "ok"]
    err = [r for r in per_file if r["status"] == "error"]

    lines = [
        "CDIF-XAS batch generation report",
        f"Total inputs:  {len(per_file)}",
        f"  ok:          {len(ok)}",
        f"  error:       {len(err)}",
        "",
        "=" * 70,
        "OK",
        "=" * 70,
    ]
    for r in ok:
        lines.append(f"  {r['filename']:60s} -> {r['output_file']}")
    if err:
        lines += ["", "=" * 70, "ERRORS", "=" * 70]
        for r in err:
            lines.append(f"  {r['filename']}")
            lines.append(f"    {r['error']}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "status", "output_file", "error"])
        for r in per_file:
            w.writerow([r["filename"], r["status"],
                        r["output_file"] or "", r["error"] or ""])

    json_path.write_text(json.dumps({
        "count": len(per_file),
        "ok": len(ok),
        "error": len(err),
        "per_file": per_file,
    }, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input_dir", type=Path,
                    help="Directory of *.xdi input files")
    ap.add_argument("output_dir", type=Path,
                    help="Directory to write per-file JSON-LD outputs into")
    args = ap.parse_args(argv)

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not input_dir.is_dir():
        sys.exit(f"Not a directory: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parent.parent
    resources_dir = _resources_dir(repo_root)
    skos_json = resources_dir / "cdif_skos.json"
    framed_path = resources_dir / "cdif_dds_framed.jsonld"

    generate_cdi, generate_cdif, rml_map, rml_frame = _import_pipeline()

    files = sorted(input_dir.glob("*.xdi"))
    if not files:
        sys.exit(f"No *.xdi files found in {input_dir}")

    print(f"Generating CDIF-XAS for {len(files)} XDI files")
    print(f"  input : {input_dir}")
    print(f"  output: {output_dir}\n", flush=True)

    per_file = []
    for i, xdi in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {xdi.name}", end=" ", flush=True)
        r = _process_one(
            xdi, output_dir, resources_dir, skos_json, framed_path,
            generate_cdi, generate_cdif, rml_map, rml_frame,
        )
        marker = "OK" if r["status"] == "ok" else f"ERROR ({r['error']})"
        print(marker, flush=True)
        per_file.append(r)

    _write_reports(output_dir, per_file)

    ok = sum(1 for r in per_file if r["status"] == "ok")
    err = sum(1 for r in per_file if r["status"] == "error")
    print(f"\nDone. {ok} ok, {err} error(s).")
    print(f"Reports in {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
