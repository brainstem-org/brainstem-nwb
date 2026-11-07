"""Data acquisitions: NWB data_collection text and the manifest's raw-data references."""

from __future__ import annotations

from ..manifest.models import DataSource, RecordRef
from ..normalize.kv import repository_links
from ..store.graph import Record
from . import describe
from .context import MapContext
from .registry import MappingRule, rules

IMAGING_TYPES = {
    "TwoPhotonMicroscopy", "ThreePhotonMicroscopy", "SinglePhotonMicroscopy", "ConfocalMicroscopy",
    "LightFieldMicroscopy", "Miniscope", "FiberPhotometry",
}
ICEPHYS_TYPES = {"IntracellularEphys"}


def acquisition_line(ctx: MapContext, acquisition: Record) -> str:
    store = ctx.store
    code = str(acquisition.get("type") or "DataAcquisition")
    label = ctx.inventory.type_label("DataAcquisition", code) or code
    parts = []
    details = describe.details_text(acquisition.get("type_json"))
    if details:
        parts.append(details)
    interfaces = describe.interface_names(store, acquisition)
    if interfaces:
        parts.append(f"interfaces {interfaces}")
    equipment = describe.equipment_names(store, acquisition)
    if equipment:
        parts.append(f"equipment {equipment}")
    notes = describe.notes_text(acquisition)
    if notes:
        parts.append(f"notes: {notes}")
    body = "; ".join(parts)
    return f"{label} {describe.ref(acquisition)}" + (f": {body}" if body else "")


@rules(
    MappingRule(
        id="acquisitions.data_collection",
        destination="NWBFile.data_collection",
        sources=("modules.dataacquisition.type", "modules.dataacquisition.type_json",
                 "modules.dataacquisition.notes", "modules.experimentalinterface.name", "modules.equipment.name"),
        transform="one line per acquisition, in acquisition order: type, BrainSTEM id, details as stored "
                  "(file name, format, sampling rate with unit, channel count, ...; long channel lists are "
                  "summarized), interfaces, equipment, notes. Measured data is not written in metadata-only mode",
        condition="the session has acquisitions included for the subject",
    ),
    MappingRule(
        id="acquisitions.data_sources",
        destination="manifest data_sources (input to raw-data conversion)",
        sources=("modules.dataacquisition.type_json", "stem.session.repository_links_json",
                 "stem.session.name_used_in_storage", "stem.subject.name_used_in_storage",
                 "personal_attributes.datastorage.name"),
        transform="file name and format from the acquisition details, the session's data storages in order, "
                  "storage names of session and subject, and repository links",
        section="Manifest",
    ),
)
def map_acquisitions(ctx: MapContext) -> list[DataSource]:
    acquisitions = sorted(ctx.unit.role("dataacquisition"), key=lambda r: (r.get("order") or 0, r.pk))
    lines = [acquisition_line(ctx, acquisition) for acquisition in acquisitions]
    if lines:
        ctx.nwbfile["data_collection"] = "\n".join(lines)
        ctx.map("acquisitions.data_collection", "NWBFile.data_collection", "present", ctx.nwbfile["data_collection"],
                acquisitions)
    else:
        ctx.map("acquisitions.data_collection", "NWBFile.data_collection", "missing")

    for acquisition in acquisitions:
        if acquisition.get("type") in IMAGING_TYPES:
            ctx.warn("IMAGING_PLANE_NOT_CREATED", record=acquisition, rule_id="acquisitions.data_collection")
        if acquisition.get("type") in ICEPHYS_TYPES:
            ctx.warn("ICEPHYS_NOT_MAPPED", record=acquisition, rule_id="acquisitions.data_collection")

    session = ctx.unit.session
    order = {link.get("datastorage"): link.get("order") or 0 for link in ctx.unit.role("session_datastorage")}
    storages = sorted(ctx.unit.role("datastorage"), key=lambda s: (order.get(s.pk, 0), s.pk))
    links = [{"repository": repo, "url": url} for repo, url in repository_links(session.get("repository_links_json"))]
    subject = ctx.unit.subject
    sources = []
    for acquisition in acquisitions:
        details = acquisition.get("type_json") if isinstance(acquisition.get("type_json"), dict) else {}
        sources.append(DataSource(
            dataacquisition_id=acquisition.pk,
            type=str(acquisition.get("type") or ""),
            file_name=str(details["fileName"]) if details.get("fileName") else None,
            format=str(details["format"]) if details.get("format") else None,
            session_storage_name=session.get("name_used_in_storage") or None,
            subject_storage_name=(subject.get("name_used_in_storage") or None) if subject else None,
            datastorages=[RecordRef(id=s.pk, name=s.get("name")) for s in storages],
            repository_links=links,
        ))
    ctx.map("acquisitions.data_sources", "manifest.data_sources", "present" if sources else "missing",
            len(sources) if sources else None, acquisitions)
    return sources
