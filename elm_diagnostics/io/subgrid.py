# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Sub-gridcell hierarchy detection and helpers."""

from __future__ import annotations

from typing import Literal

import xarray as xr

SubgridLevel = Literal["column", "pft", "landunit"]

# Dimensions that indicate sub-gridcell output (dov2xy = .false.)
_SUBGRID_DIMS = frozenset({"column", "pft", "landunit"})


def detect_subgrid_dims(ds: xr.Dataset) -> set[str]:
    """Return the set of sub-gridcell dimensions present in a dataset.

    If the set is empty, the dataset uses gridcell-averaged output
    (dov2xy = .true.).
    """
    all_dims: set[str] = set()
    for dim in ds.dims:
        if dim in _SUBGRID_DIMS:
            all_dims.add(str(dim))
    return all_dims


def has_subgrid(ds: xr.Dataset) -> bool:
    """Check whether a dataset has sub-gridcell dimensions."""
    return bool(detect_subgrid_dims(ds))


def validate_by_keyword(
    ds: xr.Dataset,
    by: SubgridLevel | None,
) -> None:
    """Validate that the ``by`` keyword is compatible with the dataset.

    Raises
    ------
    ValueError
        If ``by`` is requested but the dataset is gridcell-averaged,
        or if the requested level isn't present.
    """
    if by is None:
        return

    available = detect_subgrid_dims(ds)
    if not available:
        raise ValueError(
            f"Cannot facet by={by!r}: dataset uses gridcell-averaged output "
            "(dov2xy=.true.). Sub-gridcell dimensions are not present."
        )
    if by not in available:
        raise ValueError(
            f"Cannot facet by={by!r}: dimension not found. "
            f"Available sub-gridcell dimensions: {available}"
        )


def get_subgrid_level(da: xr.DataArray) -> SubgridLevel | None:
    """Determine the sub-gridcell level of a DataArray, if any."""
    for dim in da.dims:
        if dim in _SUBGRID_DIMS:
            return dim  # type: ignore[return-value]
    return None
