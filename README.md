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

The `/cdif` endpoint accepts a local XDI file path (via `file://` URL
or an absolute path). Dataverse's `?exporter=schema.org` enrichment is
skipped and the pipeline generates placeholder schema.org `Dataset`
metadata from the file itself:

- `@id`: `urn:local:xdi:<file-stem>`
- `schema:name`: file stem
- `schema:identifier`: `local:<file-stem>`
- `schema:dateModified` / `schema:datePublished`: file mtime
- `schema:license`: `https://creativecommons.org/licenses/by/4.0/`
  (CDIF metadata default — distinct from any license on the payload
  data, which is unknown in local mode)
- `schema:distribution`: a `DataDownload` whose `contentUrl` points at
  the file's `file://` URI

See `api/local_input.py` for the exact placeholder shape.

```bash
uv sync
uv run uvicorn api.api:app --reload --port 8000
curl "http://localhost:8000/cdif?url=file:///path/to/data.xdi&type=xas"
```

Portable paths for the RML `/map` pipeline are also supported. Set
`RMLMAPPER_JAR=/path/to/rmlmapper-8.1.0-r0-all.jar` (or drop the JAR
at `<repo>/lib/rmlmapper-8.1.0-r0-all.jar`). Set
`CDIF_XAS_RESOURCES_DIR` if the resources folder isn't at the default
`<repo>/resources/`.

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

**Note**: this branch applies UPLIFT-INSTRUCTIONS.md tasks 1–10 in full
(mechanical: namespace rebind, concept renames, conformsTo additions,
@id-form policy, xas:analysisevent + schema:Action, bundled-schema
refresh; editorial: peer prov:used instrument model, X-ray source
wrapper with static defaults, MaterialSample sample block reading
XDI Sample.* headers, DefinedTerm content enrichment for element edge
and symbol).

Known conditional gaps (depend on what the XDI headers carry):

- `schema:object` MaterialSample block only emits if the XDI has a
  `# Sample.name` header (parsed to `cdi:Sample`). Missing Sample header
  → no sample node → SHACL will flag the activity as missing
  `schema:object`. Add a `# Sample.name: ...` header to your XDI, or
  supply the sample name in a wrapping process.
- The element-symbol keyword's `schema:name` reads
  `# Element.name: ...`. If missing, the DefinedTerm lacks a name and
  may fail xasCore's DefinedTerm shape.
- `xas:samplepreparation` PropertyValue only emits if the XDI has a
  `# Sample.prep` header.
- The `schema:propertyID` on `schema:variableMeasured` items is built by
  a GREL string_replace that prepends `https://w3id.org/cdif/xas/` to
  whatever `$['meaning']` is. Values with spaces or mixed case (e.g.
  "mono energy") produce non-resolving IRIs. If the column-meaning
  build in `api/cdif.py` doesn't already normalize to v2 glossary local
  names (lowercase, no spaces, no underscores), consider adding a
  normalization step there.

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