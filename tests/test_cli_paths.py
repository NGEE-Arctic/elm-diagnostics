"""Characterization tests for CLI error paths and non-quiet output.

Some assertions pin current, known-buggy behavior (see REFACTOR_NOTES.md B1/B2)
so that fixing those bugs is a deliberate, visible change to these tests.
"""

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
def data_dir(tmp_path):
    ds = make_water_balance_dataset(n_months=24)
    for extra in (
        make_energy_balance_dataset(n_months=24),
        make_carbon_balance_dataset(n_months=24),
    ):
        for name in extra.data_vars:
            if name not in ds:
                ds[name] = extra[name]
    save_as_elm_files(ds, tmp_path / "run", casename="clicase")
    return tmp_path / "run"


@pytest.fixture
def small_config(tmp_path):
    path = tmp_path / "small.yaml"
    path.write_text(
        "report:\n"
        "  performance:\n"
        "    parallel_plot_workers: 1\n"
        "variable_groups:\n"
        "  hydrology: {enabled: false}\n"
        "  carbon_pools: {enabled: false}\n"
        "  carbon_fluxes: {enabled: false}\n"
        "  energy: {enabled: false}\n"
        "  soil_state: {enabled: false}\n"
        "  vegetation: {enabled: false}\n"
        "  met_forcing:\n"
        "    variables: [RAIN]\n"
        "    plot_types: {seasonal: false, histogram: false}\n"
    )
    return path


# --------------------------------------------------------------------------
# Error paths
# --------------------------------------------------------------------------


def test_plot_kind_diurnal_is_rejected(data_dir):
    # B1: diurnal is advertised in --help but not accepted.
    result = runner.invoke(app, ["plot", "GPP", str(data_dir), "--kind", "diurnal"])

    assert result.exit_code == 1
    assert "Unknown plot kind: diurnal" in result.output
    assert "Valid options: timeseries, hovmuller, seasonal, anomaly, histogram" in (
        result.output
    )
    # B2: the generic handler also fires after the specific message.
    assert "Run with --debug for full traceback" in result.output


def test_missing_path_reports_directory_not_found():
    result = runner.invoke(app, ["plot", "GPP", "/nonexistent/elm/output"])

    assert result.exit_code == 1
    assert "Directory not found: /nonexistent/elm/output" in result.output


def test_verbose_and_quiet_conflict_before_loading(data_dir):
    for command in (["plot", "GPP"], ["balance", "water"], ["report"]):
        result = runner.invoke(app, [*command, str(data_dir), "-v", "-q"])
        assert result.exit_code == 1
        assert "Cannot specify both --verbose and --quiet" in result.output


def test_unknown_balance_type(data_dir):
    result = runner.invoke(app, ["balance", "bogus", str(data_dir)])

    assert result.exit_code == 1
    assert "Unknown balance type: bogus" in result.output
    assert "Valid options: water, carbon, energy" in result.output


def test_missing_variable_is_reported(data_dir, tmp_path):
    result = runner.invoke(
        app, ["plot", "NOPE", str(data_dir), "--out", str(tmp_path / "x.png")]
    )

    assert result.exit_code == 1
    assert "'NOPE' not found in any stream" in result.output
    assert not (tmp_path / "x.png").exists()


# --------------------------------------------------------------------------
# Non-quiet success paths
# --------------------------------------------------------------------------


def test_balance_water_non_quiet(data_dir, tmp_path):
    out = tmp_path / "bal"
    result = runner.invoke(app, ["balance", "water", str(data_dir), "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert "Generating plots..." in result.output
    assert "Saved to" in result.output
    assert sorted(p.name for p in out.iterdir()) == [
        "water_balance.nc",
        "water_panel1.png",
        "water_panel2.png",
        "water_panel3.png",
        "water_panel4.png",
    ]


def test_plot_seasonal_non_quiet(data_dir, tmp_path):
    out = tmp_path / "p.png"
    result = runner.invoke(
        app, ["plot", "RAIN", str(data_dir), "--kind", "seasonal", "--out", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert "Generating seasonal plot for RAIN..." in result.output
    assert out.exists()


def test_report_compare(data_dir, tmp_path, small_config):
    out = tmp_path / "rpt"
    result = runner.invoke(
        app,
        [
            "report",
            str(data_dir),
            "--compare",
            str(data_dir),
            "--out",
            str(out),
            "--config",
            str(small_config),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Building diagnostics report..." in result.output
    assert "Report generated:" in result.output
    assert "Section timings" in result.output
    html = (out / "index.html").read_text()
    assert "Base vs. Experiment" in html
    assert (out / "met-forcing.html").exists()
