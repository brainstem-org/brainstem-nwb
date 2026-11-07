# Proposal: JSON schemas in the project export (format 2.2)

**Status:** proposal, deferred. BrainSTEM now publishes every schema version at a stable URL (`/schemas/<Family>/<Type>/<version>.json`, with the URL as `$id`). brainstem-nwb uses that: it writes each schema's URL into the file and, with `--embed-schemas`, fetches and embeds the schemas itself (see [extensions](../extensions.md#schemas)). Carrying the schemas in the export, as proposed below, would make embedding work offline too.

This page is for whoever implements the change in the BrainSTEM server's project export (`stem/services/project_export.py`). It specifies an addition to the export: the JSON schemas that the exported records' typed JSON fields were validated against.

## Why

Many records keep their typed details in JSON fields (`type_json`, `coordinates_json`, ...) and record which schema version the values follow (`type_schema_version`, ...). An export holds the values and the version string, but not the schema. A reader therefore can't tell from the file alone what the fields mean, which units they allow, or what their enum codes are.

`brainstem-nwb --extension brainstem` names the schema of every row (`details_schema = "Procedure/VirusInjection@3.0.0"`). When the export carries the schemas, it also embeds them in the NWB file (the `schemas` table). The file then documents its own details, without access to the BrainSTEM server or a login.

## Format

A new top-level key `schemas`, next to `export_info` and `records`:

```json
{
  "export_info": {"format_version": "2.2", "...": "..."},
  "records": {"...": []},
  "schemas": {
    "Procedure/VirusInjection@3.0.0": {"$schema": "http://json-schema.org/draft-07/schema#", "schemaVersion": "3.0.0", "...": "..."},
    "Procedure/VirusInjection@2.1.0": {"...": "..."},
    "Coordinates/Stereotaxic_BregmaBrainSurface@2.0.0": {"...": "..."},
    "SubjectLog/Weighing@1.1.1": {"...": "..."}
  }
}
```

- **Key:** `<Family>/<Type>@<version>`. This is a logical identifier: the schema family (`Procedure`, `Coordinates`, ...), the type code, and the stored `*_schema_version` value. It does not depend on where the schema files live, so it survives a reorganization of the files.
- **Value:** the schema file's JSON, as stored (not re-serialized with changes).
- **Order:** keys sorted, so unchanged data still exports identically apart from `exported_at`.
- **Only schemas the exported records use** are included, each once.
- **Not in `export_info`.** That stays small, and its doc says it never holds more than metadata about the export.

## Which schemas to include

For every exported record, for each typed JSON field that has a value (not `null`, `{}` or `[]`), include the schema it was validated against:

| Model | JSON field | Family | Type from | Version from |
|---|---|---|---|---|
| `modules.procedure` | `type_json` | `Procedure` | `type` | `type_schema_version` |
| `modules.procedure` | `coordinates_json` | `Coordinates` | `coordinates` | `coordinates_schema_version` |
| `modules.dataacquisition` | `type_json` | `DataAcquisition` | `type` | `type_schema_version` |
| `modules.manipulation` | `type_json` | `Manipulation` | `type` | `type_schema_version` |
| `modules.equipment` | `type_json` / `coordinates_json` | `Equipment` / `Coordinates` | `type` / `coordinates` | `type_schema_version` / `coordinates_schema_version` |
| `modules.experimentalinterface` | `type_json` / `coordinates_json` | `ExperimentalInterface` / `Coordinates` | `type` / `coordinates` | `type_schema_version` / `coordinates_schema_version` |
| `modules.specimenprocedure` | `type_json` | `SpecimenProcedure` | `type` | `type_schema_version` |
| `stem.specimenset`, `stem.specimen` | `type_json` | `SpecimenSet`, `Specimen` | `type` | `type_schema_version` |
| `resources.consumable` | `type_json` | `Consumable` | `type` | `type_schema_version` |
| `resources.hardwaredevice` | `type_json` | `HardwareDevice` | `type` | `type_schema_version` |
| `modules.consumablestock` | `type_json` | `ConsumableStock` | `type` | `type_schema_version` |
| `modules.moduleslogentry`, `modules.startendmoduleslogentry` | `type_json` | the log's family (`SubjectLog`, `ProcedureLog`, `SpecimenLog`) | the log's `type` | `type_schema_version` |
| `modules.materialusage` | `details_json` | `MaterialUsage` | `type` | `details_schema_version` |
| `modules.procedurestage` | `details_json` | (as the stage form validates it) | `detail_type` | `details_schema_version` |
| `modules.dataacquisitioninterface`, `modules.manipulationinterface` | `metadata_json` | (as the form validates it) | | `metadata_schema_version` |

The rows marked "as the form validates it" are the cases I couldn't confirm from the forms. Use whatever family and type the form passes to `clean_json` / `clean_json_field`. The rule is: **the schema the server would use to validate this value**.

Exports also have JSON fields that are always validated against one fixed schema (`extra_content_json` → `Session/Array.json`, `repository_links_json` → `Session/Repository.json`, `external_identifiers` → `<Family>/ExternalIdentifiers.json`). Including those is welcome, under the same key pattern, but not required.

### Resolving a version to a file

The schema files stay where they are, so these paths remain valid. Changing how schemas are served to users and the front end doesn't affect the export, which reads them from disk.

- **Version equals the current `schemaVersion`** of `schemas/<Family>/<Type>.json`: use that file.
- **Older version:** use the archive, `schema_versions/<Family>/<Type>_<M>_<m>_<p>.json`. `brainstem/utils/schema_utils.get_all_schema_versions()` already lists both.
- **Version empty** (records saved before versioning, or by paths that don't set it): `clean_json` treats a missing version as "the latest". Include the current schema under the key **without a version**: `Procedure/VirusInjection`. brainstem-nwb writes `details_schema` without `@version` for such records, so the keys match.
- **Version not found** in either place (a gap in the archive): leave it out of `schemas` and list it in a new `export_info.schemas_missing`, a sorted list of keys. Never substitute another version.

## Public schemas

BrainSTEM is changing how schemas are served to users and the front end; the files themselves stay where they are. If the new way of serving gives each schema version a stable public URL, that URL should be the schema's `$id`, e.g. `https://www.brainstem.org/schemas/Procedure/VirusInjection/3.0.0.json`. Two things follow:

- The URL travels inside the copy embedded in each export and NWB file, so readers have both the copy and the link.
- brainstem-nwb can also write the URL next to each schema in the NWB file's `schemas` table.

Embedding the copy remains the main mechanism: a file stays self-describing offline, and readable if a URL ever changes.

## Size

Each schema is a few KB, and an export includes only the distinct (family, type, version) combinations its records use. That's typically tens of schemas: well under a megabyte, even for large projects. The whole `schemas/` tree is about 6 MB.

## Versioning

- Adding a top-level key is a **minor** change: format **2.2**.
- 2.x readers must already ignore keys they don't know.
- Update `docs/project-export-format.md`: the layout, a "Schemas" section with the rules above, and the change log.

## Server tests

1. An export of records with typed details includes exactly the schemas those records use. Keys are sorted, and values are equal to the files on disk.
2. A record whose `type_schema_version` is an older version gets the archived file.
3. A record with an empty version gets the current schema under the version-less key.
4. A missing archived version is listed in `export_info.schemas_missing` and not substituted.
5. Records with empty JSON fields add no schema.
6. Exporting unchanged data twice gives identical `schemas`.
7. Session exports include only the schemas of their records.

## What brainstem-nwb does with it

- Reads `payload["schemas"]`. This is already implemented: `ProjectExport.schemas`.
- With `--extension brainstem`, writes the schemas named by the file's `details_schema` values into the `schemas` table (`BrainstemSchemaTable`: `schema_id`, `schema_url`, `schema_json`; `coordinates_schema` values are listed too).
- When 2.2 is released: raises `KNOWN_EXPORT_MINOR` to 2, names coordinate schemas in `details_schema` too, and reports keys listed in `schemas_missing` as a warning.
