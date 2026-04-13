"""Annual anomaly plots."""

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


def _annual_anomaly(da: xr.DataArray) -> tuple[np.ndarray, np.ndarray]:
    """Compute annual mean anomalies from the long-term mean.

    Returns (years, anomalies).
    """
    annual = da.groupby("time.year").mean()
    long_term_mean = float(annual.mean())
    anomalies = annual.values - long_term_mean
    years = annual.year.values
    return years, anomalies


def plot_anomaly(
    source: Run | Comparison,
    varname: str,
    *,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot annual anomalies of a variable as a bar chart.

    Positive anomalies in blue, negative in red.
    For a Comparison, shows the difference (experiment - base).

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
        years_b, anom_b = _annual_anomaly(da_base)
        years_e, anom_e = _annual_anomaly(da_exp)

        # Show delta (experiment - base) for overlapping years
        common_years = np.intersect1d(years_b, years_e)
        if len(common_years) > 0:
            mask_b = np.isin(years_b, common_years)
            mask_e = np.isin(years_e, common_years)
            delta = anom_e[mask_e] - anom_b[mask_b]
            colors = ["tab:blue" if v >= 0 else "tab:red" for v in delta]
            ax.bar(common_years, delta, color=colors, alpha=0.8)
            ax.set_title(f"{varname} — Annual Anomaly (exp - base)")
        else:
            ax.text(0.5, 0.5, "No overlapping years",
                    transform=ax.transAxes, ha="center")
    else:
        da = _squeeze_spatial(source.get(varname))
        years, anomalies = _annual_anomaly(da)
        colors = ["tab:blue" if v >= 0 else "tab:red" for v in anomalies]
        ax.bar(years, anomalies, color=colors, alpha=0.8)

        title = f"{varname} — Annual Anomaly"
        if isinstance(source, Run):
            title += f" — {source.name}"
        ax.set_title(title)

    units = ""
    if isinstance(source, Comparison):
        units = source.base.get(varname).attrs.get("units", "")
    else:
        units = source.get(varname).attrs.get("units", "")

    ax.set_xlabel("Year")
    ax.set_ylabel(units)
    ax.axhline(0, color="gray", linewidth=0.5)
    fig.tight_layout()

    return fig
