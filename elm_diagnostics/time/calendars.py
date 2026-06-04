"""Water-year and calendar-year reindexing for cftime-aware datasets."""

from __future__ import annotations

import cftime
import numpy as np
import xarray as xr


def _get_month(time_val) -> int:
    """Extract month from a cftime or numpy datetime."""
    if hasattr(time_val, "month"):
        return int(time_val.month)
    return int(np.datetime64(time_val, "M").astype(int) % 12 + 1)


def _get_year(time_val) -> int:
    """Extract year from a cftime or numpy datetime."""
    if hasattr(time_val, "year"):
        return int(time_val.year)
    return int(np.datetime64(time_val, "Y").astype(int) + 1970)


def water_year(time_val, start_month: int = 10) -> int:
    """Compute the water year for a given time value.

    A water year starting in October means that Oct 2014 - Sep 2015
    is water year 2015.
    """
    month = _get_month(time_val)
    year = _get_year(time_val)
    if month >= start_month:
        return year + 1
    return year


def add_water_year_coord(
    ds: xr.Dataset,
    start_month: int = 10,
    dim: str = "time",
) -> xr.Dataset:
    """Add a ``water_year`` coordinate to a dataset.

    Parameters
    ----------
    ds : xr.Dataset
        Dataset with a time dimension.
    start_month : int
        First month of the water year (default 10 = October).
    dim : str
        Name of the time dimension.

    Returns
    -------
    xr.Dataset
        Dataset with an added ``water_year`` coordinate on the time dimension.
    """
    times = ds[dim].values
    wy = np.array([water_year(t, start_month) for t in times])
    return ds.assign_coords(water_year=(dim, wy))


def select_year(
    ds: xr.Dataset,
    year: int,
    frame: str = "calendar",
    start_month: int = 10,
    dim: str = "time",
) -> xr.Dataset:
    """Select a single year from a dataset.

    Parameters
    ----------
    ds : xr.Dataset
    year : int
        The year to select.
    frame : {'calendar', 'water_year'}
        Whether to select by calendar year or water year.
    start_month : int
        Only used when frame='water_year'.
    dim : str
        Name of the time dimension.
    """
    if frame == "water_year":
        if "water_year" not in ds.coords:
            ds = add_water_year_coord(ds, start_month=start_month, dim=dim)
        return ds.where(ds["water_year"] == year, drop=True)

    # Calendar year
    times = ds[dim].values
    mask = np.array([_get_year(t) == year for t in times])
    return ds.isel({dim: mask})


def get_available_years(
    ds: xr.Dataset,
    frame: str = "calendar",
    start_month: int = 10,
    dim: str = "time",
) -> list[int]:
    """Return sorted list of complete years available in the dataset."""
    times = ds[dim].values

    if frame == "water_year":
        years = sorted({water_year(t, start_month) for t in times})
    else:
        years = sorted({_get_year(t) for t in times})

    return years


def subset_climo_years(
    da: xr.DataArray,
    climo_start_year: int,
    climo_end_year: int,
    dim: str = "time",
) -> xr.DataArray:
    """Subset a DataArray to a climatology year window.

    Uses ``-1`` as a sentinel for earliest/latest available year.
    """
    if dim not in da.dims or len(da[dim]) == 0:
        return da

    times = da[dim].values
    years = np.array([_get_year(t) for t in times], dtype=int)
    if len(years) == 0:
        return da

    min_year = int(np.min(years))
    max_year = int(np.max(years))

    start_year = min_year if climo_start_year == -1 else climo_start_year
    end_year = max_year if climo_end_year == -1 else climo_end_year

    if start_year > end_year:
        return da.isel({dim: slice(0, 0)})

    mask = (years >= start_year) & (years <= end_year)
    return da.isel({dim: mask})


def day_of_year(time_val, start_month: int = 1) -> int:
    """Compute day-of-year, optionally offset by start_month.

    For water-year-relative DOY, pass start_month=10.
    """
    month = _get_month(time_val)
    year = _get_year(time_val)

    if hasattr(time_val, "dayofyr"):
        abs_doy = time_val.dayofyr
    elif hasattr(time_val, "timetuple"):
        abs_doy = time_val.timetuple().tm_yday
    else:
        abs_doy = (
            np.datetime64(time_val, "D") - np.datetime64(f"{year}-01-01", "D")
        ).astype(int) + 1

    if start_month == 1:
        return abs_doy

    # Offset for non-January start
    if hasattr(time_val, "calendar"):
        cal = time_val.calendar
    else:
        cal = "standard"

    try:
        year_start = cftime.datetime(
            year if month >= start_month else year - 1, start_month, 1, calendar=cal
        )
        if hasattr(time_val, "toordinal"):
            delta = time_val.toordinal() - year_start.toordinal()
        else:
            delta = abs_doy  # fallback
    except Exception:
        delta = abs_doy

    return max(1, delta + 1)
