# Validation

This page explains how exported files are validated and how to read the validation report.

Unless you pass `--no-validate`, every file is checked three ways:

1. **NWB schema validation** with `pynwb.validate`.
2. **NWB Inspector** best-practice checks. By default these use the `dandi` configuration, the one DANDI applies on upload.
3. **BrainSTEM checks**:
   - **Against the manifest:** the NWB identifier, session and subject ids, epoch count and devices match it, and the file is the one recorded (sha256).
   - **Metadata-only content:** the provenance block can be read, the file holds no acquisition, stimulus or processed data, and it carries the `metadata-only` keyword.
   - **DANDI readiness:** the subject has `subject_id`, `species`, `sex`, and age or date of birth.

## Severity

| Finding | Severity |
|---|---|
| pynwb validation error, Inspector CRITICAL, failed BrainSTEM manifest check | error |
| Inspector BEST_PRACTICE_VIOLATION, DANDI-readiness gap | warning |
| Inspector ERROR: a check crashed on the file, which is an Inspector problem rather than a file problem | warning |
| Inspector BEST_PRACTICE_SUGGESTION | info |

Some Inspector checks always fail on metadata-only files, so they are reported as `info`, marked `expected`, and given the reason. For example, an optogenetic stimulus site has no `OptogeneticSeries` because there is no stimulus data. The list is `EXPECTED_FINDINGS` in `brainstem_nwb/validation/checks.py`. Checks that fire on `ndx-brainstem` tables by design are listed in `EXPECTED_ON_BRAINSTEM_TABLES` there and are downgraded in the same way:
- JSON objects in text columns: the typed details are stored as JSON;
- single-row tables;
- link indices that look binary.

CRITICAL findings are never downgraded. With `--extension brainstem`, the BrainSTEM checks also compare the extension's tables and row ids with the manifest.

Typical findings and what to do:

| Finding | Severity | What to do |
|---|---|---|
| `check_subject_age` | error (CRITICAL) | Add the subject's birth date in BrainSTEM |
| `check_experimenter_exists`, `check_institution` | info | Set them in the [configuration](cli.md#configuration) |

## Reports

- `validation-report.json`: machine readable, with its schema in `schemas/validation-report-1.0.0.schema.json`.
- `validation-report.txt`: findings grouped by file and severity, followed by totals.

## Conversion warnings and validation findings

These are two different things:
- **Conversion warnings** are in the manifest. They describe what happened while mapping, for example "brain regions are not in the export".
- **Validation findings** are in the report. They describe the file as written.

Some causes appear in both. A missing birth date, for example, gives the manifest warning `SUBJECT_AGE_UNKNOWN` and the validation finding `check_subject_age`.
