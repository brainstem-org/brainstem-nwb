"""
The conversion manifest: the versioned, machine-readable record of one export run.

It sits between BrainSTEM retrieval and NWB writing. For every session x subject unit it keeps
the BrainSTEM records the unit was built from, how each record was attributed to the unit, every
intended NWB destination with the state of its value, the exact plan the NWB writer consumes
(``NwbPlan``), references to the raw data files, and all warnings. A dry run stops after
building it, so the metadata can be inspected before any NWB file is written.

The NWB writer reads only ``NwbPlan``; it knows nothing about BrainSTEM.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["error", "warning", "info"]

# The five states of a value. Only "present" values are written to NWB; "unknown" is written only
# where NWB has a code for it (subject sex "U").
ValueState = Literal["present", "missing", "unknown", "not_applicable", "not_exported"]

UnitStatus = Literal["planned", "written", "up_to_date", "failed", "skipped"]
ExportMode = Literal["metadata-only", "with-raw-data", "partial-raw-data"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourcePointer(_Model):
    """Where a value or a problem comes from: a BrainSTEM record and, optionally, a field path in it."""

    label: str | None = None
    pk: str | None = None
    path: str | None = None


class ConversionWarning(_Model):
    code: str
    severity: Severity
    message: str
    source: SourcePointer | None = None
    nwb_path: str | None = None
    rule_id: str | None = None


# --------------------------------------------------------------------------------------------
# NWB plan: plain data consumed by brainstem_nwb.nwb.writer
# --------------------------------------------------------------------------------------------


class NWBFilePlan(_Model):
    session_description: str
    identifier: str
    session_start_time: dt.datetime
    timestamps_reference_time: dt.datetime
    file_create_date: dt.datetime | None = None
    session_id: str | None = None
    experiment_description: str | None = None
    experimenter: list[str] = Field(default_factory=list)
    lab: str | None = None
    institution: str | None = None
    keywords: list[str] = Field(default_factory=list)
    related_publications: list[str] = Field(default_factory=list)
    protocol: str | None = None
    surgery: str | None = None
    virus: str | None = None
    pharmacology: str | None = None
    stimulus_notes: str | None = None
    data_collection: str | None = None
    slices: str | None = None
    notes: str | None = None
    source_script: str | None = None
    source_script_file_name: str | None = None
    was_generated_by: list[list[str]] = Field(default_factory=list)


class SubjectPlan(_Model):
    subject_id: str
    species: str | None = None
    strain: str | None = None
    sex: str | None = None
    date_of_birth: dt.datetime | None = None
    age: str | None = None
    age__reference: str | None = None
    genotype: str | None = None
    description: str | None = None
    weight: str | None = None


class DeviceModelPlan(_Model):
    name: str
    manufacturer: str
    model_number: str | None = None
    description: str | None = None


class DevicePlan(_Model):
    name: str
    description: str | None = None
    serial_number: str | None = None
    model: str | None = None  # name of a DeviceModelPlan
    brainstem_label: str
    brainstem_id: str


class ElectrodeGroupPlan(_Model):
    name: str
    description: str
    location: str
    device: str  # name of a DevicePlan
    brainstem_interface_id: str
    channels: list[int] | None = None


class OptogeneticSitePlan(_Model):
    name: str
    description: str
    device: str
    excitation_lambda: float  # nm
    location: str
    brainstem_interface_id: str


class EpochColumnPlan(_Model):
    name: str
    description: str


class EpochRowPlan(_Model):
    start_time: float
    stop_time: float
    tags: list[str]
    values: dict[str, str]


class EpochsPlan(_Model):
    columns: list[EpochColumnPlan] = Field(default_factory=list)
    rows: list[EpochRowPlan] = Field(default_factory=list)


class ExtensionColumnPlan(_Model):
    name: str
    description: str
    # Name of the BrainstemTable this column links to, or "/intervals/epochs"; None for a text column.
    link_table: str | None = None
    # The BrainSTEM field the column holds (None for derived columns such as nwb_device)
    field: str | None = None


class ExtensionTablePlan(_Model):
    """One ndx-brainstem BrainstemTable: a row per BrainSTEM record, a column per field."""

    name: str
    description: str
    brainstem_models: list[str]
    columns: list[ExtensionColumnPlan] = Field(default_factory=list)
    rows: list[dict[str, str | list[int]]] = Field(default_factory=list)


class BrainstemExtensionPlan(_Model):
    """The ndx-brainstem content of a file (``--extension brainstem``)."""

    namespace_version: str = "0.2.0"
    attributes: dict[str, str | list[str]] = Field(default_factory=dict)
    tables: list[ExtensionTablePlan] = Field(default_factory=list)
    schemas: list[dict[str, str]] = Field(default_factory=list)
    # BrainSTEM's terms for the embedded schemas, written with them (the schemas are not open source)
    schemas_terms: str | None = None


class SpacePlan(_Model):
    name: str
    space_name: str
    origin: str
    units: str
    orientation: str
    predefined: Literal["AllenCCFv3"] | None = None


class LocalizationRowPlan(_Model):
    entity_row: int
    x: float
    y: float
    z: float
    brain_region: str = ""


class LocalizationTablePlan(_Model):
    """One ndx-anatomical-localization AnatomicalCoordinatesTable over rows of an ndx-brainstem table."""

    name: str
    description: str
    method: str
    space: str
    entity_table: str
    rows: list[LocalizationRowPlan] = Field(default_factory=list)


class LocalizationPlan(_Model):
    spaces: list[SpacePlan] = Field(default_factory=list)
    tables: list[LocalizationTablePlan] = Field(default_factory=list)


class HerdRefPlan(_Model):
    """One HERD reference: an ontology term for a value of a core NWB object."""

    target: Literal["subject", "electrode_group", "ogen_site", "device_model"]
    target_name: str | None = None
    attribute: str
    key: str
    entity_id: str
    entity_uri: str


class NwbPlan(_Model):
    nwbfile: NWBFilePlan
    subject: SubjectPlan | None = None
    device_models: list[DeviceModelPlan] = Field(default_factory=list)
    devices: list[DevicePlan] = Field(default_factory=list)
    electrode_groups: list[ElectrodeGroupPlan] = Field(default_factory=list)
    optogenetic_sites: list[OptogeneticSitePlan] = Field(default_factory=list)
    epochs: EpochsPlan = Field(default_factory=EpochsPlan)
    brainstem: BrainstemExtensionPlan | None = None
    localization: LocalizationPlan | None = None
    herd: list[HerdRefPlan] = Field(default_factory=list)
    # Appended to NWBFile.notes as a fenced JSON block by the writer. Kept apart from the notes
    # text so the content digest (and so the NWB identifier) ignores when the export was made.
    provenance: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------------------------


class RecordRef(_Model):
    id: str
    name: str | None = None


class SubjectRef(_Model):
    id: str
    name: str
    label: str


class UnitOutput(_Model):
    relative_path: str
    herd_relative_path: str | None = None
    nwb_identifier: str | None = None
    sha256: str | None = None


class Attribution(_Model):
    """Why a BrainSTEM record is part of a unit, or why it was left out."""

    label: str
    pk: str
    decision: Literal["included", "shared", "excluded"]
    reason: str


class FieldMapping(_Model):
    """One intended NWB destination and the state of the value that goes there."""

    rule_id: str
    nwb_path: str
    state: ValueState
    value: Any = None
    sources: list[SourcePointer] = Field(default_factory=list)
    note: str | None = None


class RecordEntry(_Model):
    """A BrainSTEM record as exported (minus private bookkeeping fields) and its role in the unit."""

    label: str
    pk: str
    roles: list[str]
    fields: dict[str, Any]
    unmapped_fields: list[str] = Field(default_factory=list)


class RawConversion(_Model):
    status: Literal["not_attempted", "converted", "failed", "not_supported"] = "not_attempted"
    converter: str | None = None
    message: str | None = None


class DataSource(_Model):
    """Where a DataAcquisition's raw data lives, as far as BrainSTEM records it (input to Phase 4)."""

    dataacquisition_id: str
    type: str
    file_name: str | None = None
    format: str | None = None
    session_storage_name: str | None = None
    subject_storage_name: str | None = None
    datastorages: list[RecordRef] = Field(default_factory=list)
    repository_links: list[dict[str, str]] = Field(default_factory=list)
    raw_conversion: RawConversion = Field(default_factory=RawConversion)


class UnitFailure(_Model):
    code: str
    message: str
    exception_type: str | None = None


class Unit(_Model):
    unit_id: str
    status: UnitStatus = "planned"
    session: RecordRef
    subject: SubjectRef | None = None
    specimen_sets: list[RecordRef] = Field(default_factory=list)
    output: UnitOutput
    attribution: list[Attribution] = Field(default_factory=list)
    mappings: list[FieldMapping] = Field(default_factory=list)
    records: list[RecordEntry] = Field(default_factory=list)
    nwb: NwbPlan | None = None  # None only when mapping the unit failed (see error)
    data_sources: list[DataSource] = Field(default_factory=list)
    warnings: list[ConversionWarning] = Field(default_factory=list)
    error: UnitFailure | None = None


class UnitErrorEntry(_Model):
    """A session (or one of its subjects) that produced no unit."""

    session_id: str
    session_name: str | None = None
    subject_id: str | None = None
    code: str
    message: str


# --------------------------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------------------------


class ExporterInfo(_Model):
    name: str = "brainstem-nwb"
    version: str
    mapping_version: str
    pynwb: str | None = None
    hdmf: str | None = None
    nwb_schema: str | None = None


class RunInfo(_Model):
    created_at: dt.datetime
    reproducible: bool
    dry_run: bool
    options: dict[str, Any] = Field(default_factory=dict)


class SourceInfo(_Model):
    kind: Literal["file", "api", "dict"]
    name: str | None = None
    host: str | None = None
    sha256: str
    format_version: str
    exported_at: str | None = None
    scope: Literal["project", "session"] = "project"
    project_id: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    record_count: int | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    lab_resources: str | None = None
    restricted: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    unmapped_labels: list[str] = Field(default_factory=list)


class ExternalRefCount(_Model):
    total: int
    resolved: int


class ProjectInfo(_Model):
    id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    publication_ids: list[str] = Field(default_factory=list)
    repository_links: list[dict[str, str]] = Field(default_factory=list)
    custom_fields: list[dict[str, str]] = Field(default_factory=list)


class DataModelInfo(_Model):
    """The BrainSTEM data model the export was read with: read from the server at run time, never bundled."""

    server: str
    data_model: str
    export_format_version: str
    server_commit: str | None = None
    sha256: str
    license_url: str | None = None


class SchemaInfo(_Model):
    """The BrainSTEM JSON schemas the records use and where the embedded copies came from."""

    used: int
    embedded: int
    origin: Literal["export", "fetched", "none"]
    base_url: str | None = None
    missing: list[str] = Field(default_factory=list)


class Coverage(_Model):
    records_total: int
    records_in_units: int
    records_unreached: dict[str, list[str]] = Field(default_factory=dict)


class Summary(_Model):
    sessions: int = 0
    units: int = 0
    written: int = 0
    up_to_date: int = 0
    planned: int = 0
    failed: int = 0
    unit_errors: int = 0
    warnings_by_severity: dict[str, int] = Field(default_factory=dict)


class Manifest(_Model):
    manifest_schema_version: str
    exporter: ExporterInfo
    export_mode: ExportMode = "metadata-only"
    run: RunInfo
    source: SourceInfo
    data_model: DataModelInfo | None = None
    projects: list[ProjectInfo] = Field(default_factory=list)
    external_refs: dict[str, ExternalRefCount] = Field(default_factory=dict)
    units: list[Unit] = Field(default_factory=list)
    unit_errors: list[UnitErrorEntry] = Field(default_factory=list)
    coverage: Coverage | None = None
    schemas: SchemaInfo | None = None
    warnings: list[ConversionWarning] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
