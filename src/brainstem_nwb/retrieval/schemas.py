"""
Fetch BrainSTEM JSON schemas from the public schema service (``--embed-schemas``).

Published versions are served at ``<server>/schemas/<Family>/<Type>/<version>.json`` and never change,
so fetching them again gives the same files. The service is public: no token is sent. A schema the
server does not have is reported as missing and never replaced by another version; ids without a
version are not fetched, because the version the record followed is unknown.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from ..normalize.schemas import SchemaRef

DEFAULT_SERVER = "https://www.brainstem.org/"
TIMEOUT = 30


def schemas_base(server: str | None) -> str:
    """``<server>/schemas/``; the server is the explicit one, else ``BRAINSTEM_API_URL``, else www.brainstem.org."""
    server = server or os.environ.get("BRAINSTEM_API_URL") or DEFAULT_SERVER
    return (server if server.endswith("/") else server + "/") + "schemas/"


def fetch_schemas(refs: list[SchemaRef], server: str | None = None,
                  session: Any = None) -> tuple[dict[str, Any], list[str]]:
    """Fetch the versioned schemas among ``refs``. Returns ({id: schema}, [ids not available])."""
    http = session or requests.Session()
    base = schemas_base(server)
    found: dict[str, Any] = {}
    missing: list[str] = []
    for ref in refs:
        if not ref.version:
            continue
        try:
            response = http.get(ref.url(base), timeout=TIMEOUT, headers={"Accept": "application/schema+json"})
            if response.status_code != 200:
                missing.append(ref.id)
                continue
            schema = response.json()
        except (requests.RequestException, ValueError):
            missing.append(ref.id)
            continue
        if str(schema.get("schemaVersion", ref.version)) != ref.version:  # never substitute another version
            missing.append(ref.id)
            continue
        found[ref.id] = schema
    return found, sorted(missing)
