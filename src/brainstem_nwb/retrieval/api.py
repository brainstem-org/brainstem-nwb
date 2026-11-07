"""
Fetch a project export from BrainSTEM with ``brainstem_python_api_tools``.

Authentication is that of the API tools: an explicit token, or the token they cached at
``~/.config/brainstem/token`` after ``brainstem login``. The browser (device) login of the API
tools blocks until the user approves it, so it is only started when ``allow_device_flow`` is set
(the CLI does so on an interactive terminal); otherwise a missing token raises ``AuthRequired``.

Exporting needs read access to the project (export format 2.1; contributor access on servers
with format 2.0) and API tools 2.1.0 or later (``BrainstemClient.export_project`` and
``export_session``). Tokens are never logged or stored by this package.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..errors import AuthRequired, RetrievalError
from .loader import ProjectExport, SourceRef, load_export, with_source

DEFAULT_URL = "https://www.brainstem.org/"


def resolve_url(url: str | None) -> str:
    """The server to talk to: the explicit URL, else ``BRAINSTEM_API_URL`` (as the API tools read it), else
    www.brainstem.org. Used for the client and for the manifest's source host alike."""
    return url or os.environ.get("BRAINSTEM_API_URL") or DEFAULT_URL
SESSION_EXPORT_HINT = (
    "fetching a single session needs brainstem_python_api_tools with BrainstemClient.export_session "
    "(GET/POST /api/private/stem/session/{id}/export/). Until then, fetch the project with --project, or download "
    "the session export in the web interface (Project -> Download -> JSON, Contents: one session) and use "
    "--export-file."
)
API_TOOLS_HINT = (
    "fetching exports needs brainstem_python_api_tools with BrainstemClient.export_project (newer than 2.0.0): "
    "pip install -U brainstem_python_api_tools, or "
    "pip install git+https://github.com/brainstem-org/brainstem_python_api_tools. "
    "Alternatively download the project export (Project -> Download -> JSON) and use --export-file."
)


def _cached_token_exists() -> bool:
    try:
        from brainstem_api_tools import brainstem_api_client as client_module

        token_file = getattr(client_module, "_TOKEN_FILE", None)
        return token_file is not None and Path(token_file).exists()
    except Exception:
        return False


def make_client(*, token: str | None = None, url: str | None = None, allow_device_flow: bool = False,
                headless: bool = True) -> Any:
    try:
        from brainstem_api_tools import BrainstemClient
    except ImportError as exc:  # pragma: no cover - dependency of the package
        raise RetrievalError(f"brainstem_python_api_tools is not installed: {exc}") from exc
    if not hasattr(BrainstemClient, "export_project"):
        raise RetrievalError(API_TOOLS_HINT)
    if not token and not _cached_token_exists() and not allow_device_flow:
        raise AuthRequired(
            "no BrainSTEM token: pass --token (or set BRAINSTEM_API_TOKEN), run 'brainstem login' once to cache a "
            "token, or run interactively to log in with the browser"
        )
    try:
        return BrainstemClient(token=token, headless=headless, url=url)
    except Exception as exc:
        raise _translate(exc) from exc


def fetch_export(
    project_id: str | None = None,
    *,
    session_id: str | None = None,
    token: str | None = None,
    url: str | None = None,
    background: bool = True,
    allow_device_flow: bool = False,
    headless: bool = True,
    client: Any = None,
    save_to: Path | None = None,
) -> ProjectExport:
    """
    Fetch the export of ``project_id``, or with ``session_id`` the session export (format 2.1: the
    session and everything it touches, the content of its NWB files). ``background`` uses the
    server's export jobs, which are needed for large projects. With ``save_to``, the raw export is
    also written there (gzip when the name ends in .gz) so the conversion can be reproduced offline.
    """
    if not project_id and not session_id:
        raise RetrievalError("give a project id or a session id to fetch")
    url = resolve_url(url)
    if client is None:
        client = make_client(token=token, url=url, allow_device_flow=allow_device_flow, headless=headless)
    if session_id and not hasattr(client, "export_session"):
        raise RetrievalError(SESSION_EXPORT_HINT)
    try:
        if session_id:
            payload = client.export_session(session_id, background=background)
        else:
            payload = client.export_project(project_id, background=background)
    except Exception as exc:
        raise _translate(exc) from exc
    export = load_export(payload)
    host = urlparse(url).hostname
    export = with_source(export, SourceRef(kind="api", name=None, host=host))
    if save_to is not None:
        save_export(payload, save_to)
    return export


def save_export(payload: dict[str, Any], path: Path) -> Path:
    import gzip
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if path.suffix == ".gz":
        data = gzip.compress(data, mtime=0)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def _translate(exc: Exception) -> Exception:
    name = type(exc).__name__
    if name == "AuthenticationError":
        return AuthRequired(f"BrainSTEM rejected the token: {exc}")
    if name == "ExportError":
        return RetrievalError(f"BrainSTEM export failed: {exc}")
    if isinstance(exc, (AuthRequired, RetrievalError)):
        return exc
    return RetrievalError(f"could not fetch the export: {name}: {exc}")
