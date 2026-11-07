"""
The three validation passes run on every exported file:

1. NWB schema validation (``pynwb.validate``);
2. NWB Inspector best-practice checks, by default with the DANDI configuration;
3. BrainSTEM-specific semantic checks against the manifest unit the file was written from.

Severities: pynwb errors, Inspector CRITICAL findings and failed semantic checks are errors; an
Inspector ERROR (a check that crashed on the file, a tool problem) is a warning;
BEST_PRACTICE_VIOLATION is a warning; BEST_PRACTICE_SUGGESTION is info. A few Inspector checks are
expected to fire on every metadata-only file and are downgraded to info, with the reason, in
``EXPECTED_FINDINGS``. CRITICAL findings are never downgraded.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from ..manifest.models import Severity, Unit
from ..nwb.canonical import canonical_summary, provenance_from_notes
from ..nwb.writer import file_sha256
from .report import Finding

# Inspector checks that metadata-only files fail by design: check name -> reason.
EXPECTED_FINDINGS: dict[str, dict[str, str]] = {
    "metadata-only": {
        "check_optogenetic_stimulus_site_has_optogenetic_series":
            "metadata-only files describe stimulation sites but contain no stimulus data",
    },
}
# Inspector checks expected to fire on ndx-brainstem tables only: check -> reason.
BRAINSTEM_TABLE_TYPES = frozenset({"BrainstemTable", "BrainstemSchemaTable"})
EXPECTED_ON_BRAINSTEM_TABLES: dict[str, str] = {
    "check_table_values_for_dict": "ndx-brainstem keeps BrainSTEM's typed details and JSON schemas as JSON text, "
                                   "by design",
    "check_single_row": "ndx-brainstem has one table per kind of record, whatever the number of records",
    "check_column_binary_capability": "ndx-brainstem link indices are row numbers, not booleans",
}

_IMPORTANCE_SEVERITY: dict[str, Severity] = {
    "CRITICAL": "error",
    "ERROR": "warning",  # an Inspector check crashed on the file: a tool problem, not a file problem
    "PYNWB_VALIDATION": "error",
    "BEST_PRACTICE_VIOLATION": "warning",
    "BEST_PRACTICE_SUGGESTION": "info",
}


def run_pynwb_validation(path: Path) -> list[Finding]:
    from pynwb import validate

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = validate(path=str(path))
    except Exception as exc:  # unreadable file
        return [Finding(severity="error", origin="pynwb", code="UNREADABLE", message=f"{type(exc).__name__}: {exc}")]
    errors = result[0] if isinstance(result, tuple) else result
    return [
        Finding(severity="error", origin="pynwb", code=type(error).__name__,
                message=str(getattr(error, "reason", error)),
                location=str(getattr(error, "location", "") or "") or None)
        for error in errors or []
    ]


def run_inspector(path: Path, *, config: str | None = "dandi", mode: str = "metadata-only") -> list[Finding]:
    from nwbinspector import inspect_nwbfile, load_config

    expected = EXPECTED_FINDINGS.get(mode, {})
    loaded = load_config(config) if config else None
    findings = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        messages = list(inspect_nwbfile(nwbfile_path=str(path), config=loaded, skip_validate=True))
    for message in messages:
        if message is None:
            continue
        importance = message.importance.name
        severity: Severity = _IMPORTANCE_SEVERITY.get(importance, "warning")
        reason = expected.get(message.check_function_name or "")
        if not reason and message.object_type in BRAINSTEM_TABLE_TYPES:
            reason = EXPECTED_ON_BRAINSTEM_TABLES.get(message.check_function_name or "")
        is_expected = bool(reason) and importance != "CRITICAL"
        if is_expected:
            severity = "info"
        location = message.location or (
            f"{message.object_type} '{message.object_name}'" if message.object_type else None)
        findings.append(Finding(
            severity=severity, origin="nwbinspector", code=message.check_function_name or "unknown",
            message=message.message, location=location, importance=importance,
            expected=is_expected, expected_reason=reason if is_expected else None,
        ))
    return findings


def run_semantic_checks(path: Path, unit: Unit | None) -> list[Finding]:
    """Check the file against the manifest unit it was written from, and for DANDI readiness."""
    findings: list[Finding] = []

    def error(code: str, message: str, location: str | None = None) -> None:
        findings.append(Finding(severity="error", origin="brainstem", code=code, message=message, location=location))

    def warning(code: str, message: str, location: str | None = None) -> None:
        findings.append(Finding(severity="warning", origin="brainstem", code=code, message=message, location=location))

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            summary = canonical_summary(path)
    except Exception as exc:
        error("UNREADABLE", f"cannot read the file: {type(exc).__name__}: {exc}")
        return findings

    provenance = provenance_from_notes(summary.get("notes"))
    if provenance is None:
        error("PROVENANCE_MISSING", "NWBFile.notes has no readable BrainSTEM provenance block", "/general/notes")
    if "metadata-only" not in (summary.get("keywords") or []):
        warning("METADATA_ONLY_KEYWORD_MISSING", "keyword 'metadata-only' is missing", "/general/keywords")
    if summary["acquisition"] or summary["stimulus"] or summary["processing"]:
        error("DATA_IN_METADATA_ONLY_FILE",
              "a metadata-only export contains acquisition, stimulus or processing data")

    subject = summary.get("subject")
    if subject is None:
        warning("DANDI_SUBJECT_MISSING", "no Subject: DANDI requires subject_id, species and sex", "/general/subject")
    else:
        for key in ("subject_id", "species", "sex"):
            if not subject.get(key):
                warning(f"DANDI_SUBJECT_{key.upper()}_MISSING", f"Subject.{key} is missing (required by DANDI)",
                        f"/general/subject/{key}")
        if not subject.get("age") and not subject.get("date_of_birth"):
            warning("DANDI_SUBJECT_AGE_MISSING", "Subject has neither age nor date_of_birth (required by DANDI)",
                    "/general/subject")

    if unit is not None and unit.nwb is not None:
        if summary["identifier"] != unit.output.nwb_identifier:
            error("IDENTIFIER_MISMATCH",
                  f"identifier {summary['identifier']} differs from the manifest ({unit.output.nwb_identifier})")
        if provenance is not None and provenance.get("unit_id") != unit.unit_id:
            error("PROVENANCE_MISMATCH", "the provenance block names another unit", "/general/notes")
        if summary.get("session_id") != unit.nwb.nwbfile.session_id:
            error("SESSION_ID_MISMATCH", "session_id differs from the manifest", "/session_id")
        planned_subject = unit.nwb.subject.subject_id if unit.nwb.subject else None
        actual_subject = subject.get("subject_id") if subject else None
        if planned_subject != actual_subject:
            error("SUBJECT_ID_MISMATCH",
                  f"subject_id {actual_subject!r} differs from the manifest ({planned_subject!r})")
        if len(summary["epochs"]) != len(unit.nwb.epochs.rows):
            error("EPOCH_COUNT_MISMATCH",
                  f"{len(summary['epochs'])} epochs in the file, {len(unit.nwb.epochs.rows)} planned",
                  "/intervals/epochs")
        if set(summary["devices"]) != {d.name for d in unit.nwb.devices}:
            error("DEVICES_MISMATCH", "the file's devices differ from the manifest", "/general/devices")
        extension = summary.get("brainstem")
        if unit.nwb.brainstem is not None or extension is not None:
            planned = {t.name: [str(r["brainstem_id"]) for r in t.rows]
                       for t in (unit.nwb.brainstem.tables if unit.nwb.brainstem else [])}
            if extension is None:
                error("EXTENSION_MISSING", "the manifest plans ndx-brainstem tables, the file has none",
                      "/general/brainstem")
            elif extension["unit_id"] != unit.unit_id or extension["tables"] != planned:
                error("EXTENSION_MISMATCH", "the ndx-brainstem tables differ from the manifest", "/general/brainstem")
        if unit.output.sha256 and file_sha256(path) != unit.output.sha256:
            error("CHECKSUM_MISMATCH", "the file changed since it was written (sha256 differs from the manifest)")
    return findings
