import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Response

from api.Mapper import map, frame, validate
from api.cdi import generate_cdi
from api.cdif import generate_cdif

app = FastAPI()

# Path where the RML pipeline (/map) reads its input JSON. Mirrors
# api/Mapper.py:RESOURCES_DIR resolution so a /cdif call can prepare
# input for a subsequent /map call.
_SKOS_JSON_PATH = Path(
    os.environ.get(
        "CDIF_XAS_RESOURCES_DIR",
        str(Path(__file__).resolve().parent.parent / "resources"),
    )
) / "cdif_skos.json"


@app.get("/")
def read_root():
    return {"message": "XDI to CDIF Service"}

@app.get("/cdif")
def cdif_generate(
    url: str = Query(
        ...,
        description=(
            "Source XDI file. HTTP(S) URL for remote files (default), or "
            "file:// / absolute path for a local file. Local mode skips "
            "Dataverse enrichment and generates placeholder schema.org "
            "Dataset metadata from file name + mtime; see api/local_input.py."
        ),
    ),
    resources: Optional[str] = None,
    type: str = "xas",
    datasetid: Optional[str] = Query(
        None,
        description="Dataverse persistent id (only used for remote URLs).",
    ),
    write_skos: bool = Query(
        True,
        description=(
            "If true (default), write the framed output to "
            "resources/cdif_skos.json so a subsequent /map + /frame + "
            "/validate call consumes THIS XDI file's data instead of the "
            "committed Se_Na2SeO4 fixture. Set false to leave the fixture "
            "untouched."
        ),
    ),
    include_data: bool = Query(
        False,
        description=(
            "If true, include XDI data rows in the SKOS graph as rdf:List "
            "triples. Default false — the row triples are not used by the "
            "downstream RML mapping and add seconds-to-minutes of parse "
            "time on real-size XDI files. Set true only for debugging."
        ),
    ),
):
    graph = generate_cdi(url, resources, type, datasetid, include_data=include_data)
    cdi_jsonld = graph.serialize(format="json-ld")

    pp_data = generate_cdif(cdi_jsonld)

    if write_skos:
        try:
            _SKOS_JSON_PATH.write_text(
                json.dumps(pp_data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            # Don't fail the /cdif response over a disk write; log and continue.
            print(f"Warning: failed to write {_SKOS_JSON_PATH}: {e}")

    dataexport = json.dumps(pp_data)
    return Response(content=dataexport, media_type="application/json")

@app.get("/map")
def mapper(profile: str = Query(...)):
    map(profile)

@app.get("/frame")
def framer(profile: str = Query(...)):
    frame(profile)

@app.get("/validate")
def validator(profile: str = Query(...)):
    validate(profile)