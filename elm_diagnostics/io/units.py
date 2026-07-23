# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

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
_KNOWN_STATES = frozenset(
    {
        "SOILLIQ",
        "SOILICE",
        "H2OSNO",
        "H2OCAN",
        "H2OSFC",
        "LEAFC",
        "LIVESTEMC",
        "DEADSTEMC",
        "FROOTC",
        "LIVECROOTC",
        "DEADCROOTC",
        "TOTSOMC",
        "TOTLITC",
        "CWDC",
        "TOTECOSYSC",
        "TOTCOLC",
        "TOTPFTC",
        "TOTVEGC",
        "WOODC",
        "CPOOL",
        "TOTPRODC",
        "SNOWDP",
        "hc_soi",
        "hc_soisno",
    }
)

# Variables known to be intensive (per-unit-area, not integrated over area)
_KNOWN_INTENSIVE = frozenset(
    {
        "TSOI",
        "TSA",
        "TLAI",
        "TSAI",
        "HTOP",
        "HBOT",
        "FPSN",
        "BTRANMN",
    }
)


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
    ('g/m**2', 1.0)
    >>> convert_flux_to_cumulative_units("W/m^2")
    ('J/m**2', 1.0)
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


def convert_water_to_mm(da: xr.DataArray) -> xr.DataArray:
    """Convert water storage variable to mm units.

    Water mass per unit area (kg/m²) and water depth (mm) are numerically
    equivalent for liquid water: 1 kg/m² = 1 mm H2O (assuming density = 1000 kg/m³).

    This function standardizes the units attribute to "mm" without changing values.
    Variables already in mm are returned unchanged.

    Parameters
    ----------
    da : xr.DataArray
        Water storage variable with units in kg/m², mm, or variants.

    Returns
    -------
    xr.DataArray
        Variable with units standardized to "mm". Values are unchanged.

    Raises
    ------
    ValueError
        If units cannot be converted to mm (e.g., temperature, pressure).

    Examples
    --------
    >>> soilliq = xr.DataArray([100.0, 150.0], attrs={"units": "kg/m2"})
    >>> result = convert_water_to_mm(soilliq)
    >>> result.attrs["units"]
    'mm'
    >>> result.values
    array([100., 150.])
    """
    units_str = da.attrs.get("units", "")
    if not units_str:
        raise ValueError("DataArray has no 'units' attribute")

    normalized = normalize_unit_string(units_str)

    # Already in mm - return as-is
    if normalized == "mm":
        return da

    # kg/m² variants → mm (numerically equivalent for water)
    kg_m2_variants = ["kg/m**2", "kg/m^2", "kg/m2"]
    if normalized in kg_m2_variants:
        result = da.copy(deep=False)  # Shallow copy - share data, copy attrs
        result.attrs = dict(da.attrs)
        result.attrs["units"] = "mm"
        return result

    # mm H2O variant → mm
    if normalized == "mm/s":
        raise ValueError(
            f"Cannot convert flux units '{units_str}' to mm. "
            "Use cumulative_integral() to integrate fluxes first."
        )

    # Unknown/incompatible units
    raise ValueError(
        f"Cannot convert units '{units_str}' to mm. "
        f"Expected kg/m² or mm variants, got normalized: '{normalized}'"
    )
