"""Validation report: findings per file from pynwb, NWB Inspector and BrainSTEM-specific checks."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .._version import REPORT_SCHEMA_VERSION
from ..manifest.models import Severity

REPORT_JSON = "validation-report.json"
REPORT_TEXT = "validation-report.txt"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    origin: Literal["pynwb", "nwbinspector", "brainstem"]
    code: str
    message: str
    location: str | None = None
    importance: str | None = None  # NWB Inspector importance, as reported
    expected: bool = False
    expected_reason: str | None = None


class FileReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    unit_id: str | None = None
    findings: list[Finding] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        counter = Counter(f.severity for f in self.findings)
        return {key: counter.get(key, 0) for key in ("error", "warning", "info")}


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_schema_version: str = REPORT_SCHEMA_VERSION
    tool_versions: dict[str, str] = Field(default_factory=dict)
    inspector_config: str | None = None
    summary: dict[str, int] = Field(default_factory=dict)
    files: list[FileReport] = Field(default_factory=list)

    def finalize(self) -> ValidationReport:
        totals: Counter[str] = Counter()
        for file in self.files:
            totals.update(file.counts())
        self.summary = {"files": len(self.files), **{key: totals.get(key, 0) for key in ("error", "warning", "info")}}
        return self

    def has(self, severity: Severity) -> bool:
        return any(f.severity == severity for file in self.files for f in file.findings)


def render_text(report: ValidationReport) -> str:
    lines = [f"brainstem-nwb validation report (schema {report.report_schema_version})"]
    if report.tool_versions:
        lines.append("Tools: " + ", ".join(f"{k} {v}" for k, v in sorted(report.tool_versions.items())))
    if report.inspector_config:
        lines.append(f"NWB Inspector configuration: {report.inspector_config}")
    lines.append("")
    order = {"error": 0, "warning": 1, "info": 2}
    for file in report.files:
        counts = file.counts()
        lines.append(f"{file.path}: {counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info")
        for finding in sorted(file.findings, key=lambda f: (order[f.severity], f.origin, f.code)):
            where = f" at {finding.location}" if finding.location else ""
            expected = f" [expected: {finding.expected_reason}]" if finding.expected else ""
            label = f"{finding.severity.upper():7} {finding.origin}:{finding.code}"
            lines.append(f"  {label}{where}: {finding.message}{expected}")
        lines.append("")
    summary = report.summary
    lines.append(f"Total: {summary.get('files', 0)} file(s), {summary.get('error', 0)} error(s), "
                 f"{summary.get('warning', 0)} warning(s), {summary.get('info', 0)} info")
    return "\n".join(lines) + "\n"
