# Example: synthetic electrophysiology session

This example is a fully reproducible export from a synthetic BrainSTEM project. All names and values are invented. It contains:
- one mouse;
- a virus injection, a silicon-probe implant and anesthesia;
- one session with an extracellular recording and video tracking;
- an open-field behavior and two epochs;
- a procedure after the session, which is left out of the file.

The example needs no BrainSTEM account and no network access.

| File | Contents |
|---|---|
| `brainstem-export.json` | The project export, in the format BrainSTEM's *Download → JSON* produces |
| `brainstem-nwb.toml` | Experimenter, lab and institution, which are not in BrainSTEM exports |

## Run it

```bash
pip install brainstem-nwb
brainstem-nwb export \
    --export-file examples/synthetic-ephys/brainstem-export.json \
    --config examples/synthetic-ephys/brainstem-nwb.toml \
    --output out/ --reproducible
```

The output is:

```
out/
  sub-SynthMouse01/sub-SynthMouse01_ses-SM01-2024-04-01.nwb
  brainstem-nwb-manifest.json
  validation-report.json
  validation-report.txt        0 error(s), 0 warning(s)
```

With `--reproducible`, running the command again gives the same manifest and the same NWB identifier. Only the HDF5 file checksums differ, because HDF5 object ids are random.

## Look at the result

```python
from pynwb import NWBHDF5IO

with NWBHDF5IO("out/sub-SynthMouse01/sub-SynthMouse01_ses-SM01-2024-04-01.nwb") as io:
    nwbfile = io.read()
    print(nwbfile.subject)                 # SynthMouse01, Mus musculus, C57BL/6J, M, P90D
    print(nwbfile.virus)                   # the AAV injection, with construct, titer and coordinates
    print(nwbfile.electrode_groups)        # Probe A_shank1, Probe A_shank2
    print(nwbfile.epochs.to_dataframe())   # exploration and sleep
```

The manifest shows:
- which BrainSTEM records were used;
- which fields have no NWB destination;
- warnings, such as `REGION_NOT_RESOLVED`: a probe or implant without a recorded target region gets the electrode group location `unknown`.

The export is generated from `tests/fixtures/scenarios.py` (`python tests/fixtures/regen.py`).
