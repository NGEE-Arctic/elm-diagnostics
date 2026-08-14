# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Shared helpers for detecting and labeling additional plotting dimensions."""

from __future__ import annotations

import warnings

import numpy as np
import xarray as xr

_SPACE_DIMS = ("lat", "lon", "lndgrid", "gridcell")


def squeeze_spatial_dims(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton spatial dims (lat/lon/lndgrid/gridcell)."""
    for dim in _SPACE_DIMS:
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def detect_additional_dimension(
    da: xr.DataArray,
    *,
    excluded_dims: tuple[str, ...] = (),
) -> str | None:
    """Pick an expandable extra dimension beyond time and spatial dims."""
    excluded = {"time", *excluded_dims, *_SPACE_DIMS}
    candidates = [dim for dim in da.dims if dim not in excluded and da.sizes[dim] > 1]
    if not candidates:
        return None
    if len(candidates) > 1:
        warnings.warn(
            f"Multiple additional dimensions {candidates}; using '{candidates[0]}'.",
            UserWarning,
            stacklevel=3,
        )
    return candidates[0]


def _is_index_like(values: np.ndarray) -> bool:
    if values.ndim != 1 or values.size == 0:
        return False
    if not np.issubdtype(values.dtype, np.number):
        return False
    idx = np.arange(values.size)
    return np.allclose(values.astype(float), idx.astype(float), rtol=0.0, atol=1e-12)


def _coord_score(name: str, coord: xr.DataArray, dim: str) -> int:
    """Score coordinate candidates; higher score means better plotting axis."""
    score = 0
    values = np.asarray(coord.values)
    lower_name = name.lower()

    if name != dim:
        score += 2
    if not _is_index_like(values):
        score += 3

    attrs = coord.attrs
    if attrs.get("units"):
        score += 1
    if attrs.get("positive") in ("up", "down"):
        score += 1
    if attrs.get("long_name") or attrs.get("standard_name"):
        score += 1

    if any(tok in lower_name for tok in ("depth", "height", "layer", "z")):
        score += 1

    return score


def _coord_candidates_from_dataarray(
    da: xr.DataArray, dim: str
) -> list[tuple[str, xr.DataArray]]:
    candidates: list[tuple[str, xr.DataArray]] = []
    for cname, coord in da.coords.items():
        if coord.dims == (dim,) and coord.size == da.sizes[dim]:
            candidates.append((cname, coord))
    return candidates


def resolve_dimension_axis(
    da: xr.DataArray,
    dim: str,
) -> tuple[np.ndarray, str, str, str, bool]:
    """Resolve axis values/labels for an additional dimension.

    Returns
    -------
    values : np.ndarray
    axis_label : str
    level_name : str
    level_units : str
    is_depth_like : bool
    """
    candidates = _coord_candidates_from_dataarray(da, dim)

    if not candidates:
        return np.arange(da.sizes[dim]), f"{dim} index", dim, "", False

    best_name, best_coord = max(
        candidates,
        key=lambda item: _coord_score(item[0], item[1], dim),
    )

    values = np.asarray(best_coord.values)
    attrs = best_coord.attrs
    units = str(attrs.get("units", "")).strip()
    positive = str(attrs.get("positive", "")).lower().strip()
    long_name = str(attrs.get("long_name", attrs.get("standard_name", ""))).strip()

    long_name_lower = long_name.lower()
    is_depth_like = (
        positive in ("up", "down")
        or "depth" in best_name.lower()
        or "depth" in long_name_lower
        or best_name.lower().startswith("z")
    )

    if (
        is_depth_like
        and positive != "up"
        and values.ndim == 1
        and np.all(np.isfinite(values))
        and np.nanmax(values) <= 0.0
    ):
        values = np.abs(values)

    if positive == "up":
        axis_label = long_name or "Height"
    elif is_depth_like:
        axis_label = long_name or "Depth"
    else:
        axis_label = long_name or best_name

    if units:
        axis_label = f"{axis_label} ({units})"

    return values, axis_label, best_name, units, is_depth_like


def format_level_label(level_value: object, level_name: str, units: str = "") -> str:
    """Format legend label for one coordinate level."""
    suffix = f" {units}" if units else ""
    try:
        numeric = float(level_value)
        if np.isfinite(numeric):
            return f"{level_name}={numeric:.3g}{suffix}"
    except (TypeError, ValueError):
        pass
    return f"{level_name}={level_value}{suffix}"


def apply_max_levels(
    da: xr.DataArray,
    dim: str,
    max_levels: int | None,
) -> xr.DataArray:
    """Apply max_levels filter to vertical dimension.

    Parameters
    ----------
    da : xr.DataArray
        Data with vertical dimension
    dim : str
        Name of vertical dimension (e.g., 'levgrnd')
    max_levels : int | None
        Maximum number of levels to keep from top (index 0).
        If None, returns data unchanged.

    Returns
    -------
    xr.DataArray
        Data masked to first max_levels along dim, or unchanged if
        max_levels is None or dimension not present.

    Notes
    -----
    Assumes level 0 is at top (surface). Works with both indexed
    dimensions and physical coordinate dimensions.
    """
    if max_levels is None or dim not in da.dims:
        return da

    n_levels = da.sizes[dim]
    if n_levels <= max_levels:
        return da  # Already within limit

    # Select first max_levels (0:max_levels)
    return da.isel({dim: slice(0, max_levels)})
