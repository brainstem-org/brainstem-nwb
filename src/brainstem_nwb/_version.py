"""Version numbers of the package and of the formats it reads and writes."""

__version__ = "0.1.0"

# Bumped whenever a mapping rule changes what is written to an NWB file. It is part of every
# file's identifier, so the same BrainSTEM records exported with a different mapping get a new one.
MAPPING_VERSION = "1.3.0"

# Version of the conversion manifest (brainstem-nwb-manifest.json) and of the validation report.
MANIFEST_SCHEMA_VERSION = "1.0.0"
REPORT_SCHEMA_VERSION = "1.0.0"

# Major version of the BrainSTEM project export format this release reads; newer minors are accepted.
SUPPORTED_EXPORT_MAJOR = 2
KNOWN_EXPORT_MINOR = 1

# Generations of the BrainSTEM data model (``data_model`` in the server's reference manifest) the mapping
# is written for. The data model itself is read from the server at run time.
SUPPORTED_DATA_MODELS = ("specimen-1",)

PACKAGE_URL = "https://github.com/brainstem-org/brainstem-nwb"
