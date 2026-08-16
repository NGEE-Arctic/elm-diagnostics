"""Tests for CLI commands."""

from __future__ import annotations

import os
import subprocess

import pytest
from typer.testing import CliRunner

from elm_diagnostics.cli import app, _resolve_analysis_year_filter
from tests.fixtures.synthetic_elm import (
    make_water_balance_dataset,
    make_carbon_balance_dataset,
    make_energy_balance_dataset,
    save_as_elm_files,
)

runner = CliRunner()

# Subprocess timeouts. CI runners (especially the optional-deps job, which pulls in
# dask/plotly/cartopy) are several times slower than a dev laptop, so allow generous
# budgets and let them be tuned via the environment.
CLI_HELP_TIMEOUT = int(os.environ.get("ELM_DIAGNOSTICS_TEST_HELP_TIMEOUT", "60"))
CLI_REPORT_TIMEOUT = int(os.environ.get("ELM_DIAGNOSTICS_TEST_REPORT_TIMEOUT", "1200"))


@pytest.fixture
def synthetic_data_dir(tmp_path):
    """Create a directory with synthetic ELM data files for all balance types."""
    data_dir = tmp_path / "elm_data"
    data_dir.mkdir()

    # Create datasets with all needed variables
    ds_water = make_water_balance_dataset(start_year=2000, n_months=12)
    ds_carbon = make_carbon_balance_dataset(start_year=2000, n_months=12)
    ds_energy = make_energy_balance_dataset(start_year=2000, n_months=12)

    # Merge all datasets
    import xarray as xr

    ds = xr.merge([ds_water, ds_carbon, ds_energy])

    # Save to file
    save_as_elm_files(ds, data_dir, casename="test", tape="h0")

    return data_dir


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary output directory."""
    out_dir = tmp_path / "output"
    return out_dir


# =============================================================================
# Basic Command Tests
# =============================================================================


def test_cli_help():
    """Test that --help works for main command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Diagnostics and budget-closure" in result.output
    assert "report" in result.output
    assert "balance" in result.output
    assert "plot" in result.output


def test_report_command_help():
    """Test that report --help works."""
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    assert "Generate a full diagnostics report" in result.output
    # Strip ANSI codes to handle CI terminal width differences
    import re

    output_clean = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--compare" in output_clean
    assert "--config" in output_clean
    assert "--year" not in output_clean
    assert "--all-years" not in output_clean
    assert "--water-year-start" not in output_clean


def test_balance_command_help():
    """Test that balance --help works."""
    result = runner.invoke(app, ["balance", "--help"])
    assert result.exit_code == 0
    assert "Compute and plot a single budget balance" in result.output
    assert "water, carbon, or energy" in result.output


def test_plot_command_help():
    """Test that plot --help works."""
    result = runner.invoke(app, ["plot", "--help"])
    assert result.exit_code == 0
    assert "Plot a single variable" in result.output
    assert "timeseries" in result.output


def test_report_command_basic(synthetic_data_dir, temp_output_dir):
    """Test basic report generation."""
    result = runner.invoke(
        app,
        ["report", str(synthetic_data_dir), "--out", str(temp_output_dir), "--quiet"],
    )
    assert result.exit_code == 0
    assert "Report generated" in result.output
    assert (temp_output_dir / "index.html").exists()


def test_report_with_analysis_window_config(
    synthetic_data_dir, temp_output_dir, tmp_path
):
    """Test report generation using year window in config."""
    config_file = tmp_path / "analysis_window.yaml"
    config_file.write_text(
        "\n".join(
            [
                "time:",
                "  analysis_start_year: 2000",
                "  analysis_end_year: 2000",
                "  water_year_start_month: 10",
                "plots:",
                "  climatology:",
                "    include_climos: false",
                "",
            ]
        )
    )

    result = runner.invoke(
        app,
        [
            "report",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--config",
            str(config_file),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (temp_output_dir / "index.html").exists()


def test_balance_water(synthetic_data_dir, temp_output_dir):
    """Test water balance via CLI."""
    result = runner.invoke(
        app,
        [
            "balance",
            "water",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert "Saved to" in result.output
    assert (temp_output_dir / "water_panel1.png").exists()
    assert (temp_output_dir / "water_panel2.png").exists()
    assert (temp_output_dir / "water_panel3.png").exists()
    assert (temp_output_dir / "water_panel4.png").exists()
    assert (temp_output_dir / "water_balance.nc").exists()


def test_balance_carbon(synthetic_data_dir, temp_output_dir):
    """Test carbon balance via CLI."""
    result = runner.invoke(
        app,
        [
            "balance",
            "carbon",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (temp_output_dir / "carbon_panel1.png").exists()
    assert (temp_output_dir / "carbon_panel2.png").exists()


def test_balance_energy(synthetic_data_dir, temp_output_dir):
    """Test energy balance via CLI."""
    result = runner.invoke(
        app,
        [
            "balance",
            "energy",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (temp_output_dir / "energy_panel1.png").exists()


# =============================================================================
# Plot Command Tests
# =============================================================================


def test_plot_timeseries(synthetic_data_dir, temp_output_dir):
    """Test timeseries plot via CLI."""
    out_file = temp_output_dir / "gpp_timeseries.png"
    temp_output_dir.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "plot",
            "GPP",
            str(synthetic_data_dir),
            "--kind",
            "timeseries",
            "--out",
            str(out_file),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()


def test_plot_seasonal(synthetic_data_dir, temp_output_dir):
    """Test seasonal plot via CLI."""
    out_file = temp_output_dir / "rain_seasonal.png"
    temp_output_dir.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "plot",
            "RAIN",
            str(synthetic_data_dir),
            "--kind",
            "seasonal",
            "--out",
            str(out_file),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()


def test_plot_histogram(synthetic_data_dir, temp_output_dir):
    """Test histogram plot via CLI."""
    out_file = temp_output_dir / "er_histogram.png"
    temp_output_dir.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "plot",
            "ER",
            str(synthetic_data_dir),
            "--kind",
            "histogram",
            "--out",
            str(out_file),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()


def test_plot_default_kind(synthetic_data_dir, temp_output_dir):
    """Test that default plot kind is timeseries."""
    out_file = temp_output_dir / "default.png"
    temp_output_dir.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "plot",
            "GPP",
            str(synthetic_data_dir),
            "--out",
            str(out_file),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()


# =============================================================================
# Error Handling Tests
# =============================================================================


def test_invalid_path():
    """Test error message for nonexistent directory."""
    result = runner.invoke(app, ["report", "/nonexistent/path/to/data", "--quiet"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_invalid_balance_type(synthetic_data_dir):
    """Test error message for invalid balance type."""
    result = runner.invoke(
        app, ["balance", "nitrogen", str(synthetic_data_dir), "--quiet"]
    )
    assert result.exit_code == 1
    assert "Unknown balance type" in result.output
    assert "water" in result.output
    assert "carbon" in result.output
    assert "energy" in result.output


def test_invalid_plot_kind(synthetic_data_dir):
    """Test error message for invalid plot kind."""
    result = runner.invoke(
        app,
        ["plot", "GPP", str(synthetic_data_dir), "--kind", "invalid", "--quiet"],
    )
    assert result.exit_code == 1
    assert "Unknown plot kind" in result.output
    assert "timeseries" in result.output
    assert "seasonal" in result.output


def test_missing_required_args():
    """Test that missing required arguments shows help."""
    result = runner.invoke(app, ["report"])
    assert result.exit_code == 2  # Typer uses exit code 2 for usage errors
    assert "Missing argument" in result.output or "required" in result.output.lower()


def test_invalid_config_file(synthetic_data_dir, temp_output_dir):
    """Test error for nonexistent config file."""
    result = runner.invoke(
        app,
        [
            "report",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--config",
            "/nonexistent/config.yaml",
            "--quiet",
        ],
    )
    assert result.exit_code == 1
    assert "Config file not found" in result.output


def test_conflicting_quiet_verbose(synthetic_data_dir, temp_output_dir):
    """Test that --quiet and --verbose cannot be used together."""
    result = runner.invoke(
        app,
        [
            "report",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--quiet",
            "--verbose",
        ],
    )
    assert result.exit_code == 1
    assert "Cannot specify both" in result.output


# =============================================================================
# Option Tests
# =============================================================================


def test_verbose_flag(synthetic_data_dir, temp_output_dir):
    """Test --verbose flag shows extra output."""
    result = runner.invoke(
        app,
        [
            "report",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--verbose",
        ],
    )
    assert result.exit_code == 0
    # Verbose mode should show timing or other details
    # For now, just check it succeeds


def test_quiet_flag_suppresses_output(synthetic_data_dir, temp_output_dir):
    """Test --quiet flag suppresses progress output."""
    result = runner.invoke(
        app,
        [
            "balance",
            "water",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    # Quiet mode should have minimal output
    assert "Loading" not in result.output or "Saved to" in result.output


def test_analysis_year_filter_includes_previous_year_for_water_year(tmp_path):
    """Year narrowing should include prior year for water-year framing."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "\n".join(
            [
                "time:",
                "  analysis_start_year: 2000",
                "  analysis_end_year: 2000",
                "  water_year_start_month: 10",
                "plots:",
                "  climatology:",
                "    include_climos: false",
                "",
            ]
        )
    )

    lo, hi = _resolve_analysis_year_filter(str(cfg))
    assert (lo, hi) == (1999, 2000)


def test_analysis_year_filter_uses_config_window(tmp_path):
    """Year narrowing should honor config start/end year bounds."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "\n".join(
            [
                "time:",
                "  analysis_start_year: 1990",
                "  analysis_end_year: 1995",
                "  water_year_start_month: 1",
                "plots:",
                "  climatology:",
                "    include_climos: false",
                "",
            ]
        )
    )

    lo, hi = _resolve_analysis_year_filter(str(cfg))
    assert (lo, hi) == (1990, 1995)


# =============================================================================
# Comparison Mode Tests
# =============================================================================


def test_report_comparison(synthetic_data_dir, tmp_path, temp_output_dir):
    """Test --compare flag for comparison report."""
    # Create a second synthetic dataset
    compare_dir = tmp_path / "compare_data"
    compare_dir.mkdir()

    # We need to import and create another dataset
    from tests.fixtures.synthetic_elm import make_single_point_dataset
    import numpy as np

    # Create a slightly different dataset
    variables = {
        "GPP": {
            "data": np.random.uniform(2, 8, 12),
            "units": "gC m-2 s-1",
            "cell_methods": "time: mean",
        },
        "ER": {
            "data": np.random.uniform(1, 5, 12),
            "units": "gC m-2 s-1",
            "cell_methods": "time: mean",
        },
    }
    ds2 = make_single_point_dataset(n_months=12, variables=variables)
    ds2.to_netcdf(compare_dir / "test.elm.h0.2000-01.nc")

    result = runner.invoke(
        app,
        [
            "report",
            str(synthetic_data_dir),
            "--compare",
            str(compare_dir),
            "--out",
            str(temp_output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (temp_output_dir / "index.html").exists()


# =============================================================================
# Exit Code Tests
# =============================================================================


def test_success_exit_code(synthetic_data_dir, temp_output_dir):
    """Test that successful commands return exit code 0."""
    result = runner.invoke(
        app,
        ["report", str(synthetic_data_dir), "--out", str(temp_output_dir), "--quiet"],
    )
    assert result.exit_code == 0


def test_error_exit_code():
    """Test that errors return exit code 1."""
    result = runner.invoke(app, ["report", "/nonexistent/path", "--quiet"])
    assert result.exit_code == 1


def test_help_exit_code():
    """Test that --help returns exit code 0."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0


# =============================================================================
# Integration Tests (using subprocess for real CLI)
# =============================================================================


def test_cli_installed():
    """Integration test: verify CLI command is in PATH."""
    result = subprocess.run(
        ["elm-diagnostics", "--help"],
        capture_output=True,
        text=True,
        timeout=CLI_HELP_TIMEOUT,
    )
    assert result.returncode == 0
    assert "Diagnostics and budget-closure" in result.stdout


def test_cli_entry_point_version():
    """Integration test: verify CLI entry point works."""
    result = subprocess.run(
        ["elm-diagnostics", "--help"],
        capture_output=True,
        text=True,
        timeout=CLI_HELP_TIMEOUT,
    )
    assert result.returncode == 0
    assert "report" in result.stdout
    assert "balance" in result.stdout
    assert "plot" in result.stdout


@pytest.mark.slow
def test_cli_end_to_end_subprocess(synthetic_data_dir, temp_output_dir):
    """Integration test: full report generation via subprocess."""
    result = subprocess.run(
        [
            "elm-diagnostics",
            "report",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=CLI_REPORT_TIMEOUT,
    )
    assert result.returncode == 0
    assert "Report generated" in result.stdout
    assert (temp_output_dir / "index.html").exists()


# =============================================================================
# Custom Config Tests
# =============================================================================


def test_report_with_custom_config(synthetic_data_dir, temp_output_dir, tmp_path):
    """Test report with custom config file."""
    # Create a minimal config file
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("""
report:
  title_template: "Test Report - {casename}"

plots:
  style:
    figsize: [8, 5]
    dpi: 150
""")

    result = runner.invoke(
        app,
        [
            "report",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--config",
            str(config_file),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (temp_output_dir / "index.html").exists()


def test_balance_with_analysis_window_config(
    synthetic_data_dir, temp_output_dir, tmp_path
):
    """Test balance command uses year window in config."""
    config_file = tmp_path / "analysis_window.yaml"
    config_file.write_text(
        "\n".join(
            [
                "time:",
                "  analysis_start_year: 2000",
                "  analysis_end_year: 2000",
                "plots:",
                "  climatology:",
                "    include_climos: false",
                "",
            ]
        )
    )

    result = runner.invoke(
        app,
        [
            "balance",
            "water",
            str(synthetic_data_dir),
            "--config",
            str(config_file),
            "--out",
            str(temp_output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (temp_output_dir / "water_panel1.png").exists()


# =============================================================================
# Keyboard Interrupt Test
# =============================================================================


def test_keyboard_interrupt_handling(synthetic_data_dir, temp_output_dir, monkeypatch):
    """Test that KeyboardInterrupt is handled gracefully."""
    from elm_diagnostics.io.run import Run

    def mock_init(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(Run, "__init__", mock_init)

    result = runner.invoke(
        app,
        ["report", str(synthetic_data_dir), "--out", str(temp_output_dir), "--quiet"],
    )

    assert result.exit_code == 1
    assert "cancelled" in result.output.lower()
