"""
The BrainSTEM JSON schema behind each typed JSON field of a record.

Records keep type-specific values in JSON fields (``type_json``, ``coordinates_json``,
``details_json``) and store the version of the schema the server validated them against. A schema
is identified as ``<Family>/<Type>@<version>``; published versions never change and are served at
``https://www.brainstem.org/schemas/<Family>/<Type>/<version>.json`` (the schema's ``$id``). A
record that stores no version gets the id ``<Family>/<Type>``: its version is unknown, so it points
to the listing of the type's versions, not to the current one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..store.graph import Record, RecordStore

CANONICAL_BASE = "https://www.brainstem.org/schemas/"

# model label -> [(kind, JSON field, schema family, type field, version field)]
_FIELDS: dict[str, list[tuple[str, str, str, str, str]]] = {
    "modules.procedure": [("details", "type_json", "Procedure", "type", "type_schema_version"),
                          ("coordinates", "coordinates_json", "Coordinates", "coordinates",
                           "coordinates_schema_version")],
    "modules.dataacquisition": [("details", "type_json", "DataAcquisition", "type", "type_schema_version")],
    "modules.manipulation": [("details", "type_json", "Manipulation", "type", "type_schema_version")],
    "modules.equipment": [("details", "type_json", "Equipment", "type", "type_schema_version"),
                          ("coordinates", "coordinates_json", "Coordinates", "coordinates",
                           "coordinates_schema_version")],
    "modules.experimentalinterface": [
        ("details", "type_json", "ExperimentalInterface", "type", "type_schema_version"),
        ("coordinates", "coordinates_json", "Coordinates", "coordinates", "coordinates_schema_version")],
    "modules.specimenprocedure": [("details", "type_json", "SpecimenProcedure", "type", "type_schema_version")],
    "modules.procedurestage": [("details", "details_json", "SpecimenProcedureStage", "detail_type",
                                "details_schema_version")],
    "modules.materialusage": [("details", "details_json", "MaterialUsage", "type", "details_schema_version")],
    "modules.consumablestock": [("details", "type_json", "ConsumableStock", "type", "type_schema_version")],
    "resources.consumable": [("details", "type_json", "Consumable", "type", "type_schema_version")],
    "resources.hardwaredevice": [("details", "type_json", "HardwareDevice", "type", "type_schema_version")],
    "stem.specimenset": [("details", "type_json", "SpecimenSet", "type", "type_schema_version")],
    "stem.specimen": [("details", "type_json", "Specimen", "type", "type_schema_version")],
}
_LOG_ENTRY_LABELS = ("modules.moduleslogentry", "modules.startendmoduleslogentry")
_LOG_FAMILIES = {"modules.subjectlog": "SubjectLog", "modules.procedurelog": "ProcedureLog",
                 "modules.specimenlog": "SpecimenLog"}

Kind = Literal["details", "coordinates"]


@dataclass(frozen=True)
class SchemaRef:
    family: str
    type: str
    version: str  # "" when the record stores none

    @property
    def id(self) -> str:
        return f"{self.family}/{self.type}@{self.version}" if self.version else f"{self.family}/{self.type}"

    def url(self, base: str = CANONICAL_BASE) -> str:
        base = base if base.endswith("/") else base + "/"
        if self.version:
            return f"{base}{self.family}/{self.type}/{self.version}.json"
        return f"{base}{self.family}/{self.type}/"  # version unknown: the listing of the type's versions


def parse_schema_id(schema_id: str) -> SchemaRef:
    path, _, version = schema_id.partition("@")
    family, _, type_ = path.partition("/")
    return SchemaRef(family=family, type=type_, version=version)


def _has_value(value: object) -> bool:
    return value not in (None, "", {}, [])


def schema_refs(store: RecordStore, record: Record) -> dict[str, SchemaRef]:
    """The schemas of a record's filled JSON fields: {'details': ..., 'coordinates': ...}."""
    refs: dict[str, SchemaRef] = {}
    if record.label in _LOG_ENTRY_LABELS:
        log = store.get(str(record.get("content_type") or "").lower(), record.get("object_id"))
        family = _LOG_FAMILIES.get(log.label) if log is not None else None
        if log is not None and family and log.get("type") and _has_value(record.get("type_json")):
            refs["details"] = SchemaRef(family, str(log.get("type")), str(record.get("type_schema_version") or ""))
        return refs
    for kind, json_field, family, type_field, version_field in _FIELDS.get(record.label, []):
        code = record.get(type_field)
        if code and _has_value(record.get(json_field)):
            refs[kind] = SchemaRef(family, str(code), str(record.get(version_field) or ""))
    return refs


def collect_schema_refs(store: RecordStore) -> list[SchemaRef]:
    """Every schema the export's records use, sorted by id."""
    found: dict[str, SchemaRef] = {}
    for label in store.labels():
        for record in store.all(label):
            for ref in schema_refs(store, record).values():
                found[ref.id] = ref
    return [found[key] for key in sorted(found)]
