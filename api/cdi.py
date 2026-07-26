import os
from datetime import datetime
from pathlib import Path
import re
from typing import Optional
from urllib.parse import urlparse
import requests
import rdflib

from api.local_input import is_local_path, read_local_xdi


# XDI header keys whose values are datetimes and should be normalized
# to ISO 8601 before flowing into CDIF-XAS. The XDI/1.0 spec calls for
# ISO 8601, but real-world files commonly use space-separated ISO or
# slash-date variants; downstream schemas / SHACL want strict ISO.
_DATETIME_KEYS = {"Scan.start_time", "Scan.end_time"}

# Non-ISO formats we accept, tried in order after fromisoformat fails.
_DATETIME_FALLBACK_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%dT%H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%Y%m%d",
    "%Y%m%dT%H%M%S",
)


def _normalize_datetime(value: str) -> Optional[str]:
    """Try to parse a raw XDI datetime string and return ISO 8601.

    Returns None when the value can't be parsed by any recognized form,
    so the caller can preserve the original string and let downstream
    validation surface it. Non-fatal by design: the CDIF-XAS pipeline
    should not hard-fail on a spec-noncompliant timestamp.
    """
    s = value.strip()
    if not s:
        return None
    try:
        # Python 3.11+ fromisoformat accepts space separator and offsets
        return datetime.fromisoformat(s).isoformat()
    except ValueError:
        pass
    for fmt in _DATETIME_FALLBACK_FORMATS:
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


class CDI_DDI:
    def __init__(self, url=None, resources_dir="/app/resources", type=None):
        self.url = url
        self.g = rdflib.Graph()
        self.resources = {}
        self.resources_dir = resources_dir
        self.resources = self.load_resources(type)
        self.skos = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")
        self.rdf = rdflib.Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
        self.dcat = rdflib.Namespace("http://www.w3.org/ns/dcat#")
        self.name = rdflib.Namespace("https://ddi-cdi.org/label/")
        self.label = rdflib.Namespace("https://ddi-cdi.org/label/")
        self.bind = rdflib.Namespace("https://ddi-cdi.org/bind/")
        self.g.bind("skos", self.skos)
        self.g.bind("rdf", self.rdf)
        self.g.bind("dcat", self.dcat)
        self.g.bind("name", self.name)
        self.g.bind("label", self.label)
        self.g.bind("bind", self.bind)
        if url:
            # Local paths (file:// or absolute) read off disk; anything
            # else is treated as an HTTP URL for requests.get.
            if is_local_path(url):
                self.response = read_local_xdi(url)
            else:
                self.response = requests.get(url)
        else:
            self.response = None
        self.lastvariable = ""
        self.data = []
        self.datasets = {}
        self.navigator = None
        self.session_triples = []
        self.triples_memory = []
        # Array-labels line: the last '#'-prefixed comment line before the
        # first data row. XDI files that omit the '# Column.N:' headers
        # (spec-noncompliant but common) usually still carry column names
        # on this line; captured so _synthesize_columns_from_array_labels
        # can back-fill the missing cdi:Column_N triples after parse.
        self.array_labels_line = None

    def load_resources(self, type):
        self.resources = {}
        for file in os.listdir(self.resources_dir):
            if type in file:
                #print(type, file)
                if file.endswith(".jsonld"):
                    self.resources[file.replace(".jsonld", "")] = self.g.parse(os.path.join(self.resources_dir, file), format="json-ld")
                elif file.endswith(".ttl"):
                    self.resources[file.replace(".ttl", "")] = self.g.parse(os.path.join(self.resources_dir, file), format="turtle")
        return self.resources
    
    def check_variable_name(self, variable_name):
        if variable_name.startswith('#'):
            return True
        else:
            return False
        
    def parse_structure(self, value):
        if ':' in value:
            # NON-greedy on the name half so multi-colon values parse
            # correctly: "# Beamline.focusing: Pitch: 2.3; Height: -6.4"
            # -> name = "Beamline.focusing", value = "Pitch: 2.3; ...".
            # Previously the greedy match assigned name up to the LAST
            # colon, producing garbled cdi: predicate URIs and empty
            # skos:definition values.
            compound_variable_name = re.search(r'#\s+(.*?)\:', value)
            variable_value = re.search(r'\:\s*(.*)', value)
            return compound_variable_name, variable_value
        else:
            return None, value
    
    def parse_xdi(self, include_data: bool = True):
        """Parse XDI header lines (and, by default, data rows) into rdflib.

        If include_data=False, data rows are skipped entirely. That drops
        thousands of rdf:List add() calls for large XDI files and cuts
        end-to-end /cdif time from minutes to seconds. Metadata output
        is identical either way; only the row-by-row triples are omitted.
        """
        # Track the most recent '#'-prefixed line that isn't a compound
        # header ('Namespace.field: value') or a structural marker
        # ('# ---', '# ///'). When we hit the first data row this holds
        # the array-labels line for column-name back-fill.
        pending_last_comment = None
        for line in self.response.text.split("\n"):
            # Variables path
            if self.check_variable_name(line):
                stripped = line.strip()
                # Ignore structural markers ('# ---' end-of-header,
                # '# ///' free-form-comment separator, blank '#').
                if (stripped and stripped != '#'
                        and not stripped.startswith('# ---')
                        and not stripped.startswith('#---')
                        and not stripped.startswith('# ///')
                        and not stripped.startswith('#///')
                        # Only remember comments WITHOUT ':' — a compound
                        # header ('Namespace.field: value') is real data,
                        # not an array-labels candidate.
                        and ':' not in stripped):
                    pending_last_comment = stripped.lstrip('#').strip()
                compound_variable_name, variable_value = self.parse_structure(line)
                if compound_variable_name and variable_value:
                        compound_variable_name = compound_variable_name.group(1).strip('#  ')
                        variable_value = variable_value.group(1)
                        # Canonicalize XDI namespaced key case: XDI/1.0 uses
                        # capitalized namespace + lowercase field
                        # (Facility.name, Beamline.name, Mono.d_spacing).
                        # Real files often use inconsistent case
                        # (Facility.Name, Beamline.Name, Scan.Start_Time).
                        # Lowercase everything after the first '.' so the
                        # downstream RML mapping's canonical predicates
                        # (cdi:Facility_name, cdi:Beamline_name, ...) match
                        # regardless of source-side casing.
                        if '.' in compound_variable_name:
                            head, rest = compound_variable_name.split('.', 1)
                            compound_variable_name = head + '.' + rest.lower()
                        if compound_variable_name in _DATETIME_KEYS:
                            iso = _normalize_datetime(variable_value)
                            if iso is not None:
                                variable_value = iso
                        if '.' in compound_variable_name:
                            compound_variable_name_uri = compound_variable_name.replace(" ", "_").replace(":", "_")
                            variables = compound_variable_name_uri.split('.')
                            for variable_id in range(0,len(variables)-1):
                                variable_name = variables[variable_id]
                                variable_next = variables[variable_id+1]
                                self.g.add((rdflib.URIRef(self.name + variable_name), self.skos.prefLabel, rdflib.Literal(variable_name)))
                                self.g.add((rdflib.URIRef(self.name + variable_name), self.skos.broader, rdflib.URIRef(self.name + variable_name + '_' + variable_next)))
                                blank = rdflib.BNode()
                                self.g.add((rdflib.URIRef(self.name + variable_name), rdflib.URIRef(self.name + variable_name + '_' + variable_next), blank))
                                self.g.add((blank, rdflib.URIRef(self.skos.definition), rdflib.Literal(variable_value)))
                                self.navigator = blank
                        else:
                            variable_name = compound_variable_name.strip('#  ').replace(" ", "_")
                            try:
                                variable_value = variable_value.group(1)
                                self.g.add((rdflib.URIRef(self.name + variable_name), self.skos.prefLabel, rdflib.Literal(variable_value)))
                            except:
                                pass
                        try:
                            self.lastvariable = variable_name
                            self.g.add((rdflib.URIRef(self.name + variable_name), self.skos.prefLabel, rdflib.Literal(variable_value)))
                            self.data.append({
                                variable_name: variable_value
                            })
                        except:
                            pass
            # Data path
            else:
                # Stash the last '#'-comment as the array-labels line the
                # first time we transition into data. Subsequent data
                # rows leave it untouched.
                if self.array_labels_line is None and pending_last_comment:
                    self.array_labels_line = pending_last_comment
                if not include_data:
                    continue
                if self.navigator:
                    if not self.lastvariable in self.datasets:
                        self.datasets[self.navigator] = [line.strip()]
                        for row in line.strip().split(' '):
                            self.g.add((self.navigator, rdflib.URIRef(self.rdf.List), rdflib.Literal(row)))
                    else:
                        self.datasets[self.navigator].append(line.strip())
                        for row in line.strip().split(' '):
                            self.g.add((self.navigator, rdflib.URIRef(self.rdf.List), rdflib.Literal(row)))

        return self.g

def _synthesize_columns_from_array_labels(g: "rdflib.Graph",
                                          name_ns: "rdflib.Namespace",
                                          skos_ns: "rdflib.Namespace",
                                          labels_line: str) -> None:
    """Back-fill cdi:Column / cdi:Column_N SKOS triples from an
    XDI array-labels line when the file omits '# Column.N: ...' headers.

    Rationale: XDI/1.0 specifies both '# Column.N:' compound headers
    AND a whitespace-separated array-labels line right after '# ---'.
    Real files often carry only the array-labels line. Without
    Column.N headers the mapping emits no data structure, which then
    fails xasCore's conformsTo declarations for data_description /
    data_structure. Reconstruct the missing headers here from the
    array-labels line so those profile URIs stay honest.

    Fires only when the graph has no cdi:Column subject yet (real
    Column headers were parsed → do nothing).
    """
    from rdflib import BNode, Literal, URIRef
    column_uri = URIRef(str(name_ns) + "Column")
    if (column_uri, None, None) in g:
        return
    tokens = labels_line.split()
    if not tokens:
        return
    g.add((column_uri, URIRef(str(skos_ns) + "prefLabel"), Literal("Column")))
    for i, tok in enumerate(tokens, start=1):
        child_pred = URIRef(str(name_ns) + f"Column_{i}")
        broader = URIRef(str(skos_ns) + "broader")
        g.add((column_uri, broader, child_pred))
        blank = BNode()
        g.add((column_uri, child_pred, blank))
        g.add((blank, URIRef(str(skos_ns) + "definition"), Literal(tok)))


def _add_xas_fallback_triples(g: "rdflib.Graph", name_ns: "rdflib.Namespace",
                              skos_ns: "rdflib.Namespace") -> None:
    """Inject placeholder triples so the RML mapping can populate
    xasCore-required content that many XDI dialects don't carry
    explicitly. Each fallback fires only when the corresponding
    real key is absent — real data from the XDI is never overwritten.

    Fallbacks currently emitted:
      cdi:Mono has no cdi:Mono_d_spacing -> synthesize with value 'unknown'
        (correct value depends on the crystal cut; the fallback keeps
        the schema:value predicate present so xasCore validates)

    Add more as new XDI dialects surface with different gaps.
    """
    from rdflib import BNode, Literal, URIRef

    def _has_child(subject: "URIRef", child_local: str) -> bool:
        child_pred = URIRef(str(name_ns) + child_local)
        return any(g.triples((subject, child_pred, None)))

    def _synthesize_child(subject: "URIRef", child_local: str, value: str) -> None:
        child_pred = URIRef(str(name_ns) + child_local)
        blank = BNode()
        g.add((subject, child_pred, blank))
        g.add((blank, URIRef(str(skos_ns) + "definition"), Literal(value)))

    mono = URIRef(str(name_ns) + "Mono")
    if (mono, None, None) in g:
        if not _has_child(mono, "Mono_d_spacing"):
            _synthesize_child(mono, "Mono_d_spacing", "unknown")

    # Beamline / Facility schema:name are required by the xasDocument
    # profile (JSON Schema for the beamline peer instrument, SHACL
    # Organization shape for the Facility). When the corresponding
    # cdi:*_name key is absent from the SKOS graph — either because the
    # XDI header is missing OR because it was written in a non-canonical
    # case (e.g. `Facility.Name` with capital N never populates
    # `cdi:Facility_name`) — synthesize a "missing" sentinel so the RML
    # mapping's schema:name lookup finds a value.
    for parent_local, child_local in (
        ("Beamline", "Beamline_name"),
        ("Facility", "Facility_name"),
    ):
        parent = URIRef(str(name_ns) + parent_local)
        if (parent, None, None) in g and not _has_child(parent, child_local):
            _synthesize_child(parent, child_local, "missing")


def generate_cdi(source_url: str, resources_dir: Optional[str], dataset_type: Optional[str], datasetid: Optional[str] = None, datasetversion: Optional[str] = None, include_data: bool = True) -> None:
    from api.cdi import CDI_DDI

    resources_dir_final = resources_dir or os.path.join(Path(__file__).parent.parent, "resources")
    generator = CDI_DDI(
        url=source_url,
        resources_dir=resources_dir_final,
        type=dataset_type,
    )
    cdi_graph = generator.parse_xdi(include_data=include_data)

    # Back-fill Column headers from the array-labels line when the XDI
    # omits '# Column.N:' comments (spec-noncompliant but common).
    if generator.array_labels_line:
        _synthesize_columns_from_array_labels(
            cdi_graph, generator.name, generator.skos,
            generator.array_labels_line,
        )

    _add_xas_fallback_triples(cdi_graph, generator.name, generator.skos)

    # Quick sanity/compatibility check of the CDI graph
    try:
        _ = cdi_graph.serialize(format="json-ld")
    except Exception:
        print("Warning: CDI graph serialization failed; using empty graph as fallback.")
        cdi_graph = rdflib.Graph()
    # Enrich the graph with schema.org Dataset metadata.
    # Local mode: build placeholder metadata from the file itself
    # (Dataverse isn't available).
    # Otherwise: fetch the schema.org export from Dataverse.
    if is_local_path(source_url):
        try:
            from api.local_input import build_placeholder_dataset
            for triple in build_placeholder_dataset(source_url):
                cdi_graph.add(triple)
        except Exception as e:
            print(f"Warning: placeholder metadata generation failed: {e}")
    else:
        schema_url = None
        if datasetid:
            # Try to infer base site from source_url; fallback to dev codata
            try:
                parsed = urlparse(source_url)
                base = parsed.scheme + "://" + parsed.netloc if parsed.scheme and parsed.netloc else "https://dataverse.dev.codata.org"
            except Exception:
                base = "https://dataverse.dev.codata.org"
            schema_url = base.rstrip("/") + "/api/datasets/export?exporter=schema.org&persistentId=" + datasetid
        else:
            # Default example fallback if no datasetid provided
            schema_url = "https://dataverse.dev.codata.org/api/datasets/export?exporter=schema.org&persistentId=doi%3A10.5072/FK2/8MODGT"
        try:
            schema_graph = rdflib.Graph()
            schema_graph.parse(schema_url, format="json-ld")
            # Merge schema_graph into cdi_graph
            for triple in schema_graph:
                cdi_graph.add(triple)
        except Exception:
            # Ignore enrichment errors to not block core generation
            pass

    # Stable marker for the RML iterators: tag every schema:Dataset in
    # the merged graph with cdif:isDatasetRecord "yes". Emitted for both
    # the local placeholder Dataset (redundant with local_input.py but
    # harmless — same triple) and any Dataverse-enriched Dataset. RML
    # iterators use this marker instead of a regex on the Dataverse
    # citation-URL @id shape.
    _SCHEMA = rdflib.Namespace("http://schema.org/")
    _CDIF = rdflib.Namespace("https://w3id.org/cdif/")
    for ds_subj in set(cdi_graph.subjects(rdflib.RDF.type, _SCHEMA.Dataset)):
        cdi_graph.add((ds_subj, _CDIF.isDatasetRecord, rdflib.Literal("yes")))

    return cdi_graph