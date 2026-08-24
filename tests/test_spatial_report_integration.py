"""Tests for spatial plot integration in Report class."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from elm_diagnostics import Comparison, Report, Run
from tests.fixtures.synthetic_elm import make_gridded_dataset

# Skip all tests if cartopy not available
pytest.importorskip("cartopy")


@pytest.fixture
def gridded_run(tmp_path: Path) -> Run:
    """Create a test run with gridded (lat/lon) data."""
    ds = make_gridded_dataset(nlat=3, nlon=3, n_months=12)
    fname = tmp_path / "gridded_test.elm.h0.2000-01.nc"
    ds.to_netcdf(fname)
    return Run(str(tmp_path), name="Gridded Test")


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


class TestSpatialReportIntegration:
    """Tests for spatial plot integration in reports."""

    def test_report_with_spatial_data(self, gridded_run: Run):
        """Test that report generates with spatial section for multi-cell data."""
        with TemporaryDirectory() as outdir:
            report = Report(gridded_run)
            html_path = report.build(outdir)

            assert html_path.exists()
            assert "Spatial Patterns" in report._rendered_section_titles

            # Check that spatial plots were created
            figdir = Path(outdir) / "figures"
            spatial_plots = list(figdir.glob("spatial_*.png"))
            assert len(spatial_plots) > 0, "No spatial plots were generated"

    def test_report_comparison_with_spatial(self, gridded_comparison: Comparison):
        """Test that comparison report includes spatial section."""
        with TemporaryDirectory() as outdir:
            report = Report(gridded_comparison)
            html_path = report.build(outdir)

            assert html_path.exists()
            assert "Spatial Patterns" in report._rendered_section_titles

            # Check that spatial comparison plots were created
            figdir = Path(outdir) / "figures"
            spatial_plots = list(figdir.glob("spatial_*.png"))
            assert len(spatial_plots) > 0

    def test_spatial_section_disabled(self, gridded_run: Run):
        """Test that spatial section can be disabled via config."""
        from elm_diagnostics.config.schema import Config, PlotsConfig, SpatialPlotConfig

        config = Config(plots=PlotsConfig(spatial=SpatialPlotConfig(enabled=False)))

        with TemporaryDirectory() as outdir:
            report = Report(gridded_run, config=config)
            html_path = report.build(outdir)

            assert html_path.exists()
            assert "Spatial Patterns" not in report._rendered_section_titles

    def test_spatial_section_custom_variables(self, gridded_run: Run):
        """Test that spatial section uses configured variable list."""
        from elm_diagnostics.config.schema import Config, PlotsConfig, SpatialPlotConfig

        config = Config(
            plots=PlotsConfig(
                spatial=SpatialPlotConfig(
                    enabled=True,
                    variables=["GPP", "RAIN"],  # Only these two
                )
            )
        )

        with TemporaryDirectory() as outdir:
            report = Report(gridded_run, config=config)
            html_path = report.build(outdir)

            assert html_path.exists()

            # Check that only specified variables were plotted
            figdir = Path(outdir) / "figures"
            spatial_plots = list(figdir.glob("spatial_*.png"))
            # Filter out thumbnails
            plot_vars = {
                p.stem.replace("spatial_", "")
                for p in spatial_plots
                if "_thumb" not in p.stem
            }

            # Should only have GPP and RAIN (if they exist in the data)
            assert plot_vars.issubset({"GPP", "RAIN"})

    def test_spatial_section_time_aggregation(self, gridded_run: Run):
        """Test different time aggregation methods."""
        from elm_diagnostics.config.schema import Config, PlotsConfig, SpatialPlotConfig

        for agg_method in ["mean", "median", "sum"]:
            config = Config(
                plots=PlotsConfig(
                    spatial=SpatialPlotConfig(
                        enabled=True, time_aggregation=agg_method, variables=["GPP"]
                    )
                )
            )

            with TemporaryDirectory() as outdir:
                report = Report(gridded_run, config=config)
                html_path = report.build(outdir)

                assert html_path.exists()
                assert "Spatial Patterns" in report._rendered_section_titles

    def test_single_point_no_spatial_section(self, tmp_path: Path):
        """Test that single-point data doesn't generate spatial section."""
        import numpy as np
        from tests.fixtures.synthetic_elm import make_single_point_dataset

        variables = {
            "GPP": {
                "data": np.random.rand(12),
                "units": "gC/m^2/s",
                "cell_methods": "time: mean",
            }
        }
        ds = make_single_point_dataset(n_months=12, variables=variables)
        fname = tmp_path / "single_point.elm.h0.2000-01.nc"
        ds.to_netcdf(fname)
        run = Run(str(tmp_path))

        with TemporaryDirectory() as outdir:
            report = Report(run)
            html_path = report.build(outdir)

            assert html_path.exists()
            # Spatial section should not appear for single-point data
            assert "Spatial Patterns" not in report._rendered_section_titles
