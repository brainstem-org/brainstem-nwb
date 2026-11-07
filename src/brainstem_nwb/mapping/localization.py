"""
Coordinates of procedures and interfaces as ndx-anatomical-localization tables, written with
``--extension brainstem``. The coordinates are stored twice by design: as recorded (every system,
with angles) in the ndx-brainstem rows, and as points in a defined space here, each row linking to
its ndx-brainstem row.

Each table localizes rows of an ndx-brainstem table (``procedures``, ``interfaces``) in one space.
Only coordinate systems that give a point in a 3D space are written:

- ``Stereotaxic_BregmaAbsolute`` / ``Stereotaxic_LambdaAbsolute``: a space with origin bregma or
  lambda, x = ML (positive right), y = AP (positive anterior), z = DV (positive ventral): orientation
  ``RAI``, millimetres;
- ``CCF_XYZ_Absolute``: the predefined Allen CCFv3 space (PIR, micrometres).

Brain-surface systems (an entry point on the brain surface and a depth along the insertion axis) do not
give a point without the brain's surface geometry, so they are left out (LOCALIZATION_NOT_SUPPORTED);
their values stay in the ndx-brainstem tables. Angles stay there too.
"""

from __future__ import annotations

from ..manifest.models import (
    BrainstemExtensionPlan,
    LocalizationPlan,
    LocalizationRowPlan,
    LocalizationTablePlan,
    SpacePlan,
)
from ..normalize.quantities import convert, parse_quantity
from . import describe
from .context import MapContext
from .registry import MappingRule, rules

SPACES: dict[str, tuple[SpacePlan, tuple[str, str, str]]] = {
    "Stereotaxic_BregmaAbsolute": (
        SpacePlan(name="Stereotaxic_BregmaAbsolute", space_name="BrainSTEM Stereotaxic_BregmaAbsolute",
                  origin="bregma", units="mm", orientation="RAI"),
        ("mlCoordinate", "apCoordinate", "dvCoordinate"),
    ),
    "Stereotaxic_LambdaAbsolute": (
        SpacePlan(name="Stereotaxic_LambdaAbsolute", space_name="BrainSTEM Stereotaxic_LambdaAbsolute",
                  origin="lambda", units="mm", orientation="RAI"),
        ("mlCoordinate", "apCoordinate", "dvCoordinate"),
    ),
    "CCF_XYZ_Absolute": (
        SpacePlan(name="AllenCCFv3", space_name="AllenCCFv3",
                  origin="Anterior-Superior-Left (ASL) corner of the 3D image volume", units="um",
                  orientation="PIR", predefined="AllenCCFv3"),
        ("x", "y", "z"),
    ),
}
LOCALIZED_TABLES = ("procedures", "interfaces")


@rules(
    MappingRule(
        id="extension.localization",
        destination="ndx-anatomical-localization: /general/localization (AnatomicalCoordinatesTable per space)",
        section="Extension",
        sources=("modules.procedure.coordinates", "modules.procedure.coordinates_json",
                 "modules.experimentalinterface.coordinates", "modules.experimentalinterface.coordinates_json"),
        transform="Stereotaxic_BregmaAbsolute and Stereotaxic_LambdaAbsolute: x = ML, y = AP, z = DV in mm "
                  "(orientation RAI, origin bregma or lambda); CCF_XYZ_Absolute: x, y, z in the Allen CCFv3 space "
                  "(PIR, um). localized_entity = the record's row in the ndx-brainstem table; brain_region = target "
                  "region acronyms; method names the coordinate system",
        units="mm (stereotaxic), um (CCF)",
        condition="--extension brainstem; coordinates in one of these systems with all three axes",
        missing="brain-surface systems and other spaces: LOCALIZATION_NOT_SUPPORTED; a missing axis or unit: "
                "LOCALIZATION_INCOMPLETE",
    ),
)
def map_localization(ctx: MapContext, brainstem: BrainstemExtensionPlan) -> LocalizationPlan:
    tables: dict[tuple[str, str], LocalizationTablePlan] = {}
    for table in brainstem.tables:
        if table.name not in LOCALIZED_TABLES:
            continue
        for position, row in enumerate(table.rows):
            record = ctx.store.get(str(row["brainstem_model"]), row["brainstem_id"])
            if record is None:
                continue
            system = record.get("coordinates")
            values = record.get("coordinates_json")
            if not system or not isinstance(values, dict) or not values:
                continue
            if system not in SPACES:
                ctx.warn("LOCALIZATION_NOT_SUPPORTED", f"coordinates in {system} are not localized", once=True,
                         rule_id="extension.localization")
                continue
            space, axes = SPACES[system]
            point: list[float | None] = []
            for axis in axes:
                quantity = parse_quantity(values.get(axis))
                try:
                    point.append(convert(quantity, space.units) if quantity is not None else None)
                except ValueError:
                    point.append(None)
            x, y, z = point
            if x is None or y is None or z is None:
                ctx.warn("LOCALIZATION_INCOMPLETE", f"{record.label} {record.pk}: {system} lacks an axis or unit",
                         record=record, rule_id="extension.localization")
                continue
            key = (table.name, system)
            if key not in tables:
                tables[key] = LocalizationTablePlan(
                    name=f"{table.name}_{space.name}",
                    description=f"Coordinates of BrainSTEM {table.name} as recorded in BrainSTEM ({system})",
                    method=f"coordinates recorded in BrainSTEM, coordinate system {system}",
                    space=space.name, entity_table=table.name)
            tables[key].rows.append(LocalizationRowPlan(
                entity_row=position, x=round(x, 9), y=round(y, 9), z=round(z, 9),
                brain_region=", ".join(describe.region_acronyms(ctx.store, record))))
            ctx.map("extension.localization", f"/general/localization/{tables[key].name}", "present", point, [record])
    used = {t.space for t in tables.values()}
    spaces = [space for space, _axes in SPACES.values() if space.name in used]
    return LocalizationPlan(spaces=sorted(spaces, key=lambda s: s.name),
                            tables=[tables[k] for k in sorted(tables)])
