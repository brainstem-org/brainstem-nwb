"""
Map one export unit (session x subject) to a manifest ``Unit`` holding its ``NwbPlan``.

The mappers run in a fixed order; devices come before electrode groups and optogenetic sites,
which refer to them by name.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from .._version import MANIFEST_SCHEMA_VERSION, MAPPING_VERSION, PACKAGE_URL, __version__
from ..config import ExportOptions
from ..manifest.io import digest
from ..manifest.models import (
    NWBFilePlan,
    NwbPlan,
    RecordEntry,
    RecordRef,
    SubjectRef,
    Unit,
    UnitOutput,
)
from ..normalize.units import ExportUnit, subject_label
from ..retrieval.loader import ProjectExport
from ..store.graph import RecordStore
from ..store.inventory import DROPPED_FIELDS
from . import (
    acquisitions,
    devices,
    epochs,
    extension,
    herd,
    localization,
    manipulations,
    notes,
    procedures,
    session,
    subject,
)
from .context import MapContext
from .registry import field_policy

# Namespace of the deterministic NWB identifiers written by brainstem-nwb.
IDENTIFIER_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, PACKAGE_URL)

_BOOKKEEPING = {"created_at", "updated_at", "is_public", "order", "is_active", "is_obsolete", "graph_order"}

_NOTES_ORDER = ["Behaviors", "Other procedures", "Session custom fields", "Repository links",
                "Kept in the conversion manifest only"]


def map_unit(
    store: RecordStore,
    unit: ExportUnit,
    options: ExportOptions,
    export: ProjectExport,
    *,
    file_create_date: dt.datetime | None = None,
) -> Unit:
    ctx = MapContext(store=store, unit=unit, options=options, export=export)
    session.map_session(ctx)
    session.map_project(ctx)
    session.map_people(ctx)
    session.map_protocols(ctx)
    subject.map_subject(ctx)
    lines = procedures.map_procedures(ctx)
    manipulations.map_manipulations(ctx, lines)
    data_sources = acquisitions.map_acquisitions(ctx)
    devices.map_devices(ctx)
    devices.map_electrode_groups(ctx)
    devices.map_optogenetic_sites(ctx)
    epochs.map_epochs(ctx)
    notes.map_notes(ctx)

    records = _record_entries(ctx)
    unmapped = sorted({f"{entry.label}.{name}" for entry in records for name in entry.unmapped_fields})
    if unmapped:
        ctx.add_notes("Kept in the conversion manifest only",
                      [f"BrainSTEM fields without an NWB destination: {', '.join(unmapped)}"])
        ctx.warn("UNMAPPED_FIELDS", f"{len(unmapped)} BrainSTEM field(s) with values are kept in the manifest only")

    ctx.nwbfile["notes"] = _notes_text(ctx)
    ctx.nwbfile["source_script"] = f"brainstem-nwb {__version__} ({PACKAGE_URL})"
    ctx.nwbfile["source_script_file_name"] = "brainstem_nwb"
    ctx.nwbfile["was_generated_by"] = [["brainstem-nwb", __version__]]

    wanted = set(options.extensions)
    brainstem = extension.map_extension(ctx) if wanted & {"brainstem", "localization"} else None
    # Coordinates go to both: as recorded in the ndx-brainstem rows, and as points in a defined space in
    # ndx-anatomical-localization tables linked to those rows (ndx-brainstem includes its namespace).
    located = localization.map_localization(ctx, brainstem) if brainstem else None

    plan = NwbPlan(
        brainstem=brainstem,
        localization=located if located and located.tables else None,
        herd=herd.map_herd(ctx) if options.herd else [],
        nwbfile=NWBFilePlan(identifier="", **ctx.nwbfile),
        subject=ctx.subject,
        device_models=ctx.device_models,
        devices=ctx.devices,
        electrode_groups=ctx.electrode_groups,
        optogenetic_sites=ctx.optogenetic_sites,
        epochs=ctx.epochs,
    )
    content_digest = digest(plan.model_dump(mode="json", exclude={"provenance": True,
                                                                  "nwbfile": {"identifier", "file_create_date"},
                                                                  "brainstem": {"attributes"}}))
    identifier = str(uuid.uuid5(
        IDENTIFIER_NAMESPACE,
        f"{unit.session.pk}|{unit.subject.pk if unit.subject else ''}|{MAPPING_VERSION}|{content_digest}",
    ))
    plan.nwbfile.identifier = identifier
    plan.nwbfile.file_create_date = file_create_date
    plan.provenance = _provenance(ctx, export, identifier, content_digest)
    if plan.brainstem is not None:
        plan.brainstem.attributes = _extension_attributes(plan.provenance)

    subject_ref = None
    if unit.subject is not None:
        subject_ref = SubjectRef(id=unit.subject.pk, name=str(unit.subject.get("name")),
                                 label=subject_label(unit.subject, options.subject.label_field))
    return Unit(
        unit_id=unit.unit_id,
        session=RecordRef(id=unit.session.pk, name=unit.session.get("name")),
        subject=subject_ref,
        specimen_sets=[RecordRef(id=s.pk, name=s.get("name")) for s in unit.specimen_sets],
        output=UnitOutput(relative_path=unit.relative_path, nwb_identifier=identifier,
                          herd_relative_path=herd_path(unit.relative_path) if plan.herd else None),
        attribution=unit.attribution,
        mappings=ctx.mappings,
        records=records,
        nwb=plan,
        data_sources=data_sources,
        warnings=[*unit.warnings, *ctx.warnings],
    )


def _record_entries(ctx: MapContext) -> list[RecordEntry]:
    inventory = ctx.inventory
    entries = []
    for (label, _pk), (record, roles) in sorted(ctx.unit.all_records().items()):
        known = inventory.fields(label)
        fields: dict[str, Any] = {}
        unmapped: list[str] = []
        for name, value in record.fields.items():
            if name in DROPPED_FIELDS:
                continue
            fields[name] = value
            if name not in known and name in ("created_at", "updated_at"):
                continue  # record timestamps; the reference documents leave them out of some link tables
            if name not in known:
                ctx.warn("UNKNOWN_FIELD", f"{label}.{name} is not a field this release knows; kept in the manifest",
                         path=f"{label}/fields/{name}", once=True)
                if _has_value(value):
                    unmapped.append(name)
                continue
            # Links (kept in the manifest as ids) and bookkeeping are not reported as unmapped data.
            if known[name].get("kind") in ("fk", "m2m", "tags") or name in _BOOKKEEPING \
                    or name.endswith("_schema_version"):
                continue
            if _has_value(value) and field_policy(label, name) in ("manifest_only", "unaccounted"):
                unmapped.append(name)
        entries.append(RecordEntry(label=label, pk=record.pk, roles=sorted(roles), fields=fields,
                                   unmapped_fields=sorted(unmapped)))
    return entries


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _notes_text(ctx: MapContext) -> str:
    sections = sorted(ctx.notes_sections, key=lambda s: _NOTES_ORDER.index(s[0]) if s[0] in _NOTES_ORDER else 99)
    parts = [notes.METADATA_ONLY_BANNER]
    for heading, body in sections:
        parts.append(f"{heading}:\n{body}")
    return "\n\n".join(parts)


def herd_path(relative_path: str) -> str:
    """``sub-X/sub-X_ses-Y.nwb`` -> ``sub-X/sub-X_ses-Y.herd.zip``."""
    return relative_path[:-4] + ".herd.zip" if relative_path.endswith(".nwb") else relative_path + ".herd.zip"


def _extension_attributes(provenance: dict[str, Any]) -> dict[str, str | list[str]]:
    """BrainstemMetadata attributes, from the same values as the provenance block."""
    attributes: dict[str, str | list[str]] = {
        "export_format_version": str(provenance["source_format_version"]),
        "export_scope": str(provenance["export_scope"]),
        "exported_at": str(provenance.get("exported_at") or ""),
        "source_sha256": str(provenance["source_sha256"]),
        "project_ids": [str(p) for p in provenance["project_ids"]],
        "session_id": str(provenance["session_id"]),
        "unit_id": str(provenance["unit_id"]),
        "exporter": "brainstem-nwb",
        "exporter_version": str(provenance["exporter_version"]),
        "mapping_version": str(provenance["mapping_version"]),
        "content_sha256": str(provenance["content_sha256"]),
    }
    if provenance.get("subject_id"):
        attributes["subject_id"] = str(provenance["subject_id"])
    return attributes


def _provenance(ctx: MapContext, export: ProjectExport, identifier: str, content_digest: str) -> dict[str, Any]:
    unit = ctx.unit
    return {
        "exporter": "brainstem-nwb",
        "exporter_version": __version__,
        "mapping_version": MAPPING_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "export_mode": "metadata-only",
        "source": "BrainSTEM project export",
        "source_format_version": export.format_version,
        "source_sha256": export.sha256,
        "exported_at": export.exported_at,
        "project_ids": [p.pk for p in unit.projects] or export.project_ids,
        "export_scope": export.scope,
        "session_id": unit.session.pk,
        "subject_id": unit.subject.pk if unit.subject else None,
        "specimen_set_ids": [s.pk for s in unit.specimen_sets],
        "unit_id": unit.unit_id,
        "nwb_identifier": identifier,
        "content_sha256": content_digest,
    }
