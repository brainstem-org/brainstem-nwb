"""End-to-end exports of the representative workflows, validated with the DANDI configuration."""

import subprocess
import sys
from pathlib import Path

import pytest

from brainstem_nwb import export_project
from brainstem_nwb.nwb.canonical import canonical_summary

from ..conftest import scenario_file

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name, n_files, expect", [
    ("ephys", 1, {"electrode_groups": 2, "ogen_sites": 0, "epochs": 2}),
    ("behavior", 1, {"electrode_groups": 0, "ogen_sites": 0, "epochs": 1}),
    ("optogenetics", 1, {"electrode_groups": 0, "ogen_sites": 1, "epochs": 0}),
    ("exvivo_specimen", 1, {"electrode_groups": 0, "ogen_sites": 0, "epochs": 0}),
    ("multisubject", 2, None),
])
def test_workflow_exports_validate_cleanly(tmp_path, name, n_files, expect):
    result = export_project(export_file=scenario_file(name), output_dir=tmp_path, inspector_config="dandi")
    assert result.exit_code == 0
    assert len(result.files) == n_files
    assert result.report.summary["error"] == 0
    assert all(f.severity == "info" for file in result.report.files for f in file.findings), \
        [f for file in result.report.files for f in file.findings if f.severity != "info"]
    if expect:
        summary = canonical_summary(result.files[0])
        assert len(summary["electrode_groups"]) == expect["electrode_groups"]
        assert len(summary["ogen_sites"]) == expect["ogen_sites"]
        assert len(summary["epochs"]) == expect["epochs"]
        assert summary["acquisition"] == []


def test_example_runs_as_documented(tmp_path):
    example = ROOT / "examples" / "synthetic-ephys"
    command = [sys.executable, "-m", "brainstem_nwb.cli", "export", "--export-file",
               str(example / "brainstem-export.json"), "--config", str(example / "brainstem-nwb.toml"),
               "-o", str(tmp_path), "--reproducible"]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (tmp_path / "sub-SynthMouse01" / "sub-SynthMouse01_ses-SM01-2024-04-01.nwb").exists()
    report = (tmp_path / "validation-report.txt").read_text()
    assert "0 error(s), 0 warning(s)" in report
