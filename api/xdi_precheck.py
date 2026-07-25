"""Pre-validation of the input XDI file against the XDI/1.0 specification.

Wraps the `xdi_validator` Python package (MIT licensed) by A. A. Alves Jr.
Called from the /cdif endpoint before CDIF generation, so the response
includes both:
  - the CDIF JSON-LD output (existing behavior), and
  - an xdi_validation block summarizing how the input conforms to the
    XDI/1.0 spec.

Validation is warning-only: bad XDI does not block CDIF generation.
Matches the graceful-degradation pattern used elsewhere (Dataverse
enrichment failures, placeholder Dataset metadata, Mono.d_spacing
fallback).

If xdi_validator is not installed the wrapper returns a benign result
with a note in the response, so this module doesn't hard-fail existing
deployments.

Acknowledgement / citation
--------------------------
This module uses `xdi_validator`:
  Author:  A. A. Alves Jr.
  Source:  https://github.com/AAAlvesJr/XDI-Validator
  PyPI:    https://pypi.org/project/xdi-validator/
  License: MIT
  DOI:     https://doi.org/10.5281/zenodo.20018640

`xdi_validator` is a runtime dependency installed via pip; no source is
vendored here. See its LICENSE file at
https://github.com/AAAlvesJr/XDI-Validator/blob/main/LICENSE
for the full MIT terms.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any


def _load_xdi_text(url: str) -> str:
    """Read the XDI file text. Handles the same three URL shapes as
    api/cdi.py: file:// URIs, absolute POSIX paths, Windows drive
    paths, and HTTP(S) URLs.
    """
    from api.local_input import is_local_path, _local_path_from_url
    if is_local_path(url):
        return _local_path_from_url(url).read_text(encoding="utf-8")
    import requests
    return requests.get(url).text


def _summarize_errors(err_dict: dict) -> dict:
    """Reshape xdi_validator's error dict for a clean HTTP response.

    xdi_validator returns errors keyed by field path (e.g., 'Beamline.name')
    with a list of messages as the value. Wrap that with a count and a
    top-level 'ok' flag so consumers can branch on 'ok' without walking
    the dict.
    """
    if not err_dict:
        return {"ok": True, "error_count": 0, "field_errors": {}}
    return {
        "ok": False,
        "error_count": sum(len(v) if isinstance(v, list) else 1
                           for v in err_dict.values()),
        "field_errors": err_dict,
    }


def validate_xdi(url: str) -> dict[str, Any]:
    """Run the XDI/1.0 spec validator against the input file and return
    a summary dict safe to include in an HTTP response.

    The return shape is always:
        {
            "ok": bool,           # True iff zero errors
            "error_count": int,   # total messages across all fields
            "field_errors": {...} # xdi_validator's per-field error map
            "note": str,          # optional; explains skips/failures
        }

    Never raises — infrastructure errors (missing package, unreachable
    URL, missing end-of-header) become 'note' entries on the summary.
    """
    try:
        from xdi_validator import validate, XDIEndOfHeaderMissingError
    except ImportError:
        return {
            "ok": True,
            "error_count": 0,
            "field_errors": {},
            "note": "xdi_validator package not installed; skipped XDI "
                    "spec check. pip install xdi-validator",
        }

    try:
        text = _load_xdi_text(url)
    except Exception as e:
        return {
            "ok": True,
            "error_count": 0,
            "field_errors": {},
            "note": f"could not read XDI for pre-validation: {e}",
        }

    try:
        xdi_errors, _xdi_dict = validate(io.StringIO(text))
    except XDIEndOfHeaderMissingError as ex:
        return {
            "ok": False,
            "error_count": 1,
            "field_errors": {},
            "note": f"XDI end-of-header missing: {getattr(ex, 'message', str(ex))}",
        }
    except Exception as e:
        return {
            "ok": True,
            "error_count": 0,
            "field_errors": {},
            "note": f"xdi_validator raised {type(e).__name__}: {e}",
        }

    return _summarize_errors(xdi_errors)
