# Architecture

This page is for contributors and for anyone embedding the exporter. It explains how `brainstem-nwb` is organized and how data moves through it. To change a mapping, see [Contributing](https://github.com/brainstem-org/brainstem-nwb/blob/main/CONTRIBUTING.md); the reasons behind the main choices are in [decisions.md](decisions.md).

## Layers

The exporter has four layers, and each knows only its neighbours:

```
retrieval ─► normalization ─► manifest (NwbPlan) ─► NWB writing ─► validation
```

| Layer | Package | Input → output | Knows about |
|---|---|---|---|
| Retrieval | `retrieval/` | project id or file → `ProjectExport` | the BrainSTEM API tools, the export format |
| Normalization | `store/`, `normalize/` | `ProjectExport` → `RecordStore`, `ExportUnit`s | BrainSTEM records and links |
| Mapping | `mapping/` | `ExportUnit` → manifest `Unit` with an `NwbPlan` | BrainSTEM and NWB concepts, not HTTP or HDF5 |
| NWB writing | `nwb/` | `NwbPlan` → `.nwb` file | pynwb only, not BrainSTEM |
| Validation | `validation/` | `.nwb` (+ manifest unit) → report | pynwb, NWB Inspector, the manifest |

`export.py` puts the layers together. `cli.py` and the functions in `__init__.py` are thin wrappers around it.

## Data flow

1. **Retrieval.** `load_export()` reads a project export (format 2.x) from a file or a dict. `fetch_export()` gets one through `BrainstemClient.export_project()`. The export is the **only** source of BrainSTEM records. This keeps an export reproducible: the export file, the exporter version and the BrainSTEM data model (whose checksum the manifest records) determine the result.
2. **Record store.** `RecordStore` indexes records by model label and primary key, and builds a reverse index of every foreign key and many-to-many link. The export does not record which model a link points to. That comes from the **inventory**: the BrainSTEM data model, read at run time from the server's reference documents (`store/datamodel.py`) and cached per server; brainstem-nwb ships no copy of it. A link to a record that is not in the export resolves to `Ref(reason="not_in_export")`; it is not an error.
3. **Units.** `plan_units()` decides which files to write. An NWB file holds one subject, so each session gives one unit per subject. Every record of the session is attributed to the units it belongs to, using documented rules. Each decision is recorded as an `Attribution`, and sessions that cannot be exported become `unit_errors`.
4. **Mapping.** `map_unit()` runs the mapper modules in order: session, project, people, protocols, subject, procedures, manipulations, acquisitions, devices, electrode groups, optogenetic sites, epochs and notes. Each mapper does two things:
   - fills the `NwbPlan`;
   - records every intended destination as a `FieldMapping` with a value state, and emits coded warnings.

   Mapper functions declare their `MappingRule`s with `@rules(...)`. The registry generates the mapping specification and backs the coverage test.
5. **Manifest.** The per-unit results, the source description, coverage and summary make up the `Manifest`. It is written as canonical JSON (`brainstem-nwb-manifest.json`), and a dry run stops here.
6. **Writing.** `build_nwbfile(plan)` builds a pynwb `NWBFile` from the plan alone. `write_nwbfile()` writes it to a temporary name and moves it into place.
7. **Validation.** Each file goes through `pynwb.validate`, NWB Inspector (DANDI configuration by default) and the BrainSTEM semantic checks, which compare the file with its manifest unit. Results go to `validation-report.json` and `.txt`.

## Identity and reproducibility

- The NWB `identifier` is `uuid5(namespace, session id | subject id | mapping version | sha256(plan content))`.
  - It is stable across re-exports of unchanged records.
  - It changes when any written content changes.
  - It ignores when the export was made.
- `--reproducible` (or `SOURCE_DATE_EPOCH`) takes the creation times from the export, which makes the manifest byte-identical across runs.
- HDF5 files themselves are not byte-identical (HDF5 object ids are random). Reproducibility tests therefore compare a canonical summary of each file (`nwb/canonical.py`).

## Extension points

- **New mapping.** Add a mapper function with `@rules(...)` and call it from `mapping/pipeline.py`. The coverage test lists the BrainSTEM fields still unaccounted for.
- **New BrainSTEM fields or models.** The data model comes from the server, so new fields appear on their own; `tests/test_spec.py` lists the ones the mapping does not account for yet. New record types go into `EXPORT_LABELS`.
- **Raw data (Phase 4).** Implement `raw.base.RawDataConverter` and register it, either built in or through the `brainstem_nwb.raw_converters` entry-point group. See [phase4-raw-data.md](phase4-raw-data.md).
- **Web integration (Phase 5).** The server can call `build_manifest(export_dict)` and `export_project(export=export_dict, ...)` directly with the payload of `build_project_export`, with no HTTP involved.
