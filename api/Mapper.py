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

    subprocess.run(
        ["java", "-jar", MAPPER_JAR, "-m", mapping_file, "-o", output_file, "-s", "jsonld"],
        capture_output=True,
        text=True,
        check=True
    )
    

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