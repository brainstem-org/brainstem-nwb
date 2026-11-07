"""
Raw-data conversion (Phase 4): the converter interface.

A converter adds the measured data of one BrainSTEM data acquisition to the NWB file that the
metadata export built, typically through NeuroConv. It is chosen by ``DataAcquisition.type``
(or explicitly in the data-path file). Converters never invent timing: a recording's start is
the start of the epoch it belongs to, or an explicit ``starting_time`` from the user.

No converter ships in this release; the first planned one is flat binary (``.dat``)
extracellular electrophysiology (see docs/design/phase4-raw-data.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..manifest.models import ConversionWarning, DataSource


@dataclass(frozen=True)
class RawPaths:
    """Local files of one data acquisition, resolved from the data-path file."""

    files: tuple[Path, ...]
    starting_time: float | None = None  # seconds from the session start, when the user states it
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversionResult:
    converter: str
    nwb_objects: list[str] = field(default_factory=list)  # paths of what was added, e.g. /acquisition/ElectricalSeries
    files: list[str] = field(default_factory=list)  # relative or redacted paths of the inputs
    warnings: list[ConversionWarning] = field(default_factory=list)


@runtime_checkable
class RawDataConverter(Protocol):
    name: str
    acquisition_types: tuple[str, ...]

    def check(self, source: DataSource, details: dict[str, Any], paths: RawPaths) -> list[ConversionWarning]:
        """Check the files against the BrainSTEM details (channels, sampling rate, size) without reading data."""

    def add_to_nwbfile(self, nwbfile: Any, source: DataSource, details: dict[str, Any], paths: RawPaths,
                       metadata: dict[str, Any]) -> ConversionResult:
        """Add the acquisition's data to ``nwbfile``. ``metadata`` is NeuroConv-shaped, from the NwbPlan."""
