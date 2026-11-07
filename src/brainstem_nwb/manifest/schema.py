"""JSON Schemas of the manifest and the validation report (committed under schemas/)."""

from __future__ import annotations

from typing import Any

from .._version import MANIFEST_SCHEMA_VERSION, REPORT_SCHEMA_VERSION
from .models import Manifest


def manifest_schema() -> dict[str, Any]:
    schema = Manifest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://github.com/brainstem-org/brainstem-nwb/schemas/manifest-{MANIFEST_SCHEMA_VERSION}.schema.json"
    schema["title"] = f"brainstem-nwb conversion manifest {MANIFEST_SCHEMA_VERSION}"
    return schema


def report_schema() -> dict[str, Any]:
    from ..validation.report import ValidationReport

    schema = ValidationReport.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = (f"https://github.com/brainstem-org/brainstem-nwb/schemas/"
                     f"validation-report-{REPORT_SCHEMA_VERSION}.schema.json")
    schema["title"] = f"brainstem-nwb validation report {REPORT_SCHEMA_VERSION}"
    return schema


SCHEMA_FILES = {
    f"manifest-{MANIFEST_SCHEMA_VERSION}.schema.json": manifest_schema,
    f"validation-report-{REPORT_SCHEMA_VERSION}.schema.json": report_schema,
}
