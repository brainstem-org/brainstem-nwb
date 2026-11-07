# Command-line interface

This page is the reference for every `brainstem-nwb` command and option. `brainstem-nwb --help` and `brainstem-nwb COMMAND --help` show the same options.

## `export`

Converts a whole project, or some of its sessions, into metadata-only NWB files.

```bash
brainstem-nwb export (--project UUID | --export-file FILE) --output DIR [options]
```

### Where the records come from

| Option | Meaning |
|---|---|
| `--project UUID` | Fetch the project's export from BrainSTEM |
| `--export-file FILE` | Use a downloaded export (`.json` or `.json.gz`, project or session export) |
| `--session ID\|NAME` | Export only this session; repeat for more. A single `--session UUID` without `--project` or `--export-file` fetches that session's export |
| `--token`, `--url`, `--headless`, `--no-device-flow`, `--no-background` | Fetching and authentication; see [install.md](install.md) |
| `--no-save-export` | Do not keep a copy of the fetched export in `DIR/source/` |

### What is written

| Option | Meaning |
|---|---|
| `--config FILE.toml` | Experimenter, lab, institution and subject options ([configuration](#configuration)) |
| `--dry-run` | Write only `brainstem-nwb-manifest.json` |
| `--allow-no-subject` | Export sessions that have no subject, without an NWB Subject |
| `--no-infer-subjects` | When a session lists no subjects, do not take them from its behaviors, procedures and interfaces |
| `--overwrite` | Replace existing files whose content differs. Files that are identical are kept and reported as `up_to_date` |
| `--reproducible` | Use the export time as the creation time, so reruns give identical manifests |
| `--extension brainstem\|localization` | Also write NWB extensions: every BrainSTEM record as `ndx-brainstem` tables, and coordinates as `ndx-anatomical-localization` tables. Repeatable. See [extensions](extensions.md) |
| `--embed-schemas` | With `--extension brainstem`: fetch the BrainSTEM JSON schemas the records use from the server's public schema service (`--url`) and embed them |
| `--herd` | Also write ontology terms (NCBITaxon, RRIDs, atlas regions) as a HERD zip next to each file |
| `--fail-fast` | Stop at the first unit that fails. By default the remaining units are still exported |

### Validation and output

| Option | Meaning |
|---|---|
| `--no-validate` | Skip validation |
| `--inspector-config dandi\|none` | NWB Inspector configuration. Default: `dandi` |
| `--fail-on error\|warning` | Which validation severity gives exit code 4 |
| `--json` | Print the summary as JSON |

## `manifest`

The same as `export --dry-run`, but the manifest can be written to a single named file:

```bash
brainstem-nwb manifest --export-file export.json -o manifest.json
```

## `validate`

Validates NWB files, or a directory of them. When the files are in an export directory, they are also checked against the manifest there.

```bash
brainstem-nwb validate ./nwb/ [--manifest FILE] [--report-dir DIR] [--inspector-config dandi|none] [--fail-on warning]
```

## `fetch`

Downloads a project or session export to a file, so you can convert it later or offline.

```bash
brainstem-nwb fetch --project UUID -o export.json.gz
brainstem-nwb fetch --session UUID -o session-export.json.gz
```

## `data-model`

```bash
brainstem-nwb data-model [--url URL] [--refresh]
```

Reads the BrainSTEM data model from the server (or the fresh cached copy), caches it, and shows the server, the data model generation and whether this release supports it, the export format, its checksum and the cache directory. Run it once before working offline. See [the BrainSTEM data model](install.md#the-brainstem-data-model).

## `mapping` and `schema`

| Command | Prints |
|---|---|
| `brainstem-nwb mapping` | The mapping specification (Markdown). `--format json` prints the rules instead; `--warnings` prints the warning codes |
| `brainstem-nwb schema manifest` | The JSON Schema of the manifest |
| `brainstem-nwb schema report` | The JSON Schema of the validation report |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Everything was exported and validated without errors |
| 1 | Partial export: some sessions could not be exported, or some files failed (see the manifest) |
| 2 | Usage error, invalid configuration, or unreadable or unsupported export file |
| 3 | Authentication or retrieval failure, or the data model could not be read and is not cached |
| 4 | Files were written, but validation found errors (or warnings, with `--fail-on warning`) |

If several apply, the highest code is returned.

## Configuration

Some NWB fields have no source in a BrainSTEM export. They can be set in a TOML file:

```toml
[nwbfile]
experimenter = ["Last, First", "Other, Person"]
experimenter_source = "config"    # or "session_creator": the user who created the session record, when no
                                  # experimenter is configured (BrainSTEM records who created a session, not who ran it)
lab = "My Lab"
institution = "My University"

[subject]
label_field = "name"              # or "name_used_in_storage": used for subject_id and file names
species_format = "binomial"       # or "ncbitaxon": NCBI Taxonomy IRI, preferred by DANDI
```
