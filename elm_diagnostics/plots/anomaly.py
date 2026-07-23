# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Annual anomaly plots."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.io.subgrid import SubgridLevel


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton spatial dims (lat/lon/lndgrid/gridcell)."""
    for dim in ("lat", "lon", "lndgrid", "gridcell"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def _annual_anomaly(da: xr.DataArray) -> tuple[np.ndarray, np.ndarray]:
    """Compute annual mean anomalies from the long-term mean.

    Returns (years, anomalies).
    """
    annual = da.groupby("time.year").mean()
    annual_values = np.asarray(annual.values)
    long_term_mean = float(np.mean(annual_values))
    anomalies = annual_values - long_term_mean
    years = np.asarray(annual.year.values)
    return years, anomalies


def _format_var_ylabel(varname: str, units: str) -> str:
    units = str(units).strip()
    return f"{varname} ({units})" if units else varname


def _append_long_name_line(title: str, da: xr.DataArray | None) -> str:
    if da is None:
        return title
    long_name = str(da.attrs.get("long_name", "")).strip()
    return f"{title}\n{long_name}" if long_name else title


def plot_anomaly(
    source: Run | Comparison,
    varname: str,
    *,
    by: SubgridLevel | None = None,
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
        return _plot_anomaly_single(source, varname, cfg, ax)
    else:
        # Faceted plot by subgrid dimension
        return _plot_anomaly_faceted(source, varname, by, cfg)


def _plot_anomaly_single(
    source: Run | Comparison,
    varname: str,
    config: Config,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a single anomaly chart (no faceting)."""
    style = config.plots.style

    if ax is None:
        fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    if isinstance(source, Comparison):
        da_base = _squeeze_spatial(source.base.get(varname))
        da_exp = _squeeze_spatial(source.experiment.get(varname))
        title_da = da_exp
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
            ax.set_title(
                _append_long_name_line(
                    f"{varname} — Annual Anomaly (exp - base)", title_da
                )
            )
        else:
            ax.text(
                0.5, 0.5, "No overlapping years", transform=ax.transAxes, ha="center"
            )
    else:
        da = _squeeze_spatial(source.get(varname))
        title_da = da
        years, anomalies = _annual_anomaly(da)
        colors = ["tab:blue" if v >= 0 else "tab:red" for v in anomalies]
        ax.bar(years, anomalies, color=colors, alpha=0.8)

        title = f"{varname} — Annual Anomaly"
        if isinstance(source, Run):
            title += f" — {source.name}"
        ax.set_title(_append_long_name_line(title, title_da))

    units = (
        da_base.attrs.get("units", "")
        if isinstance(source, Comparison)
        else da.attrs.get("units", "")
    )

    ax.set_xlabel("Year")
    ax.set_ylabel(_format_var_ylabel(varname, units))
    ax.axhline(0, color="gray", linewidth=0.5)
    fig.tight_layout()

    return fig


def _plot_anomaly_faceted(
    source: Run | Comparison,
    varname: str,
    by: SubgridLevel,
    config: Config,
) -> plt.Figure:
    """Plot faceted anomaly charts by sub-gridcell dimension."""
    from elm_diagnostics.plots.subgrid_helpers import (
        create_facet_figure,
        format_subgrid_title,
        get_subgrid_units,
        validate_variable_for_subgrid,
    )

    style = config.plots.style

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
    fig, axes = create_facet_figure(len(units), style)

    # Plot each subgrid unit
    for unit_id, ax_i in zip(units, axes.flat):
        if isinstance(source, Comparison):
            da_base_unit = _squeeze_spatial(da_base.sel({by: unit_id}))
            da_exp_unit = _squeeze_spatial(da_exp.sel({by: unit_id}))
            years_b, anom_b = _annual_anomaly(da_base_unit)
            years_e, anom_e = _annual_anomaly(da_exp_unit)

            # Show delta (experiment - base) for overlapping years
            common_years = np.intersect1d(years_b, years_e)
            if len(common_years) > 0:
                mask_b = np.isin(years_b, common_years)
                mask_e = np.isin(years_e, common_years)
                delta = anom_e[mask_e] - anom_b[mask_b]
                colors = ["tab:blue" if v >= 0 else "tab:red" for v in delta]
                ax_i.bar(common_years, delta, color=colors, alpha=0.8)

            units_str = da_base.attrs.get("units", "")
        else:
            da_unit = _squeeze_spatial(da.sel({by: unit_id}))
            years, anomalies = _annual_anomaly(da_unit)
            colors = ["tab:blue" if v >= 0 else "tab:red" for v in anomalies]
            ax_i.bar(years, anomalies, color=colors, alpha=0.8)

            units_str = da.attrs.get("units", "")

        # Set labels and title
        ax_i.set_xlabel("Year", fontsize="small")
        ax_i.set_ylabel(units_str, fontsize="small")
        ax_i.set_title(format_subgrid_title(by, unit_id), fontsize="medium")
        ax_i.tick_params(labelsize="small")
        ax_i.axhline(0, color="gray", linewidth=0.5)

    # Hide unused subplots
    for ax_i in axes.flat[len(units) :]:
        ax_i.set_visible(False)

    # Overall title
    if isinstance(source, Comparison):
        fig.suptitle(
            f"{varname} — Annual Anomaly by {by} — {source.base.name} vs {source.experiment.name}",
            fontsize="large",
        )
    else:
        fig.suptitle(
            f"{varname} — Annual Anomaly by {by} — {source.name}", fontsize="large"
        )

    fig.tight_layout()
    return fig
