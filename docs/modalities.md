# Supported experimental modalities

This page lists, for each kind of BrainSTEM record, what a metadata-only NWB file contains in this release (0.1). Field-level detail is in the [mapping specification](mapping-spec.md), and warning codes are explained in [warnings.md](warnings.md).

None of these files contain measured data. Converting raw data with NeuroConv is planned; see [phase 4](design/phase4-raw-data.md).

## Recordings and experiments

| BrainSTEM data | In the NWB file | Not yet |
|---|---|---|
| **Extracellular electrophysiology** (silicon probes, tetrodes, wires, arrays, ECoG, EEG) | Probe and amplifier `Device`s; one `ElectrodeGroup` per probe, or one per electrode group defined on the acquisition; file details in `data_collection` | Electrode rows, `ElectricalSeries` (Phase 4, flat binary first); electrode positions |
| **Intracellular / patch clamp** | Pipette `Device`, details in `data_collection`, slices in `slices` | Intracellular electrodes and recordings (`ICEPHYS_NOT_MAPPED`) |
| **Optogenetics** | Fiber `Device`; `OptogeneticStimulusSite` when exactly one wavelength is recorded; protocols in `stimulus_notes`; viruses in `virus` | `OptogeneticSeries` (no stimulus times in BrainSTEM) |
| **Imaging** (two-photon, miniscope, fiber photometry, …) | Devices, details in `data_collection`, viruses and implants in `virus` and `surgery` | `ImagingPlane` (indicator and rate not recorded; `IMAGING_PLANE_NOT_CREATED`) |
| **Behavior and tracking** | Assays and setups in `notes`; epochs linking behaviors in the epochs table; camera `Device`s | Position or video data (Phase 4) |
| **Pharmacology** | Anesthesia, drug and fluid procedures, and pharmacological manipulations, in `pharmacology` | — |
| **Electrical and sensory stimulation** | `stimulus_notes`, stimulator `Device`s | Stimulus series |
| **Ex vivo** (specimen sessions: slices, sections, cultures) | Subject through the specimen set; specimen sets, specimens and specimen procedures in `slices` | — |

## Other records

| BrainSTEM data | In the NWB file | Not yet |
|---|---|---|
| **Surgeries and implants** | One line per procedure in `surgery`, with target regions (acronym, name, atlas), coordinates as stored, materials with supplier and RRID, who performed it and the episode personnel | Atlas-space coordinates (structured: planned with `ndx-anatomical-localization`) |
| **Subjects** | `Subject`: id, species, strain, sex, date of birth, age, genotype, weight (latest weighing before the session), description | — |
| **Devices** | `Device`s with `DeviceModel` (manufacturer from the supplier, model number from the product id) for hardware devices and probe designs | — |
| **Epochs** | Epochs table, times relative to the session start, with BrainSTEM ids and linked records | Trials (BrainSTEM has no trial records) |

## Older exports (format 2.0)

Export formats 2.1 and later include the catalog records the files need. Exports in format 2.0 reference them by id only, so the files written from them lack the following. Each gap is listed in the manifest as `not_exported`.

| Not in a 2.0 export | What is missing in the NWB file |
|---|---|
| Brain regions, atlases | `ElectrodeGroup` and stimulus-site `location`, which are `unknown` |
| Publications | `related_publications` |
| Suppliers | Device manufacturer (no `DeviceModel`) |
| User names | People in the procedure text; `experimenter` from the session creator |
| Subject and procedure log entries | Weight |

The experimenter is never inferred. Set it in the configuration, or opt in to the session creator with `experimenter_source = "session_creator"`.
