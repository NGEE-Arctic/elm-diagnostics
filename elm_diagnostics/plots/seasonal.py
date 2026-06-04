"""Seasonal cycle plots (monthly mean with spread)."""

from __future__ import annotations

from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.io.subgrid import SubgridLevel


_MONTH_LABELS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton spatial dims (lat/lon/lndgrid/gridcell)."""
    for dim in ("lat", "lon", "lndgrid", "gridcell"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def _seasonal_stats(
    da: xr.DataArray,
    envelope: str,
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """Return (mean, lower, upper) grouped by month.

    Returns None values if insufficient data.
    """
    # Need at least 12 months for meaningful seasonal cycle
    if len(da.time) < 12:
        return None, None, None

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
    by: SubgridLevel | None = None,
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
        return _plot_seasonal_single(source, varname, cfg, ax)
    else:
        # Faceted plot by subgrid dimension
        return _plot_seasonal_faceted(source, varname, by, cfg)


def _plot_seasonal_single(
    source: Run | Comparison,
    varname: str,
    config: Config,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a single seasonal cycle (no faceting)."""
    style = config.plots.style
    include_climos = config.plots.climatology.include_climos
    envelope = config.plots.climatology.envelope if include_climos else "none"

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

        # Check if we have sufficient data
        if mean_b is None or mean_e is None:
            ax.text(
                0.5,
                0.5,
                "Insufficient data for seasonal cycle\n(need at least 12 months)",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
            fig.tight_layout()
            return fig

        if include_climos:
            ax.fill_between(months, lo_b.values, hi_b.values, alpha=0.2, color="gray")
        ax.plot(
            months, mean_b.values, color="gray", label=source.base.name, linewidth=2
        )

        if include_climos:
            ax.fill_between(months, lo_e.values, hi_e.values, alpha=0.2, color="tab:blue")
        ax.plot(
            months,
            mean_e.values,
            color="tab:blue",
            label=source.experiment.name,
            linewidth=2,
        )

        ax.legend(loc="best", fontsize="small")
    else:
        da = _squeeze_spatial(source.get(varname))
        mean, lo, hi = _seasonal_stats(da, envelope)

        # Check if we have sufficient data
        if mean is None:
            ax.text(
                0.5,
                0.5,
                "Insufficient data for seasonal cycle\n(need at least 12 months)",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
            fig.tight_layout()
            return fig

        if include_climos:
            ax.fill_between(months, lo.values, hi.values, alpha=0.2, color="tab:blue")
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


def _plot_seasonal_faceted(
    source: Run | Comparison,
    varname: str,
    by: SubgridLevel,
    config: Config,
) -> plt.Figure:
    """Plot faceted seasonal cycle by sub-gridcell dimension."""
    from elm_diagnostics.plots.subgrid_helpers import (
        create_facet_figure,
        format_subgrid_title,
        get_subgrid_units,
        validate_variable_for_subgrid,
    )

    style = config.plots.style
    include_climos = config.plots.climatology.include_climos
    envelope = config.plots.climatology.envelope if include_climos else "none"

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

    months = np.arange(1, 13)

    # Plot each subgrid unit
    for unit_id, ax_i in zip(units, axes.flat):
        if isinstance(source, Comparison):
            da_base_unit = _squeeze_spatial(da_base.sel({by: unit_id}))
            da_exp_unit = _squeeze_spatial(da_exp.sel({by: unit_id}))

            mean_b, lo_b, hi_b = _seasonal_stats(da_base_unit, envelope)
            mean_e, lo_e, hi_e = _seasonal_stats(da_exp_unit, envelope)

            # Check if we have sufficient data
            if mean_b is not None and mean_e is not None:
                if include_climos:
                    ax_i.fill_between(months, lo_b.values, hi_b.values, alpha=0.2, color="gray")
                ax_i.plot(
                    months, mean_b.values, color="gray", label=source.base.name, linewidth=2
                )
                if include_climos:
                    ax_i.fill_between(months, lo_e.values, hi_e.values, alpha=0.2, color="tab:blue")
                ax_i.plot(
                    months,
                    mean_e.values,
                    color="tab:blue",
                    label=source.experiment.name,
                    linewidth=2,
                )
                ax_i.legend(loc="best", fontsize="x-small")

            units_str = da_base.attrs.get("units", "")
        else:
            da_unit = _squeeze_spatial(da.sel({by: unit_id}))
            mean, lo, hi = _seasonal_stats(da_unit, envelope)

            # Check if we have sufficient data
            if mean is not None:
                if include_climos:
                    ax_i.fill_between(months, lo.values, hi.values, alpha=0.2, color="tab:blue")
                ax_i.plot(months, mean.values, color="tab:blue", linewidth=2)

            units_str = da.attrs.get("units", "")

        # Set labels and title
        ax_i.set_xticks(months)
        ax_i.set_xticklabels(_MONTH_LABELS, fontsize="small")
        ax_i.set_xlabel("Month", fontsize="small")
        ax_i.set_ylabel(units_str, fontsize="small")
        ax_i.set_title(format_subgrid_title(by, unit_id), fontsize="medium")
        ax_i.tick_params(labelsize="small")

    # Hide unused subplots
    for ax_i in axes.flat[len(units):]:
        ax_i.set_visible(False)

    # Overall title
    if isinstance(source, Comparison):
        fig.suptitle(
            f"{varname} — Seasonal Cycle by {by} — {source.base.name} vs {source.experiment.name}",
            fontsize="large",
        )
    else:
        fig.suptitle(f"{varname} — Seasonal Cycle by {by} — {source.name}", fontsize="large")

    fig.tight_layout()
    return fig
