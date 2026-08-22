"""Tests for spatial map plotting."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from elm_diagnostics import Comparison, Run
from elm_diagnostics.plots import plot_map, plot_map_comparison
from elm_diagnostics.plots.spatial import detect_spatial_format
from tests.fixtures.synthetic_elm import (
    make_gridded_dataset,
    make_lndgrid_dataset,
    make_single_point_dataset,
    save_as_elm_files,
)

# Skip all tests if cartopy not available
pytest.importorskip("cartopy")


@pytest.fixture
def gridded_run(tmp_path: Path) -> Run:
    """Create a test run with gridded (lat/lon) data."""
    ds = make_gridded_dataset(nlat=3, nlon=3, n_months=12)
    # Save as single file to avoid xarray concat dimension conflicts
    fname = tmp_path / "gridded_test.elm.h0.2000-01.nc"
    ds.to_netcdf(fname)
    return Run(str(tmp_path), name="Gridded Test")


@pytest.fixture
def lndgrid_run(tmp_path: Path) -> tuple[Run, Path]:
    """Create a test run with unstructured lndgrid data and domain file."""
    ds, domain_ds = make_lndgrid_dataset(ncells=9, n_months=12)
    # Save as single file
    fname = tmp_path / "lndgrid_test.elm.h0.2000-01.nc"
    ds.to_netcdf(fname)

    # Save domain file
    domain_file = tmp_path / "domain.lnd.test.nc"
    domain_ds.to_netcdf(domain_file)

    return Run(str(tmp_path), name="Lndgrid Test"), domain_file


@pytest.fixture
def gridded_comparison(tmp_path: Path) -> Comparison:
    """Create a comparison with two gridded runs."""
    base_dir = tmp_path / "base"
    exp_dir = tmp_path / "exp"
    base_dir.mkdir()
    exp_dir.mkdir()

    # Base run
    ds_base = make_gridded_dataset(
        nlat=3, nlon=3, n_months=12, add_spatial_gradient=True
    )
    fname_base = base_dir / "base.elm.h0.2000-01.nc"
    ds_base.to_netcdf(fname_base)

    # Experiment run (slightly different values)
    ds_exp = make_gridded_dataset(
        nlat=3, nlon=3, n_months=12, add_spatial_gradient=True
    )
    # Modify GPP to create difference
    ds_exp["GPP"] = ds_exp["GPP"] * 1.1
    fname_exp = exp_dir / "exp.elm.h0.2000-01.nc"
    ds_exp.to_netcdf(fname_exp)

    base_run = Run(str(base_dir), name="Base")
    exp_run = Run(str(exp_dir), name="Experiment")
    return Comparison(base_run, exp_run)


class TestDetectSpatialFormat:
    """Tests for detect_spatial_format function."""

    def test_latlon_format(self, gridded_run: Run):
        da = gridded_run.get("GPP")
        assert detect_spatial_format(da) == "latlon"

    def test_lndgrid_format(self, lndgrid_run: tuple[Run, Path]):
        run, _ = lndgrid_run
        da = run.get("GPP")
        assert detect_spatial_format(da) == "lndgrid"

    def test_single_point(self):
        with TemporaryDirectory() as tmpdir:
            import numpy as np

            # Create single point dataset with some variables
            variables = {
                "RAIN": {
                    "data": np.random.rand(12),
                    "units": "mm/s",
                    "cell_methods": "time: mean",
                }
            }
            ds = make_single_point_dataset(n_months=12, variables=variables)
            fname = Path(tmpdir) / "single_point.elm.h0.2000-01.nc"
            ds.to_netcdf(fname)
            run = Run(tmpdir)
            da = run.get("RAIN")
            assert detect_spatial_format(da) == "single_point"


class TestPlotMap:
    """Tests for plot_map function."""

    def test_plot_latlon_map_mean(self, gridded_run: Run):
        """Test lat/lon map with mean aggregation."""
        fig = plot_map(gridded_run, "GPP", time_agg="mean")
        assert fig is not None
        assert len(fig.axes) >= 1  # At least the main axes (colorbar adds another)
        # Check that title includes variable name and aggregation
        title = fig.axes[0].get_title()
        assert "GPP" in title
        assert "mean" in title.lower()

    def test_plot_latlon_map_median(self, gridded_run: Run):
        """Test lat/lon map with median aggregation."""
        fig = plot_map(gridded_run, "RAIN", time_agg="median")
        assert fig is not None
        title = fig.axes[0].get_title()
        assert "RAIN" in title
        assert "median" in title.lower()

    def test_plot_latlon_map_timestep(self, gridded_run: Run):
        """Test lat/lon map at specific timestep."""
        fig = plot_map(gridded_run, "GPP", time_agg=0)
        assert fig is not None
        title = fig.axes[0].get_title()
        assert "GPP" in title
        assert "timestep 0" in title.lower()

    def test_plot_lndgrid_map(self, lndgrid_run: tuple[Run, Path]):
        """Test unstructured lndgrid map."""
        run, domain_file = lndgrid_run
        fig = plot_map(run, "GPP", time_agg="mean", domain_file=domain_file)
        assert fig is not None
        assert len(fig.axes) >= 1

    def test_plot_lndgrid_auto_detect_domain(self, lndgrid_run: tuple[Run, Path]):
        """Test auto-detection of domain file."""
        run, _ = lndgrid_run
        # Domain file is in same dir, should auto-detect
        fig = plot_map(run, "GPP", time_agg="mean")
        assert fig is not None

    def test_single_point_raises_error(self):
        """Test that single-point data raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            import numpy as np

            variables = {
                "RAIN": {
                    "data": np.random.rand(12),
                    "units": "mm/s",
                    "cell_methods": "time: mean",
                }
            }
            ds = make_single_point_dataset(n_months=12, variables=variables)
            fname = Path(tmpdir) / "single_point.elm.h0.2000-01.nc"
            ds.to_netcdf(fname)
            run = Run(tmpdir)

            with pytest.raises(ValueError, match="no spatial variation"):
                plot_map(run, "RAIN", time_agg="mean")

    def test_invalid_time_agg_raises(self, gridded_run: Run):
        """Test that invalid time aggregation raises error."""
        with pytest.raises(ValueError, match="Unknown aggregation method"):
            plot_map(gridded_run, "GPP", time_agg="invalid")

    def test_time_index_out_of_range(self, gridded_run: Run):
        """Test that out-of-range time index raises error."""
        with pytest.raises(ValueError, match="out of range"):
            plot_map(gridded_run, "GPP", time_agg=999)

    def test_custom_colormap(self, gridded_run: Run):
        """Test custom colormap specification."""
        fig = plot_map(gridded_run, "GPP", time_agg="mean", cmap="plasma")
        assert fig is not None

    def test_custom_vmin_vmax(self, gridded_run: Run):
        """Test custom colorbar range."""
        fig = plot_map(gridded_run, "GPP", time_agg="mean", vmin=0, vmax=1e-5)
        assert fig is not None

    @pytest.mark.skip(
        reason="Orthographic projection has issues with small regional grids"
    )
    def test_projection_orthographic(self, gridded_run: Run):
        """Test different projection."""
        fig = plot_map(gridded_run, "GPP", time_agg="mean", projection="Orthographic")
        assert fig is not None


class TestPlotMapComparison:
    """Tests for plot_map_comparison function."""

    def test_comparison_three_panels(self, gridded_comparison: Comparison):
        """Test comparison creates 3-panel figure."""
        fig = plot_map_comparison(gridded_comparison, "GPP", time_agg="mean")
        assert fig is not None
        # 3 main panels + 3 colorbars = 6 axes
        assert len(fig.axes) >= 3  # At least the 3 main panels

    def test_comparison_titles(self, gridded_comparison: Comparison):
        """Test comparison panel titles."""
        fig = plot_map_comparison(gridded_comparison, "GPP", time_agg="mean")
        titles = [ax.get_title() for ax in fig.axes]
        assert any("Base" in t for t in titles)
        assert any("Experiment" in t for t in titles)
        assert any("Difference" in t for t in titles)

    def test_comparison_diff_colormap(self, gridded_comparison: Comparison):
        """Test diverging colormap for difference panel."""
        fig = plot_map_comparison(
            gridded_comparison, "GPP", time_agg="mean", diff_cmap="bwr"
        )
        assert fig is not None

    def test_comparison_median_agg(self, gridded_comparison: Comparison):
        """Test comparison with median aggregation."""
        fig = plot_map_comparison(gridded_comparison, "RAIN", time_agg="median")
        assert fig is not None

    def test_comparison_single_point_raises(self):
        """Test that single-point comparison raises error."""
        with TemporaryDirectory() as tmpdir:
            import numpy as np

            base_dir = Path(tmpdir) / "base"
            exp_dir = Path(tmpdir) / "exp"
            base_dir.mkdir()
            exp_dir.mkdir()

            variables = {
                "RAIN": {
                    "data": np.random.rand(12),
                    "units": "mm/s",
                    "cell_methods": "time: mean",
                }
            }
            ds_base = make_single_point_dataset(n_months=12, variables=variables)
            ds_exp = make_single_point_dataset(n_months=12, variables=variables)
            fname_base = base_dir / "base.elm.h0.2000-01.nc"
            fname_exp = exp_dir / "exp.elm.h0.2000-01.nc"
            ds_base.to_netcdf(fname_base)
            ds_exp.to_netcdf(fname_exp)

            base_run = Run(str(base_dir))
            exp_run = Run(str(exp_dir))
            comp = Comparison(base_run, exp_run)

            with pytest.raises(ValueError, match="no spatial variation"):
                plot_map_comparison(comp, "RAIN", time_agg="mean")


class TestWatershedBoundary:
    """Tests for watershed boundary overlay."""

    def test_boundary_without_geopandas(self, gridded_run: Run, tmp_path: Path):
        """Test that missing geopandas shows warning but doesn't fail."""
        # Create dummy boundary file
        boundary_file = tmp_path / "boundary.geojson"
        boundary_file.write_text('{"type": "FeatureCollection", "features": []}')

        # Should not raise, just warn if geopandas missing
        fig = plot_map(
            gridded_run,
            "GPP",
            time_agg="mean",
            watershed_boundary=boundary_file,
        )
        assert fig is not None


class TestDomainFileHandling:
    """Tests for domain file auto-detection and loading."""

    def test_missing_domain_raises(self, tmp_path: Path):
        """Test that missing domain file for lndgrid raises helpful error."""
        ds, _ = make_lndgrid_dataset(ncells=9, n_months=12)
        save_as_elm_files(ds, tmp_path, casename="lndgrid_test", tape="h0")
        # Don't save domain file

        run = Run(str(tmp_path))

        with pytest.raises(FileNotFoundError, match="domain file"):
            plot_map(run, "GPP", time_agg="mean")

    def test_explicit_domain_file(self, lndgrid_run: tuple[Run, Path]):
        """Test explicit domain file path."""
        run, domain_file = lndgrid_run
        fig = plot_map(run, "GPP", time_agg="mean", domain_file=domain_file)
        assert fig is not None

    def test_domain_coords_cached(self, lndgrid_run: tuple[Run, Path]):
        """Test that domain coordinates are cached in Run object."""
        run, domain_file = lndgrid_run

        # First call loads domain
        _fig1 = plot_map(run, "GPP", time_agg="mean", domain_file=domain_file)
        assert hasattr(run, "_domain_coords")

        # Second call should use cached coords
        fig2 = plot_map(run, "RAIN", time_agg="mean", domain_file=domain_file)
        assert fig2 is not None


class TestAreaWeightedStatistics:
    """Tests for area-weighted statistics helper."""

    def test_area_variable_exists(self, gridded_run: Run):
        """Test that gridded test data includes AREA variable."""
        # Our synthetic gridded data should include AREA
        ds = gridded_run.get("AREA")
        assert ds is not None
        assert (
            "area" in ds.attrs.get("units", "").lower()
            or ds.attrs.get("long_name", "") != ""
        )


# Image comparison tests (if pytest-mpl available)
try:
    import pytest_mpl  # noqa: F401

    @pytest.mark.mpl_image_compare(baseline_dir="baseline/spatial", tolerance=10)
    def test_plot_map_latlon_image(gridded_run: Run):
        """Image comparison test for lat/lon map."""
        fig = plot_map(gridded_run, "GPP", time_agg="mean")
        return fig

    @pytest.mark.mpl_image_compare(baseline_dir="baseline/spatial", tolerance=10)
    def test_plot_map_comparison_image(gridded_comparison: Comparison):
        """Image comparison test for comparison map."""
        fig = plot_map_comparison(gridded_comparison, "GPP", time_agg="mean")
        return fig

except ImportError:
    # pytest-mpl not available, skip image comparison tests
    pass
