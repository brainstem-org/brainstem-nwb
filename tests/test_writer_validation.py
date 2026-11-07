import copy

import h5py
import pytest

from brainstem_nwb.nwb.canonical import canonical_summary, provenance_from_notes
from brainstem_nwb.nwb.writer import build_nwbfile, write_nwbfile
from brainstem_nwb.validation import validate_file

from .conftest import mapped_units


@pytest.fixture(scope="module")
def ephys_file(tmp_path_factory):
    (unit,), _ = mapped_units("ephys")
    path = tmp_path_factory.mktemp("w") / "ephys.nwb"
    unit.output.sha256 = write_nwbfile(build_nwbfile(unit.nwb), path)
    return unit, path


def test_file_contents_match_plan(ephys_file):
    unit, path = ephys_file
    summary = canonical_summary(path)
    plan = unit.nwb
    assert summary["identifier"] == plan.nwbfile.identifier
    assert summary["session_id"] == "SM01_2024-04-01"
    assert summary["keywords"] == plan.nwbfile.keywords
    assert summary["surgery"] == plan.nwbfile.surgery and summary["virus"] == plan.nwbfile.virus
    assert summary["subject"]["subject_id"] == "SynthMouse01" and summary["subject"]["age"] == "P90D"
    assert set(summary["devices"]) == {"Intan amplifier", "Overhead camera", "Probe A"}
    assert summary["devices"]["Probe A"]["serial_number"] == "SN-00451"
    assert summary["electrode_groups"]["Probe A_shank1"] == {
        "description": plan.electrode_groups[0].description, "location": "CA1", "device": "Probe A"}
    assert [(e["start_time"], e["stop_time"], e["tags"]) for e in summary["epochs"]] == [
        (0.0, 1800.0, ["exploration"]), (1800.0, 5400.5, ["sleep"])]
    assert summary["was_generated_by"] == [["brainstem-nwb", "0.1.0"]]


def test_metadata_only_files_hold_no_data(ephys_file):
    _, path = ephys_file
    summary = canonical_summary(path)
    assert summary["acquisition"] == [] and summary["stimulus"] == [] and summary["processing"] == []
    assert summary["has_electrodes_table"] is False
    provenance = provenance_from_notes(summary["notes"])
    assert provenance["export_mode"] == "metadata-only"
    assert summary["notes"].startswith("METADATA-ONLY EXPORT")


def test_atomic_write_leaves_no_partial_file(tmp_path):
    (unit,), _ = mapped_units("ephys")
    nwbfile = build_nwbfile(unit.nwb)
    write_nwbfile(nwbfile, tmp_path / "x.nwb")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.nwb"]


def test_validation_clean_file(ephys_file):
    unit, path = ephys_file
    report = validate_file(path, unit=unit)
    errors = [f for f in report.findings if f.severity == "error"]
    assert errors == []
    codes = {f.code for f in report.findings}
    assert codes <= {"check_experimenter_exists", "check_institution"}
    assert all(f.severity == "info" for f in report.findings)


def test_expected_inspector_finding_is_downgraded(tmp_path):
    (unit,), _ = mapped_units("optogenetics")
    path = tmp_path / "opto.nwb"
    write_nwbfile(build_nwbfile(unit.nwb), path)
    report = validate_file(path, unit=unit)
    (finding,) = [f for f in report.findings if f.code == "check_optogenetic_stimulus_site_has_optogenetic_series"]
    assert finding.severity == "info" and finding.expected and "metadata-only" in finding.expected_reason


def test_missing_age_is_a_validation_error(tmp_path):
    (unit,), _ = mapped_units("edge_cases")
    path = tmp_path / "edge.nwb"
    write_nwbfile(build_nwbfile(unit.nwb), path)
    report = validate_file(path, unit=unit)
    critical = [f for f in report.findings if f.importance == "CRITICAL"]
    assert [f.code for f in critical] == ["check_subject_age"]
    assert critical[0].severity == "error" and not critical[0].expected
    assert any(f.code == "DANDI_SUBJECT_AGE_MISSING" for f in report.findings)


def test_semantic_checks_catch_tampering(ephys_file, tmp_path):
    unit, path = ephys_file
    other = copy.deepcopy(unit)
    other.output.nwb_identifier = "something-else"
    other.nwb.epochs.rows = other.nwb.epochs.rows[:1]
    codes = {f.code for f in validate_file(path, unit=other).findings if f.origin == "brainstem"}
    assert {"IDENTIFIER_MISMATCH", "EPOCH_COUNT_MISMATCH"} <= codes

    copied = tmp_path / "copy.nwb"
    copied.write_bytes(path.read_bytes())
    with h5py.File(copied, "a") as handle:
        del handle["general/notes"]
        handle["general"].create_dataset("notes", data="tampered")
    findings = validate_file(copied, unit=unit).findings
    codes = {f.code for f in findings if f.origin == "brainstem"}
    assert {"PROVENANCE_MISSING", "CHECKSUM_MISMATCH"} <= codes


def test_unreadable_file(tmp_path):
    bad = tmp_path / "bad.nwb"
    bad.write_bytes(b"not hdf5")
    report = validate_file(bad)
    assert [f.code for f in report.findings] == ["UNREADABLE"] and report.findings[0].severity == "error"


def test_device_models_are_written(ephys_file):
    """Devices link to DeviceModels carrying the supplier as manufacturer (export format 2.1)."""
    from pynwb import NWBHDF5IO

    _, path = ephys_file
    with NWBHDF5IO(str(path), "r") as io:
        nwbfile = io.read()
        amplifier = nwbfile.devices["Intan amplifier"]
        assert amplifier.model.manufacturer == "Intan Technologies" and amplifier.model.model_number == "C3314"
        assert nwbfile.devices["Probe A"].model.manufacturer == "Cambridge NeuroTech"
