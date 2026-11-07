"""State shared by the mapper functions while one unit is mapped."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import ExportOptions
from ..manifest.models import (
    ConversionWarning,
    DeviceModelPlan,
    DevicePlan,
    ElectrodeGroupPlan,
    EpochsPlan,
    FieldMapping,
    OptogeneticSitePlan,
    SourcePointer,
    SubjectPlan,
    ValueState,
)
from ..manifest.warnings import make_warning
from ..normalize.units import ExportUnit
from ..retrieval.loader import ProjectExport
from ..store.graph import Record, RecordStore
from ..store.inventory import Inventory


@dataclass
class MapContext:
    store: RecordStore
    unit: ExportUnit
    options: ExportOptions
    export: ProjectExport
    warnings: list[ConversionWarning] = field(default_factory=list)
    mappings: list[FieldMapping] = field(default_factory=list)
    # The NWB plan under construction
    nwbfile: dict[str, Any] = field(default_factory=dict)
    subject: SubjectPlan | None = None
    device_models: list[DeviceModelPlan] = field(default_factory=list)
    devices: list[DevicePlan] = field(default_factory=list)
    electrode_groups: list[ElectrodeGroupPlan] = field(default_factory=list)
    optogenetic_sites: list[OptogeneticSitePlan] = field(default_factory=list)
    epochs: EpochsPlan = field(default_factory=EpochsPlan)
    notes_sections: list[tuple[str, str]] = field(default_factory=list)
    device_by_record: dict[tuple[str, str], str] = field(default_factory=dict)
    device_model_by_record: dict[tuple[str, str], str] = field(default_factory=dict)
    pharmacology_sources: list[Record] = field(default_factory=list)
    _names: set[str] = field(default_factory=set)
    _warned: set[tuple[str, str | None]] = field(default_factory=set)

    @property
    def inventory(self) -> Inventory:
        return self.store.inventory

    def unique_name(self, name: str) -> str:
        """An NWB object name not used yet in this file ('/' is not allowed in NWB names)."""
        base = (name or "unnamed").replace("/", "-").strip() or "unnamed"
        candidate, counter = base, 2
        while candidate in self._names:
            candidate = f"{base} ({counter})"
            counter += 1
        self._names.add(candidate)
        return candidate

    def add_notes(self, heading: str, lines: list[str]) -> None:
        lines = [line for line in lines if line]
        if lines:
            self.notes_sections.append((heading, "\n".join(lines)))

    def map(
        self,
        rule_id: str,
        nwb_path: str,
        state: ValueState,
        value: Any = None,
        sources: list[Record] | list[SourcePointer] | None = None,
        note: str | None = None,
    ) -> None:
        """Record an intended NWB destination and the state of its value."""
        pointers: list[SourcePointer] = []
        for source in sources or []:
            if isinstance(source, SourcePointer):
                pointers.append(source)
            else:
                pointers.append(SourcePointer(label=source.label, pk=source.pk))
        self.mappings.append(FieldMapping(
            rule_id=rule_id, nwb_path=nwb_path, state=state,
            value=_short(value) if state == "present" else None, sources=pointers, note=note,
        ))

    def warn(self, code: str, message: str | None = None, *, record: Record | None = None,
             path: str | None = None, nwb_path: str | None = None, rule_id: str | None = None,
             once: bool = False) -> None:
        """Add a warning; with ``once``, only the first warning of this code in the unit is kept."""
        if once:
            key = (code, message)
            if key in self._warned:
                return
            self._warned.add(key)
        self.warnings.append(make_warning(
            code, message,
            label=record.label if record else None, pk=record.pk if record else None,
            path=path, nwb_path=nwb_path, rule_id=rule_id,
        ))


def _short(value: Any) -> Any:
    """Values recorded in mappings are previews; long text is cut (the full text is in the NWB plan)."""
    if isinstance(value, str) and len(value) > 300:
        return value[:297] + "..."
    return value
