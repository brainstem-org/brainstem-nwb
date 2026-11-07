"""
Plan the export units: one NWB file per session and subject.

An NWB file describes one subject, but a BrainSTEM session can have several (``Session.subjects``
is many-to-many; a specimen session reaches subjects through its specimen sets). For each
session this module finds the subjects and, for each subject, decides which of the session's
records belong in that subject's file. Every decision is recorded as an ``Attribution`` so the
manifest shows why a record was included, shared or left out.

Rules:

- Only performed records describe what happened: planned and cancelled sessions get no file
  (``SESSION_NOT_PERFORMED``), and planned and cancelled procedures and specimen procedures are
  left out of the file and kept in the manifest (``PROCEDURE_NOT_PERFORMED``). Records without a
  status (exports from before BrainSTEM had one) are performed.
- Data acquisitions and manipulations belong to the subjects of the experimental interfaces they
  are linked to (directly, or through the interface's specimen set). Linked to none, they are
  shared by all subjects of the session.
- Behaviors belong to their ``subjects``; with none, they are shared.
- Epochs are included when any record they link is included, or when they link nothing.
- The subject's procedures up to the session start are its history and are included; later ones
  are left out (but kept in the manifest), unless they are linked to an interface of an included
  acquisition or manipulation. A procedure without a date is included with an info warning.
- Experimental interfaces linked from included acquisitions and manipulations are included and
  become NWB devices.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from ..manifest.models import Attribution, ConversionWarning
from ..manifest.warnings import make_warning
from ..store.graph import Record, RecordStore
from .identifiers import dandi_label
from .timeutil import parse_datetime

Decision = Literal["included", "shared", "excluded"]


@dataclass
class ExportUnit:
    unit_id: str
    session: Record
    subject: Record | None
    projects: list[Record]
    specimen_sets: list[Record]
    session_start: dt.datetime
    members: dict[str, list[Record]] = field(default_factory=dict)
    attribution: list[Attribution] = field(default_factory=list)
    warnings: list[ConversionWarning] = field(default_factory=list)
    relative_path: str = ""

    @property
    def project(self) -> Record | None:
        """The first of the session's projects in the export (a session can belong to several)."""
        return self.projects[0] if self.projects else None

    def role(self, name: str) -> list[Record]:
        return self.members.get(name, [])

    def all_records(self) -> dict[tuple[str, str], tuple[Record, list[str]]]:
        """Every member record once, with the roles it has in this unit."""
        out: dict[tuple[str, str], tuple[Record, list[str]]] = {}
        for role, records in self.members.items():
            for record in records:
                if record.key in out:
                    out[record.key][1].append(role)
                else:
                    out[record.key] = (record, [role])
        return out


NOT_PERFORMED = frozenset({"planned", "cancelled"})


def is_performed(record: Record) -> bool:
    """True unless the record's status says it is planned or cancelled (no status: performed)."""
    return str(record.get("status") or "performed") not in NOT_PERFORMED


def not_performed_sessions(store: RecordStore) -> list[Record]:
    """Planned and cancelled sessions, which are not exported unless asked for by id or name."""
    return [s for s in _select_sessions(store, None, performed_only=False) if not is_performed(s)]


def interface_procedures(store: RecordStore, record: Record) -> list[Record]:
    """Procedures linked to the experimental interfaces of an acquisition or manipulation, by pk."""
    found: dict[str, Record] = {}
    for interface in store.m2m_records(record, "interfaces"):
        for procedure in store.referrers(interface, "modules.procedure", "interfaces"):
            found[procedure.pk] = procedure
    return [found[pk] for pk in sorted(found)]


@dataclass
class PlannedUnitError:
    session: Record
    code: str
    message: str
    subject_pk: str | None = None


def plan_units(
    store: RecordStore,
    *,
    sessions: list[str] | None = None,
    allow_no_subject: bool = False,
    infer_subjects: bool = True,
    subject_label_field: str = "name",
) -> tuple[list[ExportUnit], list[PlannedUnitError]]:
    """Plan the units of every session (or of the sessions named by id or name)."""
    planner = _Planner(store, allow_no_subject, infer_subjects, subject_label_field)
    selected = _select_sessions(store, sessions)
    units: list[ExportUnit] = []
    errors: list[PlannedUnitError] = []
    for session in selected:
        new_units, new_errors = planner.plan_session(session)
        units.extend(new_units)
        errors.extend(new_errors)
    _assign_paths(units, subject_label_field)
    return units, errors


def _select_sessions(store: RecordStore, wanted: list[str] | None, *, performed_only: bool = True) -> list[Record]:
    sessions = sorted(store.all("stem.session"), key=lambda r: (str(r.get("name") or ""), r.pk))
    if not wanted:
        return [s for s in sessions if is_performed(s)] if performed_only else sessions
    wanted_set = {str(item) for item in wanted}
    selected = [s for s in sessions if s.pk in wanted_set or str(s.get("name")) in wanted_set]
    found = {s.pk for s in selected} | {str(s.get("name")) for s in selected}
    missing = sorted(wanted_set - found)
    if missing:
        from ..errors import ConfigError

        raise ConfigError(f"session(s) not in this project's export: {', '.join(missing)}")
    return selected


class _Planner:
    def __init__(self, store: RecordStore, allow_no_subject: bool, infer_subjects: bool, label_field: str):
        self.store = store
        self.allow_no_subject = allow_no_subject
        self.infer_subjects = infer_subjects
        self.label_field = label_field
        self.projects = sorted(store.all("stem.project"), key=lambda p: (str(p.get("name") or ""), p.pk))

    # -- subjects ---------------------------------------------------------------------------

    def plan_session(self, session: Record) -> tuple[list[ExportUnit], list[PlannedUnitError]]:
        store = self.store
        errors: list[PlannedUnitError] = []
        if not is_performed(session):
            return [], [PlannedUnitError(session, "SESSION_NOT_PERFORMED",
                                         f"session '{session.get('name')}' is {session.get('status')}, not performed; "
                                         "no NWB file is written")]
        raw_start = session.get("date_time")
        if not raw_start:
            return [], [PlannedUnitError(session, "SESSION_START_TIME_MISSING",
                                         f"session '{session.get('name')}' has no date and time; NWB requires a "
                                         "session start time")]
        try:
            start = parse_datetime(raw_start)
        except ValueError as exc:
            return [], [PlannedUnitError(session, "SESSION_START_TIME_MISSING",
                                         f"session '{session.get('name')}' has an unreadable date_time: {exc}")]

        session_warnings: list[ConversionWarning] = []
        specimen_sets = store.m2m_records(session, "specimen_sets")
        subjects: dict[str, Record] = {}
        sets_by_subject: dict[str | None, list[Record]] = defaultdict(list)

        for ref in store.m2m(session, "subjects"):
            if ref.record is None:
                errors.append(PlannedUnitError(session, "SUBJECT_NOT_IN_EXPORT",
                                               f"session '{session.get('name')}' lists subject {ref.pk}, which is "
                                               "not in this project's export", subject_pk=ref.pk))
            else:
                subjects[ref.pk] = ref.record
        for specimen_set in specimen_sets:
            subject_ref = store.fk(specimen_set, "subject")
            if subject_ref is None:
                sets_by_subject[None].append(specimen_set)
            elif subject_ref.record is None:
                errors.append(PlannedUnitError(session, "SUBJECT_NOT_IN_EXPORT",
                                               f"specimen set '{specimen_set.get('name')}' belongs to subject "
                                               f"{subject_ref.pk}, which is not in this project's export",
                                               subject_pk=subject_ref.pk))
            else:
                subjects.setdefault(subject_ref.pk, subject_ref.record)
                sets_by_subject[subject_ref.pk].append(specimen_set)

        if not subjects and not errors and self.infer_subjects:
            inferred = self._infer_subjects(session)
            if inferred:
                subjects = inferred
                session_warnings.append(make_warning(
                    "SUBJECTS_INFERRED",
                    f"session '{session.get('name')}' lists no subjects; using "
                    f"{', '.join(sorted(str(s.get('name')) for s in inferred.values()))} from its linked records",
                    label=session.label, pk=session.pk,
                ))

        if len(subjects) > 1:
            session_warnings.append(make_warning(
                "MULTIPLE_SUBJECTS",
                f"session '{session.get('name')}' has {len(subjects)} subjects; writing one file per subject",
                label=session.label, pk=session.pk,
            ))

        units: list[ExportUnit] = []
        if not subjects:
            if errors:
                return [], errors
            if not self.allow_no_subject:
                return [], [PlannedUnitError(session, "NO_SUBJECT",
                                             f"session '{session.get('name')}' has no subject; use "
                                             "--allow-no-subject to export it without one")]
            unit = self._build_unit(session, None, sets_by_subject.get(None, []), start, n_subjects=0)
            unit.warnings.insert(0, make_warning("NO_SUBJECT_ALLOWED", label=session.label, pk=session.pk))
            units.append(unit)
        else:
            ordered = sorted(subjects.values(), key=lambda s: (str(s.get("name") or ""), s.pk))
            for subject in ordered:
                unit = self._build_unit(session, subject, sets_by_subject.get(subject.pk, []), start,
                                        n_subjects=len(ordered))
                units.append(unit)
        for unit in units:
            unit.warnings[:0] = session_warnings
        return units, errors

    def _infer_subjects(self, session: Record) -> dict[str, Record]:
        store = self.store
        found: dict[str, Record] = {}
        for behavior in store.referrers(session, "modules.behavior", "session"):
            for subject in store.m2m_records(behavior, "subjects"):
                found[subject.pk] = subject
        for label in ("modules.dataacquisition", "modules.manipulation"):
            for record in store.referrers(session, label, "session"):
                for subject in self._linked_subjects(record):
                    found[subject.pk] = subject
        return found

    def _linked_subjects(self, record: Record) -> list[Record]:
        """Subjects an acquisition or manipulation is tied to through its interfaces (and their specimen sets)."""
        store = self.store
        subjects: dict[str, Record] = {}
        for interface in store.m2m_records(record, "interfaces"):
            subject = store.fk_record(interface, "subject")
            if subject is None:
                specimen_set = store.fk_record(interface, "specimen_set")
                subject = store.fk_record(specimen_set, "subject") if specimen_set else None
            if subject:
                subjects[subject.pk] = subject
        return list(subjects.values())

    # -- one unit ---------------------------------------------------------------------------

    def _build_unit(self, session: Record, subject: Record | None, specimen_sets: list[Record],
                    start: dt.datetime, n_subjects: int) -> ExportUnit:
        store = self.store
        unit = ExportUnit(
            unit_id=f"{session.pk}__{subject.pk if subject else 'nosubject'}",
            session=session,
            subject=subject,
            projects=[p for p in self.projects if p.pk in set(map(str, session.get("projects") or []))]
            or list(self.projects),
            specimen_sets=specimen_sets,
            session_start=start,
        )
        members: dict[str, dict[str, Record]] = defaultdict(dict)

        def add(role: str, record: Record | None) -> None:
            if record is not None:
                members[role][record.pk] = record

        def attribute(record: Record, decision: Decision, reason: str) -> None:
            unit.attribution.append(Attribution(label=record.label, pk=record.pk, decision=decision, reason=reason))

        add("session", session)
        for project in unit.projects:
            add("project", project)
            for publication in store.m2m_records(project, "publications"):
                add("publication", publication)
                add("journal", store.fk_record(publication, "journal"))
        if subject is not None:
            add("subject", subject)
            add("species", store.fk_record(subject, "species"))
            add("strain", store.fk_record(subject, "strain"))
        for specimen_set in specimen_sets:
            add("specimen_set", specimen_set)

        # Acquisitions and manipulations
        for label, role in (("modules.dataacquisition", "dataacquisition"), ("modules.manipulation", "manipulation")):
            for record in store.referrers(session, label, "session"):
                linked = self._linked_subjects(record)
                if not linked:
                    add(role, record)
                    if n_subjects > 1:
                        attribute(record, "shared", "linked to no subject; included for every subject of the session")
                        unit.warnings.append(make_warning(
                            "RECORD_SHARED_ACROSS_SUBJECTS",
                            f"{_kind(label)} {_name(record)} is linked to no subject and is included for each of "
                            f"the session's {n_subjects} subjects",
                            label=label, pk=record.pk,
                        ))
                    else:
                        attribute(record, "included", "part of the session")
                elif subject is not None and subject.pk in {s.pk for s in linked}:
                    add(role, record)
                    attribute(record, "included", "linked to the subject through its procedures or interfaces")
                elif subject is None:
                    attribute(record, "excluded", "linked to a subject; this unit has none")
                else:
                    attribute(record, "excluded", "linked to another subject of the session")

        # Behaviors
        for behavior in store.referrers(session, "modules.behavior", "session"):
            behavior_subjects = {ref.pk for ref in store.m2m(behavior, "subjects")}
            if not behavior_subjects:
                add("behavior", behavior)
                if n_subjects > 1:
                    attribute(behavior, "shared", "lists no subjects; included for every subject of the session")
                    unit.warnings.append(make_warning(
                        "RECORD_SHARED_ACROSS_SUBJECTS",
                        f"behavior {behavior.pk} lists no subjects and is included for each of the session's "
                        f"{n_subjects} subjects",
                        label=behavior.label, pk=behavior.pk,
                    ))
                else:
                    attribute(behavior, "included", "part of the session")
            elif subject is not None and subject.pk in behavior_subjects:
                add("behavior", behavior)
                attribute(behavior, "included", "lists the subject")
            else:
                attribute(behavior, "excluded", "lists other subjects")

        included_das = set(members["dataacquisition"])
        included_manips = set(members["manipulation"])
        included_behaviors = set(members["behavior"])

        # Epochs
        for epoch in store.referrers(session, "stem.epoch", "session"):
            behavior_pk = epoch.get("behavior")
            da_pks = {ref.pk for ref in store.m2m(epoch, "dataacquisitions")}
            manip_pks = {ref.pk for ref in store.m2m(epoch, "manipulations")}
            links = ({str(behavior_pk)} if behavior_pk else set()) | da_pks | manip_pks
            if not links:
                add("epoch", epoch)
                attribute(epoch, "included", "part of the session; links no records")
            elif (
                (behavior_pk and str(behavior_pk) in included_behaviors)
                or da_pks & included_das
                or manip_pks & included_manips
            ):
                add("epoch", epoch)
                attribute(epoch, "included", "links records included for this subject")
            else:
                attribute(epoch, "excluded", "links only records of other subjects")

        # Procedures of the subject
        linked_procedures: set[str] = set()
        for record in [*members["dataacquisition"].values(), *members["manipulation"].values()]:
            linked_procedures.update(p.pk for p in interface_procedures(store, record))
        not_performed = 0

        def not_performed_procedure(procedure: Record, role: str) -> bool:
            nonlocal not_performed
            if is_performed(procedure):
                return False
            add(role, procedure)
            attribute(procedure, "excluded", f"{procedure.get('status')}, not performed; kept in the manifest")
            not_performed += 1
            return True

        if subject is not None:
            after_session = 0
            for procedure in store.referrers(subject, "modules.procedure", "subject"):
                when = _safe_datetime(procedure.get("date_time")) if procedure.get("date_time") else None
                if not_performed_procedure(procedure, "procedure_not_performed"):
                    continue
                if procedure.pk in linked_procedures:
                    add("procedure", procedure)
                    attribute(procedure, "included", "linked to an interface of an included acquisition or "
                                                     "manipulation")
                elif when is None:
                    add("procedure", procedure)
                    attribute(procedure, "included", "no (readable) date; treated as before the session")
                    unit.warnings.append(make_warning(
                        "PROCEDURE_DATE_UNKNOWN",
                        f"procedure {procedure.get('type')} ({procedure.pk}) has no date; "
                        "treated as before the session",
                        label=procedure.label, pk=procedure.pk,
                    ))
                elif when <= start:
                    add("procedure", procedure)
                    attribute(procedure, "included", "performed before the session")
                else:
                    add("procedure_after_session", procedure)
                    attribute(procedure, "excluded", "performed after the session start; kept in the manifest")
                    after_session += 1
            if after_session:
                unit.warnings.append(make_warning(
                    "PROCEDURE_AFTER_SESSION",
                    f"{after_session} procedure(s) of the subject happened after the session; they are left out of "
                    "the NWB file and kept in the manifest",
                    label=subject.label, pk=subject.pk,
                ))
        for pk in sorted(linked_procedures - set(members["procedure"]) - set(members["procedure_not_performed"])):
            linked_procedure = store.get("modules.procedure", pk)
            if linked_procedure is not None and not not_performed_procedure(linked_procedure,
                                                                             "procedure_not_performed"):
                add("procedure", linked_procedure)
                attribute(linked_procedure, "included", "linked to an interface of an included acquisition or "
                                                        "manipulation")

        procedures = list(members["procedure"].values())

        # Procedure episodes, stages, logs and through records
        for procedure in procedures:
            add("procedure_episode", store.fk_record(procedure, "procedure_episode"))
            add("protocol", store.fk_record(procedure, "protocol"))
            for license_record in store.m2m_records(procedure, "licenses"):
                add("license", license_record)
            for stage in store.referrers(procedure, "modules.procedurestage", "procedure"):
                add("procedure_stage", stage)
            for log in store.referrers(procedure, "modules.procedurelog", "procedure"):
                add("procedure_log", log)
            for link in store.referrers(procedure, "modules.procedureinterface", "procedure"):
                add("procedure_interface", link)
        for episode in list(members["procedure_episode"].values()):
            add("protocol", store.fk_record(episode, "protocol"))
            for license_record in store.m2m_records(episode, "licenses"):
                add("license", license_record)
            for person in store.referrers(episode, "modules.episodepersonnel", "episode"):
                add("episode_personnel", person)

        # Interfaces, equipment, through records of acquisitions and manipulations
        for record in members["dataacquisition"].values():
            for interface in store.m2m_records(record, "interfaces"):
                add("interface", interface)
            for link in store.referrers(record, "modules.dataacquisitioninterface", "dataacquisition"):
                add("dataacquisition_interface", link)
        for record in members["manipulation"].values():
            for interface in store.m2m_records(record, "interfaces"):
                add("interface", interface)
            for link in store.referrers(record, "modules.manipulationinterface", "manipulation"):
                add("manipulation_interface", link)
        if subject is not None:
            for interface in store.referrers(subject, "modules.experimentalinterface", "subject"):
                if interface.pk in members["interface"]:
                    continue
                if _in_place(interface, start):
                    add("interface_in_place", interface)
                    attribute(interface, "included", "in place at the session start; kept in the manifest")

        # Specimens (ex vivo)
        for specimen_set in specimen_sets:
            for specimen in store.referrers(specimen_set, "stem.specimen", "specimen_set"):
                add("specimen", specimen)
            for specimen_procedure in store.referrers(specimen_set, "modules.specimenprocedure", "specimen_set"):
                if not_performed_procedure(specimen_procedure, "specimen_procedure_not_performed"):
                    continue
                add("specimen_procedure", specimen_procedure)
                add("protocol", store.fk_record(specimen_procedure, "protocol"))
                for stage in store.referrers(specimen_procedure, "modules.procedurestage", "specimen_procedure"):
                    add("procedure_stage", stage)
            for interface in store.referrers(specimen_set, "modules.experimentalinterface", "specimen_set"):
                if interface.pk not in members["interface"]:
                    add("interface_in_place", interface)

        # Equipment and materials
        equipment_sources = [
            *members["dataacquisition"].values(), *members["manipulation"].values(),
            *procedures, *members["interface"].values(), *members["specimen_procedure"].values(),
        ]
        for record in equipment_sources:
            for equipment in store.m2m_records(record, "equipment"):
                add("equipment", equipment)
        for equipment in members["equipment"].values():
            add("hardwaredevice", store.fk_record(equipment, "hardwaredevice"))
            add("consumable", store.fk_record(equipment, "consumable"))
            add("setup", store.fk_record(equipment, "setup"))
        for behavior in members["behavior"].values():
            add("setup", store.fk_record(behavior, "setup"))
            add("behavioralassay", store.fk_record(behavior, "behavioralassay"))

        material_parents = (
            [("procedure", p) for p in procedures]
            + [("experimental_interface", i) for i in [*members["interface"].values(),
                                                        *members["interface_in_place"].values()]]
            + [("specimen_procedure", s) for s in members["specimen_procedure"].values()]
        )
        for field_name, parent in material_parents:
            for usage in store.referrers(parent, "modules.materialusage", field_name):
                add("material_usage", usage)
        for interface in [*members["interface"].values(), *members["interface_in_place"].values()]:
            add("material_usage", store.fk_record(interface, "source_material_usage"))
        for usage in list(members["material_usage"].values()):
            stock = store.fk_record(usage, "consumable_stock")
            add("consumable_stock", stock)
            add("consumable", store.fk_record(usage, "consumable"))
            if stock is not None:
                add("consumable", store.fk_record(stock, "consumable"))
                add("inventory", store.fk_record(stock, "inventory"))

        # Licenses of the subject, protocols' licenses, data storage
        if subject is not None:
            for license_record in store.m2m_records(subject, "licenses"):
                add("license", license_record)
        for protocol in list(members["protocol"].values()):
            for license_record in store.m2m_records(protocol, "licenses"):
                add("license", license_record)
        for storage in store.m2m_records(session, "datastorage"):
            add("datastorage", storage)
        for link in store.referrers(session, "stem.sessiondatastorage", "session"):
            add("session_datastorage", link)

        if not_performed:
            unit.warnings.append(make_warning(
                "PROCEDURE_NOT_PERFORMED",
                f"{not_performed} procedure(s) or specimen procedure(s) are planned or cancelled; they are left out "
                "of the NWB file and kept in the manifest",
                label=(subject or session).label, pk=(subject or session).pk,
            ))

        # Logs and their entries (weights, observations, impedances, depth adjustments)
        if subject is not None:
            for log in store.referrers(subject, "modules.subjectlog", "subject"):
                add("subject_log", log)
        for log in [*members["subject_log"].values(), *members["procedure_log"].values()]:
            for entry in store.log_entries(log):
                add("log_entry", entry)

        # People named on the included records (names only; the export has no other user data)
        for procedure in procedures:
            add("person", store.fk_record(procedure, "performed_by"))
        for person in members["episode_personnel"].values():
            add("person", store.fk_record(person, "person"))
        for entry in members["log_entry"].values():
            add("person", store.fk_record(entry, "performedBy"))

        # Shared catalog entries the included records reference
        region_sources = [*procedures, *members["interface"].values(), *members["interface_in_place"].values(),
                          *members["specimen_procedure"].values(), *specimen_sets]
        for record in region_sources:
            for region in store.m2m_records(record, "target_regions"):
                add("region", region)
        for procedure in procedures:
            add("atlas", store.fk_record(procedure, "anatomical_reference"))
            add("coordinate_transform", store.fk_record(procedure, "coordinate_transform"))
        for region in members["region"].values():
            add("atlas", store.fk_record(region, "reference"))
        for record in [*members["consumable"].values(), *members["hardwaredevice"].values()]:
            add("supplier", store.fk_record(record, "supplier"))
        for setup in members["setup"].values():
            add("setup_type", store.fk_record(setup, "setup_type"))
        for assay in members["behavioralassay"].values():
            paradigm = store.fk_record(assay, "behavioral_paradigm")
            add("behavioral_paradigm", paradigm)
            if paradigm is not None:
                add("behavioral_category", store.fk_record(paradigm, "category"))
        for license_record in members["license"].values():
            add("regulatory_authority", store.fk_record(license_record, "regulatory_authority"))

        unit.members = {
            role: [records[pk] for pk in sorted(records)] for role, records in members.items() if records
        }
        return unit


def _safe_datetime(value: object) -> dt.datetime | None:
    try:
        return parse_datetime(str(value))
    except ValueError:
        return None


def _in_place(interface: Record, start: dt.datetime) -> bool:
    installed = _safe_datetime(interface.get("installed_at")) if interface.get("installed_at") else None
    removed = _safe_datetime(interface.get("removed_at")) if interface.get("removed_at") else None
    if installed is None or installed > start:
        return False
    return removed is None or removed > start


def _kind(label: str) -> str:
    return {"modules.dataacquisition": "data acquisition", "modules.manipulation": "manipulation"}.get(label, label)


def _name(record: Record) -> str:
    return f"{record.get('type') or ''} ({record.pk})".strip()


def _assign_paths(units: list[ExportUnit], label_field: str) -> None:
    """``sub-<subject>/sub-<subject>_ses-<session>.nwb``; ``ses-<session>.nwb`` without a subject."""
    paths: dict[str, list[ExportUnit]] = defaultdict(list)
    for unit in units:
        paths[_path_for(unit, label_field, suffix=False)].append(unit)
    for path, group in paths.items():
        if len(group) == 1:
            group[0].relative_path = path
            continue
        for unit in group:
            unit.relative_path = _path_for(unit, label_field, suffix=True)
            unit.warnings.append(make_warning(
                "FILENAME_COLLISION",
                f"{path} would be used by {len(group)} units; wrote {unit.relative_path}",
                label=unit.session.label, pk=unit.session.pk,
            ))


def subject_label(subject: Record, label_field: str) -> str:
    value = subject.get(label_field) if label_field != "name" else None
    return str(value or subject.get("name") or subject.pk)


def _path_for(unit: ExportUnit, label_field: str, suffix: bool) -> str:
    session_label = dandi_label(str(unit.session.get("name") or unit.session.pk))
    if suffix:
        session_label = f"{session_label}-{unit.session.pk[:8]}"
    if unit.subject is None:
        return f"ses-{session_label}.nwb"
    sub = dandi_label(subject_label(unit.subject, label_field))
    if suffix:
        sub = f"{sub}-{unit.subject.pk[:8]}"
    return f"sub-{sub}/sub-{sub}_ses-{session_label}.nwb"
