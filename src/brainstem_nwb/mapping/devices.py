"""
NWB devices, electrode groups and optogenetic stimulus sites.

Devices come from the equipment of the included acquisitions, manipulations, procedures and
interfaces, and from the experimental interfaces (probes, fibers, ...) the acquisitions and
manipulations use. No electrode (channel) rows and no positions are written: channel geometry
belongs with the raw data (Phase 4) and BrainSTEM coordinates have no single NWB frame.
"""

from __future__ import annotations

from ..manifest.models import DeviceModelPlan, DevicePlan, ElectrodeGroupPlan, OptogeneticSitePlan
from ..normalize.quantities import convert, parse_quantity
from ..normalize.text import humanize_code
from ..normalize.units import is_performed
from ..store.graph import Record
from . import describe
from .context import MapContext
from .registry import MappingRule, rules

SECTION = "Devices"

EPHYS_INTERFACE_TYPES = {
    "SiliconProbe", "Tetrode", "SingleWireElectrode", "TungstenMicroelectrode", "MultiElectrodeArray",
    "ECoG", "EEG",
}
EPHYS_ACQUISITION_TYPES = {"ExtracellularEphys", "Electroencephalography"}
OPTIC_FIBER_TYPES = {"OpticFiber"}
OPTOGENETIC_MANIPULATIONS = {"OptogeneticStimulation"}


@rules(
    MappingRule(id="devices.equipment", destination="NWBFile.devices (Device)", section=SECTION,
                sources=("modules.equipment.name", "modules.equipment.type", "modules.equipment.notes",
                         "personal_attributes.setup.name", "personal_attributes.setup.location",
                         "taxonomies.setuptype.name", "resources.hardwaredevice.name",
                         "resources.hardwaredevice.type"),
                transform="Device(name=<equipment name>, description=\"<type>; setup <name> (<location>; <setup "
                          "type>); hardware <device name>; <notes>; BrainSTEM equipment <id>\", model=<DeviceModel of "
                          "its hardware device>)",
                condition="equipment of an included acquisition, manipulation, procedure or interface; equipment the "
                          "exporting user cannot read is named in the text fields only"),
    MappingRule(id="devices.models", destination="NWBFile.device_models (DeviceModel)", section=SECTION,
                sources=("resources.hardwaredevice.name", "resources.hardwaredevice.type",
                         "resources.hardwaredevice.type_json", "resources.hardwaredevice.rrid",
                         "resources.hardwaredevice.supplier", "resources.consumable.supplier",
                         "resources.supplier.name"),
                transform="one DeviceModel per hardware device (equipment) or device design (consumable of an "
                          "interface, e.g. a probe design): name, manufacturer = supplier name, model_number = "
                          "details.productId, description = type, other details, RRID, BrainSTEM id. "
                          "Device.manufacturer (deprecated) is never used",
                condition="the catalog entry has a supplier (NWB requires a manufacturer)",
                missing="no DeviceModel (DEVICE_MANUFACTURER_UNKNOWN); the catalog entry is described in the "
                        "Device description"),
    MappingRule(id="devices.interfaces", destination="NWBFile.devices (Device)", section=SECTION,
                sources=("modules.experimentalinterface.name", "modules.experimentalinterface.type",
                         "modules.experimentalinterface.type_json", "modules.experimentalinterface.notes",
                         "modules.experimentalinterface.installed_at", "modules.experimentalinterface.removed_at",
                         "modules.experimentalinterface.target_regions"),
                transform="Device(name=<interface name>, description=\"<type>; <details>; design <consumable>; "
                          "installed <date>; removed <date>; <notes>; BrainSTEM interface <id>\", "
                          "serial_number=details.deviceIdentifier)",
                condition="interfaces used by included acquisitions or manipulations"),
)
def _device_model(ctx: MapContext, catalog: Record | None) -> str | None:
    """The DeviceModel for a hardware device or device design; None when it has no supplier."""
    if catalog is None:
        return None
    if catalog.key in ctx.device_model_by_record:
        return ctx.device_model_by_record[catalog.key]
    supplier = ctx.store.fk_record(catalog, "supplier")
    if supplier is None or not supplier.get("name"):
        ctx.warn("DEVICE_MANUFACTURER_UNKNOWN", record=catalog, rule_id="devices.models", once=True)
        return None
    details = catalog.get("type_json") if isinstance(catalog.get("type_json"), dict) else {}
    parts = [humanize_code(str(catalog.get("type") or "device"))]
    detail = describe.details_text({k: v for k, v in details.items() if k != "productId"})
    if detail:
        parts.append(detail)
    if catalog.get("rrid"):
        parts.append(str(catalog.get("rrid")))
    parts.append(f"BrainSTEM {catalog.label.split('.')[-1]} {catalog.pk}")
    name = ctx.unique_name(str(catalog.get("name") or "device model"))
    product = details.get("productId")
    ctx.device_models.append(DeviceModelPlan(
        name=name, manufacturer=str(supplier.get("name")),
        model_number=str(product) if product not in (None, "") else None, description="; ".join(parts)))
    ctx.device_model_by_record[catalog.key] = name
    ctx.map("devices.models", f"/general/device_models/{name}", "present", name, [catalog, supplier])
    return name


def _design(ctx: MapContext, interface: Record) -> Record | None:
    """The catalog entry (consumable) an interface was made from, through its source material usage."""
    usage = ctx.store.fk_record(interface, "source_material_usage")
    if usage is None:
        return None
    consumable = ctx.store.fk_record(usage, "consumable")
    if consumable is None:
        stock = ctx.store.fk_record(usage, "consumable_stock")
        consumable = ctx.store.fk_record(stock, "consumable") if stock is not None else None
    return consumable


def map_devices(ctx: MapContext) -> None:
    store = ctx.store
    for equipment in ctx.unit.role("equipment"):
        parts = [humanize_code(str(equipment.get("type") or "equipment"))]
        setup = store.fk_record(equipment, "setup")
        if setup is not None:
            setup_type = store.fk_record(setup, "setup_type")
            setup_details = [str(p) for p in (setup.get("location"), setup_type.get("name") if setup_type else None)
                             if p]
            parts.append(f"setup {setup.get('name')}" + (f" ({'; '.join(setup_details)})" if setup_details else ""))
        hardware = store.fk_record(equipment, "hardwaredevice")
        model = _device_model(ctx, hardware)
        if hardware is not None:
            detail = describe.details_text(hardware.get("type_json"))
            parts.append(f"hardware {hardware.get('name')}" + (f" ({detail})" if detail else ""))
        consumable = store.fk_record(equipment, "consumable")
        if consumable is not None:
            parts.append(f"consumable {describe.consumable_text(store, consumable)}")
        notes = describe.notes_text(equipment)
        if notes:
            parts.append(notes)
        parts.append(f"BrainSTEM equipment {equipment.pk}")
        name = ctx.unique_name(str(equipment.get("name") or "equipment"))
        ctx.devices.append(DevicePlan(name=name, description="; ".join(parts), model=model,
                                      brainstem_label=equipment.label, brainstem_id=equipment.pk))
        ctx.device_by_record[equipment.key] = name
        ctx.map("devices.equipment", f"/general/devices/{name}", "present", name, [equipment])

    for interface in ctx.unit.role("interface"):
        details = interface.get("type_json") if isinstance(interface.get("type_json"), dict) else {}
        parts = [humanize_code(str(interface.get("type") or "interface"))]
        detail = describe.details_text({k: v for k, v in details.items() if k != "deviceIdentifier"})
        if detail:
            parts.append(detail)
        usage = store.fk_record(interface, "source_material_usage")
        if usage is not None:
            parts.append(f"design {describe.material_text(store, usage)}")
        targets = describe.regions_text(store, interface)
        if targets:
            parts.append(f"targets {targets}")
        coordinates = describe.coordinates_text(interface.get("coordinates"), interface.get("coordinates_json"))
        if coordinates:
            parts.append(f"coordinates {coordinates}")
        for key, label in (("installed_at", "installed"), ("removed_at", "removed")):
            value = describe.when(interface.get(key))
            if value:
                parts.append(f"{label} {value}")
        notes = describe.notes_text(interface)
        if notes:
            parts.append(notes)
        parts.append(f"BrainSTEM interface {interface.pk}")
        serial = details.get("deviceIdentifier")
        model = _device_model(ctx, _design(ctx, interface))
        name = ctx.unique_name(str(interface.get("name") or interface.get("type") or "interface"))
        ctx.devices.append(DevicePlan(name=name, description="; ".join(parts), model=model,
                                      serial_number=str(serial) if serial not in (None, "") else None,
                                      brainstem_label=interface.label, brainstem_id=interface.pk))
        ctx.device_by_record[interface.key] = name
        ctx.map("devices.interfaces", f"/general/devices/{name}", "present", name, [interface])


def _location(ctx: MapContext, interface: Record) -> tuple[str, str, bool]:
    """
    (location, region description, resolved): the target region acronyms of the interface, or of
    the procedure that placed it, as NWB ``location``, and their full names and atlas for the
    description. ``("unknown", "", False)`` when no target region is recorded or none is in the export.
    """
    store = ctx.store
    candidates = [interface]
    for link in store.referrers(interface, "modules.procedureinterface", "interface"):
        if link.get("relationship") in ("created", "positioned", "modified"):
            procedure = store.fk_record(link, "procedure")
            if procedure is not None and is_performed(procedure):
                candidates.append(procedure)
    for record in candidates:
        acronyms = describe.region_acronyms(store, record)
        if acronyms:
            return ", ".join(acronyms), describe.regions_text(store, record), True
    return "unknown", "", False


@rules(
    MappingRule(id="devices.electrode_groups", destination="NWBFile.electrode_groups (ElectrodeGroup)",
                section=SECTION,
                sources=("modules.experimentalinterface.name", "modules.experimentalinterface.target_regions",
                         "modules.dataacquisition.type_json", "taxonomies.anatomicalregion.acronym",
                         "taxonomies.anatomicalregion.name", "taxonomies.anatomicalreference.name",
                         "taxonomies.anatomicalreference.version"),
                transform="one ElectrodeGroup per electrophysiology interface (silicon probe, tetrode, wire, "
                          "array, ECoG, EEG) used by an ExtracellularEphys or EEG acquisition; when that acquisition "
                          "uses exactly one such interface and defines electrode groups, one ElectrodeGroup per "
                          "group ('<interface>_<label>', channels in the description). location = the target "
                          "region acronyms of the interface, or else of the procedure that created or positioned "
                          "it; region names and atlas go to the description",
                missing="location 'unknown' (REGION_NOT_RESOLVED); no position; no electrode rows "
                        "(ELECTRODES_NOT_WRITTEN)"),
)
def map_electrode_groups(ctx: MapContext) -> None:
    store = ctx.store
    acquisitions = [da for da in ctx.unit.role("dataacquisition") if da.get("type") in EPHYS_ACQUISITION_TYPES]
    seen: set[str] = set()
    unresolved = False
    for acquisition in sorted(acquisitions, key=lambda r: (r.get("order") or 0, r.pk)):
        interfaces = [i for i in store.m2m_records(acquisition, "interfaces") if i.get("type") in EPHYS_INTERFACE_TYPES]
        details = acquisition.get("type_json") if isinstance(acquisition.get("type_json"), dict) else {}
        groups = [g for g in details.get("electrodeGroups") or [] if isinstance(g, dict)]
        if groups and len(interfaces) > 1:
            ctx.warn("ELECTRODE_GROUP_LABELS_UNATTRIBUTABLE", record=acquisition,
                     rule_id="devices.electrode_groups")
        for interface in interfaces:
            if interface.pk in seen:
                continue
            seen.add(interface.pk)
            device = ctx.device_by_record.get(interface.key)
            if device is None:
                continue
            location, region_text, resolved = _location(ctx, interface)
            unresolved = unresolved or not resolved
            kind = humanize_code(str(interface.get("type")))
            regions_suffix = f"; target {region_text}" if region_text else ""
            if groups and len(interfaces) == 1:
                for index, group in enumerate(groups, start=1):
                    label = str(group.get("label") or f"group{index}")
                    channels = [c for c in group.get("channels") or [] if isinstance(c, int)]
                    name = ctx.unique_name(f"{interface.get('name')}_{label}")
                    description = (f"{kind} {interface.get('name')}, electrode group '{label}' of acquisition "
                                   f"{acquisition.pk}" + (f"; channels {_ranges(channels)}" if channels else "")
                                   + regions_suffix)
                    ctx.electrode_groups.append(ElectrodeGroupPlan(
                        name=name, description=description, location=location, device=device,
                        brainstem_interface_id=interface.pk, channels=channels or None))
                    ctx.map("devices.electrode_groups", f"/general/extracellular_ephys/{name}", "present", name,
                            [interface, acquisition])
            else:
                name = ctx.unique_name(str(interface.get("name")))
                if name == device:  # an ElectrodeGroup may not share its name with its device
                    ctx._names.discard(name)
                    name = ctx.unique_name(f"{interface.get('name')}_group")
                ctx.electrode_groups.append(ElectrodeGroupPlan(
                    name=name, description=f"{kind} {interface.get('name')}{regions_suffix}", location=location,
                    device=device,
                    brainstem_interface_id=interface.pk))
                ctx.map("devices.electrode_groups", f"/general/extracellular_ephys/{name}", "present", name,
                        [interface, acquisition])
    if unresolved:
        ctx.warn("REGION_NOT_RESOLVED", rule_id="devices.electrode_groups", once=True)
    if ctx.electrode_groups:
        ctx.warn("ELECTRODES_NOT_WRITTEN", rule_id="devices.electrode_groups")


def _ranges(channels: list[int]) -> str:
    """[0,1,2,3,7] -> '0-3, 7'."""
    if not channels:
        return ""
    values = sorted(set(channels))
    out = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        out.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = value
    out.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(out)


@rules(
    MappingRule(id="devices.optogenetic_sites", destination="NWBFile.ogen_sites (OptogeneticStimulusSite)",
                section=SECTION,
                sources=("modules.experimentalinterface.name", "modules.experimentalinterface.target_regions",
                         "modules.manipulation.type_json"),
                transform="one site per optic fiber interface used by an OptogeneticStimulation manipulation; "
                          "excitation_lambda = the protocols' wavelength converted to nm; description = the "
                          "stimulation protocols as stored",
                units="nm",
                condition="exactly one distinct wavelength with a unit is recorded for the fiber",
                missing="no site (OPTO_SITE_NO_WAVELENGTH, OPTO_SITE_WAVELENGTH_AMBIGUOUS, LEGACY_BARE_NUMBER); "
                        "the fiber is still a Device; no OptogeneticSeries (no stimulus data)"),
)
def map_optogenetic_sites(ctx: MapContext) -> None:
    store = ctx.store
    by_interface: dict[str, list[Record]] = {}
    for manipulation in ctx.unit.role("manipulation"):
        if manipulation.get("type") not in OPTOGENETIC_MANIPULATIONS:
            continue
        for interface in store.m2m_records(manipulation, "interfaces"):
            if interface.get("type") in OPTIC_FIBER_TYPES:
                by_interface.setdefault(interface.pk, []).append(manipulation)
    for interface_pk in sorted(by_interface):
        fiber = store.get("modules.experimentalinterface", interface_pk)
        manipulations = by_interface[interface_pk]
        if fiber is None:
            continue
        interface = fiber
        wavelengths: set[float] = set()
        bare = False
        for manipulation in manipulations:
            items = manipulation.get("type_json")
            items = items if isinstance(items, list) else [items] if isinstance(items, dict) else []
            for item in items:
                if not isinstance(item, dict) or item.get("wavelength") in (None, ""):
                    continue
                quantity = parse_quantity(item.get("wavelength"))
                if quantity is None:
                    continue
                if quantity.unit is None:
                    bare = True
                    continue
                try:
                    wavelengths.add(round(convert(quantity, "nm"), 6))
                except ValueError:
                    bare = True
        nwb_path = f"/general/optogenetics/{interface.get('name')}"
        if bare:
            ctx.warn("LEGACY_BARE_NUMBER",
                     f"a wavelength for optic fiber '{interface.get('name')}' has no (convertible) unit",
                     record=manipulations[0], rule_id="devices.optogenetic_sites")
        if len(wavelengths) != 1:
            code = "OPTO_SITE_NO_WAVELENGTH" if not wavelengths else "OPTO_SITE_WAVELENGTH_AMBIGUOUS"
            ctx.warn(code, record=interface, nwb_path=nwb_path, rule_id="devices.optogenetic_sites")
            ctx.map("devices.optogenetic_sites", nwb_path, "missing", sources=[interface, *manipulations],
                    note=code)
            continue
        device = ctx.device_by_record.get(interface.key)
        if device is None:
            continue
        location, region_text, resolved = _location(ctx, interface)
        if not resolved:
            ctx.warn("REGION_NOT_RESOLVED", rule_id="devices.optogenetic_sites", once=True)
        description = "; ".join(
            f"{describe.ref(m)} {describe.details_text(m.get('type_json'))}".strip() for m in manipulations)
        if region_text:
            description = f"{description}; target {region_text}"
        name = ctx.unique_name(f"{interface.get('name')}_site")
        ctx.optogenetic_sites.append(OptogeneticSitePlan(
            name=name, description=description or "optogenetic stimulation", device=device,
            excitation_lambda=next(iter(wavelengths)), location=location, brainstem_interface_id=interface.pk))
        ctx.map("devices.optogenetic_sites", f"/general/optogenetics/{name}", "present", name,
                [interface, *manipulations])
