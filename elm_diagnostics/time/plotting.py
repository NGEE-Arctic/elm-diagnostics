# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.


"""Time-axis values for matplotlib."""

from __future__ import annotations

import cftime
import numpy as np
import xarray as xr

_PLOT_TIME_CACHE: dict[tuple[int, int], list] = {}
_PLOT_TIME_CACHE_MAX = 4096


def plot_times(da: xr.DataArray) -> list | np.ndarray:
    """Return ``da``'s time values in a form matplotlib can plot.

    cftime dates are converted to ``datetime.datetime`` (matplotlib cannot plot
    cftime without nc_time_axis); other time values are returned unchanged.
    """
    time_data = da.coords["time"].data
    # NOTE: keyed on id() without holding a reference, so a recycled id can
    # return another array's dates (bug B19 in REFACTOR_NOTES.md).
    cache_key = (id(time_data), len(time_data))
    cached = _PLOT_TIME_CACHE.get(cache_key)
    if cached is not None:
        return cached

    times = da.time.values
    if len(times) > 0 and isinstance(times[0], cftime.datetime):
        converted = [t._to_real_datetime() for t in times]
        if len(_PLOT_TIME_CACHE) >= _PLOT_TIME_CACHE_MAX:
            _PLOT_TIME_CACHE.clear()
        _PLOT_TIME_CACHE[cache_key] = converted
        return converted
    return times
