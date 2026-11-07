"""
The BrainSTEM data model as far as the exporter needs it: the fields of every exported record
type, which fields link to which record types, and the type vocabularies.

It is read from the BrainSTEM server at run time (``datamodel.py``); the export itself carries no
type information, and brainstem-nwb ships no copy of the data model.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from .datamodel import EXPORT_LABELS, DataModelDocuments, inventory_data, load_documents, server_base

# Fields left out of the manifest. ``user`` is the record's creator (a user id); the others are
# server bookkeeping.
DROPPED_FIELDS = frozenset({"user", "permission_uids_at_deletion", "m2m_data_at_deletion", "wp_id"})

@dataclass(frozen=True)
class Relation:
    target: str
    kind: Literal["fk", "m2m"]
    through: str | None = None


@dataclass(frozen=True)
class VocabularyEntry:
    code: str
    label: str
    group: str | None
    deprecated: bool


class Inventory:
    def __init__(self, data: dict[str, Any], source: DataModelDocuments | None = None):
        self.source = source
        self.data_model: str = data.get("data_model", "")
        self.export_format_version: str = data.get("export_format_version", "")
        self.server_commit: str | None = data.get("server_commit")
        self.sha256: str = data.get("sha256", "")
        self.license: dict[str, Any] | None = data.get("license")
        # Every record type the server describes; ``export_labels`` are the ones a project export holds.
        self.labels: dict[str, dict[str, dict[str, Any]]] = dict(data["labels"])
        self.export_labels: tuple[str, ...] = EXPORT_LABELS
        self.relations: dict[tuple[str, str], Relation] = {}
        for label, fields in self.labels.items():
            for name, spec in fields.items():
                if spec.get("kind") in ("fk", "m2m"):
                    self.relations[(label, name)] = Relation(
                        target=spec["target"], kind=spec["kind"], through=spec.get("through")
                    )
        self.vocabularies: dict[str, dict[str, VocabularyEntry]] = {
            family: {
                item["code"]: VocabularyEntry(
                    code=item["code"], label=item["label"], group=item.get("group"),
                    deprecated=bool(item.get("deprecated")),
                )
                for item in items
            }
            for family, items in data.get("vocabularies", {}).items()
        }

    def fields(self, label: str) -> dict[str, dict[str, Any]]:
        return self.labels.get(label, {})

    def relation(self, label: str, field: str) -> Relation | None:
        return self.relations.get((label, field))

    def type_label(self, family: str, code: str | None) -> str | None:
        if not code:
            return None
        entry = self.vocabularies.get(family, {}).get(code)
        return entry.label if entry else None

    def type_group(self, family: str, code: str | None) -> str | None:
        if not code:
            return None
        entry = self.vocabularies.get(family, {}).get(code)
        return entry.group if entry else None

    def known_type(self, family: str, code: str | None) -> bool:
        return bool(code) and code in self.vocabularies.get(family, {})


def get_inventory(server: str | None = None) -> Inventory:
    """The data model of ``server`` (default: ``BRAINSTEM_API_URL``, else www.brainstem.org), read once per run."""
    return _inventory(server_base(server))


@lru_cache(maxsize=8)
def _inventory(server: str) -> Inventory:
    documents = load_documents(server)
    return Inventory(inventory_data(documents.documents), source=documents)
