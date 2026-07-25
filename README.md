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

**Note**: this branch applies UPLIFT-INSTRUCTIONS.md tasks 1–5 + 10
(mechanical: namespace rebind, concept renames, conformsTo additions,
@id-form policy, xas:analysisevent + schema:Action, bundled-schema
refresh). Editorial tasks 6–9 (peer prov:used restructure, source
instrument, MaterialSample sample, wired-up measurementTechnique +
keywords) are NOT yet applied — those need domain review. Expect
residual SHACL violations from missing xasCore-required content until
they land; see [`UPLIFT-INSTRUCTIONS.md`](./UPLIFT-INSTRUCTIONS.md) for
the full plan.