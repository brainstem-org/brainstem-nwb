"""Command-line interface: ``brainstem-nwb``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from ._version import __version__
from .errors import BrainstemNwbError

_SOURCE_HELP = "BrainSTEM project export (.json or .json.gz, from Project -> Download -> JSON)."


def _source_options(func: Any) -> Any:
    options = [
        click.option("--project", "project_id", metavar="UUID", help="BrainSTEM project id; its export is fetched."),
        click.option("--export-file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
                     help=_SOURCE_HELP),
        click.option("--session", "sessions", multiple=True, metavar="ID|NAME",
                     help="Only this session (repeatable). Default: every session of the project. A single "
                          "--session without --project or --export-file fetches that session's export."),
        click.option("--config", type=click.Path(exists=True, dir_okay=False, path_type=Path),
                     help="TOML configuration (experimenter, lab, institution, subject options)."),
        click.option("--allow-no-subject", is_flag=True, default=None,
                     help="Export sessions without a subject (no NWB Subject)."),
        click.option("--no-infer-subjects", "infer_subjects", flag_value=False, default=None,
                     help="Do not take subjects from linked records when a session lists none."),
        click.option("--reproducible", is_flag=True, default=None,
                     help="Use the export time as creation time, so reruns give identical manifests."),
        click.option("--extension", "extensions", multiple=True, type=click.Choice(["brainstem", "localization"]),
                     help="Also write NWB extensions (need the ndx-brainstem package: "
                          "pip install 'brainstem-nwb[extensions]'): 'brainstem' adds every "
                          "BrainSTEM record as ndx-brainstem tables, and the coordinates of procedures and interfaces "
                          "as ndx-anatomical-localization tables ('localization' is the same)."),
        click.option("--embed-schemas", is_flag=True, default=None,
                     help="With --extension brainstem: fetch the BrainSTEM JSON schemas the records use from the "
                          "server's public schema service (--url, default www.brainstem.org) and embed them."),
        click.option("--herd", is_flag=True, default=None,
                     help="Also write ontology terms (NCBITaxon, RRIDs, atlas regions) as a HERD zip next to each "
                          "NWB file."),
        click.option("--token", envvar="BRAINSTEM_API_TOKEN", metavar="TOKEN",
                     help="BrainSTEM API token (default: $BRAINSTEM_API_TOKEN, then the token cached by "
                          "'brainstem login')."),
        click.option("--url", metavar="URL", help="BrainSTEM server (default https://www.brainstem.org/)."),
        click.option("--no-background", "background", flag_value=False, default=True,
                     help="Fetch the export in one request instead of a background export job."),
        click.option("--headless", is_flag=True, help="For browser login: print the login URL instead of opening it."),
        click.option("--no-device-flow", is_flag=True, help="Never start the browser login; fail without a token."),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _fetch_kwargs(token: str | None, url: str | None, background: bool, headless: bool,
                  no_device_flow: bool) -> dict[str, Any]:
    return {
        "token": token or None,
        "url": url,
        "background": background,
        "headless": headless,
        "allow_device_flow": (not no_device_flow) and sys.stdin.isatty(),
    }


def _fail(exc: BrainstemNwbError) -> None:
    click.echo(f"error: {exc}", err=True)
    sys.exit(exc.exit_code)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="brainstem-nwb")
def main() -> None:
    """Export BrainSTEM experimental metadata to NWB files."""


@main.command()
@_source_options
@click.option("-o", "--output", type=click.Path(file_okay=False, path_type=Path), required=True,
              help="Output directory.")
@click.option("--dry-run", is_flag=True, help="Write only the manifest; no NWB files.")
@click.option("--no-validate", "validate", flag_value=False, default=True, help="Skip validation.")
@click.option("--overwrite", is_flag=True, help="Replace existing NWB files that differ.")
@click.option("--fail-fast", is_flag=True, help="Stop at the first unit that fails.")
@click.option("--inspector-config", default="dandi", show_default=True,
              help="NWB Inspector configuration ('dandi' or 'none').")
@click.option("--fail-on", type=click.Choice(["error", "warning"]), default="error", show_default=True,
              help="Validation severity that makes the exit code non-zero.")
@click.option("--no-save-export", "save_export", flag_value=False, default=True,
              help="Do not keep a copy of the fetched export in OUTPUT/source/.")
@click.option("--json", "as_json", is_flag=True, help="Print the manifest summary as JSON.")
def export(project_id, export_file, sessions, config, allow_no_subject, infer_subjects, reproducible, extensions,
           embed_schemas, herd, token, url, background, headless, no_device_flow, output, dry_run, validate, overwrite,
           fail_fast, inspector_config, fail_on, save_export, as_json) -> None:
    """Export a project (or some of its sessions) to metadata-only NWB files.

    One file is written per session and subject, as sub-<subject>/sub-<subject>_ses-<session>.nwb,
    with brainstem-nwb-manifest.json and validation-report.{json,txt}.
    """
    from .export import export_project

    if not project_id and not export_file and len(sessions) != 1:
        raise click.UsageError("give --project, --export-file, or one --session to fetch")
    try:
        result = export_project(
            project_id, output, export_file=export_file, sessions=list(sessions) or None, config=config,
            dry_run=dry_run, validate=validate, allow_no_subject=allow_no_subject, infer_subjects=infer_subjects,
            reproducible=reproducible, extensions=list(extensions) or None, herd=herd,
            embed_schemas=embed_schemas, overwrite=overwrite,
            fail_fast=fail_fast,
            inspector_config=None if inspector_config == "none" else inspector_config, fail_on=fail_on,
            save_export=save_export, **_fetch_kwargs(token, url, background, headless, no_device_flow),
        )
    except BrainstemNwbError as exc:
        _fail(exc)
        return
    _print_summary(result, as_json)
    sys.exit(result.exit_code)


@main.command()
@_source_options
@click.option("-o", "--output", type=click.Path(path_type=Path), required=True,
              help="Output directory, or a .json file name for the manifest.")
def manifest(project_id, export_file, sessions, config, allow_no_subject, infer_subjects, reproducible, extensions,
             embed_schemas, herd, token, url, background, headless, no_device_flow, output) -> None:
    """Build the conversion manifest only (same as export --dry-run)."""
    from .export import build_manifest
    from .manifest.io import MANIFEST_FILENAME, write_manifest
    from .retrieval.api import fetch_export

    if not project_id and not export_file and len(sessions) != 1:
        raise click.UsageError("give --project, --export-file, or one --session to fetch")
    try:
        session_id = sessions[0] if len(sessions) == 1 and not export_file else None
        source = export_file or fetch_export(
            None if session_id else project_id, session_id=session_id,
            **_fetch_kwargs(token, url, background, headless, no_device_flow))
        result = build_manifest(source, sessions=list(sessions) or None, config=config,
                                allow_no_subject=allow_no_subject, infer_subjects=infer_subjects,
                                reproducible=reproducible, extensions=list(extensions) or None, herd=herd,
                                embed_schemas=embed_schemas, schema_server=url)
    except BrainstemNwbError as exc:
        _fail(exc)
        return
    path = output if output.suffix == ".json" else output / MANIFEST_FILENAME
    write_manifest(result, path)
    s = result.summary
    click.echo(f"{s.units} unit(s) planned from {s.sessions} session(s); {s.unit_errors} session(s) cannot be "
               f"exported. Manifest: {path}")
    sys.exit(1 if result.unit_errors else 0)


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--manifest", "manifest_path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="Manifest to check the files against (default: the one next to the files).")
@click.option("--inspector-config", default="dandi", show_default=True)
@click.option("--report-dir", type=click.Path(file_okay=False, path_type=Path),
              help="Write validation-report.{json,txt} here.")
@click.option("--fail-on", type=click.Choice(["error", "warning"]), default="error", show_default=True)
def validate(paths, manifest_path, inspector_config, report_dir, fail_on) -> None:
    """Validate NWB files (schema, NWB Inspector, BrainSTEM checks)."""
    from .export import validate_output
    from .validation import ValidationReport, render_text

    combined = ValidationReport()
    for path in paths:
        report = validate_output(path, manifest=manifest_path,
                                 inspector_config=None if inspector_config == "none" else inspector_config)
        combined.tool_versions = report.tool_versions
        combined.inspector_config = report.inspector_config
        combined.files.extend(report.files)
    combined.finalize()
    if report_dir:
        from .export import _write_report

        _write_report(combined, report_dir)
    click.echo(render_text(combined), nl=False)
    failed = combined.has("error") or (fail_on == "warning" and combined.has("warning"))
    sys.exit(4 if failed else 0)


@main.command()
@click.option("--project", "project_id", metavar="UUID")
@click.option("--session", "session_id", metavar="UUID", help="Fetch this session's export instead of a project's.")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True,
              help="File to write (.json or .json.gz).")
@click.option("--token", envvar="BRAINSTEM_API_TOKEN", metavar="TOKEN")
@click.option("--url", metavar="URL")
@click.option("--no-background", "background", flag_value=False, default=True)
@click.option("--headless", is_flag=True)
@click.option("--no-device-flow", is_flag=True)
def fetch(project_id, session_id, output, token, url, background, headless, no_device_flow) -> None:
    """Download a project (or session) export, to convert later or offline."""
    from .retrieval.api import fetch_export

    if bool(project_id) == bool(session_id):
        raise click.UsageError("give --project or --session")
    try:
        export_data = fetch_export(project_id, session_id=session_id, save_to=output,
                                   **_fetch_kwargs(token, url, background, headless, no_device_flow))
    except BrainstemNwbError as exc:
        _fail(exc)
        return
    what = f"session {export_data.session_id}" if export_data.scope == "session" else \
        f"project {export_data.project_id}"
    click.echo(f"Saved export of {what} (format {export_data.format_version}, "
               f"{export_data.info.get('record_count')} records) to {output}")


@main.command()
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md", show_default=True)
@click.option("--warnings", "show_warnings", is_flag=True, help="Show the warning codes instead.")
@click.option("--check", "check_path", type=click.Path(dir_okay=False, path_type=Path),
              help="Exit 1 if this file differs from the generated Markdown.")
def mapping(fmt, show_warnings, check_path) -> None:
    """Print the BrainSTEM-to-NWB mapping specification."""
    from dataclasses import asdict

    from .mapping.docs import render_mapping_spec, render_warnings
    from .mapping.registry import RULES, _load_mappers

    if fmt == "json":
        _load_mappers()
        click.echo(json.dumps([asdict(rule) for rule in sorted(RULES.values(), key=lambda r: r.id)], indent=2))
        return
    text = render_warnings() if show_warnings else render_mapping_spec()
    if check_path:
        current = check_path.read_text(encoding="utf-8") if check_path.exists() else ""
        if current != text:
            click.echo(f"{check_path} is out of date; regenerate it with brainstem-nwb mapping", err=True)
            sys.exit(1)
        return
    click.echo(text, nl=False)


@main.command()
@click.argument("name", type=click.Choice(["manifest", "report"]))
def schema(name) -> None:
    """Print the JSON Schema of the manifest or the validation report."""
    from .manifest.schema import manifest_schema, report_schema

    data = manifest_schema() if name == "manifest" else report_schema()
    click.echo(json.dumps(data, indent=2, sort_keys=True))


@main.command("data-model")
@click.option("--url", metavar="URL", help="BrainSTEM server (default https://www.brainstem.org/).")
@click.option("--refresh", is_flag=True, help="Fetch the documents again, even when the cached copy is fresh.")
def data_model(url, refresh) -> None:
    """Read the BrainSTEM data model from the server, cache it, and show which one it is.

    brainstem-nwb ships no copy of the data model; exports read it from the server (cached for an hour, and
    used from the cache when the server cannot be reached). Run this once before working offline.
    """
    from ._version import SUPPORTED_DATA_MODELS
    from .store.datamodel import cache_dir, inventory_data, load_documents

    try:
        documents = load_documents(url, refresh=refresh)
    except BrainstemNwbError as exc:
        _fail(exc)
    data = inventory_data(documents.documents)
    supported = "supported" if data["data_model"] in SUPPORTED_DATA_MODELS else \
        f"not supported by this release ({', '.join(SUPPORTED_DATA_MODELS)})"
    click.echo(f"server:        {documents.server}")
    click.echo(f"data model:    {data['data_model']} ({supported})")
    click.echo(f"export format: {data['export_format_version']}")
    click.echo(f"sha256:        {data['sha256']}")
    origin = {"fetched": "fetched now", "cache": "cached copy (fresh)", "directory": "BRAINSTEM_NWB_DATA_MODEL",
              "stale_cache": f"cached copy; server not reachable: {documents.error}"}[documents.origin]
    click.echo(f"read from:     {origin}" + (f", {documents.fetched_at}" if documents.fetched_at else ""))
    if documents.origin != "directory":
        click.echo(f"cache:         {cache_dir(documents.server)}")
    if data.get("license"):
        click.echo(f"terms:         {data['license'].get('url')}")


def _print_summary(result: Any, as_json: bool) -> None:
    manifest = result.manifest
    if as_json:
        payload = {"exit_code": result.exit_code, "manifest": str(result.manifest_path),
                   "summary": manifest.summary.model_dump(),
                   "validation": result.report.summary if result.report else None}
        click.echo(json.dumps(payload, indent=2))
        return
    s = manifest.summary
    click.echo(f"Sessions: {s.sessions}  units: {s.units}  written: {s.written}  up to date: {s.up_to_date}  "
               f"failed: {s.failed}  not exportable: {s.unit_errors}")
    for error in manifest.unit_errors:
        click.echo(f"  not exported: session '{error.session_name}' ({error.code}): {error.message}")
    for unit in manifest.units:
        if unit.status == "failed" and unit.error:
            click.echo(f"  failed: {unit.output.relative_path}: {unit.error.message}")
    if result.report is not None:
        r = result.report.summary
        click.echo(f"Validation: {r.get('error', 0)} error(s), {r.get('warning', 0)} warning(s), "
                   f"{r.get('info', 0)} info (see validation-report.txt)")
    click.echo(f"Manifest: {result.manifest_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
