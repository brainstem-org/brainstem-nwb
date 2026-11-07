"""
Export orchestration: project export -> manifest -> NWB files -> validation reports.

One unit failing (an unreadable value, a write error) does not stop the others; it is marked
``failed`` in the manifest with the error, and the exit code reports a partial export.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import traceback
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ._version import (
    KNOWN_EXPORT_MINOR,
    MANIFEST_SCHEMA_VERSION,
    MAPPING_VERSION,
    SUPPORTED_DATA_MODELS,
    SUPPORTED_EXPORT_MAJOR,
    __version__,
)
from .config import ExportOptions, build_options
from .errors import BrainstemNwbError, ConfigError
from .manifest.io import MANIFEST_FILENAME, read_manifest, write_manifest
from .manifest.models import (
    Coverage,
    DataModelInfo,
    ExporterInfo,
    ExternalRefCount,
    Manifest,
    ProjectInfo,
    RecordRef,
    RunInfo,
    SchemaInfo,
    SourceInfo,
    Summary,
    Unit,
    UnitErrorEntry,
    UnitFailure,
    UnitOutput,
)
from .manifest.warnings import make_warning
from .mapping.pipeline import map_unit
from .normalize.kv import key_values, repository_links
from .normalize.text import html_to_text
from .normalize.timeutil import parse_datetime
from .normalize.units import ExportUnit, not_performed_sessions, plan_units
from .retrieval.loader import ProjectExport, is_newer_minor, load_export
from .store.graph import Record, RecordStore
from .store.inventory import Inventory, get_inventory
from .validation import ValidationReport, render_text, tool_versions, validate_file
from .validation.report import REPORT_JSON, REPORT_TEXT

FailOn = Literal["error", "warning"]

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_VALIDATION = 4


@dataclass
class ExportResult:
    manifest: Manifest
    report: ValidationReport | None = None
    output_dir: Path | None = None
    manifest_path: Path | None = None
    files: list[Path] = field(default_factory=list)
    exit_code: int = EXIT_OK


# ------------------------------------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------------------------------------


def export_project(
    project_id: str | None = None,
    output_dir: str | Path = "nwb",
    *,
    export_file: str | Path | None = None,
    export: ProjectExport | dict[str, Any] | None = None,
    sessions: list[str] | None = None,
    config: str | Path | dict[str, Any] | ExportOptions | None = None,
    dry_run: bool = False,
    validate: bool = True,
    allow_no_subject: bool | None = None,
    infer_subjects: bool | None = None,
    reproducible: bool | None = None,
    extensions: list[str] | None = None,
    herd: bool | None = None,
    embed_schemas: bool | None = None,
    overwrite: bool = False,
    fail_fast: bool = False,
    inspector_config: str | None = "dandi",
    fail_on: FailOn = "error",
    token: str | None = None,
    url: str | None = None,
    background: bool = True,
    allow_device_flow: bool = False,
    headless: bool = True,
    save_export: bool = True,
) -> ExportResult:
    """
    Export every session of a BrainSTEM project (or the ``sessions`` named by id or name) to
    metadata-only NWB files in ``output_dir``: one file per session and subject, plus
    ``brainstem-nwb-manifest.json`` and the validation reports.

    The records come from ``export_file`` (a downloaded project export, .json or .json.gz), an
    already loaded ``export``, or are fetched from BrainSTEM for ``project_id``. With ``dry_run``
    only the manifest is written.
    """
    output = Path(output_dir)
    if reproducible is None and os.environ.get("SOURCE_DATE_EPOCH"):
        reproducible = True
    options = build_options(config, sessions=sessions, allow_no_subject=allow_no_subject,
                            infer_subjects=infer_subjects, reproducible=reproducible, extensions=extensions,
                            herd=herd, embed_schemas=embed_schemas)
    project_export = _obtain_export(project_id, export_file, export, output, token=token, url=url,
                                    background=background, allow_device_flow=allow_device_flow, headless=headless,
                                    save_export=save_export and not dry_run, sessions=sessions)
    if project_id and project_export.project_ids and str(project_id) not in project_export.project_ids:
        raise ConfigError(f"the export is of project(s) {', '.join(project_export.project_ids)}, not {project_id}")

    manifest, units = _plan(project_export, options, dry_run=dry_run, schema_server=url)
    result = ExportResult(manifest=manifest, output_dir=output)
    if not dry_run:
        report = ValidationReport(tool_versions=tool_versions(), inspector_config=inspector_config)
        for unit_model, export_unit in units:
            _write_unit(unit_model, export_unit, output, overwrite=overwrite, fail_fast=fail_fast)
            if validate and unit_model.status in ("written", "up_to_date"):
                path = output / unit_model.output.relative_path
                report.files.append(validate_file(path, unit=unit_model, inspector_config=inspector_config,
                                                  display_path=unit_model.output.relative_path))
            if unit_model.status in ("written", "up_to_date"):
                result.files.append(output / unit_model.output.relative_path)
        if validate:
            result.report = report.finalize()
            _write_report(result.report, output)
    _summarize(manifest)
    result.manifest_path = write_manifest(manifest, output / MANIFEST_FILENAME)
    result.exit_code = _exit_code(manifest, result.report, fail_on)
    return result


def export_session(session_id: str, output_dir: str | Path = "nwb", *, project_id: str | None = None,
                   **kwargs: Any) -> ExportResult:
    """
    Export one session (by id or name). Without an export file or project id, the session export is
    fetched from BrainSTEM (needs ``BrainstemClient.export_session``; pass a session id, not a name).
    """
    return export_project(project_id, output_dir, sessions=[session_id], **kwargs)


def build_manifest(
    source: str | Path | ProjectExport | dict[str, Any],
    *,
    sessions: list[str] | None = None,
    config: str | Path | dict[str, Any] | ExportOptions | None = None,
    allow_no_subject: bool | None = None,
    infer_subjects: bool | None = None,
    reproducible: bool | None = None,
    extensions: list[str] | None = None,
    herd: bool | None = None,
    embed_schemas: bool | None = None,
    schema_server: str | None = None,
) -> Manifest:
    """Build the conversion manifest (what would be exported) without writing anything."""
    project_export = source if isinstance(source, ProjectExport) else load_export(source)
    options = build_options(config, sessions=sessions, allow_no_subject=allow_no_subject,
                            infer_subjects=infer_subjects, reproducible=reproducible, extensions=extensions,
                            herd=herd, embed_schemas=embed_schemas)
    manifest, _ = _plan(project_export, options, dry_run=True, schema_server=schema_server)
    _summarize(manifest)
    return manifest


def validate_output(
    path: str | Path,
    *,
    manifest: str | Path | Manifest | None = None,
    inspector_config: str | None = "dandi",
    report_dir: str | Path | None = None,
) -> ValidationReport:
    """
    Validate exported NWB files: a file, or a directory (searched recursively). The manifest is
    found next to the files when not given, enabling the checks against it.
    """
    path = Path(path)
    root = path if path.is_dir() else path.parent
    if manifest is None and (root / MANIFEST_FILENAME).exists():
        manifest = root / MANIFEST_FILENAME
    loaded = manifest if isinstance(manifest, Manifest) else read_manifest(Path(manifest)) if manifest else None
    by_path = {u.output.relative_path: u for u in loaded.units} if loaded else {}
    files = sorted(path.rglob("*.nwb")) if path.is_dir() else [path]
    report = ValidationReport(tool_versions=tool_versions(), inspector_config=inspector_config)
    for file in files:
        relative = file.relative_to(root).as_posix()
        report.files.append(validate_file(file, unit=by_path.get(relative), inspector_config=inspector_config,
                                          display_path=relative))
    report.finalize()
    if report_dir is not None:
        _write_report(report, Path(report_dir))
    return report


# ------------------------------------------------------------------------------------------------
# Steps
# ------------------------------------------------------------------------------------------------


def _obtain_export(project_id: str | None, export_file: str | Path | None,
                   export: ProjectExport | dict[str, Any] | None, output: Path, *, save_export: bool,
                   sessions: list[str] | None = None, **fetch_kwargs: Any) -> ProjectExport:
    given = [x is not None for x in (export_file, export)]
    if sum(given) > 1:
        raise ConfigError("give either an export file or an export, not both")
    if export is not None:
        return export if isinstance(export, ProjectExport) else load_export(export)
    if export_file is not None:
        return load_export(export_file)
    session_id = sessions[0] if sessions and len(sessions) == 1 else None
    if not project_id and not session_id:
        raise ConfigError("give a project id or one session id (to fetch the export from BrainSTEM), or an export file")
    from .retrieval.api import fetch_export

    # One session: fetch the session export, which is smaller and needs only read access.
    target = f"session-{session_id}" if session_id else str(project_id)
    save_to = None
    if save_export:
        save_to = output / "source" / f"brainstem-export-{_safe(target)}.json.gz"
    fetched = fetch_export(None if session_id else project_id, session_id=session_id, save_to=save_to,
                           **fetch_kwargs)
    if save_to is not None:
        stamped = save_to.with_name(f"brainstem-export-{_safe(target)}-{_safe(fetched.exported_at or 'unknown')}"
                                    ".json.gz")
        save_to.replace(stamped)
        from .retrieval.loader import SourceRef, with_source

        fetched = with_source(fetched, SourceRef(kind="api", name=stamped.name, host=fetched.source.host))
    return fetched


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", text).strip("-")


def _plan(
    export: ProjectExport, options: ExportOptions, *, dry_run: bool, schema_server: str | None = None
) -> tuple[Manifest, list[tuple[Unit, ExportUnit]]]:
    inventory = get_inventory(schema_server)
    store = RecordStore(export, inventory)
    schema_info, export = _schemas(store, export, options, schema_server)
    created_at = _created_at(export, options.reproducible)
    file_create_date = created_at
    manifest = Manifest(
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        exporter=ExporterInfo(version=__version__, mapping_version=MAPPING_VERSION, **_nwb_versions()),
        run=RunInfo(created_at=created_at, reproducible=options.reproducible, dry_run=dry_run,
                    options=options.model_dump(mode="json")),
        source=_source_info(export, store),
        data_model=_data_model_info(inventory),
        projects=_project_infos(store),
        schemas=schema_info,
    )
    manifest.warnings.extend(_data_model_warnings(inventory))
    for missing in schema_info.missing:
        manifest.warnings.append(make_warning(
            "SCHEMA_NOT_AVAILABLE", f"schema {missing} could not be fetched; its URL is written, not the schema"))
    if is_newer_minor(export):
        manifest.warnings.append(make_warning(
            "EXPORT_MINOR_NEWER", f"export format {export.format_version} is newer than this release knows "
            f"({SUPPORTED_EXPORT_MAJOR}.{KNOWN_EXPORT_MINOR}); unknown labels and keys are kept in the manifest"))
    for label in manifest.source.unmapped_labels:
        manifest.warnings.append(make_warning("UNKNOWN_LABEL", f"record type '{label}' is not known to this release; "
                                              "its records are kept out of the NWB files", label=label))
    restricted = sum(len(items) for items in manifest.source.restricted.values())
    if restricted:
        names = sorted(item["name"] for items in manifest.source.restricted.values() for item in items)
        manifest.warnings.append(make_warning(
            "RESTRICTED_LAB_RESOURCES",
            f"{restricted} referenced lab resource(s) are not readable by the exporting user: {', '.join(names)}"))
    manifest.external_refs = {
        label: ExternalRefCount(total=total, resolved=resolved)
        for label, (total, resolved) in store.external_refs().items()
    }

    sessions = options.sessions
    if not sessions and export.scope == "session" and export.session_id:
        sessions = [export.session_id]  # a session export also holds the subjects' other records, not sessions
    if not sessions:
        for session in not_performed_sessions(store):
            manifest.warnings.append(make_warning(
                "SESSION_NOT_PERFORMED", f"session '{session.get('name')}' is {session.get('status')}, not performed; "
                "no NWB file is written", label=session.label, pk=session.pk))
    export_units, planned_errors = plan_units(
        store, sessions=sessions, allow_no_subject=options.allow_no_subject,
        infer_subjects=options.infer_subjects, subject_label_field=options.subject.label_field,
    )
    manifest.unit_errors = [
        UnitErrorEntry(session_id=e.session.pk, session_name=e.session.get("name"), subject_id=e.subject_pk,
                       code=e.code, message=e.message)
        for e in planned_errors
    ]
    pairs: list[tuple[Unit, ExportUnit]] = []
    for export_unit in export_units:
        try:
            unit = map_unit(store, export_unit, options, export, file_create_date=file_create_date)
        except Exception as exc:
            unit = Unit(
                unit_id=export_unit.unit_id, status="failed",
                session=RecordRef(id=export_unit.session.pk, name=export_unit.session.get("name")),
                output=UnitOutput(relative_path=export_unit.relative_path),
                attribution=export_unit.attribution, warnings=list(export_unit.warnings),
                error=_failure(exc),
            )
        pairs.append((unit, export_unit))
        manifest.units.append(unit)
    manifest.coverage = _coverage(store, export_units)
    return manifest, pairs


def _schemas(store: RecordStore, export: ProjectExport, options: ExportOptions,
             server: str | None) -> tuple[SchemaInfo, ProjectExport]:
    """Which schemas the records use; with --embed-schemas, fetch the ones the export does not carry."""
    from .normalize.schemas import collect_schema_refs

    refs = collect_schema_refs(store)
    provided = dict(export.schemas)
    if not options.embed_schemas or not options.extensions:
        return SchemaInfo(used=len(refs), embedded=sum(r.id in provided for r in refs),
                          origin="export" if provided else "none"), export
    from .retrieval.schemas import fetch_schemas, schemas_base

    wanted = [ref for ref in refs if ref.id not in provided]
    fetched, missing = fetch_schemas(wanted, server)
    provided.update(fetched)
    extra = {**export.extra, "schemas": provided}
    export = ProjectExport(info=export.info, records=export.records, sha256=export.sha256, source=export.source,
                           format_major=export.format_major, format_minor=export.format_minor,
                           raw_bytes=export.raw_bytes, extra=extra)
    info = SchemaInfo(used=len(refs), embedded=sum(r.id in provided for r in refs), origin="fetched",
                      base_url=schemas_base(server), missing=missing)
    return info, export


def _write_unit(unit: Unit, export_unit: ExportUnit, output: Path, *, overwrite: bool, fail_fast: bool) -> None:
    if unit.status == "failed" or unit.nwb is None:
        if fail_fast:
            raise BrainstemNwbError(f"unit {unit.unit_id} failed: {unit.error.message if unit.error else ''}")
        return
    from .nwb.writer import build_nwbfile, file_sha256, read_identifier, write_nwbfile

    path = output / unit.output.relative_path
    try:
        if path.exists() and not overwrite:
            if read_identifier(path) == unit.output.nwb_identifier:
                unit.status = "up_to_date"
                unit.output.sha256 = file_sha256(path)
                return
            unit.status = "failed"
            unit.error = UnitFailure(code="OUTPUT_EXISTS",
                                     message=f"{unit.output.relative_path} exists with other content; use --overwrite")
            unit.warnings.append(make_warning("OUTPUT_EXISTS", unit.error.message))
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            nwbfile = build_nwbfile(unit.nwb)
            herd_path = output / unit.output.herd_relative_path if unit.output.herd_relative_path else None
            unit.output.sha256 = write_nwbfile(nwbfile, path, herd=unit.nwb.herd, herd_path=herd_path)
        unit.status = "written"
    except Exception as exc:
        unit.status = "failed"
        unit.error = _failure(exc)
        unit.warnings.append(make_warning("UNIT_FAILED", unit.error.message))
        if fail_fast:
            raise


def _failure(exc: Exception) -> UnitFailure:
    frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
    where = f" ({Path(frame.filename).name}:{frame.lineno})" if frame else ""
    return UnitFailure(code="UNIT_FAILED", message=f"{exc}{where}", exception_type=type(exc).__name__)


def _write_report(report: ValidationReport, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    from .manifest.io import canonical_json

    (directory / REPORT_JSON).write_text(canonical_json(report.model_dump(mode="json")), encoding="utf-8")
    (directory / REPORT_TEXT).write_text(render_text(report), encoding="utf-8")


def _created_at(export: ProjectExport, reproducible: bool) -> dt.datetime:
    if reproducible:
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if epoch and epoch.isdigit():
            return dt.datetime.fromtimestamp(int(epoch), tz=dt.timezone.utc)
        if export.exported_at:
            try:
                return parse_datetime(export.exported_at)
            except ValueError:
                pass
        return dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _nwb_versions() -> dict[str, Any]:
    from importlib.metadata import version

    out: dict[str, Any] = {"pynwb": version("pynwb"), "hdmf": version("hdmf"), "nwb_schema": None}
    try:
        from pynwb import get_type_map

        out["nwb_schema"] = str(get_type_map().namespace_catalog.get_namespace("core").version)
    except Exception:  # pragma: no cover - informational only
        pass
    return out


def _data_model_info(inventory: Inventory) -> DataModelInfo:
    license_info = inventory.license or {}
    return DataModelInfo(
        server=inventory.source.server if inventory.source else "",
        data_model=inventory.data_model, export_format_version=inventory.export_format_version,
        server_commit=inventory.server_commit, sha256=inventory.sha256,
        license_url=str(license_info["url"]) if license_info.get("url") else None,
    )


def _data_model_warnings(inventory: Inventory) -> list[Any]:
    out = []
    source = inventory.source
    if source is not None and source.origin == "stale_cache":
        out.append(make_warning(
            "DATA_MODEL_CACHED", f"could not reach {source.server} ({source.error}); used the data model cached on "
            f"{source.fetched_at}"))
    if inventory.data_model and inventory.data_model not in SUPPORTED_DATA_MODELS:
        out.append(make_warning(
            "DATA_MODEL_UNSUPPORTED", f"the server's data model is '{inventory.data_model}'; this release is written "
            f"for {', '.join(SUPPORTED_DATA_MODELS)}"))
    return out


def _source_info(export: ProjectExport, store: RecordStore) -> SourceInfo:
    known = set(store.inventory.export_labels)
    counts = export.info.get("counts")
    return SourceInfo(
        kind=export.source.kind,
        name=export.source.name,
        host=export.source.host,
        sha256=export.sha256,
        format_version=export.format_version,
        exported_at=export.exported_at,
        scope="session" if export.scope == "session" else "project",
        project_id=export.project_id,
        project_ids=export.project_ids,
        session_id=export.session_id,
        record_count=export.info.get("record_count"),
        counts={str(k): int(v) for k, v in counts.items()} if isinstance(counts, dict) else {},
        lab_resources=export.info.get("lab_resources"),
        restricted={
            str(label): [{"pk": str(i.get("pk")), "name": str(i.get("name") or "")} for i in items or []
                         if isinstance(i, dict)]
            for label, items in sorted(export.restricted.items()) if items
        },
        unmapped_labels=sorted(label for label in export.records if label not in known),
    )


def _project_infos(store: RecordStore) -> list[ProjectInfo]:
    return [_project_info(project) for project in sorted(store.all("stem.project"), key=lambda p: p.pk)]


def _project_info(project: Record) -> ProjectInfo:
    return ProjectInfo(
        id=project.pk,
        name=str(project.get("name") or ""),
        description=html_to_text(project.get("description")) or None,
        tags=sorted(str(t) for t in project.get("tags") or []),
        publication_ids=[str(p) for p in project.get("publications") or []],
        repository_links=[{"repository": r, "url": u}
                          for r, u in repository_links(project.get("repository_links_json"))],
        custom_fields=[{"key": k, "value": v} for k, v in key_values(project.get("extra_content_json"))],
    )


# Shared catalogs and users: exported because records reference them, not records of the project.
CATALOG_APPS = ("taxonomies.", "resources.", "dissemination.", "users.")


def _coverage(store: RecordStore, units: list[ExportUnit]) -> Coverage:
    """Project records (catalog entries and users excluded) and whether a unit reached them."""
    reached = {key for unit in units for key in unit.all_records()}
    for unit in units:  # records left out of a unit were still looked at
        reached.update((a.label, a.pk) for a in unit.attribution)
    unreached: dict[str, list[str]] = defaultdict(list)
    total = 0
    for label in store.labels():
        if label.startswith(CATALOG_APPS):
            continue
        for record in store.all(label):
            total += 1
            if record.key not in reached:
                unreached[label].append(record.pk)
    return Coverage(records_total=total, records_in_units=len(reached),
                    records_unreached=dict(sorted(unreached.items())))


def _summarize(manifest: Manifest) -> None:
    status = Counter(unit.status for unit in manifest.units)
    severities: Counter[str] = Counter(w.severity for w in manifest.warnings)
    for unit in manifest.units:
        severities.update(w.severity for w in unit.warnings)
    severities.update("error" for _ in manifest.unit_errors)
    manifest.summary = Summary(
        sessions=len({u.session.id for u in manifest.units} | {e.session_id for e in manifest.unit_errors}),
        units=len(manifest.units),
        written=status.get("written", 0),
        up_to_date=status.get("up_to_date", 0),
        planned=status.get("planned", 0),
        failed=status.get("failed", 0),
        unit_errors=len(manifest.unit_errors),
        warnings_by_severity={key: severities.get(key, 0) for key in ("error", "warning", "info")},
    )


def _exit_code(manifest: Manifest, report: ValidationReport | None, fail_on: FailOn) -> int:
    code = EXIT_OK
    if manifest.unit_errors or any(u.status == "failed" for u in manifest.units):
        code = max(code, EXIT_PARTIAL)
    if report is not None and (report.has("error") or (fail_on == "warning" and report.has("warning"))):
        code = max(code, EXIT_VALIDATION)
    return code
