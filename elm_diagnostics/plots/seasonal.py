"""Seasonal cycle plots (monthly mean with spread)."""

from __future__ import annotations

from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run


_MONTH_LABELS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    for dim in ("lat", "lon"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def _seasonal_stats(
    da: xr.DataArray,
    envelope: str,
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """Return (mean, lower, upper) grouped by month."""
    grouped = da.groupby("time.month")
    mean = grouped.mean()

    if envelope == "minmax":
        lo = grouped.min()
        hi = grouped.max()
    elif envelope == "p10_p90":
        lo = grouped.quantile(0.1)
        hi = grouped.quantile(0.9)
    elif envelope == "std":
        std = grouped.std()
        lo = mean - std
        hi = mean + std
    else:
        lo = mean
        hi = mean

    return mean, lo, hi


def plot_seasonal(
    source: Run | Comparison,
    varname: str,
    *,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot the seasonal (monthly) cycle of a variable.

    Shows the multi-year monthly mean with a spread envelope.
    For a Comparison, overlays base and experiment.

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
    envelope = cfg.plots.climatology.envelope

    if ax is None:
        fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    months = np.arange(1, 13)

    if isinstance(source, Comparison):
        da_base = _squeeze_spatial(source.base.get(varname))
        da_exp = _squeeze_spatial(source.experiment.get(varname))

        mean_b, lo_b, hi_b = _seasonal_stats(da_base, envelope)
        mean_e, lo_e, hi_e = _seasonal_stats(da_exp, envelope)

        ax.fill_between(months, lo_b.values, hi_b.values,
                        alpha=0.2, color="gray")
        ax.plot(months, mean_b.values, color="gray",
                label=source.base.name, linewidth=2)

        ax.fill_between(months, lo_e.values, hi_e.values,
                        alpha=0.2, color="tab:blue")
        ax.plot(months, mean_e.values, color="tab:blue",
                label=source.experiment.name, linewidth=2)

        ax.legend(loc="best", fontsize="small")
    else:
        da = _squeeze_spatial(source.get(varname))
        mean, lo, hi = _seasonal_stats(da, envelope)

        ax.fill_between(months, lo.values, hi.values,
                        alpha=0.2, color="tab:blue")
        ax.plot(months, mean.values, color="tab:blue", linewidth=2)

    ax.set_xticks(months)
    ax.set_xticklabels(_MONTH_LABELS)
    ax.set_xlabel("Month")

    units = ""
    if isinstance(source, Comparison):
        units = source.base.get(varname).attrs.get("units", "")
    else:
        units = source.get(varname).attrs.get("units", "")
    ax.set_ylabel(units)

    title = f"{varname} — Seasonal Cycle"
    if isinstance(source, Run):
        title += f" — {source.name}"
    ax.set_title(title)
    fig.tight_layout()

    return fig
