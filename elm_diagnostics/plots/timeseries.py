"""Time series plots with optional climatology envelope."""

from __future__ import annotations

from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.balances.base import _plot_time
from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.io.subgrid import SubgridLevel


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton spatial dims (lat/lon/lndgrid/gridcell)."""
    for dim in ("lat", "lon", "lndgrid", "gridcell"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def plot_timeseries(
    source: Run | Comparison,
    varname: str,
    *,
    by: SubgridLevel | None = None,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a variable's time series.

    For a Run: single line with optional climatology envelope.
    For a Comparison: base (gray) and experiment (accent) overlaid.

    Parameters
    ----------
    source : Run or Comparison
    varname : str
        Variable name to plot
    by : {"column", "pft", "landunit"}, optional
        Facet plots by sub-gridcell dimension. Creates separate subplot
        for each subgrid unit. Only works with dov2xy=.false. output.
        Cannot be combined with the `ax` parameter.
    config : Config, optional
    ax : matplotlib Axes, optional
        Axes to plot into. Cannot be combined with `by` parameter.

    Returns
    -------
    matplotlib Figure

    Raises
    ------
    ValueError
        If `by` is specified but variable doesn't have that dimension,
        or if dataset uses gridcell-averaged output (dov2xy=.true.),
        or if both `by` and `ax` are specified.

    Examples
    --------
    >>> from elm_diagnostics import Run
    >>> from elm_diagnostics.plots import plot_timeseries
    >>> run = Run("/path/to/output")
    >>> fig = plot_timeseries(run, "GPP")  # Single plot
    >>> fig = plot_timeseries(run, "GPP", by="column")  # Faceted by column
    """
    cfg = config or load_config()

    # Validate ax + by compatibility
    if by is not None and ax is not None:
        raise ValueError(
            "Cannot specify both 'by' and 'ax': faceted plots create "
            "their own figure. Remove 'ax' parameter or set by=None."
        )

    if by is None:
        # Single plot (existing logic)
        return _plot_timeseries_single(source, varname, cfg, ax)
    else:
        # Faceted plot by subgrid dimension
        return _plot_timeseries_faceted(source, varname, by, cfg)


def _plot_timeseries_single(
    source: Run | Comparison,
    varname: str,
    config: Config,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a single timeseries (no faceting)."""
    style = config.plots.style

    if ax is None:
        fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    if isinstance(source, Comparison):
        da_base = _squeeze_spatial(source.base.get(varname))
        da_exp = _squeeze_spatial(source.experiment.get(varname))
        ax.plot(
            _plot_time(da_base),
            da_base.values,
            color="gray",
            label=source.base.name,
            alpha=0.8,
        )
        ax.plot(
            _plot_time(da_exp),
            da_exp.values,
            color="tab:blue",
            label=source.experiment.name,
        )
        ax.legend(loc="best", fontsize="small")
    else:
        da = _squeeze_spatial(source.get(varname))
        ax.plot(_plot_time(da), da.values, color="tab:blue")

        # Climatology envelope if multi-year
        _add_climatology_envelope(da, ax, config.plots.climatology.envelope)

    units = ""
    if isinstance(source, Comparison):
        units = source.base.get(varname).attrs.get("units", "")
    else:
        units = source.get(varname).attrs.get("units", "")

    ax.set_xlabel("Time")
    ax.set_ylabel(units)
    title = varname
    if isinstance(source, Comparison):
        title += f" — {source.base.name} vs {source.experiment.name}"
    elif isinstance(source, Run):
        title += f" — {source.name}"
    ax.set_title(title)
    fig.tight_layout()

    return fig


def _plot_timeseries_faceted(
    source: Run | Comparison,
    varname: str,
    by: SubgridLevel,
    config: Config,
) -> plt.Figure:
    """Plot faceted timeseries by sub-gridcell dimension."""
    from elm_diagnostics.plots.subgrid_helpers import (
        create_facet_figure,
        format_subgrid_title,
        get_subgrid_units,
        validate_variable_for_subgrid,
    )

    # Get data and validate
    if isinstance(source, Comparison):
        da_base = source.base.get(varname)
        da_exp = source.experiment.get(varname)
        # Validate using experiment structure
        validate_variable_for_subgrid(da_exp, by, varname)
    else:
        da = source.get(varname)
        validate_variable_for_subgrid(da, by, varname)

    # Get subgrid units
    if isinstance(source, Comparison):
        units = get_subgrid_units(da_exp, by)
    else:
        units = get_subgrid_units(da, by)

    # Create faceted figure
    fig, axes = create_facet_figure(len(units), config.plots.style)

    # Plot each subgrid unit
    for unit_id, ax_i in zip(units, axes.flat):
        if isinstance(source, Comparison):
            da_base_unit = _squeeze_spatial(da_base.sel({by: unit_id}))
            da_exp_unit = _squeeze_spatial(da_exp.sel({by: unit_id}))

            ax_i.plot(
                _plot_time(da_base_unit),
                da_base_unit.values,
                color="gray",
                label=source.base.name,
                alpha=0.8,
            )
            ax_i.plot(
                _plot_time(da_exp_unit),
                da_exp_unit.values,
                color="tab:blue",
                label=source.experiment.name,
            )
            ax_i.legend(loc="best", fontsize="x-small")

            units_str = da_base.attrs.get("units", "")
        else:
            da_unit = _squeeze_spatial(da.sel({by: unit_id}))
            ax_i.plot(_plot_time(da_unit), da_unit.values, color="tab:blue")

            # Climatology envelope
            _add_climatology_envelope(da_unit, ax_i, config.plots.climatology.envelope)

            units_str = da.attrs.get("units", "")

        # Set labels and title
        ax_i.set_xlabel("Time", fontsize="small")
        ax_i.set_ylabel(units_str, fontsize="small")
        ax_i.set_title(format_subgrid_title(by, unit_id), fontsize="medium")
        ax_i.tick_params(labelsize="small")

    # Hide unused subplots
    for ax_i in axes.flat[len(units):]:
        ax_i.set_visible(False)

    # Overall title
    if isinstance(source, Comparison):
        fig.suptitle(
            f"{varname} by {by} — {source.base.name} vs {source.experiment.name}",
            fontsize="large",
        )
    else:
        fig.suptitle(f"{varname} by {by} — {source.name}", fontsize="large")

    fig.tight_layout()
    return fig


def _add_climatology_envelope(
    da: xr.DataArray,
    ax: plt.Axes,
    method: str,
) -> None:
    """Add a climatology envelope if data spans multiple years."""
    times = da.time.values
    if len(times) < 24:
        return  # Need at least 2 years for meaningful climatology

    # Group by month
    months = da.time.dt.month
    unique_months = np.unique(months.values)
    if len(unique_months) < 12:
        return

    grouped = da.groupby("time.month")

    if method == "minmax":
        lo = grouped.min()
        hi = grouped.max()
    elif method == "p10_p90":
        lo = grouped.quantile(0.1)
        hi = grouped.quantile(0.9)
    elif method == "std":
        mean = grouped.mean()
        std = grouped.std()
        lo = mean - std
        hi = mean + std
    else:
        return

    # Plot envelope as fill between month indices
    month_vals = np.arange(1, 13)
    ax_twin = ax.twinx()
    ax_twin.fill_between(
        month_vals,
        lo.values,
        hi.values,
        alpha=0.15,
        color="tab:blue",
        label=f"Climatology ({method})",
    )
    ax_twin.set_ylabel("")
    ax_twin.set_yticks([])
