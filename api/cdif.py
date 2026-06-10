import json

from pyld import jsonld as jsonldlib


def generate_cdif(cdi_jsonld) -> dict[str, any]:
    datajson = cdi_jsonld

    # Helper functions for blank-node inlining
    def collect_nodes(obj, store):
        if isinstance(obj, dict):
            node_id = obj.get("@id")
            if node_id and node_id.startswith("_:"):
                store[node_id] = obj
            for v in obj.values():
                collect_nodes(v, store)
        elif isinstance(obj, list):
            for v in obj:
                collect_nodes(v, store)

    def deep_clone(o):
        try:
            return json.loads(json.dumps(o))
        except Exception:
            return o

    def inline_refs(obj, node_map, seen_ids):
        if isinstance(obj, dict):
            if set(obj.keys()) == {"@id"} and isinstance(obj.get("@id"), str) and obj["@id"].startswith("_:"):
                ref_id = obj["@id"]
                target = node_map.get(ref_id)
                if target and ref_id not in seen_ids:
                    seen_ids.add(ref_id)
                    inlined = inline_refs(deep_clone(target), node_map, seen_ids)
                    seen_ids.discard(ref_id)
                    return inlined
                return obj
            return {k: inline_refs(v, node_map, seen_ids) for k, v in obj.items()}
        if isinstance(obj, list):
            return [inline_refs(v, node_map, seen_ids) for v in obj]
        return obj

    frame_context = {
        "@vocab": "http://ddialliance.org/Specification/DDI-CDI/1.0/RDF/",
        "schema": "http://schema.org/",
        "dcterms": "http://purl.org/dc/terms/",
        "geosparql": "http://www.opengis.net/ont/geosparql#",
        "spdx": "http://spdx.org/rdf/terms#",
        "time": "http://www.w3.org/2006/time#",
        "nx": "https://xas.org/dictionary/",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "cdifq": "https://cdif.codata.org/concept/",
        "prov": "http://www.w3.org/ns/prov#",
        "xas": "http://ddialliance.org/Specification/XAS/",
        "cdi": "https://ddi-cdi.org/label/"
    }

    # Try to embed distribution nodes instead of blank-node references using JSON-LD framing
    try:
        doc = json.loads(datajson)
        frame = {
            "@context": frame_context,
            "@type": "schema:Dataset",
            "@embed": "@always",
            "@explicit": False
        }
        framed = jsonldlib.frame(doc, frame)
        compacted = jsonldlib.compact(framed, frame_context)
        # Post-process: inline blank-node references {"@id": "_:b..."} with their full node objects
        node_map = {}
        collect_nodes(compacted, node_map)
        ddicdi_models = inline_refs(compacted, node_map, set())

        # Collect XAS and CDI namespace nodes from the original document that are
        # not matched by the schema:Dataset frame (e.g. SKOS concept/vocabulary terms).
        # Also include all blank nodes so their values can be inlined into CDI nodes.
        xas_ns = "http://ddialliance.org/Specification/XAS/"
        cdi_label_ns = "https://ddi-cdi.org/label/"
        all_doc_nodes = doc if isinstance(doc, list) else doc.get("@graph", [])
        extra_nodes_raw = [
            node for node in all_doc_nodes
            if isinstance(node, dict) and (
                str(node.get("@id", "")).startswith(xas_ns) or
                str(node.get("@id", "")).startswith(cdi_label_ns) or
                str(node.get("@id", "")).startswith("_:")
            )
        ]

    except Exception:
        ddicdi_models = json.loads(datajson)
        extra_nodes_raw = []

    # Wrap output with requested top-level @context and @graph
    if isinstance(ddicdi_models, dict) and "@graph" in ddicdi_models:
        graph_nodes = ddicdi_models.get("@graph", [])
    elif isinstance(ddicdi_models, list):
        graph_nodes = ddicdi_models
    else:
        graph_nodes = [ddicdi_models]

    # Compact XAS and CDI nodes (blank nodes included so values resolve),
    # then inline any remaining blank-node references and add only named nodes.
    if extra_nodes_raw:
        extra_doc = {"@context": frame_context, "@graph": extra_nodes_raw}
        extra_compacted = jsonldlib.compact(extra_doc, frame_context)
        extra_graph = extra_compacted.get("@graph", [extra_compacted])
        # Build node_map from blank nodes in the compacted extra graph
        extra_node_map = {}
        collect_nodes({"@graph": extra_graph}, extra_node_map)
        # Inline blank-node references and keep only named (non-blank) nodes
        graph_nodes.extend([
            inline_refs(node, extra_node_map, set())
            for node in extra_graph
            if not str(node.get("@id", "")).startswith("_:")
        ])

    payload = {
        "@context": frame_context,
        "@graph": graph_nodes,
    }

    col_node = next(
        (n for n in payload.get("@graph", []) if n.get("@id") == "cdi:Column"),
        None
    )
    columns = []
    if col_node:
        for k, v in col_node.items():
            if k.startswith("cdi:Column_") and isinstance(v, dict):
                entry = {"columnKey": k.replace("cdi:", ""), "definition": v.get("skos:definition", "")}
                # Attach meaning from matching xas: ontology term if present
                col_name = v.get("skos:definition", "").split(" ")[0]
                xas_term = next(
                    (n for n in payload.get("@graph", [])
                    if n.get("@id") == f"xas:Column.N.{col_name}"),
                    None
                )
                if xas_term:
                    entry["meaning"] = xas_term.get("skos:definition", "")
                columns.append(entry)

    payload["columns"] = columns

    return payload
