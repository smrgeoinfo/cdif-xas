# Proposal: one intermediate model, two input formats

**To:** Deirdre, Slava
**From:** Stephen Richard (smrgeoinfo)
**About:** `cdif-xas-UKDS` and `usgin/hdf5metadata`

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

| | `cdif-xas-UKDS` | `usgin/hdf5metadata` |
|---|---|---|
| Input formats | XDI | XDI **and** NeXus/HDF5 |
| Intermediate keys | `cdi:Facility_name` | `cdifxas:facility` |
| Mapping | RML, `mapping_dds.ttl` (~1600 lines) | SSSOM TSV + Python |
| Runtime | FastAPI + Java rmlmapper + pyld | Python only |
| Dataverse | yes | **no** |
| Reviewed / in production | **yes** | no |
| Tests | — | 189 |

Neither is strictly better. The columns that matter for this proposal
are the second and the last two.

## The one thing worth changing

`cdif-xas-UKDS` keys its intermediate on XDI-flavoured names.
`cdi:Facility_name` means simultaneously *the facility* and *what XDI
calls it*. That works for one input format and has nowhere to put a
second: there is no place to record that the same concept arrived from
`NXsource/name` in an HDF5 file.

`hdf5metadata` keys on the concept — `cdifxas:facility` — and records
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

**Adding a format cost one parser.** XDI support in `hdf5metadata` is
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

## What RML genuinely gives you

Stating the other side plainly, because it is not nothing:

- It is a standards-track mapping language, which matters for a
  standards project.
- The mapping is inspectable as data by people who do not read Python.
- It is the artifact that has been reviewed.

If those outweigh the costs for your governance, that is a legitimate
answer and this proposal fails on its merits rather than on argument.

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

## Open issues, stated rather than hidden

- **`hdf5metadata` has no Dataverse integration at all.** It emits
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

- `usgin/hdf5metadata` — `DESIGN.md`, `STATUS.md`
- `XAS-CDIF/exampleMetadata-hdf5metadata/README.md` — both pipelines'
  output over the same 55 files, with the differences characterised
- `cdif-xas-UKDS/UPLIFT-INSTRUCTIONS.md` — the CDIF 1.1 uplift already
  applied here
