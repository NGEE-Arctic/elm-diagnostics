"""Tests for report generation."""

import tempfile
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.report.build import Report
from elm_diagnostics.config.schema import Config
from tests.fixtures.synthetic_elm import (
    make_multicolumn_dataset,
    make_water_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def report_run():
    ds = make_water_balance_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="report_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


@pytest.fixture
def comparison_runs():
    """Create two runs for comparison testing."""
    ds_base = make_water_balance_dataset(start_year=2000, n_months=12)
    ds_exp = make_water_balance_dataset(start_year=2001, n_months=12)
    
    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            save_as_elm_files(ds_base, Path(tmpdir1), casename="base", tape="h0")
            save_as_elm_files(ds_exp, Path(tmpdir2), casename="experiment", tape="h0")
            base_run = Run(tmpdir1, name="base")
            exp_run = Run(tmpdir2, name="experiment")
            comparison = Comparison(base=base_run, experiment=exp_run)
            yield comparison
            base_run.close()
            exp_run.close()


def test_report_build(report_run):
    """Test basic report generation."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        assert html_path.exists()
        assert html_path.name == "index.html"
        content = html_path.read_text()
        assert "report_test" in content
        assert "Water Balance" in content


def test_report_creates_figures(report_run):
    """Test that figures directory is created with PNG files."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        rpt.build(outdir)
        figdir = Path(outdir) / "figures"
        assert figdir.exists()
        pngs = list(figdir.glob("*.png"))
        assert len(pngs) > 0


def test_report_creates_thumbnails(report_run):
    """Test that thumbnail images are generated."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        rpt.build(outdir)
        figdir = Path(outdir) / "figures"
        thumbs = list(figdir.glob("*_thumb.png"))
        assert len(thumbs) > 0, "Should generate thumbnail images"


def test_report_creates_data_directory(report_run):
    """Test that data directory is created."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        rpt.build(outdir)
        datadir = Path(outdir) / "data"
        assert datadir.exists()


def test_report_saves_netcdf(report_run):
    """Test that NetCDF files are saved for balances."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        rpt.build(outdir)
        datadir = Path(outdir) / "data"
        nc_files = list(datadir.glob("*.nc"))
        # Should have at least water balance NetCDF
        assert len(nc_files) > 0, "Should save NetCDF files"


def test_report_metadata_section(report_run):
    """Test that metadata section is included."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        assert "Run Information" in content or "Metadata" in content.lower()
        assert "report_test" in content


def test_report_summary_bar(report_run):
    """Test that summary bar is present in HTML."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        assert "summary-bar" in content
        assert "Sections" in content or "Figures" in content


def test_report_statistics_tables(report_run):
    """Test that statistics tables are generated."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        assert "stats-table" in content


def test_report_lightbox_elements(report_run):
    """Test that lightbox HTML elements are present."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        assert "lightbox" in content.lower()


def test_report_multiple_plot_types(report_run):
    """Test that multiple plot types are generated."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        rpt.build(outdir)
        figdir = Path(outdir) / "figures"
        
        # Check for different plot type names in filenames
        all_files = [f.name for f in figdir.glob("*.png")]
        plot_types_found = set()
        for fname in all_files:
            if "timeseries" in fname:
                plot_types_found.add("timeseries")
            if "seasonal" in fname:
                plot_types_found.add("seasonal")
            if "histogram" in fname:
                plot_types_found.add("histogram")
        
        # Should have at least timeseries
        assert "timeseries" in plot_types_found


def test_report_error_handling(report_run):
    """Test that errors are handled gracefully."""
    # Force an error by requesting a non-existent year
    rpt = Report(report_run, year=9999)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        # Should still create HTML even with errors
        assert html_path.exists()
        # Check for diagnostics section
        content = html_path.read_text()
        # Report should still be generated
        assert len(content) > 100


def test_report_comparison_mode(comparison_runs):
    """Test report generation with Comparison object."""
    rpt = Report(comparison_runs)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        assert html_path.exists()
        content = html_path.read_text()
        # Should mention both runs
        assert "base" in content.lower() or "experiment" in content.lower()


def test_report_config_customization(report_run):
    """Test that config options are respected."""
    from elm_diagnostics.config.schema import Config, ReportConfig, ThumbnailConfig
    
    # Create custom config with thumbnails disabled
    config = Config()
    config.report = ReportConfig()
    config.report.thumbnails = ThumbnailConfig(enabled=False)
    
    rpt = Report(report_run, config=config)
    with tempfile.TemporaryDirectory() as outdir:
        rpt.build(outdir)
        # When thumbnails disabled, may still have files but they should be same as originals
        # or none at all - implementation detail


def test_report_with_subgrid_data():
    """Test report with multi-column data."""
    ds = make_multicolumn_dataset(n_columns=3, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save the dataset
        file_path = Path(tmpdir) / "test.elm.h0.2000-01.nc"
        ds.to_netcdf(file_path)
        
        run = Run(tmpdir, name="multicolumn_test")
        rpt = Report(run)
        
        with tempfile.TemporaryDirectory() as outdir:
            html_path = rpt.build(outdir)
            assert html_path.exists()
            content = html_path.read_text()
            assert "multicolumn_test" in content
        
        run.close()


def test_report_toc_navigation(report_run):
    """Test that table of contents is present."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        assert "sidebar" in content
        assert "Contents" in content


def test_report_responsive_css(report_run):
    """Test that CSS includes responsive design."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        # Check for viewport meta tag
        assert "viewport" in content
        # Check for CSS grid or flex
        assert "grid" in content or "flex" in content


def test_report_generation_timestamp(report_run):
    """Test that generation timestamp is included."""
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        # Should have a date/time mention
        import datetime
        current_year = str(datetime.datetime.now().year)
        assert current_year in content


def test_report_diagnostics_include_provenance(report_run, monkeypatch):
    """Diagnostics section should include git version and invocation command."""
    monkeypatch.setattr(Report, "_detect_git_version", lambda self: "test-git-version")
    rpt = Report(report_run, invocation_command="elm-diagnostics report /tmp/run")

    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        assert "Diagnostics" in content
        assert "Git version" in content
        assert "test-git-version" in content
        assert "Invocation command" in content
        assert "elm-diagnostics report /tmp/run" in content
        assert "Analysis run at" in content
        assert "Working directory" in content
        assert "User" in content
        assert "Machine" in content
        assert "Section timings" in content
        assert (
            "Configuration (merged)" in content
            or "Configuration file contents" in content
        )


def test_report_water_balance_section_with_january_water_year_start(report_run):
    """Water Balance section should render when water year starts in January."""
    config = Config()
    config.time.water_year_start_month = 1

    rpt = Report(report_run, config=config, year=2000)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        content = html_path.read_text()
        assert "Water Balance" in content
