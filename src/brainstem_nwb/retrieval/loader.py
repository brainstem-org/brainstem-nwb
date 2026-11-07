"""
Read a BrainSTEM project export (format 2.x) from a file, a stream or an already-parsed dict.

The export is the only source of BrainSTEM records. It is produced by the web download
(Project -> Download -> JSON), by ``GET/POST /api/private/stem/project/{id}/export/``, or by
``BrainstemClient.export_project()``; see ``fetch_export`` for the API route.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Literal

from .._version import KNOWN_EXPORT_MINOR, SUPPORTED_EXPORT_MAJOR
from ..errors import ExportFormatError

_GZIP_MAGIC = b"\x1f\x8b"


@dataclass(frozen=True)
class SourceRef:
    kind: Literal["file", "api", "dict"]
    name: str | None = None  # file base name only; never an absolute path
    host: str | None = None


@dataclass(frozen=True)
class ProjectExport:
    """A parsed project export: ``info`` is ``export_info``; ``records`` maps model labels to records."""

    info: dict[str, Any]
    records: dict[str, list[dict[str, Any]]]
    sha256: str
    source: SourceRef
    format_major: int
    format_minor: int
    raw_bytes: bytes | None = field(default=None, repr=False, compare=False)
    # Top-level keys other than export_info and records (e.g. 'schemas'), kept as given
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def format_version(self) -> str:
        return str(self.info.get("format_version"))

    @property
    def project_id(self) -> str | None:
        value = self.info.get("project_id")
        return str(value) if value is not None else None

    @property
    def exported_at(self) -> str | None:
        value = self.info.get("exported_at")
        return str(value) if value is not None else None

    @property
    def scope(self) -> str:
        """``"project"`` or ``"session"`` (format 2.1); 2.0 exports are always project exports."""
        return str(self.info.get("scope") or "project")

    @property
    def session_id(self) -> str | None:
        value = self.info.get("session_id")
        return str(value) if value else None

    @property
    def project_ids(self) -> list[str]:
        """The exported projects: ``project_ids`` (2.1), else ``project_id``."""
        ids = self.info.get("project_ids")
        if isinstance(ids, list) and ids:
            return sorted(str(pk) for pk in ids)
        return [self.project_id] if self.project_id else []

    @property
    def schemas(self) -> dict[str, Any]:
        """BrainSTEM JSON schemas the records use, by '<Family>/<Type>@<version>' (top-level 'schemas')."""
        value = self.extra.get("schemas")
        return value if isinstance(value, dict) else {}

    @property
    def restricted(self) -> dict[str, list[dict[str, Any]]]:
        """Lab resources the records reference that the exporting user cannot read: label -> [{pk, name}]."""
        value = self.info.get("restricted")
        return value if isinstance(value, dict) else {}


def load_export(source: str | Path | IO[bytes] | dict[str, Any] | bytes) -> ProjectExport:
    """
    Load a project export from a ``.json`` or ``.json.gz`` path, a binary stream, bytes, or a dict.

    Gzip is detected from the content, not the file name. Raises ``ExportFormatError`` for
    unreadable content or a format major version other than the supported one.
    """
    if isinstance(source, dict):
        payload = source
        text = json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return _build(payload, hashlib.sha256(text).hexdigest(), SourceRef(kind="dict"), None)

    if isinstance(source, (str, Path)):
        path = Path(source)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ExportFormatError(f"cannot read export file {path.name}: {exc.strerror or exc}") from exc
        ref = SourceRef(kind="file", name=path.name)
    elif isinstance(source, bytes):
        data, ref = source, SourceRef(kind="dict")
    else:
        data = source.read()
        ref = SourceRef(kind="file", name=Path(getattr(source, "name", "")).name or None)

    if data[:2] == _GZIP_MAGIC:
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise ExportFormatError(f"corrupt gzip export: {exc}") from exc
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportFormatError(f"the export is not valid JSON: {exc}") from exc
    return _build(payload, hashlib.sha256(data).hexdigest(), ref, data)


def with_source(export: ProjectExport, source: SourceRef) -> ProjectExport:
    return ProjectExport(
        info=export.info,
        records=export.records,
        sha256=export.sha256,
        source=source,
        format_major=export.format_major,
        format_minor=export.format_minor,
        raw_bytes=export.raw_bytes,
        extra=export.extra,
    )


def _build(payload: Any, sha256: str, ref: SourceRef, raw: bytes | None) -> ProjectExport:
    if not isinstance(payload, dict) or "export_info" not in payload or "records" not in payload:
        raise ExportFormatError(
            "not a BrainSTEM project export: expected top-level 'export_info' and 'records' "
            "(format 2.x; older 1.x downloads are not supported)"
        )
    info = payload["export_info"]
    records = payload["records"]
    if not isinstance(info, dict) or not isinstance(records, dict):
        raise ExportFormatError("malformed export: 'export_info' and 'records' must be objects")
    version = str(info.get("format_version", ""))
    try:
        major_text, _, minor_text = version.partition(".")
        major, minor = int(major_text), int(minor_text or 0)
    except ValueError as exc:
        raise ExportFormatError(f"export has no valid format_version (got {version!r})") from exc
    if major != SUPPORTED_EXPORT_MAJOR:
        raise ExportFormatError(
            f"export format {version} is not supported; this release reads format "
            f"{SUPPORTED_EXPORT_MAJOR}.x"
        )
    cleaned: dict[str, list[dict[str, Any]]] = {}
    for label, items in records.items():
        if not isinstance(items, list):
            raise ExportFormatError(f"malformed export: records[{label!r}] is not a list")
        for item in items:
            if not isinstance(item, dict) or "pk" not in item or not isinstance(item.get("fields"), dict):
                raise ExportFormatError(f"malformed record in {label!r}: expected {{model, pk, fields}}")
        cleaned[str(label)] = items
    return ProjectExport(
        info=info,
        records=cleaned,
        sha256=sha256,
        source=ref,
        format_major=major,
        format_minor=minor,
        raw_bytes=raw,
        extra={k: v for k, v in payload.items() if k not in ("export_info", "records")},
    )


def is_newer_minor(export: ProjectExport) -> bool:
    return export.format_minor > KNOWN_EXPORT_MINOR
