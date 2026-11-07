# NWB extensions and ontology terms

This page explains the optional extras an export can write on top of core NWB, and how to read them back. All of them are opt-in.

| Option | Writes | Needs |
|---|---|---|
| `--extension brainstem` | Every BrainSTEM record the file was made from, with every field, as `ndx-brainstem` tables; and the coordinates of procedures and interfaces as `ndx-anatomical-localization` tables. `--extension localization` is the same | `ndx-brainstem` (pre-release; `pip install "brainstem-nwb[extensions]"`, brings `ndx-anatomical-localization`) |
| `--embed-schemas` | With `--extension brainstem`: the BrainSTEM JSON schemas the records use, fetched from the server's public schema service and embedded in the file | network access to the server (`--url`, default www.brainstem.org) |
| `--herd` | Ontology terms (NCBITaxon, RRIDs, atlas regions) for core values, as a HERD zip next to each file | nothing extra |

Files written with an extension can be read by any pynwb or MatNWB without the extension package installed, because the extension's schema is stored in the file.

## `--extension brainstem` (ndx-brainstem)

Install the [ndx-brainstem](https://github.com/brainstem-org/ndx-brainstem) package (pre-release; the schema may change before 1.0):

```bash
pip install "brainstem-nwb[extensions]"
```

Each file then gets `/general/brainstem`, a `BrainstemMetadata` container. It holds the export provenance and one `BrainstemTable` per kind of record:

| Group | Tables |
|---|---|
| Catalog | `people`, `organisms`, `suppliers`, `publications`, `atlases`, `regions`, `catalog` |
| Lab resources | `lab_resources` |
| Project, subject, session | `projects`, `subjects`, `sessions` |
| Ex vivo | `specimen_sets`, `specimens`, `specimen_procedures` |
| Procedures and devices | `procedure_episodes`, `episode_personnel`, `procedures`, `interfaces`, `procedure_interfaces`, `materials`, `procedure_stages` |
| Acquisitions and stimulation | `acquisitions`, `acquisition_links`, `manipulations`, `manipulation_interfaces` |
| Behavior and time | `behaviors`, `epochs` |
| Logs | `logs`, `log_entries` |

Each table holds one row per record and one column per BrainSTEM field:

- **Text columns.** Strings are stored as they are. Other values (numbers, booleans, typed details such as `type_json`) are JSON. An empty string means no value.
- **Renamed columns.** A field whose name a table cannot use is written as `record_<field>`, e.g. `record_name`, `record_description`. A field ending in `_time` holds ISO 8601 text, so it is written as `<field>_iso` (e.g. `date_time_iso`), because NWB tools read `*_time` columns as seconds.
- **Links.** A link to a record in an earlier table is a ragged `DynamicTableRegion`. Tables are ordered so that links never form a cycle, which keeps `to_dataframe()` working. A link within a table, or to a later table, is written as BrainSTEM ids in a text column. Links to records not in the file are listed in `unresolved_links`.
- **Typed details.** `details_schema` and `coordinates_schema` name the BrainSTEM JSON schemas of a record's typed details and coordinates, e.g. `Procedure/VirusInjection@3.0.0`. A record that stores no schema version gets the id without a version (see [Schemas](#schemas)).
- **Links to core NWB objects.** `interfaces.nwb_device` and `lab_resources.nwb_device` name the NWB `Device` made from the record. `epochs.nwb_epochs` links to the rows of `/intervals/epochs`.

**What is left out:**
- **Administrative lab resources:** licenses, data storages, inventories, regulatory authorities, and the links to them.
- **Administrative fields** of the resources that are kept, such as a stock's cost, dates and storage.
- **Record bookkeeping:** creator and timestamps.
- **Records after the session start:** procedures and log entries.

Everything left out stays in the conversion manifest.

### Schemas

The `schemas` table lists every schema the file's tables name:

| Column | Contents |
|---|---|
| `schema_id` | The schema's id |
| `schema_url` | Its stable URL, e.g. `https://www.brainstem.org/schemas/Procedure/VirusInjection/3.0.0.json`. Published BrainSTEM schema versions never change, so the URL can be cited |
| `schema_json` | The schema itself, when embedded; otherwise empty |

The BrainSTEM schemas are © BrainSTEM, all rights reserved, and are not open source ([terms](https://www.brainstem.org/reference/license.md)). They are embedded unchanged, as a BrainSTEM export embeds them, for the records the file describes; the table's description carries BrainSTEM's notice and the URL of the terms.

The schema itself is embedded in either of two cases:
- **with `--embed-schemas`**, which fetches each version from the server's public schema service (`<server>/schemas/<Family>/<Type>/<version>.json`; no token needed);
- **when the export carries the schemas** (a possible future addition, see the [proposal](design/export-schemas.md)).

Two cases are never embedded:
- **A version the server doesn't have** is reported as `SCHEMA_NOT_AVAILABLE`. Another version is never used in its place.
- **A record that stores no version** gets the id `<Family>/<Type>` and the URL listing the type's versions, `/schemas/<Family>/<Type>/`. The version it followed is unknown, so no schema is embedded for it.

The manifest's `schemas` section records how many schemas were used and embedded, where they came from, and which were missing.

Reading:

```python
from pynwb import NWBHDF5IO

with NWBHDF5IO("sub-X_ses-Y.nwb", "r") as io:
    brainstem = io.read().lab_meta_data["brainstem"]
    procedures = brainstem.brainstem_tables["procedures"].to_dataframe()
    regions_of_first = brainstem.brainstem_tables["procedures"]["target_regions"][0]
```

## Coordinates in both extensions

With `--extension brainstem`, coordinates are stored twice, on purpose:

- **As recorded**, in the `ndx-brainstem` `procedures` and `interfaces` rows: the coordinate system name and the values with their units, for every system, angles included. This copy is lossless.
- **As a point in a defined space**, in `ndx-anatomical-localization` tables. These state the origin, axis orientation and units explicitly, and use the community's predefined atlas spaces, so tools that understand that standard can read them. Each row links to its `ndx-brainstem` row, so the two copies cannot be confused.

The second copy is written only when the coordinates describe a point in a 3D space:

| BrainSTEM coordinate system | Space | Axes | Units |
|---|---|---|---|
| `Stereotaxic_BregmaAbsolute` | origin bregma | x = ML (positive right), y = AP (positive anterior), z = DV (positive ventral); orientation `RAI` | mm |
| `Stereotaxic_LambdaAbsolute` | origin lambda | same | mm |
| `CCF_XYZ_Absolute` | Allen CCFv3 (predefined) | PIR | µm |

Each row links to the procedure or interface it localizes, in the `ndx-brainstem` tables, and names the target regions.

Not written as coordinates:
- **Brain-surface systems** (`*_BrainSurface`): an entry point on the brain surface plus an insertion depth gives no 3D point without the brain's surface geometry. Reported as `LOCALIZATION_NOT_SUPPORTED`.
- **Other atlas spaces.**
- **Angles.**

All of these stay in the `ndx-brainstem` tables.

## `--herd` (ontology terms)

HERD references attach ontology terms to values of core NWB objects:

| NWB value | Term |
|---|---|
| `Subject.species` | NCBI Taxonomy (`NCBITaxon:10090`) |
| `Subject.strain` | the strain's RRID |
| `ElectrodeGroup.location`, `OptogeneticStimulusSite.location` | each region acronym. Allen regions resolve to their structure id; MA and UBERON regions resolve to their OBO term, as BrainSTEM resolves them |
| `DeviceModel.model_number` | the hardware device's or design's RRID |

pynwb stores HERD in a zip file next to the NWB file, `sub-X_ses-Y.herd.zip`, not inside it. Read it with `NWBHDF5IO(path, herd_path=...)`. A plain `dandi upload` of NWB files does not carry the zip. The same identifiers are inside the file in the `ndx-brainstem` tables.

## Why not ndx-optogenetics?

`ndx-optogenetics` (0.4.1) stores viruses, injections, opsins, fibers and light sources in a structured way. Its required fields cannot all be filled from BrainSTEM records without inventing values:

| ndx-optogenetics requires | BrainSTEM |
|---|---|
| `stimulation_software` for the whole container | Not recorded |
| An effector `label` for each site: which injected virus is the opsin | Not distinguished. A construct such as GCaMP is an indicator, not an effector |
| A light source's `excitation_mode` | Not recorded |
| A virus `manufacturer` and titer in vg/mL | Available when the construct has a supplier and the stock a titer |

It will be added once BrainSTEM records these, or once the extension makes them optional. Until then, the same information is complete in the `ndx-brainstem` tables and the `virus` and `stimulus_notes` text.
