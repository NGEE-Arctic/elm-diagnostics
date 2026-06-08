"""Compute derived ELM variables from available history output.

This module provides functions to compute commonly-needed variables that may
not be in the default h0 output, but can be calculated from component variables.

Based on ELM source code analysis (April 2026):
- Total ET from components: QSOIL + QVEGE + QVEGT
- Total storage from vertical profiles: sum(SOILLIQ) + sum(SOILICE) + ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import xarray as xr

if TYPE_CHECKING:
    from elm_diagnostics.io.run import Run


def compute_total_et(run: Run) -> xr.DataArray:
    """Compute total evapotranspiration if QFLX_EVAP_TOT is missing.

    Based on ELM source (SoilFluxesMod.F90, VegetationDataType.F90):
        QFLX_EVAP_TOT = QSOIL + QVEGE + QVEGT

    Where:
        QSOIL = Ground evaporation (soil/snow evap + sublimation - dew)
        QVEGE = Canopy evaporation (evap from leaves and stems)
        QVEGT = Canopy transpiration (stomatal)

    Parameters
    ----------
    run : Run
        Run object containing the necessary component variables.

    Returns
    -------
    xr.DataArray
        Total evapotranspiration in mm/s (or units of components).

    Raises
    ------
    ValueError
        If required component variables are not available.
    """
    required = ["QSOIL", "QVEGE", "QVEGT"]
    missing = [v for v in required if not run.has(v)]
    if missing:
        raise ValueError(
            f"Cannot compute QFLX_EVAP_TOT: missing required variables {missing}. "
            f"Total ET = QSOIL + QVEGE + QVEGT."
        )

    qsoil = run.get("QSOIL")
    qvege = run.get("QVEGE")
    qvegt = run.get("QVEGT")

    et_total = qsoil + qvege + qvegt
    et_total.attrs["long_name"] = "total evapotranspiration (computed)"
    et_total.attrs["units"] = qsoil.attrs.get("units", "mm/s")
    et_total.attrs["description"] = "Computed as QSOIL + QVEGE + QVEGT"
    et_total.name = "QFLX_EVAP_TOT"

    return et_total


def aggregate_vertical_storage(
    run: Run,
    varname: str,
    vertical_dim: str = "levgrnd",
) -> xr.DataArray:
    """Aggregate a vertical profile storage variable to column total.

    For variables like SOILLIQ(time, levgrnd, ...) or SOILICE(time, levgrnd, ...),
    sum over the vertical dimension to get total column storage.

    Parameters
    ----------
    run : Run
        Run object containing the variable.
    varname : str
        Variable name (e.g., "SOILLIQ", "SOILICE").
    vertical_dim : str, optional
        Name of the vertical dimension. Default is "levgrnd".
        Will auto-detect from ["levgrnd", "levsoi", "levdcmp"] if not specified.

    Returns
    -------
    xr.DataArray
        Column-total storage, summed over vertical levels.
    """
    da = run.get(varname)

    # Auto-detect vertical dimension if present
    possible_vdims = ["levgrnd", "levsoi", "levdcmp", "levlak"]
    vdim = None
    for dim in possible_vdims:
        if dim in da.dims:
            vdim = dim
            break

    if vdim is None:
        # No vertical dimension - convert units and return
        if varname in ["SOILLIQ", "SOILICE"]:
            from elm_diagnostics.io.units import convert_water_to_mm

            da = convert_water_to_mm(da)
        return da

    # Sum over vertical dimension
    total = da.sum(dim=vdim, keep_attrs=True)
    total.attrs["long_name"] = f"column total {da.attrs.get('long_name', varname)}"
    total.attrs["aggregation"] = f"sum over {vdim}"

    # Convert water storage to mm for consistency (kg/m² → mm)
    if varname in ["SOILLIQ", "SOILICE"]:
        from elm_diagnostics.io.units import convert_water_to_mm

        total = convert_water_to_mm(total)

    return total


def compute_total_soil_water(run: Run) -> xr.DataArray:
    """Compute total soil water (liquid + ice) column storage.

    Sums SOILLIQ and SOILICE over vertical levels.

    Parameters
    ----------
    run : Run
        Run object.

    Returns
    -------
    xr.DataArray
        Total soil water in kg/m² (or mm, depending on units).
    """
    soilliq = aggregate_vertical_storage(run, "SOILLIQ")
    soilice = aggregate_vertical_storage(run, "SOILICE")

    total = soilliq + soilice
    total.attrs["long_name"] = "total soil water (liquid + ice)"
    total.attrs["units"] = "mm"  # Converted from kg/m² by aggregate_vertical_storage()
    total.name = "TOTAL_SOIL_WATER"

    return total


# Registry of derivable variables
# Maps output variable name to the function that computes it
DERIVABLE_VARS = {
    "QFLX_EVAP_TOT": compute_total_et,
    "TOTAL_SOIL_WATER": compute_total_soil_water,
}


def can_derive(varname: str) -> bool:
    """Check if a variable can be derived from components.

    Parameters
    ----------
    varname : str
        Variable name to check.

    Returns
    -------
    bool
        True if variable can be derived.
    """
    return varname in DERIVABLE_VARS


def derive_variable(run: Run, varname: str) -> xr.DataArray:
    """Derive a variable from available components.

    Parameters
    ----------
    run : Run
        Run object.
    varname : str
        Variable name to derive.

    Returns
    -------
    xr.DataArray
        Derived variable.

    Raises
    ------
    ValueError
        If variable cannot be derived or required components are missing.
    """
    if varname not in DERIVABLE_VARS:
        raise ValueError(
            f"Variable '{varname}' is not in the registry of derivable variables. "
            f"Available: {list(DERIVABLE_VARS.keys())}"
        )

    compute_func = DERIVABLE_VARS[varname]
    return compute_func(run)
