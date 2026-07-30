# Uplift `cdif-xas-UKDS` output to CDIF `xasDocument/1.0`

> **For Deirdre.** Drop this file into your Claude Code session in the
> `cdif-xas-UKDS` repository root and ask Claude to work through the
> tasks in order. Every reference URL below dereferences to a live file;
> no external context needed.

---

## Already applied in this repository (2026-07-28)

> Read this before starting. Several tasks below are **done in
> `smrgeoinfo/cdif-xas`**, the fork this checkout points at, and the
> instructions still describe the pre-uplift state. Re-applying them
> would be work at best and a regression at worst.

Applied here and not yet submitted upstream to `UKDSResearch/cdif-xas`:

- **Tasks 1-9** — the prefix rebinding, concept renames, conformance
  URIs, `@id`-form policy, `xas:analysisevent`, the peer instrument
  model, the source-instrument wrapper, `schema:object` MaterialSample,
  and `measurementTechnique`/`keywords`.
- **Three `rr:constant` corrections** that were producing wrong values
  rather than missing ones: the reflection plane (wrong for 13 of 55
  files), the monochromator crystal (right by luck), and the detection
  mode (wrong for the one fluorescence-only file). See "Derive in
  Python, assign in RML" in `AGENTS.md` — the hazard is the general
  lesson, not the three instances.
- **Header normalisations** in `api/cdi.py`: ISO datetimes, qualitative
  temperatures (`room temperature` to `295.0 K`, with a note recording
  the original), unit-less energies, and `Sample.preparation` aliased to
  the dictionary's `Sample.prep`.
- **`schema:propertyID` on every variable.** The mapping had a rule that
  read `$['meaning']` -- a definition sentence -- and only fired when a
  `xas:Column.N.*` node was in the graph, which it never is. So no
  propertyID was emitted for any column in any file. `api/cdif.py` now
  builds the whole IRI as `$['propertyIRI']`: the glossary base plus the
  concept's local name from the crosswalk, or the OGC nil URI where no
  crosswalk row names one. The mapping assigns it with
  `rr:termType rr:IRI` and no GREL.

The nil URI is a convention worth keeping: a column that was measured is
recorded whether or not anyone has named its concept, and saying nothing
at all would be indistinguishable from a column nobody looked at.

**Where this leaves the two implementations.** Over the same 55 XDI
files, this pipeline and `usgin/cdifnexmetadata` now agree on the top-level
property set, the variable count per file, the document shape, and --
since the propertyID work -- on all 55 files the exact set of concepts
carried by the variables. What remains is one structural difference
that is not expressible as a mapping rule: where `cdi:isStructuredBy`
goes, and whether parts are typed as datasets, depends on how many
datasets the input holds. Every XDI file holds one spectrum, so this
pipeline never meets the case. See `CONVERGENCE-PROPOSAL.md`.

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
| `api/cdif.py` | Python framer — has hardcoded contexts to fix; Task 13 adds `cdif:` prefix |
| `api/cdi.py` | XDI parser — Tasks 11-12 add case normalization, datetime normalization, sentinel fallbacks, and a marker-tag sweep |
| `api/Mapper.py` | Constant `DDS_SCHEMA_PATH` may need updating if schema is renamed |
| `pyproject.toml` | Task 12 adds `xdi-validator>=0.1.0` for pre-validation |

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

4. **Audit all subject maps for a missing `rml:class`.** RML only emits
   an `rdf:type` triple when the subject map carries `rml:class` (or
   `rr:class`); subject maps without one emit anonymous, untyped
   subjects. In the reference example every emitted object carries an
   `@type` — the framing has nothing to project into `@type` if the
   subject was untyped upstream. Grep for `rml:subjectMap` blocks and
   confirm each has a class. Known culprits from real-world testing:

   - `TriplesMap_representedVariable` — needs `rml:class cdi:InstanceVariable`
     (a subclass of RepresentedVariable) so `cdif:isDefinedBy_RepresentedVariable`
     objects carry `@type`.
   - `TriplesMap_physicalMapping` — needs `rml:class cdif:TextMapping`
     (or `cdif:PhysicalMapping` / `cdif:LocatorMapping` per your
     dataset shape).
   - The four peer wrappers added in Tasks 6 and 7 — see the class
     recommendations in those tasks.

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
       rml:subjectMap [
           rml:template "..." ;
           rml:termType rml:BlankNode ;
           rr:class prov:Entity, schema:Thing
       ] ;
       rr:predicateObjectMap [
           rr:predicate schema:instrument ;
           rr:objectMap [ rr:parentTriplesMap <#TriplesMap_beamline> ]
       ] .
   ```
   The `rr:class prov:Entity, schema:Thing` line is REQUIRED — the
   xasDocument schema description for `prov:used` items says "Inline
   entities SHOULD carry an @type that includes prov:Entity plus a
   schema.org type for the kind of thing used". Skipping this leaves
   the peer wrapper subjects untyped in the JSON-LD output (see Task 4
   note 4).
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
2. A `TriplesMap_prov_used_source` wrapping it (Task 6 pattern —
   remember `rr:class prov:Entity, schema:Thing` on its subject map).
3. A fourth `rr:predicate prov:used` on the activity, pointing at the
   new source wrapper.

**Sentinel-value gotcha for required fields.** xasCore requires
`Mono.d_spacing` on the monochromator peer. If the XDI omits it, you
have two ways to plug the hole: (a) a fallback TriplesMap in RML that
emits a constant `"unknown"`, or (b) a Python pre-pass that injects
the missing triple into the SKOS graph. **Pick exactly one — never
both.** If both fire, RMLMapper generates two `schema:PropertyValue`
subjects with the same blank-node template and framing collapses
them into a single node with `schema:value: ["3.13", "unknown"]`,
which fails the schema's string requirement. Task 11 introduces the
Python approach and is preferred (Python owns the "does this key
exist?" test, which JSONPath cannot express cleanly).

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

## Task 11 — XDI parser resilience (`api/cdi.py`)

Real-world XDI files have three recurring irregularities that cause
downstream SHACL / JSON Schema failures even when the mapping is
correct. All three fix cleanly in `parse_xdi()` because Python owns
the SKOS graph construction — RML sees only the normalized result.

**11a. Case-normalize XDI header keys.** XDI/1.0 canonicalizes
`Facility.name`, `Beamline.name`, `Mono.d_spacing` — capitalized
namespace segment, lowercase field segment. Real files are
inconsistent (`Facility.Name`, `Beamline.Name`, `Mono.D_Spacing`,
`Scan.Start_Time`). The mapping's `cdi:Facility_name` /
`cdi:Beamline_name` predicates never match a `Facility.Name` header,
so Organizations and beamline peers come out with no `schema:name`.

Fix — one edit in `parse_xdi()` right after the key is stripped, before
the `.` branch:

```python
# Canonicalize: keep first segment (namespace) as-is,
# lowercase everything after the first dot.
if '.' in compound_variable_name:
    head, rest = compound_variable_name.split('.', 1)
    compound_variable_name = head + '.' + rest.lower()
```

**11b. Normalize datetime fields to ISO 8601.** XDI files carry
`Scan.start_time` / `Scan.end_time` in space-separated ISO
(`2008-04-10 21:58:50`), slash-date (`2001/06/26 22:27:31`), US m/d/y,
etc. Downstream `schema:startDate` / `schema:endDate` want strict ISO
8601 with `T` separator. Do the conversion at parse time so ordering
of `skos:prefLabel` values (which the RML `[2]`-indexes) is preserved.

Add near the top of `cdi.py`:

```python
from datetime import datetime

_DATETIME_KEYS = {"Scan.start_time", "Scan.end_time"}
_DATETIME_FALLBACK_FORMATS = (
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%dT%H:%M:%S",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
    "%Y-%m-%d", "%Y%m%d", "%Y%m%dT%H%M%S",
)

def _normalize_datetime(value: str) -> str | None:
    s = value.strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).isoformat()   # accepts space sep on 3.11+
    except ValueError:
        pass
    for fmt in _DATETIME_FALLBACK_FORMATS:
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None
```

Call it in `parse_xdi()` right after 11a's case normalization:

```python
if compound_variable_name in _DATETIME_KEYS:
    iso = _normalize_datetime(variable_value)
    if iso is not None:
        variable_value = iso
```

Unparseable values pass through unchanged so downstream validation
still surfaces them.

**11c. Sentinel fallbacks for required-but-missing fields.** xasCore
requires certain content (`Mono.d_spacing`, `Beamline.name`,
`Facility.name`) to be present. When the XDI omits them entirely,
inject a marker triple into the SKOS graph so the RML mapping's
predicate lookup finds a value — otherwise the emitted PropertyValue
has no `schema:value` and fails validation. Introduce a helper that
runs on the graph returned by `parse_xdi()` and BEFORE JSON-LD
serialization:

```python
def _add_xas_fallback_triples(g, name_ns, skos_ns):
    """Inject placeholders so xasCore-required content the XDI didn't
    carry is still present in the graph. Real data is never
    overwritten — fires only when the key is genuinely absent.
    """
    from rdflib import BNode, Literal, URIRef

    def _has_child(subject, child_local):
        return any(g.triples((subject, URIRef(str(name_ns) + child_local), None)))

    def _synthesize_child(subject, child_local, value):
        blank = BNode()
        g.add((subject, URIRef(str(name_ns) + child_local), blank))
        g.add((blank, URIRef(str(skos_ns) + "definition"), Literal(value)))

    mono = URIRef(str(name_ns) + "Mono")
    if (mono, None, None) in g and not _has_child(mono, "Mono_d_spacing"):
        _synthesize_child(mono, "Mono_d_spacing", "unknown")

    for parent_local, child_local in (
        ("Beamline", "Beamline_name"),
        ("Facility", "Facility_name"),
    ):
        parent = URIRef(str(name_ns) + parent_local)
        if (parent, None, None) in g and not _has_child(parent, child_local):
            _synthesize_child(parent, child_local, "missing")
```

Convention: `"unknown"` for numeric/enumerated fields that a domain
expert must supply; `"missing"` for identifier / name fields. If a URI
value is expected but absent, use `<http://www.opengis.net/def/nil/OGC/0/missing>`.

Call it in `generate_cdi` right after `parse_xdi()` returns:

```python
cdi_graph = generator.parse_xdi()
_add_xas_fallback_triples(cdi_graph, generator.name, generator.skos)
```

Extend the helper as new xasCore-required fields surface. See the
Task 7 sentinel-gotcha note — do NOT also add an RML fallback
TriplesMap for the same field.

**11d. Array-labels-line column back-fill.** XDI/1.0 specifies both
`# Column.N:` compound headers AND a whitespace-separated array-labels
line right after `# ---` (header end). Real files often carry only
the array-labels line. Without `Column.N:` headers, the mapping
emits no `cdi:Column_N` triples, no data structure — which breaks
the `cdifDataDescription/1.1` and `cdifDataStructure/1.1` conformance
declarations.

Capture the last `#`-prefixed comment line before the first data row
during `parse_xdi()`:

```python
self.array_labels_line = None    # add to __init__
# In parse_xdi's for-loop, before dispatching to variable/data path:
pending_last_comment = None    # top of parse_xdi
# ...for each '#' line that isn't a structural marker or compound key:
if (stripped and stripped != '#'
    and not stripped.startswith('# ---') and not stripped.startswith('#---')
    and not stripped.startswith('# ///') and not stripped.startswith('#///')
    and ':' not in stripped):
    pending_last_comment = stripped.lstrip('#').strip()
# ...at the FIRST non-'#' line (data path):
if self.array_labels_line is None and pending_last_comment:
    self.array_labels_line = pending_last_comment
```

Then in `generate_cdi`, before `_add_xas_fallback_triples`:

```python
if generator.array_labels_line:
    _synthesize_columns_from_array_labels(
        cdi_graph, generator.name, generator.skos,
        generator.array_labels_line,
    )
```

`_synthesize_columns_from_array_labels` fires only when the graph has
no `cdi:Column` subject (real Column headers were parsed → do
nothing). Otherwise emits `cdi:Column` + one `cdi:Column_N` per
whitespace token, each carrying the token as `skos:definition`.

---

## Task 12 — XDI pre-validation (surface spec issues before /cdif)

Real XDI files often violate XDI/1.0 in ways the RML mapping can't
detect (missing `# ---` header end line, missing `Element.symbol`,
non-conforming date formats, out-of-vocabulary edge names). Running a
spec-check before /cdif runs surfaces these as an `xdi_validation`
report in the response so downstream consumers can fix the input at
its source.

Recommended package: [`xdi_validator`](https://github.com/AAAlvesJr/XDI-Validator)
(MIT, by A. A. Alves Jr.). Warning-only integration — non-compliant
XDI does not block CDIF generation.

1. Add `xdi-validator>=0.1.0` to `pyproject.toml` and `uv sync`.
   Requires Python 3.13; update `.python-version` if needed.
2. Create `api/xdi_precheck.py` — a thin wrapper that reads the input
   URL (local or HTTP), runs `xdi_validator.validate(fh)`, returns a
   summary dict `{ok: bool, error_count: int, field_errors: {...}}`.
3. In `api/api.py:cdif_generate`, call the precheck first. Attach the
   summary to the response as `xdi_validation` — but **only after**
   `cdif_skos.json` has been written to disk (the RML pipeline reads
   that file for /map; adding a top-level key `xdi_validation` to it
   breaks the mapping).

Add an Acknowledgement section to your README citing xdi_validator
and its Zenodo DOI. The pre-check catches issues that would otherwise
turn into cryptic SHACL failures 30 seconds later in the pipeline.

**Tip:** the AAAlves validator has an XDI/1.0 spec issue our team's
fork corrected — `mono.d_spacing` is only required when the abscissa
is angle or encoder (not for energy abscissae). Upstream PR at
<https://github.com/AAAlvesJr/XDI-Validator/pull/6>; until merged you
can install from `smrgeoinfo/XDI-Validator@conditional-mono-d-spacing`.

---

## Task 13 — RML iterator resilience (marker predicate)

Nine of the mapping's TriplesMap iterators use a regex to locate the
top-level Dataset:

```
rml:iterator "$['@graph'][?(@['@id'] =~ /^http:\\/\\/localhost:8080\\/citation\\?persistentId=perma:DV\\/.*/)]"
```

Another nine use `$['@graph'][0]` — positional indexing that depends
on JSON-LD serialization order being stable. Both patterns are
brittle: the regex couples RML to Dataverse's citation-URL format;
the positional iterator can silently pick the wrong node if the
serializer ever reorders.

**Fix**: tag the Dataset node with a stable marker predicate in
Python, iterate on the marker. All 18 iterators become identical:

```
rml:iterator "$['@graph'][?(@['cdif:isDatasetRecord'] == 'yes')]"
```

Implementation:

1. In `api/cdif.py:frame_context`, add `"cdif": "https://w3id.org/cdif/"`
   so the marker predicate serializes as `cdif:isDatasetRecord` (not
   the full URI) in `cdif_skos.json`.
2. In `api/cdi.py:generate_cdi`, after the Dataverse `schema_graph` is
   merged into `cdi_graph`, tag every `schema:Dataset` in the merged
   graph:
   ```python
   _SCHEMA = rdflib.Namespace("http://schema.org/")
   _CDIF = rdflib.Namespace("https://w3id.org/cdif/")
   for ds_subj in set(cdi_graph.subjects(rdflib.RDF.type, _SCHEMA.Dataset)):
       cdi_graph.add((ds_subj, _CDIF.isDatasetRecord, rdflib.Literal("yes")))
   ```
3. In `resources/mapping_dds.ttl`, replace every regex iterator and
   every `$['@graph'][0]` iterator with the marker iterator above. A
   grep should find exactly 18 lines.

GREL `string_replace` patterns that derive downstream IRIs from the
Dataverse @id (e.g. rewriting `http://localhost:8080/citation?persistentId=perma:`
→ `https://example.org/dataset/`) keep working unchanged — they still
receive the real @id via `$['@id']`. Only the iteration targets change.

The immediate benefit is decoupling from Dataverse's URL format; the
larger benefit is architectural clarity — Python owns "which nodes
should RML iterate over" via a single marker triple, instead of
scattering that knowledge across nine regex declarations. Consider
adopting the same pattern for any future subject class that RML needs
to locate.

---

## Task 14 — Shape safety nets (name-or-identifier constraints)

Several CDIF shapes require ONE of {name, identifier} to be present.
Add four small post-frame passes in `api/Mapper.py` alongside the
existing `_drop_incomplete_additional_properties`, each walking the
framed dict and injecting a sentinel only when both alternatives are
absent. Real data is never overwritten.

**Sentinel-value conventions:**

- `"Missing"` — text placeholder for a required `schema:name`.
- `<http://www.opengis.net/def/nil/OGC/0/missing>` — IRI sentinel
  (OGC Rainbow nil-value vocabulary) for required URI-shape values.

**The four passes** (call each from `frame()` after
`_drop_incomplete_additional_properties`):

| Function | Target `@type` | Sentinel |
|----------|---------------|----------|
| `_ensure_person_has_name_or_identifier` | `schema:Person` | `schema:name = "Missing"` |
| `_ensure_organization_has_name_or_identifier` | `schema:Organization` | `schema:name = "Missing"` |
| `_ensure_role_has_contributor` | `schema:Role` | `schema:contributor = {"@id": OGC_NIL_MISSING}` |
| `_ensure_definedterm_has_name_or_identifier` | `schema:DefinedTerm` | `schema:identifier = {"@id": OGC_NIL_MISSING}` |

Skeleton (all four share the same shape):

```python
OGC_NIL_MISSING = "http://www.opengis.net/def/nil/OGC/0/missing"

def _has_type(node_types, target):
    if isinstance(node_types, str):
        return node_types == target
    if isinstance(node_types, list):
        return target in node_types
    return False

def _ensure_person_has_name_or_identifier(node):
    if isinstance(node, dict):
        if _has_type(node.get("@type"), "schema:Person"):
            if not node.get("schema:name") and not node.get("schema:identifier"):
                node["schema:name"] = "Missing"
        for v in node.values():
            _ensure_person_has_name_or_identifier(v)
    elif isinstance(node, list):
        for x in node:
            _ensure_person_has_name_or_identifier(x)
```

Reference: `_sources/schemaorgProperties/{person,organization,agentInRole}/rules.shacl`
in the CDIF metadataBuildingBlocks repo enumerate the shapes.

---

## Task 15 — Blank-node identifier materialization

JSON-LD framing typically leaves blank-node `@id` values in the
`_:xxx` syntax. This is valid RDF but fails plain-JSON URI-format
validators (e.g. Oxygen JSON validation). Rewrite each unique
`_:xxx` to a real IRI under the `ex:` namespace already bound in
`resources/context.json`:

```
_:b14  →  ex:blank/b14
```

Add a post-frame pass in `api/Mapper.py` that walks the framed dict
and rewrites both node subjects (`@id` field) and object references
(`{"@id": "_:xxx"}` shape). Same substitution everywhere so
references still resolve to the same subject.

```python
def _materialize_blank_node_ids(node):
    def _rewrite(val):
        if isinstance(val, str) and val.startswith("_:"):
            return "ex:blank/" + val[2:]
        return val

    if isinstance(node, dict):
        if "@id" in node:
            node["@id"] = _rewrite(node["@id"])
        for v in node.values():
            _materialize_blank_node_ids(v)
    elif isinstance(node, list):
        for x in node:
            _materialize_blank_node_ids(x)
```

Call it LAST in `frame()` so the other safety-net passes still see
the original blank IDs when walking the dict.

---

## Task 16 — CDIF Core creator alignment (schema:creator, not contributor)

Per CDIF Core: `schema:creator` holds the author/creator (intellectual
originator) of the dataset; `schema:contributor` is reserved for
OTHER roles like Facility, Funder, etc. — those keep the Role wrapper
pattern.

The current UKDS mapping puts BOTH Author and Creator into
`schema:contributor` with Role wrappers (`TriplesMap_dv_author_role` /
`TriplesMap_dv_creator_role`), each pointing at a schema:Person via
another Role's `schema:contributor`. This is legacy shape from the
DataCite-style role model and doesn't match CDIF Core.

**Cleanup:**

1. On `TriplesMap_root` (`mapping_dds.ttl`, around line 128), replace
   the two `schema:contributor` predicate-object maps that reference
   `TriplesMap_dv_author_role` / `TriplesMap_dv_creator_role` with a
   single `schema:creator` predicate-object map pointing at a new
   `TriplesMap_dv_creator`.
2. Delete `TriplesMap_dv_author_role`,
   `TriplesMap_dv_author_contributor`, `TriplesMap_dv_creator_role`,
   `TriplesMap_dv_creator_contributor` (four blocks around lines
   639-733 in the pre-uplift mapping).
3. Add one new TriplesMap that emits the Person directly (no Role
   wrapper) with `schema:name` from `$['schema:author']['schema:name']`:

   ```
   <#TriplesMap_dv_creator> a rml:TriplesMap;
     rml:logicalSource [ ... same source, uses the Task 13 marker iterator ...] ;
     rml:subjectMap [
         rr:termType rr:BlankNode;
         rr:class schema:Person;
         rml:template "_:dv_creator"
       ] ;
     rr:predicateObjectMap [
       rr:predicate schema:name;
       rr:objectMap [
         rml:reference "$['schema:author']['schema:name']"
       ]
     ] .
   ```
4. The `schema:contributor` predicate on `TriplesMap_root` for the
   Facility Organization stays as-is — Facility is correctly a
   contributor per CDIF Core.

**Frame update** (`resources/CDIFDiscoveryDataDescriptionStructure-frame.jsonld`):
the `schema:creator` sub-frame currently lists `schema:affiliation`,
`schema:identifier`, `schema:contactPoint`, but NOT `schema:name`.
Add `"schema:name": {}` — without it, pyld's framer drops the
creator Person entirely when the Person only has a name (as our
placeholder does):

```
"schema:creator": {
    "@embed": "@always",
    "schema:name": {},                     ← add this line
    "schema:affiliation": { ... },
    "schema:identifier": {"@embed": "@always"},
    "schema:contactPoint": {"@embed": "@always"}
},
```

The `schema:contributor` sub-frame already has `"schema:name": {}` —
symmetric fix.

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

- After Tasks 11–12 (parser resilience + pre-validation): no CDIF
  output changes, but any XDI files that violate the spec are
  reported to the response as `xdi_validation`. Fewer downstream
  surprises.
- After Task 1–5 (mechanical): 5–15 violations, mostly from missing
  xasCore-required content (sample, keywords, measurementTechnique) —
  expected until Tasks 6–9 land.
- After Task 4 (URI @id-form policy + `@type` audit): every emitted
  object should carry an `@type`. If you still see untyped subjects
  in the framed output, re-check the audit — an untyped subject means
  its RML subject map is missing `rml:class`.
- After Task 6: peer prov:used shape now matches; violations from that
  shape go away, but xasCore's requirement that each instrument
  entity be non-empty may fire until Task 7 adds the source.
- After Tasks 7–9: content-completeness shapes should be quiet.
- After Task 10 Option B: JSON Schema validation aligns with the XAS
  document profile. Real corpora reaching 0 violations at this point
  are the goal; on a 37-file test corpus we hit 37/37 fully valid
  after applying Tasks 11, 13, 14, 15, 16 alongside the base 1-10.
- After Task 14 (shape safety nets): SHACL violations from missing
  name/identifier on Person / Organization / DefinedTerm / Role
  clear. Sentinel-value convention (`"Missing"`, OGC nil IRI) makes
  placeholder values visibly distinct from real content.
- After Task 15 (blank-node materialization): no SHACL / JSON Schema
  change (both accept blank nodes and IRIs), but plain-JSON
  validators like Oxygen stop flagging `_:xxx` as invalid URI.
- After Task 16 (creator alignment): the framed dataset's
  `schema:contributor` now contains only OTHER roles (Facility,
  Funder, etc.); the author/creator lives on `schema:creator`.
- After Task 13 (iterator marker): no output change if Task 13's
  Python marker-tag sweep and RML iterator updates are consistent.
  This task is safety-net + brittleness reduction, not correctness
  improvement.

---

## Suggested execution order

Do the parser-side resilience work FIRST so subsequent mapping
validation runs against normalized input:

1. Task 11 (`api/cdi.py` resilience — case + datetime + sentinels).
2. Task 12 (XDI pre-validation) — surfaces spec issues before any of
   the below run.
3. Task 1 (namespace rebind) — no functional change, just IRI hygiene.
4. Task 2 (concept renames) — same batch.
5. Task 3 (conformance URIs) — one-line RML addition.
6. Task 5 (xas:analysisevent) — one-line RML addition.
7. Task 10 (refresh bundled schema, Option B) — now validating against
   the right target.
8. Task 4 (URI @id-form policy + missing-`@type` audit) — biggest
   SHACL cleanup this task provides.
9. Task 6 (peer prov:used restructure) — largest RML restructure.
10. Task 9 (wire up measurementTechnique + keywords) — mostly additive
    predicate-object maps on the root, with content edits on the
    already-existing DefinedTerm TriplesMaps.
11. Task 7 (source instrument) — additive.
12. Task 8 (MaterialSample sample) — additive.
13. Task 16 (CDIF Core creator alignment) — schema.org shape cleanup;
    do after Task 6 so you're not re-editing the contributor block.
14. Task 14 (shape safety nets) — defensive post-frame passes; small,
    idempotent; run once you have real Persons/Orgs flowing through.
15. Task 15 (blank-node materialization) — cosmetic fix for JSON
    validator compatibility; do near the end so you don't
    re-materialize identifiers you're still inspecting as `_:xxx`.
16. Task 13 (RML iterator marker) — do LAST. Structural change to 18
    iterators; safest once the mapping's semantics are stable.

Validate after each. The reference example
(`example_dds_framed.json`) is a valid endpoint — diff against it
whenever unsure.

**Batch validation tip.** Once Tasks 1-10 are in, generating and
validating a whole XDI corpus in one shot beats one-off `/cdif` +
`pyshacl` runs. Two small drivers we found useful on our end:

- Batch generation: for each `*.xdi` in an input directory, run
  the `/cdif` → `/map` → `/frame` pipeline directly (no HTTP layer)
  and drop the framed JSON-LD in an output directory. See
  `tools/batch_generate_cdif.py` in the smrgeoinfo/cdif-xas fork on
  the `local-xdi-input` branch for a working template.
- Batch validation: for each `*.jsonld` in that output directory,
  run JSON Schema (Draft 2020-12) + SHACL (pyshacl) and emit a
  per-file report. Template at `tools/batch_validate_cdif.py` in the
  same branch. Useful for turning the "37 files, 0 fully valid → 37
  fully valid" iteration into a single feedback loop.

---

## Not in scope for this uplift

- **The `/cdif` framing logic** in `api/cdif.py:generate_cdif`. It
  uses a SKOS-heavy intermediate representation and doesn't emit
  xasDocument-shaped output directly. Tasks 11-13 add resilience and
  RML-decoupling but stop short of rewriting the framer itself. A
  full Python-native alternative to the RML pipeline is a larger,
  separate project.
- **Adding new XDI header fields.** Where new content (sample,
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
