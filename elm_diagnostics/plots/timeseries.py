"""Time series plots with optional climatology envelope."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.balances.base import _plot_time
from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton lat/lon dims."""
    for dim in ("lat", "lon"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def plot_timeseries(
    source: Run | Comparison,
    varname: str,
    *,
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
    config : Config, optional
    ax : matplotlib Axes, optional

    Returns
    -------
    matplotlib Figure
    """
    cfg = config or load_config()
    style = cfg.plots.style

    if ax is None:
        fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    if isinstance(source, Comparison):
        da_base = _squeeze_spatial(source.base.get(varname))
        da_exp = _squeeze_spatial(source.experiment.get(varname))
        ax.plot(_plot_time(da_base), da_base.values, color="gray",
                label=source.base.name, alpha=0.8)
        ax.plot(_plot_time(da_exp), da_exp.values, color="tab:blue",
                label=source.experiment.name)
        ax.legend(loc="best", fontsize="small")
    else:
        da = _squeeze_spatial(source.get(varname))
        ax.plot(_plot_time(da), da.values, color="tab:blue")

        # Climatology envelope if multi-year
        _add_climatology_envelope(da, ax, cfg.plots.climatology.envelope)

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
    ax_twin.fill_between(month_vals, lo.values, hi.values,
                         alpha=0.15, color="tab:blue", label=f"Climatology ({method})")
    ax_twin.set_ylabel("")
    ax_twin.set_yticks([])
