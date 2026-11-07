import copy

import pytest

from brainstem_nwb.config import ExportOptions
from brainstem_nwb.mapping.pipeline import map_unit
from brainstem_nwb.normalize.units import plan_units
from brainstem_nwb.retrieval.loader import load_export
from brainstem_nwb.store.graph import RecordStore

from .conftest import by_code, mapped_units, mapping_state, scenario


@pytest.fixture(scope="module")
def ephys_unit():
    (unit,), _ = mapped_units("ephys")
    return unit


class TestNWBFile:
    def test_core_fields(self, ephys_unit):
        f = ephys_unit.nwb.nwbfile
        assert f.session_description == "Open field exploration followed by sleep."
        assert f.session_id == "SM01_2024-04-01"
        assert f.session_start_time.isoformat() == "2024-04-01T10:00:00+00:00"
        assert f.timestamps_reference_time == f.session_start_time
        assert f.experiment_description == (
            "Hippocampal dynamics (synthetic): Synthetic project used to test brainstem-nwb.")
        assert f.keywords == ["BrainSTEM", "hippocampus", "metadata-only", "open field", "synthetic"]
        assert f.was_generated_by[0][0] == "brainstem-nwb"
        assert f.experimenter == [] and f.lab is None

    def test_identifier_is_deterministic_and_content_sensitive(self, ephys_unit):
        (again,), _ = mapped_units("ephys")
        assert again.nwb.nwbfile.identifier == ephys_unit.nwb.nwbfile.identifier
        payload = copy.deepcopy(scenario("ephys"))
        payload["records"]["stem.session"][0]["fields"]["description"] = "changed"
        export = load_export(payload)
        store = RecordStore(export)
        (unit,), _ = plan_units(store)
        changed = map_unit(store, unit, ExportOptions(), export)
        assert changed.nwb.nwbfile.identifier != ephys_unit.nwb.nwbfile.identifier

    def test_identifier_ignores_export_time(self, ephys_unit):
        payload = copy.deepcopy(scenario("ephys"))
        payload["export_info"]["exported_at"] = "2030-01-01T00:00:00+00:00"
        export = load_export(payload)
        store = RecordStore(export)
        (unit,), _ = plan_units(store)
        later = map_unit(store, unit, ExportOptions(), export)
        assert later.nwb.nwbfile.identifier == ephys_unit.nwb.nwbfile.identifier
        assert later.nwb.provenance["source_sha256"] != ephys_unit.nwb.provenance["source_sha256"]

    def test_procedure_narratives(self, ephys_unit):
        f = ephys_unit.nwb.nwbfile
        assert f.surgery.startswith("2024-03-01T11:00:00Z — Silicon probe implant [brainstem:procedure/")
        assert "coordinates Stereotaxic_BregmaBrainSurface AP -2 mm, ML 1.5 mm, depth 1 mm" in f.surgery
        assert "interfaces Probe A (created)" in f.surgery
        assert "PerfusionFixation" not in f.surgery and "perfusion" not in f.surgery.lower()
        assert "AAV9-hSyn-GCaMP6f" in f.virus and "capsid: AAV9" in f.virus and "batch id: B-17" in f.virus
        assert "supplier Addgene, RRID:Addgene_100837" in f.virus
        assert "volume: 300 nL, rate: 50 nL/min, route: intraparenchymal" in f.virus
        assert f.pharmacology.startswith("2024-03-01T09:05:00Z — Anesthesia")
        assert "Isoflurane" in f.pharmacology and "1.5 %" in f.pharmacology
        assert "targets CA1 (Field CA1; Allen Mouse Common Coordinate Framework 2017)" in f.surgery
        assert "performed by Grace Surgeon" in f.surgery
        assert "episode Implant surgery (surgeon Grace Surgeon, assistant Alan Assistant)" in f.surgery
        assert f.related_publications == ["doi:10.0000/synthetic.0001"]

    def test_protocol_and_data_collection(self, ephys_unit):
        f = ephys_unit.nwb.nwbfile
        assert f.protocol == "Rodent survival surgery (surgical) https://example.org/protocols/surgery"
        assert "sr: 20000 Hz, lsb: 0.195 µV, electrode groups: 2 (shank1, shank2)" in f.data_collection
        assert "frame rate: 30 Hz" in f.data_collection

    def test_notes(self, ephys_unit):
        notes = ephys_unit.nwb.nwbfile.notes
        assert notes.startswith("METADATA-ONLY EXPORT")
        assert "Behaviors:\nBehavior [brainstem:behavior/" in notes
        assert "room temperature: 22 C" in notes
        assert "DANDI: https://dandiarchive.org/dandiset/000000" in notes
        assert ephys_unit.nwb.provenance["session_id"] == ephys_unit.session.id

    def test_missing_description_gets_placeholder(self):
        (unit,), _ = mapped_units("edge_cases")
        assert unit.nwb.nwbfile.session_description == "BrainSTEM session 'edge session (1)' has no description."
        assert mapping_state(unit, "session.description") == ["missing"]
        assert "SESSION_DESCRIPTION_MISSING" in by_code(unit.warnings)


class TestSubject:
    def test_fields(self, ephys_unit):
        s = ephys_unit.nwb.subject
        assert (s.subject_id, s.species, s.strain, s.sex, s.genotype) == (
            "SynthMouse01", "Mus musculus", "C57BL/6J", "M", "wild type")
        assert s.date_of_birth.isoformat() == "2024-01-02T00:00:00+00:00"
        assert (s.age, s.age__reference) == ("P90D", "birth")
        assert s.description == ("Implanted for chronic recording. External identifier: EAR-0101. "
                                 "Strain RRID: RRID:IMSR_JAX:000664. Weight 25.3 g measured 2024-03-31T09:00:00Z. "
                                 f"BrainSTEM subject: {ephys_unit.subject.id}.")
        # the latest weighing at or before the session start (a later one exists)
        assert s.weight == "25.3 g"
        assert mapping_state(ephys_unit, "subject.weight") == ["present"]

    def test_weight_unknown_and_2_0_exports(self):
        (unit,), _ = mapped_units("behavior")
        assert unit.nwb.subject.weight is None and "SUBJECT_WEIGHT_UNKNOWN" in by_code(unit.warnings)
        payload = copy.deepcopy(scenario("ephys"))
        payload["export_info"]["format_version"] = "2.0"
        for label in ("modules.moduleslogentry", "modules.startendmoduleslogentry"):
            del payload["records"][label]
        export = load_export(payload)
        store = RecordStore(export)
        (planned,), _ = plan_units(store)
        mapped = map_unit(store, planned, ExportOptions(), export)
        assert mapped.nwb.subject.weight is None and "SUBJECT_WEIGHT_NOT_IN_EXPORT" in by_code(mapped.warnings)

    def test_experimenter_from_session_creator(self):
        (unit,), _ = mapped_units("ephys", nwbfile={"experimenter_source": "session_creator"})
        assert unit.nwb.nwbfile.experimenter == ["Example, Ada"]
        (configured,), _ = mapped_units("ephys", nwbfile={"experimenter_source": "session_creator",
                                                          "experimenter": ["Doe, Jane"]})
        assert configured.nwb.nwbfile.experimenter == ["Doe, Jane"]

    def test_species_iri(self):
        (unit,), _ = mapped_units("ephys", subject={"species_format": "ncbitaxon"})
        assert unit.nwb.subject.species == "http://purl.obolibrary.org/obo/NCBITaxon_10090"

    def test_unknown_sex_missing_birth_and_slash(self):
        (unit,), _ = mapped_units("edge_cases")
        s = unit.nwb.subject
        assert s.sex == "U" and mapping_state(unit, "subject.sex") == ["unknown"]
        assert s.age is None and s.date_of_birth is None
        assert mapping_state(unit, "subject.age") == ["missing"]
        assert s.subject_id == "Edge-Case #1"
        codes = by_code(unit.warnings)
        assert "SUBJECT_AGE_UNKNOWN" in codes and "IDENTIFIER_SLASH_REPLACED" in codes
        assert "cage: C-12." in s.description and "diet: ." in s.description

    def test_negative_age_is_an_error(self):
        payload = copy.deepcopy(scenario("ephys"))
        payload["records"]["stem.subject"][0]["fields"]["birth_date"] = "2025-01-01"
        export = load_export(payload)
        store = RecordStore(export)
        (unit,), _ = plan_units(store)
        mapped = map_unit(store, unit, ExportOptions(), export)
        assert mapped.nwb.subject.age is None
        assert by_code(mapped.warnings)["SUBJECT_AGE_NEGATIVE"][0].severity == "error"


class TestDevices:
    def test_devices_and_electrode_groups(self, ephys_unit):
        devices = {d.name: d for d in ephys_unit.nwb.devices}
        assert set(devices) == {"Intan amplifier", "Overhead camera", "Probe A"}
        assert devices["Probe A"].serial_number == "SN-00451"
        assert "hardware RHD2164 headstage" in devices["Intan amplifier"].description
        assert "Freely moving, awake" in devices["Intan amplifier"].description
        models = {m.name: m for m in ephys_unit.nwb.device_models}
        assert (models["RHD2164 headstage"].manufacturer, models["RHD2164 headstage"].model_number) == (
            "Intan Technologies", "C3314")
        assert (models["Buzsaki64"].manufacturer, models["Buzsaki64"].model_number) == (
            "Cambridge NeuroTech", "B64-8x8")
        assert (devices["Intan amplifier"].model, devices["Probe A"].model, devices["Overhead camera"].model) == (
            "RHD2164 headstage", "Buzsaki64", None)
        groups = ephys_unit.nwb.electrode_groups
        assert [(g.name, g.device, g.location, g.channels[:2]) for g in groups] == [
            ("Probe A_shank1", "Probe A", "CA1", [0, 1]), ("Probe A_shank2", "Probe A", "CA1", [32, 33])]
        assert "channels 0-31" in groups[0].description
        assert "target CA1 (Field CA1; Allen Mouse Common Coordinate Framework 2017)" in groups[0].description
        codes = by_code(ephys_unit.warnings)
        assert "ELECTRODES_NOT_WRITTEN" in codes
        assert "REGION_NOT_RESOLVED" not in codes and "DEVICE_MANUFACTURER_UNKNOWN" not in codes

    def test_missing_regions_and_suppliers(self):
        """Without region or supplier records (format 2.0), locations are 'unknown' and no DeviceModel is written."""
        payload = copy.deepcopy(scenario("ephys"))
        payload["records"]["taxonomies.anatomicalregion"] = []
        payload["records"]["resources.supplier"] = []
        export = load_export(payload)
        store = RecordStore(export)
        (unit,), _ = plan_units(store)
        mapped = map_unit(store, unit, ExportOptions(), export)
        assert {g.location for g in mapped.nwb.electrode_groups} == {"unknown"}
        assert "1 region(s) not in the export" in mapped.nwb.nwbfile.virus
        assert mapped.nwb.device_models == [] and all(d.model is None for d in mapped.nwb.devices)
        codes = by_code(mapped.warnings)
        assert "REGION_NOT_RESOLVED" in codes and "DEVICE_MANUFACTURER_UNKNOWN" in codes

    def test_restricted_equipment_is_named(self):
        (unit,), _ = mapped_units("behavior")
        assert "Sync box (other lab) (not readable by the exporting user)" in unit.nwb.nwbfile.data_collection
        assert {d.name for d in unit.nwb.devices} == {"Maze camera"}

    def test_behavior_paradigm_and_setup_type(self, ephys_unit):
        notes = ephys_unit.nwb.nwbfile.notes
        assert "paradigm Open field test, category Exploration" in notes
        assert "setup Rig 1 (Room 101; Freely moving, awake;" in notes

    def test_optogenetic_sites(self):
        (unit,), _ = mapped_units("optogenetics")
        (site,) = unit.nwb.optogenetic_sites
        assert site.name == "fiberA_site" and site.device == "fiberA"
        assert site.excitation_lambda == pytest.approx(473.0)  # 473 nm and 0.473 µm agree
        codes = by_code(unit.warnings)
        assert codes["OPTO_SITE_NO_WAVELENGTH"][0].source.pk  # fiberB
        assert "OPTO_SITE_WAVELENGTH_AMBIGUOUS" in codes  # fiberC
        assert {d.name for d in unit.nwb.devices} >= {"fiberA", "fiberB", "fiberC", "473 nm laser"}
        f = unit.nwb.nwbfile
        assert f.stimulus_notes.count("Optogenetic stimulation") == 3
        assert "Pharmacological injection" in f.pharmacology and "saline control" in f.pharmacology


class TestEpochs:
    def test_rows(self, ephys_unit):
        rows = ephys_unit.nwb.epochs.rows
        assert [(r.start_time, r.stop_time, r.tags) for r in rows] == [
            (0.0, 1800.0, ["exploration"]), (1800.0, 5400.5, ["sleep"])]
        assert rows[0].values["behavior"].startswith("Open field [")
        assert "BehavioralTracking" in rows[0].values["data_acquisitions"]
        assert [c.name for c in ephys_unit.nwb.epochs.columns] == [
            "brainstem_id", "behavior", "data_acquisitions", "manipulations"]

    def test_odd_epochs(self):
        (unit,), _ = mapped_units("edge_cases")
        rows = unit.nwb.epochs.rows
        assert [(r.tags[0], r.start_time, r.stop_time) for r in rows] == [
            ("before start", -1.0, 10.0), ("long", 0.0, 93600.0)]
        codes = by_code(unit.warnings)
        assert {"EPOCH_TIMES_MISSING", "EPOCH_STOP_BEFORE_START", "EPOCH_NEGATIVE_TIME"} <= set(codes)

    def test_multisubject_epoch_columns_drop_other_subjects_records(self):
        units, _ = mapped_units("multisubject")
        b = next(u for u in units if u.subject.name == "PairB")
        interaction = next(r for r in b.nwb.epochs.rows if r.tags == ["interaction"])
        assert "FiberPhotometry" not in interaction.values["data_acquisitions"]
        assert "VideoTracking" in interaction.values["data_acquisitions"]


class TestOther:
    def test_behavior_without_epoch(self):
        (unit,), _ = mapped_units("behavior")
        assert "no epoch (no timing recorded)" in unit.nwb.nwbfile.notes
        assert len(by_code(unit.warnings)["BEHAVIOR_NO_TIMING"]) == 1

    def test_slices_and_icephys(self):
        (unit,), _ = mapped_units("exvivo_specimen")
        slices = unit.nwb.nwbfile.slices
        assert slices.startswith("Specimen set SM04 acute slices [brainstem:specimenset/")
        assert "specimen S1" in slices and "laterality left" in slices and "thickness: 300 µm" in slices
        assert "ICEPHYS_NOT_MAPPED" in by_code(unit.warnings)
        (ephys,), _ = mapped_units("ephys")
        assert mapping_state(ephys, "specimens.slices") == ["not_applicable"]

    def test_unknown_procedure_type_goes_to_notes(self):
        (unit,), _ = mapped_units("edge_cases")
        assert "Other procedures:" in unit.nwb.nwbfile.notes and "TimeTravelImplant" in unit.nwb.nwbfile.notes
        assert "PROCEDURE_TYPE_UNCLASSIFIED" in by_code(unit.warnings)
        assert "PROCEDURE_DATE_UNKNOWN" in by_code(unit.warnings)

    def test_unknown_fields_warned_once_and_kept(self):
        (unit,), _ = mapped_units("edge_cases")
        assert len(by_code(unit.warnings)["UNKNOWN_FIELD"]) == 1
        session = next(r for r in unit.records if r.label == "stem.session")
        assert session.fields["new_field"] == "from the future" and "new_field" in session.unmapped_fields

    def test_records_drop_private_fields(self, ephys_unit):
        for entry in ephys_unit.records:
            assert "user" not in entry.fields and "permission_uids_at_deletion" not in entry.fields

    def test_data_sources(self, ephys_unit):
        ephys = next(d for d in ephys_unit.data_sources if d.type == "ExtracellularEphys")
        assert (ephys.file_name, ephys.format, ephys.session_storage_name, ephys.subject_storage_name) == (
            "SM01_240401.dat", "dat", "SM01_240401", "SM01")
        assert [s.name for s in ephys.datastorages] == ["Lab server"]
        assert ephys.raw_conversion.status == "not_attempted"

    def test_configured_people(self):
        (unit,), _ = mapped_units("ephys", nwbfile={"experimenter": ["Doe, Jane"], "lab": "Lab",
                                                    "institution": "Uni"})
        f = unit.nwb.nwbfile
        assert (f.experimenter, f.lab, f.institution) == (["Doe, Jane"], "Lab", "Uni")
        codes = by_code(unit.warnings)
        assert "EXPERIMENTER_NOT_AVAILABLE" not in codes and "LAB_NOT_AVAILABLE" not in codes


def test_administrative_lab_resources_stay_out_of_the_nwb_file(ephys_unit):
    """Licenses, data storages and inventories are kept in the manifest only."""
    plan = ephys_unit.nwb.model_dump_json(exclude={"provenance"})
    for text in ("Animal license", "AN-2024-001", "SAWB", "Lab server", "-80 freezer"):
        assert text not in plan, text
    labels = {entry.label for entry in ephys_unit.records}
    assert {"personal_attributes.license", "personal_attributes.datastorage",
            "personal_attributes.inventory"} <= labels
