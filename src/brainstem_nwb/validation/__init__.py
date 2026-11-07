"""Validation of exported NWB files: schema, NWB Inspector, and BrainSTEM semantic checks."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from ..manifest.models import Unit
from .checks import EXPECTED_FINDINGS, run_inspector, run_pynwb_validation, run_semantic_checks
from .report import FileReport, Finding, ValidationReport, render_text


def validate_file(path: Path, *, unit: Unit | None = None, inspector_config: str | None = "dandi",
                  display_path: str | None = None) -> FileReport:
    path = Path(path)
    findings = [*run_pynwb_validation(path)]
    if not any(f.code == "UNREADABLE" for f in findings):
        findings.extend(run_inspector(path, config=inspector_config))
        findings.extend(run_semantic_checks(path, unit))
    return FileReport(path=display_path or path.name, unit_id=unit.unit_id if unit else None, findings=findings)


def tool_versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    from .._version import __version__

    out = {"brainstem-nwb": __version__}
    for package in ("pynwb", "hdmf", "nwbinspector"):
        with suppress(PackageNotFoundError):
            out[package] = version(package)
    return out


__all__ = ["EXPECTED_FINDINGS", "FileReport", "Finding", "ValidationReport", "render_text", "tool_versions",
           "validate_file"]
