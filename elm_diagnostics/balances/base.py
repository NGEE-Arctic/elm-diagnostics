# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Abstract base class for budget balances."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import cftime
import matplotlib.pyplot as plt
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Run
from elm_diagnostics.io.subgrid import SubgridLevel
from elm_diagnostics.time.calendars import (
    get_available_years,
    select_year,
)


_PLOT_TIME_CACHE: dict[tuple[int, int], list] = {}
_PLOT_TIME_CACHE_MAX = 4096


def _plot_time(da: xr.DataArray):
    """Return time values suitable for matplotlib plotting.

    Converts cftime dates to Python datetime objects since matplotlib
    cannot handle cftime types natively without nc_time_axis.
    """
    time_data = da.coords["time"].data
    # Use (id, length) tuple as cache key to avoid returning wrong-length
    # cached result when object IDs are reused after garbage collection
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


class Balance(ABC):
    """Abstract base for water, carbon, and energy budget balances.

    Subclasses define which YAML config section to read and how to
    assemble the balance equation.
    """

    def __init__(
        self,
        run: Run,
        year: int | None = None,
        by: SubgridLevel | None = None,
        config: Config | str | Path | None = None,
        analysis_year_min: int | None = None,
        analysis_year_max: int | None = None,
    ):
        self.run = run
        self.year = year
        self.by = by
        self.analysis_year_min = analysis_year_min
        self.analysis_year_max = analysis_year_max

        if config is None or isinstance(config, (str, Path)):
            self.config = load_config(config)
        else:
            self.config = config

        self._balance_config = self._get_balance_config()
        self._components_cache: dict[str, xr.DataArray] | None = None
        self._components_cache_key: tuple[Any, ...] | None = None
        self._residual_cache: xr.DataArray | None = None
        self._residual_cache_key: tuple[Any, ...] | None = None

        # Validate sub-gridcell dimension if requested
        if by is not None:
            from elm_diagnostics.io.subgrid import validate_by_keyword

            # Get first stream to check
            first_stream = self.run._open_stream(self.run._tape_order[0])
            validate_by_keyword(first_stream, by)

    @abstractmethod
    def _get_balance_config(self) -> Any:
        """Return the relevant sub-config for this balance type."""

    @property
    def frame(self) -> str:
        return self._balance_config.frame

    def _get_var(self, varname: str) -> xr.DataArray:
        """Retrieve a variable from the run, squeezing spatial singletons.

        Preserves the sub-gridcell dimension specified by self.by if set.
        """
        da = self.run.get(varname)
        # Squeeze singleton spatial dims for single-point data
        # But preserve the sub-gridcell dimension if specified
        for dim in ("lat", "lon", "lndgrid", "gridcell"):
            if dim in da.dims and da.sizes[dim] == 1:
                da = da.squeeze(dim, drop=True)
        return da

    def _select_year(self, ds_or_da):
        """Subset to the requested year or analysis window if set."""
        start_month = self.config.time.water_year_start_month

        # If a specific year is requested, use single-year selection
        if self.year is not None:
            if isinstance(ds_or_da, xr.Dataset):
                return select_year(ds_or_da, self.year, self.frame, start_month)

            # For DataArray: wrap in dataset, select, extract
            tmp = ds_or_da.to_dataset(name="__tmp")
            tmp = select_year(tmp, self.year, self.frame, start_month)
            return tmp["__tmp"]

        # If an analysis window is requested, apply it
        if self.analysis_year_min is not None or self.analysis_year_max is not None:
            # Apply analysis window filtering
            if isinstance(ds_or_da, xr.Dataset):
                ds = ds_or_da
            else:
                ds = ds_or_da.to_dataset(name="__tmp")

            # Extract year values from time coordinate
            if "time" not in ds.dims or len(ds["time"]) == 0:
                if isinstance(ds_or_da, xr.DataArray):
                    return ds_or_da
                return ds

            import numpy as np

            times = ds["time"].values
            years = []
            for t in times:
                if hasattr(t, "year"):
                    years.append(int(t.year))
                else:
                    years.append(int(np.datetime64(t, "Y").astype(int) + 1970))

            # Apply window filter
            min_yr = (
                self.analysis_year_min
                if self.analysis_year_min is not None
                else min(years)
            )
            max_yr = (
                self.analysis_year_max
                if self.analysis_year_max is not None
                else max(years)
            )

            mask = np.array([min_yr <= y <= max_yr for y in years])
            ds = ds.isel(time=mask)

            if isinstance(ds_or_da, xr.DataArray):
                return ds["__tmp"]
            return ds

        # No filtering requested
        return ds_or_da

    def _cache_key(self) -> tuple[Any, ...]:
        """Return a key describing the current balance state."""
        return (
            self.year,
            self.by,
            self.frame,
            self.analysis_year_min,
            self.analysis_year_max,
        )

    @abstractmethod
    def _compute_components(self) -> dict[str, xr.DataArray]:
        """Return unit-normalized, time-aligned balance components."""

    def components(self) -> dict[str, xr.DataArray]:
        """Return cached unit-normalized, time-aligned balance components."""
        key = self._cache_key()
        if self._components_cache is None or self._components_cache_key != key:
            self._components_cache = self._compute_components()
            self._components_cache_key = key
        return self._components_cache

    @abstractmethod
    def _compute_residual(self) -> xr.DataArray:
        """Compute the closure residual."""

    def residual(self) -> xr.DataArray:
        """Return the cached closure residual."""
        key = self._cache_key()
        if self._residual_cache is None or self._residual_cache_key != key:
            self._residual_cache = self._compute_residual()
            self._residual_cache_key = key
        return self._residual_cache

    @abstractmethod
    def plot(self) -> tuple[plt.Figure, ...]:
        """Generate balance plots.

        Returns a tuple of figures for this balance type.
        """

    def to_netcdf(self, path: str | Path) -> None:
        """Save balance components to NetCDF."""
        comps = self.components()
        ds = xr.Dataset(comps)
        ds["residual"] = self.residual()
        ds.to_netcdf(path)

    def plot_all_years(self):
        """Iterate over all available years, yielding plot tuples."""
        # Get a representative dataset for year discovery
        first_var = next(iter(self._get_variable_names()))
        da = self._get_var(first_var)
        ds = da.to_dataset(name=first_var)

        start_month = self.config.time.water_year_start_month
        years = get_available_years(ds, self.frame, start_month)

        for yr in years:
            self.year = yr
            yield self.plot()

    @abstractmethod
    def _get_variable_names(self) -> list[str]:
        """Return all variable names used by this balance."""
