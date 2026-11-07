# The conversion manifest

This page explains what `brainstem-nwb-manifest.json` contains and how to read it.

Every run writes this file next to the NWB files. It records:
- what was exported, and from which BrainSTEM records;
- how each record was mapped to NWB;
- every warning.

A dry run (`export --dry-run` or `manifest`) writes only the manifest, so you can check the result before any file is written.

The manifest follows a versioned JSON Schema: [`schemas/manifest-1.0.0.schema.json`](https://github.com/brainstem-org/brainstem-nwb/blob/main/schemas/manifest-1.0.0.schema.json). `brainstem-nwb schema manifest` prints the same schema.

## Top level

| Key | Contents |
|---|---|
| `manifest_schema_version` | Version of this format (1.0.0) |
| `exporter` | brainstem-nwb, pynwb, hdmf and NWB schema versions, and the **mapping version** |
| `export_mode` | `metadata-only` in this release |
| `run` | Creation time, whether the run was reproducible or a dry run, and the options (no secrets, no paths) |
| `source` | The export: file name or host, sha256, format version, export time, scope (`project` or `session`), project and session ids, record counts, lab resources the exporting user could not read (`restricted`), record types this release does not know |
| `data_model` | The BrainSTEM data model the export was read with: the server, its data model generation (e.g. `specimen-1`), the export format it writes, its commit when published, a sha256 of the record types, fields and vocabularies used, and the URL of BrainSTEM's terms |
| `projects` | Each exported project's name, description, tags, publication ids, repository links, custom fields. A session export can hold several |
| `external_refs` | Linked record types that are not in the export (e.g. brain regions), with counts |
| `units` | One entry per NWB file (session × subject) |
| `unit_errors` | Sessions that could not be exported, and why |
| `schemas` | The BrainSTEM JSON schemas the records use: how many, how many were embedded, their origin (`export`, `fetched` or `none`), the schema service URL, and any versions that could not be fetched |
| `coverage` | Exported project records not reached by any unit, e.g. subjects without sessions. Catalog entries and users are not counted |
| `warnings` | Project-level warnings |
| `summary` | Counts of units by status and of warnings by severity |

## A unit

| Key | Contents |
|---|---|
| `unit_id` | `<session id>__<subject id>` |
| `status` | `planned`, `written`, `up_to_date` or `failed` |
| `session`, `subject`, `specimen_sets` | Ids and names |
| `output` | Relative path, NWB identifier, file sha256, and the HERD zip's path with `--herd` |
| `attribution` | For each record of the session, whether it was included, shared or excluded, and why |
| `mappings` | Every intended NWB destination, with its value state and source records |
| `records` | Every BrainSTEM record used, exactly as exported (minus the creator id), with its roles and its fields that have no NWB destination (`unmapped_fields`) |
| `nwb` | The exact plan the NWB writer used: core NWB, and with options the `ndx-brainstem` tables (`brainstem`), localization tables (`localization`) and HERD references (`herd`) |
| `data_sources` | Each data acquisition's file name, format, storage names, data storages and repository links: the input for raw-data conversion |
| `warnings` | Coded warnings ([list](warnings.md)), each pointing at a record and field path |
| `error` | Why the unit failed, if it did |

## Value states

Every entry in `mappings` has one of five states:

| State | Meaning | Example |
|---|---|---|
| `present` | Written to NWB | `Subject.species` |
| `missing` | BrainSTEM has the field, but it is empty | no birth date |
| `unknown` | BrainSTEM explicitly records "unknown" | sex `U` (written as `U`) |
| `not_applicable` | The destination does not apply | `slices` for an in vivo session |
| `not_exported` | The source is not in the export | subject weight, publication DOIs |

## Privacy

The manifest leaves out:
- the creator of each record;
- e-mail addresses (the export never contains them);
- tokens;
- absolute paths.

It contains everything else exported for the records it lists, including notes. Treat it with the same care as the export.
