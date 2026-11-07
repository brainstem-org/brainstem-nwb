"""
Deterministic text descriptions of BrainSTEM records, for the NWB free-text fields
(surgery, virus, pharmacology, stimulus_notes, data_collection, slices, notes).

Values are written as stored: quantities keep their unit, enum codes are only made readable,
and nothing is converted or inferred. The same records always give the same text.
"""

from __future__ import annotations

from typing import Any

from ..normalize.quantities import parse_quantity
from ..normalize.text import html_to_text, humanize_code, humanize_key, one_line
from ..normalize.timeutil import isoformat_utc, parse_datetime
from ..store.graph import Record, RecordStore

_COORDINATE_NAMES = {
    "apCoordinate": "AP",
    "mlCoordinate": "ML",
    "dvCoordinate": "DV",
    "rcCoordinate": "RC",
    "depth": "depth",
    "apAngle": "AP angle",
    "mlAngle": "ML angle",
    "rotation": "rotation",
    "x": "x",
    "y": "y",
    "z": "z",
}

# Keys whose values are long channel lists; they are summarized instead of listed.
_SUMMARIZED_LISTS = {"electrodeGroups": "electrode groups", "channelTags": "channel tags",
                     "siteCoordinates": "site coordinates", "siteGroups": "site groups", "shanks": "shanks"}
_MAX_LIST = 12


def ref(record: Record) -> str:
    """``[brainstem:procedure/<uuid>]``: how text descriptions cite their source record."""
    return f"[brainstem:{record.label.split('.')[-1]}/{record.pk}]"


def when(value: Any) -> str | None:
    if not value:
        return None
    try:
        return isoformat_utc(parse_datetime(str(value)))
    except ValueError:
        return str(value)


def value_text(value: Any) -> str:
    """One stored JSON value as text."""
    quantity = parse_quantity(value)
    if quantity is not None and isinstance(value, dict):
        return quantity.text()
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    if isinstance(value, str):
        stripped = value.strip()
        if "_" in stripped and " " not in stripped and stripped.islower():
            return humanize_code(stripped)
        return one_line(html_to_text(stripped))
    if isinstance(value, list):
        if not value:
            return ""
        if len(value) > _MAX_LIST:
            return f"[{len(value)} items]"
        parts = [value_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        inner = details_text(value)
        return f"({inner})" if inner else ""
    return str(value)


def details_text(details: Any) -> str:
    """Readable text of a ``type_json`` / ``details_json`` object or list (manipulation protocols)."""
    if details in (None, "", {}, []):
        return ""
    if isinstance(details, list):
        parts = []
        for index, item in enumerate(details, start=1):
            text = details_text(item) if isinstance(item, dict) else value_text(item)
            if text:
                parts.append(f"protocol {index}: {text}" if len(details) > 1 else text)
        return "; ".join(parts)
    if not isinstance(details, dict):
        return value_text(details)
    parts = []
    for key, value in details.items():
        if key in _SUMMARIZED_LISTS and isinstance(value, list):
            if value:
                labels = [str(item.get("label")) for item in value if isinstance(item, dict) and item.get("label")]
                label_text = f" ({', '.join(labels[:_MAX_LIST])}{', ...' if len(labels) > _MAX_LIST else ''})" \
                    if labels else ""
                parts.append(f"{_SUMMARIZED_LISTS[key]}: {len(value)}{label_text}")
            continue
        text = value_text(value)
        if text:
            parts.append(f"{humanize_key(key)}: {text}")
    return ", ".join(parts)


def coordinates_text(system: Any, coordinates: Any) -> str:
    if not isinstance(coordinates, dict) or not coordinates:
        return ""
    parts = []
    for key, value in coordinates.items():
        quantity = parse_quantity(value)
        if quantity is None:
            text = value_text(value)
            if text:
                parts.append(f"{humanize_key(key)} {text}")
            continue
        parts.append(f"{_COORDINATE_NAMES.get(key, humanize_key(key))} {quantity.text()}")
    if not parts:
        return ""
    prefix = f"{system} " if system else ""
    return f"{prefix}{', '.join(parts)}"


def region_records(store: RecordStore, record: Record, field_name: str = "target_regions") -> tuple[list[Record], int]:
    """Target region records of ``record`` (by acronym) and the number of links not in the export."""
    found: list[Record] = []
    unresolved = 0
    for link in store.m2m(record, field_name):
        if link.record is None:
            unresolved += 1
        else:
            found.append(link.record)
    return sorted(found, key=lambda r: (str(r.get("acronym") or r.get("name") or ""), r.pk)), unresolved


def region_label(store: RecordStore, region: Record) -> str:
    """``CA1 (Field CA1; Allen Mouse Common Coordinate Framework 2017)``."""
    acronym, name = region.get("acronym"), region.get("name")
    atlas = store.fk_record(region, "reference")
    atlas_text = " ".join(str(p) for p in (atlas.get("name"), atlas.get("version")) if p) if atlas else ""
    detail = "; ".join(p for p in (str(name or ""), atlas_text) if p and p != acronym)
    head = str(acronym or name or region.pk)
    return f"{head} ({detail})" if detail else head


def regions(store: RecordStore, record: Record, field_name: str = "target_regions") -> tuple[list[str], int]:
    """Readable target regions and the number unresolved."""
    found, unresolved = region_records(store, record, field_name)
    return [region_label(store, region) for region in found], unresolved


def region_acronyms(store: RecordStore, record: Record, field_name: str = "target_regions") -> list[str]:
    found, _ = region_records(store, record, field_name)
    return [str(r.get("acronym") or r.get("name") or r.pk) for r in found]


def regions_text(store: RecordStore, record: Record, field_name: str = "target_regions") -> str:
    names, unresolved = regions(store, record, field_name)
    parts = list(names)
    if unresolved:
        parts.append(f"{unresolved} region(s) not in the export (ids in manifest)")
    return ", ".join(parts)


def person_name(store: RecordStore, record: Record, field_name: str) -> str | None:
    """'First Last' of a user the record names; the export has names only."""
    ref = store.fk(record, field_name)
    if ref is None:
        return None
    if ref.record is None:
        return f"user {ref.pk} (not in the export)"
    return full_name(ref.record)


def full_name(user: Record) -> str:
    name = " ".join(str(p) for p in (user.get("first_name"), user.get("last_name")) if p)
    return name or f"user {user.pk}"


def nwb_person(user: Record) -> str:
    """NWB's person format: 'Last, First'."""
    first, last = user.get("first_name") or "", user.get("last_name") or ""
    return f"{last}, {first}".strip(", ") or f"user {user.pk}"


def consumable_text(store: RecordStore, consumable: Record | None) -> str:
    if consumable is None:
        return ""
    parts = [str(consumable.get("name") or "unnamed")]
    kind = consumable.get("type")
    detail = details_text(consumable.get("type_json"))
    rrid = consumable.get("rrid")
    supplier = store.fk_record(consumable, "supplier")
    supplier_text = f"supplier {supplier.get('name')}" if supplier is not None else ""
    extra = ", ".join(part for part in (humanize_code(kind) if kind else "", detail, supplier_text, str(rrid or ""))
                      if part)
    return f"{parts[0]} ({extra})" if extra else parts[0]


def material_text(store: RecordStore, usage: Record) -> str:
    """A material used in a procedure: catalog item, stock batch and the applied amounts."""
    stock = store.fk_record(usage, "consumable_stock")
    consumable = store.fk_record(usage, "consumable") or (store.fk_record(stock, "consumable") if stock else None)
    if consumable is not None:
        name = consumable_text(store, consumable)
    elif usage.get("manual_name"):
        name = str(usage.get("manual_name"))
    else:
        name = "material not recorded"
    parts = [f"{humanize_code(str(usage.get('type') or 'material'))}: {name}"]
    if stock is not None:
        stock_detail = details_text(stock.get("type_json"))
        if stock_detail:
            parts.append(f"stock {stock_detail}")
    applied = details_text(usage.get("details_json"))
    if applied:
        parts.append(f"applied {applied}")
    if usage.get("notes"):
        parts.append(f"notes: {one_line(html_to_text(str(usage.get('notes'))))}")
    return "; ".join(parts)


def notes_text(record: Record, field_name: str = "notes") -> str:
    value = record.get(field_name)
    return one_line(html_to_text(str(value))) if value else ""


def linked_names(store: RecordStore, record: Record, field_name: str) -> list[str]:
    """Names of linked records; lab resources the exporting user cannot read are named as such."""
    names = []
    for link in store.m2m(record, field_name):
        if link.record is not None:
            names.append(str(link.record.get("name")))
        elif link.reason == "restricted":
            names.append(f"{link.name} (not readable by the exporting user)")
    return names


def equipment_names(store: RecordStore, record: Record) -> str:
    return ", ".join(linked_names(store, record, "equipment"))


def interface_names(store: RecordStore, record: Record) -> str:
    out = []
    for interface in store.m2m_records(record, "interfaces"):
        kind = interface.get("type")
        out.append(f"{interface.get('name')} ({humanize_code(kind)})" if kind else str(interface.get("name")))
    return ", ".join(out)
