"""Seasonal cycle plots (monthly mean with spread)."""

from __future__ import annotations


import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.io.subgrid import SubgridLevel
from elm_diagnostics.plots.climatology import compute_climo_stats
from elm_diagnostics.plots.dimension_helpers import (
    detect_additional_dimension,
    format_level_label,
    resolve_dimension_axis,
    squeeze_spatial_dims,
)


_MONTH_LABELS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def _format_var_ylabel(varname: str, units: str) -> str:
    units = str(units).strip()
    return f"{varname} ({units})" if units else varname


def _append_long_name_line(title: str, da: xr.DataArray | None) -> str:
    if da is None:
        return title
    long_name = str(da.attrs.get("long_name", "")).strip()
    return f"{title}\n{long_name}" if long_name else title


def _legend_level_indices(n_levels: int, max_entries: int = 8) -> set[int]:
    """Choose representative vertical levels for concise legends."""
    if max_entries <= 0:
        return set()
    if n_levels <= max_entries:
        return set(range(n_levels))
    idx = np.linspace(0, n_levels - 1, max_entries).astype(int)
    return set(idx.tolist())


def _plot_multilevel_seasonal_lines(
    ax: plt.Axes,
    months: np.ndarray,
    mean_da: xr.DataArray,
    *,
    linestyle: str = "-",
    alpha: float = 1.0,
    linewidth: float = 2.0,
    legend_max_entries: int = 8,
) -> str | None:
    """Plot one seasonal line per additional-dimension level."""
    dim = detect_additional_dimension(mean_da, excluded_dims=("month",))
    if dim is None:
        return None

    n_levels = mean_da.sizes[dim]
    level_values, _, level_name, level_units, _ = resolve_dimension_axis(mean_da, dim)
    legend_idx = _legend_level_indices(n_levels, max_entries=legend_max_entries)
    cmap = plt.get_cmap("viridis")

    for i in range(n_levels):
        fraction = i / max(n_levels - 1, 1)
        line_label = (
            format_level_label(level_values[i], level_name, units=level_units)
            if i in legend_idx
            else "_nolegend_"
        )
        ax.plot(
            months,
            mean_da.isel({dim: i}).values,
            color=cmap(fraction),
            linestyle=linestyle,
            alpha=alpha,
            linewidth=linewidth,
            label=line_label,
        )

    return dim


def _seasonal_stats(
    da: xr.DataArray,
    envelope: str,
    climo_start_year: int = -1,
    climo_end_year: int = -1,
) -> tuple[xr.DataArray | None, xr.DataArray | None, xr.DataArray | None]:
    """Return (mean, lower, upper) grouped by month.

    Returns None values if insufficient data.
    """
    return compute_climo_stats(
        da,
        groupby="time.month",
        method=envelope,
        climo_start_year=climo_start_year,
        climo_end_year=climo_end_year,
        min_points=12,
        required_groups=12,
    )


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
        da_base = squeeze_spatial_dims(source.base.get(varname))
        da_exp = squeeze_spatial_dims(source.experiment.get(varname))
        title_da = da_exp

        mean_b, lo_b, hi_b = _seasonal_stats(
            da_base,
            envelope,
            config.plots.climatology.climo_start_year,
            config.plots.climatology.climo_end_year,
        )
        mean_e, lo_e, hi_e = _seasonal_stats(
            da_exp,
            envelope,
            config.plots.climatology.climo_start_year,
            config.plots.climatology.climo_end_year,
        )

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

        level_dim = _plot_multilevel_seasonal_lines(
            ax,
            months,
            mean_e,
            linestyle="-",
            alpha=1.0,
            linewidth=2,
        )

        if level_dim is not None:
            _plot_multilevel_seasonal_lines(
                ax,
                months,
                mean_b,
                linestyle="--",
                alpha=0.7,
                linewidth=1.8,
                legend_max_entries=0,
            )
            depth_legend = ax.legend(
                loc="upper right", fontsize="x-small", title=f"{level_dim} levels"
            )
            ax.add_artist(depth_legend)
            run_handles = [
                Line2D([0], [0], color="black", linestyle="--", label=source.base.name),
                Line2D(
                    [0], [0], color="black", linestyle="-", label=source.experiment.name
                ),
            ]
            ax.legend(handles=run_handles, loc="upper left", fontsize="x-small")
        else:
            if include_climos:
                ax.fill_between(
                    months, lo_b.values, hi_b.values, alpha=0.2, color="gray"
                )
            ax.plot(
                months, mean_b.values, color="gray", label=source.base.name, linewidth=2
            )

            if include_climos:
                ax.fill_between(
                    months, lo_e.values, hi_e.values, alpha=0.2, color="tab:blue"
                )
            ax.plot(
                months,
                mean_e.values,
                color="tab:blue",
                label=source.experiment.name,
                linewidth=2,
            )

            ax.legend(loc="best", fontsize="small")
        units = da_base.attrs.get("units", "")
    else:
        da = squeeze_spatial_dims(source.get(varname))
        title_da = da
        mean, lo, hi = _seasonal_stats(
            da,
            envelope,
            config.plots.climatology.climo_start_year,
            config.plots.climatology.climo_end_year,
        )

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

        level_dim = _plot_multilevel_seasonal_lines(ax, months, mean, linewidth=2)
        if level_dim is not None:
            ax.legend(loc="best", fontsize="x-small", title=f"{level_dim} levels")
        else:
            if include_climos:
                ax.fill_between(
                    months, lo.values, hi.values, alpha=0.2, color="tab:blue"
                )
            ax.plot(months, mean.values, color="tab:blue", linewidth=2)
        units = da.attrs.get("units", "")

    ax.set_xticks(months)
    ax.set_xticklabels(_MONTH_LABELS)
    ax.set_xlabel("Month")
    ax.set_ylabel(_format_var_ylabel(varname, units))

    title = f"{varname} — Seasonal Cycle"
    if isinstance(source, Run):
        title += f" — {source.name}"
    ax.set_title(_append_long_name_line(title, title_da))
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
            da_base_unit = squeeze_spatial_dims(da_base.sel({by: unit_id}))
            da_exp_unit = squeeze_spatial_dims(da_exp.sel({by: unit_id}))

            mean_b, lo_b, hi_b = _seasonal_stats(
                da_base_unit,
                envelope,
                config.plots.climatology.climo_start_year,
                config.plots.climatology.climo_end_year,
            )
            mean_e, lo_e, hi_e = _seasonal_stats(
                da_exp_unit,
                envelope,
                config.plots.climatology.climo_start_year,
                config.plots.climatology.climo_end_year,
            )

            # Check if we have sufficient data
            if mean_b is not None and mean_e is not None:
                level_dim = _plot_multilevel_seasonal_lines(
                    ax_i,
                    months,
                    mean_e,
                    linestyle="-",
                    alpha=1.0,
                    linewidth=2,
                )
                if level_dim is not None:
                    _plot_multilevel_seasonal_lines(
                        ax_i,
                        months,
                        mean_b,
                        linestyle="--",
                        alpha=0.7,
                        linewidth=1.8,
                        legend_max_entries=0,
                    )
                    if unit_id == units[0]:
                        depth_legend = ax_i.legend(
                            loc="upper right",
                            fontsize="xx-small",
                            title=f"{level_dim} levels",
                        )
                        ax_i.add_artist(depth_legend)
                        run_handles = [
                            Line2D(
                                [0],
                                [0],
                                color="black",
                                linestyle="--",
                                label=source.base.name,
                            ),
                            Line2D(
                                [0],
                                [0],
                                color="black",
                                linestyle="-",
                                label=source.experiment.name,
                            ),
                        ]
                        ax_i.legend(
                            handles=run_handles, loc="upper left", fontsize="xx-small"
                        )
                else:
                    if include_climos:
                        ax_i.fill_between(
                            months, lo_b.values, hi_b.values, alpha=0.2, color="gray"
                        )
                    ax_i.plot(
                        months,
                        mean_b.values,
                        color="gray",
                        label=source.base.name,
                        linewidth=2,
                    )
                    if include_climos:
                        ax_i.fill_between(
                            months,
                            lo_e.values,
                            hi_e.values,
                            alpha=0.2,
                            color="tab:blue",
                        )
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
            da_unit = squeeze_spatial_dims(da.sel({by: unit_id}))
            mean, lo, hi = _seasonal_stats(
                da_unit,
                envelope,
                config.plots.climatology.climo_start_year,
                config.plots.climatology.climo_end_year,
            )

            # Check if we have sufficient data
            if mean is not None:
                level_dim = _plot_multilevel_seasonal_lines(
                    ax_i,
                    months,
                    mean,
                    linewidth=2,
                )
                if level_dim is not None:
                    if unit_id == units[0]:
                        ax_i.legend(
                            loc="best", fontsize="xx-small", title=f"{level_dim} levels"
                        )
                else:
                    if include_climos:
                        ax_i.fill_between(
                            months, lo.values, hi.values, alpha=0.2, color="tab:blue"
                        )
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
    for ax_i in axes.flat[len(units) :]:
        ax_i.set_visible(False)

    # Overall title
    if isinstance(source, Comparison):
        fig.suptitle(
            f"{varname} — Seasonal Cycle by {by} — {source.base.name} vs {source.experiment.name}",
            fontsize="large",
        )
    else:
        fig.suptitle(
            f"{varname} — Seasonal Cycle by {by} — {source.name}", fontsize="large"
        )

    fig.tight_layout()
    return fig
