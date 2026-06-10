import json
import subprocess
import sys

from api.FrameAndValidate import frame_cdif_document, validate_against_schema

BASE_DIR = "/files/"
RESOURCES_DIR = BASE_DIR + "resources"
MAPPER_JAR = BASE_DIR + "lib/" + "rmlmapper-8.1.0-r0-all.jar"
CONTEXT_PATH = RESOURCES_DIR + "/context.json"

# Core Discovery Profile
CD_MAPPING_FILE = RESOURCES_DIR + "/mapping_cd.ttl"
CD_OUTPUT_FILE = RESOURCES_DIR + "/cdif_cd.jsonld"
CD_FRAMED_FILE = RESOURCES_DIR + "/cdif_framed_cd.jsonld"

CD_FRAME_PATH = RESOURCES_DIR + "/CDIFDiscoveryDoc-frame.jsonld"
CD_SCHEMA_PATH = RESOURCES_DIR + "/CDIFDiscoveryDocStructuredSchema.json"

# Data Description Profile
DD_MAPPING_FILE = RESOURCES_DIR + "/mapping_dd.ttl"
DD_OUTPUT_FILE = RESOURCES_DIR + "/cdif_dd.jsonld"
DD_FRAMED_FILE = RESOURCES_DIR + "/cdif_framed_dd.jsonld"

DD_FRAME_PATH = RESOURCES_DIR + "/cdifDataDescription-frame.jsonld"
DD_SCHEMA_PATH = RESOURCES_DIR + "/cdifDataDescriptionStructuredSchema.json"

def map(profile: str):
    if profile == "Core Discovery":
        mapping_file = CD_MAPPING_FILE
        output_file = CD_OUTPUT_FILE
    elif profile == "Data Description":
        mapping_file = DD_MAPPING_FILE
        output_file = DD_OUTPUT_FILE

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
    elif profile == "Data Description":
        output_file = DD_OUTPUT_FILE
        frame_path = DD_FRAME_PATH
        framed_file = DD_FRAMED_FILE
    
    framed = frame_cdif_document(output_file, frame_path, CONTEXT_PATH)
    with open(framed_file, 'w', encoding='utf-8') as f:
        json.dump(framed, f, indent=2)

def validate(profile: str):
    if profile == "Core Discovery":
        framed_file = CD_FRAMED_FILE
        schema_path = CD_SCHEMA_PATH
    elif profile == "Data Description":
        framed_file = DD_FRAMED_FILE
        schema_path = DD_SCHEMA_PATH

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