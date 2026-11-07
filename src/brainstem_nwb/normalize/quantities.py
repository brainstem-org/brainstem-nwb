"""
Quantities in BrainSTEM JSON details.

Current schemas store a measured value as ``{"value": 1.5, "unit": "mm"}``. Records saved under
older schema versions may hold a bare number, whose unit is the schema's default and is not in
the export, so it is reported as unknown rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Conversion factors to a base unit, per dimension. Keys are the unit strings BrainSTEM schemas use.
_FACTORS: dict[str, dict[str, float]] = {
    "frequency": {"GHz": 1e9, "MHz": 1e6, "kHz": 1e3, "Hz": 1.0, "mHz": 1e-3},
    "voltage": {"V": 1.0, "mV": 1e-3, "µV": 1e-6, "uV": 1e-6, "μV": 1e-6, "nV": 1e-9},
    "length": {"m": 1.0, "cm": 1e-2, "mm": 1e-3, "µm": 1e-6, "um": 1e-6, "μm": 1e-6, "nm": 1e-9},
    "time": {"h": 3600.0, "min": 60.0, "s": 1.0, "ms": 1e-3, "µs": 1e-6, "us": 1e-6, "μs": 1e-6},
    "power": {"W": 1.0, "mW": 1e-3, "µW": 1e-6, "uW": 1e-6, "μW": 1e-6},
    "mass": {"kg": 1e3, "g": 1.0, "mg": 1e-3, "µg": 1e-6, "ug": 1e-6, "μg": 1e-6},
}
_DIMENSION = {unit: dim for dim, units in _FACTORS.items() for unit in units}


@dataclass(frozen=True)
class Quantity:
    value: float | int | str | None
    unit: str | None
    legacy_bare_number: bool = False

    def text(self) -> str:
        """Value and unit as stored, never converted: ``"1.5 mm"``."""
        if self.value is None:
            return ""
        value = self.value
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{value} {self.unit}".strip() if self.unit else f"{value} (unit not recorded)"


def parse_quantity(raw: Any) -> Quantity | None:
    """Return a Quantity for a ``{value, unit}`` object or a bare number; None for anything else."""
    if isinstance(raw, dict) and "value" in raw:
        value = raw.get("value")
        if value in (None, ""):
            return None
        unit = raw.get("unit")
        return Quantity(value=value, unit=str(unit) if unit not in (None, "") else None)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return Quantity(value=raw, unit=None, legacy_bare_number=True)
    return None


def convert(quantity: Quantity, unit: str) -> float:
    """Convert to ``unit``. Raises ValueError when the unit is missing, unknown or of another dimension."""
    if quantity.unit is None:
        raise ValueError("quantity has no unit")
    if quantity.value is None:
        raise ValueError("quantity has no value")
    source = _normalize_unit(quantity.unit)
    target = _normalize_unit(unit)
    dim_source, dim_target = _DIMENSION.get(source), _DIMENSION.get(target)
    if dim_source is None:
        raise ValueError(f"unknown unit {quantity.unit!r}")
    if dim_source != dim_target:
        raise ValueError(f"cannot convert {quantity.unit!r} to {unit!r}")
    factors = _FACTORS[dim_source]
    return float(quantity.value) * factors[source] / factors[target]


def _normalize_unit(unit: str) -> str:
    return unit.strip()
