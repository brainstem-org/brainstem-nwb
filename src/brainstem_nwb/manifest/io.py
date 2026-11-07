"""Canonical reading and writing of manifests: the same manifest always gives the same bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import Manifest

MANIFEST_FILENAME = "brainstem-nwb-manifest.json"


def canonical_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def manifest_to_json(manifest: Manifest) -> str:
    return canonical_json(manifest.model_dump(mode="json"))


def write_manifest(manifest: Manifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(manifest_to_json(manifest), encoding="utf-8")
    tmp.replace(path)
    return path


def read_manifest(path: Path) -> Manifest:
    return Manifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def digest(data: Any) -> str:
    """sha256 of the canonical, compact JSON form of ``data``."""
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
