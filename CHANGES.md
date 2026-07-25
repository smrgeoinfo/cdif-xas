# cdif-xas-UKDS — uplift to CDIF xasDocument/1.0

Analysis and patch plan, 2026-07-24. **Not applied** — this file
describes the changes; no code is modified in this commit.

## What this repo does today

FastAPI service (`api/api.py`) with two pipelines that both target the
same output — a framed JSON-LD document conforming to a CDIF profile:

1. **`/cdif`** (Python custom): parses an XDI header line-by-line
   (`api/cdi.py:parse_xdi`), enriches with Dataverse's schema.org export,
   frames via `pyld` (`api/cdif.py:generate_cdif`), inlines blank-node
   refs, returns JSON. Simpler but less structured.
2. **`/map`, `/frame`, `/validate`** (RML): shells out to
   `rmlmapper-8.1.0-r0-all.jar` with `resources/mapping_dds.ttl` (1501-line
   RML), produces `cdif_dds.jsonld` → framed to `cdif_dds_framed.jsonld` →
   validated against a bundled StructuredSchema. This is where the real
   structural transformation happens.

Reference output today: `resources/cdif_dds_framed.jsonld`. It declares
conformance to `core/1.1 + discovery/1.1 + data_description/1.1 +
data_structure/1.1` — a CDIF DDS record that describes XAS data, but
does **not** declare the two XAS conformance tiers (`xasCore/1.0`,
`xasOptional/1.0`) and therefore would not validate against the current
`xasDocument/1.0` profile.

The same file was adapted upstream into
`metadataBuildingBlocks/_sources/profiles/cdifCompositeProfile/xasDocument/example_dds_framed.json`
— see `CHANGES-from-UKDS.md` in that directory for the full transformation
log. That adapted file is the reference for what the current output
*should* look like.


## Part 1 — Local-runnability (unblocks XDI testing off the shelf)

Currently the service assumes:
- A running Dataverse instance to fetch XDI files via `requests.get(url)`
  and to enrich with schema.org via `?exporter=schema.org&persistentId=`.
- Docker paths (`/app/resources`, `/files/lib/rmlmapper-8.1.0-r0-all.jar`).

To point it at local XDI files with no Docker and no Dataverse:

### 1.1 Accept local file paths in `/cdif` (small)

`api/cdi.py:CDI_DDI.__init__` line 29–32:
```python
if url:
    self.response = requests.get(url)
```

`requests.get` does not handle `file://` URIs. Change to:

```python
if url:
    if url.startswith("file://") or url.startswith("/") or (len(url) > 1 and url[1] == ":"):
        # Local path — file://, absolute POSIX, or Windows drive path
        path = url.removeprefix("file://")
        from types import SimpleNamespace
        self.response = SimpleNamespace(text=Path(path).read_text(encoding="utf-8"))
    else:
        self.response = requests.get(url)
```

(Uses `Path` which is already imported.) One-line docs update in the
`/cdif` endpoint would say it accepts `file:///…` or absolute paths.

### 1.2 Make the Dataverse enrichment truly optional

`api/cdi.py:generate_cdi` lines 141–162 already wrap the enrichment
`rdflib.Graph.parse(schema_url)` in `try/except Exception: pass`, so a
missing/unreachable Dataverse doesn't block. Fine as-is, but the
`datasetid=None` path (line 152) still tries the hardcoded
`dataverse.dev.codata.org` URL. When running locally, pass an empty
`datasetid=""` or add an explicit `--no-enrich` toggle to skip the block
entirely rather than relying on the network to fail.

### 1.3 Portable path resolution for `Mapper.py`

`api/Mapper.py` hardcodes container paths (`/files/…`,
`/app/resources/…`). For local runs of the RML pipeline:

```python
# Replace top-level constants with:
BASE_DIR = str(Path(__file__).parent.parent)              # repo root
RESOURCES_DIR = str(Path(BASE_DIR) / "resources")
MAPPER_JAR = os.environ.get(
    "RMLMAPPER_JAR",
    str(Path(BASE_DIR) / "lib" / "rmlmapper-8.1.0-r0-all.jar"),
)
```

Users then either drop the JAR at `<repo>/lib/rmlmapper-8.1.0-r0-all.jar`
or set `RMLMAPPER_JAR=/path/to/jar`.

### 1.4 Minimal local run

With 1.1 + 1.3 applied you can run the service without Docker:

```bash
uv run uvicorn api.api:app --reload --port 8000
curl "http://localhost:8000/cdif?url=file:///path/to/data.xdi&type=xas"
```

The Python `/cdif` pipeline needs only 1.1 to become locally usable. The
RML `/map` pipeline needs 1.1 + 1.3 **plus** the `rmlmapper` JAR.

**Does the content-correctness uplift (Part 2 below) enable local
running?** No — Part 1 and Part 2 are independent. The Part 2 patches
change *what* the pipeline emits; Part 1 changes *where the input comes
from and where the JAR lives*. Do Part 1 first if the goal is to test
against local XDI files; run the current uplifted mapping against
whatever gives you the fastest feedback loop.


## Part 2 — Content-correctness uplift (bring output onto xasDocument/1.0)

Enumerated by file. Line numbers are from HEAD as of 2026-07-24.

### 2.1 `resources/mapping_dds.ttl` — the RML mapping

#### 2.1.1 Namespace rebind (mechanical, ~15 places)

Prefix declaration (top of file):
```
- @prefix xas:     <https://ada.astromat.org/metadata/xas/> .
+ @prefix xas:     <https://w3id.org/cdif/xas/> .
```

IRI-literal occurrences of the old base (must be updated in tandem):
lines **160, 703, 723, 771** (the `provevent` activity IRI); change all
four from `<https://ada.astromat.org/metadata/xas/provevent>` to
`<https://w3id.org/cdif/xas/provevent>`.

All prefix-compact usages (`xas:foo`, ~11 places at lines 246, 749, 844,
909, 943, 977, 1027, 1086, 1113, 1152, 1186) become correct
automatically once the prefix is rebound.

#### 2.1.2 Concept URI renames (mechanical, v1 → v2 glossary local names)

Applied to `rr:constant` values on `xas:` and to any templated
`"xas:" + ...` fragments:

| Line | Old | New |
|-----:|-----|-----|
| 749 | `xas:edge_energy` | `xas:edgeenergy` |
| 977 | `xas:harmonic_rejection` | `xas:harmonicrejection` |
| 1086 | `xas:d_spacing` | `xas:dspacing` |
| 1152 | `xas:I0` | `xas:detectori0` |
| 1186 | `xas:I1` | `xas:detectorit` |
| 907 | `xas:collimation` | *(no change)* |
| 943 | `xas:focusing` | *(no change)* |

Human-readable `schema:name` values on those PropertyValues should track
the rename (`d_spacing` → `d-spacing`, `harmonic_rejection` →
`harmonic rejection`, `I0` → `incident-flux detection method`, etc.) at
lines 990 (harmonic_rejection), 1093 (d_spacing), 1165 (I0), 1199 (I1).
See the reference `example_dds_framed.json` for the exact naming used.

Also: the instrument identifiers built via templates at lines 826 (Beamline
`schema:identifier`), 1009 (Mono), 1113 (Detector) currently emit
`"xas:Beamline/13-BM-D"`, `"xas:Mono/Si 111"`, `"xas:Detector"` as bare
strings. These aren't required by xasDocument (identifier is optional),
but if kept they should be `rr:termType rr:IRI` — see 2.1.3.

#### 2.1.3 JSON-LD IRI-reference policy (mechanical, ~4 places)

The current SHACL policy `PropertyIDUriShouldBeIRIShape` /
`AdditionalTypeUriShouldBeIRIShape` (aggregated in `xasDocumentRules.shacl`)
requires URI-shape values on `schema:additionalType` and
`schema:propertyID` to be JSON-LD IRI references (`{"@id":"..."}`),
not string literals. In RML that means the object map has
`rr:termType rr:IRI` (or is generated via a joining TriplesMap), not a
`rr:constant` string.

Files that emit bare strings (need `rr:termType rr:IRI` added):

- **Line 365** (`TriplesMap_subjectOf`, `schema:additionalType`):
  `rr:constant "dcat:CatalogRecord"` → `rr:constant dcat:CatalogRecord;
  rr:termType rr:IRI`. (Note the prefix form vs. quoted string.)
- **Line 228** (`TriplesMap_variableMeasured`, `schema:propertyID`):
  currently an FnO-computed `"xas:" + $meaning` string. Rewrite the
  function to produce a full IRI and mark `rr:termType rr:IRI`.

Bare-string identifiers (optional, but worth cleaning up while you're
here): lines 826, 1009, 1113 as noted above.

#### 2.1.4 Add xasCore + xasOptional conformance URIs (mechanical, additive)

`TriplesMap_subjectOf`, lines 370–397 (the `dcterms:conformsTo`
predicate-object maps). The current list emits four IRIs:

- `https://w3id.org/cdif/core/1.1`
- `https://w3id.org/cdif/discovery/1.1`
- `https://w3id.org/cdif/data_description/1.1`
- `https://w3id.org/cdif/data_structure/1.1`

Add two more object maps to the same predicate group:

- `https://w3id.org/cdif/xasCore/1.0`
- `https://w3id.org/cdif/xasOptional/1.0`

Six total. Pattern: copy any existing `rr:predicateObjectMap` block that
emits one of the current URIs, change the `rr:constant` value, and
duplicate.

#### 2.1.5 Restructure `prov:used` to peer instrument model (editorial)

Current shape (single wrapper, three peer instruments inside):

```
Activity
  prov:used _:b   <- one blank node
    schema:instrument Beamline
    schema:instrument Mono
    schema:instrument Detector
```

xasCore expects one wrapper per instrument:

```
Activity
  prov:used _:b1
    schema:instrument Beamline
  prov:used _:b2
    schema:instrument Mono
  prov:used _:b3
    schema:instrument Detector
```

Concretely in `mapping_dds.ttl`:
- `TriplesMap_prov_used_entity` currently emits ONE entity with three
  `schema:instrument` predicates (lines 793–810). Split into three
  separate TriplesMaps, one per instrument, each emitting one blank-node
  entity with one `schema:instrument` predicate.
- `TriplesMap_activity_used` (the parent) should generate **three**
  `prov:used` predicate-object maps, one for each new instrument wrapper.

Same result via a different route: keep the current single
`prov_used_entity`, remove the `schema:instrument` triple from it, and
add three new TriplesMaps that each set `prov:used` on the activity via
a joining subject map. Either works; splitting is cleaner.

#### 2.1.6 Add a source-instrument wrapper (editorial, new content)

xasCore requires a fourth instrument peer: the X-ray source itself,
distinct from the beamline. Not present in the current XDI input, so
this needs either:
- A default emission (`rr:constant`) block if the XDI doesn't carry
  source info (`xas:xraysourcetype = "Synchrotron X-ray Source"`,
  `xas:probe = "x-ray"`); or
- An input schema change so the XDI parser reads `xas:Source` metadata
  and populates it through the mapping.

The current `example_dds_framed.json` in mBB uses the default-emission
approach with "APS bending magnet source" as the sample value.

#### 2.1.7 Add `schema:object` MaterialSample (editorial, new content)

xasCore requires the activity to carry a `schema:object` pointing at the
material sample. Structure:

```
Activity
  schema:object
    @type [schema:Thing, schema:Product]
    schema:additionalType ["MaterialSample", {@id: <isample URI>}]
    schema:name  <sample chemical name from XDI>
    schema:additionalProperty [
      { propertyID xas:samplepreparation, value "..." },
      ... optional xas:porosity, xas:ph, xas:temperature ...
    ]
```

The XDI header typically has `Sample.name`, `Sample.prep`, `Sample.formula`
fields that map to this. If not present in the input, emit at least the
type + name (which the parser already captures as `xas:Sample_name` or
similar) and let the additionalProperty list default to empty.

New TriplesMaps to add:
- `TriplesMap_activity_object` — emits `schema:object` on the Activity,
  linking to a subject built from Sample.name.
- `TriplesMap_sample` — emits the sample subject with @type,
  additionalType, name.
- `TriplesMap_sample_prep`, `TriplesMap_sample_porosity`, etc. — one per
  optional sample additionalProperty.

#### 2.1.8 Add measurementTechnique + keywords (editorial, new content)

Two `schema:measurementTechnique` DefinedTerms — one for the acquisition
mode (Transmission / Fluorescence / …) and one for XAS classification
(PaNET term). The current mapping has `TriplesMap_nexus` and
`TriplesMap_panet` (both DefinedTerms) but neither is wired to
`schema:measurementTechnique` on the root dataset — they emit standalone
nodes. Add predicate-object maps on `TriplesMap_root` that point at
those two TriplesMaps' subjects.

Two `schema:keywords` DefinedTerms — the K-edge and the element symbol.
`TriplesMap_keywords_element_edge` and
`TriplesMap_keywords_element_symbol` are in the mapping but again not
wired into `TriplesMap_root`. Add two `schema:keywords`
predicate-object maps.

Both edge and symbol entries need `schema:about "element.edge"` /
`schema:about "element.symbol"` markers (glossary tooling annotation)
per the current xasCore convention. The symbol entry needs
`schema:identifier` from SWEET (`http://sweetontology.net/matrElement/Se`)
and `schema:inDefinedTermSet` set to
`http://sweetontology.net/matrElement`.

#### 2.1.9 Add `xas:analysisevent` on the activity (mechanical, additive)

`TriplesMap_scan` (line ~703) needs a new predicate-object map:

```
schema:additionalType { @id: xas:analysisevent }
```

xasCore's SHACL requires the activity to carry this typing marker in
addition to `schema:Action + prov:Activity`.

### 2.2 `resources/CDIFDiscoveryDataDescriptionStructureProfileStructuredSchema.json`

Refresh from the current mBB build. Either:

- **Copy from an active release repo**: the closest match to the
  current bundled file is
  `C:\GithubC\CDIF\doc-discoverydatadescriptionstructure\CDIFDiscoveryDataDescriptionStructureProfileStructuredSchema.json`
  (which we just synced on 2026-07-24, commit `20fbb57`). This has the
  post-URI-serialization-policy schema shapes but no XAS extension.
- **Or swap to the XAS document profile schema** by replacing the
  bundled file with
  `C:\GithubC\CDIF\XAS-CDIF\release\cdifXASDocumentStructuredSchema.json`
  (from the `cdifxasRelease` branch of XAS-CDIF). This is what a
  conformant XAS document actually validates against.

If you swap: `Mapper.py:validate` also needs to point at the new schema
path (`DDS_SCHEMA_PATH` constant, line 26).

### 2.3 `resources/CDIFDiscoveryDataDescriptionStructure-frame.jsonld`

The JSON-LD frame determines what gets embedded and how the output
tree is shaped. If validating against xasDocument/1.0 the frame should
be adjusted to include XAS-specific slots (`prov:wasGeneratedBy`,
`schema:object` sample, `schema:measurementTechnique`, `schema:keywords`).

Currently the frame is DDS-only. Two options:

- Extend it with the extra top-level slots (safest — keeps the DDS
  behavior).
- Swap for
  `C:\GithubC\CDIF\XAS-CDIF\release\cdifXASDocument-frame.jsonld`
  (currently just a copy of the Core frame — the XAS-specific slots
  aren't in it yet, so this is not automatically an upgrade).

Frame updates aren't strictly required to validate: framing is a
transformation, not a filter of what can pass validation. But the
framed output structure matters for downstream consumers.

### 2.4 `resources/context.json` and namespace bindings

The framed output currently uses:

```json
"xas": "https://ada.astromat.org/metadata/xas/"
```

Update to `"https://w3id.org/cdif/xas/"`. Also inspect `context.json`
(if it's what feeds `Mapper.py:CONTEXT_PATH`) and update the `xas:`
binding there too.

### 2.5 `api/cdif.py` — the Python framer

Line 43–56 hardcodes a JSON-LD context with `xas:` bound to
`http://ddialliance.org/Specification/XAS/`. That's a **third** namespace
(neither the old astromat one nor the current w3id one). Rebind to
`https://w3id.org/cdif/xas/` for consistency.

Line 77 hardcodes `xas_ns = "http://ddialliance.org/Specification/XAS/"`.
Same rebind.

### 2.6 `api/cdi.py` — the XDI parser

The parser doesn't emit `xas:` triples directly (it uses SKOS with a
`https://ddi-cdi.org/label/` namespace as the primary vocabulary), so no
`xas:` changes needed there. But if the parser is later reworked to
emit `xas:` triples directly (bypassing the intermediate SKOS
representation and the RML mapping), the same URI-serialization policy
applies: URI-shape values on additionalType/propertyID must be IRI nodes.

### 2.7 `resources/xas_core_amended.jsonld` and `xas_metadata_amended.jsonld`

Small (49 + 252 lines). These appear to be reference inputs / annotation
overlays used by the mapping. Inspect and update any `xas:` prefix
bindings and concept URI names using the same rename table above.


## Part 3 — Suggested rollout order

1. **Part 1.1 + 1.3** (~30 min): enable local file input + portable
   `RMLMAPPER_JAR`. Unblocks testing with your local XDI files against
   the *current* mapping. Confirms the harness works end-to-end before
   changing semantics.
2. **Part 2.1.1 + 2.1.2 + 2.1.4** (~1 h): namespace rebind, concept
   renames, add two conformsTo URIs. Purely mechanical; produces output
   with the correct URIs but not the full xasCore structure.
3. **Part 2.1.3 + 2.1.9** (~30 min): @id-form policy + xas:analysisevent
   typing. Clears the URI-serialization SHACL shape violations.
4. **Part 2.2 + 2.4 + 2.5** (~30 min): refresh bundled schema, fix
   `xas:` bindings in `cdif.py`. Validation now targets the current
   schema.
5. **Part 2.1.5 + 2.1.6 + 2.1.7 + 2.1.8** (variable, several hours):
   editorial content — peer prov:used restructure, source instrument,
   sample MaterialSample, measurementTechnique + keywords. This is the
   substantive domain work; needs review of the XDI header fields your
   input files actually carry to decide what to emit statically vs. what
   to read from input.

After each step, regenerate `cdif_dds_framed.jsonld` and re-run
validation to confirm forward progress. The reference target is
`_sources/profiles/cdifCompositeProfile/xasDocument/example_dds_framed.json`
in mBB.


## Testing

After Part 1: `curl 'http://localhost:8000/cdif?url=file:///…/data.xdi'`.
After Part 2: validate the framed output against xasDocumentRules.shacl:

```bash
pyshacl -s xasDocumentRules.shacl -f table \
    -df json-ld resources/cdif_dds_framed.jsonld
```

(SHACL rules file lives in the `cdifxasRelease` branch of XAS-CDIF at
`release/xasDocumentRules.shacl`, or in mBB at
`_sources/profiles/cdifCompositeProfile/xasDocument/rules.shacl`.)

Goal: 0 violations. Warnings are OK.
