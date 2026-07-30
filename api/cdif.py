import json

from pyld import jsonld as jsonldlib



#: XDI column label -> CDIF XAS concept local name.
#:
#: These are the Column.* rows of xdi-to-cdifxas.sssom.tsv, the crosswalk
#: built and validated by crosswalk/build_crosswalk.py in XAS-CDIF --
#: which checks every concept against the glossary, so a name that is not
#: a real concept fails that build rather than producing a propertyID
#: here that resolves to nothing.
#:
#: Held as a table rather than read from the TSV so the service stays
#: self-contained. If it drifts, the crosswalk is the authority.

def split_column_label(value):
    """`Column.N` value -> (name, unit or None).

    XDI writes a column label as a name optionally followed by a unit:
    `energy eV`. Beamline software sometimes appends its own provenance
    after `||` -- `itrans counts || 13BMD:scaler1_calc3.VAL` -- which is
    neither, so anything from the separator on is dropped first.

    Only a second token is a unit. Three tokens means the label is prose,
    and guessing which word is the unit would be worse than recording
    none. Matches inspect/xdi.py in usgin/hdf5metadata, deliberately:
    the two implementations should read the same label the same way.
    """
    if not value:
        return "", None
    head = value.split("||", 1)[0].strip()
    parts = head.split()
    if not parts:
        return "", None
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], None


#: What a column's propertyID says when no crosswalk row names its
#: concept. The column was measured and is recorded; nothing is claimed
#: about what it means. Saying nothing at all would be indistinguishable
#: from a column nobody looked at.
NIL_MISSING = "http://www.opengis.net/def/nil/OGC/0/missing"

XAS_BASE = "https://w3id.org/cdif/xas/"

COLUMN_CONCEPTS = {
    "energy": "monochromatorenergy",
    "i0": "incidentintensity",
    "itrans": "transmittedintensity",
    "irefer": "referenceintensity",
    "mutrans": "absorptioncoefficient",
    "ifluor": "fluorescenceintensity",
    "mufluor": "fluorescenceabsorptioncoefficient",
    "murefer": "referenceabsorptioncoefficient",
}

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
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "cdifq": "https://cdif.codata.org/concept/",
        "prov": "http://www.w3.org/ns/prov#",
        "xas": "https://w3id.org/cdif/xas/",
        "cdi": "https://ddi-cdi.org/label/",
        # cdif: is used for stable markers on the SKOS graph
        # (e.g. cdif:isDatasetRecord) so the RML iterators can locate
        # the top-level Dataset node without regex-matching its @id.
        "cdif": "https://w3id.org/cdif/"
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
        xas_ns = "https://w3id.org/cdif/xas/"
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

    dataset_id = payload.get("@graph", [])[0].get("@id", "").replace("http://localhost:8080/citation?persistentId=perma:", "")

    col_node = next(
        (n for n in payload.get("@graph", []) if n.get("@id") == "cdi:Column"),
        None
    )

    # for n in payload.get("@graph", []):
    #     print("n: ", n.get("@id", ""))

    columns = []
    if col_node:
        print("col_node: ", col_node)
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
                # The concept this column measures, as the glossary's own
                # local name. schema:propertyID is built from this: it was
                # built from $['meaning'] before, which is a definition
                # sentence, so the IRI it produced could not resolve --
                # and $['meaning'] is only set when a xas:Column.N.* node
                # happens to be in the graph, which it never is, so no
                # propertyID was emitted at all.
                concept = COLUMN_CONCEPTS.get(col_name.lower())
                # The full IRI, built here rather than assembled in the
                # mapping: an unmapped column's propertyID is the OGC nil
                # URI, which is not under the glossary base, so no amount
                # of prefixing gets there from a local name.
                entry["propertyIRI"] = (
                    XAS_BASE + concept if concept else NIL_MISSING)
                # Only when the label states one. Emitting "" asserts
                # that the unit IS the empty string, which a consumer
                # cannot tell from a column whose unit was never
                # recorded -- and 19 of the 55 reference files write a
                # bare `energy` with no unit at all.
                _, unit = split_column_label(v.get("skos:definition", ""))
                if unit:
                    entry["unitText"] = unit
                if concept:
                    entry["conceptLocalName"] = concept
                if dataset_id:
                    entry["componentIRI"] = f"https://example.org/struct/{dataset_id}/comp/{entry['columnKey']}"
                    entry["rvIRI"] = f"https://example.org/struct/{dataset_id}/rv/{entry['columnKey']}"
                    entry["ivIRI"] = f"https://example.org/{dataset_id}/iv/{entry['columnKey']}"
                columns.append(entry)

    payload["columns"] = columns

    return payload
