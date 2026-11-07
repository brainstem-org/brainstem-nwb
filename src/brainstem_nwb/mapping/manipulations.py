"""Manipulations of the session as NWB stimulus notes and pharmacology text."""

from __future__ import annotations

from ..normalize.units import interface_procedures, is_performed
from ..store.graph import Record
from . import describe
from .context import MapContext
from .registry import MappingRule, rules

PHARMACOLOGICAL_MANIPULATIONS = {
    "PharmacologicalInjection",
    "PharmacologicalInhalation",
    "PharmacologicalSuperfusion",
    "Microperfusion",
    "LiquidPerturbation",
}


def manipulation_line(ctx: MapContext, manipulation: Record) -> str:
    store = ctx.store
    code = str(manipulation.get("type") or "Manipulation")
    label = ctx.inventory.type_label("Manipulation", code) or code
    parts = []
    details = describe.details_text(manipulation.get("type_json"))
    if details:
        parts.append(details)
    interfaces = describe.interface_names(store, manipulation)
    if interfaces:
        parts.append(f"interfaces {interfaces}")
    equipment = describe.equipment_names(store, manipulation)
    if equipment:
        parts.append(f"equipment {equipment}")
    procedures = [str(p.get("type")) for p in interface_procedures(store, manipulation) if is_performed(p)]
    if procedures:
        parts.append(f"procedures {', '.join(procedures)}")
    notes = describe.notes_text(manipulation)
    if notes:
        parts.append(f"notes: {notes}")
    body = "; ".join(parts)
    return f"{label} {describe.ref(manipulation)}" + (f": {body}" if body else "")


@rules(
    MappingRule(
        id="manipulations.stimulus_notes",
        destination="NWBFile.stimulus_notes",
        sources=("modules.manipulation.type", "modules.manipulation.type_json", "modules.manipulation.notes",
                 "modules.experimentalinterface.name", "modules.equipment.name"),
        transform="one line per non-pharmacological manipulation (optogenetic, electrical, sensory, ...): type, "
                  "BrainSTEM id, each stimulation protocol's parameters as stored, interfaces, equipment, "
                  "procedures, notes. No stimulus time series is written: BrainSTEM records no stimulus times",
        condition="the session has such manipulations",
    ),
    MappingRule(
        id="manipulations.pharmacology",
        destination="NWBFile.pharmacology",
        sources=("modules.manipulation.type", "modules.manipulation.type_json", "modules.manipulation.notes"),
        transform="pharmacological manipulations (injection, inhalation, superfusion, microperfusion, liquid "
                  "perturbation), appended after the pharmacological procedures",
        condition="the session has such manipulations",
    ),
)
def map_manipulations(ctx: MapContext, procedure_lines: dict[str, list[str]]) -> None:
    stimulus: list[str] = []
    pharmacology = list(procedure_lines.get("pharmacology", []))
    pharmacology_sources = list(ctx.pharmacology_sources)
    stimulus_sources = []
    for manipulation in sorted(ctx.unit.role("manipulation"), key=lambda m: (m.get("order") or 0, m.pk)):
        line = manipulation_line(ctx, manipulation)
        if manipulation.get("type") in PHARMACOLOGICAL_MANIPULATIONS:
            pharmacology.append(line)
            pharmacology_sources.append(manipulation)
        else:
            stimulus.append(line)
            stimulus_sources.append(manipulation)
    if stimulus:
        ctx.nwbfile["stimulus_notes"] = "\n".join(stimulus)
        ctx.map("manipulations.stimulus_notes", "NWBFile.stimulus_notes", "present", ctx.nwbfile["stimulus_notes"],
                stimulus_sources)
    else:
        ctx.map("manipulations.stimulus_notes", "NWBFile.stimulus_notes", "missing")
    if pharmacology:
        ctx.nwbfile["pharmacology"] = "\n".join(pharmacology)
        ctx.map("procedures.pharmacology", "NWBFile.pharmacology", "present", ctx.nwbfile["pharmacology"],
                pharmacology_sources)
    else:
        ctx.map("procedures.pharmacology", "NWBFile.pharmacology", "missing")
