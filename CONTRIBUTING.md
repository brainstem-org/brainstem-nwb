# Contributing to brainstem-nwb

Contributions are welcome: new mappings, raw-data converters, fixes and documentation. This page explains how to set up a development environment and make the most common kinds of change.

## Development setup

```bash
git clone https://github.com/brainstem-org/brainstem-nwb
cd brainstem-nwb
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,extensions]"
pytest                 # unit and integration tests
ruff check src tests scripts
mypy
```

The tests use only synthetic BrainSTEM exports (`tests/fixtures/`); no account is needed. They run against the data model www.brainstem.org publishes, so the first run needs network access; it is then cached for an hour, and used from the cache when offline. Set `BRAINSTEM_NWB_DATA_MODEL` to a directory with the reference documents to run without network.

## How the code is organized

See [docs/design/architecture.md](docs/design/architecture.md). In short:

| Directory | Purpose |
|---|---|
| `retrieval/` | Reads the project export |
| `store/` | Indexes records and resolves links |
| `normalize/units.py` | Decides which records go into which file |
| `mapping/` | Fills the NWB plan and the manifest |
| `nwb/` | Writes the file |
| `validation/` | Checks it |

## Changing or adding a mapping

1. Find the mapper in `src/brainstem_nwb/mapping/` and edit it. Every mapper function declares its rules with `@rules(MappingRule(...))`. A rule records its source fields, NWB destination, transformation, units, condition and what happens when data is missing. Update the rule along with the code.
2. Record every destination with `ctx.map(rule_id, nwb_path, state, value, sources)`, and every gap with `ctx.warn(CODE, ...)`. A new warning code must be added to `manifest/warnings.py` with a severity and a description.
3. Never invent values. If BrainSTEM does not record something, leave the NWB field empty. If NWB requires it, either skip the object or use an explicit placeholder that says it is a placeholder, and warn either way.
4. If the change alters what is written to files, bump `MAPPING_VERSION` in `_version.py`.
5. Regenerate the derived files and run the tests:

   ```bash
   python scripts/generate_docs.py     # docs/mapping-spec.md, docs/warnings.md, schemas/
   pytest
   ```

   `tests/test_spec.py` fails if any exported BrainSTEM field is not accounted for. Each field must be:
   - mapped by a rule;
   - listed in `STRUCTURAL` (used to link records);
   - or listed in `MANIFEST_ONLY` with a reason.

## When BrainSTEM's data model changes

brainstem-nwb reads the data model from the server at run time (`store/datamodel.py`), so nothing is regenerated. When www.brainstem.org gains a field, `tests/test_spec.py` fails and lists it: map it, mark it `STRUCTURAL`, or add it to `MANIFEST_ONLY` with a reason. A new record type in the export goes into `EXPORT_LABELS` in `store/datamodel.py`. When the server's data model generation changes (`brainstem-nwb data-model` shows it), review the mappings and update `SUPPORTED_DATA_MODELS` in `_version.py`.

The contract exports (`tests/fixtures/exports/server_contract_2_1*.json`) are written by the server's own export builder. Regenerating them needs a BrainSTEM server checkout, so it is a maintainer task; it uses a throwaway database:

```bash
/path/to/brainstem/.venv/bin/python scripts/make_contract_export.py /path/to/brainstem \
    tests/fixtures/exports/server_contract_2_1.json
```

## Test fixtures

Synthetic exports are built in `tests/fixtures/scenarios.py` with `ExportBuilder`. The builder fills every field the server would write. After changing a scenario, run:

```bash
python tests/fixtures/regen.py
```

This rewrites `tests/fixtures/exports/*.json` and the example export.

## Adding a raw-data converter (Phase 4)

Implement `brainstem_nwb.raw.base.RawDataConverter` and register it. A converter in this repository registers itself in `raw/registry.py`; one in another package uses the `brainstem_nwb.raw_converters` entry point. See [docs/design/phase4-raw-data.md](docs/design/phase4-raw-data.md).

## Releases

1. Set the version in `src/brainstem_nwb/_version.py` and date the release in `CHANGELOG.md`.
2. Commit, then tag and push: `git tag v0.1.0 && git push origin v0.1.0`.

The `Release` workflow checks that the tag matches the version, runs the tests, builds, and publishes to PyPI with trusted publishing (no token).

## Pull requests

- Keep each change focused, and include tests.
- Describe user-visible changes in `CHANGELOG.md`.
- Public API changes (names exported from `brainstem_nwb`) need a note in the changelog. Breaking changes need a major version bump after 1.0.
