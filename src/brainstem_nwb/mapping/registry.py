"""
The BrainSTEM-to-NWB mapping specification, as data.

Every NWB destination the exporter writes is described by a ``MappingRule``: the BrainSTEM
fields it reads, the transformation, units, the condition under which it applies, and what
happens when the source is missing. Mapper functions declare their rules with ``@rules(...)``;
``docs/mapping-spec.md`` is generated from the registry, so the documentation cannot drift
from the code.

Every field of every exported record type is accounted for: it is read by a rule, used to link
records (``STRUCTURAL``), kept in the manifest only (``MANIFEST_ONLY`` with a reason), or
dropped as private bookkeeping (``inventory.DROPPED_FIELDS``). A test enforces this against the
data model the BrainSTEM server publishes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class MappingRule:
    id: str
    destination: str
    sources: tuple[str, ...]
    transform: str
    condition: str = "always"
    missing: str = "not written"
    units: str | None = None
    section: str = "NWBFile"


RULES: dict[str, MappingRule] = {}


def rules(*declared: MappingRule) -> Callable[[F], F]:
    """Register the rules a mapper function implements."""

    def decorator(func: F) -> F:
        for rule in declared:
            if rule.id in RULES and RULES[rule.id] != rule:
                raise ValueError(f"duplicate mapping rule id {rule.id}")
            RULES[rule.id] = rule
        func.__mapping_rules__ = declared  # type: ignore[attr-defined]
        return func

    return decorator


# Fields used to find and link records (which session a record belongs to, its subject, ...),
# not data in their own right.
STRUCTURAL: dict[str, set[str]] = {
    "stem.project": set(),
    "stem.session": {"projects", "subjects", "specimen_sets", "datastorage", "session_type", "status"},
    "stem.subject": {"projects", "species", "strain"},
    "stem.epoch": {"session", "order"},
    "modules.dataacquisition": {"session", "interfaces", "equipment", "order"},
    "modules.manipulation": {"session", "interfaces", "equipment", "order"},
    "modules.behavior": {"session", "subjects", "order"},
    "modules.procedure": {"subject", "procedure_episode", "equipment", "interfaces", "licenses", "protocol", "status"},
    "modules.experimentalinterface": {"subject", "specimen_set", "equipment", "source_material_usage"},
    "modules.equipment": {"setup", "hardwaredevice", "consumable"},
    "modules.materialusage": {"procedure", "specimen_procedure", "experimental_interface", "consumable_stock",
                              "consumable", "order"},
    "modules.consumablestock": {"consumable", "inventory"},
    "modules.procedureepisode": {"subject", "licenses", "protocol"},
    "modules.specimenprocedure": {"specimen_set", "equipment", "protocol", "licenses", "status"},
    "stem.specimenset": {"projects", "subject"},
    "stem.specimen": {"specimen_set", "order"},
    "modules.dataacquisitioninterface": {"dataacquisition", "interface", "order"},
    "modules.manipulationinterface": {"manipulation", "interface", "order"},
    "modules.procedureinterface": {"procedure", "interface"},
    "personal_attributes.protocol": {"licenses"},
    "modules.moduleslogentry": {"content_type", "object_id"},
    "modules.startendmoduleslogentry": {"content_type", "object_id"},
    "taxonomies.anatomicalregion": {"reference"},
    "taxonomies.behavioralparadigm": {"category"},
    "dissemination.publication": {"journal"},
}

_TIMESTAMPS = {"created_at": "record bookkeeping time", "updated_at": "record bookkeeping time"}

# Record types and fields kept in the manifest only, with the reason. "*" covers a whole record type.
MANIFEST_ONLY: dict[str, dict[str, str]] = {
    "stem.project": {
        "is_public": "access setting", "name_used_in_storage": "storage naming",
        "repository_links_json": "listed in the manifest's project section",
        "extra_content_json": "listed in the manifest's project section",
        "publications": "linked publication records: DOIs go to related_publications, the links are kept in the "
                        "manifest",
    },
    "stem.session": {"name_used_in_storage": "used for data paths (Phase 4); in data_sources"},
    "stem.subject": {
        "status": "colony status, not an NWB field", "death_date": "no NWB field",
        "breeding": "colony management",
        "supplier": "supplier record: kept in the manifest and the ndx-brainstem tables",
        "licenses": "regulatory approvals; in the manifest",
        "name_used_in_storage": "storage naming (or subject_id, see subject.label_field)",
        "extra_content_json": "described in Subject.description",
        "tags": "subject tags have no NWB Subject field",
    },
    "stem.epoch": {},
    "modules.dataacquisition": {"image": "uploaded image file reference", "type_schema_version": "schema version"},
    "modules.manipulation": {"type_schema_version": "schema version"},
    "modules.behavior": {},
    "modules.procedure": {
        "type_schema_version": "schema version of details", "coordinates_schema_version": "schema version",
        "anatomical_reference": "atlas record: named in location descriptions, kept in the manifest",
        "coordinate_transform": "transform record: kept in the manifest and the ndx-brainstem tables",
        "performed_by": "user name (first and last): named in procedure text, kept in the manifest",
    },
    "modules.experimentalinterface": {
        "coordinates": "described in device descriptions", "coordinates_json": "described in device descriptions",
        "coordinates_schema_version": "schema version", "type_schema_version": "schema version",
        "persistence": "described in device descriptions", "target_specimens": "specimen links",
    },
    "modules.equipment": {
        "coordinates": "position of equipment in the setup", "coordinates_json": "position in the setup",
        "coordinates_schema_version": "schema version", "type_json": "equipment schemas define no fields",
        "type_schema_version": "schema version", "date_time": "equipment record date",
    },
    "modules.materialusage": {
        "stage": "procedure stage link", "copied_from": "template provenance",
        "source_snapshot": "catalog snapshot at use; the linked catalog record is used",
        "details_schema_version": "schema version", "target_specimens": "specimen links",
    },
    "resources.consumable": {
        "type_schema_version": "schema version",
        "supplier": "supplier record: manufacturer of the DeviceModel, otherwise kept in the manifest",
        "external_identifiers": "kept in the manifest", "description": "catalog description",
    },
    "resources.hardwaredevice": {
        "type_schema_version": "schema version",
        "supplier": "supplier record: manufacturer of the DeviceModel, otherwise kept in the manifest",
        "external_identifiers": "kept in the manifest", "description": "catalog description",
        "rrid": "kept in the manifest",
    },
    "modules.consumablestock": {
        "type_schema_version": "schema version", "acquisition_date": "inventory management",
        "expiration_date": "inventory management", "status": "inventory management",
        "storage_conditions": "inventory management", "storage_location": "inventory management",
        "intended_use": "inventory management", "cost": "inventory management", "notes": "inventory notes",
        "type": "stock type", "type_json": "only batchId and titer are used for viruses",
    },
    "taxonomies.species": {"appearance": "not an NWB field", "popular_name": "the binomial name is used",
                           "description": "catalog description"},
    "taxonomies.strain": {"appearance": "not an NWB field", "popular_name": "the strain name is used",
                          "breeding": "breeding scheme of the strain", "description": "catalog description",
                          "external_identifiers": "kept in the manifest", "species": "species of the strain"},
    "personal_attributes.setup": {"image": "uploaded image", "is_public": "access setting",
                                  "setup_type": "setup type record: kept in the manifest",
                                  "specifications": "kept in the manifest"},
    "personal_attributes.behavioralassay": {"is_public": "access setting", "licenses": "regulatory approvals",
                                            "setup_type": "setup type record: kept in the manifest",
                                            "behavioral_paradigm": "paradigm record: kept in the manifest"},
    "personal_attributes.protocol": {"attachment": "uploaded file", "is_public": "access setting",
                                     "description": "kept in the manifest"},
    "personal_attributes.license": {"*": "regulatory approvals are administrative lab resources: manifest only"},
    "modules.procedureepisode": {"severity": "regulatory severity", "status": "workflow status",
                                 "recovery_outcome": "kept in the manifest", "description": "kept in the manifest",
                                 "intervention_class": "described by the procedures' types",
                                 "start_date_time": "kept in the manifest; procedures carry their own dates",
                                 "end_date_time": "kept in the manifest"},
    "stem.specimenset": {
        "storage_conditions": "storage", "storage_location": "storage", "status": "inventory status",
        "type_schema_version": "schema version", "source_specimen_set": "derivation link",
        "termination_datetime": "kept in the manifest", "extra_content_json": "kept in the manifest",
        "target_regions": "region records: acronyms give NWB locations, the links are kept in the manifest",
        "baseline_conditions": "kept in the manifest",
        "tags": "kept in the manifest",
    },
    "stem.specimen": {"storage_conditions": "storage", "storage_location": "storage", "status": "status",
                      "type_schema_version": "schema version", "source_specimen": "derivation link",
                      "termination_datetime": "kept in the manifest",
                      "type_json": "kept in the manifest", "quality": "kept in the manifest"},
    "modules.specimenprocedure": {"type_schema_version": "schema version", "target_scope": "kept in the manifest",
                                  "target_specimens": "specimen links",
                                  "target_regions": "region records: acronyms give NWB locations, the links are kept "
                                                    "in the manifest"},
    "modules.dataacquisitioninterface": {"metadata_json": "kept in the manifest",
                                         "metadata_schema_version": "schema version"},
    "modules.manipulationinterface": {"metadata_json": "kept in the manifest",
                                      "metadata_schema_version": "schema version"},
    "modules.procedureinterface": {"notes": "kept in the manifest"},
    # Catalog entries (export format 2.1)
    "dissemination.publication": {
        "title": "kept in the manifest; NWB related_publications holds the DOI",
        "authors": "kept in the manifest", "abstract": "kept in the manifest", "volume": "kept in the manifest",
        "publication_date": "kept in the manifest", "pdf_url": "kept in the manifest",
    },
    "dissemination.journal": {"*": "kept in the manifest"},
    "resources.supplier": {"description": "catalog description", "website": "kept in the manifest"},
    "taxonomies.anatomicalregion": {
        "description": "catalog description", "graph_order": "atlas ordering",
        "parent_acronym": "atlas hierarchy; kept in the manifest",
        "region_id": "atlas structure id; kept in the manifest", "is_obsolete": "catalog status",
        "replaced_by": "catalog status",
    },
    "taxonomies.anatomicalreference": {
        "*": "atlas description (code, coordinate space, orientation, units, citation); kept in the manifest",
    },
    "taxonomies.coordinatetransform": {"*": "coordinate transforms are kept in the manifest"},
    "taxonomies.behavioralcategory": {"description": "catalog description", "parent": "category hierarchy"},
    "taxonomies.behavioralparadigm": {
        "description": "catalog description", "external_identifiers": "kept in the manifest",
        "original_publication": "kept in the manifest", "reference_url": "kept in the manifest",
        "species": "species the paradigm applies to",
    },
    "taxonomies.regulatoryauthority": {"*": "authorities of licenses, which are kept in the manifest only"},
    "taxonomies.setuptype": {"category": "setup category code; the setup type name is used",
                             "description": "catalog description"},
    "users.user": {"*": "the export holds first and last names only; no other user field is ever exported"},
    "modules.moduleslogentry": {
        "*": "log entries are kept in the manifest; weights become Subject.weight",
    },
    "modules.startendmoduleslogentry": {
        "*": "log entries are kept in the manifest; weights become Subject.weight",
    },
    # Whole record types without an NWB counterpart in a metadata-only file.
    "stem.cohort": {"*": "cohorts group subjects across sessions; no NWB counterpart"},
    "stem.cohortsubject": {"*": "cohort membership order"},
    "stem.breeding": {"*": "colony management"},
    "stem.collection": {"*": "collections group sessions; no NWB counterpart"},
    "stem.collectionsession": {"*": "collection membership order"},
    "stem.sessiondatastorage": {"*": "data storage order; storages are listed in data_sources"},
    "modules.episodepersonnel": {"*": "personnel names: in procedure text, kept in the manifest"},
    "modules.procedurestage": {"*": "stage-level procedure detail; kept in the manifest"},
    "modules.procedurestagetarget": {"*": "stage targets"},
    "modules.specimenproceduretarget": {"*": "specimen procedure targets"},
    "modules.materialusagetarget": {"*": "material usage targets"},
    "modules.subjectlog": {"*": "log entries: the last weighing before the session gives Subject.weight, the rest is "
                                "kept in the manifest"},
    "modules.procedurelog": {"*": "log entries (impedances, depth adjustments): kept in the manifest"},
    "modules.specimenlog": {"*": "specimen log entries: kept in the manifest"},
    "personal_attributes.datastorage": {"*": "administrative lab resource: listed in the manifest's data_sources "
                                             "(Phase 4 input), never in the NWB file"},
    "personal_attributes.inventory": {"*": "administrative lab resource: manifest only"},
    "personal_attributes.protocolallowedsubtype": {"*": "protocol configuration"},
}


def rule_sources_by_label() -> dict[str, set[str]]:
    """label -> fields read by at least one registered rule."""
    _load_mappers()
    out: dict[str, set[str]] = {}
    for rule in RULES.values():
        for source in rule.sources:
            label, _, field_name = source.rpartition(".")
            if label.count(".") == 1:
                out.setdefault(label, set()).add(field_name)
    return out


def field_policy(label: str, field_name: str) -> str:
    """'mapped', 'structural', 'manifest_only', 'dropped' or 'unaccounted' for one exported field."""
    from ..store.inventory import DROPPED_FIELDS

    if field_name in DROPPED_FIELDS:
        return "dropped"
    if field_name in rule_sources_by_label().get(label, set()):
        return "mapped"
    if field_name in STRUCTURAL.get(label, set()):
        return "structural"
    policy = MANIFEST_ONLY.get(label, {})
    if "*" in policy or field_name in policy or field_name in _TIMESTAMPS:
        return "manifest_only"
    return "unaccounted"


def manifest_only_reason(label: str, field_name: str) -> str | None:
    policy = MANIFEST_ONLY.get(label, {})
    return policy.get(field_name) or policy.get("*") or _TIMESTAMPS.get(field_name)


def _load_mappers() -> None:
    # Importing the mapper modules registers their rules.
    from . import pipeline  # noqa: F401
