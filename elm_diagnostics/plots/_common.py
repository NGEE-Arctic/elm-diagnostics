# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Small labeling and argument helpers shared by the plot modules."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


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
