import copy

import pytest

from brainstem_nwb.errors import ConfigError
from brainstem_nwb.normalize.units import plan_units
from brainstem_nwb.retrieval.loader import load_export
from brainstem_nwb.store.graph import RecordStore

from .conftest import by_code, load, scenario


def _decisions(unit, label):
    return {a.pk: (a.decision, a.reason) for a in unit.attribution if a.label == label}


def test_single_subject_unit_and_path():
    _, store = load("ephys")
    units, errors = plan_units(store)
    assert errors == []
    (unit,) = units
    assert unit.relative_path == "sub-SynthMouse01/sub-SynthMouse01_ses-SM01-2024-04-01.nwb"
    assert unit.subject.get("name") == "SynthMouse01"
    assert {r.get("type") for r in unit.role("dataacquisition")} == {"ExtracellularEphys", "BehavioralTracking"}
    assert [r.get("name") for r in unit.role("interface")] == ["Probe A"]
    assert {r.get("name") for r in unit.role("equipment")} == {"Intan amplifier", "Overhead camera"}
    assert len(unit.role("epoch")) == 2


def test_procedures_after_the_session_are_excluded_but_recorded():
    _, store = load("ephys")
    (unit,) = plan_units(store)[0]
    included = {p.get("type") for p in unit.role("procedure")}
    assert included == {"Anesthesia", "VirusInjection", "SiliconProbeImplant"}
    (late,) = unit.role("procedure_after_session")
    assert late.get("type") == "PerfusionFixation"
    assert _decisions(unit, "modules.procedure")[late.pk][0] == "excluded"
    assert "PROCEDURE_AFTER_SESSION" in by_code(unit.warnings)


def test_materials_consumables_and_stocks_are_reached():
    _, store = load("ephys")
    (unit,) = plan_units(store)[0]
    assert {u.get("type") for u in unit.role("material_usage")} == {"AnestheticAgent", "ViralComponent",
                                                                     "SiliconProbe"}
    assert {c.get("name") for c in unit.role("consumable")} == {"Isoflurane", "AAV9-hSyn-GCaMP6f", "Buzsaki64"}
    assert [s.get("type") for s in unit.role("consumable_stock")] == ["VirusSolution"]


def test_multisubject_session_gives_one_unit_per_subject_with_attribution():
    _, store = load("multisubject")
    units, errors = plan_units(store)
    assert errors == []
    assert [u.subject.get("name") for u in units] == ["PairA", "PairB"]
    a, b = units
    # Fiber photometry is linked to PairA's implant: only in A's file
    assert {r.get("type") for r in a.role("dataacquisition")} == {"FiberPhotometry", "VideoTracking"}
    assert {r.get("type") for r in b.role("dataacquisition")} == {"VideoTracking"}
    video = next(r for r in a.role("dataacquisition") if r.get("type") == "VideoTracking")
    assert _decisions(a, "modules.dataacquisition")[video.pk][0] == "shared"
    assert "RECORD_SHARED_ACROSS_SUBJECTS" in by_code(a.warnings)
    # Behavior 'solo' lists only PairB; the epoch linking it is only in B's file
    assert len(a.role("behavior")) == 1 and len(b.role("behavior")) == 2
    assert [e.get("name") for e in a.role("epoch")] == ["interaction"]
    assert [e.get("name") for e in b.role("epoch")] == ["interaction", "solo"]
    # Each subject's own procedures only
    assert [p.get("type") for p in a.role("procedure")] == ["OpticFiberImplant"]
    assert [p.get("type") for p in b.role("procedure")] == ["Craniotomy"]
    assert "MULTIPLE_SUBJECTS" in by_code(a.warnings)


def test_session_problems_are_unit_errors():
    _, store = load("multisession")
    units, errors = plan_units(store)
    assert [u.session.get("name") for u in units] == ["SM05_day1", "SM05_day2"]
    assert sorted((e.session.get("name"), e.code) for e in errors) == [
        ("SM05_undated", "SESSION_START_TIME_MISSING"),
        ("foreign_subject", "SUBJECT_NOT_IN_EXPORT"),
        ("orphan_session", "NO_SUBJECT"),
    ]


def test_allow_no_subject():
    _, store = load("multisession")
    units, errors = plan_units(store, allow_no_subject=True)
    orphan = next(u for u in units if u.session.get("name") == "orphan_session")
    assert orphan.subject is None and orphan.relative_path == "ses-orphan-session.nwb"
    assert "NO_SUBJECT_ALLOWED" in by_code(orphan.warnings)
    assert {e.code for e in errors} == {"SESSION_START_TIME_MISSING", "SUBJECT_NOT_IN_EXPORT"}


def test_subjects_inferred_from_behaviors_when_session_lists_none():
    payload = copy.deepcopy(scenario("behavior"))
    payload["records"]["stem.session"][0]["fields"]["subjects"] = []
    store = RecordStore(load_export(payload))
    (unit,), errors = plan_units(store)
    assert errors == [] and unit.subject.get("name") == "SynthMouse02"
    assert "SUBJECTS_INFERRED" in by_code(unit.warnings)
    units, errors = plan_units(store, infer_subjects=False)
    assert units == [] and errors[0].code == "NO_SUBJECT"


def test_specimen_session_takes_subject_from_specimen_set():
    _, store = load("exvivo_specimen")
    (unit,), errors = plan_units(store)
    assert errors == []
    assert unit.subject.get("name") == "SynthMouse04"
    assert [s.get("name") for s in unit.specimen_sets] == ["SM04 acute slices"]
    assert {s.get("local_identifier") for s in unit.role("specimen")} == {"S1", "S2"}
    assert [r.get("type") for r in unit.role("dataacquisition")] == ["IntracellularEphys"]


def test_session_selection_by_id_or_name():
    _, store = load("multisession")
    day1 = next(s for s in store.all("stem.session") if s.get("name") == "SM05_day1")
    for selector in (day1.pk, "SM05_day1"):
        units, errors = plan_units(store, sessions=[selector])
        assert [u.session.pk for u in units] == [day1.pk] and errors == []
    with pytest.raises(ConfigError, match="not in this project"):
        plan_units(store, sessions=["nope"])


def test_filename_collisions_get_suffixes():
    payload = copy.deepcopy(scenario("multisession"))
    sessions = payload["records"]["stem.session"]
    for record in sessions:
        if record["fields"]["name"] == "SM05_day2":
            record["fields"]["name"] = "SM05 day1"  # sanitizes to the same label as SM05_day1
    store = RecordStore(load_export(payload))
    units, _ = plan_units(store)
    paths = [u.relative_path for u in units]
    assert len(set(paths)) == 2
    assert all("FILENAME_COLLISION" in by_code(u.warnings) for u in units)


def test_subject_label_field():
    _, store = load("ephys")
    (unit,), _ = plan_units(store, subject_label_field="name_used_in_storage")
    assert unit.relative_path.startswith("sub-SM01/")
