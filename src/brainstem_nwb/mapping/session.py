"""NWBFile fields that describe the session, the project and the people."""

from __future__ import annotations

from ..normalize.text import html_to_text
from . import describe
from .context import MapContext
from .registry import MappingRule, rules


@rules(
    MappingRule(
        id="session.description",
        destination="NWBFile.session_description",
        sources=("stem.session.description",),
        transform="rich text (HTML) converted to plain text",
        missing="placeholder \"BrainSTEM session '<name>' has no description.\" and warning "
                "SESSION_DESCRIPTION_MISSING (the field is required by NWB)",
    ),
    MappingRule(
        id="session.start_time",
        destination="NWBFile.session_start_time, NWBFile.timestamps_reference_time",
        sources=("stem.session.date_time",),
        transform="ISO 8601 datetime with the time zone it is exported in (UTC from the BrainSTEM server)",
        missing="no file is written for the session (unit error SESSION_START_TIME_MISSING)",
    ),
    MappingRule(
        id="session.id",
        destination="NWBFile.session_id",
        sources=("stem.session.name",),
        transform="verbatim ('/' replaced by '-', IDENTIFIER_SLASH_REPLACED)",
    ),
    MappingRule(
        id="session.keywords",
        destination="NWBFile.keywords",
        sources=("stem.project.tags", "stem.session.tags"),
        transform="union of project and session tags, sorted, plus 'BrainSTEM' and 'metadata-only'",
    ),
)
def map_session(ctx: MapContext) -> None:
    session = ctx.unit.session
    name = str(session.get("name") or session.pk)
    description = html_to_text(session.get("description"))
    if description:
        ctx.map("session.description", "NWBFile.session_description", "present", description, [session])
    else:
        description = f"BrainSTEM session '{name}' has no description."
        ctx.map("session.description", "NWBFile.session_description", "missing", sources=[session],
                note="placeholder written")
        ctx.warn("SESSION_DESCRIPTION_MISSING", record=session, path="/fields/description",
                 nwb_path="/session_description", rule_id="session.description")
    ctx.nwbfile["session_description"] = description

    ctx.nwbfile["session_start_time"] = ctx.unit.session_start
    ctx.nwbfile["timestamps_reference_time"] = ctx.unit.session_start
    ctx.map("session.start_time", "NWBFile.session_start_time", "present",
            ctx.unit.session_start.isoformat(), [session])

    session_id = name.replace("/", "-")
    if session_id != name:
        ctx.warn("IDENTIFIER_SLASH_REPLACED", f"session_id '{name}' written as '{session_id}'", record=session,
                 nwb_path="/session_id", rule_id="session.id")
    ctx.nwbfile["session_id"] = session_id
    ctx.map("session.id", "NWBFile.session_id", "present", session_id, [session])

    tags: set[str] = set()
    for record in (*ctx.unit.projects, session):
        tags.update(str(tag) for tag in record.get("tags") or [] if str(tag).strip())
    keywords = sorted(tags | {"BrainSTEM", "metadata-only"})
    ctx.nwbfile["keywords"] = keywords
    ctx.map("session.keywords", "NWBFile.keywords", "present", keywords, [*ctx.unit.projects, session])


@rules(
    MappingRule(
        id="project.experiment_description",
        destination="NWBFile.experiment_description",
        sources=("stem.project.name", "stem.project.description"),
        transform="\"<project name>: <description as plain text>\"; a session in several projects lists each, "
                  "separated by blank lines",
        missing="project name only",
    ),
    MappingRule(
        id="project.related_publications",
        destination="NWBFile.related_publications",
        sources=("dissemination.publication.doi", "dissemination.publication.publication_url"),
        transform="\"doi:<doi>\" for each publication of the session's projects; the publication URL when it "
                  "has no DOI",
        condition="publication records are in the export (format 2.1)",
        missing="not written; publication ids are listed in the manifest (PUBLICATIONS_NOT_RESOLVED)",
    ),
)
def map_project(ctx: MapContext) -> None:
    projects = ctx.unit.projects
    if not projects:
        ctx.map("project.experiment_description", "NWBFile.experiment_description", "not_exported")
        return
    texts = []
    for project in projects:
        name = str(project.get("name") or project.pk)
        description = html_to_text(project.get("description"))
        texts.append(f"{name}: {description}" if description else name)
    text = "\n\n".join(texts)
    ctx.nwbfile["experiment_description"] = text
    ctx.map("project.experiment_description", "NWBFile.experiment_description", "present", text, projects)

    references: set[str] = set()
    unresolved = 0
    for project in projects:
        for link in ctx.store.m2m(project, "publications"):
            if link.record is None:
                unresolved += 1
            elif link.record.get("doi"):
                references.add(f"doi:{str(link.record.get('doi')).strip()}")
            elif link.record.get("publication_url"):
                references.add(str(link.record.get("publication_url")))
    if references:
        ctx.nwbfile["related_publications"] = sorted(references)
        ctx.map("project.related_publications", "NWBFile.related_publications", "present", sorted(references),
                projects)
    if unresolved:
        ctx.map("project.related_publications", "NWBFile.related_publications", "not_exported", sources=projects,
                note=f"{unresolved} publication id(s) in the manifest")
        ctx.warn("PUBLICATIONS_NOT_RESOLVED",
                 f"{unresolved} publication(s) of the project are not in the export",
                 record=projects[0], path="/fields/publications", rule_id="project.related_publications")
    elif not references:
        ctx.map("project.related_publications", "NWBFile.related_publications", "missing", sources=projects)


@rules(
    MappingRule(
        id="config.experimenter",
        destination="NWBFile.experimenter",
        sources=("stem.session.user", "users.user.first_name", "users.user.last_name"),
        transform="from the configuration file (nwbfile.experimenter, 'Last, First' per person); with "
                  "nwbfile.experimenter_source = \"session_creator\" and none configured, the user who created the "
                  "session record, as 'Last, First'",
        condition="configured; BrainSTEM records who created a session, not who ran it",
        missing="not written (EXPERIMENTER_NOT_AVAILABLE); surgeons are never used as experimenters",
        section="Configuration",
    ),
    MappingRule(
        id="config.lab_institution",
        destination="NWBFile.lab, NWBFile.institution",
        sources=(),
        transform="from the configuration file (nwbfile.lab, nwbfile.institution)",
        condition="configured; laboratory records are not exported",
        missing="not written (LAB_NOT_AVAILABLE)",
        section="Configuration",
    ),
)
def map_people(ctx: MapContext) -> None:
    config = ctx.options.nwbfile
    creator = ctx.store.fk_record(ctx.unit.session, "user") if config.experimenter_source == "session_creator" \
        else None
    if config.experimenter:
        ctx.nwbfile["experimenter"] = list(config.experimenter)
        ctx.map("config.experimenter", "NWBFile.experimenter", "present", list(config.experimenter),
                note="from configuration")
    elif creator is not None:
        ctx.nwbfile["experimenter"] = [describe.nwb_person(creator)]
        ctx.map("config.experimenter", "NWBFile.experimenter", "present", ctx.nwbfile["experimenter"],
                [ctx.unit.session, creator], note="creator of the session record")
    else:
        ctx.map("config.experimenter", "NWBFile.experimenter", "not_exported")
        ctx.warn("EXPERIMENTER_NOT_AVAILABLE", nwb_path="/general/experimenter", rule_id="config.experimenter")
    for key in ("lab", "institution"):
        value = getattr(config, key)
        if value:
            ctx.nwbfile[key] = value
            ctx.map("config.lab_institution", f"NWBFile.{key}", "present", value, note="from configuration")
        else:
            ctx.map("config.lab_institution", f"NWBFile.{key}", "not_exported")
    if not config.lab or not config.institution:
        ctx.warn("LAB_NOT_AVAILABLE", rule_id="config.lab_institution")


@rules(
    MappingRule(
        id="protocol.protocols",
        destination="NWBFile.protocol",
        sources=("personal_attributes.protocol.name", "personal_attributes.protocol.protocol_type",
                 "personal_attributes.protocol.url"),
        transform="one line per protocol of the included procedures, episodes and specimen procedures: "
                  "\"<name> (<type>) <url>\". Licenses (regulatory approvals) are administrative lab resources and "
                  "stay in the manifest",
        missing="not written",
    ),
)
def map_protocols(ctx: MapContext) -> None:
    lines = []
    for protocol in ctx.unit.role("protocol"):
        kind = protocol.get("protocol_type")
        url = protocol.get("url")
        lines.append(" ".join(part for part in (
            str(protocol.get("name") or protocol.pk), f"({kind})" if kind else "", str(url or "")) if part))
    if lines:
        text = "\n".join(lines)
        ctx.nwbfile["protocol"] = text
        ctx.map("protocol.protocols", "NWBFile.protocol", "present", text, ctx.unit.role("protocol"))
    else:
        ctx.map("protocol.protocols", "NWBFile.protocol", "missing")
