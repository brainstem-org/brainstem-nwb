# Troubleshooting

## "cannot read the BrainSTEM data model" (exit code 3)

brainstem-nwb reads the data model from the server at run time and had neither network access nor a cached copy. Connect once (`brainstem-nwb data-model`), or set `BRAINSTEM_NWB_DATA_MODEL` to a directory with the reference documents. See [the BrainSTEM data model](install.md#the-brainstem-data-model).

## "no BrainSTEM token" (exit code 3)

You can authenticate in any of these ways:
- Run `brainstem login` once; this caches a token.
- Pass `--token`.
- Set `BRAINSTEM_API_TOKEN`.

In non-interactive runs the exporter never starts the browser login.

## "fetching exports needs brainstem_python_api_tools with BrainstemClient.export_project"

The installed API tools predate project exports. You have two options:
- Upgrade: `pip install -U brainstem_python_api_tools`, or install from GitHub.
- Download the export in the web interface and use `--export-file`.

## "BrainSTEM export failed: … needs contributor access"

The server uses export format 2.0, which requires permission to change the project. Servers with format 2.1 or later need only read access. Ask a project manager for contributor access, or for the export file.

## "fetching a single session needs … BrainstemClient.export_session"

The installed API tools cannot fetch session exports yet. Use `--project` (the project export is cut to the session), or download the session export in the web interface and use `--export-file`.

## A session is "not exported"

The summary and `unit_errors` in the manifest give the reason:

| Code | Fix |
|---|---|
| `SESSION_START_TIME_MISSING` | Set the session's date and time in BrainSTEM |
| `NO_SUBJECT` | Link the session to its subject or subjects, or pass `--allow-no-subject` |
| `SUBJECT_NOT_IN_EXPORT` | The session lists a subject from another project. Add that subject to this project |
| `SESSION_NOT_PERFORMED` | The session is planned or cancelled in BrainSTEM. Mark it performed once it has happened |

## A file exists and is "failed: OUTPUT_EXISTS"

The file in the output directory was written from different metadata. Use `--overwrite` to replace it, or export to a new directory. Files that are unchanged are kept and reported as `up_to_date`.

## Validation error `check_subject_age`

DANDI needs the subject's age. Add the birth date in BrainSTEM: the age is computed from it and the session date.

## `location` is "unknown" for electrode groups

No target region is recorded for the probe, or for the procedure that implanted it, or the export is format 2.0, which does not include region records. Add the target region in BrainSTEM, or export again from a server with format 2.1 or later.

## A field I expected is missing

1. Look up the field in the [mapping specification](mapping-spec.md). Fields without an NWB destination are listed under *Kept in the manifest only*.
2. In the manifest, find the destination under the unit's `mappings`. Its `state` says whether the value was `missing`, `unknown`, `not_applicable` or `not_exported`.
3. Check the unit's `warnings` for an explanation.

## The export file is "not a BrainSTEM project export"

This release reads export format 2.x, the layout with `export_info` and `records`. Downloads made before format 2.0 are not supported, so download the export again.
