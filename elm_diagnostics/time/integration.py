"""Time-bounds-aware cumulative integration for flux variables."""

from __future__ import annotations

import numpy as np
import xarray as xr


def get_time_deltas(ds: xr.Dataset, dim: str = "time") -> xr.DataArray:
    """Compute time step widths (in seconds) from time_bounds.

    This is non-negotiable: we never assume uniform dt. The actual
    time_bounds widths are used for flux integration.

    Parameters
    ----------
    ds : xr.Dataset
        Must contain ``time_bounds`` or ``time_bnds``.
    dim : str
        Name of the time dimension.

    Returns
    -------
    xr.DataArray
        Time deltas in seconds, with the same time coordinate.
    """
    if "time_bounds" in ds:
        bounds_var = "time_bounds"
    elif "time_bnds" in ds:
        bounds_var = "time_bnds"
    else:
        # Fallback: estimate from coordinate diffs
        return _estimate_dt_from_coords(ds, dim)

    bounds = ds[bounds_var]
    # bounds shape: (time, 2)
    dt_raw = bounds.isel({bounds.dims[-1]: 1}) - bounds.isel({bounds.dims[-1]: 0})

    # Convert to seconds
    dt_seconds = _to_seconds(dt_raw, dim)
    return dt_seconds


def _estimate_dt_from_coords(ds: xr.Dataset, dim: str) -> xr.DataArray:
    """Estimate dt from time coordinate differences (fallback)."""
    times = ds[dim]
    n = len(times)
    if n < 2:
        # Single time step: assume 30 days
        dt_vals = np.array([30.0 * 86400.0])
        return xr.DataArray(dt_vals, coords={dim: ds[dim]}, dims=[dim])

    diffs = times.diff(dim)
    last_diff = diffs.isel({dim: -1})
    dt_raw = xr.concat([diffs, last_diff], dim=dim)
    dt_raw = dt_raw.assign_coords({dim: ds[dim]})
    return _to_seconds(dt_raw, dim)


def _scalar_to_seconds(value: object) -> float:
    """Convert one raw time delta value to seconds."""
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    if hasattr(value, "days"):
        return float(value.days * 86400.0 + getattr(value, "seconds", 0))
    if isinstance(value, np.timedelta64):
        return float(value / np.timedelta64(1, "s"))
    if isinstance(value, (int, float, np.integer, np.floating)):
        fv = float(value)
        return fv if fv > 1000 else fv * 86400.0
    return float(value) * 86400.0


def _to_seconds(dt_raw: xr.DataArray, dim: str) -> xr.DataArray:
    """Convert raw time deltas to seconds."""
    seconds = xr.apply_ufunc(
        _scalar_to_seconds,
        dt_raw,
        vectorize=True,
        dask="parallelized",
        output_dtypes=[np.float64],
    )
    coords = {dim: dt_raw[dim]} if dim in dt_raw.dims else {}
    return seconds.assign_coords(coords)


def cumulative_integral(
    da: xr.DataArray,
    ds: xr.Dataset,
    dim: str = "time",
) -> xr.DataArray:
    """Integrate a flux variable cumulatively over time using time_bounds.

    Parameters
    ----------
    da : xr.DataArray
        Flux variable (units with /s, e.g. mm/s, gC/m2/s, W/m2).
    ds : xr.Dataset
        Parent dataset (needed for time_bounds).
    dim : str
        Time dimension name.

    Returns
    -------
    xr.DataArray
        Cumulative integral. For mm/s input, result is in mm.
        For W/m2 input, result is in J/m2.
    """
    dt = get_time_deltas(ds, dim=dim)

    # Broadcast dt to match da's shape
    increments = da * dt
    result = increments.cumsum(dim=dim)

    # Normalize so result[0] = 0: the cumulative integral is relative to
    # the first time step, matching storage_change(S) = S(t) - S(0).
    result = result - result.isel({dim: 0})

    # Update units in attrs
    old_units = da.attrs.get("units", "")
    if "/s" in old_units:
        new_units = old_units.replace("/s", "").strip()
        # Normalize to standard mm for water fluxes (not "mm H2O")
        if "mm" in new_units.lower() or new_units == "mm":
            new_units = "mm"
    elif "W" in old_units:
        new_units = old_units.replace("W", "J")
    else:
        new_units = old_units

    result.attrs = dict(da.attrs)
    result.attrs["units"] = new_units
    result.attrs["long_name"] = f"cumulative {da.attrs.get('long_name', da.name or '')}"

    return result


def storage_change(
    da: xr.DataArray,
    dim: str = "time",
) -> xr.DataArray:
    """Compute dS/dt as a cumulative change from the first time step.

    For state variables: dS(t) = S(t) - S(t=0).

    Parameters
    ----------
    da : xr.DataArray
        State variable (e.g. SOILLIQ in kg/m2).
    dim : str
        Time dimension name.

    Returns
    -------
    xr.DataArray
        S(t) - S(0), same units as input.
    """
    initial = da.isel({dim: 0})
    result = da - initial

    result.attrs = dict(da.attrs)
    result.attrs["long_name"] = f"change in {da.attrs.get('long_name', da.name or '')}"
    return result
