import json
import os
import subprocess
import sys
from pathlib import Path

from api.FrameAndValidate import frame_cdif_document, validate_against_schema

# Path resolution: Docker container mounts everything under /files; a
# local checkout runs from the repo root. Prefer env-var overrides so
# neither environment is baked into the code.
BASE_DIR = os.environ.get("CDIF_XAS_BASE_DIR",
                          "/files/" if Path("/files").is_dir()
                          else str(Path(__file__).resolve().parent.parent) + "/")
RESOURCES_DIR = os.environ.get("CDIF_XAS_RESOURCES_DIR",
                               BASE_DIR + "resources")


def _discover_mapper_jar() -> str:
    """Locate the RMLMapper jar. Preference order:
       1. RMLMAPPER_JAR env var (explicit override).
       2. Newest rmlmapper-*.jar under <BASE_DIR>/lib/.
       3. Hard fallback string (may not exist — will fail at subprocess.run).
    """
    env_val = os.environ.get("RMLMAPPER_JAR")
    if env_val:
        return env_val
    lib_dir = Path(BASE_DIR) / "lib"
    if lib_dir.is_dir():
        jars = sorted(lib_dir.glob("rmlmapper-*.jar"), key=lambda p: p.stat().st_mtime)
        if jars:
            return str(jars[-1])
    return str(lib_dir / "rmlmapper-8.1.0-r0-all.jar")


MAPPER_JAR = _discover_mapper_jar()
CONTEXT_PATH = RESOURCES_DIR + "/context.json"

# Core Discovery Profile
CD_MAPPING_FILE = RESOURCES_DIR + "/mapping_cd.ttl"
CD_OUTPUT_FILE = RESOURCES_DIR + "/cdif_cd.jsonld"
CD_FRAMED_FILE = RESOURCES_DIR + "/cdif_cd_framed.jsonld"

CD_FRAME_PATH = RESOURCES_DIR + "/CDIFDiscoveryDoc-frame.jsonld"
CD_SCHEMA_PATH = RESOURCES_DIR + "/CDIFDiscoveryDocStructuredSchema.json"

# Data Description Structure Profile
DDS_MAPPING_FILE = RESOURCES_DIR + "/mapping_dds.ttl"
DDS_OUTPUT_FILE = RESOURCES_DIR + "/cdif_dds.jsonld"
DDS_FRAMED_FILE = RESOURCES_DIR + "/cdif_dds_framed.jsonld"

DDS_FRAME_PATH = RESOURCES_DIR + "/CDIFDiscoveryDataDescriptionStructure-frame.jsonld"
# Validate against the CDIF XAS document profile schema (aggregated
# resolved schema for core + discovery + data_description + data_structure
# + xasCore + xasOptional). Snapshot at:
#   https://github.com/smrgeoinfo/XAS-CDIF/blob/cdifxasRelease/release/cdifXASDocumentResolvedSchema.json
DDS_SCHEMA_PATH = RESOURCES_DIR + "/cdifXASDocumentResolvedSchema.json"

def map(profile: str):
    if profile == "Core Discovery":
        mapping_file = CD_MAPPING_FILE
        output_file = CD_OUTPUT_FILE
    elif profile == "Data Description Structure":
        mapping_file = DDS_MAPPING_FILE
        output_file = DDS_OUTPUT_FILE

    result = subprocess.run(
        ["java", "-jar", MAPPER_JAR, "-m", mapping_file, "-o", output_file, "-s", "jsonld"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Surface the JVM stderr so the caller can diagnose. Previously
        # subprocess.CalledProcessError swallowed the actual message.
        print("=" * 60)
        print(f"RMLMapper FAILED (exit {result.returncode})")
        print("--- stdout ---")
        print(result.stdout)
        print("--- stderr ---")
        print(result.stderr)
        print("=" * 60)
        raise subprocess.CalledProcessError(
            result.returncode, result.args,
            output=result.stdout, stderr=result.stderr,
        )
    

def _drop_incomplete_additional_properties(node):
    """Recursively strip schema:additionalProperty entries that lack
    schema:value.

    Rationale: the RML mapping's optional-content TriplesMaps
    (Beamline.collimation, Detector.i0, Sample.prep, ...) iterate on
    the parent node's presence. When the source key is absent the
    referenced value is null, but the subject is still emitted with
    schema:name + schema:propertyID — a PropertyValue with no
    schema:value, which fails the base CDIF AdditionalProperty shape
    (schema:value is required). RMLMapper's JSONPath engine does not
    support the compound '&&' / '!' predicates that would let us
    skip these at iteration time, so we filter them here after framing.

    Real cases where the sub-TriplesMap should keep firing but the
    source value is legitimately absent (Mono.d_spacing on B18) are
    handled by placeholder injection in api/cdi.py, so those items
    have a real (if 'unknown') value and pass this filter.
    """
    if isinstance(node, dict):
        aps = node.get("schema:additionalProperty")
        if isinstance(aps, list):
            filtered = [
                ap for ap in aps
                if not (isinstance(ap, dict) and "schema:value" not in ap)
            ]
            if filtered != aps:
                node["schema:additionalProperty"] = filtered
        elif isinstance(aps, dict) and "schema:value" not in aps:
            del node["schema:additionalProperty"]
        for v in node.values():
            _drop_incomplete_additional_properties(v)
    elif isinstance(node, list):
        for x in node:
            _drop_incomplete_additional_properties(x)


# OGC nil-value URI, used as sentinel where the constraint demands an
# IRI reference (schema:contributor filler on a Role wrapper, missing
# schema:identifier on a DefinedTerm, etc.).
OGC_NIL_MISSING = "http://www.opengis.net/def/nil/OGC/0/missing"


def _has_type(node_types, target):
    if isinstance(node_types, str):
        return node_types == target
    if isinstance(node_types, list):
        return target in node_types
    return False


def _ensure_person_has_name_or_identifier(node):
    """Enforce the CDIF Person shape: every schema:Person must carry at
    least one of schema:name or schema:identifier.

    Source of truth: _sources/schemaorgProperties/person/rules.shacl
    in the CDIF metadataBuildingBlocks repo (cdifd:CDIFPersonShape) —
    an sh:or of (has schema:identifier) or (has schema:name >= 3 chars).

    Where our current mapping falls short: TriplesMap_dv_creator reads
    the Person's schema:name from $['schema:author']['schema:name'] on
    the Dataset. In local mode api/local_input.py always emits that
    value (as "unknown" placeholder). In Dataverse mode it depends on
    the exported schema:author carrying schema:name — if it doesn't,
    the framed Person has neither name nor identifier and fails SHACL.

    General safety net rather than a fix for one known site. Any
    @type-includes-schema:Person node without schema:name AND without
    schema:identifier gets schema:name = "unknown" injected. Real data
    is never overwritten.
    """
    if isinstance(node, dict):
        if _has_type(node.get("@type"), "schema:Person"):
            if not node.get("schema:name") and not node.get("schema:identifier"):
                node["schema:name"] = "Missing"
        for v in node.values():
            _ensure_person_has_name_or_identifier(v)
    elif isinstance(node, list):
        for x in node:
            _ensure_person_has_name_or_identifier(x)


def _ensure_organization_has_name_or_identifier(node):
    """Mirror of _ensure_person_has_name_or_identifier for
    schema:Organization. Same shape family (cdifd:CDIFOrganizationShape
    in _sources/schemaorgProperties/organization/rules.shacl) — an
    sh:or of (schema:identifier) or (schema:name).

    Sentinel: schema:name = "Missing" (per user directive; distinct
    from Person's "unknown" to signal the two came from different
    source paths).
    """
    if isinstance(node, dict):
        if _has_type(node.get("@type"), "schema:Organization"):
            if not node.get("schema:name") and not node.get("schema:identifier"):
                node["schema:name"] = "Missing"
        for v in node.values():
            _ensure_organization_has_name_or_identifier(v)
    elif isinstance(node, list):
        for x in node:
            _ensure_organization_has_name_or_identifier(x)


def _ensure_role_has_contributor(node):
    """Enforce cdifd:CDIFRoleShape
    (_sources/schemaorgProperties/agentInRole/rules.shacl):
    a schema:Role must have a schema:contributor that is a Person,
    Organization, or IRI reference.

    Safety net when the Role wrapper fires but the referenced
    Person/Organization sub-map produces nothing (e.g. Dataverse
    export missing the entity being wrapped). Injects an OGC nil-URI
    IRI reference so the Role's required contributor slot is filled
    — validation stays green and the sentinel signals that the value
    was placeholded rather than genuinely absent.
    """
    if isinstance(node, dict):
        if _has_type(node.get("@type"), "schema:Role"):
            if not node.get("schema:contributor"):
                node["schema:contributor"] = {"@id": OGC_NIL_MISSING}
        for v in node.values():
            _ensure_role_has_contributor(v)
    elif isinstance(node, list):
        for x in node:
            _ensure_role_has_contributor(x)


def _ensure_definedterm_has_name_or_identifier(node):
    """Enforce that any schema:DefinedTerm carries at least a
    schema:name or a schema:identifier
    (cdifd:CDIFDefinedTermShape in
    _sources/schemaorgProperties/agentInRole/rules.shacl and
    _sources/schemaorgProperties/spatialExtent/rules.shacl).

    Sentinel when neither is present: schema:identifier = OGC nil URI
    (IRI form — DefinedTerm identifiers are typically resolvable URIs
    to a controlled vocabulary term).
    """
    if isinstance(node, dict):
        if _has_type(node.get("@type"), "schema:DefinedTerm"):
            if not node.get("schema:name") and not node.get("schema:identifier"):
                node["schema:identifier"] = {"@id": OGC_NIL_MISSING}
        for v in node.values():
            _ensure_definedterm_has_name_or_identifier(v)
    elif isinstance(node, list):
        for x in node:
            _ensure_definedterm_has_name_or_identifier(x)


def _materialize_blank_node_ids(node):
    """Rewrite JSON-LD blank-node @ids (`_:b14`) to compact `ex:blank/b14`
    IRIs so JSON-only validators (e.g. Oxygen) don't flag them as
    invalid URIs.

    JSON-LD's `_:` syntax is valid RDF (denotes a blank node) but is
    not a valid URI in a plain-JSON context. Consumers that read the
    framed document as JSON — not as JSON-LD — see `@id` values that
    fail URI-format checks. Materialize each unique `_:xxx` as
    `ex:blank/xxx` (relative to the `ex: https://example.org/` prefix
    bound in resources/context.json). Same substitution everywhere so
    references still resolve to the same subject.
    """
    def _rewrite(val):
        if isinstance(val, str) and val.startswith("_:"):
            return "ex:blank/" + val[2:]
        return val

    if isinstance(node, dict):
        if "@id" in node:
            node["@id"] = _rewrite(node["@id"])
        for v in node.values():
            _materialize_blank_node_ids(v)
    elif isinstance(node, list):
        for x in node:
            _materialize_blank_node_ids(x)


def frame(profile: str):
    if profile == "Core Discovery":
        output_file = CD_OUTPUT_FILE
        frame_path = CD_FRAME_PATH
        framed_file = CD_FRAMED_FILE
    elif profile == "Data Description Structure":
        output_file = DDS_OUTPUT_FILE
        frame_path = DDS_FRAME_PATH
        framed_file = DDS_FRAMED_FILE

    framed = frame_cdif_document(output_file, frame_path, CONTEXT_PATH)
    _drop_incomplete_additional_properties(framed)
    _ensure_person_has_name_or_identifier(framed)
    _ensure_organization_has_name_or_identifier(framed)
    _ensure_role_has_contributor(framed)
    _ensure_definedterm_has_name_or_identifier(framed)
    _materialize_blank_node_ids(framed)
    with open(framed_file, 'w', encoding='utf-8') as f:
        json.dump(framed, f, indent=2)

def validate(profile: str):
    if profile == "Core Discovery":
        framed_file = CD_FRAMED_FILE
        schema_path = CD_SCHEMA_PATH
    elif profile == "Data Description Structure":
        framed_file = DDS_FRAMED_FILE
        schema_path = DDS_SCHEMA_PATH

    with open(framed_file, "r", encoding="utf-8") as f:
        framed = json.load(f)

        print("\nValidating against schema...")
        result = validate_against_schema(framed, schema_path)

        if result['valid']:
            print("Validation PASSED")
        else:
            print("Validation FAILED")
            print("\nErrors:")
            for error in result['errors']:
                path = '/'.join(str(p) for p in error.absolute_path) if error.absolute_path else '/'
                print(f"  - /{path}: {error.message}")
            sys.exit(1)