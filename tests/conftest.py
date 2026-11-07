from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import pytest

from brainstem_nwb.config import ExportOptions
from brainstem_nwb.mapping.pipeline import map_unit
from brainstem_nwb.normalize.units import plan_units
from brainstem_nwb.retrieval.loader import ProjectExport, load_export
from brainstem_nwb.store.graph import RecordStore

from .fixtures.scenarios import SCENARIOS

EXPORTS = Path(__file__).parent / "fixtures" / "exports"


@pytest.fixture(autouse=True)
def _quiet_hdmf_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


def scenario(name: str) -> dict[str, Any]:
    return SCENARIOS[name]()


def scenario_file(name: str) -> Path:
    return EXPORTS / f"{name}.json"


def load(name: str) -> tuple[ProjectExport, RecordStore]:
    export = load_export(scenario(name))
    return export, RecordStore(export)


def mapped_units(name: str, **options: Any):
    export, store = load(name)
    opts = ExportOptions(**options)
    units, errors = plan_units(store, allow_no_subject=opts.allow_no_subject, infer_subjects=opts.infer_subjects,
                               subject_label_field=opts.subject.label_field, sessions=opts.sessions)
    return [map_unit(store, unit, opts, export) for unit in units], errors


def by_code(warnings_list) -> dict[str, list]:
    out: dict[str, list] = {}
    for warning in warnings_list:
        out.setdefault(warning.code, []).append(warning)
    return out


def mapping_state(unit, rule_id: str, nwb_path: str | None = None) -> list[str]:
    return [m.state for m in unit.mappings if m.rule_id == rule_id and (nwb_path is None or m.nwb_path == nwb_path)]


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def pytest_sessionstart(session):
    """The tests run against the data model the BrainSTEM server publishes; read it once, or stop clearly."""
    from brainstem_nwb.store.datamodel import DataModelUnavailable
    from brainstem_nwb.store.inventory import get_inventory

    try:
        get_inventory()
    except DataModelUnavailable as exc:
        pytest.exit(f"the tests need the BrainSTEM data model: {exc}", returncode=3)
