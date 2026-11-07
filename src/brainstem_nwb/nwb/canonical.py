"""
A canonical, comparable summary of an NWB file's metadata.

HDF5 files written twice from the same plan are not byte-identical (random object ids, HDF5
timestamps), so reproducibility and the semantic validation compare this summary instead.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from pynwb import NWBHDF5IO

from .writer import PROVENANCE_HEADER

_NWBFILE_FIELDS = (
    "identifier", "session_description", "session_id", "experiment_description", "experimenter", "lab",
    "institution", "keywords", "related_publications", "protocol", "surgery", "virus", "pharmacology",
    "stimulus_notes", "data_collection", "slices", "notes", "source_script", "source_script_file_name",
)
_SUBJECT_FIELDS = ("subject_id", "species", "strain", "sex", "date_of_birth", "age", "age__reference", "genotype",
                   "description", "weight")


def _plain(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "tolist"):
        return _plain(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if not isinstance(value, str) and hasattr(value, "__len__") and hasattr(value, "__getitem__"):
        return [_plain(value[index]) for index in range(len(value))]  # h5py / hdmf string datasets
    return value


def canonical_summary(path: Path) -> dict[str, Any]:
    with NWBHDF5IO(str(path), mode="r") as io:
        nwbfile = io.read()
        out: dict[str, Any] = {key: _plain(getattr(nwbfile, key, None)) for key in _NWBFILE_FIELDS}
        out["session_start_time"] = _plain(nwbfile.session_start_time)
        out["timestamps_reference_time"] = _plain(nwbfile.timestamps_reference_time)
        out["was_generated_by"] = _plain(getattr(nwbfile, "was_generated_by", None))
        subject = nwbfile.subject
        out["subject"] = {key: _plain(getattr(subject, key, None)) for key in _SUBJECT_FIELDS} if subject else None
        out["devices"] = {
            name: {"description": device.description, "serial_number": getattr(device, "serial_number", None)}
            for name, device in sorted(nwbfile.devices.items())
        }
        out["electrode_groups"] = {
            name: {"description": group.description, "location": group.location, "device": group.device.name}
            for name, group in sorted(nwbfile.electrode_groups.items())
        }
        out["ogen_sites"] = {
            name: {"description": site.description, "location": site.location, "device": site.device.name,
                   "excitation_lambda": float(site.excitation_lambda)}
            for name, site in sorted(nwbfile.ogen_sites.items())
        }
        if nwbfile.epochs is not None:
            frame = nwbfile.epochs.to_dataframe()
            out["epochs"] = json.loads(frame.reset_index(drop=True).to_json(orient="records"))
        else:
            out["epochs"] = []
        out["acquisition"] = sorted(nwbfile.acquisition)
        out["stimulus"] = sorted(nwbfile.stimulus)
        out["processing"] = sorted(nwbfile.processing)
        out["has_electrodes_table"] = nwbfile.electrodes is not None
        brainstem = nwbfile.lab_meta_data.get("brainstem") if nwbfile.lab_meta_data else None
        if brainstem is not None:
            out["brainstem"] = {
                "unit_id": getattr(brainstem, "unit_id", None),
                "tables": {name: [str(v) for v in table["brainstem_id"][:]]
                           for name, table in sorted(brainstem.brainstem_tables.items())},
            }
        else:
            out["brainstem"] = None
    return out


def provenance_from_notes(notes: str | None) -> dict[str, Any] | None:
    """Parse the provenance block the writer appends to NWBFile.notes; None when absent or invalid."""
    if not notes or PROVENANCE_HEADER not in notes:
        return None
    try:
        return json.loads(notes.split(PROVENANCE_HEADER, 1)[1].strip())
    except json.JSONDecodeError:
        return None
