# AGENTS.md — cdif-xas-UKDS

Orientation for future Claude Code (or human) sessions working on this
repository.

## What this repo is

A FastAPI microservice that converts XDI (XAS Data Interchange) files
into CDIF-XAS JSON-LD metadata. Two pipelines:

- **`/cdif`** — Python-only. Parses XDI header → SKOS graph → JSON-LD
  frame (`api/cdif.py`) → returns the framed JSON. Faster; used for
  quick end-to-end runs.
- **`/map` → `/frame` → `/validate`** — RML-driven. Reads
  `resources/cdif_skos.json`, runs `rmlmapper-*.jar` per
  `resources/mapping_dds.ttl`, frames the RML output, validates against
  the bundled JSON Schema. This is the pipeline that produces the
  full-shape CDIF XAS document.

`/cdif` writes `resources/cdif_skos.json` as a side effect (unless
`?write_skos=false`), so the two pipelines chain: `/cdif` prepares
input for `/map`.

Target profile: **`https://w3id.org/cdif/xasDocument/1.0`** — a
six-profile composite (core + discovery + data_description +
data_structure + xasCore + xasOptional). Resolved schema and aggregated
SHACL are bundled at
`resources/cdifXASDocumentResolvedSchema.json` and
`resources/xasDocumentRules.shacl` respectively.

## Working branches

- **`main`** — the upstream state; do not push here without deliberate
  intent.
- **`local-xdi-input`** — active development branch adding local XDI
  file input (via `file://` or absolute paths), placeholder Dataverse
  metadata, portable path resolution for `rmlmapper`, xasDocument/1.0
  uplift of the RML mapping, and XDI pre-validation. See
  [`UPLIFT-INSTRUCTIONS.md`](./UPLIFT-INSTRUCTIONS.md) on the
  `analysis-uplift-to-xasdocument` branch for the plan.
- **`analysis-uplift-to-xasdocument`** — analysis-only branch carrying
  `CHANGES.md` and `UPLIFT-INSTRUCTIONS.md`. Meant to be forwarded to
  Deirdre; no code edits here.

## Graceful-degradation pattern

The pipeline never hard-fails on missing metadata. Seven coordinated
strategies keep validation green when the source is thin. Verified
37/37 fully valid on the XAS-CDIF/exampleData corpus (JSON Schema +
SHACL against the smrgeoinfo/XAS-CDIF@cdifxasRelease release/
artifacts).

**Sentinel-value conventions used throughout:**

- `"Missing"` — text placeholder for a required `schema:name` /
  identifier-string field when the source is genuinely absent.
- `"unknown"` — text placeholder for a required numeric / enumerated
  field where a domain expert must supply the real value later.
- `<http://www.opengis.net/def/nil/OGC/0/missing>` — IRI sentinel
  (OGC Rainbow nil-value vocabulary) for required URI-shape values
  like an absent `schema:identifier` on a DefinedTerm or an absent
  Role `schema:contributor`.

**Strategies:**

1. **No Dataverse instance** → `api/local_input.py:build_placeholder_dataset`
   synthesizes a minimal `schema:Dataset` from file name + mtime.
   Emits a Dataverse-shaped `@id`
   (`http://localhost:8080/citation?persistentId=perma:DV/<stem>`) so
   the RML iterator matches without dialect handling. Also emits a
   placeholder `schema:author` (Person with `schema:name = "Missing"`)
   and a `schema:distribution` with `schema:contentUrl` =
   `https://w3id.org/cdif/testing/{filename}` (a dereferenceable
   HTTPS placeholder — real data comes from Dataverse in production).
2. **xasCore-required content missing** (e.g., `Mono.d_spacing`,
   `Beamline.name`, `Facility.name`) → `api/cdi.py:_add_xas_fallback_triples`
   injects a placeholder triple into the SKOS graph AFTER
   `parse_xdi()` and BEFORE JSON-LD serialization. Fires only when
   the source key is genuinely absent; never overwrites real data.
   Uses `"unknown"` for numeric/enumerated fields, `"missing"` for
   identifier/name fields. Scaffolded to add more cases easily.
3. **Optional sub-property TriplesMaps emit incomplete PropertyValues**
   (e.g., `Beamline.collimation` when the header is absent — the
   TriplesMap fires on `cdi:Beamline` existence, then its value
   `rml:reference` resolves to null, and a `schema:PropertyValue`
   with no `schema:value` is emitted) →
   `api/Mapper.py:_drop_incomplete_additional_properties` runs
   inside `frame()` and recursively strips any
   `schema:additionalProperty` entry that lacks `schema:value`.
   Complete entries (including placeholder `"unknown"` from strategy 2)
   pass through untouched.
4. **Non-strict-ISO datetime headers** (space separator, slash-date,
   US m/d/y, date-only, basic ISO) → `api/cdi.py:_normalize_datetime`
   runs at parse time on the keys in `_DATETIME_KEYS`
   (`Scan.start_time`, `Scan.end_time`), converting recognized forms
   to canonical `YYYY-MM-DDTHH:MM:SS` before the SKOS triples are
   written. Unparseable values pass through unchanged. Normalize at
   parse-time rather than as a post-graph sweep — the RML mapping
   picks the datetime out of `$['skos:prefLabel'][2]`, which is
   position-sensitive, and rdflib graph edits after the fact don't
   guarantee the JSON-LD serialization keeps the same order.
5. **Non-canonical XDI header case + missing `# Column.N:` headers**
   (`api/cdi.py:parse_xdi`) — real files vary. Two parse-time
   normalizations:
   - **Case**: everything after the first `.` in a compound key
     lowercases, so `Facility.Name` / `Beamline.Name` /
     `Mono.D_Spacing` / `Scan.Start_Time` all populate the
     canonical `cdi:Facility_name` / `cdi:Beamline_name` /
     `cdi:Mono_d_spacing` predicates the RML mapping expects.
     First segment stays capitalized (the RML vocab has
     `cdi:Beamline`, `cdi:Mono`, `cdi:Facility`).
   - **Array-labels-line back-fill**: capture the last `#`-comment
     line before the first data row; if the graph has no
     `cdi:Column` subject after header parsing, synthesize
     `cdi:Column` + `cdi:Column_N` triples from whitespace-separated
     tokens in that line. XDI files that omit `# Column.N:` headers
     but carry column names on the array-labels line still produce a
     complete data structure.
6. **Shape name-or-identifier constraints on Person / Organization /
   Role / DefinedTerm** — four post-frame passes in
   `api/Mapper.py` inject sentinels only when both alternatives are
   absent:
   - `_ensure_person_has_name_or_identifier` → `schema:name = "Missing"`
   - `_ensure_organization_has_name_or_identifier` → `schema:name = "Missing"`
   - `_ensure_role_has_contributor` → `schema:contributor = {@id: OGC nil}`
   - `_ensure_definedterm_has_name_or_identifier` → `schema:identifier = {@id: OGC nil}`
7. **JSON-LD blank-node identifiers rejected by plain-JSON validators**
   → `api/Mapper.py:_materialize_blank_node_ids` rewrites every
   `_:xxx` `@id` (both node subjects and object references) to
   `ex:blank/xxx` so tools like Oxygen JSON validation don't flag
   the `_:` syntax as an invalid URI. Uses the `ex: https://example.org/`
   prefix bound in `resources/context.json`. Runs last inside
   `frame()` so all other passes still see the original blank IDs.

**XDI/1.0 spec violations** in the input → surfaced in the `/cdif`
response as an `xdi_validation` object; do not block CDIF generation.

### Lessons from getting these to work

- **RMLMapper's JSONPath does NOT support compound predicates.** The
  parser (`org.jsfr.json.compiler.JsonPathParser`) throws
  `ParseCancellationException` on `&&` or `!` inside `[?(...)]`
  filters. All iterators must be simple single-predicate filters.
  For any "fire only when X exists"-style logic, use Python injection
  (strategy 2 above) instead of trying to filter at the iterator.
- **`/cdif` must always run before `/map` on new XDI input.** `/map`
  reads `resources/cdif_skos.json`, which is written by `/cdif`. A
  stale `cdif_skos.json` means `/map` processes yesterday's data.
  If validation errors don't respond to fixes, first check the
  `LastWriteTime` of `cdif_skos.json` vs the current time — the most
  common failure mode is "the fix landed but the pipeline didn't
  actually re-run."
- **When `/map` fails, look at the uvicorn stderr, not the endpoint
  response.** `api/Mapper.py:map()` now prints the JVM stdout+stderr
  around a big `============= RMLMapper FAILED =============` banner
  when the subprocess exits non-zero, then re-raises. Prior
  swallowed-stderr behavior turned real errors into opaque 500s.
- **JSON-LD framing wraps values inconsistently.** A frame entry with
  `{"@embed": "@always"}` on a scalar-valued predicate can cause pyld
  to wrap the value in an array (e.g., `["decimal"]` instead of
  `"decimal"`), which then fails schemas that expect a string.
  Use bare `{}` on predicates whose target values should stay scalar.

## XDI pre-validation

`/cdif` runs the input through the third-party `xdi_validator` package
(MIT, by **A. A. Alves Jr.**;
<https://github.com/AAAlvesJr/XDI-Validator>) before generating CDIF.
Results embed as `xdi_validation` in the response. Wrapper at
`api/xdi_precheck.py`. See README for citation and license note.

## Key files

| File | Role |
|------|------|
| `api/api.py` | FastAPI routes |
| `api/cdi.py` | XDI parser + fallback triple injection |
| `api/cdif.py` | JSON-LD framing / blank-node inlining |
| `api/Mapper.py` | RML pipeline driver (map / frame / validate) |
| `api/local_input.py` | file:// detection + placeholder Dataset |
| `api/xdi_precheck.py` | XDI/1.0 spec pre-validation wrapper |
| `api/FrameAndValidate.py` | JSON-LD framing + JSON Schema validation |
| `resources/mapping_dds.ttl` | RML mapping (1500+ lines) |
| `resources/CDIFDiscoveryDataDescriptionStructure-frame.jsonld` | JSON-LD frame |
| `resources/cdifXASDocumentResolvedSchema.json` | Target JSON Schema |
| `resources/xasDocumentRules.shacl` | Aggregated SHACL rules |
| `resources/cdif_skos.json` | Intermediate SKOS input for `/map` (regenerated by `/cdif`) |
| `resources/cdif_dds.jsonld` | RML output (regenerated by `/map`) |
| `resources/cdif_dds_framed.jsonld` | Framed output (regenerated by `/frame`) |

## Running locally

Requires Python 3.11+, Java (for rmlmapper), and `uv`. Path env vars
are honored:

```powershell
$env:RMLMAPPER_JAR = "C:\path\to\rmlmapper-8.1.0-r380-all.jar"
cd C:\path\to\cdif-xas-UKDS
uv sync
uv run uvicorn api.api:app --reload --port 8000
```

Then in a second shell:

```powershell
curl.exe "http://localhost:8000/cdif?url=file:///C:/path/to/data.xdi&type=xas" > out.jsonld
curl.exe "http://localhost:8000/map?profile=Data%20Description%20Structure"
curl.exe "http://localhost:8000/frame?profile=Data%20Description%20Structure"
curl.exe "http://localhost:8000/validate?profile=Data%20Description%20Structure"
```

## Iteration discipline

Every time `/cdif` is not re-run before `/map` on a NEW XDI file, the
RML pipeline consumes the stale `cdif_skos.json` from the last run.
When debugging validation errors that don't seem to respond to mapping
edits, first confirm `/cdif` re-ran (check `cdif_skos.json` mtime).
