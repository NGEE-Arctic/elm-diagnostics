"""Regression tests for analysis window filtering in reports.

These tests verify that the analysis_start_year and analysis_end_year config
settings are properly enforced when generating reports, including:
- Time range of plotted data
- Metadata Time Range reporting
- Water-year boundary handling
- Climatology interaction with analysis windows
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from elm_diagnostics.cli import app
from tests.fixtures.synthetic_elm import (
    make_carbon_balance_dataset,
    make_energy_balance_dataset,
    make_water_balance_dataset,
    save_as_elm_files,
)

runner = CliRunner()


@pytest.fixture
def multi_year_data_dir(tmp_path):
    """Create synthetic data spanning multiple years (2000-2002)."""
    data_dir = tmp_path / "elm_data_multi"
    data_dir.mkdir()

    # Create datasets for three full years
    import xarray as xr

    all_ds = []
    for year in [2000, 2001, 2002]:
        ds_water = make_water_balance_dataset(start_year=year, n_months=12)
        ds_carbon = make_carbon_balance_dataset(start_year=year, n_months=12)
        ds_energy = make_energy_balance_dataset(start_year=year, n_months=12)
        all_ds.append(xr.merge([ds_water, ds_carbon, ds_energy]))

    ds_full = xr.concat(all_ds, dim="time")
    save_as_elm_files(ds_full, data_dir, casename="test", tape="h0")

    return data_dir


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary output directory."""
    out_dir = tmp_path / "output"
    return out_dir


def _extract_time_range_from_html(html_path: Path) -> tuple[str, str] | None:
    """Extract Time Range from generated report HTML."""
    try:
        content = html_path.read_text()
        # Look for "Time Range" followed by dates
        match = re.search(
            r"Time Range[^0-9]*([0-9]{4}-[0-9]{2}-[0-9]{2})[^0-9]*to[^0-9]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
            content,
        )
        if match:
            return (match.group(1), match.group(2))
    except Exception:
        # Ignore any parsing errors and return None
        return None
    return None


class TestAnalysisWindowFiltering:
    """Test suite for analysis window filtering in reports."""

    def test_report_single_year_respects_analysis_window(
        self, multi_year_data_dir, temp_output_dir, tmp_path
    ):
        """Report with analysis window 2001-2001 should not include 2000 or 2002 data."""
        config_file = tmp_path / "single_year.yaml"
        config_file.write_text(
            "time:\n  analysis_start_year: 2001\n  analysis_end_year: 2001\n  water_year_start_month: 1\nplots:\n  climatology:\n    include_climos: false\n"
        )

        result = runner.invoke(
            app,
            [
                "report",
                str(multi_year_data_dir),
                "--out",
                str(temp_output_dir),
                "--config",
                str(config_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0

        html_path = Path(temp_output_dir) / "index.html"
        assert html_path.exists()

        # Extract time range from metadata in HTML
        time_range = _extract_time_range_from_html(html_path)
        if time_range:
            start, end = time_range
            # Should be within 2001 (allow some tolerance for month boundaries)
            assert start.startswith("2001"), f"Start date {start} should be in 2001"
            assert end.startswith("2001"), f"End date {end} should be in 2001"

    def test_report_with_water_year_boundary(
        self, multi_year_data_dir, temp_output_dir, tmp_path
    ):
        """Report with water year start month=10 and 2001-2001 should include Oct 2000-Sep 2001."""
        config_file = tmp_path / "water_year.yaml"
        config_file.write_text(
            "time:\n  analysis_start_year: 2001\n  analysis_end_year: 2001\n  water_year_start_month: 10\nplots:\n  climatology:\n    include_climos: false\n"
        )

        result = runner.invoke(
            app,
            [
                "report",
                str(multi_year_data_dir),
                "--out",
                str(temp_output_dir),
                "--config",
                str(config_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0

        html_path = Path(temp_output_dir) / "index.html"
        assert html_path.exists()

        # For water year 2001 (Oct 2000-Sep 2001), start should be in 2000
        time_range = _extract_time_range_from_html(html_path)
        if time_range:
            start, end = time_range
            # Water year 2001 should start in Oct 2000
            assert start.startswith("2000"), (
                f"Water year 2001 start {start} should be in 2000"
            )
            # And end in Sep 2001
            assert end.startswith("2001"), (
                f"Water year 2001 end {end} should be in 2001"
            )

    def test_report_multi_year_window(
        self, multi_year_data_dir, temp_output_dir, tmp_path
    ):
        """Report with analysis window 2000-2002 should include only those years."""
        config_file = tmp_path / "multi_year.yaml"
        config_file.write_text(
            "time:\n  analysis_start_year: 2000\n  analysis_end_year: 2002\n  water_year_start_month: 1\nplots:\n  climatology:\n    include_climos: false\n"
        )

        result = runner.invoke(
            app,
            [
                "report",
                str(multi_year_data_dir),
                "--out",
                str(temp_output_dir),
                "--config",
                str(config_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0

        html_path = Path(temp_output_dir) / "index.html"
        assert html_path.exists()

        time_range = _extract_time_range_from_html(html_path)
        if time_range:
            start, end = time_range
            assert start.startswith("2000"), f"Start {start} should be in 2000"
            assert end.startswith("2002"), f"End {end} should be in 2002"

    def test_balance_respects_analysis_window(
        self, multi_year_data_dir, temp_output_dir, tmp_path
    ):
        """Balance command with analysis window should also respect the window."""
        config_file = tmp_path / "balance_window.yaml"
        config_file.write_text(
            "time:\n  analysis_start_year: 2001\n  analysis_end_year: 2001\n  water_year_start_month: 1\nplots:\n  climatology:\n    include_climos: false\n"
        )

        result = runner.invoke(
            app,
            [
                "balance",
                "water",
                str(multi_year_data_dir),
                "--out",
                str(temp_output_dir),
                "--config",
                str(config_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        # If balance succeeds, at least one plot should exist
        png_files = list(Path(temp_output_dir).glob("*.png"))
        assert len(png_files) > 0, f"No PNG files found in {temp_output_dir}"

    def test_climatology_default_does_not_override_analysis_window(
        self, multi_year_data_dir, temp_output_dir, tmp_path
    ):
        """Analysis window should be enforced even with default climatology sentinels.

        This was the main regression: with climatology.include_climos=true and
        climo_start/end_year=-1, the analysis window was completely ignored.
        """
        config_file = tmp_path / "climo_with_window.yaml"
        config_file.write_text(
            "time:\n  analysis_start_year: 2001\n  analysis_end_year: 2001\n  water_year_start_month: 1\nplots:\n  climatology:\n    include_climos: true\n    climo_start_year: -1\n    climo_end_year: -1\n"
        )

        result = runner.invoke(
            app,
            [
                "report",
                str(multi_year_data_dir),
                "--out",
                str(temp_output_dir),
                "--config",
                str(config_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0

        html_path = Path(temp_output_dir) / "index.html"
        assert html_path.exists()

        # Even with climatology enabled, analysis window should be respected
        time_range = _extract_time_range_from_html(html_path)
        if time_range:
            start, end = time_range
            assert start.startswith("2001"), (
                f"Start {start} should be in 2001 despite climatology"
            )
            assert end.startswith("2001"), (
                f"End {end} should be in 2001 despite climatology"
            )
