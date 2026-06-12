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


def _append_long_name_line(title: str, da: xr.DataArray | None) -> str:
    if da is None:
        return title
    long_name = str(da.attrs.get("long_name", "")).strip()
    return f"{title}\n{long_name}" if long_name else title


def _is_index_like(values: np.ndarray) -> bool:
    if values.ndim != 1 or values.size == 0:
        return False
    if not np.issubdtype(values.dtype, np.number):
        return False
    idx = np.arange(values.size)
    return np.allclose(values.astype(float), idx.astype(float), rtol=0.0, atol=1e-12)


def _compute_color_limits(
    values: np.ndarray,
    *,
    method: str,
    q_low: float,
    q_high: float,
    sigma_count: float,
) -> tuple[float, float, str] | None:
    """Compute vmin/vmax and colorbar extend using configured method."""
    arr = np.asarray(values, dtype=float).ravel()
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return None

    vmin_full = float(np.min(finite))
    vmax_full = float(np.max(finite))
    if (
        not np.isfinite(vmin_full)
        or not np.isfinite(vmax_full)
        or vmin_full == vmax_full
    ):
        return None

    def _extend_for(vmin: float, vmax: float) -> str:
        eps = 1e-12
        below = vmin > (vmin_full + eps)
        above = vmax < (vmax_full - eps)
        if below and above:
            return "both"
        if below:
            return "min"
        if above:
            return "max"
        return "neither"

    if method == "full_range":
        return vmin_full, vmax_full, "neither"

    if method == "quantile":
        if q_low >= q_high:
            warnings.warn(
                (
                    "plots.hovmuller.color_limit_quantile_low must be less than "
                    "color_limit_quantile_high; using full_range instead."
                ),
                UserWarning,
                stacklevel=3,
            )
            return vmin_full, vmax_full, "neither"
        vmin = float(np.nanpercentile(finite, q_low))
        vmax = float(np.nanpercentile(finite, q_high))
    elif method == "sigma_clip":
        mean = float(np.nanmean(finite))
        std = float(np.nanstd(finite))
        if not np.isfinite(std) or std <= 0.0:
            return vmin_full, vmax_full, "neither"
        vmin = mean - float(sigma_count) * std
        vmax = mean + float(sigma_count) * std
    else:
        warnings.warn(
            f"Unknown plots.hovmuller.color_limit_method='{method}'; using full_range.",
            UserWarning,
            stacklevel=3,
        )
        return vmin_full, vmax_full, "neither"

    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
        warnings.warn(
            (
                f"Unable to compute valid Hovmuller color limits using method '{method}'; "
                "using full_range instead."
            ),
            UserWarning,
            stacklevel=3,
        )
        return vmin_full, vmax_full, "neither"

    return float(vmin), float(vmax), _extend_for(float(vmin), float(vmax))


def _max_depth_mask(
    yvals: np.ndarray,
    *,
    max_depth_m: float | None,
    dim: str,
    is_index_based_axis: bool,
) -> np.ndarray | None:
    """Return a boolean mask for max-depth clipping, or None if not applicable."""
    if max_depth_m is None:
        return None

    if is_index_based_axis:
        warnings.warn(
            (
                f"plots.hovmuller.max_depth_m={max_depth_m} ignored for dimension "
                f"'{dim}' because no coordinate variable was available to convert "
                "indices to physical depth/height."
            ),
            UserWarning,
            stacklevel=3,
        )
        return None

    values = np.asarray(yvals)
    if values.ndim != 1 or not np.issubdtype(values.dtype, np.number):
        warnings.warn(
            (
                f"plots.hovmuller.max_depth_m={max_depth_m} ignored for dimension "
                f"'{dim}' because the axis values are non-numeric."
            ),
            UserWarning,
            stacklevel=3,
        )
        return None

    mask = np.isfinite(values) & (values <= float(max_depth_m))
    if not np.any(mask):
        warnings.warn(
            (
                f"plots.hovmuller.max_depth_m={max_depth_m} selected no levels "
                f"for dimension '{dim}'; using full extent instead."
            ),
            UserWarning,
            stacklevel=3,
        )
        return None

    if np.all(mask):
        return None

    return mask


def _apply_max_depth_limit(
    yvals: np.ndarray,
    field: np.ndarray,
    *,
    mask: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Optionally clip vertical axis and field to a maximum depth/height."""
    if mask is None:
        return yvals, field
    values = np.asarray(yvals)
    return values[mask], field[mask, :]


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
    yvals_raw, axis_label_raw, _, level_units, is_depth_like = resolve_dimension_axis(
        da2, dim
    )
    is_index_based_axis = axis_label_raw == f"{dim} index" or _is_index_like(
        np.asarray(yvals_raw)
    )
    yvals, ylab, is_depth_like = _enforce_depth_convention(
        dim,
        yvals_raw,
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
    mask = _max_depth_mask(
        yvals,
        max_depth_m=config.plots.hovmuller.max_depth_m,
        dim=dim,
        is_index_based_axis=is_index_based_axis,
    )
    yvals, field = _apply_max_depth_limit(
        yvals,
        field,
        mask=mask,
    )

    clim = _compute_color_limits(
        field,
        method=config.plots.hovmuller.color_limit_method,
        q_low=config.plots.hovmuller.color_limit_quantile_low,
        q_high=config.plots.hovmuller.color_limit_quantile_high,
        sigma_count=config.plots.hovmuller.color_limit_sigma,
    )
    mesh_kwargs = {"shading": "auto", "cmap": "viridis"}
    cbar_extend = "neither"
    if clim is not None:
        mesh_kwargs["vmin"] = clim[0]
        mesh_kwargs["vmax"] = clim[1]
        cbar_extend = clim[2]

    mesh = ax.pcolormesh(_plot_time(da2), yvals, field, **mesh_kwargs)
    cbar = fig.colorbar(mesh, ax=ax, extend=cbar_extend)
    units = str(da.attrs.get("units", "")).strip()
    cbar.set_label(units)

    if is_depth_like and np.nanmin(yvals) >= 0.0:
        ax.invert_yaxis()

    ax.set_xlabel("Time")
    ax.set_ylabel(ylab)
    ax.set_title(_append_long_name_line(f"{varname} Hovmuller — {run.name}", da))
    fig.tight_layout()
    return fig


def _plot_hovmuller_comparison(
    source: Comparison,
    varname: str,
    config: Config,
) -> plt.Figure:
    """Plot side-by-side Hovmuller diagrams for a base/experiment comparison."""
    style = config.plots.style
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(style.figsize[0], style.figsize[1] * 1.6),
        dpi=style.dpi,
        sharex=True,
    )

    da_base = squeeze_spatial_dims(source.base.get(varname))
    da_exp = squeeze_spatial_dims(source.experiment.get(varname))
    dim = detect_additional_dimension(da_exp)
    if dim is None:
        raise ValueError(
            f"Variable '{varname}' has no additional dimension for Hovmuller plotting."
        )

    base2 = da_base.transpose("time", dim)
    exp2 = da_exp.transpose("time", dim)
    yvals_raw, axis_label_raw, _, level_units, is_depth_like = resolve_dimension_axis(
        exp2, dim
    )
    is_index_based_axis = axis_label_raw == f"{dim} index" or _is_index_like(
        np.asarray(yvals_raw)
    )
    yvals, ylab, is_depth_like = _enforce_depth_convention(
        dim,
        yvals_raw,
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
    mask = _max_depth_mask(
        yvals,
        max_depth_m=config.plots.hovmuller.max_depth_m,
        dim=dim,
        is_index_based_axis=is_index_based_axis,
    )
    yvals_full = yvals
    yvals, base_field = _apply_max_depth_limit(
        yvals_full,
        base_field,
        mask=mask,
    )
    _, exp_field = _apply_max_depth_limit(
        yvals_full,
        exp_field,
        mask=mask,
    )
    clim = _compute_color_limits(
        np.concatenate([base_field.ravel(), exp_field.ravel()]),
        method=config.plots.hovmuller.color_limit_method,
        q_low=config.plots.hovmuller.color_limit_quantile_low,
        q_high=config.plots.hovmuller.color_limit_quantile_high,
        sigma_count=config.plots.hovmuller.color_limit_sigma,
    )
    mesh_kwargs = {"shading": "auto", "cmap": "viridis"}
    cbar_extend = "neither"
    if clim is not None:
        mesh_kwargs["vmin"] = clim[0]
        mesh_kwargs["vmax"] = clim[1]
        cbar_extend = clim[2]

    mesh_base = axes[0].pcolormesh(_plot_time(base2), yvals, base_field, **mesh_kwargs)
    mesh_exp = axes[1].pcolormesh(_plot_time(exp2), yvals, exp_field, **mesh_kwargs)

    units = str(da_exp.attrs.get("units", "")).strip()
    cbar0 = fig.colorbar(mesh_base, ax=axes[0], extend=cbar_extend)
    cbar1 = fig.colorbar(mesh_exp, ax=axes[1], extend=cbar_extend)
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

    fig.suptitle(
        _append_long_name_line(
            f"{varname} Hovmuller — {source.base.name} vs {source.experiment.name}",
            da_exp,
        )
    )
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
            raise ValueError(
                "Comparison Hovmuller creates its own figure; do not pass ax."
            )
        return _plot_hovmuller_comparison(source, varname, cfg)

    return _plot_hovmuller_run(source, varname, cfg, ax=ax)
