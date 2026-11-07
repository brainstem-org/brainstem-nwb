"""
Registry of raw-data converters (Phase 4).

Converters are registered by built-in modules and by other packages through the entry point
group ``brainstem_nwb.raw_converters``::

    [project.entry-points."brainstem_nwb.raw_converters"]
    my-format = "my_package.converter:MyConverter"
"""

from __future__ import annotations

from importlib.metadata import entry_points

from .base import RawDataConverter

ENTRY_POINT_GROUP = "brainstem_nwb.raw_converters"

_REGISTERED: dict[str, RawDataConverter] = {}


def register(converter: RawDataConverter) -> RawDataConverter:
    if converter.name in _REGISTERED:
        raise ValueError(f"a raw-data converter named {converter.name!r} is already registered")
    _REGISTERED[converter.name] = converter
    return converter


def available() -> dict[str, RawDataConverter]:
    converters = dict(_REGISTERED)
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        if entry.name not in converters:
            converters[entry.name] = entry.load()()
    return converters


def for_acquisition_type(acquisition_type: str) -> list[RawDataConverter]:
    return [c for _, c in sorted(available().items()) if acquisition_type in c.acquisition_types]
