"""
The data-path file (Phase 4): where the raw files of BrainSTEM data acquisitions are on disk.

Large recordings stay local; BrainSTEM only records their names. The file maps data
acquisitions to local files, either explicitly or through a template::

    # data-paths.toml
    [defaults]
    root = "/data/lab"
    template = "{root}/{subject_storage}/{session_storage}/{file_name}"

    [dataacquisition."<DataAcquisition uuid>"]
    files = ["/data/lab/SM01/SM01_240401/SM01_240401.dat"]
    converter = "flat-binary-ephys"
    starting_time = 0.0
    options = { xml_file_path = "/data/lab/SM01/SM01_240401/SM01_240401.xml" }

Template fields: ``root``, ``subject_storage`` and ``session_storage`` (the BrainSTEM
``name_used_in_storage``, falling back to the names), ``file_name`` (from the acquisition's
details) and ``dataacquisition_id``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..manifest.models import DataSource
from .base import RawPaths


class AcquisitionPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[str] = Field(default_factory=list)
    converter: str | None = None
    starting_time: float | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class PathDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str | None = None
    template: str | None = None


class DataPathFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: PathDefaults = Field(default_factory=PathDefaults)
    dataacquisition: dict[str, AcquisitionPaths] = Field(default_factory=dict)


def resolve(paths: DataPathFile, source: DataSource, *, session_name: str, subject_name: str | None) -> RawPaths | None:
    """Local files of one acquisition: the explicit entry, else the template; None when neither applies."""
    entry = paths.dataacquisition.get(source.dataacquisition_id)
    if entry is not None and entry.files:
        return RawPaths(files=tuple(Path(f) for f in entry.files), starting_time=entry.starting_time,
                        options=dict(entry.options))
    template = paths.defaults.template
    if not template or not source.file_name:
        return None
    path = template.format(
        root=paths.defaults.root or "",
        subject_storage=source.subject_storage_name or subject_name or "",
        session_storage=source.session_storage_name or session_name,
        file_name=source.file_name,
        dataacquisition_id=source.dataacquisition_id,
    )
    return RawPaths(files=(Path(path),), starting_time=entry.starting_time if entry else None,
                    options=dict(entry.options) if entry else {})
