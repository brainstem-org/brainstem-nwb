# brainstem-nwb

`brainstem-nwb` exports experimental metadata from [BrainSTEM](https://www.brainstem.org) to [NWB](https://www.nwb.org) files. It reads a BrainSTEM project export and writes one file per session and subject. Alongside the files it writes a conversion manifest and a validation report.

- [Installation and authentication](install.md)
- [Command-line interface](cli.md) and [Python API](python-api.md)
- [Mapping specification](mapping-spec.md) and [warning codes](warnings.md)
- [The conversion manifest](manifest.md) and [validation](validation.md)
- [NWB extensions and ontology terms](extensions.md)
- [Supported modalities](modalities.md) and [troubleshooting](troubleshooting.md)
- Design: [architecture](design/architecture.md), [decisions](design/decisions.md), [raw-data conversion](design/phase4-raw-data.md), [ndx-brainstem extension (draft)](design/ndx-brainstem.md)
- [Reproducible example](https://github.com/brainstem-org/brainstem-nwb/blob/main/examples/synthetic-ephys/README.md)
