"""Helper functions for faceting plots by sub-gridcell dimensions."""

from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import PlotStyleConfig
from elm_diagnostics.io.subgrid import SubgridLevel

# Warn if creating more than this many facets
_MAX_FACETS_NO_WARNING = 16


def calculate_facet_layout(n_units: int) -> tuple[int, int]:
    """Calculate optimal (nrows, ncols) layout for n subgrid units.

    The layout aims for a roughly square grid, with preference for
    wider-than-tall layouts for better use of screen space.

    Parameters
    ----------
    n_units : int
        Number of sub-gridcell units to plot

    Returns
    -------
    tuple[int, int]
        (nrows, ncols) for subplot layout

    Examples
    --------
    >>> calculate_facet_layout(1)
    (1, 1)
    >>> calculate_facet_layout(3)
    (1, 3)
    >>> calculate_facet_layout(4)
    (2, 2)
    >>> calculate_facet_layout(6)
    (2, 3)
    >>> calculate_facet_layout(9)
    (3, 3)
    """
    if n_units <= 0:
        raise ValueError(f"n_units must be positive, got {n_units}")

    if n_units == 1:
        return (1, 1)
    elif n_units == 2:
        return (1, 2)
    elif n_units == 3:
        return (1, 3)
    elif n_units <= 6:
        # 4, 5, 6 → 2 rows
        return (2, (n_units + 1) // 2)
    elif n_units <= 12:
        # 7-12 → 3 rows
        return (3, (n_units + 2) // 3)
    else:
        # For large numbers, aim for roughly square
        ncols = int(np.ceil(np.sqrt(n_units)))
        nrows = int(np.ceil(n_units / ncols))
        return (nrows, ncols)


def create_facet_figure(
    n_units: int,
    style: PlotStyleConfig,
    sharex: bool = True,
    sharey: bool = True,
) -> tuple[plt.Figure, np.ndarray]:
    """Create figure with subplots for faceting by sub-gridcell units.

    Parameters
    ----------
    n_units : int
        Number of sub-gridcell units to plot
    style : PlotStyleConfig
        Style configuration (figsize, dpi)
    sharex : bool, default True
        Share x-axis across subplots
    sharey : bool, default True
        Share y-axis across subplots

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : numpy.ndarray
        Flattened array of axes (1D), with length ≥ n_units.
        Unused axes (if grid is larger than n_units) should be hidden
        by the caller.

    Warnings
    --------
    Issues a warning if n_units > 16 (large figures may be slow to render
    or difficult to read).
    """
    if n_units > _MAX_FACETS_NO_WARNING:
        warnings.warn(
            f"Creating {n_units} faceted subplots. "
            f"Consider filtering to a subset of units if the figure "
            f"is too large. You can select specific units with "
            f"da.sel({{dimension: [1, 2, 3]}}) before plotting.",
            UserWarning,
            stacklevel=3,
        )

    nrows, ncols = calculate_facet_layout(n_units)

    # Scale figure size based on layout
    # Base figsize is for a single plot; scale proportionally
    base_width, base_height = style.figsize
    fig_width = base_width * ncols / 1.5  # Slightly compressed horizontally
    fig_height = base_height * nrows / 1.5  # Slightly compressed vertically

    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(fig_width, fig_height),
        dpi=style.dpi,
        sharex=sharex,
        sharey=sharey,
        squeeze=False,  # Always return 2D array
    )

    # Flatten axes to 1D for easier iteration
    axes_flat = axes.flatten()

    return fig, axes_flat


def validate_variable_for_subgrid(
    da: xr.DataArray,
    by: SubgridLevel,
    varname: str,
) -> None:
    """Validate that a variable has the requested sub-gridcell dimension.

    Parameters
    ----------
    da : xr.DataArray
        Variable data array
    by : {"column", "pft", "landunit"}
        Requested sub-gridcell dimension
    varname : str
        Variable name (for error message)

    Raises
    ------
    ValueError
        If the variable does not have the requested dimension, or if
        the dimension has size ≤ 1 (making faceting meaningless).
    """
    if by not in da.dims:
        available = [d for d in da.dims if d in ("column", "pft", "landunit")]
        if available:
            raise ValueError(
                f"Variable '{varname}' does not have dimension '{by}'. "
                f"Available sub-gridcell dimensions: {available}. "
                f"Use by='{available[0]}' or select a different variable."
            )
        else:
            raise ValueError(
                f"Variable '{varname}' does not have dimension '{by}'. "
                f"This variable has no sub-gridcell dimensions (column, pft, landunit). "
                f"It may be gridcell-averaged. Remove the 'by' parameter or select "
                f"a variable with sub-gridcell output."
            )

    # Check dimension size
    size = da.sizes[by]
    if size <= 1:
        raise ValueError(
            f"Variable '{varname}' has dimension '{by}' but size is {size}. "
            f"Faceting requires multiple units. Use by=None for single-unit data."
        )


def get_subgrid_units(da: xr.DataArray, by: SubgridLevel) -> list[int]:
    """Extract list of sub-gridcell unit indices from a DataArray.

    Parameters
    ----------
    da : xr.DataArray
        Data array with sub-gridcell dimension
    by : {"column", "pft", "landunit"}
        Sub-gridcell dimension name

    Returns
    -------
    list[int]
        Sorted list of unit indices along the specified dimension
    """
    coords = da.coords[by].values
    return sorted(coords.tolist())


def format_subgrid_title(by: SubgridLevel, unit_id: int) -> str:
    """Format a subplot title for a sub-gridcell unit.

    Parameters
    ----------
    by : {"column", "pft", "landunit"}
        Sub-gridcell level
    unit_id : int
        Unit index/ID

    Returns
    -------
    str
        Formatted title (e.g., "Column 1", "PFT 12", "Landunit 3")

    Examples
    --------
    >>> format_subgrid_title("column", 1)
    'Column 1'
    >>> format_subgrid_title("pft", 12)
    'PFT 12'
    >>> format_subgrid_title("landunit", 3)
    'Landunit 3'
    """
    label = {
        "column": "Column",
        "pft": "PFT",
        "landunit": "Landunit",
    }[by]
    return f"{label} {unit_id}"
