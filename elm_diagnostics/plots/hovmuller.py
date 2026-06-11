"""Hovmuller plots (time x depth colored by variable value)."""

from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.balances.base import _plot_time
from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.plots.dimension_helpers import (
    detect_additional_dimension,
    resolve_dimension_axis,
    squeeze_spatial_dims,
)

_DEPTH_DIMS = {"levgrnd", "levsoi"}


def _enforce_depth_convention(
    dim: str,
    yvals: np.ndarray,
    *,
    units: str,
    is_depth_like: bool,
) -> tuple[np.ndarray, str, bool]:
    """Force levgrnd/levsoi axes to be depth-from-top coordinates.

    For these dimensions, 0 must be at the top and values must increase
    downward whether the source is a physical coordinate or layer indices.
    """
    if dim not in _DEPTH_DIMS:
        label = "Depth" if is_depth_like else dim
        if units:
            label = f"{label} ({units})"
        return yvals, label, is_depth_like

    values = np.asarray(yvals)
    if values.ndim != 1 or not np.issubdtype(values.dtype, np.number):
        values = np.arange(values.size)
    values = values.astype(float, copy=False)

    # Convert negative-down conventions to positive depth, then rebase to zero.
    if np.all(np.isfinite(values)) and np.nanmax(values) <= 0.0:
        values = np.abs(values)
    min_val = float(np.nanmin(values)) if values.size > 0 else 0.0
    values = values - min_val

    label = "Depth"
    if units:
        label = f"{label} ({units})"
    return values, label, True


def _plot_hovmuller_run(
    run: Run,
    varname: str,
    config: Config,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot Hovmuller diagram for a single run."""
    style = config.plots.style
    if ax is None:
        fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    da = squeeze_spatial_dims(run.get(varname))
    dim = detect_additional_dimension(da)
    if dim is None:
        raise ValueError(
            f"Variable '{varname}' has no additional dimension for Hovmuller plotting."
        )

    da2 = da.transpose("time", dim)
    yvals, _, _, level_units, is_depth_like = resolve_dimension_axis(da2, dim)
    yvals, ylab, is_depth_like = _enforce_depth_convention(
        dim,
        yvals,
        units=level_units,
        is_depth_like=is_depth_like,
    )
    if level_units == "" and dim in _DEPTH_DIMS:
        warnings.warn(
            f"No explicit depth units found for dimension '{dim}'; using raw values.",
            UserWarning,
            stacklevel=3,
        )
    elif ylab.endswith(" index"):
        warnings.warn(
            f"No coordinate found for dimension '{dim}'; using index values.",
            UserWarning,
            stacklevel=3,
        )
    field = da2.transpose(dim, "time").values

    mesh = ax.pcolormesh(_plot_time(da2), yvals, field, shading="auto", cmap="viridis")
    cbar = fig.colorbar(mesh, ax=ax)
    units = str(da.attrs.get("units", "")).strip()
    cbar.set_label(units)

    if is_depth_like and np.nanmin(yvals) >= 0.0:
        ax.invert_yaxis()

    ax.set_xlabel("Time")
    ax.set_ylabel(ylab)
    ax.set_title(f"{varname} Hovmuller — {run.name}")
    fig.tight_layout()
    return fig


def _plot_hovmuller_comparison(
    source: Comparison,
    varname: str,
    config: Config,
) -> plt.Figure:
    """Plot side-by-side Hovmuller diagrams for a base/experiment comparison."""
    style = config.plots.style
    fig, axes = plt.subplots(2, 1, figsize=(style.figsize[0], style.figsize[1] * 1.6), dpi=style.dpi, sharex=True)

    da_base = squeeze_spatial_dims(source.base.get(varname))
    da_exp = squeeze_spatial_dims(source.experiment.get(varname))
    dim = detect_additional_dimension(da_exp)
    if dim is None:
        raise ValueError(
            f"Variable '{varname}' has no additional dimension for Hovmuller plotting."
        )

    base2 = da_base.transpose("time", dim)
    exp2 = da_exp.transpose("time", dim)
    yvals, _, _, level_units, is_depth_like = resolve_dimension_axis(exp2, dim)
    yvals, ylab, is_depth_like = _enforce_depth_convention(
        dim,
        yvals,
        units=level_units,
        is_depth_like=is_depth_like,
    )
    if level_units == "" and dim in _DEPTH_DIMS:
        warnings.warn(
            f"No explicit depth units found for dimension '{dim}'; using raw values.",
            UserWarning,
            stacklevel=3,
        )
    elif ylab.endswith(" index"):
        warnings.warn(
            f"No coordinate found for dimension '{dim}'; using index values.",
            UserWarning,
            stacklevel=3,
        )

    base_field = base2.transpose(dim, "time").values
    exp_field = exp2.transpose(dim, "time").values
    vmin = min(float(np.nanmin(base_field)), float(np.nanmin(exp_field)))
    vmax = max(float(np.nanmax(base_field)), float(np.nanmax(exp_field)))

    mesh_base = axes[0].pcolormesh(_plot_time(base2), yvals, base_field, shading="auto", cmap="viridis", vmin=vmin, vmax=vmax)
    mesh_exp = axes[1].pcolormesh(_plot_time(exp2), yvals, exp_field, shading="auto", cmap="viridis", vmin=vmin, vmax=vmax)

    units = str(da_exp.attrs.get("units", "")).strip()
    cbar0 = fig.colorbar(mesh_base, ax=axes[0])
    cbar1 = fig.colorbar(mesh_exp, ax=axes[1])
    cbar0.set_label(units)
    cbar1.set_label(units)

    if is_depth_like and np.nanmin(yvals) >= 0.0:
        axes[0].invert_yaxis()
        axes[1].invert_yaxis()

    axes[0].set_title(source.base.name)
    axes[1].set_title(source.experiment.name)
    axes[0].set_ylabel(ylab)
    axes[1].set_ylabel(ylab)
    axes[1].set_xlabel("Time")

    fig.suptitle(f"{varname} Hovmuller — {source.base.name} vs {source.experiment.name}")
    fig.tight_layout()
    return fig


def plot_hovmuller(
    source: Run | Comparison,
    varname: str,
    *,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a Hovmuller diagram (time x additional dimension)."""
    cfg = config or load_config()

    if isinstance(source, Comparison):
        if ax is not None:
            raise ValueError("Comparison Hovmuller creates its own figure; do not pass ax.")
        return _plot_hovmuller_comparison(source, varname, cfg)

    return _plot_hovmuller_run(source, varname, cfg, ax=ax)
