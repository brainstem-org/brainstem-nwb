import copy
import gzip
import io
import json

import pytest

from brainstem_nwb.errors import ExportFormatError
from brainstem_nwb.retrieval.loader import is_newer_minor, load_export
from brainstem_nwb.store.graph import RecordStore
from brainstem_nwb.store.inventory import get_inventory

from .conftest import EXPORTS, scenario
from .fixtures.scenarios import DANGLING_REGION, REGION_CA1, SCENARIOS


class TestLoader:
    def test_json_gzip_stream_and_dict_agree(self, tmp_path):
        payload = scenario("ephys")
        raw = json.dumps(payload).encode()
        (tmp_path / "e.json").write_bytes(raw)
        (tmp_path / "e.json.gz").write_bytes(gzip.compress(raw))
        (tmp_path / "gz-without-suffix").write_bytes(gzip.compress(raw))
        from_file = load_export(tmp_path / "e.json")
        from_gz = load_export(tmp_path / "e.json.gz")
        assert from_file.sha256 == from_gz.sha256 == load_export(tmp_path / "gz-without-suffix").sha256
        assert load_export(io.BytesIO(raw)).sha256 == from_file.sha256
        assert from_file.source.kind == "file" and from_file.source.name == "e.json"
        assert load_export(payload).records.keys() == from_file.records.keys()
        assert from_file.project_id == payload["export_info"]["project_id"]

    def test_dict_digest_is_stable(self):
        assert load_export(scenario("ephys")).sha256 == load_export(scenario("ephys")).sha256

    @pytest.mark.parametrize("payload, match", [
        ({"records": {}}, "not a BrainSTEM project export"),
        ({"subjects": []}, "not a BrainSTEM project export"),
        ({"export_info": {"format_version": "1.3"}, "records": {}}, "not supported"),
        ({"export_info": {"format_version": "3.0"}, "records": {}}, "not supported"),
        ({"export_info": {}, "records": {}}, "format_version"),
        ({"export_info": {"format_version": "2.0"}, "records": {"stem.session": {}}}, "not a list"),
        ({"export_info": {"format_version": "2.0"}, "records": {"stem.session": [{"pk": 1}]}}, "malformed record"),
    ])
    def test_rejects(self, payload, match):
        with pytest.raises(ExportFormatError, match=match):
            load_export(payload)

    def test_bad_bytes(self, tmp_path):
        (tmp_path / "x.json").write_text("{not json")
        with pytest.raises(ExportFormatError, match="not valid JSON"):
            load_export(tmp_path / "x.json")
        with pytest.raises(ExportFormatError, match="cannot read"):
            load_export(tmp_path / "missing.json")

    def test_newer_minor(self):
        assert is_newer_minor(load_export(scenario("edge_cases")))
        assert not is_newer_minor(load_export(scenario("ephys")))


def test_committed_fixtures_match_scenarios():
    """tests/fixtures/exports/ must be regenerated (tests/fixtures/regen.py) when scenarios change."""
    for name, build in SCENARIOS.items():
        committed = json.loads((EXPORTS / f"{name}.json").read_text(encoding="utf-8"))
        assert committed == build(), f"{name}.json is stale; run python tests/fixtures/regen.py"


class TestStore:
    def setup_method(self):
        self.store = RecordStore(load_export(scenario("ephys")))

    def test_every_inventory_relation_target_is_a_known_label_or_external(self):
        inventory = get_inventory()
        for (label, field), relation in inventory.relations.items():
            if label in inventory.export_labels:
                assert relation.target and relation.target.count(".") == 1, (label, field)

    def test_fk_and_m2m(self):
        session = self.store.all("stem.session")[0]
        subjects = self.store.m2m(session, "subjects")
        assert [ref.reason for ref in subjects] == ["ok"]
        subject = subjects[0].record
        species = self.store.fk_record(subject, "species")
        assert species.get("name") == "Mus musculus"
        assert self.store.fk(subject, "breeding") is None

    def test_catalog_references_resolve(self):
        procedure = next(p for p in self.store.all("modules.procedure") if p.get("type") == "VirusInjection")
        (region,) = self.store.m2m(procedure, "target_regions")
        assert region.ok and region.pk == REGION_CA1 and region.record.get("acronym") == "CA1"
        assert self.store.external_refs() == {}

    def test_reference_outside_export(self):
        store = RecordStore(load_export(scenario("edge_cases")))
        procedure = next(p for p in store.all("modules.procedure") if p.get("type") == "Craniotomy")
        (region,) = store.m2m(procedure, "target_regions")
        assert region.reason == "not_in_export" and region.pk == DANGLING_REGION and not region.ok
        assert store.external_refs()["taxonomies.anatomicalregion"] == (1, 0)

    def test_restricted_lab_resources_resolve_to_names(self):
        store = RecordStore(load_export(scenario("behavior")))
        acquisition = store.all("modules.dataacquisition")[0]
        refs = {ref.reason: ref for ref in store.m2m(acquisition, "equipment")}
        assert refs["restricted"].name == "Sync box (other lab)" and refs["restricted"].record is None
        assert refs["ok"].record.get("name") == "Maze camera"

    def test_log_entries(self):
        (log,) = self.store.all("modules.subjectlog")
        entries = self.store.log_entries(log)
        assert [e.get("type_json")["weight"]["value"] for e in entries] == [24.1, 25.3, 26.0]

    def test_session_scope(self):
        export = load_export(scenario("session_export"))
        assert export.scope == "session" and export.session_id and export.project_id is None
        assert len(export.project_ids) == 2

    def test_referrers(self):
        session = self.store.all("stem.session")[0]
        acquisitions = self.store.referrers(session, "modules.dataacquisition", "session")
        assert {a.get("type") for a in acquisitions} == {"ExtracellularEphys", "BehavioralTracking"}

    def test_wrong_field_kind_raises(self):
        session = self.store.all("stem.session")[0]
        with pytest.raises(KeyError):
            self.store.fk(session, "subjects")
        with pytest.raises(KeyError):
            self.store.m2m(session, "name")

    def test_unknown_labels_are_kept(self):
        payload = copy.deepcopy(scenario("edge_cases"))
        store = RecordStore(load_export(payload))
        assert store.get("stem.futurething", "f-1") is not None
