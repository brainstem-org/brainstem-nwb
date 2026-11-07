"""
Index the records of a project export and resolve the links between them.

Foreign keys in the export are bare primary keys and many-to-many fields are sorted key lists;
which record type a field points to comes from the inventory. A link can point outside the file
(users, brain regions, publications, records of other projects), which ``Ref.reason`` reports
as ``not_in_export`` instead of failing.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..retrieval.loader import ProjectExport
from .inventory import DROPPED_FIELDS, Inventory, get_inventory

LOG_ENTRY_LABELS = ("modules.moduleslogentry", "modules.startendmoduleslogentry")
# Link targets that are not records: a log entry's content_type is exported as a model label.
NOT_RECORDS = frozenset({"contenttypes.contenttype"})


@dataclass(frozen=True)
class Record:
    label: str
    pk: str
    fields: Mapping[str, Any]

    def get(self, name: str, default: Any = None) -> Any:
        return self.fields.get(name, default)

    @property
    def key(self) -> tuple[str, str]:
        return (self.label, self.pk)


@dataclass(frozen=True)
class Ref:
    label: str
    pk: str
    record: Record | None
    reason: Literal["ok", "restricted", "not_in_export"]
    name: str | None = None  # for restricted lab resources: the name the export gives

    @property
    def ok(self) -> bool:
        return self.record is not None


class RecordStore:
    def __init__(self, export: ProjectExport, inventory: Inventory | None = None):
        self.export = export
        self.inventory = inventory or get_inventory()
        self._by_key: dict[tuple[str, str], Record] = {}
        self._by_label: dict[str, list[Record]] = {}
        for label, items in export.records.items():
            records = [Record(label=label, pk=str(item["pk"]), fields=item["fields"]) for item in items]
            records.sort(key=lambda record: record.pk)
            self._by_label[label] = records
            for record in records:
                self._by_key[record.key] = record
        # Lab resources the exporting user cannot read (format 2.1): their name only
        self._restricted: dict[tuple[str, str], str] = {}
        for label, items in export.restricted.items():
            for item in items or []:
                if isinstance(item, dict) and item.get("pk") is not None:
                    self._restricted[(str(label), str(item["pk"]))] = str(item.get("name") or "")
        # Log entries name their log by content type (a model label) and object id
        self._log_entries: dict[tuple[str, str], list[Record]] = defaultdict(list)
        for label in LOG_ENTRY_LABELS:
            for record in self._by_label.get(label, []):
                content_type, object_id = record.get("content_type"), record.get("object_id")
                if content_type and object_id is not None:
                    self._log_entries[(str(content_type).lower(), str(object_id))].append(record)
        # (target label, target pk) -> [(source label, field, source record)]
        self._reverse: dict[tuple[str, str], list[tuple[str, str, Record]]] = defaultdict(list)
        relations_by_label = defaultdict(list)
        for (rel_label, field_name), relation in self.inventory.relations.items():
            relations_by_label[rel_label].append((field_name, relation))
        for label, records in self._by_label.items():
            for field_name, relation in relations_by_label.get(label, []):
                for record in records:
                    for target_pk in _keys(record.get(field_name)):
                        self._reverse[(relation.target, target_pk)].append((label, field_name, record))

    # -- lookup ----------------------------------------------------------------------------

    def labels(self) -> list[str]:
        return sorted(self._by_label)

    def all(self, label: str) -> list[Record]:
        return list(self._by_label.get(label, []))

    def get(self, label: str, pk: Any) -> Record | None:
        if pk is None:
            return None
        return self._by_key.get((label, str(pk)))

    def __len__(self) -> int:
        return len(self._by_key)

    # -- links -----------------------------------------------------------------------------

    def fk(self, record: Record, field_name: str) -> Ref | None:
        """Follow a foreign key; None when the field is null."""
        relation = self.inventory.relation(record.label, field_name)
        if relation is None or relation.kind != "fk":
            raise KeyError(f"{record.label}.{field_name} is not a foreign key")
        value = record.get(field_name)
        if value is None or value == "":
            return None
        return self._ref(relation.target, str(value))

    def m2m(self, record: Record, field_name: str) -> list[Ref]:
        relation = self.inventory.relation(record.label, field_name)
        if relation is None or relation.kind != "m2m":
            raise KeyError(f"{record.label}.{field_name} is not a many-to-many field")
        return [self._ref(relation.target, pk) for pk in _keys(record.get(field_name))]

    def fk_record(self, record: Record, field_name: str) -> Record | None:
        ref = self.fk(record, field_name)
        return ref.record if ref else None

    def m2m_records(self, record: Record, field_name: str) -> list[Record]:
        return [ref.record for ref in self.m2m(record, field_name) if ref.record is not None]

    def referrers(self, target: Record, source_label: str, field_name: str) -> list[Record]:
        """Records of ``source_label`` whose ``field_name`` points at ``target``, sorted by pk."""
        found = {
            record.pk: record
            for label, name, record in self._reverse.get(target.key, [])
            if label == source_label and name == field_name
        }
        return [found[pk] for pk in sorted(found)]

    def log_entries(self, log: Record) -> list[Record]:
        """Entries of a subject, procedure or specimen log, by date then pk."""
        entries = self._log_entries.get((log.label, log.pk), [])
        return sorted(entries, key=lambda e: (str(e.get("date_time") or e.get("start_date_time") or ""), e.pk))

    def restricted_name(self, label: str, pk: str) -> str | None:
        return self._restricted.get((label, str(pk)))

    def external_refs(self) -> dict[str, tuple[int, int]]:
        """
        Per target label: (records linked, linked records in the export). Links the exporter does not
        use (a record's creator) are not counted.
        """
        totals: dict[str, set[str]] = defaultdict(set)
        resolved: dict[str, set[str]] = defaultdict(set)
        for (target, pk), sources in self._reverse.items():
            if target in NOT_RECORDS or all(field in DROPPED_FIELDS for _label, field, _record in sources):
                continue
            totals[target].add(pk)
            if (target, pk) in self._by_key:
                resolved[target].add(pk)
        return {
            label: (len(totals[label]), len(resolved[label]))
            for label in sorted(totals)
            if len(totals[label]) != len(resolved[label])
        }

    def _ref(self, label: str, pk: str) -> Ref:
        record = self._by_key.get((label, pk))
        if record is not None:
            return Ref(label=label, pk=pk, record=record, reason="ok")
        name = self._restricted.get((label, pk))
        if name is not None:
            return Ref(label=label, pk=pk, record=None, reason="restricted", name=name)
        return Ref(label=label, pk=pk, record=None, reason="not_in_export")


def _keys(value: Any) -> Iterable[str]:
    if value is None or value == "":
        return ()
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return (str(value),)
