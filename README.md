# brainstem-nwb

Export experimental metadata from [BrainSTEM](https://www.brainstem.org) to
[Neurodata Without Borders (NWB)](https://www.nwb.org) files.

`brainstem-nwb` reads a BrainSTEM project export and writes one NWB file per session and subject,
following NWB and DANDI conventions. Each file holds what BrainSTEM knows about the experiment:
- session and subject
- surgeries, viruses and drugs
- devices, electrode groups and optogenetic sites
- acquisitions, behaviors, manipulations and epochs

Alongside the files it writes a versioned **conversion manifest** and a **validation report**.

This release exports **metadata only**. Measured data (recordings, video, imaging) is not converted
yet; the files describe it and point to it. Raw-data conversion with
[NeuroConv](https://github.com/catalystneuro/neuroconv), starting with flat binary extracellular
recordings, is designed and planned (see [docs/design/phase4-raw-data.md](docs/design/phase4-raw-data.md)).

## Install

```bash
pip install brainstem-nwb
# the development version:
pip install git+https://github.com/brainstem-org/brainstem-nwb
```

Python 3.10 or newer. brainstem-nwb reads the BrainSTEM data model from the server at run time, so the
first export needs network access to www.brainstem.org (or your `--url`); the model is then cached (see
[installation](docs/install.md#the-brainstem-data-model)). Installing also installs [pynwb](https://github.com/NeurodataWithoutBorders/pynwb),
[NWB Inspector](https://github.com/NeurodataWithoutBorders/nwbinspector) and the
[BrainSTEM Python API tools](https://github.com/brainstem-org/brainstem_python_api_tools).

## Quick start

From a project export downloaded in BrainSTEM (Project → Download → JSON):

```bash
brainstem-nwb export --export-file brainstem-export.json.gz --output ./nwb/
```

Or fetch the export directly (needs read access to the project):

```bash
brainstem login                     # once, from the BrainSTEM API tools
brainstem-nwb export --project PROJECT_UUID --output ./nwb/
brainstem-nwb export --session SESSION_UUID --output ./nwb/   # one session's export
```

From Python:

```python
from brainstem_nwb import export_project

result = export_project(project_id="PROJECT_UUID", output_dir="./nwb")
# or: export_project(export_file="brainstem-export.json.gz", output_dir="./nwb")
print(result.exit_code, result.manifest.summary)
```

The output directory then contains:

```
nwb/
  sub-<subject>/sub-<subject>_ses-<session>.nwb
  brainstem-nwb-manifest.json      what was exported, from which records, with every warning
  validation-report.json / .txt    pynwb, NWB Inspector (DANDI configuration) and BrainSTEM checks
  source/brainstem-export-….json.gz   the export the files were built from (when fetched)
```

Other commands:
- **Dry run:** `brainstem-nwb manifest --export-file … -o manifest.json` writes only the manifest, so you can inspect what would be written.
- **One session:** `brainstem-nwb export … --session NAME`.
- **Validate existing files:** `brainstem-nwb validate ./nwb/`.

Some NWB fields are not in a BrainSTEM export, so they are never guessed: experimenter, lab and institution. Supply them in a configuration file:

```toml
# brainstem-nwb.toml  (use with --config brainstem-nwb.toml)
[nwbfile]
experimenter = ["Last, First"]
lab = "My Lab"
institution = "My University"
```

A fully reproducible example is in [examples/synthetic-ephys](examples/synthetic-ephys/).

## Principles

- **Nothing is invented.** No time series, electrode positions or other observations are generated from metadata. Fields BrainSTEM does not have stay empty, and the manifest records why. Each value is marked present, missing, unknown, not applicable or not exported.
- **Nothing is silently dropped.** Every field of every exported record is accounted for:
  - mapped to NWB,
  - used to link records,
  - or kept in the manifest, with the reason.

  The [mapping specification](docs/mapping-spec.md) is generated from the code.
- **Traceable.** Every file carries a provenance block naming its BrainSTEM records, the exporter and mapping versions, and the checksum of the source export. Its NWB identifier is derived from the content, so re-exporting unchanged records gives the same identifier.
- **Core NWB by default.** With `--extension brainstem`, every BrainSTEM record is also stored losslessly in the file as `ndx-brainstem` tables. See [extensions](docs/extensions.md).

## Documentation

- [Installation and authentication](docs/install.md)
- [Quick start and CLI](docs/cli.md) · [Python API](docs/python-api.md)
- [Mapping specification](docs/mapping-spec.md) · [Warning codes](docs/warnings.md)
- [Conversion manifest](docs/manifest.md) · [Validation](docs/validation.md)
- [Supported modalities](docs/modalities.md) · [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/design/architecture.md) · [Design decisions](docs/design/decisions.md)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## License

The code is released under the [MIT License](LICENSE).

The BrainSTEM data model and its JSON schemas are not part of this package and are not covered by that
license: they are © BrainSTEM, all rights reserved ([terms](https://www.brainstem.org/reference/license.md)).
brainstem-nwb reads them from the BrainSTEM server as an API client. `--embed-schemas` embeds the schemas of a
file's records unchanged, as a BrainSTEM export does, with BrainSTEM's notice next to them.
