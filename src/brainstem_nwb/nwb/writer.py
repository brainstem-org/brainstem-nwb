"""
Build and write an NWB file from an ``NwbPlan``.

This module knows nothing about BrainSTEM: everything it writes is in the plan. Files are
written to a temporary name next to the target and moved into place, so an interrupted export
never leaves a partial file under the final name.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from pynwb import NWBHDF5IO, NWBFile
from pynwb.device import Device, DeviceModel
from pynwb.file import Subject

from ..errors import ConfigError
from ..manifest.models import BrainstemExtensionPlan, HerdRefPlan, LocalizationPlan, NwbPlan

PROVENANCE_HEADER = "BrainSTEM provenance (JSON):"


def notes_with_provenance(plan: NwbPlan) -> str:
    notes = plan.nwbfile.notes or ""
    if not plan.provenance:
        return notes
    block = json.dumps(plan.provenance, indent=2, sort_keys=True, ensure_ascii=False)
    return f"{notes}\n\n{PROVENANCE_HEADER}\n{block}" if notes else f"{PROVENANCE_HEADER}\n{block}"


def build_nwbfile(plan: NwbPlan) -> NWBFile:
    f = plan.nwbfile
    kwargs = {
        "session_description": f.session_description,
        "identifier": f.identifier,
        "session_start_time": f.session_start_time,
        "timestamps_reference_time": f.timestamps_reference_time,
        "notes": notes_with_provenance(plan),
    }
    if f.file_create_date is not None:
        kwargs["file_create_date"] = f.file_create_date
    for key in ("session_id", "experiment_description", "lab", "institution", "protocol", "surgery", "virus",
                "pharmacology", "stimulus_notes", "data_collection", "slices", "source_script",
                "source_script_file_name"):
        value = getattr(f, key)
        if value:
            kwargs[key] = value
    for key in ("experimenter", "keywords", "related_publications"):
        value = getattr(f, key)
        if value:
            kwargs[key] = list(value)
    if f.was_generated_by:
        kwargs["was_generated_by"] = [list(item) for item in f.was_generated_by]
    nwbfile = NWBFile(**kwargs)

    if plan.subject is not None:
        s = plan.subject
        subject_kwargs = {key: getattr(s, key) for key in (
            "subject_id", "species", "strain", "sex", "date_of_birth", "age", "age__reference", "genotype",
            "description", "weight") if getattr(s, key) not in (None, "")}
        nwbfile.subject = Subject(**subject_kwargs)

    models = {}
    for model in plan.device_models:
        models[model.name] = DeviceModel(name=model.name, manufacturer=model.manufacturer,
                                         model_number=model.model_number, description=model.description)
        nwbfile.add_device_model(models[model.name])
    devices = {}
    for device in plan.devices:
        device_kwargs = {"name": device.name}
        if device.description:
            device_kwargs["description"] = device.description
        if device.serial_number:
            device_kwargs["serial_number"] = device.serial_number
        if device.model:
            device_kwargs["model"] = models[device.model]
        devices[device.name] = Device(**device_kwargs)
        nwbfile.add_device(devices[device.name])

    for group in plan.electrode_groups:
        nwbfile.create_electrode_group(name=group.name, description=group.description, location=group.location,
                                       device=devices[group.device])
    for site in plan.optogenetic_sites:
        nwbfile.create_ogen_site(name=site.name, device=devices[site.device], description=site.description,
                                 excitation_lambda=site.excitation_lambda, location=site.location)

    if plan.epochs.rows:
        for column in plan.epochs.columns:
            nwbfile.add_epoch_column(name=column.name, description=column.description)
        for row in plan.epochs.rows:
            values = {column.name: row.values.get(column.name, "") for column in plan.epochs.columns}
            nwbfile.add_epoch(start_time=row.start_time, stop_time=row.stop_time, tags=list(row.tags), **values)
    if plan.brainstem is not None:
        brainstem_tables = add_brainstem_extension(nwbfile, plan.brainstem)
        if plan.localization is not None:
            add_localization(nwbfile, plan.localization, brainstem_tables)
    return nwbfile


def add_localization(nwbfile: NWBFile, plan: LocalizationPlan, brainstem_tables: dict[str, Any]) -> None:
    """ndx-anatomical-localization tables over rows of the ndx-brainstem tables."""
    try:
        from ndx_anatomical_localization import AllenCCFv3Space, AnatomicalCoordinatesTable, Localization, Space
    except ImportError as exc:
        raise ConfigError("--extension localization needs ndx-anatomical-localization (installed with "
                          "ndx-brainstem)") from exc
    spaces: dict[str, Any] = {}
    for space in plan.spaces:
        if space.predefined == "AllenCCFv3":
            spaces[space.name] = AllenCCFv3Space(name=space.name)
        else:
            spaces[space.name] = Space(name=space.name, space_name=space.space_name, origin=space.origin,
                                       units=space.units, orientation=space.orientation)
    tables = []
    for table_plan in plan.tables:
        table = AnatomicalCoordinatesTable(name=table_plan.name, description=table_plan.description,
                                           method=table_plan.method, space=spaces[table_plan.space],
                                           target=brainstem_tables[table_plan.entity_table])
        table.add_column(name="brain_region", description="target brain regions (acronyms) of the record")
        for row in table_plan.rows:
            table.add_row(x=row.x, y=row.y, z=row.z, localized_entity=row.entity_row, brain_region=row.brain_region)
        tables.append(table)
    nwbfile.add_lab_meta_data(Localization(anatomical_coordinates_tables=tables, spaces=list(spaces.values())))


EXTENSION_HINT = (
    "--extension brainstem needs the ndx-brainstem package: "
    'pip install "brainstem-nwb[extensions]"'
)


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def installed_extension_version() -> str | None:
    """Version of the ndx-brainstem namespace pynwb has loaded, or None when it cannot be read."""
    try:
        from pynwb import get_type_map

        return str(get_type_map().namespace_catalog.get_namespace("ndx-brainstem").version)
    except Exception:  # any failure here means "unknown", never a crash
        return None


def check_extension_version(required: str, installed: str | None = None) -> None:
    """Raise ConfigError when the installed ndx-brainstem is older than the namespace this release writes
    (``BrainstemExtensionPlan.namespace_version``): the schema table and coordinates column need it."""
    installed = installed if installed is not None else installed_extension_version()
    if installed is None:
        return
    if _version_tuple(installed) < _version_tuple(required):
        raise ConfigError(
            f"ndx-brainstem {installed} is installed, but --extension brainstem writes namespace version "
            f"{required} (schema_url and coordinates_schema columns). Upgrade it: {EXTENSION_HINT}"
        )


def add_brainstem_extension(nwbfile: NWBFile, plan: BrainstemExtensionPlan) -> dict[str, Any]:
    """Add the ndx-brainstem BrainstemMetadata container and its tables."""
    try:
        from ndx_brainstem import BrainstemMetadata, BrainstemSchemaTable, BrainstemTable
    except ImportError as exc:
        raise ConfigError(EXTENSION_HINT) from exc
    check_extension_version(plan.namespace_version)
    tables = {
        table.name: BrainstemTable(name=table.name, description=table.description,
                                   brainstem_models=list(table.brainstem_models))
        for table in plan.tables
    }
    schemas = None
    if plan.schemas:
        description = "BrainSTEM JSON schemas named by the tables"
        if plan.schemas_terms:
            description += f". {plan.schemas_terms}"
        schemas = BrainstemSchemaTable(name="schemas", description=description)
        for schema in plan.schemas:
            schemas.add_row(schema_id=schema["schema_id"], schema_url=schema["schema_url"],
                            schema_json=schema["schema_json"])
    attributes = dict(plan.attributes)
    metadata = BrainstemMetadata(brainstem_tables=list(tables.values()), schemas=schemas, **attributes)
    nwbfile.add_lab_meta_data(metadata)  # attach first, so links between tables share an ancestor
    # Text columns and rows first; links once every table has its rows (hdmf checks link bounds).
    for table in plan.tables:
        target_table = tables[table.name]
        text_columns = [c for c in table.columns if c.link_table is None]
        for column in text_columns:
            target_table.add_column(name=column.name, description=column.description)
        for row in table.rows:
            target_table.add_row(brainstem_id=row["brainstem_id"], brainstem_model=row["brainstem_model"],
                                 **{c.name: str(row.get(c.name, "")) for c in text_columns})
    for table in plan.tables:
        target_table = tables[table.name]
        for column in table.columns:
            if column.link_table is None:
                continue
            linked = nwbfile.epochs if column.link_table == "/intervals/epochs" else tables[column.link_table]
            values = [list(row.get(column.name) or []) for row in table.rows]
            if not any(values):  # no row links anything (hdmf cannot store an empty ragged column)
                continue
            flat = np.array([v for row_values in values for v in row_values], dtype=np.int64)
            ends = np.cumsum([len(row_values) for row_values in values]).astype(np.int64)
            target_table.add_column(name=column.name, description=column.description, table=linked,
                                    data=flat, index=ends)
    return tables


def write_nwbfile(nwbfile: NWBFile, path: Path, *, herd: list[HerdRefPlan] | None = None,
                  herd_path: Path | None = None) -> str:
    """Write ``nwbfile`` atomically to ``path`` (and its HERD references to ``herd_path``); return its sha256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}.partial{path.suffix}")
    tmp_herd = herd_path.with_name(f".{herd_path.name}.partial") if herd and herd_path else None
    try:
        if tmp_herd is not None and herd:
            with NWBHDF5IO(str(tmp), mode="w", herd_path=str(tmp_herd)) as io:
                io.write(nwbfile, herd=build_herd(nwbfile, herd))
        else:
            with NWBHDF5IO(str(tmp), mode="w") as io:
                io.write(nwbfile)
        os.replace(tmp, path)
        if tmp_herd is not None and herd_path is not None:
            _normalize_zip(tmp_herd)
            os.replace(tmp_herd, herd_path)
    finally:
        for leftover in (tmp, tmp_herd):
            if leftover is not None and leftover.exists():
                leftover.unlink()
    return file_sha256(path)


def _normalize_zip(path: Path) -> None:
    """
    Store the HERD tables under their file names only. hdmf's HERD.to_zip stores them under the full
    path they were written to (leaking local directories), and HERD.from_zip then cannot find them.
    """
    import zipfile

    with zipfile.ZipFile(path) as source:
        members = [(Path(info.filename).name, source.read(info)) for info in source.infolist()]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, data)


def build_herd(nwbfile: NWBFile, refs: list[HerdRefPlan]) -> Any:
    """HERD references for core objects of ``nwbfile``."""
    from hdmf.common import HERD
    from pynwb import get_type_map

    herd = HERD(type_map=get_type_map())
    for ref in refs:
        if ref.target == "subject":
            container = nwbfile.subject
        elif ref.target == "electrode_group":
            container = nwbfile.electrode_groups[ref.target_name]
        elif ref.target == "ogen_site":
            container = nwbfile.ogen_sites[ref.target_name]
        else:
            container = nwbfile.device_models[ref.target_name]
        herd.add_ref(container=container, attribute=ref.attribute, key=ref.key, entity_id=ref.entity_id,
                     entity_uri=ref.entity_uri)
    return herd


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_identifier(path: Path) -> str | None:
    """The identifier of an existing NWB file, or None when it cannot be read."""
    try:
        import h5py

        with h5py.File(path, "r") as handle:
            value = handle["identifier"][()]
            return value.decode("utf-8") if isinstance(value, bytes) else str(value)
    except Exception:
        return None
