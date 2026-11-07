# Phase 4: raw-data conversion (design)

**Status:** designed; not implemented in 0.1.

This page is for contributors who will implement raw-data conversion. It describes how measured data will be added to the NWB files that the metadata export writes. The converter protocol, the converter registry, the data-path file model and the NeuroConv metadata hand-off already exist in `raw/` and are tested. No converter ships yet.

## Goals

- Raw files stay local: BrainSTEM records their names, and the files are read from the user's disk.
- NeuroConv and SpikeInterface do the format work. We do not reimplement readers.
- The metadata file is the starting point. Raw data adds `acquisition` objects and electrode rows to the `NWBFile` that the metadata export built, so the subject, devices and electrode groups are identical in both modes.
- Timing is never guessed.

## Components

| Piece | Module | Purpose |
|---|---|---|
| Converter protocol | `raw/base.py` | `RawDataConverter{name, acquisition_types, check(), add_to_nwbfile()}` |
| Registry | `raw/registry.py` | Built-in converters, plus the `brainstem_nwb.raw_converters` entry-point group for other packages |
| Data-path file | `raw/paths.py` | Maps DataAcquisitions to local files, either explicitly or by template |
| Metadata hand-off | `raw/metadata.py` | Builds NeuroConv-shaped metadata from the `NwbPlan`, reusing the planned names |

A converter is chosen by `DataAcquisition.type`, unless the data-path file names one explicitly with `converter`.

## Data-path file

```toml
[defaults]
root = "/data/lab"
template = "{root}/{subject_storage}/{session_storage}/{file_name}"

[dataacquisition."<uuid>"]
files = ["/data/lab/SM01/SM01_240401/SM01_240401.dat"]
converter = "flat-binary-ephys"
starting_time = 0.0
options = { xml_file_path = "/data/lab/SM01/SM01_240401/SM01_240401.xml" }
```

- **Template fields:**
  - `subject_storage` and `session_storage` come from BrainSTEM `name_used_in_storage`, falling back to the record names.
  - `file_name` comes from the acquisition details (`fileName`).
- **Paths in the manifest:** recorded relative to `root`, or redacted when outside it.
- **Missing files:** the acquisition stays metadata-only and gets the warning `RAW_DATA_NOT_FOUND`.

## Timing

DataAcquisitions have no times of their own. A recording's `starting_time`, in seconds from the session start, is taken from, in order:

1. the start of the epoch that links the acquisition (each acquisition is in at most one epoch);
2. an explicit `starting_time` in the data-path file.

If neither is available, the acquisition is not converted. This is an error that names the acquisition.

## First converter: flat binary extracellular ephys

BrainSTEM's `ExtracellularEphys` details already describe a flat binary (`.dat`) file completely:

| BrainSTEM detail | Used as |
|---|---|
| `fileName` | file to read |
| `type` | dtype (default `int16`) |
| `nChannels` | channel count |
| `nSamples` | used for the file-size check |
| `sr` | sampling rate, converted to Hz |
| `lsb` | gain, converted to µV per bit |
| `electrodeGroups[{label, channels}]` | channel groups |
| `channelTags` | boolean channel properties |

The converter will work as follows:

- Read the file with SpikeInterface `BinaryRecordingExtractor(file_paths, sampling_frequency, num_channels, dtype, gain_to_uV, offset_to_uV=0, time_axis=0)`.
- Check that the file size equals `nSamples × nChannels × itemsize`. A mismatch is an error. If `nSamples` is missing, derive it from the file size and note it.
- Set the `group_name` channel property from `electrodeGroups`, so channels attach to the ElectrodeGroups the metadata export already created (`<interface>_<label>`).
- Write with `neuroconv.tools.spikeinterface.add_recording_to_nwbfile(recording, nwbfile, metadata=neuroconv_metadata(plan))`. This adds the electrodes table rows and one `ElectricalSeries` per acquisition.
- If a NeuroScope `.xml` sits next to the `.dat` (or is given in `options`), use NeuroConv's `NeuroScopeRecordingInterface` instead and cross-check its channel count and sampling rate against BrainSTEM.

Install with the extra: `pip install "brainstem-nwb[neuroconv]"`.

## Effect on the manifest and file

- `export_mode` becomes `with-raw-data` when every acquisition was converted, and `partial-raw-data` otherwise.
- The metadata-only banner and keyword are removed only when every acquisition was converted.
- Each data source records `raw_conversion.status`, the converter used, the input files, their sizes and optionally their sha256.

## Next converters

1. Video and behavioral tracking, via NeuroConv's external video interface.
2. Fiber photometry and two-photon imaging (with `ndx-fiber-photometry`, `ndx-ophys-devices`).
3. SpikeGLX, Open Ephys and Intan, through their NeuroConv interfaces.
