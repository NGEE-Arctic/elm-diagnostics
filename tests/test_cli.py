"""Tests for CLI commands."""

from __future__ import annotations

import os
import signal
import subprocess

import pytest
from typer.testing import CliRunner

from elm_diagnostics.cli import _resolve_analysis_year_filter, app
from tests.fixtures.synthetic_elm import (
    make_carbon_balance_dataset,
    make_energy_balance_dataset,
    make_water_balance_dataset,
    save_as_elm_files,
)

runner = CliRunner()

# Subprocess timeouts. CI runners are much slower and far more variable than a dev
# laptop, so allow generous budgets and let them be tuned via the environment.
CLI_HELP_TIMEOUT = int(os.environ.get("ELM_DIAGNOSTICS_TEST_HELP_TIMEOUT", "60"))
CLI_REPORT_TIMEOUT = int(os.environ.get("ELM_DIAGNOSTICS_TEST_REPORT_TIMEOUT", "600"))


def run_cli(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run the installed ``elm-diagnostics`` console script, dumping stacks on hang.

    ``report`` has hung on CI a handful of times: the run never finishes, while
    every other test on the same runner keeps normal pace, so it is a deadlock
    rather than a slow machine. Plot rendering pulls data through dask's threaded
    scheduler onto netCDF4/HDF5, which serializes on a global lock, and that
    combination is a known intermittent-deadlock surface.

    A bare ``TimeoutExpired`` says nothing about where the process was stuck, so
    run the child with faulthandler enabled and SIGABRT it on timeout. That makes
    it print a traceback for every thread, turning the next occurrence into a
    diagnosis instead of another blind timeout bump.
    """
    env = dict(os.environ, PYTHONFAULTHANDLER="1")
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGABRT)
        try:
            _, stacks = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stacks = proc.communicate()
            stacks = f"(child ignored SIGABRT; killed)\n{stacks}"
        pytest.fail(
            f"{' '.join(args)} did not finish within {timeout}s.\n"
            f"Thread stacks at the time of the hang:\n{stacks}"
        )
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


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
        "time:\n  analysis_start_year: 2000\n  analysis_end_year: 2000\n  water_year_start_month: 10\nplots:\n  climatology:\n    include_climos: false\n"
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
        "time:\n  analysis_start_year: 2000\n  analysis_end_year: 2000\n  water_year_start_month: 10\nplots:\n  climatology:\n    include_climos: false\n"
    )

    lo, hi = _resolve_analysis_year_filter(str(cfg))
    assert (lo, hi) == (1999, 2000)


def test_analysis_year_filter_uses_config_window(tmp_path):
    """Year narrowing should honor config start/end year bounds."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "time:\n  analysis_start_year: 1990\n  analysis_end_year: 1995\n  water_year_start_month: 1\nplots:\n  climatology:\n    include_climos: false\n"
    )

    lo, hi = _resolve_analysis_year_filter(str(cfg))
    assert (lo, hi) == (1990, 1995)


def test_last_n_years_not_overridden_by_default_climatology(tmp_path):
    """--last-n-years must win over climatology's 'use all years' widening.

    Regression: with the default config (include_climos=True and
    climo_start/end_year == -1, meaning "all available years"), the climatology
    branch reset the resolved window to (None, None), silently discarding an
    explicit --last-n-years request and loading every file.
    """
    from pathlib import Path

    # Minimal ELM-like files spanning three years so max-year detection works.
    for year in (2010, 2011, 2012):
        (tmp_path / f"case.elm.h0.{year}-01-01-00000.nc").write_bytes(b"")

    # Default config: climatology enabled with the -1 "all years" sentinel and
    # a water-year start month of October (prior year is pulled in).
    lo, hi = _resolve_analysis_year_filter(
        None, last_n_years=1, elm_path=Path(tmp_path)
    )

    assert hi == 2012, f"expected max year 2012, got {hi}"
    # Window must be bounded (not None) — i.e. --last-n-years was honored.
    assert lo is not None and hi is not None, (
        f"--last-n-years was discarded: got ({lo}, {hi})"
    )
    # last_n_years=1 -> 2012; October water year pulls in the prior year 2011.
    assert lo == 2011, f"expected lower bound 2011 (water-year prev), got {lo}"


# =============================================================================
# Comparison Mode Tests
# =============================================================================


def test_report_comparison(synthetic_data_dir, tmp_path, temp_output_dir):
    """Test --compare flag for comparison report."""
    # Create a second synthetic dataset
    compare_dir = tmp_path / "compare_data"
    compare_dir.mkdir()

    # We need to import and create another dataset
    import numpy as np

    from tests.fixtures.synthetic_elm import make_single_point_dataset

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
    result = run_cli(["elm-diagnostics", "--help"], timeout=CLI_HELP_TIMEOUT)
    assert result.returncode == 0
    assert "Diagnostics and budget-closure" in result.stdout


def test_cli_entry_point_version():
    """Integration test: verify CLI entry point works."""
    result = run_cli(["elm-diagnostics", "--help"], timeout=CLI_HELP_TIMEOUT)
    assert result.returncode == 0
    assert "report" in result.stdout
    assert "balance" in result.stdout
    assert "plot" in result.stdout


@pytest.mark.slow
def test_cli_end_to_end_subprocess(synthetic_data_dir, temp_output_dir, tmp_path):
    """Integration test: report generation via the installed console script.

    This test exists to verify the packaging path — that ``elm-diagnostics`` is
    on PATH, imports cleanly in a fresh interpreter, and writes a report — not
    to re-check plot content. The variable-group sections render ~250 figures
    and account for the large majority of report runtime, so they are disabled
    here; ``test_report_command_basic`` still exercises the full default report
    in-process. Balance sections are kept so the run remains a real report.
    """
    env = os.environ.copy()
    # Use synchronous scheduler to prevent dask threading issues
    env["DASK_SCHEDULER"] = "synchronous"
    # Ensure matplotlib uses non-interactive backend
    env["MPLBACKEND"] = "Agg"
    # Limit threads to prevent resource contention in CI
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"

    config_file = tmp_path / "end_to_end_config.yaml"
    config_file.write_text(
        """
report:
  sections:
    variable_groups: false
  thumbnails:
    enabled: false
"""
    )

    result = subprocess.run(
        [
            "elm-diagnostics",
            "report",
            str(synthetic_data_dir),
            "--out",
            str(temp_output_dir),
            "--config",
            str(config_file),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=CLI_REPORT_TIMEOUT,
        check=False,
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
        "time:\n  analysis_start_year: 2000\n  analysis_end_year: 2000\nplots:\n  climatology:\n    include_climos: false\n"
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
# Last N Years Tests
# =============================================================================


def test_compute_max_year_from_files():
    """Test _compute_max_year_from_files helper function."""
    from pathlib import Path

    from elm_diagnostics.cli import _compute_max_year_from_files

    # Use real test data
    test_data_path = Path(__file__).parent / "fixtures" / "data"
    max_year = _compute_max_year_from_files(test_data_path)
    assert max_year == 2001


def test_last_n_years_report(tmp_path):
    """Test report command with --last-n-years option."""
    from pathlib import Path

    # Use real test data that spans multiple years
    test_data_path = Path(__file__).parent / "fixtures" / "data"
    out_dir = tmp_path / "report_output"

    result = runner.invoke(
        app,
        [
            "report",
            str(test_data_path),
            "--out",
            str(out_dir),
            "--last-n-years",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (out_dir / "index.html").exists()


def test_last_n_years_balance(tmp_path):
    """Test balance command with --last-n-years option."""
    from pathlib import Path

    test_data_path = Path(__file__).parent / "fixtures" / "data"
    out_dir = tmp_path / "balance_output"

    result = runner.invoke(
        app,
        [
            "balance",
            "water",
            str(test_data_path),
            "--out",
            str(out_dir),
            "--last-n-years",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (out_dir / "water_panel1.png").exists()


def test_last_n_years_plot(tmp_path):
    """Test plot command with --last-n-years option."""
    from pathlib import Path

    test_data_path = Path(__file__).parent / "fixtures" / "data"
    out_file = tmp_path / "gpp_last_n_years.png"

    result = runner.invoke(
        app,
        [
            "plot",
            "GPP",
            str(test_data_path),
            "--out",
            str(out_file),
            "--last-n-years",
            "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()


def test_last_n_years_filters_files_correctly(tmp_path):
    """Test that --last-n-years actually filters files before loading."""
    from pathlib import Path

    from elm_diagnostics.io.run import Run

    test_data_path = Path(__file__).parent / "fixtures" / "data"

    # Load with all years
    run_all = Run(str(test_data_path))
    all_files = run_all._stream_files["h0"]
    run_all.close()

    # Load with last 1 year only
    run_last1 = Run(str(test_data_path), analysis_year_min=2001, analysis_year_max=2001)
    last1_files = run_last1._stream_files["h0"]
    run_last1.close()

    # Should have fewer files when filtered
    assert len(last1_files) < len(all_files)
    # Should only have files from 2001
    for f in last1_files:
        assert "2001" in f.name


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
