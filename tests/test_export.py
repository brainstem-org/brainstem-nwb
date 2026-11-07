import copy
import json
import re

import pytest

from brainstem_nwb import build_manifest, export_project, export_session, validate_output
from brainstem_nwb.errors import ConfigError
from brainstem_nwb.manifest.io import MANIFEST_FILENAME, manifest_to_json, read_manifest
from brainstem_nwb.manifest.schema import manifest_schema
from brainstem_nwb.nwb.canonical import canonical_summary

from .conftest import scenario, scenario_file


def test_export_writes_files_manifest_and_reports(tmp_path):
    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path)
    assert result.exit_code == 0
    assert (tmp_path / MANIFEST_FILENAME).exists()
    assert (tmp_path / "validation-report.json").exists() and (tmp_path / "validation-report.txt").exists()
    (unit,) = result.manifest.units
    assert unit.status == "written" and unit.output.sha256
    assert (tmp_path / unit.output.relative_path).exists()
    assert result.manifest.summary.written == 1
    assert result.manifest.source.kind == "file" and result.manifest.source.name == "ephys.json"
    assert result.report.summary["error"] == 0


def test_manifest_matches_its_schema_and_round_trips(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    result = export_project(export_file=scenario_file("multisubject"), output_dir=tmp_path)
    data = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    jsonschema.validate(data, manifest_schema())
    assert manifest_to_json(read_manifest(tmp_path / MANIFEST_FILENAME)) == manifest_to_json(result.manifest)


def test_partial_export_exit_code_and_unit_errors(tmp_path):
    result = export_project(export_file=scenario_file("multisession"), output_dir=tmp_path)
    assert result.exit_code == 1
    assert result.manifest.summary.written == 2 and result.manifest.summary.unit_errors == 3
    assert {e.code for e in result.manifest.unit_errors} == {
        "SESSION_START_TIME_MISSING", "NO_SUBJECT", "SUBJECT_NOT_IN_EXPORT"}


def test_validation_error_exit_code(tmp_path):
    result = export_project(export_file=scenario_file("edge_cases"), output_dir=tmp_path)
    assert result.exit_code == 4
    assert any(w.code == "EXPORT_MINOR_NEWER" for w in result.manifest.warnings)
    assert any(w.code == "UNKNOWN_LABEL" for w in result.manifest.warnings)
    assert result.manifest.source.unmapped_labels == ["stem.futurething"]


def test_fail_on_warning(tmp_path):
    clean = export_project(export_file=scenario_file("behavior"), output_dir=tmp_path / "a")
    assert clean.exit_code == 0
    strict = export_project(export_file=scenario_file("behavior"), output_dir=tmp_path / "b", fail_on="warning",
                            config={"nwbfile": {}})
    assert strict.exit_code in (0, 4)  # 4 only when the inspector reports violations
    assert strict.exit_code == (4 if strict.report.has("warning") else 0)


def test_dry_run_writes_only_the_manifest(tmp_path):
    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path, dry_run=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == [MANIFEST_FILENAME]
    assert result.manifest.run.dry_run and result.manifest.units[0].status == "planned"
    assert result.report is None and result.exit_code == 0


def test_build_manifest_equals_dry_run(tmp_path):
    manifest = build_manifest(scenario_file("ephys"), reproducible=True)
    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path, dry_run=True, reproducible=True)
    assert manifest_to_json(manifest) == manifest_to_json(result.manifest)


def test_rerun_is_up_to_date_and_changes_need_overwrite(tmp_path):
    first = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path)
    again = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path)
    assert again.manifest.units[0].status == "up_to_date"
    assert again.manifest.units[0].output.sha256 == first.manifest.units[0].output.sha256
    assert again.exit_code == 0

    payload = copy.deepcopy(scenario("ephys"))
    payload["records"]["stem.session"][0]["fields"]["description"] = "Edited in BrainSTEM"
    changed = export_project(export=payload, output_dir=tmp_path)
    assert changed.manifest.units[0].status == "failed"
    assert changed.manifest.units[0].error.code == "OUTPUT_EXISTS" and changed.exit_code == 1
    replaced = export_project(export=payload, output_dir=tmp_path, overwrite=True)
    assert replaced.manifest.units[0].status == "written" and replaced.exit_code == 0


def test_reproducible_exports(tmp_path):
    a = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path / "a", reproducible=True)
    export_project(export_file=scenario_file("ephys"), output_dir=tmp_path / "b", reproducible=True)

    # Manifests are byte-identical apart from the per-file sha256 (HDF5 object ids are random)
    def manifest_text(run):
        text = (tmp_path / run / MANIFEST_FILENAME).read_text()
        return re.sub(r'"sha256": "[0-9a-f]{64}"', '"sha256": "X"', text)

    assert manifest_text("a") == manifest_text("b")
    path = a.manifest.units[0].output.relative_path
    assert canonical_summary(tmp_path / "a" / path) == canonical_summary(tmp_path / "b" / path)
    assert a.manifest.run.created_at.isoformat().startswith("2025-01-15T12:00:00")


def test_source_date_epoch_makes_runs_reproducible(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path, dry_run=True)
    assert result.manifest.run.reproducible
    assert result.manifest.run.created_at.isoformat() == "2023-11-14T22:13:20+00:00"


def test_one_failing_unit_does_not_stop_the_others(tmp_path, monkeypatch):
    from brainstem_nwb.nwb import writer

    original = writer.build_nwbfile

    def flaky(plan):
        if plan.nwbfile.session_id == "SM05_day1":
            raise RuntimeError("disk on fire")
        return original(plan)

    monkeypatch.setattr(writer, "build_nwbfile", flaky)
    result = export_project(export_file=scenario_file("multisession"), output_dir=tmp_path)
    statuses = {u.session.name: u.status for u in result.manifest.units}
    assert statuses == {"SM05_day1": "failed", "SM05_day2": "written"}
    failed = next(u for u in result.manifest.units if u.status == "failed")
    assert failed.error.exception_type == "RuntimeError" and "disk on fire" in failed.error.message
    assert not list(tmp_path.rglob("*SM05-day1*"))
    assert result.exit_code == 1


def test_fail_fast(tmp_path, monkeypatch):
    from brainstem_nwb.nwb import writer

    monkeypatch.setattr(writer, "build_nwbfile", lambda plan: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        export_project(export_file=scenario_file("multisession"), output_dir=tmp_path, fail_fast=True)


def test_export_session(tmp_path):
    result = export_session("SM05_day2", tmp_path, export_file=scenario_file("multisession"))
    assert [u.session.name for u in result.manifest.units] == ["SM05_day2"]
    assert result.exit_code == 0 and result.manifest.unit_errors == []


def test_project_id_must_match_export(tmp_path):
    with pytest.raises(ConfigError, match="not"):
        export_project("another-project", tmp_path, export_file=scenario_file("ephys"))


def test_needs_a_source(tmp_path):
    with pytest.raises(ConfigError):
        export_project(output_dir=tmp_path)


def test_validate_output_uses_manifest(tmp_path):
    export_project(export_file=scenario_file("multisubject"), output_dir=tmp_path, validate=False)
    assert not (tmp_path / "validation-report.json").exists()
    report = validate_output(tmp_path, report_dir=tmp_path)
    assert report.summary["files"] == 2 and report.summary["error"] == 0
    assert all(f.unit_id for f in report.files)
    assert (tmp_path / "validation-report.txt").exists()


def test_coverage_and_external_refs(tmp_path):
    result = export_project(export_file=scenario_file("ephys"), output_dir=tmp_path, dry_run=True)
    manifest = result.manifest
    assert manifest.external_refs == {}
    project_labels = [label for label in manifest.source.counts if not label.startswith(("taxonomies.", "resources.",
                                                                                    "dissemination.", "users."))]
    assert manifest.coverage.records_total == sum(manifest.source.counts[label] for label in project_labels)
    assert manifest.coverage.records_unreached == {}
    edge = export_project(export_file=scenario_file("edge_cases"), output_dir=tmp_path / "edge", dry_run=True)
    assert edge.manifest.external_refs["taxonomies.anatomicalregion"].resolved == 0


def test_session_export(tmp_path):
    result = export_project(export_file=scenario_file("session_export"), output_dir=tmp_path)
    assert result.exit_code == 0
    manifest = result.manifest
    assert (manifest.source.scope, len(manifest.source.project_ids), manifest.source.project_id) == ("session", 2, None)
    assert len(manifest.projects) == 2
    (unit,) = manifest.units
    f = unit.nwb.nwbfile
    assert f.experiment_description.count(":") == 2 and "Second project (synthetic)" in f.experiment_description
    assert "memory" in f.keywords and "hippocampus" in f.keywords
    assert unit.nwb.provenance["export_scope"] == "session" and len(unit.nwb.provenance["project_ids"]) == 2
    # the project id the user names must be one of the exported projects
    export_project(manifest.source.project_ids[1], tmp_path / "again", export_file=scenario_file("session_export"),
                   dry_run=True)


def test_restricted_resources_reported(tmp_path):
    result = export_project(export_file=scenario_file("behavior"), output_dir=tmp_path, dry_run=True)
    (warning,) = [w for w in result.manifest.warnings if w.code == "RESTRICTED_LAB_RESOURCES"]
    assert "Sync box (other lab)" in warning.message
    assert result.manifest.source.restricted["modules.equipment"][0]["name"] == "Sync box (other lab)"


def test_manifest_has_no_private_data(tmp_path):
    payload = copy.deepcopy(scenario("ephys"))
    export_project(export=payload, output_dir=tmp_path, token=None)
    text = (tmp_path / MANIFEST_FILENAME).read_text()
    assert "@" not in text.replace("@6779271", "")  # no e-mail addresses
    assert str(tmp_path) not in text  # no absolute paths
    for record in json.loads(text)["units"][0]["records"]:
        assert "user" not in record["fields"]
