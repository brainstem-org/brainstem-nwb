"""
NeuroConv-shaped metadata from an ``NwbPlan`` (Phase 4).

Raw-data converters pass this to NeuroConv so it reuses the NWBFile fields, the Subject, the
devices and the electrode groups the metadata export planned, instead of creating its own.
"""

from __future__ import annotations

from typing import Any

from ..manifest.models import NwbPlan


def neuroconv_metadata(plan: NwbPlan) -> dict[str, Any]:
    nwbfile = plan.nwbfile.model_dump(exclude_none=True, exclude={"was_generated_by"})
    metadata: dict[str, Any] = {"NWBFile": {k: v for k, v in nwbfile.items() if v not in ([], "")}}
    if plan.subject is not None:
        metadata["Subject"] = plan.subject.model_dump(exclude_none=True)
    metadata["Ecephys"] = {
        "Device": [
            {"name": d.name, **({"description": d.description} if d.description else {})}
            for d in plan.devices
            if d.name in {g.device for g in plan.electrode_groups}
        ],
        "ElectrodeGroup": [
            {"name": g.name, "description": g.description, "location": g.location, "device": g.device}
            for g in plan.electrode_groups
        ],
    }
    return metadata
