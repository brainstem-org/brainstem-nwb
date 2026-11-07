"""
brainstem-nwb: export BrainSTEM experimental metadata to Neurodata Without Borders (NWB) files.

    from brainstem_nwb import export_project

    export_project(project_id="PROJECT_UUID", output_dir="./nwb")
    export_project(export_file="brainstem-export.json.gz", output_dir="./nwb")
"""

from ._version import MAPPING_VERSION, __version__
from .config import ExportOptions
from .errors import AuthRequired, BrainstemNwbError, ConfigError, ExportFormatError, RetrievalError
from .export import ExportResult, build_manifest, export_project, export_session, validate_output
from .retrieval.api import fetch_export
from .retrieval.loader import ProjectExport, load_export

__all__ = [
    "MAPPING_VERSION",
    "AuthRequired",
    "BrainstemNwbError",
    "ConfigError",
    "ExportFormatError",
    "ExportOptions",
    "ExportResult",
    "ProjectExport",
    "RetrievalError",
    "__version__",
    "build_manifest",
    "export_project",
    "export_session",
    "fetch_export",
    "load_export",
    "validate_output",
]
