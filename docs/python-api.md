# Python API

This page is the reference for calling `brainstem-nwb` from Python. Everything listed here is importable from `brainstem_nwb`.

```python
from brainstem_nwb import (
    export_project, export_session, build_manifest, validate_output,
    load_export, fetch_export, ExportOptions,
)
```

## `export_project`

```python
result = export_project(
    project_id=None,            # fetch this project's export from BrainSTEM, or
    output_dir="nwb",
    *,
    export_file=None,           # use a downloaded export (.json/.json.gz), or
    export=None,                # an already loaded ProjectExport or export dict
    sessions=None,              # list of session ids or names
    config=None,                # TOML path, dict, or ExportOptions
    dry_run=False, validate=True,
    allow_no_subject=None, infer_subjects=None, reproducible=None,
    extensions=None,            # ["brainstem", "localization"]: see docs/extensions.md
    herd=None,                  # True: ontology terms as <file>.herd.zip
    embed_schemas=None,         # True: embed the BrainSTEM JSON schemas (fetched from `url`)
    overwrite=False, fail_fast=False,
    inspector_config="dandi", fail_on="error",
    token=None, url=None, background=True, allow_device_flow=False, headless=True, save_export=True,
)
```

Returns an `ExportResult` with these fields:

| Field | Contents |
|---|---|
| `manifest` | The `Manifest` model |
| `report` | The `ValidationReport`, or `None` when validation was skipped |
| `files` | Paths of the files written or already up to date |
| `manifest_path` | Path of the manifest written |
| `exit_code` | The CLI exit code (0, 1 or 4) |

Errors raise `BrainstemNwbError` subclasses:
- `ExportFormatError`
- `ConfigError`
- `AuthRequired`
- `RetrievalError`

One unit failing does not raise: it is reported in the manifest.

The project export payload already holds every record the exporter needs, so a caller that has it (for example the BrainSTEM server) can convert without a network round trip:

```python
from stem.services.project_export import build_project_export      # inside the BrainSTEM server
from brainstem_nwb import export_project

export_project(export=build_project_export(user, project), output_dir=tmp_dir, dry_run=False)
```

## `export_session`

```python
export_session(session_id_or_name, output_dir, project_id=None, export_file=None, **same_options)
```

The same as `export_project(..., sessions=[session])`. Without `export_file` or `project_id`, the session's own export is fetched; this needs `BrainstemClient.export_session` and a session id rather than a name.

## `build_manifest`

```python
manifest = build_manifest("export.json.gz", sessions=None, config=None, reproducible=True)
for unit in manifest.units:
    print(unit.output.relative_path, [w.code for w in unit.warnings])
```

Builds the full conversion manifest without writing anything.

## `validate_output`

```python
report = validate_output("nwb/", manifest=None, inspector_config="dandi", report_dir=None)
```

Validates existing files. If a manifest sits next to them, the files are also checked against it.

## Loading and fetching exports

```python
export = load_export("export.json.gz")           # also accepts a dict or a binary stream
export = fetch_export("PROJECT_UUID", token=..., background=True, save_to="export.json.gz")
export = fetch_export(session_id="SESSION_UUID", save_to="session.json.gz")
```

`ProjectExport` has these attributes:

| Attribute | Contents |
|---|---|
| `info` | The export's `export_info` |
| `records` | Records keyed by label |
| `sha256` | Checksum of the export |
| `format_version` | Export format version |
| `project_id` | The exported project's id (`None` for a session export) |
| `project_ids` | All exported projects (a session can belong to several) |
| `scope`, `session_id` | `"project"` or `"session"`, and the session of a session export |
| `restricted` | Lab resources the exporting user cannot read: label to `[{pk, name}]` |
| `exported_at` | When the export was made |

## Manifest models

The manifest classes live in `brainstem_nwb.manifest.models`: `Manifest`, `Unit`, `NwbPlan`, `FieldMapping`, `ConversionWarning` and others. They are pydantic v2 models. Use `model_dump(mode="json")` for plain data; `brainstem_nwb.manifest.read_manifest(path)` loads a written manifest.

## Stability

The names listed above are the public API and follow semantic versioning from 1.0. Anything else (`mapping.*`, `normalize.*`, `store.*`) is internal and can change between minor versions before then.
