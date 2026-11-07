"""NWB Subject from the BrainSTEM subject, its species and strain."""

from __future__ import annotations

import datetime as dt

from ..manifest.models import SubjectPlan
from ..normalize.identifiers import ncbi_taxon_iri, normalize_rrid
from ..normalize.kv import key_values
from ..normalize.quantities import parse_quantity
from ..normalize.text import html_to_text, one_line
from ..normalize.timeutil import iso_duration_days, isoformat_utc, parse_date, parse_datetime
from ..normalize.units import subject_label
from ..store.graph import Record
from .context import MapContext
from .registry import MappingRule, rules

SECTION = "Subject"


@rules(
    MappingRule(id="subject.id", destination="Subject.subject_id", section=SECTION,
                sources=("stem.subject.name",),
                transform="verbatim ('/' replaced by '-', IDENTIFIER_SLASH_REPLACED); with subject.label_field = "
                          "name_used_in_storage, that field when set"),
    MappingRule(id="subject.species", destination="Subject.species", section=SECTION,
                sources=("taxonomies.species.name", "taxonomies.species.external_identifiers",
                         "taxonomies.species.rrid"),
                transform="binomial name (default); with subject.species_format = ncbitaxon, the NCBI Taxonomy "
                          "IRI from the species' NCBI identifier or RRID",
                missing="not written (SUBJECT_SPECIES_MISSING); the species is required in BrainSTEM, so this "
                        "only happens when the species record is missing from the export"),
    MappingRule(id="subject.strain", destination="Subject.strain", section=SECTION,
                sources=("taxonomies.strain.name",), transform="verbatim; the strain RRID goes to the description",
                condition="the subject has a strain"),
    MappingRule(id="subject.sex", destination="Subject.sex", section=SECTION,
                sources=("stem.subject.sex",),
                transform="F, M and U as stored (BrainSTEM has no 'O'); U is recorded as state 'unknown'"),
    MappingRule(id="subject.date_of_birth", destination="Subject.date_of_birth", section=SECTION,
                sources=("stem.subject.birth_date",), transform="the date at 00:00 UTC",
                missing="not written (SUBJECT_AGE_UNKNOWN)"),
    MappingRule(id="subject.age", destination="Subject.age, Subject.age__reference", section=SECTION,
                sources=("stem.subject.birth_date", "stem.session.date_time"),
                transform="whole days from the birth date to the session start date (UTC), as ISO 8601 "
                          "'P<n>D'; age__reference = 'birth'",
                units="days",
                missing="not written; a birth date after the session is an error (SUBJECT_AGE_NEGATIVE)"),
    MappingRule(id="subject.genotype", destination="Subject.genotype", section=SECTION,
                sources=("stem.subject.genotype",), transform="verbatim"),
    MappingRule(id="subject.description", destination="Subject.description", section=SECTION,
                sources=("stem.subject.description", "stem.subject.genetic_line", "stem.subject.subject_identifier",
                         "taxonomies.strain.rrid", "stem.subject.extra_content_json"),
                transform="description as plain text, then 'Genetic line: ...', 'External identifier: ...', "
                          "'Strain RRID: ...', custom fields as 'key: value', and 'BrainSTEM subject: <id>'"),
    MappingRule(id="subject.weight", destination="Subject.weight", section=SECTION,
                sources=("modules.subjectlog.type", "modules.moduleslogentry.type_json",
                         "modules.moduleslogentry.date_time", "modules.startendmoduleslogentry.type_json",
                         "modules.startendmoduleslogentry.start_date_time"),
                transform="the weight of the latest Weighing or Monitoring log entry at or before the session start, "
                          "as '<value> <unit>' as stored; its date goes to the description",
                condition="log entries are in the export (format 2.1)",
                missing="not written (SUBJECT_WEIGHT_UNKNOWN; SUBJECT_WEIGHT_NOT_IN_EXPORT for 2.0 exports)"),
)
def map_subject(ctx: MapContext) -> None:
    subject = ctx.unit.subject
    if subject is None:
        ctx.map("subject.id", "Subject", "not_applicable", note="exported without a subject")
        return
    store = ctx.store
    species = store.fk_record(subject, "species")
    strain = store.fk_record(subject, "strain")

    original_id = subject_label(subject, ctx.options.subject.label_field)
    subject_id = original_id.replace("/", "-")
    if subject_id != original_id:
        ctx.warn("IDENTIFIER_SLASH_REPLACED", f"subject_id '{original_id}' written as '{subject_id}'",
                 record=subject, nwb_path="/general/subject/subject_id", rule_id="subject.id")
    ctx.map("subject.id", "Subject.subject_id", "present", subject_id, [subject])

    species_value = None
    if species is None:
        ctx.map("subject.species", "Subject.species", "not_exported", sources=[subject])
        ctx.warn("SUBJECT_SPECIES_MISSING", record=subject, path="/fields/species", rule_id="subject.species")
    else:
        species_value = str(species.get("name"))
        if ctx.options.subject.species_format == "ncbitaxon":
            iri = ncbi_taxon_iri(dict(species.fields))
            if iri:
                species_value = iri
            else:
                ctx.warn("SPECIES_IRI_UNAVAILABLE",
                         f"species '{species.get('name')}' names no NCBI Taxonomy id; wrote the binomial name",
                         record=species, rule_id="subject.species")
        ctx.map("subject.species", "Subject.species", "present", species_value, [species])

    strain_value = str(strain.get("name")) if strain is not None else None
    ctx.map("subject.strain", "Subject.strain", "present" if strain_value else "missing", strain_value,
            [strain] if strain is not None else [subject])

    sex = subject.get("sex") or None
    if sex == "U":
        ctx.map("subject.sex", "Subject.sex", "unknown", sources=[subject], note="written as 'U'")
    elif sex:
        ctx.map("subject.sex", "Subject.sex", "present", sex, [subject])
    else:
        ctx.map("subject.sex", "Subject.sex", "missing", sources=[subject])

    date_of_birth = None
    age = None
    birth = subject.get("birth_date")
    if birth:
        birth_date = parse_date(str(birth))
        date_of_birth = dt.datetime(birth_date.year, birth_date.month, birth_date.day, tzinfo=dt.timezone.utc)
        ctx.map("subject.date_of_birth", "Subject.date_of_birth", "present", date_of_birth.isoformat(), [subject])
        days = (ctx.unit.session_start.astimezone(dt.timezone.utc).date() - birth_date).days
        if days < 0:
            ctx.map("subject.age", "Subject.age", "missing", sources=[subject, ctx.unit.session],
                    note="birth date after session start")
            ctx.warn("SUBJECT_AGE_NEGATIVE",
                     f"subject '{subject.get('name')}' was born {birth} after the session started", record=subject,
                     path="/fields/birth_date", rule_id="subject.age")
        else:
            age = iso_duration_days(days)
            ctx.map("subject.age", "Subject.age", "present", age, [subject, ctx.unit.session])
    else:
        ctx.map("subject.date_of_birth", "Subject.date_of_birth", "missing", sources=[subject])
        ctx.map("subject.age", "Subject.age", "missing", sources=[subject])
        ctx.warn("SUBJECT_AGE_UNKNOWN", f"subject '{subject.get('name')}' has no birth date", record=subject,
                 path="/fields/birth_date", rule_id="subject.age")

    genotype = str(subject.get("genotype") or "").strip() or None
    ctx.map("subject.genotype", "Subject.genotype", "present" if genotype else "missing", genotype, [subject])

    description_parts = []
    text = html_to_text(subject.get("description"))
    if text:
        description_parts.append(one_line(text))
    if subject.get("genetic_line"):
        description_parts.append(f"Genetic line: {subject.get('genetic_line')}.")
    if subject.get("subject_identifier"):
        description_parts.append(f"External identifier: {subject.get('subject_identifier')}.")
    strain_rrid = normalize_rrid(strain.get("rrid")) if strain is not None else None
    if strain_rrid:
        description_parts.append(f"Strain RRID: {strain_rrid}.")
    for key, value in key_values(subject.get("extra_content_json")):
        description_parts.append(f"{key}: {value}.")
    weight, weighed = _latest_weight(ctx, subject)
    if weight is not None and weighed is not None:
        description_parts.append(f"Weight {weight} measured {isoformat_utc(weighed)}.")
    description_parts.append(f"BrainSTEM subject: {subject.pk}.")
    description = " ".join(description_parts)
    ctx.map("subject.description", "Subject.description", "present", description, [subject])

    if weight is not None and weighed is not None:
        ctx.map("subject.weight", "Subject.weight", "present", weight, [subject])
    elif "modules.moduleslogentry" not in ctx.export.records:
        ctx.map("subject.weight", "Subject.weight", "not_exported", sources=[subject])
        ctx.warn("SUBJECT_WEIGHT_NOT_IN_EXPORT", record=subject, rule_id="subject.weight")
    else:
        ctx.map("subject.weight", "Subject.weight", "missing", sources=[subject])
        ctx.warn("SUBJECT_WEIGHT_UNKNOWN", f"subject '{subject.get('name')}' has no weighing before the session",
                 record=subject, rule_id="subject.weight")

    ctx.subject = SubjectPlan(
        subject_id=subject_id,
        species=species_value,
        strain=strain_value,
        sex=sex,
        date_of_birth=date_of_birth,
        age=age,
        age__reference="birth" if age else None,
        genotype=genotype,
        description=description,
        weight=weight,
    )


WEIGHT_LOG_TYPES = {"Weighing", "Monitoring"}


def _latest_weight(ctx: MapContext, subject: Record) -> tuple[str | None, dt.datetime | None]:
    """The latest recorded weight at or before the session start, as stored ('25.3 g'), and when."""
    best: tuple[dt.datetime, str, str] | None = None
    for log in ctx.store.referrers(subject, "modules.subjectlog", "subject"):
        if log.get("type") not in WEIGHT_LOG_TYPES:
            continue
        for entry in ctx.store.log_entries(log):
            details = entry.get("type_json") if isinstance(entry.get("type_json"), dict) else {}
            quantity = parse_quantity(details.get("weight"))
            when_raw = entry.get("date_time") or entry.get("start_date_time")
            if quantity is None or quantity.unit is None or not when_raw:
                continue
            try:
                when = parse_datetime(str(when_raw))
            except ValueError:
                continue
            if when > ctx.unit.session_start:
                continue
            candidate = (when, entry.pk, quantity.text())
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best is None:
        return None, None
    return best[2], best[0].astimezone(dt.timezone.utc).replace(microsecond=0)
