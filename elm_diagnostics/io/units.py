"""Unit handling for ELM history variables using pint / pint-xarray."""

from __future__ import annotations

from typing import Literal

import pint
import xarray as xr

# ---------------------------------------------------------------------------
# Custom pint registry with ELM-friendly aliases
# ---------------------------------------------------------------------------

_registry = pint.UnitRegistry()

# ELM uses some non-standard unit strings in history files
_UNIT_ALIASES = {
    "mm/s": "mm/s",
    "mm H2O/s": "mm/s",  # 1 mm H2O ≈ 1 kg/m2
    "kg/m2/s": "kg/m**2/s",
    "kg/m^2/s": "kg/m**2/s",
    "W/m2": "W/m**2",
    "W/m^2": "W/m**2",
    "gC/m^2": "g/m**2",
    "gC/m2": "g/m**2",
    "gC/m^2/s": "g/m**2/s",
    "gC/m2/s": "g/m**2/s",
    "gC/m^3": "g/m**3",
    "MJ/m2": "MJ/m**2",
    "MJ/m^2": "MJ/m**2",
    "mol/m2/s": "mol/m**2/s",
    "mol/m^2/s": "mol/m**2/s",
    "m": "m",
    "mm": "mm",
    "K": "K",
    "m/s": "m/s",
    "unitless": "dimensionless",
    "proportion": "dimensionless",
    "m2/m2": "dimensionless",
    "m^2/m^2": "dimensionless",
    "none": "dimensionless",
    "1": "dimensionless",
}

VariableKind = Literal["flux", "state", "intensive"]

# Units that indicate a flux (rate per time)
_FLUX_UNIT_PATTERNS = {"s", "/s", "s-1", "s**-1"}

# Variables known to be states regardless of unit inspection
_KNOWN_STATES = frozenset({
    "SOILLIQ", "SOILICE", "H2OSNO", "H2OCAN", "H2OSFC",
    "LEAFC", "LIVESTEMC", "DEADSTEMC", "FROOTC", "LIVECROOTC", "DEADCROOTC",
    "TOTSOMC", "TOTLITC", "CWDC", "TOTECOSYSC", "TOTCOLC", "TOTPFTC",
    "TOTVEGC", "WOODC", "CPOOL", "TOTPRODC",
    "SNOWDP", "hc_soi", "hc_soisno",
})

# Variables known to be intensive (per-unit-area, not integrated over area)
_KNOWN_INTENSIVE = frozenset({
    "TSOI", "TSA", "TLAI", "TSAI", "HTOP", "HBOT",
    "FPSN", "BTRANMN",
})


def get_registry() -> pint.UnitRegistry:
    """Return the shared pint unit registry."""
    return _registry


def normalize_unit_string(raw: str) -> str:
    """Convert an ELM unit string to a pint-parseable form."""
    raw = raw.strip()
    return _UNIT_ALIASES.get(raw, raw)


def parse_units(raw: str) -> pint.Unit:
    """Parse an ELM unit string into a pint Unit."""
    return _registry.Unit(normalize_unit_string(raw))


def classify_variable(da: xr.DataArray) -> VariableKind:
    """Classify a variable as flux, state, or intensive.

    Uses (in priority order):
    1. Known variable name lists.
    2. ``cell_methods`` attribute (contains ``"time: mean"`` → flux-like).
    3. Unit string inspection (contains ``/s`` → flux).
    """
    name = da.name or ""

    if name in _KNOWN_STATES:
        return "state"
    if name in _KNOWN_INTENSIVE:
        return "intensive"

    # Check cell_methods
    cell_methods = da.attrs.get("cell_methods", "")
    if "time: point" in cell_methods or "time: instantaneous" in cell_methods:
        return "state"

    # Check units for rate indication
    units_str = da.attrs.get("units", "")
    if any(p in units_str for p in _FLUX_UNIT_PATTERNS):
        return "flux"

    if "time: mean" in cell_methods:
        return "flux"

    # Default: assume state if no rate unit found
    return "state"


def convert_flux_to_cumulative_units(
    units_str: str,
) -> tuple[str, float]:
    """Determine the target cumulative units for a flux.

    Returns (target_unit_string, seconds_multiplier).

    Examples
    --------
    >>> convert_flux_to_cumulative_units("mm/s")
    ('mm', 1.0)
    >>> convert_flux_to_cumulative_units("gC/m^2/s")
    ('gC/m^2', 1.0)
    >>> convert_flux_to_cumulative_units("W/m^2")
    ('J/m^2', 1.0)
    """
    norm = normalize_unit_string(units_str)

    # W/m2 -> J/m2 (1 W = 1 J/s)
    if "W" in norm:
        target = norm.replace("W", "J")
        return (target, 1.0)

    # Remove /s to get cumulative unit
    for suffix in ("/s", " s**-1", " s-1"):
        if suffix in norm:
            target = norm.replace(suffix, "")
            return (target.strip(), 1.0)

    # Already cumulative
    return (norm, 1.0)
