import os
from pathlib import Path
import re
from typing import Optional
from urllib.parse import urlparse
import requests
import rdflib


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
            self.response = requests.get(url)
        else:
            self.response = None
        self.lastvariable = ""
        self.data = []
        self.datasets = {}
        self.navigator = None
        self.session_triples = []
        self.triples_memory = []

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
            compound_variable_name = re.search(r'#\s+(.*)\:', value)
            variable_value = re.search(r'\:\s*(.*)', value) 
            return compound_variable_name, variable_value
        else:
            return None, value
    
    def parse_xdi(self):
        for line in self.response.text.split("\n"):
            print("line: ", line)
            # Variables path
            if self.check_variable_name(line):
                compound_variable_name, variable_value = self.parse_structure(line)
                print("compound_variable_name: ", compound_variable_name)
                print("variable_value: ", variable_value)
                if compound_variable_name and variable_value:
                        compound_variable_name = compound_variable_name.group(1).strip('#  ') 
                        variable_value = variable_value.group(1)
                        print("compound_variable_name_1: ", compound_variable_name)
                        print("variable_value_1: ", variable_value)
                        if '.' in compound_variable_name:
                            compound_variable_name_uri = compound_variable_name.replace(" ", "_").replace(":", "_")
                            variables = compound_variable_name_uri.split('.')
                            for variable_id in range(0,len(variables)-1):
                                variable_name = variables[variable_id]
                                variable_next = variables[variable_id+1]
                                print("Compound: " + variable_name + '.' + variable_next + " = " + variable_value)
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

def generate_cdi(source_url: str, resources_dir: Optional[str], dataset_type: Optional[str], datasetid: Optional[str] = None, datasetversion: Optional[str] = None) -> None:
    from api.cdi import CDI_DDI

    resources_dir_final = resources_dir or os.path.join(Path(__file__).parent.parent, "resources")
    generator = CDI_DDI(
        url=source_url,
        resources_dir=resources_dir_final,
        type=dataset_type,
    )
    cdi_graph = generator.parse_xdi()

    # for triple in cdi_graph:
    #     print("cdi_graph triple: ", triple)


    # Quick sanity/compatibility check of the CDI graph
    try:
        _ = cdi_graph.serialize(format="json-ld")
    except Exception:
        print("Warning: CDI graph serialization failed; using empty graph as fallback.")
        cdi_graph = rdflib.Graph()
    # Also enrich the graph with schema.org JSON-LD from Dataverse
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

    return cdi_graph