"""
Ontology terms for core NWB values, as HERD (HDMF External Resources Data) references (``--herd``).

pynwb writes HERD to a zip file next to the NWB file (``<file>.herd.zip``), not inside it. The same
identifiers are inside the file in the ndx-brainstem tables (species NCBI ids, RRIDs, atlas region ids).

- ``Subject.species``: NCBI Taxonomy, from the species' NCBI identifier or RRID;
- ``Subject.strain``: the strain's RRID;
- ``ElectrodeGroup.location`` and ``OptogeneticStimulusSite.location``: each region acronym, resolved
  as BrainSTEM resolves region terms: Allen (AIA) by structure id, MA and UBERON by the CURIE stored
  as the acronym;
- ``DeviceModel.model_number``: the hardware device's or design's RRID (when it has a product id).
"""

from __future__ import annotations

from typing import Literal

from ..manifest.models import HerdRefPlan
from ..normalize.identifiers import ncbi_taxon_id, normalize_rrid
from ..normalize.units import is_performed
from ..store.graph import Record, RecordStore
from . import describe
from .context import MapContext
from .registry import MappingRule, rules


def region_term(store: RecordStore, region: Record) -> tuple[str, str] | None:
    """(entity id, URI) of a BrainSTEM region, as the server's AnatomicalRegion.ontology_url resolves it."""
    atlas = store.fk_record(region, "reference")
    code = atlas.get("region_atlas_code") if atlas is not None else None
    acronym = str(region.get("acronym") or "")
    if code == "AIA" and region.get("region_id") not in (None, ""):
        structure = str(region.get("region_id"))
        return f"Allen:{structure}", f"https://api.brain-map.org/api/v2/data/Structure/{structure}"
    if code in ("MA", "UBERON") and ":" in acronym:
        return acronym, f"http://purl.obolibrary.org/obo/{acronym.replace(':', '_', 1)}"
    return None


def rrid_uri(rrid: str) -> str:
    return f"https://scicrunch.org/resolver/{rrid}"


@rules(
    MappingRule(
        id="herd.terms",
        destination="HERD sidecar (<file>.herd.zip): Subject.species, Subject.strain, ElectrodeGroup.location, "
                    "OptogeneticStimulusSite.location, DeviceModel.model_number",
        section="Extension",
        sources=("taxonomies.species.external_identifiers", "taxonomies.species.rrid", "taxonomies.strain.rrid",
                 "taxonomies.anatomicalregion.region_id", "taxonomies.anatomicalregion.acronym",
                 "taxonomies.anatomicalreference.region_atlas_code", "resources.hardwaredevice.rrid",
                 "resources.consumable.rrid"),
        transform="species -> NCBITaxon IRI; strain and device models -> RRID resolver URL; region acronyms -> "
                  "Allen structure (AIA) or OBO PURL (MA, UBERON), as BrainSTEM resolves them",
        condition="--herd; the identifier is recorded",
        missing="no reference for that value",
    ),
)
def map_herd(ctx: MapContext) -> list[HerdRefPlan]:
    store = ctx.store
    refs: list[HerdRefPlan] = []
    subject = ctx.unit.subject
    if subject is not None and ctx.subject is not None:
        species = store.fk_record(subject, "species")
        taxon = ncbi_taxon_id(dict(species.fields)) if species is not None else None
        if taxon and ctx.subject.species:
            refs.append(HerdRefPlan(target="subject", attribute="species", key=ctx.subject.species,
                                    entity_id=f"NCBITaxon:{taxon}",
                                    entity_uri=f"http://purl.obolibrary.org/obo/NCBITaxon_{taxon}"))
        strain = store.fk_record(subject, "strain")
        rrid = normalize_rrid(strain.get("rrid")) if strain is not None else None
        if rrid and ctx.subject.strain:
            refs.append(HerdRefPlan(target="subject", attribute="strain", key=ctx.subject.strain,
                                    entity_id=rrid, entity_uri=rrid_uri(rrid)))
    located: list[tuple[Literal["electrode_group", "ogen_site"], str, str]] = [
        ("electrode_group", g.name, g.brainstem_interface_id) for g in ctx.electrode_groups]
    located += [("ogen_site", s.name, s.brainstem_interface_id) for s in ctx.optogenetic_sites]
    for target, name, interface_pk in located:
        interface = store.get("modules.experimentalinterface", interface_pk)
        if interface is None:
            continue
        candidates = [interface] + [store.fk_record(link, "procedure")
                                    for link in store.referrers(interface, "modules.procedureinterface", "interface")
                                    if link.get("relationship") in ("created", "positioned", "modified")]
        for record in candidates:
            if record is None or not is_performed(record):
                continue
            found, _ = describe.region_records(store, record)
            if not found:
                continue
            for region in found:
                term = region_term(store, region)
                if term is not None:
                    refs.append(HerdRefPlan(target=target, target_name=name, attribute="location",
                                            key=str(region.get("acronym")), entity_id=term[0], entity_uri=term[1]))
            break
    for model in ctx.device_models:
        catalog = next((store.get(label, pk) for (label, pk), name in ctx.device_model_by_record.items()
                        if name == model.name), None)
        rrid = normalize_rrid(catalog.get("rrid")) if catalog is not None else None
        if rrid and model.model_number:  # HERD annotates fields; the RRID identifies the product (model number)
            refs.append(HerdRefPlan(target="device_model", target_name=model.name, attribute="model_number",
                                    key=model.model_number, entity_id=rrid, entity_uri=rrid_uri(rrid)))
    for ref in refs:
        ctx.map("herd.terms", f"{ref.target}:{ref.target_name or ''}.{ref.attribute}", "present", ref.entity_id)
    return refs
