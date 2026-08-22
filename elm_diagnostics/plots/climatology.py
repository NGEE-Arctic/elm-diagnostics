# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Shared climatology helpers for plot modules."""

from __future__ import annotations

from typing import Literal

import numpy as np
import xarray as xr

from elm_diagnostics.time.calendars import _get_year, subset_climo_years


def compute_climo_stats(
    da: xr.DataArray,
    *,
    groupby: Literal["time.month", "time.hour"],
    method: str,
    climo_start_year: int = -1,
    climo_end_year: int = -1,
    min_points: int = 1,
    required_groups: int | None = None,
) -> tuple[xr.DataArray | None, xr.DataArray | None, xr.DataArray | None]:
    """Return (mean, lower, upper) climatology statistics.

    Returns ``(None, None, None)`` if there is not enough data after
    year-window filtering.
    """
    da = subset_climo_years(da, climo_start_year, climo_end_year)

    if len(da.time) < min_points:
        return None, None, None

    if groupby == "time.month" and method not in {"minmax", "p10_p90", "std"}:
        # For mean-only climatology, monthly pre-aggregation shrinks the problem
        # size and avoids expensive grouping over high-frequency raw samples.
        monthly = da.resample(time="MS").mean()
        if len(monthly.time) < min_points:
            return None, None, None
        mean = monthly.groupby("time.month").mean()
        if required_groups is not None and mean.size < required_groups:
            return None, None, None
        return mean, mean, mean

    grouped = da.groupby(groupby)
    mean = grouped.mean()

    if required_groups is not None and mean.size < required_groups:
        return None, None, None

    if method == "minmax":
        lo = grouped.min()
        hi = grouped.max()
    elif method == "p10_p90":
        lo = grouped.quantile(0.1)
        hi = grouped.quantile(0.9)
    elif method == "std":
        std = grouped.std()
        lo = mean - std
        hi = mean + std
    else:
        lo = mean
        hi = mean

    return mean, lo, hi


def compute_individual_year_seasonal_cycles(
    da: xr.DataArray,
    climo_start_year: int = -1,
    climo_end_year: int = -1,
) -> tuple[list[int], list[xr.DataArray]]:
    """Return individual year seasonal cycles as (years, seasonal_arrays).

    Each seasonal array in the returned list has shape (12,) for the month
    dimension, representing the monthly means for that specific year.
    Additional dimensions (e.g., levgrnd) are preserved.

    Parameters
    ----------
    da : xr.DataArray
        Input data with a time dimension.
    climo_start_year : int, optional
        Start year for filtering (-1 = earliest available).
    climo_end_year : int, optional
        End year for filtering (-1 = latest available).

    Returns
    -------
    years : list[int]
        Sorted list of years present in the filtered data.
    seasonal_arrays : list[xr.DataArray]
        One DataArray per year with monthly means (grouped by time.month).
        Each has shape (12,) for month dimension plus any additional dimensions.
    """
    # Filter to requested year range
    da = subset_climo_years(da, climo_start_year, climo_end_year)

    if len(da.time) == 0:
        return [], []

    # Extract unique years
    times = da.time.values
    years = sorted({_get_year(t) for t in times})

    # Compute seasonal cycle for each year
    seasonal_arrays = []
    for year in years:
        # Select data for this year
        year_mask = np.array([_get_year(t) == year for t in times])
        da_year = da.isel(time=year_mask)

        if len(da_year.time) == 0:
            continue

        # Compute monthly means for this year
        monthly_mean = da_year.groupby("time.month").mean().compute()

        seasonal_arrays.append(monthly_mean)

    return years, seasonal_arrays
