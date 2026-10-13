"""Unit handling for 1:1 input values.

Every dimension the user types is interpreted in the currently selected input
unit and stored internally in millimetres at full scale (1:1).
"""

from __future__ import annotations

from dataclasses import dataclass

#: name -> factor to convert a value of that unit into millimetres
UNITS: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}

UNIT_LABELS: dict[str, str] = {
    "mm": "Millimetres (mm)",
    "cm": "Centimetres (cm)",
    "m": "Metres (m)",
    "in": "Inches (in)",
    "ft": "Feet (ft, decimal)",
}


def to_mm(value: float, unit: str) -> float:
    """Convert *value* expressed in *unit* to millimetres."""
    try:
        factor = UNITS[unit]
    except KeyError:
        raise ValueError(f"unknown unit: {unit!r}") from None
    return float(value) * factor


def from_mm(value_mm: float, unit: str) -> float:
    """Convert a millimetre value into *unit*."""
    return float(value_mm) / UNITS[unit]


@dataclass(frozen=True)
class Scale:
    """A modelling scale expressed as 1 : *divider*."""

    divider: float

    def __post_init__(self) -> None:
        if self.divider <= 0:
            raise ValueError("scale divider must be greater than zero")

    @property
    def factor(self) -> float:
        """Multiplier that converts a 1:1 length into scale space."""
        return 1.0 / self.divider

    def apply(self, value_mm: float) -> float:
        """Convert a 1:1 millimetre length into scale-space millimetres."""
        return value_mm * self.factor

    def invert(self, value_mm: float) -> float:
        """Convert a scale-space millimetre length back to 1:1 millimetres."""
        return value_mm * self.divider

    def __str__(self) -> str:
        return f"1:{self.divider:g}"


#: Common railway modelling scales, smallest divider (largest model) first.
SCALE_PRESETS: dict[str, float] = {
    "1:22.5 (G / I)": 22.5,
    "1:32 (1/3.5 / 2mm)": 32.0,
    "1:43.5 (OO)": 43.5,
    "1:48 (O / HO scale)": 48.0,
    "1:64 (S)": 64.0,
    "1:72": 72.0,
    "1:76 (EM)": 76.0,
    "1:87 (HO)": 87.0,
    "1:100": 100.0,
    "1:120 (TT)": 120.0,
    "1:150": 150.0,
    "1:160 (N)": 160.0,
    "1:180 (Z)": 180.0,
    "1:225 (Zm)": 225.0,
}


def parse_scale(text: str) -> Scale:
    """Parse ``"1:87"``, ``"87"`` or ``"1/87"`` into a :class:`Scale`."""
    cleaned = text.strip().replace(" ", "")
    for separator in (":", "/", "1:", "x"):
        if separator in cleaned:
            head, _, tail = cleaned.partition(separator)
            if head in ("1", ""):
                return Scale(float(tail))
    return Scale(float(cleaned))
