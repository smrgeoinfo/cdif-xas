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
pipeline never hard-fails — seven fallback strategies keep validation
green when the source is thin. Verified 37/37 fully valid on the
XAS-CDIF/exampleData corpus (JSON Schema + SHACL). Full detail of
each strategy is in [AGENTS.md](./AGENTS.md#graceful-degradation-pattern);
brief summary here.

**Sentinel-value conventions:**

- `"Missing"` for absent required text/name fields.
- `"unknown"` for absent required numeric/enumerated fields where a
  domain expert must supply the real value later.
- `<http://www.opengis.net/def/nil/OGC/0/missing>` (OGC Rainbow
  nil-value IRI) for absent required URI-shape values.

**Strategies:**

1. **No Dataverse instance** → `api/local_input.py:build_placeholder_dataset`
   synthesizes a minimal `schema:Dataset` (identifier, name,
   dateModified, license, distribution, placeholder author with name
   "Missing", contentUrl `https://w3id.org/cdif/testing/{filename}`).
2. **xasCore-required content missing** (`Mono.d_spacing`,
   `Beamline.name`, `Facility.name`) → `api/cdi.py:_add_xas_fallback_triples`
   injects sentinel triples into the SKOS graph. Real data is never
   overwritten. Scaffolded to add more fields easily.
3. **Optional sub-property TriplesMaps emit incomplete PropertyValues**
   → `api/Mapper.py:_drop_incomplete_additional_properties` strips
   any `schema:additionalProperty` entry missing `schema:value`.
4. **Non-strict-ISO datetimes** on `Scan.start_time` /
   `Scan.end_time` → `api/cdi.py:_normalize_datetime` converts
   recognized forms (space-separated ISO, slash-date, US m/d/y,
   date-only, basic ISO) to canonical `YYYY-MM-DDTHH:MM:SS` at
   parse time. Preserves `skos:prefLabel` order the RML indexes.
5. **Non-canonical XDI header case + missing `# Column.N:` headers**
   → parse-time normalization in `api/cdi.py:parse_xdi`. Case:
   lowercase everything after the first `.` so `Facility.Name` /
   `Beamline.Name` populate canonical `cdi:*_name` predicates.
   Array-labels-line: synthesize `cdi:Column_N` from whitespace tokens
   in the last `#`-comment before data when the graph has no
   `cdi:Column`.
6. **Shape name-or-identifier constraints** on Person / Organization
   / Role / DefinedTerm → four post-frame passes in
   `api/Mapper.py` (`_ensure_person_has_name_or_identifier`, etc.)
   inject `"Missing"` or an OGC nil IRI only when both alternatives
   are absent.
7. **JSON-LD blank-node identifiers** (`_:xxx`) rejected by
   plain-JSON validators → `api/Mapper.py:_materialize_blank_node_ids`
   rewrites them to `ex:blank/xxx` IRIs (uses the `ex:` prefix
   bound in `resources/context.json`).

The result is an honest artifact: fields that were in the input come
through as-is, fields synthesized by fallback are visibly marked with
sentinel values (`"Missing"`, `"unknown"`, or the OGC nil IRI), and
optional fields with no source data are omitted rather than emitted
malformed.

## Header normalisation

`api/cdi.py` normalises several XDI header values before the RML
mapping sees them, because real files do not always conform and the
downstream schemas do not bend.

| header | normalisation |
|---|---|
| `Scan.start_time`, `Scan.end_time` | non-ISO forms parsed to ISO 8601 |
| `Sample.temperature` | `room temperature` → `295.0 K`, recorded in the dataset description; `10K` → `10 K` |
| `Scan.edge_energy`, `ScanParameters.E0` | a bare number gains `units not reported` |
| `Mono.name` | split into `cdi:Mono_crystal` and `cdi:Mono_reflection` |
| Column headers | detection mode derived as `cdi:Scan_mode` |

Two of these are worth understanding rather than just knowing about.

**`Sample.temperature` is genuinely non-conformant, not a validator
bug.** The XDI dictionary specifies *float + units* for that tag, so
`room temperature` does not conform and the validator is right to reject
it. But 188 of the 272 files in the XAS Data Library give a qualitative
temperature and nothing else, so refusing to convert them would discard
the only temperature information they carry. The substitution is
recorded in `schema:description` rather than applied silently — 295 K is
a stand-in, not a reading.

**Unit-less energies are flagged, not filled in.** Deliberately not
`eV`, though every edge energy in this corpus is in eV and the guess
would be right every time. The file does not say so, and a converter
that supplies units nobody wrote is indistinguishable from one that read
them.

### Before adding an `rr:constant`

Three constants in `mapping_dds.ttl` turned out to be latent data bugs:
the reflection plane (`"1,1,1"`, wrong for 13 of 55 files), the crystal
type (`"Si"`, right for all 55 by luck), and the detection mode
(`"Transmission"`, wrong for the one fluorescence file). Each produced
plausible metadata that validated cleanly, and none could have been
caught by the pipeline itself.

They share a cause: RML cannot parse a string or branch on a condition,
so a constant is the only thing available wherever the data needs
interpreting. The fix in each case was to derive the value in
`api/cdi.py`, expose a key, and reference it — which is the pattern the
table above documents.

A constant is right for a property **label** and for a value the
**format itself** determines. It is wrong anywhere the answer varies
with the file. See `AGENTS.md` for the full account, and
`CONVERGENCE-PROPOSAL.md` for what it implies architecturally.

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