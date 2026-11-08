"""
Produce a contract export with the BrainSTEM server's own export builder.

Creates a small synthetic project in a fresh, throwaway SQLite database using the server's
models, exports it with ``stem.services.project_export.build_project_export`` and writes the
JSON. The committed results (tests/fixtures/exports/server_contract_<version>*.json) prove the exporter
reads what the server really writes (value encodings, link lists, labels).

Run with the BrainSTEM server's Python environment, against a checkout of the branch with the
project export (never against a real database: the database file is created in a temporary
directory)::

    /path/to/brainstem/.venv/bin/python scripts/make_contract_export.py /path/to/brainstem-checkout \
        tests/fixtures/exports/server_contract_2_2.json \
        --session-output tests/fixtures/exports/server_contract_2_2_session.json
"""

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

PLACEHOLDER_ENV = {
    "SECRET_KEY": "contract-export-only",
    "DEBUG_VALUE": "False",
    "SITE_URL": "http://localhost:8000",
    "MAILGUN_API_KEY": "x",
    "AWS_ACCESS_KEY_ID": "x",
    "AWS_SECRET_ACCESS_KEY": "x",
    "AWS_STORAGE_BUCKET_NAME": "x",
    "RECAPTCHA_SITE_KEY": "x",
    "RECAPTCHA_SECRET_KEY": "x",
    "DISABLE_DEBUG_TOOLBAR": "1",
}

UTC = dt.timezone.utc


def setup_django(checkout: Path, database: Path) -> None:
    sys.path.insert(0, str(checkout))
    os.chdir(checkout)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brainstem.settings")
    os.environ.pop("DATABASE_URL", None)
    for key, value in PLACEHOLDER_ENV.items():
        os.environ.setdefault(key, value)
    import django
    from django.conf import settings

    settings.DATABASES["default"]["NAME"] = str(database)
    django.setup()
    from django.core.management import call_command

    call_command("migrate", verbosity=0, interactive=False)
    # BrainSTEM creates its object permissions (read_project, read_setup, ...) in a setup command,
    # not in migrations; create the ones the export checks.
    from django.apps import apps
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    for label in ("stem.project", "personal_attributes.setup", "personal_attributes.behavioralassay",
                  "personal_attributes.datastorage", "personal_attributes.license", "personal_attributes.protocol",
                  "personal_attributes.inventory"):
        model = apps.get_model(label)
        name = model._meta.model_name
        Permission.objects.get_or_create(codename=f"read_{name}", content_type=ContentType.objects.get_for_model(model),
                                         defaults={"name": f"Can read {name}"})


def build_project():
    from django.apps import apps
    from guardian.shortcuts import assign_perm
    from modules.models.Behavior import Behavior
    from modules.models.DataAcquisition import DataAcquisition
    from modules.models.Equipment import Equipment
    from modules.models.ExperimentalInterface import ExperimentalInterface
    from modules.models.Manipulation import Manipulation
    from modules.models.Procedure import Procedure
    from personal_attributes.models.BehavioralAssay import BehavioralAssay
    from personal_attributes.models.Setup import Setup
    from stem.models.Epoch import Epoch
    from stem.models.Project import Project
    from stem.models.Session import Session
    from stem.models.Subject import Subject
    from taxonomies.models.Species import Species
    from taxonomies.models.Strain import Strain
    from users.models.User import User

    # Allow reruns on a reused throwaway database
    ProcedureInterface = apps.get_model("modules.procedureinterface")

    for model in (Epoch, DataAcquisition, Manipulation, Behavior):
        model.objects.filter(session__name="Contract session").delete()
    ProcedureInterface.objects.filter(procedure__subject__name="ContractMouse").delete()
    ExperimentalInterface.objects.filter(subject__name="ContractMouse").delete()
    Procedure.objects.filter(subject__name="ContractMouse").delete()
    Equipment.objects.filter(name="Contract amplifier").delete()
    Session.objects.filter(name="Contract session").delete()
    Subject.objects.filter(name="ContractMouse").delete()
    from modules.models.ModulesLogEntry import ModulesLogEntry
    from modules.models.SubjectLog import SubjectLog

    logs = SubjectLog.objects.filter(subject__name="ContractMouse")
    ModulesLogEntry.objects.filter(object_id__in=list(logs.values_list("pk", flat=True))).delete()
    logs.delete()
    Project.objects.filter(name__in=["Contract project", "Contract project B"]).delete()
    Setup.objects.filter(name="Contract rig").delete()
    BehavioralAssay.objects.filter(name="Contract assay").delete()
    user, _ = User.objects.get_or_create(email="contract@example.org",
                                         defaults={"first_name": "Contract", "last_name": "Export"})
    project = Project.objects.create(name="Contract project", description="<p>Server contract fixture.</p>",
                                     user=user)
    for perm in ("read_project", "change_project"):
        assign_perm(perm, user, project)
    project.tags.add("contract")
    second = Project.objects.create(name="Contract project B", description="Shares the session.", user=user)
    assign_perm("read_project", user, second)

    from dissemination.models.Journal import Journal
    from dissemination.models.Publication import Publication
    from resources.models.HardwareDevice import HardwareDevice
    from resources.models.Supplier import Supplier
    from taxonomies.models.AnatomicalReference import AnatomicalReference
    from taxonomies.models.AnatomicalRegion import AnatomicalRegion

    journal, _ = Journal.objects.get_or_create(name="Contract Journal", defaults={"user": user})
    publication, _ = Publication.objects.get_or_create(title="Contract publication", journal=journal,
                                                       defaults={"doi": "10.0000/contract.1", "user": user,
                                                                 "publication_date": dt.date(2025, 1, 1)})
    project.publications.add(publication)
    supplier, _ = Supplier.objects.get_or_create(name="Contract Supplier", defaults={"user": user})
    headstage, _ = HardwareDevice.objects.get_or_create(
        name="Contract headstage", defaults={"type": "Amplifier", "supplier": supplier, "user": user,
                                             "type_json": {"productId": "C-1"}})
    atlas = AnatomicalReference.objects.get(code="allen_mouse_ccfv3_2017")
    region, _ = AnatomicalRegion.objects.get_or_create(acronym="CA1", reference=atlas,
                                                       defaults={"name": "Field CA1", "user": user})

    species, _ = Species.objects.get_or_create(name="Mus musculus", defaults={"user": user})
    strain = Strain.objects.filter(species=species).first() or Strain.objects.create(
        name="C57BL/6J", species=species, user=user)
    subject = Subject.objects.create(name="ContractMouse", species=species, strain=strain, sex="F",
                                     birth_date=dt.date(2024, 1, 2), user=user)
    subject.projects.add(project)
    session = Session.objects.create(name="Contract session", description="<p>Recorded.</p>",
                                     date_time=dt.datetime(2024, 4, 1, 10, 0, 0, 123456, tzinfo=UTC), user=user)
    session.projects.add(project, second)
    session.subjects.add(subject)

    implant = Procedure.objects.create(
        type="SiliconProbeImplant", subject=subject, user=user, performed_by=user,
        date_time=dt.datetime(2024, 3, 1, 11, 0, tzinfo=UTC),
        type_json={"duraHandling": "dura_removed"},
        coordinates="Stereotaxic_BregmaBrainSurface",
        coordinates_json={"apCoordinate": {"value": -2.0, "unit": "mm"}, "mlCoordinate": {"value": 1.5, "unit": "mm"},
                          "depth": {"value": 1.0, "unit": "mm"}},
    )
    # Saving an implant procedure creates its experimental interface (linked as "created"); use that one,
    # as real records do.
    probe = ExperimentalInterface.objects.filter(subject=subject, type="SiliconProbe").first()
    if probe is None:
        probe = ExperimentalInterface.objects.create(name="Contract probe", type="SiliconProbe", subject=subject,
                                                     persistence="chronic", user=user)
    probe.type_json = {"deviceIdentifier": "SN-1"}
    probe.installed_at = dt.datetime(2024, 3, 1, 11, 30, tzinfo=UTC)
    probe.save()
    implant.target_regions.add(region)
    probe.target_regions.add(region)
    weights = SubjectLog.objects.create(type="Weighing", subject=subject, user=user)
    ModulesLogEntry.objects.create(log=weights, date_time=dt.datetime(2024, 3, 31, 9, tzinfo=UTC), user=user,
                                   type_json={"weight": {"value": 25.3, "unit": "g"}}, performedBy=user)
    setup = Setup.objects.create(name="Contract rig", user=user)
    for perm in ("read_setup",):
        assign_perm(perm, user, setup)
    amplifier = Equipment.objects.create(name="Contract amplifier", type="Amplifier", setup=setup, user=user,
                                         hardwaredevice=headstage)
    recording = DataAcquisition.objects.create(
        session=session, type="ExtracellularEphys", user=user, order=0,
        type_json={"fileName": "contract.dat", "nChannels": 32, "sr": {"value": 20000, "unit": "Hz"},
                   "electrodeGroups": [{"label": "shank1", "channels": list(range(32))}]})
    recording.interfaces.add(probe)
    recording.equipment.add(amplifier)
    stimulation = Manipulation.objects.create(
        session=session, type="ElectricalStimulation", user=user, order=0,
        type_json=[{"amplitude": {"value": 10, "unit": "µA"}}])
    from taxonomies.models.BehavioralParadigm import BehavioralParadigm

    assay = BehavioralAssay.objects.create(name="Contract assay", user=user,
                                           behavioral_paradigm=BehavioralParadigm.objects.order_by("name").first())
    assign_perm("read_behavioralassay", user, assay)
    behavior = Behavior.objects.create(session=session, setup=setup, behavioralassay=assay, user=user, order=0)
    behavior.subjects.add(subject)
    epoch = Epoch.objects.create(name="run", session=session, start=dt.timedelta(0),
                                 end=dt.timedelta(minutes=30, microseconds=500000), behavior=behavior, user=user)
    epoch.dataacquisitions.add(recording)
    epoch.manipulations.add(stimulation)
    Epoch.objects.create(name="late", session=session, start=dt.timedelta(days=1, hours=2),
                         end=dt.timedelta(days=1, hours=3), user=user)
    return user, project, session


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path, help="the project export")
    parser.add_argument("--session-output", type=Path, help="also write the export of the contract session here")
    parser.add_argument("--database", type=Path, help="SQLite file to use (default: a temporary one); must be "
                                                         "a throwaway database")
    args = parser.parse_args()
    output = args.output.resolve()
    session_output = args.session_output.resolve() if args.session_output else None  # before chdir
    with tempfile.TemporaryDirectory() as tmp:
        database = args.database.resolve() if args.database else Path(tmp) / "contract.sqlite3"
        setup_django(args.checkout.resolve(), database)
        from stem.services.project_export import build_project_export

        user, project, session = build_project()
        exports = [(output, build_project_export(user, project))]
        if session_output:
            exports.append((session_output, build_project_export(user, None, session=session)))
    for path, payload in exports:
        payload["export_info"]["exported_at"] = "2025-01-15T12:00:00.000000+00:00"  # stable fixture
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path} ({payload['export_info']['record_count']} records)")


if __name__ == "__main__":
    main()
