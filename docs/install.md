# Installation and authentication

## Install

```bash
pip install brainstem-nwb
```

- Requires Python 3.10 or newer.
- Installs pynwb 4.x, NWB Inspector, pydantic, click, and the BrainSTEM Python API tools.

For development:

```bash
git clone https://github.com/brainstem-org/brainstem-nwb
cd brainstem-nwb
pip install -e ".[dev,extensions]"
pytest
```

The NWB extensions (`--extension brainstem`) need the extensions extra: `pip install "brainstem-nwb[extensions]"`. See [extensions](extensions.md).

Raw-data conversion (planned, Phase 4) will need the NeuroConv extra: `pip install "brainstem-nwb[neuroconv]"`.

## Where the BrainSTEM records come from

`brainstem-nwb` reads a **BrainSTEM project export**: one JSON file with all of a project's records. You can provide it in either of two ways.

1. **Download it.** In BrainSTEM, open the project, choose *Download → JSON*, and pass the file with `--export-file`. Under *Contents* you can pick the whole project or one session. Large projects can be prepared in the background and emailed. This route needs no API token and works offline, and the export file makes the conversion reproducible.
2. **Fetch it.** Pass `--project PROJECT_UUID` for a project, or a single `--session SESSION_UUID` for one session. The exporter calls `BrainstemClient.export_project()` (or `export_session()`) from the API tools and keeps a copy of the export in `OUTPUT/source/`.

Both routes need **read access** to the project. (BrainSTEM servers with export format 2.0 required contributor access.)

Exports only include the lab resources you can read: setups, equipment, assays, protocols, licenses and stocks. Resources you cannot read appear by name only; they are named in the NWB text fields and listed in the manifest.

A **session export** holds one session and everything it touches: its subjects with their full procedure history, materials, logs, devices, and the session's projects. That is exactly what its NWB files need.

> **API tools version.** Fetching needs `brainstem_python_api_tools` 2.1.0 or later (`BrainstemClient.export_project` and `export_session`), which `pip install brainstem-nwb` installs.

## The BrainSTEM data model

brainstem-nwb does not ship a copy of the BrainSTEM data model (record types, fields, links, type vocabularies). It reads it from the server the export comes from: `<server>/reference/data/`, which BrainSTEM publishes for API clients. So:

- The first export needs network access to the server (www.brainstem.org, or `--url`). No token is needed for this.
- The documents are cached per server in `~/Library/Caches/brainstem-nwb` (macOS), `%LOCALAPPDATA%\brainstem-nwb\Cache` (Windows) or `~/.cache/brainstem-nwb` (Linux); `BRAINSTEM_NWB_CACHE` moves the cache. They are read again after an hour.
- When the server cannot be reached, the cached copy is used and the manifest warns `DATA_MODEL_CACHED`.
- On a machine without network access, run `brainstem-nwb data-model` once while online, or copy the four documents (`manifest.json`, `datamodel_graph.json`, `api_surface.json`, `schemas.json`) to a directory and set `BRAINSTEM_NWB_DATA_MODEL` to it.

The manifest's `data_model` records which model an export used (generation, export format, checksum). The data model and schemas are © BrainSTEM ([terms](https://www.brainstem.org/reference/license.md)).

## Authentication

Authentication comes from the [BrainSTEM API tools](https://github.com/brainstem-org/brainstem_python_api_tools). The first of these that is available is used:

1. `--token TOKEN`, or the `BRAINSTEM_API_TOKEN` environment variable (CLI). In Python, use `token=`.
2. The token cached by `brainstem login` in `~/.config/brainstem/token`.
3. On an interactive terminal, the browser login: a code is shown and the browser opens. Use `--headless` to print the URL instead of opening it.

In scripts, CI, or with `--no-device-flow`, the exporter never waits for a browser login. Without a token it stops with exit code 3.

Tokens are never written to the manifest, the reports or the logs.

## Connecting to another server

Use `--url https://staging.example.org/`, or `url=` in Python, to talk to a BrainSTEM server other than www.brainstem.org. The data model and schemas are then read from that server too.
