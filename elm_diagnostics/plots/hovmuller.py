"""Hovmuller plots (time x depth colored by variable value)."""

from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.balances.base import _plot_time
from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run

_VERTICAL_DIMS = ("levgrnd", "levsoi", "levdcmp", "levlak", "levsno")
_VERTICAL_COORD_ALIASES = {
    "levgrnd": ("zsoi", "z_soi", "ZSoi", "depth", "depth_soil"),
    "levsoi": ("zsoi", "z_soi", "depth", "depth_soil"),
    "levdcmp": ("zsoi", "depth", "depth_soil"),
    "levlak": ("zlak", "z_lake", "depth_lake", "depth"),
    "levsno": ("zsno", "z_sno", "depth_snow", "depth"),
}


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton spatial dims (lat/lon/lndgrid/gridcell)."""
    for dim in ("lat", "lon", "lndgrid", "gridcell"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def _get_vertical_dim(da: xr.DataArray) -> str | None:
    """Return the first recognized vertical dimension in a data array."""
    for dim in _VERTICAL_DIMS:
        if dim in da.dims and da.sizes[dim] > 1:
            return dim
    return None


def _try_coord_from_dataarray(da: xr.DataArray, vdim: str) -> xr.DataArray | None:
    """Return the best depth coordinate directly available on DataArray coords."""
    for cname, coord in da.coords.items():
        if cname == vdim:
            continue
        if coord.dims == (vdim,) and coord.size == da.sizes[vdim]:
            return coord

    for alias in _VERTICAL_COORD_ALIASES.get(vdim, ()):  # alias lookup
        if alias in da.coords:
            coord = da.coords[alias]
            if coord.dims == (vdim,) and coord.size == da.sizes[vdim]:
                return coord

    return None


def _try_coord_from_run(run: Run, vdim: str) -> xr.DataArray | None:
    """Search opened run streams for depth coordinate variables on vdim."""
    for stream in run.streams.values():
        for alias in _VERTICAL_COORD_ALIASES.get(vdim, ()):  # alias lookup
            if alias not in stream:
                continue
            coord = stream[alias]
            if coord.dims == (vdim,) and coord.size > 1:
                return coord
    return None


def _to_plot_depth_values(coord: xr.DataArray) -> tuple[np.ndarray, str]:
    """Return plottable depth values and axis label from a coordinate array."""
    values = np.asarray(coord.values)
    units = str(coord.attrs.get("units", "")).strip()
    positive = str(coord.attrs.get("positive", "")).lower().strip()

    # Convert negative-down depth coordinates to positive depth for readability.
    if values.ndim == 1 and np.all(np.isfinite(values)) and np.nanmax(values) <= 0.0:
        values = np.abs(values)

    label = "Depth"
    if positive == "up":
        label = "Height"
    if units:
        label = f"{label} ({units})"

    return values, label


def _resolve_vertical_axis(run: Run, da: xr.DataArray, vdim: str) -> tuple[np.ndarray, str, bool]:
    """Resolve depth axis values, favoring physical coordinates over indices."""
    coord = _try_coord_from_dataarray(da, vdim)
    if coord is None:
        coord = _try_coord_from_run(run, vdim)

    if coord is not None:
        values, label = _to_plot_depth_values(coord)
        return values, label, False

    warnings.warn(
        f"No vertical coordinate found for dimension '{vdim}'; using layer indices.",
        UserWarning,
        stacklevel=3,
    )
    return np.arange(da.sizes[vdim]), f"{vdim} index", True


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

    da = _squeeze_spatial(run.get(varname))
    vdim = _get_vertical_dim(da)
    if vdim is None:
        raise ValueError(f"Variable '{varname}' has no vertical dimension for Hovmuller plotting.")

    da2 = da.transpose("time", vdim)
    yvals, ylab, _ = _resolve_vertical_axis(run, da2, vdim)
    field = da2.transpose(vdim, "time").values

    mesh = ax.pcolormesh(_plot_time(da2), yvals, field, shading="auto", cmap="viridis")
    cbar = fig.colorbar(mesh, ax=ax)
    units = str(da.attrs.get("units", "")).strip()
    cbar.set_label(units)

    if np.nanmin(yvals) >= 0.0:
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

    da_base = _squeeze_spatial(source.base.get(varname))
    da_exp = _squeeze_spatial(source.experiment.get(varname))
    vdim = _get_vertical_dim(da_exp)
    if vdim is None:
        raise ValueError(f"Variable '{varname}' has no vertical dimension for Hovmuller plotting.")

    base2 = da_base.transpose("time", vdim)
    exp2 = da_exp.transpose("time", vdim)
    yvals, ylab, _ = _resolve_vertical_axis(source.experiment, exp2, vdim)

    base_field = base2.transpose(vdim, "time").values
    exp_field = exp2.transpose(vdim, "time").values
    vmin = min(float(np.nanmin(base_field)), float(np.nanmin(exp_field)))
    vmax = max(float(np.nanmax(base_field)), float(np.nanmax(exp_field)))

    mesh_base = axes[0].pcolormesh(_plot_time(base2), yvals, base_field, shading="auto", cmap="viridis", vmin=vmin, vmax=vmax)
    mesh_exp = axes[1].pcolormesh(_plot_time(exp2), yvals, exp_field, shading="auto", cmap="viridis", vmin=vmin, vmax=vmax)

    units = str(da_exp.attrs.get("units", "")).strip()
    cbar0 = fig.colorbar(mesh_base, ax=axes[0])
    cbar1 = fig.colorbar(mesh_exp, ax=axes[1])
    cbar0.set_label(units)
    cbar1.set_label(units)

    if np.nanmin(yvals) >= 0.0:
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
    """Plot a Hovmuller diagram (time x depth) for vertically resolved data."""
    cfg = config or load_config()

    if isinstance(source, Comparison):
        if ax is not None:
            raise ValueError("Comparison Hovmuller creates its own figure; do not pass ax.")
        return _plot_hovmuller_comparison(source, varname, cfg)

    return _plot_hovmuller_run(source, varname, cfg, ax=ax)
