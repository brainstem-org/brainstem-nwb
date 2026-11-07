"""
Build synthetic BrainSTEM project exports (format 2.1) for tests and examples.

Records have every field the BrainSTEM data model has (as the server publishes it), filled with
the values Django's serializer writes for an empty field, then overridden by the arguments.
Keys are deterministic (uuid5 of the label and a name), links are sorted, datetimes use the
``...Z`` millisecond form and durations Django's ``duration_string`` form, as the server writes them.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from brainstem_nwb.store.inventory import get_inventory

NAMESPACE = uuid.UUID("6f1c6f0e-2b7f-4e0e-9a51-6d1a8f3b9c01")

# Fields the server leaves out of exports (format 2.1), and the only user fields it exports.
INTERNAL_FIELDS = ("permission_uids_at_deletion", "m2m_data_at_deletion", "wp_id")
EXPORTED_USER_FIELDS = ("first_name", "last_name")

# Empty values by the field kinds of the server's reference documents; other kinds are null.
_EMPTY = {"char": "", "text": "", "choice": "", "file": "", "string": "", "bool": False, "boolean": False,
          "list": []}
# Record types with a planning status; the server's default is "performed".
_PLANNABLE = ("stem.session", "stem.breeding", "modules.procedure", "modules.specimenprocedure")


class ExportBuilder:
    def __init__(self, *, exported_at: str = "2025-01-15T12:00:00.000000+00:00"):
        self.inventory = get_inventory()
        self.records: dict[str, list[dict[str, Any]]] = {label: [] for label in self.inventory.export_labels}
        self.exported_at = exported_at
        self.project_pk: str | None = None
        self.creator_pk: int | None = None
        self.restricted: dict[str, list[dict[str, str]]] = {}
        self.scope = "project"
        self.session_id: str | None = None

    # -- generic -------------------------------------------------------------------------

    def pk(self, label: str, key: str) -> str:
        return str(uuid.uuid5(NAMESPACE, f"{label}:{key}"))

    def add(self, label: str, key: str, **fields: Any) -> str:
        pk = self.pk(label, key)
        record_fields: dict[str, Any] = {}
        for name, spec in self.inventory.fields(label).items():
            if name in INTERNAL_FIELDS or (label == "users.user" and name not in EXPORTED_USER_FIELDS):
                continue
            if spec.get("kind") in ("m2m", "tags"):
                record_fields[name] = []
            elif spec.get("kind") == "fk" or spec.get("null"):
                record_fields[name] = None
            else:
                record_fields[name] = _EMPTY.get(spec.get("type"))
        if label in _PLANNABLE and "status" in record_fields:
            record_fields["status"] = "performed"
        if "created_at" in record_fields:
            record_fields["created_at"] = "2024-01-01T00:00:00Z"
            record_fields["updated_at"] = "2024-01-01T00:00:00Z"
        if "user" in record_fields:
            record_fields["user"] = self.creator()
        for name, value in fields.items():
            record_fields[name] = value
        for name, spec in self.inventory.fields(label).items():
            if spec.get("kind") in ("m2m", "tags") and isinstance(record_fields.get(name), list):
                record_fields[name] = sorted(record_fields[name], key=str)
        self.records.setdefault(label, []).append({"model": label, "pk": pk, "fields": record_fields})
        return pk

    def add_int(self, label: str, pk: int, **fields: Any) -> int:
        """A record with an integer key (users)."""
        self.records.setdefault(label, []).append({"model": label, "pk": pk, "fields": fields})
        return pk

    # -- helpers for common records --------------------------------------------------------

    def creator(self) -> int:
        """The user who created the synthetic records (exported as names only)."""
        if self.creator_pk is None:
            self.creator_pk = self.add_int("users.user", 7, first_name="Ada", last_name="Example")
        return self.creator_pk

    def user(self, pk: int, first_name: str, last_name: str) -> int:
        return self.add_int("users.user", pk, first_name=first_name, last_name=last_name)

    def project(self, name: str = "Synthetic project", **fields: Any) -> str:
        self.project_pk = self.add("stem.project", name, name=name, **fields)
        return self.project_pk

    def species(self, name: str = "Mus musculus", **fields: Any) -> str:
        defaults = {"popular_name": "Mouse", "rrid": "RRID:NCBITaxon_10090",
                    "external_identifiers": [{"source": "NCBI", "id": "10090",
                                              "url": "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=10090"}]}
        defaults.update(fields)
        return self.add("taxonomies.species", name, name=name, **defaults)

    def strain(self, name: str, species: str, **fields: Any) -> str:
        return self.add("taxonomies.strain", name, name=name, species=species, **fields)

    def subject(self, name: str, species: str, **fields: Any) -> str:
        fields.setdefault("projects", [self.project_pk])
        fields.setdefault("sex", "U")
        fields.setdefault("status", "active")
        return self.add("stem.subject", name, name=name, species=species, **fields)

    def session(self, name: str, **fields: Any) -> str:
        fields.setdefault("projects", [self.project_pk])
        fields.setdefault("session_type", "subject")
        return self.add("stem.session", name, name=name, **fields)

    def to_dict(self) -> dict[str, Any]:
        records = {label: sorted(items, key=lambda r: str(r["pk"])) for label, items in sorted(self.records.items())}
        counts = {label: len(items) for label, items in records.items()}
        project_ids = sorted(r["pk"] for r in records.get("stem.project", []))
        return {
            "export_info": {
                "format_version": "2.1",
                "exported_at": self.exported_at,
                "project_id": self.project_pk if self.scope == "project" else None,
                "project_ids": project_ids,
                "scope": self.scope,
                "session_id": self.session_id,
                "restricted": self.restricted,
                "lab_resources": "Behavioral assays, data storages, setups, equipment, licenses, protocols, "
                                 "inventories and consumable stocks are included when the exporting user can read "
                                 "them and the project's records reference them.",
                "record_count": sum(counts.values()),
                "counts": counts,
            },
            "records": records,
        }

    def write(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
