# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Spatial map plotting for multi-gridcell ELM output."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    HAS_CARTOPY = True
except ImportError:
    HAS_CARTOPY = False

try:
    import geopandas as gpd

    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False


SpatialFormat = Literal["latlon", "lndgrid", "single_point"]
TimeAgg = Literal["mean", "median", "sum", "std", "min", "max"]


def detect_spatial_format(da: xr.DataArray) -> SpatialFormat:
    """Detect spatial dimension format in dataset.

    Parameters
    ----------
    da : xr.DataArray
        Data array to check for spatial dimensions

    Returns
    -------
    SpatialFormat
        One of "latlon" (structured grid), "lndgrid" (unstructured),
        or "single_point" (no spatial variation)
    """
    if "lat" in da.dims and "lon" in da.dims:
        if da.sizes["lat"] > 1 or da.sizes["lon"] > 1:
            return "latlon"
    if "lndgrid" in da.dims and da.sizes["lndgrid"] > 1:
        return "lndgrid"
    return "single_point"


def _check_cartopy_available() -> None:
    """Raise ImportError if cartopy not available."""
    if not HAS_CARTOPY:
        raise ImportError(
            "Spatial plotting requires cartopy. "
            "Install with: pip install 'elm-diagnostics[maps]'"
        )


def _apply_time_aggregation(
    da: xr.DataArray, method: TimeAgg | int
) -> xr.DataArray:
    """Apply time aggregation to reduce data to single spatial map.

    Parameters
    ----------
    da : xr.DataArray
        Input data with time dimension
    method : TimeAgg or int
        Aggregation method ("mean", "median", "sum", "std", "min", "max")
        or integer index for specific timestep

    Returns
    -------
    xr.DataArray
        Aggregated data with time dimension removed
    """
    if isinstance(method, int):
        if method < 0 or method >= da.sizes.get("time", 0):
            raise ValueError(
                f"Time index {method} out of range [0, {da.sizes.get('time', 0)})"
            )
        return da.isel(time=method)

    if "time" not in da.dims:
        return da

    agg_func = getattr(da, method, None)
    if agg_func is None:
        raise ValueError(
            f"Unknown aggregation method '{method}'. "
            f"Use one of: mean, median, sum, std, min, max, or integer index"
        )

    return agg_func(dim="time")


def _load_domain_coords(run: Run, domain_file: Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Load lndgrid coordinates from ELM domain file.

    Parameters
    ----------
    run : Run
        Run object to search for domain file
    domain_file : Path, optional
        Explicit path to domain file. If None, auto-detects in run directory.

    Returns
    -------
    lon : np.ndarray
        Longitude values (degrees east)
    lat : np.ndarray
        Latitude values (degrees north)

    Raises
    ------
    FileNotFoundError
        If domain file cannot be found and lndgrid > 1
    """
    # Check if already cached
    if hasattr(run, "_domain_coords"):
        return run._domain_coords

    # Try explicit path first
    if domain_file is not None:
        if not domain_file.exists():
            raise FileNotFoundError(f"Domain file not found: {domain_file}")
        ds = xr.open_dataset(domain_file)
        lon = np.asarray(ds["xc"].values)
        lat = np.asarray(ds["yc"].values)
        run._domain_coords = (lon, lat)
        return lon, lat

    # Auto-detect in run directory
    run_path = Path(run.path)
    domain_files = list(run_path.glob("domain.lnd.*.nc"))

    if not domain_files:
        raise FileNotFoundError(
            f"No domain file (domain.lnd.*.nc) found in {run_path}. "
            "Multi-cell lndgrid data requires domain file with xc/yc coordinates. "
            "Provide via domain_file parameter or place domain.lnd.*.nc in run directory."
        )

    # Use first match
    ds = xr.open_dataset(domain_files[0])
    if "xc" not in ds or "yc" not in ds:
        raise ValueError(
            f"Domain file {domain_files[0]} missing 'xc' or 'yc' coordinates"
        )

    lon = np.asarray(ds["xc"].values)
    lat = np.asarray(ds["yc"].values)

    # Cache for future calls
    run._domain_coords = (lon, lat)
    return lon, lat


def _load_watershed_boundary(
    boundary_path: Path | str,
) -> gpd.GeoDataFrame | None:
    """Load watershed boundary from file.

    Parameters
    ----------
    boundary_path : Path or str
        Path to GeoJSON, shapefile, or other geopandas-readable format

    Returns
    -------
    gpd.GeoDataFrame or None
        Boundary geometry, or None if geopandas not available
    """
    if not HAS_GEOPANDAS:
        import warnings

        warnings.warn(
            "geopandas not installed; watershed boundary will not be plotted. "
            "Install with: pip install geopandas",
            UserWarning,
            stacklevel=3,
        )
        return None

    return gpd.read_file(boundary_path)


def plot_map(
    run: Run,
    varname: str,
    *,
    time_agg: TimeAgg | int = "mean",
    projection: str | None = None,
    watershed_boundary: Path | str | None = None,
    domain_file: Path | None = None,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    config: Config | None = None,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """Plot spatial map of a variable.

    Parameters
    ----------
    run : Run
        ELM run with multi-gridcell output
    varname : str
        Variable name to plot
    time_agg : TimeAgg or int, default="mean"
        Time aggregation method ("mean", "median", "sum", "std", "min", "max")
        or integer index for specific timestep
    projection : str, optional
        Cartopy projection name (e.g., "PlateCarree", "Orthographic").
        If None, uses PlateCarree for lat/lon grids, None for lndgrid scatter.
    watershed_boundary : Path or str, optional
        Path to watershed boundary file (GeoJSON, shapefile)
    domain_file : Path, optional
        Path to ELM domain file for lndgrid coordinates. Auto-detected if None.
    cmap : str, default="viridis"
        Matplotlib colormap name
    vmin, vmax : float, optional
        Colorbar range limits
    config : Config, optional
        Plot configuration
    ax : matplotlib Axes, optional
        Axes to plot into. Must have GeoAxes projection if provided.

    Returns
    -------
    matplotlib Figure

    Raises
    ------
    ValueError
        If data is single-point (no spatial variation)
    ImportError
        If cartopy not installed

    Examples
    --------
    >>> from elm_diagnostics import Run
    >>> from elm_diagnostics.plots import plot_map
    >>> run = Run("/path/to/watershed/output")  # doctest: +SKIP
    >>> fig = plot_map(run, "GPP", time_agg="mean")  # doctest: +SKIP
    >>> fig = plot_map(run, "QOVER", time_agg=0, projection="Orthographic")  # doctest: +SKIP
    """
    _check_cartopy_available()
    cfg = config or load_config()
    style = cfg.plots.style

    # Load and check data
    da = run.get(varname)
    spatial_format = detect_spatial_format(da)

    if spatial_format == "single_point":
        raise ValueError(
            f"Variable '{varname}' has no spatial variation (single point). "
            "Spatial maps require multi-gridcell data."
        )

    # Apply time aggregation
    da_agg = _apply_time_aggregation(da, time_agg)

    # Load watershed boundary if provided
    boundary = None
    if watershed_boundary is not None:
        boundary = _load_watershed_boundary(watershed_boundary)

    # Create figure and axes if not provided
    if ax is None:
        if projection is None:
            projection = "PlateCarree" if spatial_format == "latlon" else None

        if projection is not None:
            proj_class = getattr(ccrs, projection, None)
            if proj_class is None:
                raise ValueError(f"Unknown cartopy projection: {projection}")
            proj = proj_class()
            fig, ax = plt.subplots(
                figsize=style.figsize,
                dpi=style.dpi,
                subplot_kw={"projection": proj},
            )
        else:
            fig, ax = plt.subplots(figsize=style.figsize, dpi=style.dpi)
    else:
        fig = ax.figure

    # Plot based on spatial format
    if spatial_format == "latlon":
        _plot_latlon_map(
            ax, da_agg, cmap=cmap, vmin=vmin, vmax=vmax, boundary=boundary
        )
    else:  # lndgrid
        lon, lat = _load_domain_coords(run, domain_file)
        _plot_lndgrid_map(
            ax, da_agg, lon, lat, cmap=cmap, vmin=vmin, vmax=vmax, boundary=boundary
        )

    # Set title
    units = da.attrs.get("units", "")
    long_name = da.attrs.get("long_name", "")
    title = f"{varname}"
    if isinstance(time_agg, int):
        title += f" (timestep {time_agg})"
    else:
        title += f" ({time_agg})"
    title += f" — {run.name}"
    if long_name:
        title += f"\n{long_name}"
    if units:
        title += f" ({units})"

    ax.set_title(title)
    fig.tight_layout()

    return fig


def _plot_latlon_map(
    ax: plt.Axes,
    da: xr.DataArray,
    cmap: str,
    vmin: float | None,
    vmax: float | None,
    boundary: gpd.GeoDataFrame | None,
) -> None:
    """Plot structured lat/lon grid using pcolormesh."""
    # Extract lat/lon coordinates
    lat = da.coords["lat"].values
    lon = da.coords["lon"].values
    values = da.values

    # Handle 1D lat/lon (need meshgrid for pcolormesh)
    if lat.ndim == 1 and lon.ndim == 1:
        lon_2d, lat_2d = np.meshgrid(lon, lat)
    else:
        lon_2d, lat_2d = lon, lat

    # Mask NaNs
    values_masked = np.ma.masked_invalid(values)

    # Plot using pcolormesh
    im = ax.pcolormesh(
        lon_2d,
        lat_2d,
        values_masked,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        transform=ccrs.PlateCarree(),
        shading="auto",
    )

    # Add colorbar
    plt.colorbar(im, ax=ax, orientation="horizontal", pad=0.05, shrink=0.8)

    # Add coastlines and borders
    ax.coastlines(resolution="50m", linewidth=0.5)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle=":")

    # Add watershed boundary if provided
    if boundary is not None:
        boundary.boundary.plot(
            ax=ax, transform=ccrs.PlateCarree(), color="black", linewidth=1.5
        )

    # Set extent to data bounds
    lon_min, lon_max = lon_2d.min(), lon_2d.max()
    lat_min, lat_max = lat_2d.min(), lat_2d.max()
    margin = 0.1  # 10% margin
    lon_margin = (lon_max - lon_min) * margin
    lat_margin = (lat_max - lat_min) * margin
    ax.set_extent(
        [
            lon_min - lon_margin,
            lon_max + lon_margin,
            lat_min - lat_margin,
            lat_max + lat_margin,
        ],
        crs=ccrs.PlateCarree(),
    )


def _plot_lndgrid_map(
    ax: plt.Axes,
    da: xr.DataArray,
    lon: np.ndarray,
    lat: np.ndarray,
    cmap: str,
    vmin: float | None,
    vmax: float | None,
    boundary: gpd.GeoDataFrame | None,
) -> None:
    """Plot unstructured lndgrid using scatter or tricontourf."""
    values = da.values

    # Mask NaNs
    valid = np.isfinite(values)
    lon_valid = lon[valid]
    lat_valid = lat[valid]
    values_valid = values[valid]

    # Use tricontourf for smooth interpolated field
    try:
        im = ax.tricontourf(
            lon_valid,
            lat_valid,
            values_valid,
            levels=15,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            transform=ccrs.PlateCarree() if hasattr(ax, "projection") else None,
        )
    except Exception:
        # Fallback to scatter if tricontourf fails
        im = ax.scatter(
            lon_valid,
            lat_valid,
            c=values_valid,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            s=50,
            transform=ccrs.PlateCarree() if hasattr(ax, "projection") else None,
        )

    # Add colorbar
    plt.colorbar(im, ax=ax, orientation="horizontal", pad=0.05, shrink=0.8)

    # Add coastlines if GeoAxes
    if hasattr(ax, "coastlines"):
        ax.coastlines(resolution="50m", linewidth=0.5)
        ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle=":")

    # Add watershed boundary if provided
    if boundary is not None and hasattr(ax, "projection"):
        boundary.boundary.plot(
            ax=ax, transform=ccrs.PlateCarree(), color="black", linewidth=1.5
        )

    # Set extent to data bounds
    lon_min, lon_max = lon_valid.min(), lon_valid.max()
    lat_min, lat_max = lat_valid.min(), lat_valid.max()
    margin = 0.1
    lon_margin = (lon_max - lon_min) * margin
    lat_margin = (lat_max - lat_min) * margin

    if hasattr(ax, "set_extent"):
        ax.set_extent(
            [
                lon_min - lon_margin,
                lon_max + lon_margin,
                lat_min - lat_margin,
                lat_max + lat_margin,
            ],
            crs=ccrs.PlateCarree(),
        )
    else:
        ax.set_xlim(lon_min - lon_margin, lon_max + lon_margin)
        ax.set_ylim(lat_min - lat_margin, lat_max + lat_margin)


def plot_map_comparison(
    comparison: Comparison,
    varname: str,
    *,
    time_agg: TimeAgg | int = "mean",
    projection: str | None = None,
    watershed_boundary: Path | str | None = None,
    domain_file: Path | None = None,
    cmap: str = "viridis",
    diff_cmap: str = "RdBu_r",
    vmin: float | None = None,
    vmax: float | None = None,
    config: Config | None = None,
) -> plt.Figure:
    """Plot 3-panel comparison: base, experiment, difference.

    Parameters
    ----------
    comparison : Comparison
        Comparison object with base and experiment runs
    varname : str
        Variable name to plot
    time_agg : TimeAgg or int, default="mean"
        Time aggregation method
    projection : str, optional
        Cartopy projection name
    watershed_boundary : Path or str, optional
        Path to watershed boundary file
    domain_file : Path, optional
        Path to ELM domain file for lndgrid coordinates
    cmap : str, default="viridis"
        Colormap for base and experiment panels
    diff_cmap : str, default="RdBu_r"
        Diverging colormap for difference panel
    vmin, vmax : float, optional
        Colorbar range limits for base/experiment (difference auto-scaled)
    config : Config, optional
        Plot configuration

    Returns
    -------
    matplotlib Figure

    Raises
    ------
    ValueError
        If data is single-point or formats don't match
    ImportError
        If cartopy not installed

    Examples
    --------
    >>> from elm_diagnostics import Comparison
    >>> from elm_diagnostics.plots import plot_map_comparison
    >>> comp = Comparison("/path/to/base", "/path/to/exp")  # doctest: +SKIP
    >>> fig = plot_map_comparison(comp, "GPP", time_agg="mean")  # doctest: +SKIP
    """
    _check_cartopy_available()
    cfg = config or load_config()
    style = cfg.plots.style

    # Load data
    da_base = comparison.base.get(varname)
    da_exp = comparison.experiment.get(varname)

    # Check spatial formats
    format_base = detect_spatial_format(da_base)
    format_exp = detect_spatial_format(da_exp)

    if format_base == "single_point" or format_exp == "single_point":
        raise ValueError(
            f"Variable '{varname}' has no spatial variation. "
            "Spatial maps require multi-gridcell data."
        )

    if format_base != format_exp:
        raise ValueError(
            f"Spatial format mismatch: base is {format_base}, experiment is {format_exp}"
        )

    # Apply time aggregation
    da_base_agg = _apply_time_aggregation(da_base, time_agg)
    da_exp_agg = _apply_time_aggregation(da_exp, time_agg)

    # Compute difference
    da_diff = da_exp_agg - da_base_agg

    # Load watershed boundary if provided
    boundary = None
    if watershed_boundary is not None:
        boundary = _load_watershed_boundary(watershed_boundary)

    # Create figure with 3 subplots
    if projection is None:
        projection = "PlateCarree" if format_base == "latlon" else None

    if projection is not None:
        proj_class = getattr(ccrs, projection)
        proj = proj_class()
        fig, axes = plt.subplots(
            1,
            3,
            figsize=(style.figsize[0] * 2.5, style.figsize[1]),
            dpi=style.dpi,
            subplot_kw={"projection": proj},
        )
    else:
        fig, axes = plt.subplots(
            1, 3, figsize=(style.figsize[0] * 2.5, style.figsize[1]), dpi=style.dpi
        )

    # Determine shared colorbar range for base/experiment
    if vmin is None:
        vmin = min(float(da_base_agg.min()), float(da_exp_agg.min()))
    if vmax is None:
        vmax = max(float(da_base_agg.max()), float(da_exp_agg.max()))

    # Plot base
    if format_base == "latlon":
        _plot_latlon_map(
            axes[0], da_base_agg, cmap=cmap, vmin=vmin, vmax=vmax, boundary=boundary
        )
    else:
        lon, lat = _load_domain_coords(comparison.base, domain_file)
        _plot_lndgrid_map(
            axes[0],
            da_base_agg,
            lon,
            lat,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            boundary=boundary,
        )
    axes[0].set_title(f"Base: {comparison.base.name}")

    # Plot experiment
    if format_exp == "latlon":
        _plot_latlon_map(
            axes[1], da_exp_agg, cmap=cmap, vmin=vmin, vmax=vmax, boundary=boundary
        )
    else:
        lon, lat = _load_domain_coords(comparison.experiment, domain_file)
        _plot_lndgrid_map(
            axes[1],
            da_exp_agg,
            lon,
            lat,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            boundary=boundary,
        )
    axes[1].set_title(f"Experiment: {comparison.experiment.name}")

    # Plot difference with symmetric diverging colorbar
    diff_max = max(abs(float(da_diff.min())), abs(float(da_diff.max())))
    if format_base == "latlon":
        _plot_latlon_map(
            axes[2],
            da_diff,
            cmap=diff_cmap,
            vmin=-diff_max,
            vmax=diff_max,
            boundary=boundary,
        )
    else:
        _plot_lndgrid_map(
            axes[2],
            da_diff,
            lon,
            lat,
            cmap=diff_cmap,
            vmin=-diff_max,
            vmax=diff_max,
            boundary=boundary,
        )
    axes[2].set_title("Difference (Exp - Base)")

    # Overall title
    units = da_base.attrs.get("units", "")
    long_name = da_base.attrs.get("long_name", "")
    title = f"{varname}"
    if isinstance(time_agg, int):
        title += f" (timestep {time_agg})"
    else:
        title += f" ({time_agg})"
    if long_name:
        title += f" — {long_name}"
    if units:
        title += f" ({units})"

    fig.suptitle(title, fontsize="large")
    fig.tight_layout()

    return fig
