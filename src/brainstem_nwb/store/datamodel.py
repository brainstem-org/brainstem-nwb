"""
The BrainSTEM data model, read from the BrainSTEM server at run time.

brainstem-nwb does not ship a copy of the data model. BrainSTEM publishes it for API clients under
``<server>/reference/data/`` (terms: ``<server>/reference/license.md``), and the exporter reads it from
the server the export comes from:

- ``datamodel_graph.json``: every record type with its fields and links;
- ``api_surface.json``: the REST resources, which also describe the link tables of ordered links;
- ``schemas.json``: the type vocabularies (procedure types and their groups, acquisition types, ...);
- ``manifest.json``: the data model generation and the export format the server writes.

The documents are cached per server in the user's cache directory (``BRAINSTEM_NWB_CACHE`` moves it)
and fetched again when they are older than an hour, the server's ``max-age``. When the server cannot
be reached, the cached copy is used and the manifest says so. ``BRAINSTEM_NWB_DATA_MODEL`` names a
directory holding the four documents, for machines without network access.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from ..errors import BrainstemNwbError

DOCUMENTS = ("manifest.json", "datamodel_graph.json", "api_surface.json", "schemas.json")
MAX_AGE = 3600  # seconds; the server sends Cache-Control: max-age=3600
TIMEOUT = 30
DEFAULT_SERVER = "https://www.brainstem.org/"
CACHE_ENV = "BRAINSTEM_NWB_CACHE"
DIRECTORY_ENV = "BRAINSTEM_NWB_DATA_MODEL"

# The record types a format 2.1 export holds. Records of other types are reported as UNKNOWN_LABEL.
EXPORT_LABELS = (
    "dissemination.journal", "dissemination.publication",
    "modules.behavior", "modules.consumablestock", "modules.dataacquisition", "modules.dataacquisitioninterface",
    "modules.episodepersonnel", "modules.equipment", "modules.experimentalinterface", "modules.manipulation",
    "modules.manipulationinterface", "modules.materialusage", "modules.materialusagetarget",
    "modules.moduleslogentry", "modules.procedure", "modules.procedureepisode", "modules.procedureinterface",
    "modules.procedurelog", "modules.procedurestage", "modules.procedurestagetarget", "modules.specimenlog",
    "modules.specimenprocedure", "modules.specimenproceduretarget", "modules.startendmoduleslogentry",
    "modules.subjectlog",
    "personal_attributes.behavioralassay", "personal_attributes.datastorage", "personal_attributes.inventory",
    "personal_attributes.license", "personal_attributes.protocol", "personal_attributes.protocolallowedsubtype",
    "personal_attributes.setup",
    "resources.consumable", "resources.hardwaredevice", "resources.supplier",
    "stem.breeding", "stem.cohort", "stem.cohortsubject", "stem.collection", "stem.collectionsession",
    "stem.epoch", "stem.project", "stem.session", "stem.sessiondatastorage", "stem.specimen", "stem.specimenset",
    "stem.subject",
    "taxonomies.anatomicalreference", "taxonomies.anatomicalregion", "taxonomies.behavioralcategory",
    "taxonomies.behavioralparadigm", "taxonomies.coordinatetransform", "taxonomies.regulatoryauthority",
    "taxonomies.setuptype", "taxonomies.species", "taxonomies.strain",
    "users.user",
)

# Link tables the export holds but the server's reference documents do not describe yet: the links
# brainstem-nwb follows in them. Used only for record types the documents leave out.
LINK_TABLES: dict[str, dict[str, str | None]] = {
    "modules.procedureinterface": {"procedure": "modules.procedure", "interface": "modules.experimentalinterface",
                                   "relationship": None, "notes": None},
    "modules.materialusagetarget": {"material_usage": "modules.materialusage", "specimen": "stem.specimen",
                                    "order": None},
    "modules.procedurestagetarget": {"stage": "modules.procedurestage", "specimen": "stem.specimen", "order": None},
    "modules.specimenproceduretarget": {"specimen_procedure": "modules.specimenprocedure",
                                        "specimen": "stem.specimen", "order": None},
    "personal_attributes.protocolallowedsubtype": {"protocol": "personal_attributes.protocol", "subtype": None},
}


class DataModelUnavailable(BrainstemNwbError):
    """The BrainSTEM data model could not be read from the server, and no cached copy exists."""

    exit_code = 3


@dataclass(frozen=True)
class DataModelDocuments:
    server: str
    documents: dict[str, Any]
    origin: Literal["fetched", "cache", "stale_cache", "directory"]
    fetched_at: str | None = None
    error: str | None = None  # why a stale cached copy was used


def server_base(server: str | None) -> str:
    """The server's base URL: the explicit one, else ``BRAINSTEM_API_URL``, else www.brainstem.org."""
    base = server or os.environ.get("BRAINSTEM_API_URL") or DEFAULT_SERVER
    return base if base.endswith("/") else base + "/"


def documents_url(server: str | None) -> str:
    return server_base(server) + "reference/data/"


def cache_root() -> Path:
    if os.environ.get(CACHE_ENV):
        return Path(os.environ[CACHE_ENV])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "brainstem-nwb"
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "brainstem-nwb" / "Cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "brainstem-nwb"


def cache_dir(server: str | None) -> Path:
    parts = urlsplit(server_base(server))
    name = (parts.netloc or "server") + parts.path.rstrip("/").replace("/", "_")
    return cache_root() / "datamodel" / "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)


def load_documents(server: str | None = None, *, refresh: bool = False, session: Any = None) -> DataModelDocuments:
    """The reference documents of ``server``, from the cache when it is fresh, else from the server."""
    base = server_base(server)
    directory = os.environ.get(DIRECTORY_ENV)
    if directory:
        return DataModelDocuments(server=base, documents=_read_directory(Path(directory)), origin="directory")
    folder = cache_dir(base)
    meta = _read_meta(folder) or {}
    cached = _read_cached(folder) if meta else None
    if cached is not None and not refresh and time.time() - float(meta.get("fetched", 0)) < MAX_AGE:
        return DataModelDocuments(server=base, documents=cached, origin="cache", fetched_at=meta.get("fetched_at"))
    try:
        documents, etags = _fetch(base, cached, meta.get("etags", {}), session)
    except (OSError, ValueError) as exc:
        if cached is None:
            raise DataModelUnavailable(
                f"cannot read the BrainSTEM data model from {documents_url(base)}: {exc}. brainstem-nwb reads it from "
                f"the server at run time and caches it in {folder}; connect once, or set {DIRECTORY_ENV} to a "
                "directory with the documents") from exc
        return DataModelDocuments(server=base, documents=cached, origin="stale_cache",
                                  fetched_at=meta.get("fetched_at"), error=str(exc))
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _write_cache(folder, documents, {"server": base, "fetched": time.time(), "fetched_at": fetched_at,
                                     "etags": etags})
    return DataModelDocuments(server=base, documents=documents, origin="fetched", fetched_at=fetched_at)


def _fetch(base: str, cached: dict[str, Any] | None, etags: dict[str, str],
           session: Any) -> tuple[dict[str, Any], dict[str, str]]:
    import requests

    http = session or requests.Session()
    documents: dict[str, Any] = {}
    new_etags: dict[str, str] = {}
    for name in DOCUMENTS:
        headers = {"Accept": "application/json"}
        if cached is not None and etags.get(name):
            headers["If-None-Match"] = etags[name]
        try:
            response = http.get(documents_url(base) + name, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise OSError(str(exc)) from exc
        if response.status_code == 304 and cached is not None:
            documents[name] = cached[name]
            new_etags[name] = etags[name]
            continue
        if response.status_code != 200:
            raise OSError(f"{name}: HTTP {response.status_code}")
        documents[name] = response.json()
        if response.headers.get("ETag"):
            new_etags[name] = response.headers["ETag"]
    return documents, new_etags


def _read_directory(directory: Path) -> dict[str, Any]:
    missing = [name for name in DOCUMENTS if not (directory / name).is_file()]
    if missing:
        raise DataModelUnavailable(f"{DIRECTORY_ENV}={directory} lacks {', '.join(missing)}")
    return {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in DOCUMENTS}


def _read_meta(folder: Path) -> dict[str, Any] | None:
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def _read_cached(folder: Path) -> dict[str, Any] | None:
    try:
        return {name: json.loads((folder / name).read_text(encoding="utf-8")) for name in DOCUMENTS}
    except (OSError, ValueError):
        return None


def _write_cache(folder: Path, documents: dict[str, Any], meta: dict[str, Any]) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name, document in documents.items():
            _write_atomic(folder / name, json.dumps(document, ensure_ascii=False))
        _write_atomic(folder / "meta.json", json.dumps(meta, indent=1))
    except OSError:  # a read-only cache only costs a fetch next time
        pass


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# -- converting the documents to the exporter's inventory ----------------------------------------


def inventory_data(documents: dict[str, Any]) -> dict[str, Any]:
    """The record types, fields, links and vocabularies the exporter uses, from the reference documents."""
    manifest = documents["manifest.json"]
    labels = _labels(documents["datamodel_graph.json"], documents["api_surface.json"])
    vocabularies = _vocabularies(documents["schemas.json"])
    digest = hashlib.sha256(json.dumps(
        {"labels": {label: labels[label] for label in EXPORT_LABELS if label in labels},
         "vocabularies": vocabularies}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "data_model": str(manifest.get("data_model") or ""),
        "export_format_version": str(manifest.get("export_format_version") or ""),
        "server_commit": str(manifest.get("server_commit") or "") or None,
        "license": manifest.get("license") if isinstance(manifest.get("license"), dict) else None,
        "sha256": digest,
        "labels": labels,
        "vocabularies": vocabularies,
    }


def _labels(graph: dict[str, Any], api: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    nullable = {(resource["model"], f["name"]): bool(f.get("nullable"))
                for resource in api.get("resources", []) for f in resource.get("fields", [])}
    through = {(edge["source"], edge["source_field"]): edge.get("through")
               for edge in graph.get("edges", []) if edge.get("kind") == "m2m"}
    labels: dict[str, dict[str, dict[str, Any]]] = {}
    for node in graph.get("nodes", []):
        label = node["id"]
        app = label.partition(".")[0]
        fields: dict[str, dict[str, Any]] = {}
        for field in node.get("fields", []):
            name, kind = field["name"], field.get("kind")
            if name == "id":
                continue
            if kind == "generic":  # a generic link is exported as its two columns
                fields["content_type"] = {"type": "fk", "kind": "fk", "target": "contenttypes.contenttype"}
                fields["object_id"] = {"type": "char"}
                continue
            entry: dict[str, Any] = {"type": kind}
            if kind in ("fk", "o2o", "self"):
                entry.update(kind="fk", target=field.get("target") or label)
            elif kind == "m2m":
                table = through.get((label, name))
                entry.update(kind="m2m", target=field.get("target"),
                             through=f"{app}.{table.lower()}" if table else None)
            elif kind == "tags":
                entry["kind"] = "tags"
            if (label, name) in nullable:
                entry["null"] = nullable[(label, name)]
            fields[name] = entry
        labels[label] = dict(sorted(fields.items()))
    for resource in api.get("resources", []):
        label = resource.get("model")
        if not label or label in labels:
            continue
        fields = {}
        for field in resource.get("fields", []):
            name, kind = field["name"], field.get("kind")
            if name == "id" or kind == "computed":
                continue
            entry = {"type": kind, "null": bool(field.get("nullable"))}
            if kind == "relation":
                entry.update(kind="fk", target=field.get("target"))
            elif kind == "relation_many":
                entry.update(kind="m2m", target=field.get("target"), through=None)
            fields[name] = entry
        labels[label] = dict(sorted(fields.items()))
    for label, links in LINK_TABLES.items():
        if label in labels:
            continue
        fields = {name: ({"type": "fk", "kind": "fk", "target": target} if target else {"type": "char"})
                  for name, target in links.items()}
        labels[label] = dict(sorted(fields.items()))
    return labels


def _vocabularies(schemas: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for family in schemas.get("families", []):
        items = [{"code": t["type"], "label": t.get("label") or t.get("title") or t["type"], "group": t.get("group")}
                 for t in family.get("types", []) if t.get("type")]
        for code in family.get("types_without_schema") or []:
            code = code.get("type") if isinstance(code, dict) else code
            if code and all(item["code"] != code for item in items):
                items.append({"code": str(code), "label": str(code), "group": None})
        out[str(family["family"])] = sorted(items, key=lambda item: item["code"])
    return out
