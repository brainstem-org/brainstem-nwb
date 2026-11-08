"""
The exporter reads what the BrainSTEM server really writes.

server_contract_<version>.json (project export) and server_contract_<version>_session.json (session
export of a session in two projects) were produced by the server's own ``build_project_export`` from a
small synthetic project (scripts/make_contract_export.py), so their value encodings, link lists and
labels are the server's, not our test builder's. 2.2 is what the server writes now; 2.1 files have the
same structure and must keep working.
"""

import json

import pytest

from brainstem_nwb import export_project
from brainstem_nwb.nwb.canonical import canonical_summary
from brainstem_nwb.retrieval.loader import load_export
from brainstem_nwb.store.graph import RecordStore
from brainstem_nwb.store.inventory import get_inventory

from .conftest import EXPORTS
from .fixtures.builder import EXPORTED_USER_FIELDS, INTERNAL_FIELDS

VERSIONS = ["2_1", "2_2"]
CONTRACTS = [(EXPORTS / f"server_contract_{v}.json", EXPORTS / f"server_contract_{v}_session.json") for v in VERSIONS]


@pytest.fixture(scope="module", params=[path for pair in CONTRACTS for path in pair],
                ids=[f"{v}-{scope}" for v in VERSIONS for scope in ("project", "session")])
def contract(request):
    return load_export(request.param)


TIMESTAMPS = {"created_at", "updated_at"}  # the reference documents leave them out of some link tables


def test_labels_and_fields_match_the_server_data_model(contract):
    inventory = get_inventory()
    assert set(contract.records) == set(inventory.export_labels)
    for label, records in contract.records.items():
        expected = set(inventory.fields(label)) - set(INTERNAL_FIELDS) - TIMESTAMPS
        if label == "users.user":
            expected = set(EXPORTED_USER_FIELDS)
        for record in records:
            assert set(record["fields"]) - TIMESTAMPS == expected, label


def test_no_personal_data_beyond_names():
    for path in (path for pair in CONTRACTS for path in pair):
        text = path.read_text(encoding="utf-8")
        assert "@" not in text
        for user in json.loads(text)["records"]["users.user"]:
            assert set(user["fields"]) == {"first_name", "last_name"}


def test_server_encodings(contract):
    store = RecordStore(contract)
    session = store.all("stem.session")[0]
    assert session.get("date_time") == "2024-04-01T10:00:00.123Z"
    epochs = {e.get("name"): (e.get("start"), e.get("end")) for e in store.all("stem.epoch")}
    assert epochs == {"run": ("00:00:00", "00:30:00.500000"), "late": ("1 02:00:00", "1 03:00:00")}
    # Procedure-interface links carry their relationship (when the server created one for the implant)
    assert all(link.get("relationship") for link in store.all("modules.procedureinterface"))
    # Log entries name their log by model label
    (log,) = store.all("modules.subjectlog")
    (entry,) = store.log_entries(log)
    assert entry.get("content_type") == "modules.subjectlog"
    # Only the session's other project (not part of a project export) may point outside the file
    assert set(store.external_refs()) <= {"stem.project"}


@pytest.mark.parametrize("pair", CONTRACTS, ids=VERSIONS)
def test_scope_keys(pair):
    project, session = load_export(pair[0]), load_export(pair[1])
    assert (project.scope, project.session_id, len(project.project_ids)) == ("project", None, 1)
    assert project.project_ids == [project.project_id]
    assert (session.scope, session.project_id, len(session.project_ids)) == ("session", None, 2)
    assert session.session_id == RecordStore(session).all("stem.session")[0].pk


def test_contract_exports_cleanly(tmp_path, contract):
    result = export_project(export=contract, output_dir=tmp_path)
    assert result.exit_code == 0, [w.message for u in result.manifest.units for w in u.warnings]
    assert not any(w.code == "EXPORT_MINOR_NEWER" for w in result.manifest.warnings)
    (unit,) = result.manifest.units
    assert unit.status == "written"
    summary = canonical_summary(result.files[0])
    assert [(e["tags"], e["start_time"], e["stop_time"]) for e in summary["epochs"]] == [
        (["run"], 0.0, 1800.5), (["late"], 93600.0, 97200.0)]
    assert summary["session_start_time"] == "2024-04-01T10:00:00.123000+00:00"
    assert summary["subject"]["age"] == "P90D" and summary["subject"]["weight"] == "25.3 g"
    (probe,) = RecordStore(contract).all("modules.experimentalinterface")
    (group,) = summary["electrode_groups"].values()
    assert group["device"] == probe.get("name") and group["location"] == "CA1"
    assert "Electrical stimulation" in summary["stimulus_notes"]
    assert summary["related_publications"] == ["doi:10.0000/contract.1"]
    assert "performed by Contract Export" in summary["surgery"]
    assert result.report.summary["error"] == 0
    if contract.scope == "session":
        assert "Contract project B" in summary["experiment_description"]
