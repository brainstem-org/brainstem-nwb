from pathlib import Path

import pytest

from brainstem_nwb.raw.base import RawDataConverter
from brainstem_nwb.raw.metadata import neuroconv_metadata
from brainstem_nwb.raw.paths import DataPathFile, resolve
from brainstem_nwb.raw.registry import available, for_acquisition_type, register

from .conftest import mapped_units


@pytest.fixture(scope="module")
def ephys_unit():
    (unit,), _ = mapped_units("ephys")
    return unit


def test_template_and_explicit_paths(ephys_unit):
    source = next(d for d in ephys_unit.data_sources if d.type == "ExtracellularEphys")
    paths = DataPathFile.model_validate({
        "defaults": {"root": "/data", "template": "{root}/{subject_storage}/{session_storage}/{file_name}"}})
    resolved = resolve(paths, source, session_name="S", subject_name="M")
    assert resolved.files == (Path("/data/SM01/SM01_240401/SM01_240401.dat"),)
    explicit = DataPathFile.model_validate({"dataacquisition": {source.dataacquisition_id: {
        "files": ["/x/a.dat"], "starting_time": 12.5, "options": {"xml_file_path": "/x/a.xml"}}}})
    resolved = resolve(explicit, source, session_name="S", subject_name="M")
    assert resolved.files == (Path("/x/a.dat"),) and resolved.starting_time == 12.5
    assert resolve(DataPathFile(), source, session_name="S", subject_name="M") is None


def test_neuroconv_metadata_reuses_planned_names(ephys_unit):
    metadata = neuroconv_metadata(ephys_unit.nwb)
    assert metadata["NWBFile"]["identifier"] == ephys_unit.nwb.nwbfile.identifier
    assert metadata["Subject"]["subject_id"] == "SynthMouse01"
    assert [g["name"] for g in metadata["Ecephys"]["ElectrodeGroup"]] == ["Probe A_shank1", "Probe A_shank2"]
    assert [d["name"] for d in metadata["Ecephys"]["Device"]] == ["Probe A"]


def test_converter_registry():
    class Dummy:
        name = "dummy-test"
        acquisition_types = ("ExtracellularEphys",)

        def check(self, source, details, paths):
            return []

        def add_to_nwbfile(self, nwbfile, source, details, paths, metadata):
            raise NotImplementedError

    converter = register(Dummy())
    assert isinstance(converter, RawDataConverter)
    assert "dummy-test" in available()
    assert converter in for_acquisition_type("ExtracellularEphys")
    assert for_acquisition_type("Audio") == []
    with pytest.raises(ValueError):
        register(Dummy())
