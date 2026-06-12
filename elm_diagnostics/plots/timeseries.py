"""Time series plots with optional climatology envelope."""

from __future__ import annotations


import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D

from elm_diagnostics.balances.base import _plot_time
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


def _legend_level_indices(n_levels: int, max_entries: int = 8) -> set[int]:
    """Choose representative vertical levels for concise legends."""
    if n_levels <= max_entries:
        return set(range(n_levels))
    idx = np.linspace(0, n_levels - 1, max_entries).astype(int)
    return set(idx.tolist())


def _format_var_ylabel(varname: str, units: str) -> str:
    units = str(units).strip()
    return f"{varname} ({units})" if units else varname


def _append_long_name_line(title: str, da: xr.DataArray | None) -> str:
    if da is None:
        return title
    long_name = str(da.attrs.get("long_name", "")).strip()
    return f"{title}\n{long_name}" if long_name else title


def _plot_multilevel_lines(
    ax: plt.Axes,
    da: xr.DataArray,
    *,
    linestyle: str = "-",
    alpha: float = 1.0,
    legend_max_entries: int = 8,
) -> str | None:
    """Plot one line per additional-dimension level with colormap progression.

    Returns
    -------
    str or None
        Name of the expanded dimension if multi-level plotting was used,
        otherwise None.
    """
    dim = detect_additional_dimension(da)
    if dim is None:
        return None

    n_levels = da.sizes[dim]
    level_values, _, level_name, level_units, _ = resolve_dimension_axis(da, dim)
    legend_idx = _legend_level_indices(n_levels, max_entries=legend_max_entries)
    cmap = plt.get_cmap("viridis")
    time_values = _plot_time(da)
    line_values = np.asarray(da.transpose(dim, "time").values)

    for i in range(n_levels):
        fraction = i / max(n_levels - 1, 1)
        line_label = (
            format_level_label(level_values[i], level_name, units=level_units)
            if i in legend_idx
            else "_nolegend_"
        )
        ax.plot(
            time_values,
            line_values[i, :],
            color=cmap(fraction),
            linestyle=linestyle,
            alpha=alpha,
            label=line_label,
        )

    return dim


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
    >>> run = Run("/path/to/output")  # doctest: +SKIP
    >>> fig = plot_timeseries(run, "GPP")  # doctest: +SKIP
    >>> fig = plot_timeseries(run, "GPP", by="column")  # doctest: +SKIP
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
        da_base = squeeze_spatial_dims(source.base.get(varname))
        da_exp = squeeze_spatial_dims(source.experiment.get(varname))
        title_da = da_exp
        level_dim = _plot_multilevel_lines(ax, da_exp, linestyle="-", alpha=1.0)
        if level_dim is not None:
            # Overlay base as dashed lines with same depth colormap.
            _plot_multilevel_lines(
                ax,
                da_base,
                linestyle="--",
                alpha=0.7,
                legend_max_entries=0,
            )
            depth_legend = ax.legend(
                loc="upper right",
                fontsize="x-small",
                title=f"{level_dim} levels",
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
        units = da_base.attrs.get("units", "")
    else:
        da = squeeze_spatial_dims(source.get(varname))
        title_da = da
        level_dim = _plot_multilevel_lines(ax, da)
        if level_dim is not None:
            ax.legend(loc="best", fontsize="x-small", title=f"{level_dim} levels")
        else:
            ax.plot(_plot_time(da), da.values, color="tab:blue")

            # Climatology envelope if multi-year
            _add_climatology_envelope(
                da,
                ax,
                config.plots.climatology.envelope,
                include_climos=config.plots.climatology.include_climos,
                climo_start_year=config.plots.climatology.climo_start_year,
                climo_end_year=config.plots.climatology.climo_end_year,
            )
        units = da.attrs.get("units", "")

    ax.set_xlabel("Time")
    ax.set_ylabel(_format_var_ylabel(varname, units))
    title = varname
    if isinstance(source, Comparison):
        title += f" — {source.base.name} vs {source.experiment.name}"
    elif isinstance(source, Run):
        title += f" — {source.name}"
    ax.set_title(_append_long_name_line(title, title_da))
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
            da_base_unit = squeeze_spatial_dims(da_base.sel({by: unit_id}))
            da_exp_unit = squeeze_spatial_dims(da_exp.sel({by: unit_id}))

            level_dim = _plot_multilevel_lines(
                ax_i,
                da_exp_unit,
                linestyle="-",
                alpha=1.0,
            )
            if level_dim is not None:
                _plot_multilevel_lines(
                    ax_i,
                    da_base_unit,
                    linestyle="--",
                    alpha=0.7,
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
            da_unit = squeeze_spatial_dims(da.sel({by: unit_id}))
            level_dim = _plot_multilevel_lines(ax_i, da_unit)
            if level_dim is not None and unit_id == units[0]:
                ax_i.legend(
                    loc="best", fontsize="xx-small", title=f"{level_dim} levels"
                )
            if level_dim is None:
                ax_i.plot(_plot_time(da_unit), da_unit.values, color="tab:blue")

                # Climatology envelope
                _add_climatology_envelope(
                    da_unit,
                    ax_i,
                    config.plots.climatology.envelope,
                    include_climos=config.plots.climatology.include_climos,
                    climo_start_year=config.plots.climatology.climo_start_year,
                    climo_end_year=config.plots.climatology.climo_end_year,
                )

            units_str = da.attrs.get("units", "")

        # Set labels and title
        ax_i.set_xlabel("Time", fontsize="small")
        ax_i.set_ylabel(units_str, fontsize="small")
        ax_i.set_title(format_subgrid_title(by, unit_id), fontsize="medium")
        ax_i.tick_params(labelsize="small")

    # Hide unused subplots
    for ax_i in axes.flat[len(units) :]:
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
    include_climos: bool = True,
    climo_start_year: int = -1,
    climo_end_year: int = -1,
) -> None:
    """Add a climatology envelope if data spans multiple years."""
    if not include_climos:
        return

    _, lo, hi = compute_climo_stats(
        da,
        groupby="time.month",
        method=method,
        climo_start_year=climo_start_year,
        climo_end_year=climo_end_year,
        min_points=24,
        required_groups=12,
    )

    if lo is None or hi is None:
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
