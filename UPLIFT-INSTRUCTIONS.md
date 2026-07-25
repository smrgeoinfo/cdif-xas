# Uplift `cdif-xas-UKDS` output to CDIF `xasDocument/1.0`

> **For Deirdre.** Drop this file into your Claude Code session in the
> `cdif-xas-UKDS` repository root and ask Claude to work through the
> tasks in order. Every reference URL below dereferences to a live file;
> no external context needed.

---

## Why this exists

`cdif-xas-UKDS` currently produces `resources/cdif_dds_framed.jsonld`
that declares conformance to four CDIF 1.1 profiles
(`core`, `discovery`, `data_description`, `data_structure`). That
output does **not** satisfy the current CDIF XAS document profile,
which requires two additional XAS-specific conformance tiers plus
several XAS-mandatory content items.

The target profile is `https://w3id.org/cdif/xasDocument/1.0` — a
document-level composite of six profiles:

| Component | URI | Role |
|-----------|-----|------|
| CDIF Core | `https://w3id.org/cdif/core/1.1` | mandatory dataset discovery |
| CDIF Discovery | `https://w3id.org/cdif/discovery/1.1` | optional discovery |
| CDIF Data Description | `https://w3id.org/cdif/data_description/1.1` | measured variables |
| CDIF Data Structure | `https://w3id.org/cdif/data_structure/1.1` | physical/tabular structure |
| XAS Core | `https://w3id.org/cdif/xasCore/1.0` | XAS-mandatory instrument + sample + technique |
| XAS Optional | `https://w3id.org/cdif/xasOptional/1.0` | XAS-recommended vocabularies |

## Reference files (all URLs live)

- **Implementation Guide** (single source of truth for what the profile
  requires):
  <https://github.com/smrgeoinfo/XAS-CDIF/blob/cdifxasRelease/release/CDIFXASDocumentImplementationGuide.md>
- **Resolved JSON Schema** (Draft 2020-12, fully inlined):
  <https://github.com/smrgeoinfo/XAS-CDIF/raw/cdifxasRelease/release/cdifXASDocumentResolvedSchema.json>
- **Aggregated SHACL rules** (all six components):
  <https://github.com/smrgeoinfo/XAS-CDIF/raw/cdifxasRelease/release/xasDocumentRules.shacl>
- **Reference example** — this repository's own `cdif_dds_framed.jsonld`
  after uplift and adaptation:
  <https://github.com/Cross-Domain-Interoperability-Framework/metadataBuildingBlocks/raw/main/_sources/profiles/cdifCompositeProfile/xasDocument/example_dds_framed.json>
- **Transformation log** — what changed when adapting the UKDS example
  into the reference:
  <https://github.com/Cross-Domain-Interoperability-Framework/metadataBuildingBlocks/blob/main/_sources/profiles/cdifCompositeProfile/xasDocument/CHANGES-from-UKDS.md>
- **XAS SKOS glossary** — authoritative concept URIs (v2 naming):
  <https://w3id.org/cdif/xas/> (browser HTML)
  or `https://w3id.org/cdif/xas/{localname}/jsonld` for per-concept
  SKOS records.

## Files to be modified

Grouped by task order below. Line numbers are HEAD as of 2026-07-24;
verify before editing.

| File | Role |
|------|------|
| `resources/mapping_dds.ttl` | 1501-line RML mapping — the primary transformation |
| `resources/context.json` | JSON-LD prefixes for output |
| `resources/CDIFDiscoveryDataDescriptionStructureProfileStructuredSchema.json` | Bundled schema for validation (refresh) |
| `resources/CDIFDiscoveryDataDescriptionStructure-frame.jsonld` | JSON-LD frame |
| `api/cdif.py` | Python framer — has hardcoded contexts to fix |
| `api/Mapper.py` | Constant `DDS_SCHEMA_PATH` may need updating if schema is renamed |

---

## Task 1 — Rebind the `xas:` prefix (mechanical, low risk)

**Old**: `xas: https://ada.astromat.org/metadata/xas/`
**New**: `xas: https://w3id.org/cdif/xas/`

Locations:

- `resources/mapping_dds.ttl` line ~5 (the `@prefix xas:` declaration).
- `resources/mapping_dds.ttl` lines **160, 703, 723, 771** — IRI-literal
  form `<https://ada.astromat.org/metadata/xas/provevent>` should
  become `<https://w3id.org/cdif/xas/provevent>` in all four places
  (this is the shared Activity IRI).
- `resources/context.json` — the `xas:` binding.
- `api/cdif.py` lines 50 and 54 — hardcoded context has TWO bindings
  that should point at the same v2 URI:
  - `"nx": "https://xas.org/dictionary/"` — replace with `"xas": "https://w3id.org/cdif/xas/"` (or drop if unused)
  - `"xas": "http://ddialliance.org/Specification/XAS/"` — replace with `"xas": "https://w3id.org/cdif/xas/"`
- `api/cdif.py` line 77 — hardcoded string
  `xas_ns = "http://ddialliance.org/Specification/XAS/"` → `xas_ns = "https://w3id.org/cdif/xas/"`.

After this task the prefix-compact forms in the mapping (`xas:foo`) all
automatically point at the correct new base.

---

## Task 2 — Rename XAS concept local names (mechanical, low risk)

CDIF XAS glossary v2 dropped underscores, spaces, and mixed case. The
`cdif-xas-UKDS` mapping uses v1 names; rename each on both the
propertyID `rr:constant` and the human-readable `schema:name`.

| File / line | Old value | New value |
|-------------|-----------|-----------|
| `mapping_dds.ttl` 749 | `xas:edge_energy` | `xas:edgeenergy` |
| `mapping_dds.ttl` 977 | `xas:harmonic_rejection` | `xas:harmonicrejection` |
| `mapping_dds.ttl` 1086 | `xas:d_spacing` | `xas:dspacing` |
| `mapping_dds.ttl` 1152 | `xas:I0` | `xas:detectori0` |
| `mapping_dds.ttl` 1186 | `xas:I1` | `xas:detectorit` |
| `mapping_dds.ttl` 907 | `xas:collimation` | *(unchanged)* |
| `mapping_dds.ttl` 943 | `xas:focusing` | *(unchanged)* |

Update human-readable `schema:name` values in step with these renames
(lines 756, 990, 1093, 1165, 1199). Suggested humanized forms:

| propertyID | Suggested schema:name |
|------------|----------------------|
| `xas:edgeenergy` | Edge energy |
| `xas:harmonicrejection` | harmonic rejection |
| `xas:dspacing` | d-spacing |
| `xas:detectori0` | incident-flux detection method |
| `xas:detectorit` | transmitted-flux detection method |

Full v2 vocabulary is at <https://w3id.org/cdif/xas/> — dereference
any concept URI to see its preferred label.

---

## Task 3 — Add the two XAS conformance URIs to `subjectOf` (additive)

`resources/mapping_dds.ttl`, `TriplesMap_subjectOf`, lines **370–397**
(the `dcterms:conformsTo` predicate-object maps). Currently emits four
IRIs; add two more so the catalog record declares conformance to all
six URIs listed at the top of this document.

Pattern: copy any existing `rr:predicateObjectMap` block that emits one
of the four CDIF URIs, change the `rr:constant`, and duplicate.

Values to add:
```
https://w3id.org/cdif/xasCore/1.0
https://w3id.org/cdif/xasOptional/1.0
```

Order in the array doesn't matter semantically but the reference
example uses discovery/1.1 first, xas tiers last.

---

## Task 4 — Enforce the JSON-LD `@id`-form policy on `additionalType` and `propertyID` (mechanical)

The current `xasDocument/1.0` SHACL enforces a semantic-clarity rule:
any URI or CURIE (`scheme:localname`) value on `schema:propertyID` or
`schema:additionalType` MUST be serialized as a JSON-LD IRI reference
(`{"@id": "..."}`), not as a bare string literal. String literals that
look like URIs do not participate in RDF entailment as resource
references, which defeats the interoperability the URI was intended to
provide.

Free-label strings (`"temperature"`, `"MaterialSample"`) remain valid
as string values. `schema:DefinedTerm` objects also satisfy the rule.

The enforcing shapes (in the aggregated SHACL) are:
- `cdifd:PropertyIDUriShouldBeIRIShape` — targets objects of `schema:propertyID`
- `cdifd:AdditionalTypeUriShouldBeIRIShape` — targets objects of `schema:additionalType`

Both fire at `sh:Violation` severity.

**In RML terms**: an object map that emits a URI-shape value must have
`rr:termType rr:IRI` (or be produced via a joining TriplesMap that
generates an IRI subject). Current `rr:constant "..."` string literals
need this treatment:

1. **Line 365** (`TriplesMap_subjectOf`, `schema:additionalType`):
   ```
   -   rr:object [ rr:constant "dcat:CatalogRecord" ]
   +   rr:object [ rr:constant dcat:CatalogRecord ; rr:termType rr:IRI ]
   ```
   (Note the switch from a quoted string to the prefix-compact CURIE form
   plus the `rr:termType rr:IRI` marker.)

2. **Line 228** (`TriplesMap_variableMeasured`, `schema:propertyID`):
   currently an FnO-computed `"xas:" + $meaning` string. Rewrite the
   function to produce a full IRI (e.g. `https://w3id.org/cdif/xas/{meaning}`)
   and mark the resulting object map `rr:termType rr:IRI`.

3. **Optional** (identifier fields — not required by xasDocument but
   worth cleaning up): lines 826, 1009, 1113 emit
   `"xas:Beamline/13-BM-D"`, `"xas:Mono/Si 111"`, `"xas:Detector"` as
   bare strings. Either convert to IRI form with `rr:termType rr:IRI`
   or drop.

---

## Task 5 — Add `xas:analysisevent` on the activity (mechanical, additive)

`resources/mapping_dds.ttl`, `TriplesMap_scan` (around line 703). The
activity currently has `@type [schema:Event, prov:Activity]`. The
current xasCore requires `@type` to include `schema:Action`
(preferred) and the activity to carry
`schema:additionalType: [{ @id: xas:analysisevent }]`.

Two edits:

1. Change the activity `@type`: replace `schema:Event` with
   `schema:Action` (keep `prov:Activity`). Two `rr:class` lines in
   the subject map, plus any places the subject map is joined.
2. Add a new predicate-object map on `TriplesMap_scan`:
   ```
   rr:predicate schema:additionalType ;
   rr:objectMap [ rr:constant xas:analysisevent ; rr:termType rr:IRI ]
   ```

---

## Task 6 — EDITORIAL: restructure `prov:used` to peer instrument model

**Present shape**: `TriplesMap_prov_used_entity` emits **one** blank-node
entity with **three peer `schema:instrument` predicates** (lines
793–810), one for beamline, one for mono, one for detector. That single
entity is the sole `prov:used` object of the Activity.

**Required shape**: **one `prov:used` per instrument**, each wrapping
a single `schema:instrument`. The reference example shows this pattern
in
[`example_dds_framed.json`](https://github.com/Cross-Domain-Interoperability-Framework/metadataBuildingBlocks/raw/main/_sources/profiles/cdifCompositeProfile/xasDocument/example_dds_framed.json)
around the `prov:wasGeneratedBy[0]/prov:used` array — you should see
four separate entries, each with a single `schema:instrument`.

Rework in `mapping_dds.ttl`:

1. Delete the `schema:instrument`-peers block currently in
   `TriplesMap_prov_used_entity` (lines 793–810).
2. Create three (or four — see Task 7) new TriplesMaps of shape:
   ```
   <#TriplesMap_prov_used_beamline> a rml:TriplesMap ;
       rml:logicalSource [ ... same source as before ... ] ;
       rml:subjectMap [ rml:template "..." ; rml:termType rml:BlankNode ] ;
       rr:predicateObjectMap [
           rr:predicate schema:instrument ;
           rr:objectMap [ rr:parentTriplesMap <#TriplesMap_beamline> ]
       ] .
   ```
3. Add three new `rr:predicate prov:used` predicate-object maps on
   `TriplesMap_activity_used` (or wherever `prov:used` currently is),
   each pointing at one of the three new peer TriplesMaps as its
   parent.

Each per-instrument `schema:instrument` object retains its existing
`@type`, `schema:additionalType` (xas:beamline / xas:xraymonochromator /
xas:xraymonitor), `schema:name`, and `schema:additionalProperty` list
— those TriplesMaps (`TriplesMap_beamline`, `TriplesMap_mono`,
`TriplesMap_detector`) don't need structural changes, only content
updates from Tasks 1, 2, 4, 7.

---

## Task 7 — EDITORIAL: add source-instrument wrapper (new content)

xasCore requires a fourth peer instrument: the X-ray source itself,
distinct from the beamline. The current XDI input likely doesn't carry
distinct `Source.*` metadata, so this is either:

- **Static default** — emit constants in the mapping. See the reference
  example around the first `prov:used` entry — it has `xas:source`
  additionalType with `xas:xraysourcetype` = "Synchrotron X-ray Source"
  and `xas:probe` = "x-ray".
- **Input-driven** — require the XDI header to include `Source.type` or
  similar, parse in `api/cdi.py`, and emit through the mapping.

The static-default approach is what the reference example does. Add:

1. A `TriplesMap_source` in `mapping_dds.ttl` shaped like
   `TriplesMap_beamline` but with `xas:source` additionalType and
   the two required propertyIDs.
2. A `TriplesMap_prov_used_source` wrapping it (see Task 6 pattern).
3. A fourth `rr:predicate prov:used` on the activity, pointing at the
   new source wrapper.

---

## Task 8 — EDITORIAL: add `schema:object` MaterialSample (new content)

xasCore requires the activity to carry `schema:object` pointing at the
material sample being analyzed. Required properties:

```
schema:object
  @type [schema:Thing, schema:Product]
  schema:additionalType [
    "MaterialSample",
    { @id: https://w3id.org/isample/vocabulary/materialsampleobjecttype/materialsample }
  ]
  schema:name  <sample chemical name>
  schema:additionalProperty [
    { propertyID xas:samplepreparation, ... }
    ... optional xas:porosity, xas:ph, xas:temperature, etc ...
  ]
```

Where the sample name comes from depends on the XDI headers your
Dataverse-hosted files carry — typically `Sample.name` or
`Sample.formula`. If nothing is available, use a placeholder derived
from the dataset name.

Add:
1. `TriplesMap_sample` — subject shape as above.
2. Predicate-object map on the activity TriplesMap emitting
   `schema:object` pointing at the new sample TriplesMap.
3. Optional `TriplesMap_sample_prep`, `TriplesMap_sample_porosity`, etc.
   — one per additionalProperty. Recommended `xas:` propertyIDs listed
   in the Implementation Guide under "Sample physico-chemical
   additionalProperty".

---

## Task 9 — EDITORIAL: wire up `schema:measurementTechnique` and `schema:keywords`

The mapping already has `TriplesMap_panet`, `TriplesMap_nexus`,
`TriplesMap_keywords_element_edge`, `TriplesMap_keywords_element_symbol`
— but none of them are wired to the root dataset. They emit standalone
DefinedTerm nodes that aren't referenced.

Wire them up on `TriplesMap_root`:

```
rr:predicateObjectMap [
    rr:predicate schema:measurementTechnique ;
    rr:objectMap [ rr:parentTriplesMap <#TriplesMap_panet> ]
] ;
rr:predicateObjectMap [
    rr:predicate schema:measurementTechnique ;
    rr:objectMap [ rr:parentTriplesMap <#TriplesMap_nexus> ]
] ;
rr:predicateObjectMap [
    rr:predicate schema:keywords ;
    rr:objectMap [ rr:parentTriplesMap <#TriplesMap_keywords_element_edge> ]
] ;
rr:predicateObjectMap [
    rr:predicate schema:keywords ;
    rr:objectMap [ rr:parentTriplesMap <#TriplesMap_keywords_element_symbol> ]
]
```

Then in the DefinedTerm-emitting TriplesMaps themselves, ensure they
carry the required additional properties per the reference:

- **Edge keyword**: needs `schema:about "element.edge"` (glossary
  tooling marker), `schema:name` (e.g. "K-edge"), `schema:termCode`
  (e.g. "K"), `schema:inDefinedTermSet`
  = `https://github.com/XraySpectroscopy/XAS-Data-Interchange/blob/master/specification/dictionary.md`.
- **Symbol keyword**: needs `schema:about "element.symbol"`,
  `schema:name` (e.g. "Selenium"), `schema:termCode` (e.g. "Se"),
  `schema:identifier` from SWEET
  (`http://sweetontology.net/matrElement/Selenium`),
  `schema:inDefinedTermSet` = `http://sweetontology.net/matrElement`.
- **PaNET technique**: needs `schema:identifier
  http://purl.org/pan-science/PaNET/PaNET01196`,
  `schema:inDefinedTermSet http://purl.org/pan-science/PaNET/PaNET.owl`,
  `schema:termCode XAS`, `schema:name "X-Ray Absorption Spectroscopy"`.
- **NeXus acquisition mode**: needs
  `schema:inDefinedTermSet nxs:Field/NXxas/ENTRY/DATA/mode` and
  `schema:name` matching the acquisition mode from the XDI
  (`Transmission`, `Fluorescence`, etc.).

---

## Task 10 — Refresh the bundled JSON Schema and frame (mechanical)

`resources/CDIFDiscoveryDataDescriptionStructureProfileStructuredSchema.json`
is a snapshot from an older mBB build. Two options:

**Option A** — refresh in place, keep DDS profile:
Download the current DDS StructuredSchema from
<https://github.com/Cross-Domain-Interoperability-Framework/doc-discoverydatadescriptionstructure/raw/reviewRevision202606/CDIFDiscoveryDataDescriptionStructureProfileStructuredSchema.json>
and replace the local copy. This keeps the current profile target but
picks up the SHACL rule fix and URI-serialization policy changes.

**Option B** — swap for the xasDocument profile schema:
```
curl -o resources/cdifXASDocumentResolvedSchema.json \
    https://github.com/smrgeoinfo/XAS-CDIF/raw/cdifxasRelease/release/cdifXASDocumentResolvedSchema.json
```
Then update `api/Mapper.py` line 26:
```
- DDS_SCHEMA_PATH = RESOURCES_DIR + "/CDIFDiscoveryDataDescriptionStructureProfileStructuredSchema.json"
+ DDS_SCHEMA_PATH = RESOURCES_DIR + "/cdifXASDocumentResolvedSchema.json"
```

**Option B is what makes the output actually validate against the XAS
document profile**. Option A leaves the profile as DDS and the XAS
extensions are informally present but not enforced.

Frame update (Option B only): download the XAS document frame if you
want the output structure to include the XAS-specific slots:
```
curl -o resources/cdifXASDocument-frame.jsonld \
    https://github.com/smrgeoinfo/XAS-CDIF/raw/cdifxasRelease/release/cdifXASDocument-frame.jsonld
```
And update `DDS_FRAME_PATH` in `api/Mapper.py`.

---

## Validation recipe

After each task, regenerate `cdif_dds_framed.jsonld` and validate.

### JSON Schema

```bash
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
```

### SHACL

```bash
pip install pyshacl
curl -o /tmp/xasDocumentRules.shacl \
    https://github.com/smrgeoinfo/XAS-CDIF/raw/cdifxasRelease/release/xasDocumentRules.shacl
pyshacl -s /tmp/xasDocumentRules.shacl -f table \
    -df json-ld resources/cdif_dds_framed.jsonld
```

**Goal**: 0 SHACL violations. Warnings are advisories, not fitness
failures. Progress typically looks like:

- After Task 1–5 (mechanical): 5–15 violations, mostly from missing
  xasCore-required content (sample, keywords, measurementTechnique) —
  expected until Tasks 6–9 land.
- After Task 6: peer prov:used shape now matches; violations from that
  shape go away, but xasCore's requirement that each instrument
  entity be non-empty may fire until Task 7 adds the source.
- After Tasks 7–9: content-completeness shapes should be quiet.
- After Task 10 Option B: JSON Schema validation aligns with the XAS
  document profile.

---

## Suggested execution order

1. Task 1 (namespace rebind) — no functional change, just IRI hygiene.
2. Task 2 (concept renames) — same batch.
3. Task 3 (conformance URIs) — one-line RML addition.
4. Task 5 (xas:analysisevent) — one-line RML addition.
5. Task 10 (refresh bundled schema, Option B) — now validating against
   the right target.
6. Task 4 (URI @id-form policy) — biggest SHACL cleanup this task
   provides.
7. Task 6 (peer prov:used restructure) — largest RML restructure.
8. Task 9 (wire up measurementTechnique + keywords) — mostly additive
   predicate-object maps on the root, with content edits on the
   already-existing DefinedTerm TriplesMaps.
9. Task 7 (source instrument) — additive.
10. Task 8 (MaterialSample sample) — additive.

Validate after each. The reference example
(`example_dds_framed.json`) is a valid endpoint — diff against it
whenever unsure.

---

## Not in scope for this uplift

- **The `/cdif` Python pipeline** (`api/cdi.py:parse_xdi` +
  `api/cdif.py:generate_cdif`). It uses a SKOS-heavy intermediate
  representation and doesn't emit xasDocument-shaped output directly.
  Uplifting it is a larger, separate project.
- **The XDI header parser**. Assumes the current XDI reader is
  sufficient; the mapping is what shapes the output.
- **Adding new XDI header fields**. Where new content (sample,
  keywords, technique) can be derived from existing headers, prefer
  that over hardcoded defaults. Where no header carries the info,
  static defaults are acceptable — this is what the reference example
  does.

---

## Questions? Reference points

- Ping the CDIF group with any structural question about the profile.
- The Implementation Guide answers most "what should this look like"
  questions.
- If a SHACL shape you don't recognize is firing, its `sh:message` will
  tell you what it's checking for and its `sh:sourceShape` gives you a
  handle to grep for in the rules file.
