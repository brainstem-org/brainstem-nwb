"""--extension brainstem: the ndx-brainstem tables (needs the ndx-brainstem package: the "extensions" extra)."""

import json

import pytest

from brainstem_nwb import export_project
from brainstem_nwb.mapping.extension import ADMINISTRATIVE, LEFT_OUT_ROLES, TABLE_ORDER, TABLES

from .conftest import mapped_units, scenario_file

ndx_brainstem = pytest.importorskip("ndx_brainstem")


@pytest.fixture(scope="module")
def plan():
    (unit,), _ = mapped_units("ephys", extensions=["brainstem"])
    return unit


def tables(unit):
    return {t.name: t for t in unit.nwb.brainstem.tables}


def test_every_included_record_is_a_row(plan):
    rows = {(row["brainstem_model"], row["brainstem_id"]) for t in plan.nwb.brainstem.tables for row in t.rows}
    for entry in plan.records:
        if entry.label in ADMINISTRATIVE or set(entry.roles) <= LEFT_OUT_ROLES:
            assert (entry.label, entry.pk) not in rows, entry.label
        elif entry.label in {label for _n, _d, labels in TABLES for label in labels}:
            if entry.label in ("modules.moduleslogentry",) and entry.fields["date_time"] > "2024-04-01T10":
                assert (entry.label, entry.pk) not in rows  # after the session
            else:
                assert (entry.label, entry.pk) in rows, (entry.label, entry.pk)


def test_links_point_only_to_earlier_tables(plan):
    for table in plan.nwb.brainstem.tables:
        for column in table.columns:
            if column.link_table and column.link_table != "/intervals/epochs":
                assert TABLE_ORDER[column.link_table] < TABLE_ORDER[table.name], (table.name, column.name)


def test_values_and_links(plan):
    t = tables(plan)
    procedures = t["procedures"]
    virus = next(r for r in procedures.rows if r["type"] == "VirusInjection")
    assert json.loads(virus["type_json"])["route"] == "intraparenchymal"
    regions = t["regions"].rows
    assert [regions[i]["acronym"] for i in virus["target_regions"]] == ["CA1"]
    assert virus["date_time_iso"] == "2024-03-01T10:00:00Z"
    stock = next(r for r in t["lab_resources"].rows if r["brainstem_model"] == "modules.consumablestock")
    assert "B-17" in stock["type_json"] and "cost" not in stock
    assert {r["brainstem_model"] for r in t["people"].rows} == {"users.user"}
    interface = t["interfaces"].rows[0]
    assert interface["nwb_device"] == "Probe A"


def test_administrative_resources_are_left_out(plan):
    text = plan.nwb.brainstem.model_dump_json()
    for value in ("Animal license", "AN-2024-001", "Lab server", "-80 freezer", "SAWB"):
        assert value not in text


def test_written_file_validates(tmp_path):
    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path, extensions=["brainstem"])
    assert result.exit_code == 0
    assert result.report.summary["error"] == 0 and result.report.summary["warning"] == 0
    from pynwb import NWBHDF5IO

    with NWBHDF5IO(str(result.files[0]), "r") as io:
        metadata = io.read().lab_meta_data["brainstem"]
        assert metadata.unit_id == result.manifest.units[0].unit_id
        for table in metadata.brainstem_tables.values():
            table.to_dataframe()  # no recursion: links only point to earlier tables


@pytest.mark.parametrize("name", ["optogenetics", "exvivo_specimen", "multisubject", "session_export"])
def test_other_scenarios(tmp_path, name):
    result = export_project(export_file=scenario_file(name), output_dir=tmp_path, extensions=["brainstem"])
    assert result.exit_code == 0 and result.report.summary["error"] == 0


def test_identifier_changes_with_extension():
    (plain,), _ = mapped_units("ephys")
    (extended,), _ = mapped_units("ephys", extensions=["brainstem"])
    assert plain.nwb.nwbfile.identifier != extended.nwb.nwbfile.identifier


def test_localization(tmp_path):
    pytest.importorskip("ndx_anatomical_localization")
    (unit,), _ = mapped_units("optogenetics", extensions=["brainstem"])
    plan = unit.nwb.localization
    assert unit.nwb.brainstem is not None
    (alias,), _ = mapped_units("optogenetics", extensions=["localization"])
    assert alias.nwb.model_dump() == unit.nwb.model_dump()  # 'localization' is the same option
    tables = {t.name: t for t in plan.tables}
    assert set(tables) == {"procedures_Stereotaxic_BregmaAbsolute", "interfaces_AllenCCFv3"}
    stereo = tables["procedures_Stereotaxic_BregmaAbsolute"]
    assert sorted((r.x, r.y, r.z) for r in stereo.rows) == [(-1.4, 1.1, 0.8), (1.4, 1.1, 0.8)]
    assert {r.brain_region for r in stereo.rows} == {"MOp"}
    (ccf,) = tables["interfaces_AllenCCFv3"].rows
    assert (ccf.x, ccf.y, ccf.z) == (3500.0, 1800.0, 6900.0)  # mm -> um
    codes = {w.code for w in unit.warnings}
    assert "LOCALIZATION_INCOMPLETE" in codes  # fiberC's implant has no DV

    result = export_project(export_file=scenario_file("optogenetics"), output_dir=tmp_path,
                            extensions=["brainstem"])
    assert result.exit_code == 0 and result.report.summary["error"] == 0
    from pynwb import NWBHDF5IO

    with NWBHDF5IO(str(result.files[0]), "r") as io:
        localization = io.read().lab_meta_data["localization"]
        table = localization.anatomical_coordinates_tables["interfaces_AllenCCFv3"]
        assert table["localized_entity"][0]["nwb_device"].tolist() == ["fiberA"]
        assert localization.spaces["AllenCCFv3"].orientation == "PIR"


def test_brain_surface_coordinates_are_not_localized():
    (unit,), _ = mapped_units("ephys", extensions=["brainstem"])
    assert unit.nwb.localization is None
    assert "LOCALIZATION_NOT_SUPPORTED" in {w.code for w in unit.warnings}


def test_herd_terms(tmp_path):
    (unit,), _ = mapped_units("ephys", herd=True)
    terms = {(r.target, r.target_name, r.attribute, r.key): r.entity_id for r in unit.nwb.herd}
    assert terms[("subject", None, "species", "Mus musculus")] == "NCBITaxon:10090"
    assert terms[("subject", None, "strain", "C57BL/6J")] == "RRID:IMSR_JAX:000664"
    assert terms[("electrode_group", "Probe A_shank1", "location", "CA1")] == "Allen:382"
    assert terms[("device_model", "RHD2164 headstage", "model_number", "C3314")] == "RRID:SCR_019318"

    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path, herd=True)
    assert result.exit_code == 0
    output = result.manifest.units[0].output
    herd_file = tmp_path / output.herd_relative_path
    assert herd_file.name.endswith(".herd.zip") and herd_file.exists()
    import zipfile

    from pynwb import NWBHDF5IO

    assert sorted(zipfile.ZipFile(herd_file).namelist()) == sorted(
        ["entities.tsv", "entity_keys.tsv", "files.tsv", "keys.tsv", "object_keys.tsv", "objects.tsv"])
    with NWBHDF5IO(str(result.files[0]), "r", herd_path=str(herd_file)) as io:
        frame = io.read().get_external_resources().to_dataframe()
        assert {"NCBITaxon:10090", "RRID:IMSR_JAX:000664", "Allen:382"} <= set(frame["entity_id"])


def test_schema_ids_and_urls(plan):
    t = tables(plan)
    virus = next(r for r in t["procedures"].rows if r["type"] == "VirusInjection")
    assert virus["details_schema"] == "Procedure/VirusInjection"  # the fixture stores no version
    assert virus["coordinates_schema"] == "Coordinates/Stereotaxic_BregmaBrainSurface"
    entry = t["log_entries"].rows[0]
    assert entry["details_schema"] == "SubjectLog/Weighing@1.1.1"
    schemas = {s["schema_id"]: s for s in plan.nwb.brainstem.schemas}
    assert schemas["SubjectLog/Weighing@1.1.1"]["schema_url"] == \
        "https://www.brainstem.org/schemas/SubjectLog/Weighing/1.1.1.json"
    # no stored version: the URL lists the type's versions instead of naming one
    assert schemas["Procedure/VirusInjection"]["schema_url"] == \
        "https://www.brainstem.org/schemas/Procedure/VirusInjection/"
    assert all(s["schema_json"] == "" for s in schemas.values())  # nothing embedded without --embed-schemas


def test_embed_schemas(tmp_path, monkeypatch):
    from brainstem_nwb.retrieval import schemas as schema_service

    requested = []

    def fake_fetch(refs, server=None, session=None):
        requested.extend(ref.id for ref in refs)
        found = {ref.id: {"$id": ref.url(), "schemaVersion": ref.version} for ref in refs
                 if ref.version and ref.id != "SubjectLog/Weighing@9.9.9"}
        return found, []

    monkeypatch.setattr(schema_service, "fetch_schemas", fake_fetch)
    from brainstem_nwb import export as export_module
    from brainstem_nwb.store.inventory import get_inventory

    monkeypatch.setattr(export_module, "get_inventory", lambda server=None: get_inventory())  # no data model there
    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path, extensions=["brainstem"],
                            embed_schemas=True, url="http://127.0.0.1:8000/")
    assert result.exit_code == 0
    assert result.report.summary["warning"] == 0  # JSON schema text is an expected finding
    info = result.manifest.schemas
    assert info.origin == "fetched" and info.base_url == "http://127.0.0.1:8000/schemas/"
    assert "SubjectLog/Weighing@1.1.1" in requested
    from pynwb import NWBHDF5IO

    with NWBHDF5IO(str(result.files[0]), "r") as io:
        schemas = io.read().lab_meta_data["brainstem"].schemas.to_dataframe().set_index("schema_id")
        assert json.loads(schemas.loc["SubjectLog/Weighing@1.1.1", "schema_json"])["schemaVersion"] == "1.1.1"
        assert schemas.loc["Procedure/VirusInjection", "schema_json"] == ""  # unversioned: not fetched
        description = io.read().lab_meta_data["brainstem"].schemas.description
        assert "All rights reserved" in description and description.endswith("/reference/license.md")


def test_fetch_never_substitutes_versions():
    from brainstem_nwb.normalize.schemas import SchemaRef
    from brainstem_nwb.retrieval.schemas import fetch_schemas

    class Response:
        def __init__(self, status, payload):
            self.status_code, self._payload = status, payload

        def json(self):
            return self._payload

    class Session:
        def get(self, url, **kwargs):
            if url.endswith("/Procedure/VirusInjection/3.0.0.json"):
                return Response(200, {"schemaVersion": "3.0.0"})
            if url.endswith("/Procedure/VirusInjection/2.0.0.json"):
                return Response(200, {"schemaVersion": "3.0.0"})  # wrong version served
            return Response(404, {})

    refs = [SchemaRef("Procedure", "VirusInjection", "3.0.0"), SchemaRef("Procedure", "VirusInjection", "2.0.0"),
            SchemaRef("Procedure", "Gone", "1.0.0"), SchemaRef("Procedure", "VirusInjection", "")]
    found, missing = fetch_schemas(refs, "http://example.org", session=Session())
    assert list(found) == ["Procedure/VirusInjection@3.0.0"]
    assert missing == ["Procedure/Gone@1.0.0", "Procedure/VirusInjection@2.0.0"]
