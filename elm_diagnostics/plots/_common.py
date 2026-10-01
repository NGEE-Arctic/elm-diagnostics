# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Labeling, argument-checking, and faceting helpers shared by the plot modules."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D

from elm_diagnostics.config.schema import PlotStyleConfig
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.io.subgrid import SubgridLevel
from elm_diagnostics.plots.dimension_helpers import (
    format_level_label,
    resolve_dimension_axis,
)
from elm_diagnostics.plots.subgrid_helpers import (
    create_facet_figure,
    get_subgrid_units,
    validate_variable_for_subgrid,
)


def format_var_ylabel(varname: str, units: str) -> str:
    """Return ``"VAR (units)"``, or just ``"VAR"`` when units are empty."""
    units = str(units).strip()
    return f"{varname} ({units})" if units else varname


def append_long_name_line(title: str, da: xr.DataArray | None) -> str:
    """Append the variable's ``long_name`` attribute as a second title line."""
    if da is None:
        return title
    long_name = str(da.attrs.get("long_name", "")).strip()
    return f"{title}\n{long_name}" if long_name else title


def legend_level_indices(n_levels: int, max_entries: int = 8) -> set[int]:
    """Choose representative vertical levels for concise legends."""
    if max_entries <= 0:
        return set()
    if n_levels <= max_entries:
        return set(range(n_levels))
    idx = np.linspace(0, n_levels - 1, max_entries).astype(int)
    return set(idx.tolist())


def check_by_ax(by: str | None, ax: plt.Axes | None) -> None:
    """Reject ``by`` together with ``ax``: faceted plots make their own figure."""
    if by is not None and ax is not None:
        raise ValueError(
            "Cannot specify both 'by' and 'ax': faceted plots create "
            "their own figure. Remove 'ax' parameter or set by=None."
        )


def prepare_facets(
    source: Run | Comparison,
    varname: str,
    by: SubgridLevel,
    style: PlotStyleConfig,
) -> tuple[xr.DataArray, xr.DataArray | None, list[int], plt.Figure, np.ndarray]:
    """Load, validate, and lay out a plot faceted by sub-gridcell unit.

    Returns ``(da, da_base, units, fig, axes)``: ``da`` is the Run's data (or
    the Comparison's experiment), ``da_base`` the Comparison's base or None,
    ``units`` the unit ids along ``by``, and one axes per unit (plus spares).
    """
    if isinstance(source, Comparison):
        da_base = source.base.get(varname)
        da = source.experiment.get(varname)
    else:
        da_base = None
        da = source.get(varname)
    validate_variable_for_subgrid(da, by, varname)
    units = get_subgrid_units(da, by)
    fig, axes = create_facet_figure(len(units), style)
    return da, da_base, units, fig, axes


def hide_unused_axes(axes: np.ndarray, n_used: int) -> None:
    """Hide the spare axes a facet grid has beyond the units plotted."""
    for ax in axes.flat[n_used:]:
        ax.set_visible(False)


def plot_level_lines(
    ax: plt.Axes,
    x,
    da: xr.DataArray,
    dim: str,
    along: str,
    *,
    linestyle: str = "-",
    alpha: float = 1.0,
    legend_max_entries: int = 8,
    **line_kw,
) -> None:
    """Draw one line per level of ``dim`` against ``x``, colored along viridis.

    ``along`` is the dimension matching ``x`` (e.g. ``"time"`` or ``"month"``).
    Only a representative subset of levels gets legend labels.
    """
    n_levels = da.sizes[dim]
    level_values, _, level_name, level_units, _ = resolve_dimension_axis(da, dim)
    legend_idx = legend_level_indices(n_levels, max_entries=legend_max_entries)
    cmap = plt.get_cmap("viridis")
    line_values = np.asarray(da.transpose(dim, along).compute())

    for i in range(n_levels):
        line_label = (
            format_level_label(level_values[i], level_name, units=level_units)
            if i in legend_idx
            else "_nolegend_"
        )
        ax.plot(
            x,
            line_values[i, :],
            color=cmap(i / max(n_levels - 1, 1)),
            linestyle=linestyle,
            alpha=alpha,
            label=line_label,
            **line_kw,
        )


def add_level_and_run_legends(
    ax: plt.Axes, level_dim: str, base_name: str, exp_name: str, fontsize: str
) -> None:
    """Two legends for multi-level comparisons: level colors and run linestyles."""
    level_legend = ax.legend(
        loc="upper right", fontsize=fontsize, title=f"{level_dim} levels"
    )
    ax.add_artist(level_legend)
    run_handles = [
        Line2D([0], [0], color="black", linestyle="--", label=base_name),
        Line2D([0], [0], color="black", linestyle="-", label=exp_name),
    ]
    ax.legend(handles=run_handles, loc="upper left", fontsize=fontsize)
