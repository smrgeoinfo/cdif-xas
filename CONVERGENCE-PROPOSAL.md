# Proposal: one intermediate model, two input formats

**To:** Deirdre, Slava
**From:** Stephen Richard (smrgeoinfo)
**About:** `cdif-xas-UKDS` and `usgin/cdifnexmetadata`

## What this is not

This is not a proposal to replace `cdif-xas-UKDS`. That pipeline is in
production, it is reviewed, it integrates with Dataverse, and it
validates every file in the test corpus. The other implementation does
none of those things.

It is a proposal to change **one module** so that both pipelines share an
intermediate model, and with it a single emitter, a single set of
profile fixes, and the ability to add an input format or a technique
without touching either.

## Where things stand

Two pipelines now produce CDIF-XAS from the same 55 XDI files. Both
validate 55/55 against the `xasDocument` composite.

| | `cdif-xas-UKDS` | `usgin/cdifnexmetadata` |
|---|---|---|
| Input formats | XDI | XDI **and** NeXus/HDF5 |
| Intermediate keys | `cdi:Facility_name` | `cdifxas:facility` |
| Mapping | RML, `mapping_dds.ttl` (~1600 lines) | SSSOM TSV + Python |
| Runtime | FastAPI + Java rmlmapper + pyld | Python only |
| Dataverse | yes | **no** |
| Reviewed / in production | **yes** | no |
| Tests | — | 190 |

Neither is strictly better. The columns that matter for this proposal
are the second and the last two.

## The one thing worth changing

`cdif-xas-UKDS` keys its intermediate on XDI-flavoured names.
`cdi:Facility_name` means simultaneously *the facility* and *what XDI
calls it*. That works for one input format and has nowhere to put a
second: there is no place to record that the same concept arrived from
`NXsource/name` in an HDF5 file.

`cdifnexmetadata` keys on the concept — `cdifxas:facility` — and records
*where it came from* as an attribute of the value, alongside the SSSOM
predicate that licensed the mapping and a confidence. A second input
format is then a second parser, not a second pipeline.

That is the whole architectural difference. Everything below follows
from it.

## Evidence, not assertion

Three things were measured rather than argued.

**Adding a technique cost one file and no code.** Small-angle scattering
(`NXsas`) was added by writing `cdifsas-to-nexus.sssom.tsv`. Nothing in
the reader, the mapper or the emitter changed. Real SAS files produce 22
concepts, 4 variables, and the data-structure profile.

**Adding a format cost one parser.** XDI support in `cdifnexmetadata` is
`inspect/xdi.py` plus `map/xdi.py`. The emitter, profile detection,
validation and CLI are the same code the NeXus path uses. All 55 corpus
files are recognised and mapped.

**The declarative layer is not carrying the hard parts.** This is the
finding most relevant to you.

`mapping_dds.ttl` emitted `rr:constant "1,1,1"` for the reflection plane
of every file. That is wrong for the four `Si(220)` files and the nine
`Si(311)` files in the corpus — 13 of 55. The mapping's own comment
said so:

> emitted as a static default. Override with a real reflection … via
> `rml:reference` once your XDI vocabulary defines the field.

The value was available all along, inside `Mono.name`. Fixing it needed
string parsing, which RML cannot do, so the fix was to derive
`cdi:Mono_reflection` in `api/cdi.py` and point the mapping at it.

That is the same shape as every other non-trivial transformation in this
pipeline. `api/cdi.py` already normalises ISO datetimes, qualitative
temperatures (`room temperature` → `295.0 K`), value/unit spacing
(`10K` → `10 K`), and unit-less energies. Each of those is Python
running before RML sees the data.

So the choice is not *declarative versus imperative*. It is
**Python + RML + Java + FastAPI** versus **Python**. The declarative
layer is handling the easy parts and adding a runtime to do it.

### Four bugs of one shape

Scanning the TriplesMaps for `rr:constant` on a value-bearing predicate
turned up four defects, all now fixed:

| TriplesMap | asserted | correct for | wrong for |
|---|---|---|---|
| `mono_reflection` | `"1,1,1"` | 42 of 55 | **13** — every `Si(220)` and `Si(311)` |
| `mono_type` | `"Si"` | 55 of 55 | the first `Ge(220)` that arrives |
| `nexus` | `"Transmission"` | 54 of 55 | **1** — `xdl_pyrite2_rt_01`, an `ifluor` file |
| `physicalMapping` | `15` for both `cdi:minimumLength` and `cdi:maximumLength` | **3 of 55** | **52** — observed field widths run 5 to 15 |

The pattern matters more than any one of them.

**Each produced plausible metadata.** None was malformed, none failed
validation, and all 55 documents validated 55/55 both before and after.
A silicon monochromator and a transmission measurement are what these
files usually contain, so the wrong values looked exactly like right
ones. They were found by comparing two implementations, not by anything
the pipeline itself could have reported.

**Each had the same cause.** RML cannot parse a string or branch on a
condition. `Si(311)` holds a crystal and a reflection; which detection
mode a scan used follows from which columns are present. Neither is
expressible in the mapping language, so a constant was the only thing on
offer, and a constant is what got written. The `mono_reflection` comment
said so outright: *"emitted as a static default … until your XDI
vocabulary defines the field."*

**Each was fixed the same way** — derive the value in `api/cdi.py`,
expose a key, point the mapping at it. That is now the pattern for
datetimes, temperatures, energy units, reflection planes, crystal types,
detection modes, concept IRIs, units, sample-preparation spellings and
field widths. Ten transformations, all in Python, with RML carrying the
assignment.

**The fourth is the one that would have done real damage.** The first
three write a wrong label — a reflection plane, a crystal, a detection
mode — which a reader may notice is implausible for their sample. The
field widths are not a label but a parsing instruction: a consumer that
trusts `cdi:minimumLength == cdi:maximumLength == 15` will slice a
file whose fields are 9 or 10 characters at fixed offsets and read
numbers that are wrong without being obviously wrong. It was correct for
3 of the 55 files, and 34 of the 55 are not fixed-width at all.

It also shows how weak agreement is as evidence when one side is a
constant. The two implementations agreed on `se_na2so4_rt`, whose fields
really are 15 characters, and that agreement was briefly taken as
confirmation that both were measuring correctly. Only one was. Checking
whether the value varied across the corpus is what exposed it.

**One hid because of where it sat.** The detection mode is on
`schema:name`, where 15 of the mapping's 16 constants are property
labels and entirely correct. Only its `inDefinedTermSet` —
`nxs:Field/NXxas/ENTRY/DATA/mode` — reveals that this `schema:name`
carries data. A scan that categorised by predicate nearly filed it as
benign, which is a fair indication of how legible the mapping is to
review.

This is not an argument that the mapping was written carelessly. It is
an argument that the language pushes toward constants wherever the data
needs interpreting, that constants of this kind fail silently, and that
the interpretation has been migrating into Python one fix at a time
regardless.

## What RML genuinely gives you

Stating the other side plainly, because it is not nothing:

- It is a standards-track mapping language, which matters for a
  standards project.
- **The mapping is data**, so it can be diffed, validated and
  version-controlled as a mapping rather than as source code. That is a
  real governance property and it does not depend on who can read it.
- It is the artifact that has been reviewed.

I had written here that the mapping is "inspectable by people who do not
read Python". Having re-read it, that claim is too strong and I withdraw
it. Reading `mapping_dds.ttl` requires RML/R2RML vocabulary, JSONPath,
Turtle blank-node syntax, and the shape of the intermediate
`cdif_skos.json` it queries — four things, none of them Python, none of
them common knowledge. The set of people who can read it is smaller and
more specialised than "non-programmers", and plausibly smaller than the
set who can read the equivalent Python.

If the governance properties above outweigh the costs, that is a
legitimate answer and this proposal fails on its merits rather than on
argument.

### The same job, both ways

`TriplesMap_mono_type` emits one `schema:PropertyValue` saying what the
monochromator crystal is. In full, 29 lines:

```turtle
<#TriplesMap_mono_type> a rml:TriplesMap;
  rml:logicalSource [ a rml:LogicalSource;
      rml:iterator "$['@graph'][?(@['@id'] == 'cdi:Mono')]";
      rml:referenceFormulation rml:JSONPath;
      rml:source [ a rml:RelativePathSource;
          rml:root rml:MappingDirectory;
          rml:path "cdif_skos.json" ] ];
  rml:subjectMap [
      rr:termType rr:BlankNode;
      rr:class schema:PropertyValue;
      rr:template "_:mono_type" ] ;
  rr:predicateObjectMap [
    rr:predicate schema:name;
    rr:objectMap [ rr:constant "crystal type" ] ] ;
  rr:predicateObjectMap [
    rr:predicate schema:propertyID;
    rr:objectMap [ rr:constant xas:monochromatortype ;
                   rr:termType rr:IRI ] ] ;
  rr:predicateObjectMap [
    rr:predicate schema:value;
    rr:objectMap [ rr:constant "Si" ] ] .
```

The equivalent in `cdifnexmetadata` is one crosswalk row:

```
xdi:Mono.name   skos:closeMatch   cdifxas:monochromatortype
```

and one line saying where the concept goes in the output:

```python
"cdifxas:monochromatortype": Slot("monochromator", "monochromatortype",
                                  "monochromator crystal"),
```

Two points, and the second matters more than the line count.

**The RML version does not read the value.** The last clause is
`rr:constant "Si"`. Every file gets `Si` whatever its `Mono.name` says.
That is correct for all 55 files in the corpus, because they all use
silicon monochromators, and it would be wrong for the first Ge(220) file
that arrives. It is the same failure as the `rr:constant "1,1,1"`
reflection plane, which *was* wrong, for 13 of 55.

That is not a criticism of whoever wrote it. It is a symptom: RML cannot
parse `Si(111)` into a crystal and a reflection, so a constant is the
only thing the language offers, and a constant is what got written.

The crosswalk row above maps `Mono.name` at `skos:closeMatch` rather
than `exactMatch` precisely because XDI conflates the two, and the
splitting happens in twelve lines of Python that record the original
string in a note. The value is read; nothing is asserted.

**Judge this yourselves rather than taking my summary.** Put the two side
by side and ask which you would rather maintain, and which you would
rather debug at 5pm when a Ge monochromator turns up. Your answer to
that is better evidence than any sentence I can write here.

### The intermediate, both ways

The section above compares the mapping. This compares the thing the
mapping reads, which is where the architectural difference actually
lives.

`api/cdi.py` writes `cdif_skos.json`. For the monochromator it produces:

```json
{
  "@id": "cdi:Mono",
  "skos:broader": [ {"@id": "cdi:Mono_name"},
                    {"@id": "cdi:Mono_d_spacing"} ],
  "skos:prefLabel": [ "Mono", "Si 111", "3.13550" ],
  "cdi:Mono_name":      { "@id": "_:N21a5fce9724b41b3...",
                          "skos:definition": "Si 111" },
  "cdi:Mono_d_spacing": { "@id": "_:N86709123e522459f...",
                          "skos:definition": "3.13550" },
  "cdi:Mono_reflection": { "@id": "_:Naed454d6e4b3485...",
                           "skos:definition": "1,1,1" }
}
```

`cdifnexmetadata` produces, from the same header:

```json
{
  "cdifxas:monochromatortype": [{
    "value": "Si",
    "source_path": "#Mono.name",
    "predicate": "skos:closeMatch",
    "confidence": 0.8,
    "note": "XDI Mono.name conflates crystal material and reflection
             (e.g. 'Si(111)'); the CDIF concept is the material type
             alone. [converter key: cdi:Mono_name]; reflection split
             out into reflectionplane"
  }],
  "cdifxas:reflectionplane": [{
    "value": "1 1 1",
    "source_path": "#Mono.name",
    "confidence": 0.9,
    "note": "read out of Mono.name ('Si(111)'), which XDI uses for the
             crystal material and the reflection together"
  }]
}
```

Five differences, in rough order of consequence.

**The key names the field, or it names the concept.** `cdi:Mono_name`
says *what XDI called it*. `cdifxas:monochromatortype` says *what it is*.
The first has no second slot: when the same fact arrives from
`NXcrystal/chemical_formula` in an HDF5 file, there is nowhere to put it
that does not lie about where it came from.

**Provenance is the key, or it travels beside the value.** In the graph,
the only record of origin *is* the key — so a concept can have exactly
one origin. In the record, `source_path` is a field, so the same concept
can carry values from several places, each saying where it came from.

**Confidence and predicate exist in one and not the other.** The record
says this mapping is a `skos:closeMatch` at 0.8, because `Mono.name`
conflates two things. The graph has no way to express that; every value
is equally authoritative, and a downstream consumer cannot be more
careful with the shakier ones.

**`skos:prefLabel` is a bag.** `["Mono", "Si 111", "3.13550"]` mixes a
node label with values from two unrelated fields. Nothing downstream can
tell which is which without going back to the typed keys.

**Blank-node identifiers are regenerated every run.**
`_:N21a5fce9724b41b3...` changes on each invocation, so a diff of two
runs over unchanged input is mostly noise. The record has no identifiers
at this stage; identity is assigned once, at emission, from stable values.

Note the crosswalk keeps `[converter key: cdi:Mono_name]` in the note.
The link back to your vocabulary is not discarded — it becomes
provenance rather than structure, which is what makes a second binding
possible.

## The proposal

**Change `api/cdi.py` to emit `ConceptRecord` objects instead of an
XDI-keyed RDF graph.** Both pipelines then share one emitter.

Concretely:

1. `cdi.py` keeps its XDI parsing and all four normalisers. They are
   good and they stay.
2. Instead of building `cdi:Facility_name` triples, it produces concept
   values keyed on `cdifxas:` URIs, using `xdi-to-cdifxas.sssom.tsv` —
   which already exists and which `build_crosswalk.py` already
   validates against the glossary.
3. The shared emitter takes it from there.

This is a change to one module. `mapping_dds.ttl`, the rmlmapper
dependency and the framing step retire with it, but nothing about how
XDI is read or how Dataverse is queried changes.

### What you keep

Dataverse integration, the FastAPI service, the XDI parsing, every
normaliser, and the CDIF output shape — which the shared emitter was
built from by reading your records.

### What you gain

- **NeXus support**, without writing it.
- **One place for profile changes.** The CDIF 1.1 uplift you did by hand
  across `mapping_dds.ttl` becomes an edit to one Python module that
  both pipelines inherit.
- **A technique is a TSV.** Astromaterials and geochemistry are the
  stated next domains; neither needs an RML author.
- **Conformance detected, not asserted.** The emitter claims a profile
  only where the content for it exists.
- **A test suite.** 189 tests, offline, no Java.

### What it costs

- Rewriting the back half of `cdi.py`. Estimate: days, not weeks — the
  parsing and normalisation, which are the hard parts, are unchanged.
- Losing a declarative mapping artifact.
- Depending on a codebase that is currently one person's and not yet
  reviewed by you. **This is the real risk and I am not minimising it.**

## Where the two implementations actually stand (2026-07-28)

**The output difference is gone.** Run both pipelines over the same 55
XDI files and compare:

| | start of day | now |
|---|---|---|
| top-level property set | 55/55 agree | 55/55 |
| variable count per file | 55/55 | 55/55 |
| concepts carried by variables | **0/55** | **55/55** |
| units on variables | **0/55** | **55/55** |

That is worth stating plainly because it costs this proposal an
argument. The case can no longer be "the RML output is missing things".
It is not.

### What changed, and what it took

Four fixes, two in each pipeline:

- **RML emitted no `schema:propertyID` on any variable in any file.** A
  rule existed; it read `$['meaning']`, which is a definition sentence,
  and only fired when a `xas:Column.N.*` node was in the graph, which it
  never is. Fixed by deriving the IRI in `api/cdif.py` and assigning it
  in one line of RML. 206 propertyIDs where there were none.
- **RML wrote `""` for units it did not know**, 165 times, asserting
  that the unit is the empty string. Fixed the same way: derive in
  Python, emit nothing when there is nothing.
- **RML asserted a 15-character field width** for every column of every
  file, `rr:constant` on both `cdi:minimumLength` and
  `cdi:maximumLength`. Correct for 3 of the 55. Now measured while the
  data rows are read.
- **RML dropped `Sample.preparation`**, which one file writes instead of
  the dictionary's `Sample.prep`. Fixed with a header alias.
- **The Python pipeline discarded units the column label carried**,
  which RML was reading. Fixed by splitting the label.

Note what each fix looked like. The ones on the RML side were all
*derive in Python, assign in RML* -- because a mapping rule cannot
branch, cannot fall back, and cannot build a value that is not a
substring of the input. Two of them replaced GREL constructs that had
been silently producing nothing or producing a wrong value for every
file in the corpus, undetected. The one on the Python side was a change
to a parser and a test.

### What this leaves

**Complementary content, not disagreement.** Each pipeline emits
predicates the other does not, and both are useful: RML describes the
serialization -- delimiter, header rows, column index, field lengths --
while the Python side describes provenance and identity, `cdif:locator`
per component and an SPDX checksum. A consumer wanting to parse the file
wants the first; a consumer wanting to know which bytes these are wants
the second.

**One structural difference that is not expressible as a mapping rule.**
Where `cdi:isStructuredBy` goes, and whether a part is typed as a
dataset, depends on how many datasets the input holds. That is a
decision about the input, not a correspondence between vocabularies.
Every XDI file holds one spectrum, so this pipeline never meets the
case; a NeXus file with 26 entries does, and RML has no way to describe
it.

### So what the proposal now rests on

Not output quality. Two things:

1. **A second input format.** The RML pipeline reads XDI. Adding NeXus
   means a second mapping file, a second intermediate shape, and no
   shared place to record that `cdifxas:facility` arrived from
   `Facility.name` in one and `NXsource/name` in the other.
2. **What each fix costs.** Every RML fix above was two coordinated
   edits -- a key derived in `api/cdi.py` or `api/cdif.py`, a reference
   in `mapping_dds.ttl` -- with nothing checking that the two agree. The
   crosswalk equivalent is one row, and `build_crosswalk.py` fails the
   build if the concept is not in the glossary or the key is not one the
   converter reads.

Both were true this morning. They are just no longer obscured by an
output gap that has since closed.

## Open issues, stated rather than hidden

- **`cdifnexmetadata` has no Dataverse integration at all.** It emits
  placeholder `schema:creator`, `schema:license` and identifiers under
  `w3id.org/cdif/testing/`. Your pipeline fetches real values. Any merge
  must keep that, and it is the strongest argument for building *onto*
  `cdif-xas-UKDS` rather than away from it.
- **Technique-neutral concepts are in the wrong namespace.** `facility`,
  `beamline`, `probe`, `temperature` sit under `cdifxas:` because that
  crosswalk was written first. Writing the SAS one exposed it. This
  should be fixed in the glossary before a third domain arrives.
- **`CONCEPT_SLOTS` is Python, deliberately.** "Where does this concept
  go in a schema.org graph" involves nesting, typing and
  cross-references a flat table cannot express. A new domain needs its
  own placements. That layer is domain-specific by design.
- **The two pipelines disagree about sentinels.** Where a source type is
  absent, yours writes `Synchrotron X-ray Source` and mine writes
  `unknown`. Yours always produces a complete document; mine leaves the
  gap legible. Both are defensible and the choice should be explicit
  rather than incidental.

## Suggested next step

Not a decision. A one-file spike: have `cdi.py` emit `ConceptRecord`s
for a handful of XDI files, run them through the shared emitter, and
diff the output against what `mapping_dds.ttl` produces today. If the
documents match, the argument is settled empirically. If they do not,
the differences are the real agenda.

I am happy to write that spike.

## References

- `usgin/cdifnexmetadata` — `DESIGN.md`, `STATUS.md`
- `XAS-CDIF/exampleMetadata-cdifnexmetadata/README.md` — both pipelines'
  output over the same 55 files, with the differences characterised
- `cdif-xas-UKDS/UPLIFT-INSTRUCTIONS.md` — the CDIF 1.1 uplift already
  applied here
