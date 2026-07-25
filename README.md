# CDIF-XAS

An updated copy of CDI-XAS:
https://github.com/codata/cdi-xas

# Initialize
```
cp .env_sample .env
```

# Build
```
docker-compose build
```

# Run
Ensure Dataverse is up and running before cdif-xas
```
docker-compose up -d
```

# Local run (no Docker, no Dataverse)

Requires Python 3.13 (`.python-version` pinned, needed by
`xdi_validator`) and Java (needed by `rmlmapper`).

The `/cdif` endpoint accepts a local XDI file path via `file://` URL
or an absolute path. Dataverse's `?exporter=schema.org` enrichment is
skipped and the pipeline synthesizes a minimal schema.org `Dataset`
from the file itself:

- `@id`: `http://localhost:8080/citation?persistentId=perma:DV/<file-stem>`
  (shape chosen so the RML mapping's iterator matches without changes)
- `schema:name`, `schema:identifier`: derived from the file stem
- `schema:dateModified` / `schema:datePublished`: file mtime, typed as `schema:Date`
- `schema:license`: `https://creativecommons.org/licenses/by/4.0/`
  (CDIF metadata default — distinct from any license on the payload
  data, which is unknown in local mode)
- `schema:distribution`: a `DataDownload` whose `contentUrl` points at
  the file's `file://` URI

See `api/local_input.py` for the exact placeholder shape.

```powershell
uv sync
$env:RMLMAPPER_JAR = "$PWD\lib\rmlmapper-8.1.0-r380-all.jar"    # or absolute path
uv run uvicorn api.api:app --reload --port 8000
```

In a second shell, chain the four endpoints. `/cdif` writes
`resources/cdif_skos.json` as a side effect so `/map` consumes THIS
file's data instead of the committed Se_Na2SeO4 fixture:

```powershell
curl.exe "http://localhost:8000/cdif?url=file:///C:/path/to/data.xdi&type=xas" > out.jsonld
curl.exe "http://localhost:8000/map?profile=Data%20Description%20Structure"
curl.exe "http://localhost:8000/frame?profile=Data%20Description%20Structure"
curl.exe "http://localhost:8000/validate?profile=Data%20Description%20Structure"
```

All four return `null` on success (they complete side-effectfully).
`/validate` returns an HTTP 500 when the framed JSON Schema check
fails — the uvicorn terminal shows the specific field-level errors.

Env vars honored:

| Var | Default | Purpose |
|-----|---------|---------|
| `RMLMAPPER_JAR` | auto-discover newest `rmlmapper-*.jar` in `<repo>/lib/` | Path to the RMLMapper jar |
| `CDIF_XAS_BASE_DIR` | repo root | Base dir (Docker uses `/files/`) |
| `CDIF_XAS_RESOURCES_DIR` | `<CDIF_XAS_BASE_DIR>/resources` | Location of mapping, frame, schema, SKOS files |

## Graceful degradation for missing input

Real-world XDI files are often incomplete or spec-noncompliant. The
pipeline never hard-fails — three fallback strategies keep validation
green when the source is thin:

1. **No Dataverse instance** → local mode synthesizes the schema.org
   `Dataset` placeholder above (`api/local_input.py`).
2. **XDI has no `Mono.d_spacing` header** (xasCore-required) →
   `api/cdi.py:_add_xas_fallback_triples` injects a
   `cdi:Mono_d_spacing` triple with value `"unknown"` after parsing
   the XDI but before the RML mapping runs. Extend this function to
   add fallbacks for other xasCore-required fields as new XDI dialects
   surface. **Real data from the XDI is never overwritten** — the
   fallback fires only when the source key is genuinely absent.
3. **Optional sub-property TriplesMaps fire with no value** (e.g.,
   `Beamline.collimation` when the header is absent) → `api/Mapper.py:frame()`
   runs a post-frame filter (`_drop_incomplete_additional_properties`)
   that strips any `schema:additionalProperty` entry missing
   `schema:value`. Complete entries (including placeholder `"unknown"`
   from strategy 2) pass through untouched.

The result is an honest artifact: fields that were in the input come
through as-is, fields synthesized by fallback are visibly marked
`"unknown"`, and optional fields with no source data are omitted
rather than emitted malformed.

## Profile validation

Bundled artifacts (`resources/cdifXASDocumentResolvedSchema.json` and
`resources/xasDocumentRules.shacl`) target the CDIF XAS document
profile at `https://w3id.org/cdif/xasDocument/1.0` — the six-profile
composite (core + discovery + data_description + data_structure +
xasCore + xasOptional). Regenerate them from the release:

```bash
curl -sL -o resources/cdifXASDocumentResolvedSchema.json \
    https://raw.githubusercontent.com/smrgeoinfo/XAS-CDIF/cdifxasRelease/release/cdifXASDocumentResolvedSchema.json
curl -sL -o resources/xasDocumentRules.shacl \
    https://raw.githubusercontent.com/smrgeoinfo/XAS-CDIF/cdifxasRelease/release/xasDocumentRules.shacl
```

Validate a framed output:

```bash
# JSON Schema
python -c "
import json
from jsonschema import Draft202012Validator
schema = json.load(open('resources/cdifXASDocumentResolvedSchema.json'))
doc = json.load(open('resources/cdif_dds_framed.jsonld'))
errs = list(Draft202012Validator(schema).iter_errors(doc))
print(f'{len(errs)} errors')
for e in errs[:10]:
    print(f'  {\"/\".join(str(p) for p in e.absolute_path)}: {e.message[:160]}')
"

# SHACL
pyshacl -s resources/xasDocumentRules.shacl -f table \
    -df json-ld resources/cdif_dds_framed.jsonld
```

**Uplift status.** This branch applies UPLIFT-INSTRUCTIONS.md tasks
1–10 in full (mechanical: namespace rebind, v2 concept renames,
`conformsTo` additions, `@id`-form policy, `xas:analysisevent` +
`schema:Action`, bundled-schema refresh; editorial: peer `prov:used`
instrument model, X-ray source wrapper with static defaults,
MaterialSample sample block reading XDI `Sample.*` headers, DefinedTerm
content enrichment for element edge/symbol, and the graceful-degradation
strategies above). Confirmed end-to-end on both the committed
Se_Na2SeO4 fixture and a real-world Diamond B18 (`262875_PtSn_OCO_Abu_1.xdi`)
file that is itself XDI/1.0-noncompliant.

Known content-dependent gaps that still need domain input to fill
properly (rather than being masked by the fallbacks):

- The synthesized `Mono.d_spacing` = `"unknown"` should be a real value
  derived from the crystal cut (`Si(111)` = 3.1355 Å, `Si(311)` = 1.6376 Å,
  ...). A crystal-cut lookup table in `_add_xas_fallback_triples` would
  auto-fill this.
- XDI files with no `Element.symbol` / `Element.edge` headers (spec
  violation) currently produce no element-keyword DefinedTerms; the
  filter drops the incomplete PropertyValues. Downstream consumers see
  a valid document without element/edge tags. Consider parsing the
  sample formula (`PtSn_OCO_Abu` → Pt) or filename convention if you
  need element info for these dialects.
- `schema:propertyID` on `schema:variableMeasured` items is a GREL
  string_replace that prepends `https://w3id.org/cdif/xas/` to whatever
  `$['meaning']` is (populated by `api/cdif.py`'s column build). Values
  with spaces or mixed case produce non-resolving IRIs. Consider adding
  a v2-normalization step (lowercase, no spaces, no underscores) in the
  column build.

## XDI pre-validation

The `/cdif` endpoint runs the input file through an XDI/1.0 spec
compliance check before generating CDIF. Results are embedded in the
response as an `xdi_validation` object:

```json
{
  "xdi_validation": {
    "ok": false,
    "error_count": 3,
    "field_errors": {
      "Element.symbol": ["...missing..."],
      "Facility.energy": ["...unit must be GeV..."]
    }
  },
  "@context": {...},
  "@graph": [...],
  "columns": [...]
}
```

Validation is warning-only — non-compliant XDI does not block CDIF
generation. The `ok`/`error_count`/`field_errors` structure lets
downstream consumers decide whether to surface the report, request
input corrections, or proceed with the CDIF output as-is. See
[`api/xdi_precheck.py`](./api/xdi_precheck.py) for the wrapper.

### Acknowledgement

The pre-validation step uses the [`xdi_validator`](https://github.com/AAAlvesJr/XDI-Validator)
Python package (MIT-licensed) by **A. A. Alves Jr.** — a standalone
JSON-Schema-based validator that implements the
[XAS Data Interchange Format Draft Specification, version 1.0](https://github.com/XraySpectroscopy/XAS-Data-Interchange/blob/master/specification/xdi_spec.pdf).
`xdi_validator` is included as a runtime pip dependency; no source is
vendored in this repository. If you use `cdif-xas` in published work,
please cite `xdi_validator` alongside — the project has a Zenodo DOI
at <https://doi.org/10.5281/zenodo.20018640>.

## Dependencies

Direct runtime dependencies (see [`pyproject.toml`](./pyproject.toml)):

| Package | Role | License |
|---|---|---|
| [`fastapi`](https://fastapi.tiangolo.com/) | HTTP API framework | MIT |
| [`pyld`](https://github.com/digitalbazaar/pyld) | JSON-LD framing / expansion | BSD-3 |
| [`rdflib`](https://rdflib.readthedocs.io/) | RDF graph handling | BSD-3 |
| [`jsonschema`](https://python-jsonschema.readthedocs.io/) | Draft 2020-12 JSON Schema validation | MIT |
| [`requests`](https://requests.readthedocs.io/) | HTTP client for remote XDI fetch | Apache-2.0 |
| [`xdi_validator`](https://github.com/AAAlvesJr/XDI-Validator) | XDI/1.0 spec pre-validation (see above) | MIT |

The `/map` pipeline additionally uses [`rmlmapper`](https://github.com/RMLio/rmlmapper-java)
(Apache-2.0) as an external Java jar, invoked via subprocess. Set
`$env:RMLMAPPER_JAR` or drop the jar at `<repo>/lib/rmlmapper-*.jar`.