"""Exceptions raised by brainstem-nwb. Each carries the CLI exit code it maps to."""


class BrainstemNwbError(Exception):
    """Base class for all errors raised by brainstem-nwb."""

    exit_code = 2


class ExportFormatError(BrainstemNwbError):
    """The BrainSTEM export file is unreadable or in an unsupported format version."""

    exit_code = 2


class ConfigError(BrainstemNwbError):
    """Invalid options or configuration file."""

    exit_code = 2


class AuthRequired(BrainstemNwbError):
    """No BrainSTEM token is available and interactive login is not allowed."""

    exit_code = 3


class RetrievalError(BrainstemNwbError):
    """The project export could not be fetched from BrainSTEM."""

    exit_code = 3


class UnitError(BrainstemNwbError):
    """A session (or session x subject unit) cannot be exported; ``code`` names the reason."""

    exit_code = 1

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
