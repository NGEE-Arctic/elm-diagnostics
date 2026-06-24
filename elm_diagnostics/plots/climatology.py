"""Shared climatology helpers for plot modules."""

from __future__ import annotations

from typing import Literal

import xarray as xr

from elm_diagnostics.time.calendars import subset_climo_years


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
