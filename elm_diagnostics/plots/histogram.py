"""Histogram / PDF plots for variable distributions."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.io.subgrid import SubgridLevel


def _squeeze_spatial(da: xr.DataArray) -> xr.DataArray:
    """Squeeze singleton spatial dims (lat/lon/lndgrid/gridcell)."""
    # Compute dask arrays before drop=True to avoid KeyError
    if hasattr(da, "chunks") and da.chunks is not None:
        da = da.compute()
    for dim in ("lat", "lon", "lndgrid", "gridcell"):
        if dim in da.dims and da.sizes[dim] == 1:
            da = da.squeeze(dim, drop=True)
    return da


def _flatten_finite_values(da: xr.DataArray) -> np.ndarray:
    """Return finite values as a 1D NumPy array.

    This keeps flattening and NaN filtering in xarray until the final
    materialization step, which is friendlier to chunked arrays than
    immediately calling ``.values.ravel()``.
    """
    # Compute dask arrays before boolean indexing to avoid KeyError
    if hasattr(da, "chunks") and da.chunks is not None:
        da = da.compute()
    stacked = da.stack(sample=da.dims)
    finite = stacked.where(np.isfinite(stacked), drop=True)
    return finite.values


def _append_long_name_line(title: str, da: xr.DataArray | None) -> str:
    if da is None:
        return title
    long_name = str(da.attrs.get("long_name", "")).strip()
    return f"{title}\n{long_name}" if long_name else title


def plot_histogram(
    source: Run | Comparison,
    varname: str,
    *,
    bins: int = 50,
    density: bool = True,
    by: SubgridLevel | None = None,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a histogram of a variable's values over time.

    For a Comparison, overlays base and experiment distributions.

    Parameters
    ----------
    source : Run or Comparison
    varname : str
    bins : int
    density : bool
        If True, plot probability density.
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
        return _plot_histogram_single(source, varname, bins, density, cfg, ax)
    else:
        # Faceted plot by subgrid dimension
        return _plot_histogram_faceted(source, varname, bins, density, by, cfg)


def _plot_histogram_single(
    source: Run | Comparison,
    varname: str,
    bins: int,
    density: bool,
    config: Config,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot a single histogram (no faceting)."""
    style = config.plots.style

    if ax is None:
        fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    if isinstance(source, Comparison):
        da_base = _squeeze_spatial(source.base.get(varname))
        da_exp = _squeeze_spatial(source.experiment.get(varname))
        title_da = da_exp
        vals_b = _flatten_finite_values(da_base)
        vals_e = _flatten_finite_values(da_exp)

        # Shared bins
        all_vals = np.concatenate([vals_b, vals_e])
        bin_edges = np.linspace(np.min(all_vals), np.max(all_vals), bins + 1)

        ax.hist(
            vals_b,
            bins=bin_edges,
            density=density,
            alpha=0.5,
            color="gray",
            label=source.base.name,
        )
        ax.hist(
            vals_e,
            bins=bin_edges,
            density=density,
            alpha=0.5,
            color="tab:blue",
            label=source.experiment.name,
        )
        ax.legend(loc="best", fontsize="small")
        units = da_base.attrs.get("units", "")
    else:
        da = _squeeze_spatial(source.get(varname))
        title_da = da
        vals = _flatten_finite_values(da)
        ax.hist(vals, bins=bins, density=density, alpha=0.7, color="tab:blue")
        units = da.attrs.get("units", "")

    ax.set_xlabel(units)
    ax.set_ylabel("Density" if density else "Count")

    title = f"{varname} — Distribution"
    if isinstance(source, Run):
        title += f" — {source.name}"
    ax.set_title(_append_long_name_line(title, title_da))
    fig.tight_layout()

    return fig


def _plot_histogram_faceted(
    source: Run | Comparison,
    varname: str,
    bins: int,
    density: bool,
    by: SubgridLevel,
    config: Config,
) -> plt.Figure:
    """Plot faceted histograms by sub-gridcell dimension."""
    from elm_diagnostics.plots.subgrid_helpers import (
        create_facet_figure,
        format_subgrid_title,
        get_subgrid_units,
        validate_variable_for_subgrid,
    )

    style = config.plots.style

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

    # Plot each subgrid unit
    for unit_id, ax_i in zip(units, axes.flat):
        if isinstance(source, Comparison):
            vals_b = _flatten_finite_values(
                _squeeze_spatial(da_base.sel({by: unit_id}))
            )
            vals_e = _flatten_finite_values(_squeeze_spatial(da_exp.sel({by: unit_id})))

            # Shared bins
            all_vals = np.concatenate([vals_b, vals_e])
            bin_edges = np.linspace(np.min(all_vals), np.max(all_vals), bins + 1)

            ax_i.hist(
                vals_b,
                bins=bin_edges,
                density=density,
                alpha=0.5,
                color="gray",
                label=source.base.name,
            )
            ax_i.hist(
                vals_e,
                bins=bin_edges,
                density=density,
                alpha=0.5,
                color="tab:blue",
                label=source.experiment.name,
            )
            ax_i.legend(loc="best", fontsize="x-small")

            units_str = da_base.attrs.get("units", "")
        else:
            vals = _flatten_finite_values(_squeeze_spatial(da.sel({by: unit_id})))
            ax_i.hist(vals, bins=bins, density=density, alpha=0.7, color="tab:blue")

            units_str = da.attrs.get("units", "")

        # Set labels and title
        ax_i.set_xlabel(units_str, fontsize="small")
        ax_i.set_ylabel("Density" if density else "Count", fontsize="small")
        ax_i.set_title(format_subgrid_title(by, unit_id), fontsize="medium")
        ax_i.tick_params(labelsize="small")

    # Hide unused subplots
    for ax_i in axes.flat[len(units) :]:
        ax_i.set_visible(False)

    # Overall title
    if isinstance(source, Comparison):
        fig.suptitle(
            f"{varname} — Distribution by {by} — {source.base.name} vs {source.experiment.name}",
            fontsize="large",
        )
    else:
        fig.suptitle(
            f"{varname} — Distribution by {by} — {source.name}", fontsize="large"
        )

    fig.tight_layout()
    return fig
