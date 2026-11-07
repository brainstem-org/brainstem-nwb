"""
Procedures of the subject up to the session, as NWB surgery, virus and pharmacology text.

Procedures are classified by the group of their type in the BrainSTEM procedure vocabulary.
Each becomes one line, in date order:
``<date> — <type> [brainstem:procedure/<id>]: targets ...; coordinates ...; <details>; ...``.
The full records stay in the manifest.
"""

from __future__ import annotations

from ..normalize.text import humanize_code
from ..store.graph import Record
from . import describe
from .context import MapContext
from .registry import MappingRule, rules

SURGERY_GROUPS = {
    "Surgical Procedures",
    "Implant Procedures",
    "Brain and Tissue Procedures",
    "Sample Collection Procedures",
    "Endpoint Procedures (Euthanasia)",
}
PHARMACOLOGY_GROUPS = {"Anesthesia, Drug and Fluid Administration"}
VIRUS_TYPES = {"VirusInjection"}
PHARMACOLOGY_TYPES = {"Injection"}

_PROCEDURE_SOURCES = (
    "modules.procedure.type", "modules.procedure.date_time", "modules.procedure.type_json",
    "modules.procedure.target_regions", "modules.procedure.coordinates", "modules.procedure.coordinates_json",
    "modules.procedure.notes", "modules.procedure.performed_by", "modules.procedureepisode.name",
    "modules.episodepersonnel.person", "modules.episodepersonnel.role", "users.user.first_name",
    "users.user.last_name", "modules.procedureinterface.relationship",
    "modules.materialusage.type", "modules.materialusage.manual_name", "modules.materialusage.details_json",
    "modules.materialusage.notes", "resources.consumable.name", "resources.consumable.type",
    "resources.consumable.type_json", "resources.consumable.rrid", "personal_attributes.protocol.name",
)


def classify(ctx: MapContext, procedure: Record) -> str:
    """'virus', 'pharmacology', 'surgery' or 'other' (type not in the vocabulary)."""
    code = procedure.get("type")
    if code in VIRUS_TYPES:
        return "virus"
    if code in PHARMACOLOGY_TYPES:
        return "pharmacology"
    group = ctx.inventory.type_group("Procedure", code)
    if group in PHARMACOLOGY_GROUPS:
        return "pharmacology"
    if group in SURGERY_GROUPS:
        return "surgery"
    return "other"


def procedure_line(ctx: MapContext, procedure: Record) -> str:
    store = ctx.store
    code = str(procedure.get("type") or "Procedure")
    label = ctx.inventory.type_label("Procedure", code) or code
    head = " — ".join(part for part in (describe.when(procedure.get("date_time")), label) if part)
    parts = []
    targets = describe.regions_text(store, procedure)
    if targets:
        parts.append(f"targets {targets}")
    coordinates = describe.coordinates_text(procedure.get("coordinates"), procedure.get("coordinates_json"))
    if coordinates:
        parts.append(f"coordinates {coordinates}")
    details = describe.details_text(procedure.get("type_json"))
    if details:
        parts.append(details)
    interfaces = []
    for link in store.referrers(procedure, "modules.procedureinterface", "procedure"):
        interface = store.fk_record(link, "interface")
        if interface is not None:
            interfaces.append(f"{interface.get('name')} ({link.get('relationship') or 'related'})")
    if interfaces:
        parts.append(f"interfaces {', '.join(interfaces)}")
    materials = [describe.material_text(store, usage)
                 for usage in sorted(store.referrers(procedure, "modules.materialusage", "procedure"),
                                     key=lambda u: (u.get("order") or 0, u.pk))]
    if materials:
        parts.append(f"materials: {' | '.join(materials)}")
    performer = describe.person_name(store, procedure, "performed_by")
    if performer:
        parts.append(f"performed by {performer}")
    episode = store.fk_record(procedure, "procedure_episode")
    if episode is not None and episode.get("name"):
        personnel = [f"{humanize_code(str(p.get('role') or 'personnel'))} {describe.person_name(store, p, 'person')}"
                     for p in store.referrers(episode, "modules.episodepersonnel", "episode")]
        parts.append(f"episode {episode.get('name')}" + (f" ({', '.join(personnel)})" if personnel else ""))
    protocol = store.fk_record(procedure, "protocol")
    if protocol is not None:
        parts.append(f"protocol {protocol.get('name')}")
    notes = describe.notes_text(procedure)
    if notes:
        parts.append(f"notes: {notes}")
    body = "; ".join(parts)
    return f"{head} {describe.ref(procedure)}" + (f": {body}" if body else "")


def _sorted(procedures: list[Record]) -> list[Record]:
    return sorted(procedures, key=lambda p: (str(p.get("date_time") or "9999"), p.pk))


@rules(
    MappingRule(
        id="procedures.surgery",
        destination="NWBFile.surgery",
        sources=_PROCEDURE_SOURCES,
        transform="one line per procedure of type group Surgical, Implant, Brain and Tissue, Sample Collection or "
                  "Endpoint, performed before the session: date, type, BrainSTEM id, target regions (acronym, "
                  "name, atlas), coordinates (as stored, with units), details, interfaces, materials (with "
                  "supplier and RRID), who performed it, episode and personnel, protocol, notes",
        condition="the subject has such procedures before the session start",
    ),
    MappingRule(
        id="procedures.virus",
        destination="NWBFile.virus",
        sources=(*_PROCEDURE_SOURCES, "modules.consumablestock.type_json"),
        transform="one line per VirusInjection: injection details (volume, rate, route, ...), the ViralComponent "
                  "material with its construct (virus type, capsid, promoter, gene, reporter), stock batch and "
                  "titer, applied volume, titer and dilution, targets and coordinates",
        condition="the subject has virus injections before the session start",
        missing="a missing construct is written as 'material not recorded'",
    ),
    MappingRule(
        id="procedures.pharmacology",
        destination="NWBFile.pharmacology",
        sources=_PROCEDURE_SOURCES,
        transform="one line per anesthesia, analgesic, drug, fluid or Injection procedure before the session, with "
                  "agents and doses as stored; pharmacological manipulations of the session are appended",
        condition="such procedures or manipulations exist",
    ),
    MappingRule(
        id="procedures.other",
        destination="NWBFile.notes (section 'Other procedures')",
        sources=("modules.procedure.type",),
        transform="procedures whose type is not in this release's vocabulary, described as above",
        condition="unknown procedure types (PROCEDURE_TYPE_UNCLASSIFIED)",
    ),
)
def map_procedures(ctx: MapContext) -> dict[str, list[str]]:
    """Return the procedure lines per NWB field; manipulations add to 'pharmacology' later."""
    lines: dict[str, list[str]] = {"surgery": [], "virus": [], "pharmacology": [], "other": []}
    sources: dict[str, list[Record]] = {key: [] for key in lines}
    for procedure in _sorted(ctx.unit.role("procedure")):
        kind = classify(ctx, procedure)
        if kind == "other":
            ctx.warn("PROCEDURE_TYPE_UNCLASSIFIED",
                     f"procedure type '{procedure.get('type')}' is not in this release's vocabulary",
                     record=procedure, rule_id="procedures.other")
        lines[kind].append(procedure_line(ctx, procedure))
        sources[kind].append(procedure)
    unresolved = sum(1 for p in ctx.unit.role("procedure") for link in ctx.store.m2m(p, "target_regions")
                     if not link.ok)
    if unresolved:
        ctx.warn("REGION_NOT_RESOLVED", record=None, rule_id="procedures.surgery", once=True)
    for kind in ("surgery", "virus"):
        if lines[kind]:
            ctx.nwbfile[kind] = "\n".join(lines[kind])
            ctx.map(f"procedures.{kind}", f"NWBFile.{kind}", "present", ctx.nwbfile[kind], sources[kind])
        else:
            ctx.map(f"procedures.{kind}", f"NWBFile.{kind}", "missing")
    if lines["other"]:
        ctx.add_notes("Other procedures", lines["other"])
        ctx.map("procedures.other", "NWBFile.notes", "present", "\n".join(lines["other"]), sources["other"])
    # Pharmacology is completed (and recorded) together with the pharmacological manipulations.
    ctx.pharmacology_sources = sources["pharmacology"]
    return lines
