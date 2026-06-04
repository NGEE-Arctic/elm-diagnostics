"""Diurnal cycle plots for sub-daily data."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.io.subgrid import SubgridLevel


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton spatial dims."""
    for dim in ("lat", "lon", "lndgrid", "gridcell"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def _diurnal_stats(
    da: xr.DataArray,
    envelope: str,
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """Return (mean, lower, upper) grouped by hour of day."""
    grouped = da.groupby("time.hour")
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


def plot_diurnal(
    source: Run | Comparison,
    varname: str,
    *,
    by: SubgridLevel | None = None,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot the diurnal (hourly) cycle of a variable.

    Only works with sub-daily data (e.g., h1 tapes with hourly output).
    Shows the multi-day mean diurnal cycle with spread envelope.

    For a Comparison, overlays base and experiment cycles.

    Parameters
    ----------
    source : Run or Comparison
        Data source containing sub-daily output.
    varname : str
        Variable name to plot.
    by : {"column", "pft", "landunit"}, optional
        Facet plots by sub-gridcell dimension. Creates separate subplot
        for each subgrid unit. Only works with dov2xy=.false. output.
        Cannot be combined with the `ax` parameter.
    config : Config, optional
        Configuration object. If None, loads default config.
    ax : matplotlib Axes, optional
        Axes to plot on. If None, creates new figure.
        Cannot be combined with `by` parameter.

    Returns
    -------
    matplotlib Figure

    Raises
    ------
    ValueError
        If data is not sub-daily (less than 24 time steps per day),
        or if `by` is specified but variable doesn't have that dimension,
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
        return _plot_diurnal_single(source, varname, cfg, ax)
    else:
        # Faceted plot by subgrid dimension
        return _plot_diurnal_faceted(source, varname, by, cfg)


def _plot_diurnal_single(
    source: Run | Comparison,
    varname: str,
    config: Config,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a single diurnal cycle (no faceting)."""
    style = config.plots.style
    include_climos = config.plots.climatology.include_climos
    envelope = config.plots.climatology.envelope if include_climos else "none"

    if ax is None:
        fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    # Check if data is sub-daily
    def _check_subdaily(da: xr.DataArray) -> bool:
        """Check if data has sub-daily resolution."""
        if len(da.time) < 24:
            return False
        # Check time resolution - if median delta < 1 day, it's sub-daily
        try:
            time_diffs = np.diff(da.time.values)
            if hasattr(time_diffs[0], "astype"):
                median_hours = np.median(time_diffs).astype(
                    "timedelta64[h]"
                ) / np.timedelta64(1, "h")
            else:
                median_hours = np.median(time_diffs).total_seconds() / 3600
            return median_hours < 24
        except Exception:
            return False

    if isinstance(source, Comparison):
        da_base = _squeeze_spatial(source.base.get(varname))
        da_exp = _squeeze_spatial(source.experiment.get(varname))

        if not _check_subdaily(da_base) or not _check_subdaily(da_exp):
            ax.text(
                0.5,
                0.5,
                "Data is not sub-daily\n(need hourly or finer resolution)",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
            fig.tight_layout()
            return fig

        mean_b, lo_b, hi_b = _diurnal_stats(da_base, envelope)
        mean_e, lo_e, hi_e = _diurnal_stats(da_exp, envelope)

        # Pad to 24 hours if needed
        all_hours_b = np.arange(0, 24)
        all_hours_e = np.arange(0, 24)

        if include_climos:
            ax.fill_between(
                mean_b.hour.values, lo_b.values, hi_b.values, alpha=0.2, color="gray"
            )
        ax.plot(
            mean_b.hour.values,
            mean_b.values,
            color="gray",
            label=source.base.name,
            linewidth=2,
        )

        if include_climos:
            ax.fill_between(
                mean_e.hour.values, lo_e.values, hi_e.values, alpha=0.2, color="tab:blue"
            )
        ax.plot(
            mean_e.hour.values,
            mean_e.values,
            color="tab:blue",
            label=source.experiment.name,
            linewidth=2,
        )

        ax.legend(loc="best", fontsize="small")
    else:
        da = _squeeze_spatial(source.get(varname))

        if not _check_subdaily(da):
            ax.text(
                0.5,
                0.5,
                "Data is not sub-daily\n(need hourly or finer resolution)",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
            fig.tight_layout()
            return fig

        mean, lo, hi = _diurnal_stats(da, envelope)

        if include_climos:
            ax.fill_between(
                mean.hour.values, lo.values, hi.values, alpha=0.2, color="tab:blue"
            )
        ax.plot(mean.hour.values, mean.values, color="tab:blue", linewidth=2)

    ax.set_xticks(np.arange(0, 24, 3))
    ax.set_xlabel("Hour of Day (UTC)")

    units = ""
    if isinstance(source, Comparison):
        units = source.base.get(varname).attrs.get("units", "")
    else:
        units = source.get(varname).attrs.get("units", "")
    ax.set_ylabel(units)

    title = f"{varname} — Diurnal Cycle"
    if isinstance(source, Run):
        title += f" — {source.name}"
    ax.set_title(title)

    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    return fig


def _plot_diurnal_faceted(
    source: Run | Comparison,
    varname: str,
    by: SubgridLevel,
    config: Config,
) -> plt.Figure:
    """Plot faceted diurnal cycles by sub-gridcell dimension."""
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

    # Check if data is sub-daily
    def _check_subdaily(da: xr.DataArray) -> bool:
        """Check if data has sub-daily resolution."""
        if len(da.time) < 24:
            return False
        # Check time resolution - if median delta < 1 day, it's sub-daily
        try:
            time_diffs = np.diff(da.time.values)
            if hasattr(time_diffs[0], "astype"):
                median_hours = np.median(time_diffs).astype(
                    "timedelta64[h]"
                ) / np.timedelta64(1, "h")
            else:
                median_hours = np.median(time_diffs).total_seconds() / 3600
            return median_hours < 24
        except Exception:
            return False

    # Plot each subgrid unit
    for unit_id, ax_i in zip(units, axes.flat):
        if isinstance(source, Comparison):
            da_base_unit = _squeeze_spatial(da_base.sel({by: unit_id}))
            da_exp_unit = _squeeze_spatial(da_exp.sel({by: unit_id}))

            if _check_subdaily(da_base_unit) and _check_subdaily(da_exp_unit):
                mean_b, lo_b, hi_b = _diurnal_stats(da_base_unit, envelope)
                mean_e, lo_e, hi_e = _diurnal_stats(da_exp_unit, envelope)

                if include_climos:
                    ax_i.fill_between(
                        mean_b.hour.values, lo_b.values, hi_b.values, alpha=0.2, color="gray"
                    )
                ax_i.plot(
                    mean_b.hour.values,
                    mean_b.values,
                    color="gray",
                    label=source.base.name,
                    linewidth=2,
                )
                if include_climos:
                    ax_i.fill_between(
                        mean_e.hour.values, lo_e.values, hi_e.values, alpha=0.2, color="tab:blue"
                    )
                ax_i.plot(
                    mean_e.hour.values,
                    mean_e.values,
                    color="tab:blue",
                    label=source.experiment.name,
                    linewidth=2,
                )
                ax_i.legend(loc="best", fontsize="x-small")

            units_str = da_base.attrs.get("units", "")
        else:
            da_unit = _squeeze_spatial(da.sel({by: unit_id}))

            if _check_subdaily(da_unit):
                mean, lo, hi = _diurnal_stats(da_unit, envelope)

                if include_climos:
                    ax_i.fill_between(
                        mean.hour.values, lo.values, hi.values, alpha=0.2, color="tab:blue"
                    )
                ax_i.plot(mean.hour.values, mean.values, color="tab:blue", linewidth=2)

            units_str = da.attrs.get("units", "")

        # Set labels and title
        ax_i.set_xticks(np.arange(0, 24, 6))
        ax_i.set_xlabel("Hour (UTC)", fontsize="small")
        ax_i.set_ylabel(units_str, fontsize="small")
        ax_i.set_title(format_subgrid_title(by, unit_id), fontsize="medium")
        ax_i.tick_params(labelsize="small")
        ax_i.grid(True, alpha=0.3)

    # Hide unused subplots
    for ax_i in axes.flat[len(units) :]:
        ax_i.set_visible(False)

    # Overall title
    if isinstance(source, Comparison):
        fig.suptitle(
            f"{varname} — Diurnal Cycle by {by} — {source.base.name} vs {source.experiment.name}",
            fontsize="large",
        )
    else:
        fig.suptitle(
            f"{varname} — Diurnal Cycle by {by} — {source.name}", fontsize="large"
        )

    fig.tight_layout()
    return fig
