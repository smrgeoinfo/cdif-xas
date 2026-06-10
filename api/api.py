import json
from typing import Optional

from fastapi import FastAPI, Query, Response

from api.Mapper import map, frame, validate
from api.cdi import generate_cdi
from api.cdif import generate_cdif

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "XDI to CDIF Service"}

@app.get("/cdif")
def cdif_generate(
    url: str = Query(...),
    resources: Optional[str] = None,
    type: str = "xas",
    datasetid: Optional[str] = Query(None)
):
    graph = generate_cdi(url, resources, type, datasetid)
    cdi_jsonld = graph.serialize(format="json-ld")

    pp_data = generate_cdif(cdi_jsonld)

    # col_node = next(
    #     (n for n in pp_data.get("@graph", []) if n.get("@id") == "cdi:Column"),
    #     None
    # )
    # columns = []
    # if col_node:
    #     for k, v in col_node.items():
    #         if k.startswith("cdi:Column_") and isinstance(v, dict):
    #             entry = {"columnKey": k, "definition": v.get("skos:definition", "")}
    #             # Attach meaning from matching xas: ontology term if present
    #             col_name = v.get("skos:definition", "").split(" ")[0]
    #             xas_term = next(
    #                 (n for n in pp_data.get("@graph", [])
    #                 if n.get("@id") == f"xas:Column.N.{col_name}"),
    #                 None
    #             )
    #             if xas_term:
    #                 entry["meaning"] = xas_term.get("skos:definition", "")
    #             columns.append(entry)

    # pp_data["columns"] = columns

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