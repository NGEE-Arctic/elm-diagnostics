"""Histogram / PDF plots for variable distributions."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    for dim in ("lat", "lon"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def plot_histogram(
    source: Run | Comparison,
    varname: str,
    *,
    bins: int = 50,
    density: bool = True,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a histogram of a variable's values over time.

    For a Comparison, overlays base and experiment distributions.

    Parameters
    ----------
    source : Run or Comparison
    varname : str
    bins : int
    density : bool
        If True, plot probability density.
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
        vals_b = _squeeze_spatial(source.base.get(varname)).values.ravel()
        vals_e = _squeeze_spatial(source.experiment.get(varname)).values.ravel()
        vals_b = vals_b[np.isfinite(vals_b)]
        vals_e = vals_e[np.isfinite(vals_e)]

        # Shared bins
        all_vals = np.concatenate([vals_b, vals_e])
        bin_edges = np.linspace(np.min(all_vals), np.max(all_vals), bins + 1)

        ax.hist(vals_b, bins=bin_edges, density=density, alpha=0.5,
                color="gray", label=source.base.name)
        ax.hist(vals_e, bins=bin_edges, density=density, alpha=0.5,
                color="tab:blue", label=source.experiment.name)
        ax.legend(loc="best", fontsize="small")
    else:
        vals = _squeeze_spatial(source.get(varname)).values.ravel()
        vals = vals[np.isfinite(vals)]
        ax.hist(vals, bins=bins, density=density, alpha=0.7, color="tab:blue")

    units = ""
    if isinstance(source, Comparison):
        units = source.base.get(varname).attrs.get("units", "")
    else:
        units = source.get(varname).attrs.get("units", "")

    ax.set_xlabel(units)
    ax.set_ylabel("Density" if density else "Count")

    title = f"{varname} — Distribution"
    if isinstance(source, Run):
        title += f" — {source.name}"
    ax.set_title(title)
    fig.tight_layout()

    return fig
