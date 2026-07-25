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

**Note**: the mapping output still needs the content-correctness uplift
described in [`UPLIFT-INSTRUCTIONS.md`](./UPLIFT-INSTRUCTIONS.md) to
validate against the current `xasDocument/1.0` profile. Local mode gets
you a running pipeline against your XDI files; it does not change what
the mapping produces.