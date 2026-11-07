# Design decisions

This page is for contributors and maintainers. It records the main design choices in `brainstem-nwb` and why they were made. Each entry gives the decision, the reason, and its consequence.

### 1. The project export is the only record source

**Decision.** Records come only from a BrainSTEM export (format 2.x) of a project or of one session, either fetched or downloaded.

**Why.** One versioned, self-contained payload with stable identifiers makes exports reproducible and testable offline. The alternative was per-model REST calls, which would need many requests and our own relation handling.

**Consequences.**
- Export needs read access (format 2.1).
- Format 2.1 includes the referenced catalog records: brain regions and atlases, suppliers, publications, paradigms, setup types, regulatory authorities, user names and log entries.
- Records an export does not contain are reported as `not_exported` rather than looked up elsewhere. This covers 2.0 exports, and lab resources the exporting user cannot read, which 2.1 names in `export_info.restricted`.
- A session export is the natural unit for one session's files, and it is what a web "Download as NWB" would use.

### 2. One NWB file per session and subject

**Decision.** Each session produces one NWB file per subject, named `sub-<subject>/sub-<subject>_ses-<session>.nwb`.

**Why.** An NWB file describes one subject, but a BrainSTEM session can have several. Writing per subject follows the DANDI layout.

**Consequences.**
- Records are attributed to subjects through their links, and records linked to no subject are shared, with a warning.
- A session without a subject is not exported unless `--allow-no-subject` is given.

### 3. Core NWB by default, extensions opt-in

**Decision.** By default, metadata is written only to core NWB fields: free text, Device, ElectrodeGroup, OptogeneticStimulusSite, the epochs table and Subject. NWB extensions are written only when asked for: `--extension brainstem` (every record as `ndx-brainstem` tables, coordinates as `ndx-anatomical-localization` tables) and `--herd`.

**Why.** Core NWB files can be read by everyone without extra packages. The extensions are pre-release, so they stay opt-in until their schemas are stable.

**Consequences.**
- Structured BrainSTEM details that core NWB cannot hold structurally are written as deterministic text.
- They are also kept verbatim in the manifest, and with `--extension brainstem` losslessly in the file.
- See [extensions](../extensions.md); ndx-optogenetics is not used (it would need values BrainSTEM does not record).

### 4. Nothing is fabricated

**Decision.** The exporter writes only what BrainSTEM records.

**Why.** Invented values would be indistinguishable from measured ones in the output.

**Consequences.** In metadata-only mode:
- **No data objects.** No time series, no stimulus series, no electrode rows, no positions.
- **No guessed values.** No experimenter inferred from surgeons, and no units guessed for legacy bare numbers.
- **No incomplete objects.** No imaging planes or intracellular electrodes, because their required fields would have to be guessed.
- **Required fields BrainSTEM lacks** are either filled with an explicit placeholder that says so (session description), or the object is not written. A warning is recorded in both cases.

### 5. Five value states

**Decision.** Every intended NWB destination is recorded in the manifest with one of five states: `present`, `missing`, `unknown`, `not_applicable` or `not_exported`.

**Why.** This preserves the difference between "BrainSTEM says unknown" (e.g. sex `U`), "the field is empty", "does not apply" and "not in the export".

### 6. Provenance in `NWBFile.notes`

**Decision.** Provenance is written as a fenced JSON block at the end of the notes.

**Why.** This needs no extension and passes NWB Inspector. The alternatives were the `scratch` space (discouraged) and a custom `LabMetaData` (would need an extension).

**Consequences.**
- The block names the BrainSTEM records, exporter and mapping versions, and the source export checksum.
- Record ids also appear in the device descriptions and the epochs `brainstem_id` column.

### 7. A deterministic identifier

**Decision.** The NWB identifier is derived from the content: a uuid5 of the session, the subject, the mapping version and a digest of the planned content.

**Why.** Re-exporting unchanged records gives the same identifier, while any change in what is written gives a new one. It also lets an export run recognize a file it already wrote, which it then marks `up_to_date`.

### 8. Pydantic models for the manifest

**Decision.** The manifest is defined as pydantic models.

**Why.** One definition provides validation, serialization and the committed JSON Schema (`schemas/`).

### 9. The data model from the server, the mapping specification from the code

**Decision.** Neither is written by hand:
- **The data model** (record types, fields, links, vocabularies) is read at run time from the server's reference documents and cached; it is not bundled.
- **The mapping specification** is generated from the rule registry.

**Why.** The data model always matches the server the export came from, and BrainSTEM's terms do not allow redistributing copies of it. Tests fail when the mapping specification drifts from the code, or when a field the server publishes is unaccounted for.

### 10. Identifier characters

**Decision.** A `/` in a subject or session name is replaced by `-` in `subject_id` and `session_id`, with the warning `IDENTIFIER_SLASH_REPLACED`.

**Why.** NWB Inspector marks such identifiers as critical, because they break DANDI paths.

**Consequences.** The original name is kept in the manifest.
