"""
Synthetic export scenarios. ``python tests/fixtures/regen.py`` writes them to tests/fixtures/exports/,
and the synthetic electrophysiology scenario to examples/synthetic-ephys/. All names and values are
invented; nothing comes from a real BrainSTEM project.
"""

from __future__ import annotations

from typing import Any

from .builder import ExportBuilder

REGION_CA1 = "0c5b1f2e-0000-4000-8000-0000000000a1"
REGION_MOP = "0c5b1f2e-0000-4000-8000-0000000000a2"
DANGLING_REGION = "0c5b1f2e-0000-4000-8000-0000000000a9"  # referenced but not in the export


def _base(b: ExportBuilder, **project_fields: Any) -> tuple[str, str]:
    b.project(
        "Hippocampal dynamics (synthetic)",
        description="<p>Synthetic project used to test <b>brainstem-nwb</b>.</p>",
        tags=["hippocampus", "synthetic"],
        **project_fields,
    )
    mouse = b.species()
    strain = b.strain("C57BL/6J", mouse, rrid="RRID:IMSR_JAX:000664", breeding="I")
    atlas = b.add("taxonomies.anatomicalreference", "ccf", code="allen_mouse_ccfv3_2017", version="2017",
                  name="Allen Mouse Common Coordinate Framework", region_atlas_code="AIA", species=mouse,
                  coordinate_space_identifier="Allen CCFv3 PIR", native_unit="um", is_active=True)
    for pk, acronym, name, structure in ((REGION_CA1, "CA1", "Field CA1", 382),
                                         (REGION_MOP, "MOp", "Primary motor area", 985)):
        b.records["taxonomies.anatomicalregion"].append({"model": "taxonomies.anatomicalregion", "pk": pk, "fields": {
            "acronym": acronym, "name": name, "reference": atlas, "description": "", "region_id": structure,
            "parent_acronym": "", "graph_order": None, "is_obsolete": False, "replaced_by": None,
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z", "user": None}})
    return mouse, strain


def ephys() -> dict[str, Any]:
    """One subject, one session: virus injection, silicon probe implant, extracellular recording, epochs."""
    b = ExportBuilder()
    journal = b.add("dissemination.journal", "jneuro", name="Journal of Synthetic Neuroscience")
    publication = b.add("dissemination.publication", "paper", title="Synthetic hippocampal dynamics",
                        authors="Example A, Example B", doi="10.0000/synthetic.0001", journal=journal,
                        publication_date="2025-01-01")
    mouse, strain = _base(b, publications=[publication])
    surgeon = b.user(11, "Grace", "Surgeon")
    assistant = b.user(12, "Alan", "Assistant")
    intan = b.add("resources.supplier", "intan", name="Intan Technologies", website="https://intantech.com")
    probe_maker = b.add("resources.supplier", "cnt", name="Cambridge NeuroTech")
    addgene = b.add("resources.supplier", "addgene", name="Addgene")
    authority = b.add("taxonomies.regulatoryauthority", "authority", name="Synthetic Animal Welfare Board",
                      abbreviation="SAWB", country="DK", is_active=True)
    subject = b.subject("SynthMouse01", mouse, strain=strain, sex="M", birth_date="2024-01-02",
                        genotype="wild type", subject_identifier="EAR-0101", name_used_in_storage="SM01",
                        description="<p>Implanted for chronic recording.</p>")
    session = b.session("SM01_2024-04-01", date_time="2024-04-01T10:00:00.000Z",
                        description="<p>Open field exploration followed by sleep.</p>", subjects=[subject],
                        tags=["open field"], name_used_in_storage="SM01_240401",
                        extra_content_json=[{"key": "room temperature", "value": "22 C"}],
                        repository_links_json=[{"repository": "DANDI", "url": "https://dandiarchive.org/dandiset/000000"}])
    protocol = b.add("personal_attributes.protocol", "surgery", name="Rodent survival surgery",
                     protocol_type="surgical", url="https://example.org/protocols/surgery")
    license_pk = b.add("personal_attributes.license", "lic", name="Animal license", license_number="AN-2024-001",
                       type="animal_experiment", status="active", regulatory_authority=authority)
    b.records["stem.subject"][-1]["fields"]["licenses"] = [license_pk]
    episode = b.add("modules.procedureepisode", "ep1", name="Implant surgery", subject=subject,
                    intervention_class="surgical", start_date_time="2024-03-01T09:00:00Z",
                    end_date_time="2024-03-01T12:00:00Z", status="complete", protocol=protocol)
    b.add("modules.episodepersonnel", "ep1-surgeon", episode=episode, person=surgeon, role="surgeon")
    b.add("modules.episodepersonnel", "ep1-assistant", episode=episode, person=assistant, role="assistant")

    iso = b.add("resources.consumable", "isoflurane", name="Isoflurane", type="Drug", type_json={})
    anesthesia = b.add("modules.procedure", "anesthesia", type="Anesthesia", subject=subject,
                       date_time="2024-03-01T09:05:00Z", procedure_episode=episode, protocol=protocol,
                       type_json={"depth": "surgical_plane", "duration": {"value": 150, "unit": "min"}})
    b.add("modules.materialusage", "iso-use", procedure=anesthesia, type="AnestheticAgent", consumable=iso, order=0,
          details_json={"concentration": {"value": 1.5, "unit": "%"}})

    construct = b.add("resources.consumable", "aav", name="AAV9-hSyn-GCaMP6f", type="VirusConstruct",
                      supplier=addgene, rrid="RRID:Addgene_100837",
                      type_json={"virusType": "aav", "capsid": "AAV9", "promoter": "hSyn", "gene": "GCaMP6f"})
    inventory = b.add("personal_attributes.inventory", "freezer", name="-80 freezer")
    stock = b.add("modules.consumablestock", "aav-stock", consumable=construct, inventory=inventory,
                  type="VirusSolution", type_json={"batchId": "B-17", "titer": {"value": 2e13, "unit": "vg/mL"}})
    virus = b.add("modules.procedure", "virus", type="VirusInjection", subject=subject,
                  date_time="2024-03-01T10:00:00Z", procedure_episode=episode, protocol=protocol,
                  performed_by=surgeon,
                  target_regions=[REGION_CA1], coordinates="Stereotaxic_BregmaBrainSurface",
                  coordinates_json={"apCoordinate": {"value": -2.0, "unit": "mm"},
                                    "mlCoordinate": {"value": 1.5, "unit": "mm"},
                                    "depth": {"value": 1.2, "unit": "mm"}},
                  type_json={"volume": {"value": 300, "unit": "nL"}, "rate": {"value": 50, "unit": "nL/min"},
                             "route": "intraparenchymal"})
    b.add("modules.materialusage", "virus-use", procedure=virus, type="ViralComponent", consumable_stock=stock,
          order=0, details_json={"volume": {"value": 300, "unit": "nL"}})

    probe_design = b.add("resources.consumable", "probe-design", name="Buzsaki64", type="SiliconProbeDesign",
                         supplier=probe_maker, type_json={"productId": "B64-8x8", "nChannels": 64, "nShanks": 8})
    implant = b.add("modules.procedure", "implant", type="SiliconProbeImplant", subject=subject,
                    date_time="2024-03-01T11:00:00Z", procedure_episode=episode, protocol=protocol,
                    performed_by=surgeon,
                    target_regions=[REGION_CA1], coordinates="Stereotaxic_BregmaBrainSurface",
                    coordinates_json={"apCoordinate": {"value": -2.0, "unit": "mm"},
                                      "mlCoordinate": {"value": 1.5, "unit": "mm"},
                                      "depth": {"value": 1.0, "unit": "mm"}},
                    type_json={"duraHandling": "dura_removed", "fixationMethod": "dental_cement"},
                    notes="Probe lowered slowly.")
    probe_usage = b.add("modules.materialusage", "probe-use", procedure=implant, type="SiliconProbe",
                        consumable=probe_design, order=0)
    probe = b.add("modules.experimentalinterface", "probe", name="Probe A", type="SiliconProbe", subject=subject,
                  persistence="chronic", installed_at="2024-03-01T11:30:00Z", source_material_usage=probe_usage,
                  target_regions=[REGION_CA1],
                  type_json={"deviceIdentifier": "SN-00451", "channelCount": 64, "shankCount": 8})
    b.add("modules.procedureinterface", "implant-probe", procedure=implant, interface=probe, relationship="created")
    b.records["modules.procedure"][-1]["fields"]["interfaces"] = [probe]
    # Perfusion after the session: excluded from the file, kept in the manifest
    b.add("modules.procedure", "perfusion", type="PerfusionFixation", subject=subject,
          date_time="2024-05-01T09:00:00Z")
    # Planned, never performed: excluded from the file, kept in the manifest
    b.add("modules.procedure", "planned-analgesic", type="Analgesic", subject=subject,
          date_time="2024-03-02T09:00:00Z", status="planned")

    weighing = b.add("modules.subjectlog", "weights", type="Weighing", subject=subject, description="Weekly weights")
    for key, when, grams in (("w1", "2024-03-25T09:00:00Z", 24.1), ("w2", "2024-03-31T09:00:00Z", 25.3),
                             ("w3", "2024-04-08T09:00:00Z", 26.0)):
        b.add("modules.moduleslogentry", key, content_type="modules.subjectlog", object_id=weighing, date_time=when,
              type_json={"weight": {"value": grams, "unit": "g"}}, type_schema_version="1.1.1",
              performedBy=assistant)
    head_fixed = b.add("taxonomies.setuptype", "freely", name="Freely moving, awake", category="FA")
    category = b.add("taxonomies.behavioralcategory", "exploration", name="Exploration")
    paradigm = b.add("taxonomies.behavioralparadigm", "open-field-test", name="Open field test", category=category)
    setup = b.add("personal_attributes.setup", "rig1", name="Rig 1", location="Room 101", setup_type=head_fixed,
                  description="Open field arena with overhead camera")
    hardware = b.add("resources.hardwaredevice", "rhd", name="RHD2164 headstage", type="Amplifier", supplier=intan,
                     rrid="RRID:SCR_019318", type_json={"productId": "C3314", "nChannels": 64})
    amplifier = b.add("modules.equipment", "amp", name="Intan amplifier", type="Amplifier", setup=setup,
                      hardwaredevice=hardware)
    camera = b.add("modules.equipment", "cam", name="Overhead camera", type="Camera", setup=setup)

    recording = b.add("modules.dataacquisition", "ephys", session=session, type="ExtracellularEphys", order=0,
                      interfaces=[probe], equipment=[amplifier],
                      type_json={"fileName": "SM01_240401.dat", "format": "dat", "type": "int16",
                                 "nChannels": 64, "nSamples": 72000000, "sr": {"value": 20000, "unit": "Hz"},
                                 "lsb": {"value": 0.195, "unit": "µV"},
                                 "electrodeGroups": [{"label": "shank1", "channels": list(range(0, 32))},
                                                     {"label": "shank2", "channels": list(range(32, 64))}]})
    b.add("modules.dataacquisitioninterface", "ephys-probe", dataacquisition=recording, interface=probe, order=0)
    tracking = b.add("modules.dataacquisition", "tracking", session=session, type="BehavioralTracking", order=1,
                     equipment=[camera],
                     type_json={"fileName": "SM01_240401.avi", "format": "avi",
                                "frameRate": {"value": 30, "unit": "Hz"}})

    assay = b.add("personal_attributes.behavioralassay", "openfield", name="Open field",
                  description="Free exploration of a 1 m square arena", behavioral_paradigm=paradigm)
    behavior = b.add("modules.behavior", "of", session=session, subjects=[subject], setup=setup,
                     behavioralassay=assay, order=0)
    b.add("stem.epoch", "exploration", name="exploration", session=session, start="00:00:00", end="00:30:00",
          order=0, behavior=behavior, dataacquisitions=[recording, tracking])
    b.add("stem.epoch", "sleep", name="sleep", session=session, start="00:30:00", end="01:30:00.500000", order=1,
          dataacquisitions=[recording])
    storage = b.add("personal_attributes.datastorage", "server", name="Lab server",
                    data_organization=[{"type": "subject"}, {"type": "session"}])
    b.records["stem.session"][-1]["fields"]["datastorage"] = [storage]
    b.add("stem.sessiondatastorage", "ses-storage", session=session, datastorage=storage, order=0)
    return b.to_dict()


def behavior() -> dict[str, Any]:
    """Behavior-only session: tracking acquisition, two behaviors (one without epoch)."""
    b = ExportBuilder()
    mouse, strain = _base(b)
    subject = b.subject("SynthMouse02", mouse, strain=strain, sex="F", birth_date="2024-02-10")
    session = b.session("SM02_maze", date_time="2024-05-20T14:30:00.250Z", description="T-maze training",
                        subjects=[subject])
    setup = b.add("personal_attributes.setup", "maze", name="T-maze", location="Room 102")
    camera = b.add("modules.equipment", "cam2", name="Maze camera", type="Camera", setup=setup)
    # Equipment of another lab's setup, which the exporting user cannot read: only its name is exported
    hidden = b.pk("modules.equipment", "hidden-sync")
    b.restricted = {"modules.equipment": [{"pk": hidden, "name": "Sync box (other lab)"}]}
    tracking = b.add("modules.dataacquisition", "tracking", session=session, type="VideoTracking", order=0,
                     equipment=[camera, hidden],
                     type_json={"fileName": "maze.mp4", "format": "mp4", "frameRate": {"value": 60, "unit": "Hz"}})
    assay = b.add("personal_attributes.behavioralassay", "tmaze", name="T-maze alternation",
                  description="Spontaneous alternation")
    training = b.add("modules.behavior", "train", session=session, subjects=[subject], setup=setup,
                     behavioralassay=assay, order=0, notes="10 laps")
    b.add("modules.behavior", "home", session=session, subjects=[subject], order=1, notes="Home cage before task")
    b.add("stem.epoch", "task", name="task", session=session, start="0:05:00", end="0:25:00", order=0,
          behavior=training, dataacquisitions=[tracking])
    return b.to_dict()


def optogenetics() -> dict[str, Any]:
    """Three optic fibers: one wavelength, none, and two (ambiguous)."""
    b = ExportBuilder()
    mouse, strain = _base(b)
    subject = b.subject("SynthMouse03", mouse, strain=strain, sex="F", birth_date="2023-11-30")
    session = b.session("SM03_opto", date_time="2024-06-01T09:00:00Z", description="Optogenetic silencing",
                        subjects=[subject])
    fibers = {}
    for key in ("fiberA", "fiberB", "fiberC"):
        ccf = {"coordinates": "CCF_XYZ_Absolute",
               "coordinates_json": {"x": {"value": 3.5, "unit": "mm"}, "y": {"value": 1.8, "unit": "mm"},
                                    "z": {"value": 6.9, "unit": "mm"}}} if key == "fiberA" else {}
        fibers[key] = b.add("modules.experimentalinterface", key, name=key, type="OpticFiber", subject=subject,
                            persistence="chronic", installed_at="2024-05-01T10:00:00Z",
                            target_regions=[REGION_MOP], **ccf)
        # Absolute stereotaxic target; fiberC's implant lacks the DV value (not localized)
        dv = {} if key == "fiberC" else {"dvCoordinate": {"value": 0.8, "unit": "mm"}}
        implant = b.add("modules.procedure", f"implant-{key}", type="OpticFiberImplant", subject=subject,
                        date_time="2024-05-01T10:00:00Z", target_regions=[REGION_MOP],
                        interfaces=[fibers[key]], coordinates="Stereotaxic_BregmaAbsolute",
                        coordinates_json={"apCoordinate": {"value": 1.1, "unit": "mm"},
                                          "mlCoordinate": {"value": -1.4 if key == "fiberB" else 1.4, "unit": "mm"},
                                          **dv})
        b.add("modules.procedureinterface", f"pi-{key}", procedure=implant, interface=fibers[key],
              relationship="created")
    laser = b.add("modules.equipment", "laser", name="473 nm laser", type="Laser",
                  setup=b.add("personal_attributes.setup", "opto-rig", name="Opto rig"))
    b.add("modules.manipulation", "stimA", session=session, type="OptogeneticStimulation", order=0,
          interfaces=[fibers["fiberA"]], equipment=[laser],
          type_json=[{"power": {"value": 5, "unit": "mW"}, "profile": "pulse_train",
                      "duration": {"value": 10, "unit": "ms"}, "wavelength": {"value": 473, "unit": "nm"}},
                     {"power": {"value": 10, "unit": "mW"}, "profile": "square",
                      "wavelength": {"value": 0.473, "unit": "µm"}}])
    b.add("modules.manipulation", "stimB", session=session, type="OptogeneticStimulation", order=1,
          interfaces=[fibers["fiberB"]], type_json=[{"power": {"value": 5, "unit": "mW"}}])
    b.add("modules.manipulation", "stimC", session=session, type="OptogeneticStimulation", order=2,
          interfaces=[fibers["fiberC"]],
          type_json=[{"wavelength": {"value": 473, "unit": "nm"}}, {"wavelength": {"value": 593, "unit": "nm"}}])
    b.add("modules.manipulation", "drug", session=session, type="PharmacologicalInjection", order=3,
          type_json=[{"volume": {"value": 0.2, "unit": "mL"}, "profile": "bolus"}], notes="saline control")
    return b.to_dict()


def exvivo_specimen() -> dict[str, Any]:
    """A specimen session: acute slices from one subject, patch-clamp recording."""
    b = ExportBuilder()
    mouse, strain = _base(b)
    subject = b.subject("SynthMouse04", mouse, strain=strain, sex="M", birth_date="2024-03-01")
    specimen_set = b.add("stem.specimenset", "slices", name="SM04 acute slices", type="SliceSeries",
                         subject=subject, projects=[b.project_pk], status="in_use", quality="good", item_count=6,
                         preparation_datetime="2024-04-15T08:00:00Z",
                         preparation_conditions=["fixed"], target_regions=[REGION_CA1])
    b.add("stem.specimen", "slice1", specimen_set=specimen_set, local_identifier="S1", type="Slice",
          laterality="left", order=0)
    b.add("stem.specimen", "slice2", specimen_set=specimen_set, local_identifier="S2", type="Slice",
          laterality="right", order=1)
    b.add("modules.specimenprocedure", "sectioning", type="Sectioning",
          specimen_set=specimen_set, date_time="2024-04-15T08:00:00Z",
          type_json={"thickness": {"value": 300, "unit": "µm"}})
    b.add("modules.specimenprocedure", "staining", type="Staining", specimen_set=specimen_set,
          date_time="2024-04-15T14:00:00Z", status="cancelled")
    session = b.session("SM04_slices", session_type="specimen", date_time="2024-04-15T11:00:00Z",
                        description="Whole-cell recordings in acute slices", specimen_sets=[specimen_set])
    pipette = b.add("modules.experimentalinterface", "pipette", name="Pipette 1", type="PatchPipette",
                    specimen_set=specimen_set, persistence="transient")
    b.add("modules.dataacquisition", "patch", session=session, type="IntracellularEphys", order=0,
          interfaces=[pipette],
          type_json={"fileName": "cell1.abf", "format": "abf", "sr": {"value": 50, "unit": "kHz"}})
    return b.to_dict()


def multisubject() -> dict[str, Any]:
    """Two subjects in one session with attributed and shared records."""
    b = ExportBuilder()
    mouse, strain = _base(b)
    a = b.subject("PairA", mouse, strain=strain, sex="F", birth_date="2024-01-01")
    c = b.subject("PairB", mouse, strain=strain, sex="M", birth_date="2024-01-05")
    session = b.session("social_01", date_time="2024-04-10T13:00:00Z", description="Social interaction",
                        subjects=[a, c])
    fiber_a = b.add("modules.experimentalinterface", "fa", name="Fiber A", type="OpticFiber", subject=a,
                    installed_at="2024-03-01T10:00:00Z")
    b.add("modules.procedure", "implant-a", type="OpticFiberImplant", subject=a,
                      date_time="2024-03-01T10:00:00Z", interfaces=[fiber_a])
    b.add("modules.procedure", "implant-b", type="Craniotomy", subject=c, date_time="2024-03-02T10:00:00Z")
    photometry = b.add("modules.dataacquisition", "fp", session=session, type="FiberPhotometry", order=0,
                       interfaces=[fiber_a])
    video = b.add("modules.dataacquisition", "video", session=session, type="VideoTracking", order=1)
    both = b.add("modules.behavior", "social", session=session, subjects=[a, c], order=0)
    only_c = b.add("modules.behavior", "solo", session=session, subjects=[c], order=1)
    b.add("stem.epoch", "e1", name="interaction", session=session, start="00:00:00", end="00:10:00",
          behavior=both, dataacquisitions=[photometry, video], order=0)
    b.add("stem.epoch", "e2", name="solo", session=session, start="00:10:00", end="00:20:00",
          behavior=only_c, order=1)
    return b.to_dict()


def multisession() -> dict[str, Any]:
    """Six sessions: two good ones, one without start time, one without subjects, one with a missing subject and a
    planned one."""
    b = ExportBuilder()
    mouse, strain = _base(b)
    subject = b.subject("SynthMouse05", mouse, strain=strain, sex="F", birth_date="2024-01-01")
    for day in (1, 2):
        b.session(f"SM05_day{day}", date_time=f"2024-04-0{day}T10:00:00Z", description=f"Day {day}",
                  subjects=[subject])
    b.session("SM05_undated", description="No date", subjects=[subject])
    b.session("orphan_session", date_time="2024-04-03T10:00:00Z", description="No subject")
    b.session("foreign_subject", date_time="2024-04-04T10:00:00Z", description="Subject of another project",
              subjects=["99999999-0000-4000-8000-000000000000"])
    b.session("SM05_day3", date_time="2024-04-05T10:00:00Z", description="Not yet recorded", subjects=[subject],
              status="planned")
    return b.to_dict()


def edge_cases() -> dict[str, Any]:
    """A newer format minor (2.9) with an unknown label and field, legacy values and odd durations."""
    b = ExportBuilder()
    mouse, _ = _base(b)
    subject = b.subject("Edge/Case #1", mouse, sex="U", extra_content_json={"cage": "C-12", "diet": None},
                        description="<ul><li>first</li><li>second &amp; third</li></ul>")
    session = b.session("edge session (1)", date_time="2024-07-01T23:30:00.5+02:00", description="",
                        subjects=[subject], extra_content_json={"legacy": "dict form"})
    b.add("modules.procedure", "undated", type="Craniotomy", subject=subject, target_regions=[DANGLING_REGION])
    b.add("modules.procedure", "future-type", type="TimeTravelImplant", subject=subject,
          date_time="2024-06-01T10:00:00Z")
    b.add("modules.dataacquisition", "legacy", session=session, type="ExtracellularEphys", order=0,
          type_json={"fileName": "x.dat", "sr": 20000, "nChannels": 4})
    b.add("stem.epoch", "long", name="long", session=session, start="0:00:00", end="1 02:00:00", order=0)
    b.add("stem.epoch", "negative", name="before start", session=session, start="-1 23:59:59", end="00:00:10",
          order=1)
    b.add("stem.epoch", "open", name="open ended", session=session, start="00:00:00", end=None, order=2)
    b.add("stem.epoch", "backwards", name="backwards", session=session, start="00:10:00", end="00:05:00", order=3)
    payload = b.to_dict()
    payload["export_info"]["format_version"] = "2.9"
    payload["records"]["stem.futurething"] = [{"model": "stem.futurething", "pk": "f-1", "fields": {"name": "x"}}]
    payload["records"]["stem.session"][0]["fields"]["new_field"] = "from the future"
    return payload


def session_export() -> dict[str, Any]:
    """A session export (format 2.1 scope "session") of a session that belongs to two projects."""
    b = ExportBuilder()
    mouse, strain = _base(b)
    other = b.add("stem.project", "Second project", name="Second project (synthetic)", tags=["memory"],
                  description="Shares the session")
    subject = b.subject("SynthMouse06", mouse, strain=strain, sex="F", birth_date="2024-01-15",
                        projects=[b.project_pk, other])
    session = b.session("SM06_shared", date_time="2024-05-02T08:00:00Z", description="Session in two projects",
                        subjects=[subject], projects=[b.project_pk, other])
    b.add("modules.procedure", "cranio", type="Craniotomy", subject=subject, date_time="2024-04-01T10:00:00Z")
    b.add("modules.dataacquisition", "video", session=session, type="VideoTracking", order=0)
    b.scope, b.session_id = "session", session
    return b.to_dict()


SCENARIOS = {
    "ephys": ephys,
    "behavior": behavior,
    "optogenetics": optogenetics,
    "exvivo_specimen": exvivo_specimen,
    "multisubject": multisubject,
    "multisession": multisession,
    "edge_cases": edge_cases,
    "session_export": session_export,
}
