"""The data model is read from the BrainSTEM server at run time and cached; planned records are not exported."""

import json
import os

import pytest

from brainstem_nwb import build_manifest
from brainstem_nwb.normalize.units import plan_units
from brainstem_nwb.store import datamodel
from brainstem_nwb.store.datamodel import DataModelUnavailable, inventory_data, load_documents
from brainstem_nwb.store.inventory import Inventory, get_inventory

from .conftest import by_code, load, mapped_units, scenario_file

DOCUMENTS = {
    "manifest.json": {"data_model": "specimen-1", "export_format_version": "2.1", "server_commit": "",
                      "license": {"url": "https://example.org/reference/license.md"}},
    "datamodel_graph.json": {
        "nodes": [
            {"id": "modules.procedure", "fields": [
                {"name": "id", "kind": "char"}, {"name": "subject", "kind": "fk", "target": "stem.subject"},
                {"name": "interfaces", "kind": "m2m", "target": "modules.experimentalinterface"},
                {"name": "copied_from", "kind": "self", "target": None}, {"name": "tags", "kind": "tags"},
                {"name": "notes", "kind": "char"}]},
            {"id": "modules.subjectlog", "fields": [{"name": "log", "kind": "generic"}]},
        ],
        "edges": [{"source": "modules.procedure", "source_field": "interfaces", "kind": "m2m",
                   "target": "modules.experimentalinterface", "through": "ProcedureInterface"}],
    },
    "api_surface.json": {"resources": [
        {"model": "modules.procedure", "fields": [{"name": "notes", "kind": "string", "nullable": True}]},
        {"model": "stem.cohortsubject", "fields": [
            {"name": "id", "kind": "number"}, {"name": "cohort", "kind": "relation", "target": "stem.cohort"},
            {"name": "subject_name", "kind": "computed"}, {"name": "order", "kind": "number", "nullable": True}]},
    ]},
    "schemas.json": {"families": [{"family": "Procedure", "types": [
        {"type": "Craniotomy", "label": "Craniotomy", "group": "Surgical Procedures"}]}]},
}


def test_documents_become_the_inventory():
    data = inventory_data(DOCUMENTS)
    inventory = Inventory(data)
    assert (inventory.data_model, inventory.export_format_version, inventory.server_commit) == ("specimen-1", "2.1",
                                                                                                None)
    procedure = inventory.fields("modules.procedure")
    assert "id" not in procedure and procedure["notes"]["null"] is True
    assert inventory.relation("modules.procedure", "interfaces").through == "modules.procedureinterface"
    assert inventory.relation("modules.procedure", "copied_from").target == "modules.procedure"
    assert procedure["tags"]["kind"] == "tags"
    # A generic link is exported as content_type and object_id
    assert inventory.relation("modules.subjectlog", "content_type").target == "contenttypes.contenttype"
    assert "object_id" in inventory.fields("modules.subjectlog")
    # Link tables: from the REST resources, else the built-in description
    assert inventory.relation("stem.cohortsubject", "cohort").target == "stem.cohort"
    assert "subject_name" not in inventory.fields("stem.cohortsubject")
    assert inventory.relation("modules.procedureinterface", "interface").target == "modules.experimentalinterface"
    assert inventory.type_group("Procedure", "Craniotomy") == "Surgical Procedures"
    assert inventory_data(DOCUMENTS)["sha256"] == data["sha256"]


class FakeServer:
    def __init__(self):
        self.requests: list[tuple[str, dict]] = []
        self.down = False

    def get(self, url, headers=None, timeout=None):
        if self.down:
            import requests

            raise requests.ConnectionError("server down")
        self.requests.append((url, dict(headers or {})))
        name = url.rsplit("/", 1)[-1]
        etag = f'"{name}-1"'
        if (headers or {}).get("If-None-Match") == etag:
            return FakeResponse(304, None, etag)
        return FakeResponse(200, DOCUMENTS[name], etag)


class FakeResponse:
    def __init__(self, status_code, payload, etag):
        self.status_code, self._payload, self.headers = status_code, payload, {"ETag": etag}

    def json(self):
        return self._payload


def test_cache_refresh_and_offline_use(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINSTEM_NWB_CACHE", str(tmp_path))
    monkeypatch.delenv("BRAINSTEM_NWB_DATA_MODEL", raising=False)
    server = FakeServer()
    first = load_documents("https://bs.example.org", session=server)
    assert first.origin == "fetched" and len(server.requests) == 4
    assert server.requests[0][0] == "https://bs.example.org/reference/data/manifest.json"
    assert first.documents == DOCUMENTS
    assert load_documents("https://bs.example.org", session=server).origin == "cache"
    assert len(server.requests) == 4  # fresh cache: no request
    # An hour later: conditional requests, answered with 304
    meta_path = datamodel.cache_dir("https://bs.example.org") / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["fetched"] -= datamodel.MAX_AGE + 1
    meta_path.write_text(json.dumps(meta))
    again = load_documents("https://bs.example.org", session=server)
    assert again.origin == "fetched" and again.documents == DOCUMENTS
    assert all(headers.get("If-None-Match") for _url, headers in server.requests[4:])
    # Server down: the stale copy, with the reason
    meta = json.loads(meta_path.read_text())
    meta["fetched"] -= datamodel.MAX_AGE + 1
    meta_path.write_text(json.dumps(meta))
    server.down = True
    stale = load_documents("https://bs.example.org", session=server)
    assert stale.origin == "stale_cache" and "server down" in stale.error
    # No cache and no server
    with pytest.raises(DataModelUnavailable, match="reads it from the server at run time"):
        load_documents("https://other.example.org", session=server)


def test_documents_from_a_directory(tmp_path, monkeypatch):
    for name, document in DOCUMENTS.items():
        (tmp_path / name).write_text(json.dumps(document))
    monkeypatch.setenv("BRAINSTEM_NWB_DATA_MODEL", str(tmp_path))
    assert load_documents(None).origin == "directory"
    os.remove(tmp_path / "schemas.json")
    with pytest.raises(DataModelUnavailable, match=r"lacks schemas\.json"):
        load_documents(None)


def test_manifest_names_the_data_model():
    manifest = build_manifest(scenario_file("ephys"))
    inventory = get_inventory()
    info = manifest.data_model
    assert (info.data_model, info.export_format_version, info.sha256) == (
        inventory.data_model, inventory.export_format_version, inventory.sha256)
    assert info.server == "https://www.brainstem.org/" and info.license_url.endswith("/reference/license.md")
    assert not {"DATA_MODEL_CACHED", "DATA_MODEL_UNSUPPORTED"} & set(by_code(manifest.warnings))


def test_planned_sessions_are_not_exported():
    _, store = load("multisession")
    units, errors = plan_units(store)
    assert "SM05_day3" not in {u.session.get("name") for u in units} | {e.session.get("name") for e in errors}
    manifest = build_manifest(scenario_file("multisession"))
    (warning,) = by_code(manifest.warnings)["SESSION_NOT_PERFORMED"]
    assert "SM05_day3" in warning.message
    units, errors = plan_units(store, sessions=["SM05_day3"])
    assert units == [] and [e.code for e in errors] == ["SESSION_NOT_PERFORMED"]


def test_planned_and_cancelled_procedures_stay_out_of_the_file():
    (unit,), _ = mapped_units("ephys")
    assert "Analgesic" not in (unit.nwb.nwbfile.surgery or "") and "Silicon probe" in unit.nwb.nwbfile.surgery
    roles = {entry.pk: entry.roles for entry in unit.records if entry.label == "modules.procedure"}
    assert ["procedure_not_performed"] in roles.values()
    assert "PROCEDURE_NOT_PERFORMED" in by_code(unit.warnings)
    (specimen_unit,), _ = mapped_units("exvivo_specimen")
    slices = specimen_unit.nwb.nwbfile.slices
    assert "sectioning" in slices and "staining" not in slices
