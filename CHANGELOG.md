# Changelog

All notable changes to brainstem-nwb are documented here. The project follows semantic versioning. The mapping version, which tracks changes to what is written to NWB files, is listed separately.

## 0.1.0 (unreleased)

### The BrainSTEM data model is read from the server (mapping version 1.3.0)

- brainstem-nwb no longer ships a copy of the BrainSTEM data model. It reads the record types, fields, links and type vocabularies from the server's reference documents (`/reference/data/`), caches them per server for an hour, and uses the cached copy when the server cannot be reached (`DATA_MODEL_CACHED`). `BRAINSTEM_NWB_DATA_MODEL` names a directory with the documents for offline machines; `brainstem-nwb data-model` fetches and shows the model.
- The manifest's `data_model` names the server, the data model generation, the export format and a checksum of the model used. A generation this release was not written for is reported as `DATA_MODEL_UNSUPPORTED`.
- Follows the production data model (`specimen-1`): data acquisitions and manipulations link procedures only through their interfaces, as the server's session export does; specimens record `laterality` (no `hemisphere` or `baseline_conditions`).
- Planned and cancelled sessions get no file (`SESSION_NOT_PERFORMED`); planned and cancelled procedures and specimen procedures are left out of the file and kept in the manifest (`PROCEDURE_NOT_PERFORMED`). Records without a status are performed.
- The code is MIT. The BrainSTEM data model and schemas are © BrainSTEM, all rights reserved; embedded schemas carry BrainSTEM's notice in the `schemas` table description.

### NWB extensions (mapping version 1.2.0)

- `--extension brainstem` writes every included BrainSTEM record, with every field and the links between them, as `ndx-brainstem` tables (pre-release extension, 0.2.x; install with `pip install "brainstem-nwb[extensions]"`).
- With `--extension brainstem`, coordinates of procedures and interfaces in stereotaxic absolute and Allen CCF systems are also written as `ndx-anatomical-localization` tables, linked to their `ndx-brainstem` rows (`--extension localization` is the same option).
- The `ndx-brainstem` schema table (extension 0.2.0) lists every BrainSTEM JSON schema the file's tables name, with its stable URL. `--embed-schemas` fetches the schemas from the server's public schema service and embeds them. Coordinates get their own `coordinates_schema` column.
- Materials link directly to their catalog consumable (`catalog_entry`), also when the usage names a stock. Stocks keep only their typed details (batch, titer, volume, aliquots).
- `--herd` writes ontology terms for species, strains, regions and device models as a HERD zip next to each file.
- Licenses, data storages and inventories are no longer written to NWB files (NWBFile.protocol lists protocols only); they stay in the manifest.
- An NWB Inspector check that crashes is reported as a warning, not an error.

### Export format 2.1 (mapping version 1.1.0)

- **Session exports.** Reads session exports (`export_info.scope`, `session_id`, `project_ids`). `export --session UUID` fetches one session's export through `BrainstemClient.export_session` when the API tools provide it. A session in several projects lists all of them in `experiment_description` and `keywords`.
- **Catalog records the export now includes:**
  - Brain regions and atlases: electrode-group and stimulus-site `location` from region acronyms, with full names and atlas in descriptions and procedure text.
  - Suppliers: `DeviceModel` with manufacturer and model number for hardware devices and probe designs; suppliers in material descriptions.
  - Publications: `related_publications` DOIs.
  - User names: who performed each procedure, episode personnel, and opt-in `experimenter_source = "session_creator"`.
  - Log entries: `Subject.weight` from the latest weighing before the session.
  - Behavioral paradigms and categories, setup types, regulatory authorities.
- **Restricted lab resources.** Resources the exporting user cannot read (`export_info.restricted`) are named in the text and reported as `RESTRICTED_LAB_RESOURCES`.
- **Contract fixtures.** Regenerated from the server's export builder, as a project export and a session export.

### First version

First release: metadata-only export. Mapping version 1.0.0. Manifest and validation report schemas 1.0.0.

#### Input

- Reads BrainSTEM project exports (format 2.x), from a downloaded file (`.json` or `.json.gz`) or fetched with `BrainstemClient.export_project()`.

#### Export units

- One NWB file per session and subject, named `sub-<subject>/sub-<subject>_ses-<session>.nwb`.
- Each record is attributed to the subject it belongs to, and every decision is documented.
- Specimen (ex vivo) sessions are supported.

#### What is written

**Session and subject**

- Session fields and project context.
- `Subject`: species, optionally as an NCBI Taxonomy IRI; strain; sex; date of birth; age; genotype.

**Procedures and manipulations**

- Surgery, virus and pharmacology narratives, from procedures and their materials.
- Stimulus notes, from manipulations.

**Devices**

- Devices from equipment and experimental interfaces.
- Electrode groups.
- Optogenetic stimulus sites.

**Other**

- The epochs table.
- Ex vivo slices.
- Behaviors in the notes.
- A provenance block.

#### Manifest and validation

- **Conversion manifest:** a value state for every NWB destination, coded warnings, raw-data references, and the records used.
- **Validation:**
  - pynwb schema validation.
  - NWB Inspector, with the DANDI configuration.
  - BrainSTEM semantic checks.
  - Reports in JSON and text.

#### Tools

- **CLI:** `export`, `manifest`, `validate`, `fetch`, `mapping`, `schema`.
- **Python API:** `export_project`, `export_session`, `build_manifest`, `validate_output`, `load_export`, `fetch_export`.

#### Reproducibility

- Deterministic NWB identifiers.
- `--reproducible` mode.
- Idempotent re-runs: files that are already up to date are kept.

#### Raw data (Phase 4)

- Designed only: the converter protocol, registry, data-path file and NeuroConv metadata hand-off.
