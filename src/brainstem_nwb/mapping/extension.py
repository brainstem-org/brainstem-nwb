"""
The ndx-brainstem tables of a unit (``--extension brainstem``): every BrainSTEM record the file was
made from, with every field, so nothing BrainSTEM records is lost inside the NWB file.

Tables, columns and links are generated from the field inventory, not written by hand:

- each table holds the records of one kind (``TABLES``), one row per record, sorted by model and id;
- each BrainSTEM field is a column named as the field: strings as stored, other values as JSON,
  an empty string for no value;
- a link field whose targets are in another table becomes a ragged link (DynamicTableRegion) to it;
  ids of targets not in the file go to ``unresolved_links``;
- ``details_schema`` and ``coordinates_schema`` name the BrainSTEM JSON schemas of the typed details and the
  coordinates (``Family/Type@version``); the ``schemas`` table gives each one's stable URL and, when
  embedded (from the export, or fetched with ``--embed-schemas``), the schema itself.

Administrative lab resources (licenses, data storages, inventories), the links to them, and the
administrative fields of kept resources (a stock's cost, dates and storage) are left out of the file;
they are kept in the manifest. Record bookkeeping (creator, created/updated times) is
left out as well. Records after the session start (later procedures, log entries) are left out, as in
the core file.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from ..manifest.models import BrainstemExtensionPlan, ExtensionColumnPlan, ExtensionTablePlan
from ..normalize.schemas import parse_schema_id, schema_refs
from ..normalize.timeutil import parse_datetime
from ..store.graph import Record
from ..store.inventory import DROPPED_FIELDS
from .context import MapContext
from .registry import MappingRule, rules

# (table name, description, model labels). Tables are ordered so that links only point to earlier
# tables: a cycle of links (or a table linking to itself) makes hdmf recurse without end when a reader
# converts a table to a DataFrame. A link to a later table, or within a table, is written as BrainSTEM
# ids in a text column instead.
TABLES: list[tuple[str, str, tuple[str, ...]]] = [
    ("people", "People named on the records (names only)", ("users.user",)),
    ("organisms", "Species and strains", ("taxonomies.species", "taxonomies.strain")),
    ("suppliers", "Suppliers of consumables and hardware", ("resources.supplier",)),
    ("publications", "Publications of the projects and their journals",
     ("dissemination.journal", "dissemination.publication")),
    ("atlases", "Brain atlases (anatomical references) and coordinate transforms",
     ("taxonomies.anatomicalreference", "taxonomies.coordinatetransform")),
    ("regions", "Brain regions", ("taxonomies.anatomicalregion",)),
    ("catalog", "Shared catalog entries: consumables (viruses, drugs, probe designs, ...), hardware devices, setup "
                "types, behavioral paradigms and categories",
     ("resources.consumable", "resources.hardwaredevice", "taxonomies.setuptype", "taxonomies.behavioralcategory",
      "taxonomies.behavioralparadigm")),
    ("lab_resources", "Lab resources the records use: setups, equipment, behavioral assays, protocols, consumable "
                      "stocks; nwb_device names the NWB Device of equipment",
     ("personal_attributes.setup", "modules.equipment", "personal_attributes.behavioralassay",
      "personal_attributes.protocol", "personal_attributes.protocolallowedsubtype", "modules.consumablestock")),
    ("projects", "BrainSTEM projects of the session", ("stem.project",)),
    ("subjects", "The BrainSTEM subject", ("stem.subject",)),
    ("sessions", "The BrainSTEM session", ("stem.session",)),
    ("specimen_sets", "Specimen sets (ex vivo)", ("stem.specimenset",)),
    ("specimens", "Specimens (ex vivo)", ("stem.specimen",)),
    ("procedure_episodes", "Procedure episodes (surgeries, treatments)", ("modules.procedureepisode",)),
    ("episode_personnel", "People in procedure episodes and their roles", ("modules.episodepersonnel",)),
    ("procedures", "Procedures of the subject up to the session", ("modules.procedure",)),
    ("specimen_procedures", "Specimen procedures (ex vivo)",
     ("modules.specimenprocedure", "modules.specimenproceduretarget")),
    ("interfaces", "Experimental interfaces (probes, fibers, windows, ...); nwb_device names the NWB Device",
     ("modules.experimentalinterface",)),
    ("procedure_interfaces", "Links between procedures and interfaces", ("modules.procedureinterface",)),
    ("materials", "Materials used in procedures and interfaces (viruses, drugs, probes, ...)",
     ("modules.materialusage", "modules.materialusagetarget")),
    ("procedure_stages", "Stages of procedures", ("modules.procedurestage", "modules.procedurestagetarget")),
    ("acquisitions", "Data acquisitions of the session", ("modules.dataacquisition",)),
    ("acquisition_links", "Interfaces of data acquisitions, in order", ("modules.dataacquisitioninterface",)),
    ("manipulations", "Manipulations of the session", ("modules.manipulation",)),
    ("manipulation_interfaces", "Interfaces of manipulations, in order", ("modules.manipulationinterface",)),
    ("behaviors", "Behaviors of the session", ("modules.behavior",)),
    ("epochs", "BrainSTEM epochs of the session; nwb_epochs links the rows written to /intervals/epochs",
     ("stem.epoch",)),
    ("logs", "Subject, procedure and specimen logs", ("modules.subjectlog", "modules.procedurelog",
                                                      "modules.specimenlog")),
    ("log_entries", "Log entries up to the session (weights, observations, adjustments, ...)",
     ("modules.moduleslogentry", "modules.startendmoduleslogentry")),
]
TABLE_ORDER = {name: position for position, (name, _description, _labels) in enumerate(TABLES)}

# Administrative lab resources: never written to the NWB file (kept in the manifest).
ADMINISTRATIVE = frozenset({
    "personal_attributes.license", "personal_attributes.datastorage", "personal_attributes.inventory",
    "stem.sessiondatastorage", "taxonomies.regulatoryauthority",
})
_BOOKKEEPING = frozenset({"created_at", "updated_at", "is_public"})
# Records in the unit only to be kept in the manifest: later and not performed procedures.
LEFT_OUT_ROLES = frozenset({"procedure_after_session", "procedure_not_performed", "specimen_procedure_not_performed"})
# Administrative fields of the lab resources that are kept (stocks keep batch and titer in type_json).
ADMINISTRATIVE_FIELDS: dict[str, frozenset[str]] = {
    "modules.consumablestock": frozenset({"cost", "acquisition_date", "expiration_date", "storage_conditions",
                                          "storage_location", "status", "intended_use", "notes"}),
    "stem.specimenset": frozenset({"storage_conditions", "storage_location"}),
    "stem.specimen": frozenset({"storage_conditions", "storage_location"}),
}
# Field names a DynamicTable column cannot have (table attributes and properties, and the extension's own
# columns); such a field is written as the column "record_<field>".
RESERVED_COLUMNS = frozenset({
    "name", "description", "id", "colnames", "columns", "namespace", "neurodata_type", "object_id", "parent",
    "fields", "data_type", "brainstem_models", "brainstem_id", "brainstem_model", "details_schema",
    "coordinates_schema", "unresolved_links", "nwb_device", "nwb_epochs", "log", "catalog_entry",
    "schema_id", "schema_url", "schema_json",
})


def column_name(field: str) -> str:
    """Column of a BrainSTEM field: the field name, 'record_<field>' for reserved names, and '<field>_iso' for
    fields ending in '_time' (NWB tools take '*_time' columns for times in seconds; these hold ISO 8601 text)."""
    if field in RESERVED_COLUMNS:
        return f"record_{field}"
    if field.endswith("_time"):
        return f"{field}_iso"
    return field
_EPOCHS = "/intervals/epochs"



@rules(
    MappingRule(
        id="extension.brainstem",
        destination="ndx-brainstem: /general/brainstem (BrainstemMetadata with BrainstemTables)",
        section="Extension",
        sources=(),
        transform="every included BrainSTEM record as a row of the table for its kind; every field as a column "
                  "(strings as stored, other values as JSON); links as ragged DynamicTableRegions between tables "
                  "and to /intervals/epochs; details_schema and coordinates_schema name the BrainSTEM JSON schemas, "
                  "listed with their stable URLs (and embedded with --embed-schemas) in the schemas table",
        condition="--extension brainstem",
        missing="administrative lab resources (licenses, data storages, inventories) and record bookkeeping are "
                "left out; records after the session start are left out as in the core file",
    ),
)
def map_extension(ctx: MapContext) -> BrainstemExtensionPlan:
    start = ctx.unit.session_start

    # Records per table
    label_table = {label: name for name, _description, labels in TABLES for label in labels}
    rows: dict[str, list[Record]] = defaultdict(list)
    for (label, _pk), (record, roles) in sorted(ctx.unit.all_records().items()):
        table_name = label_table.get(label)
        if table_name is None or label in ADMINISTRATIVE:
            continue
        if set(roles) <= LEFT_OUT_ROLES:
            continue
        if table_name == "log_entries" and _after(record, start):
            continue
        rows[table_name].append(record)
    for name in rows:
        rows[name].sort(key=lambda r: (r.label, r.pk))
    index = {name: {record.key: i for i, record in enumerate(records)} for name, records in rows.items()}

    nwb_epoch_rows = {row.values.get("brainstem_id"): i for i, row in enumerate(ctx.epochs.rows)}
    device_names = dict(ctx.device_by_record)
    tables: list[ExtensionTablePlan] = []
    for name, description, labels in TABLES:
        records = rows.get(name, [])
        if not records:
            continue
        columns = _columns(ctx, name, labels, records, label_table, rows)
        table = ExtensionTablePlan(name=name, description=description,
                                   brainstem_models=sorted({r.label for r in records}), columns=columns)
        for record in records:
            table.rows.append(_row(ctx, record, columns, index, label_table, nwb_epoch_rows, device_names))
        tables.append(table)

    used = sorted({str(row[column]) for t in tables for row in t.rows
                   for column in ("details_schema", "coordinates_schema") if row.get(column)})
    provided: dict[str, Any] = ctx.export.schemas  # from the export, or fetched with --embed-schemas
    schemas = [{"schema_id": sid, "schema_url": parse_schema_id(sid).url(),
                "schema_json": json.dumps(provided[sid], sort_keys=True, ensure_ascii=False) if sid in provided else ""}
               for sid in used]
    ctx.map("extension.brainstem", "/general/brainstem", "present",
            {t.name: len(t.rows) for t in tables}, note="ndx-brainstem tables (rows per table)")
    terms = schemas_terms(ctx.inventory.license) if any(s["schema_json"] for s in schemas) else None
    return BrainstemExtensionPlan(tables=tables, schemas=schemas, schemas_terms=terms)


def schemas_terms(license_info: dict[str, Any] | None) -> str:
    """BrainSTEM's ownership notice for embedded schemas, as the server states it, with the URL of its terms."""
    info = license_info or {}
    notice = str(info.get("notice") or "The BrainSTEM schemas are the property of BrainSTEM and are not open source.")
    url = str(info.get("url") or "https://www.brainstem.org/reference/license.md")
    return (f"{notice} The schemas are embedded unchanged, as a BrainSTEM export embeds them, for the records this "
            f"file describes. Terms: {url}")


def _after(record: Record, start: Any) -> bool:
    value = record.get("date_time") or record.get("start_date_time")
    if not value:
        return False
    try:
        return parse_datetime(str(value)) > start
    except ValueError:
        return False


def _columns(ctx: MapContext, table: str, labels: tuple[str, ...], records: list[Record],
             label_table: dict[str, str], rows: dict[str, list[Record]]) -> list[ExtensionColumnPlan]:
    inventory = ctx.inventory
    present = {r.label for r in records}
    columns: dict[str, ExtensionColumnPlan] = {}
    for label in labels:
        if label not in present:
            continue
        for field, spec in inventory.fields(label).items():
            if field in DROPPED_FIELDS or field in _BOOKKEEPING or column_name(field) in columns:
                continue
            if label == "users.user" and field not in ("first_name", "last_name"):
                continue
            if field in ADMINISTRATIVE_FIELDS.get(label, frozenset()):
                continue
            kind = spec.get("kind")
            target = spec.get("target")
            if kind in ("fk", "m2m") and target in ADMINISTRATIVE:
                continue
            if (kind in ("fk", "m2m") and target in label_table and label_table[target] in rows
                    and TABLE_ORDER[label_table[target]] < TABLE_ORDER[table]):
                columns[column_name(field)] = ExtensionColumnPlan(
                    name=column_name(field), description=f"BrainSTEM link {label}.{field} to {label_table[target]}",
                    link_table=label_table[target], field=field)
            else:
                columns[column_name(field)] = ExtensionColumnPlan(
                    name=column_name(field), description=f"BrainSTEM field {label}.{field} ({spec['type']})",
                    field=field)
    extra = [ExtensionColumnPlan(name="details_schema", description="BrainSTEM JSON schema of the typed details"),
             ExtensionColumnPlan(name="coordinates_schema", description="BrainSTEM JSON schema of the coordinates"),
             ExtensionColumnPlan(name="unresolved_links",
                                 description="JSON {field: [ids]} of links to records not in this file")]
    if table == "log_entries" and "logs" in rows:
        extra.append(ExtensionColumnPlan(name="log", description="the log of the entry (content_type, object_id)",
                                         link_table="logs"))
    if table == "epochs" and ctx.epochs.rows:
        extra.append(ExtensionColumnPlan(name="nwb_epochs", description="the row written to /intervals/epochs",
                                         link_table=_EPOCHS))
    if table == "materials" and "catalog" in rows:
        extra.append(ExtensionColumnPlan(
            name="catalog_entry", link_table="catalog",
            description="the catalog consumable of the material: its own consumable, or the consumable of its stock"))
    if table in ("interfaces", "lab_resources"):
        extra.append(ExtensionColumnPlan(name="nwb_device", description="name of the NWB Device made from the record"))
    for column in extra:
        columns.setdefault(column.name, column)
    if not any(schema_refs(ctx.store, r).get("coordinates") for r in records):
        columns.pop("coordinates_schema", None)
    tail = ("details_schema", "coordinates_schema", "unresolved_links")
    return [columns[name] for name in sorted(columns, key=lambda n: (n in tail, n))]


def _row(ctx: MapContext, record: Record, columns: list[ExtensionColumnPlan], index: dict[str, dict[Any, int]],
         label_table: dict[str, str], nwb_epoch_rows: dict[Any, int],
         device_names: dict[tuple[str, str], str]) -> dict[str, str | list[int]]:
    inventory = ctx.inventory
    fields = inventory.fields(record.label)
    row: dict[str, str | list[int]] = {"brainstem_id": record.pk, "brainstem_model": record.label}
    unresolved: dict[str, list[str]] = {}
    for column in columns:
        name = column.name
        field = column.field or name
        if column.link_table and column.field:  # a BrainSTEM link field
            spec = fields.get(field) or {}
            targets = _ids(record.get(field)) if spec.get("kind") in ("fk", "m2m") else []
            target_label = spec.get("target")
            links: list[int] = []
            missing: list[str] = []
            for pk in targets:
                position = index.get(column.link_table, {}).get((target_label, pk))
                if position is None:
                    missing.append(pk)
                else:
                    links.append(position)
            row[name] = sorted(links)
            if missing:
                unresolved[field] = [str(m) for m in missing]
            continue
        if name == "log":
            key = (str(record.get("content_type") or "").lower(), str(record.get("object_id") or ""))
            position = index.get("logs", {}).get(key)
            row[name] = [position] if position is not None else []
            continue
        if name == "catalog_entry":
            consumable = ctx.store.fk_record(record, "consumable") if record.label == "modules.materialusage" else None
            if consumable is None and record.label == "modules.materialusage":
                stock = ctx.store.fk_record(record, "consumable_stock")
                consumable = ctx.store.fk_record(stock, "consumable") if stock is not None else None
            position = index.get("catalog", {}).get(consumable.key) if consumable is not None else None
            row[name] = [position] if position is not None else []
            continue
        if name == "nwb_epochs":
            position = nwb_epoch_rows.get(record.pk)
            row[name] = [position] if position is not None else []
            continue
        if name == "nwb_device":
            row[name] = device_names.get(record.key, "")
            continue
        if name in ("details_schema", "coordinates_schema"):
            ref = schema_refs(ctx.store, record).get("details" if name == "details_schema" else "coordinates")
            row[name] = ref.id if ref is not None else ""
            continue
        if name == "unresolved_links":
            continue
        field_spec = fields.get(field)
        if field_spec is None or field not in record.fields or field in ADMINISTRATIVE_FIELDS.get(record.label, ()):
            row[name] = ""
            continue
        row[name] = _text(record.get(field))
    row["unresolved_links"] = json.dumps(unresolved, sort_keys=True) if unresolved else ""
    return row


def _ids(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
