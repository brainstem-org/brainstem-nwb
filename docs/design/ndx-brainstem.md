# ndx-brainstem: design draft

**Status:** implemented as version 0.2.0 (pre-release, on PyPI) in `brainstem-org/ndx-brainstem`, written by `brainstem-nwb --extension brainstem`. User documentation: [extensions](../extensions.md). The draft below is kept for the reasoning. The implementation differs from it in these ways:

- **Columns generated from the data model.** Every BrainSTEM field of a table's records is a column named as the field, with `record_<field>` for reserved names and `<field>_iso` for `*_time` fields; only `brainstem_id` and `brainstem_model` are required. This replaces the hand-picked columns and the JSON `fields` column of the draft.
- **Links form no cycle.** Tables are ordered so that every link points to an earlier table, because hdmf recurses without end on cyclic links in `to_dataframe()`. Other links are written as ids.
- **`resources` is split** into `organisms`, `suppliers`, `publications`, `atlases`, `catalog` and `lab_resources`. Licenses, data storages and inventories are left out (administrative), and so are stocks' cost, dates and storage.
- **Links to core NWB objects:** `nwb_device` holds the name of the NWB `Device`, not an object reference; `epochs.nwb_epochs` links to `/intervals/epochs`.
- **Dependency on ndx-anatomical-localization.** `ndx-brainstem` includes the `ndx-anatomical-localization` namespace, so that pynwb validates localization tables pointing at `BrainstemTable` rows. Because that dependency exists either way, `--extension brainstem` always writes both: the coordinates as recorded in the `ndx-brainstem` rows, and as points in a defined space in localization tables.
- **HERD is a sidecar:** pynwb writes HERD to a zip next to the file, not inside it.
- **`ndx-optogenetics` is not used:** its required fields cannot be filled honestly ([details](../extensions.md#why-not-ndx-optogenetics)).

This page is for the BrainSTEM team deciding on the extension and for its future implementers. It proposes an NWB extension that carries BrainSTEM's structured metadata inside the NWB file without losing anything, and explains how it fits with core NWB and the community extensions. The questions that need a decision are at the end.

## Why an extension

Today a metadata-only file holds BrainSTEM metadata in two places:

- **core NWB fields:** Subject, Device and DeviceModel, ElectrodeGroup, OptogeneticStimulusSite, the epochs table, and free text (`surgery`, `virus`, `pharmacology`, `stimulus_notes`, `data_collection`, `slices`, `notes`);
- **the conversion manifest:** a JSON file next to the NWB files, holding every record as exported.

The text is readable but not structured. The manifest is lossless, but it is a separate file: `dandi upload` does not carry it, so on DANDI the structure would survive only as text.

Community extensions help only partly:
- **[ndx-optogenetics](https://github.com/rly/ndx-optogenetics)** and **[ndx-ophys-devices](https://github.com/catalystneuro/ndx-ophys-devices):**
  - their viral vector has no fields for capsid, promoter or batch, and their injection has none for rate or route;
  - they require fields that BrainSTEM may lack, such as a virus manufacturer and titer, or a fiber's numerical aperture.
- **[ndx-anatomical-localization](https://github.com/catalystneuro/ndx-anatomical-localization):** at 0.1.0, it is still early.

So the extension is the lossless layer. Community extensions are used alongside it, where their objects can be filled honestly.

## Design principles

1. **Generic tables, not one type per BrainSTEM schema.** BrainSTEM has about 150 typed JSON schemas (procedure, acquisition, manipulation, interface, material and consumable types), and they change. A neurodata type per schema would need an extension release for every schema change. Instead:
   - each record family gets one table;
   - common fields are typed columns;
   - the type-specific part is a JSON `details` column that names its BrainSTEM schema and version.
2. **Links, not copies.** Rows reference each other (a material to its procedure, a procedure to its target regions) and point to the core NWB objects made from them (an interface to its `Device`; an acquisition to its `epochs` rows).
3. **Every row carries its BrainSTEM id and model label.** A file can always be traced back to the records it came from.
4. **Generated, not hand-written.** The rows are filled from the same field inventory and mapping registry that drive the core mapping, so the extension cannot drift from BrainSTEM. The coverage test is extended so that every exported field lands in a column or in `details`.
5. **No fabrication.** Empty stays empty. Columns are optional wherever BrainSTEM fields are.

## Proposed schema

### Container

One `LabMetaData` container, named `brainstem`, in `/general`. This is the same pattern ndx-anatomical-localization uses.

| Attribute | Example |
|---|---|
| `export_format_version` | `2.1` |
| `export_scope` | `session` |
| `exported_at` | ISO 8601 |
| `source_sha256` | sha256 of the export |
| `project_ids`, `session_id`, `subject_id`, `unit_id` | BrainSTEM ids |
| `exporter`, `exporter_version`, `mapping_version` | `brainstem-nwb`, `0.1.0`, `1.2.0` |
| `content_sha256` | digest the NWB identifier is derived from |

This replaces the JSON provenance block in `NWBFile.notes`.

### Tables

All tables are `DynamicTable`s and share these columns:

| Column | Type | Notes |
|---|---|---|
| `brainstem_id` | text | record id (UUID; users have integer ids, written as text) |
| `brainstem_model` | text | model label, e.g. `modules.procedure` |
| `type` | text, optional | vocabulary code, e.g. `VirusInjection` |
| `details` | text (JSON), optional | `type_json` / `details_json` as exported |
| `details_schema` | text, optional | `Procedure/VirusInjection@3.0.0`: BrainSTEM schema family, type and `*_schema_version` |
| `notes` | text, optional | |

| Table | Rows | Extra columns (beyond the common ones) |
|---|---|---|
| `procedures` | the subject's procedures up to the session | `date_time`, `coordinate_system`, `coordinates` (JSON), `target_regions` → `regions` (ragged), `performed_by` → `people`, `episode` → `procedure_episodes`, `protocol` → `resources`, `equipment` → `resources` (ragged) |
| `procedure_episodes` | surgical and other episodes | `name`, `intervention_class`, `start`, `end`, `status`, `personnel` → `people` (ragged), `personnel_roles` (ragged text) |
| `materials` | materials used in procedures and interfaces | `procedure` → `procedures`, `interface` → `interfaces`, `catalog_entry` → `resources`, `stock` → `resources`, `manual_name`, `order` |
| `interfaces` | implanted or placed devices (probes, fibers, windows) | `name`, `persistence`, `installed_at`, `removed_at`, `coordinate_system`, `coordinates`, `target_regions` → `regions`, `design` → `materials`, `nwb_device` (object reference to the core `Device`) |
| `procedure_interface_links` | procedure ↔ interface relationships | `procedure`, `interface`, `relationship` (created, positioned, …) |
| `acquisitions` | data acquisitions of the session | `order`, `interfaces` → `interfaces` (ragged), `equipment` → `resources`, `procedures` → `procedures`, `epochs` (region into `/intervals/epochs`), `interface_metadata` (JSON) |
| `manipulations` | manipulations of the session | like `acquisitions`; `details` holds the list of stimulation protocols |
| `behaviors` | behaviors of the session | `assay` → `resources`, `setup` → `resources`, `epochs` (region into `/intervals/epochs`) |
| `specimens` | specimen sets and specimens (ex vivo) | `kind` (set or specimen), `parent` → `specimens`, `laterality`, `preparation_conditions`, `quality`, `target_regions` → `regions` |
| `specimen_procedures` | specimen procedures | `date_time`, `specimens` → `specimens` (ragged) |
| `log_entries` | subject and procedure log entries | `log_type`, `log` (BrainSTEM id), `date_time`, `end_date_time`, `performed_by` → `people` |
| `regions` | brain regions referenced | `acronym`, `name`, `atlas_region_id`, `atlas` → `resources` |
| `resources` | catalog and lab resources referenced: consumables, stocks, hardware devices, equipment, setups, assays, protocols, licenses, data storages, suppliers, publications, paradigms, setup types, atlases, species, strains | `name`, `rrid`, `external_identifiers` (JSON), `supplier` → `resources`, `url` |
| `people` | people named on the records | `first_name`, `last_name` (see open question 3) |

`→` marks a `DynamicTableRegion` into another table; *ragged* means a ragged column with a `VectorIndex`.

**Ontologies.** Ontology terms are annotated with NWB's HERD (`NWBFile.external_resources`) rather than in this extension:
- species → NCBITaxon;
- strains, consumables, hardware and paradigms → their RRIDs;
- regions → atlas structure ids (Allen) or UBERON.

### Schema sketch (YAML)

A first cut of the spec, for the shape only. Field docs are shortened.

```yaml
namespaces:
- name: ndx-brainstem
  version: 0.2.0
  doc: BrainSTEM experimental metadata (brainstem.org), as exported by brainstem-nwb
  schema:
  - namespace: core
  - source: ndx-brainstem.extensions.yaml

groups:
- neurodata_type_def: BrainstemMetadata
  neurodata_type_inc: LabMetaData
  default_name: brainstem
  attributes:
  - {name: export_format_version, dtype: text}
  - {name: export_scope, dtype: text}
  - {name: exported_at, dtype: isodatetime}
  - {name: source_sha256, dtype: text}
  - {name: mapping_version, dtype: text}
  - {name: exporter_version, dtype: text}
  - {name: project_ids, dtype: text, shape: [null]}
  - {name: session_id, dtype: text}
  - {name: subject_id, dtype: text, required: false}
  groups:
  - {neurodata_type_inc: BrainstemProcedureTable, name: procedures, quantity: '?'}
  - {neurodata_type_inc: BrainstemMaterialTable, name: materials, quantity: '?'}
  - {neurodata_type_inc: BrainstemInterfaceTable, name: interfaces, quantity: '?'}
  - {neurodata_type_inc: BrainstemRecordTable, quantity: '*'}   # acquisitions, manipulations, behaviors, ...
  - {neurodata_type_inc: BrainstemResourceTable, name: resources, quantity: '?'}
  - {neurodata_type_inc: BrainstemRegionTable, name: regions, quantity: '?'}

- neurodata_type_def: BrainstemRecordTable
  neurodata_type_inc: DynamicTable
  doc: BrainSTEM records of one family; type-specific values in `details` (JSON, BrainSTEM schema `details_schema`)
  datasets:
  - {name: brainstem_id, neurodata_type_inc: VectorData, dtype: text}
  - {name: brainstem_model, neurodata_type_inc: VectorData, dtype: text}
  - {name: type, neurodata_type_inc: VectorData, dtype: text, quantity: '?'}
  - {name: details, neurodata_type_inc: VectorData, dtype: text, quantity: '?'}
  - {name: details_schema, neurodata_type_inc: VectorData, dtype: text, quantity: '?'}
  - {name: notes, neurodata_type_inc: VectorData, dtype: text, quantity: '?'}

- neurodata_type_def: BrainstemInterfaceTable
  neurodata_type_inc: BrainstemRecordTable
  datasets:
  - {name: name, neurodata_type_inc: VectorData, dtype: text}
  - {name: installed_at, neurodata_type_inc: VectorData, dtype: text, quantity: '?'}
  - name: nwb_device
    neurodata_type_inc: VectorData
    dtype: {target_type: Device, reftype: object}
    quantity: '?'
  - {name: target_regions, neurodata_type_inc: DynamicTableRegion, quantity: '?'}
  - {name: target_regions_index, neurodata_type_inc: VectorIndex, quantity: '?'}
  # ... procedures, materials, resources, regions follow the same pattern
```

## How it fits with the other layers

```
core NWB (always)          Subject, Device/DeviceModel, ElectrodeGroup, OptogeneticStimulusSite, epochs, text fields
community (optional)       ndx-optogenetics: viruses, injections, effectors, fibers, sites;
                           ndx-anatomical-localization: atlas coordinates            ← filled only where honest
ndx-brainstem (lossless)   every record, its details JSON, and the links between them  ← brainstem_id on every row
HERD                       ontology terms for species, strains, regions, RRIDs
manifest (sidecar)         the conversion record: attribution, value states, warnings, validation
```

- **One source per value.** Every core or community object is filled from the same records as the matching `ndx-brainstem` row. An `interfaces` row links to its `Device` through `nwb_device`. Community objects carry the `brainstem_id` in their description.
- **The manifest stays.** It records what the conversion did (attribution, value states, warnings). The extension holds the metadata.
- **Text fields stay.** `surgery`, `virus` and the other text fields remain for readers that don't load extensions.

## Compatibility and maintenance

- **Readers without the package.** pynwb caches the extension's schema in each file. pynwb, MatNWB and DANDI can therefore read the file without installing `ndx-brainstem`, through generated classes.
- **Size.** Metadata tables are tiny next to raw data.
- **Versioning:**
  - the extension follows semantic versioning on its own;
  - a new BrainSTEM schema version needs no extension release, because `details_schema` records it;
  - a new BrainSTEM record family needs a new table, which is a minor extension release.
- **Packaging.** The NWB extension catalog expects a separate repository built from `ndx-template`, e.g. `brainstem-org/ndx-brainstem`. `brainstem-nwb` depends on it and writes it behind an option at first (`--extension brainstem`), and by default once the schema is stable.

## Implementation plan (after review)

1. **Create the extension repository** `ndx-brainstem` from `ndx-template`: the spec YAML, generated Python classes, and round-trip tests with pynwb (and MatNWB if wanted).
2. **Write it from brainstem-nwb:** a `mapping/extension.py` that fills the tables from the unit's records, and a writer step.
   - The coverage test is extended so that every field is in a column or in `details`.
   - A validation check confirms that the extension's row ids match the manifest.
3. **Community extensions** (separate option, versions pinned together):
   - ndx-optogenetics for viruses, injections and sites, where the required fields exist;
   - ndx-anatomical-localization for atlas coordinates once they are available.
4. **HERD annotations** for species, strains, regions and RRIDs.
5. **Submit `ndx-brainstem` to the NWB extension catalog.**

## Questions for the BrainSTEM team

1. **JSON schema URLs.** Can BrainSTEM publish its JSON schemas at stable, versioned URLs, e.g. `https://www.brainstem.org/schemas/Procedure/VirusInjection/3.0.0.json`? `details_schema` could then be a resolvable link rather than a name.
2. **Scope of `resources`.** Should lab resources the exporting user can read (setups, protocols, licenses, data storages) be written into files that may be shared publicly on DANDI, or only catalog entries? This could be a `--public` switch that drops lab resources and notes.
3. **People.** Should `people` hold names by default, or only with an opt-in? The export includes names, but an NWB file on DANDI is public.
4. **Repository and name.** Is `brainstem-org/ndx-brainstem` with the namespace `ndx-brainstem` the right home and name?
5. **Default.** Should the extension be on by default once stable? Every reader can open the file, but tools that don't know the extension will ignore the tables.
