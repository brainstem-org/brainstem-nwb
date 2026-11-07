"""
Export options and the optional TOML configuration file.

Some NWB fields have no source in a BrainSTEM export (who ran the session, the lab, the
institution). They can be given in a configuration file; they are never guessed::

    # brainstem-nwb.toml
    [nwbfile]
    experimenter = ["Last, First"]
    experimenter_source = "config"  # or "session_creator"
    lab = "Example Lab"
    institution = "Example University"

    [subject]
    label_field = "name"            # or "name_used_in_storage"
    species_format = "binomial"     # or "ncbitaxon" (NCBI Taxonomy IRI, as DANDI prefers)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ConfigError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


class NWBFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experimenter: list[str] = Field(default_factory=list)
    # "session_creator": use the user who created the session record in BrainSTEM as experimenter when no
    # experimenter is configured. Off by default: the creator is not necessarily who ran the session.
    experimenter_source: Literal["config", "session_creator"] = "config"
    lab: str | None = None
    institution: str | None = None


class SubjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_field: Literal["name", "name_used_in_storage"] = "name"
    species_format: Literal["binomial", "ncbitaxon"] = "binomial"


Extension = Literal["brainstem", "localization"]


class ExportOptions(BaseModel):
    """Everything that changes what is exported. Recorded in the manifest (no secrets, no paths)."""

    model_config = ConfigDict(extra="forbid")

    # NWB extensions to write: "brainstem" adds the ndx-brainstem tables (every BrainSTEM record, lossless) and the
    # ndx-anatomical-localization coordinates of procedures and interfaces; "localization" means the same
    extensions: list[Extension] = Field(default_factory=list)
    # Also write ontology terms (NCBITaxon, RRIDs, atlas regions) as a HERD zip next to each NWB file
    herd: bool = False
    # Fetch the BrainSTEM JSON schemas the records use from the server's public schema service and embed them in
    # the ndx-brainstem schemas table (needs --extension brainstem)
    embed_schemas: bool = False
    nwbfile: NWBFileConfig = Field(default_factory=NWBFileConfig)
    subject: SubjectConfig = Field(default_factory=SubjectConfig)
    sessions: list[str] | None = None
    allow_no_subject: bool = False
    infer_subjects: bool = True
    reproducible: bool = False


def load_config(path: str | Path | None) -> dict[str, Any]:
    """Read a TOML configuration file into a dict of ``ExportOptions`` fields."""
    if path is None:
        return {}
    path = Path(path)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"cannot read configuration file {path.name}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path.name}: {exc}") from exc
    unknown = set(data) - {"nwbfile", "subject"}
    if unknown:
        raise ConfigError(f"unknown section(s) in {path.name}: {', '.join(sorted(unknown))}")
    return data


def build_options(config: str | Path | dict[str, Any] | ExportOptions | None = None, **overrides: Any) -> ExportOptions:
    """Combine a configuration file (or dict) with explicit options; explicit options win."""
    if isinstance(config, ExportOptions):
        base = config.model_dump()
    elif isinstance(config, dict):
        base = dict(config)
    else:
        base = load_config(config)
    for key, value in overrides.items():
        if value is not None:
            base[key] = value
    try:
        return ExportOptions.model_validate(base)
    except ValidationError as exc:
        raise ConfigError(f"invalid options: {exc}") from exc
