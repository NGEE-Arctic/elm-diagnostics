"""Tests for the met_forcing variable group and PRECT derived variable."""

import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from elm_diagnostics.config.schema import (
    Config,
    GroupPlotTypesConfig,
    VariableGroupConfig,
    load_config,
)
from elm_diagnostics.io.derived import compute_total_precip
from elm_diagnostics.io.run import Run
from elm_diagnostics.plots import plot_histogram, plot_seasonal, plot_timeseries
from elm_diagnostics.report.build import Report
from tests.fixtures.synthetic_elm import (
    make_met_forcing_dataset,
    make_single_point_dataset,
    save_as_elm_files,
)

# Variables in the met_forcing group that are directly in the fixture
MET_DIRECT_VARS = ["TBOT", "RAIN", "SNOW", "FSDS", "FLDS", "WIND", "PBOT", "QBOT"]

# All met_forcing variables including the derived one
MET_ALL_VARS = MET_DIRECT_VARS + ["PRECT"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def met_run_short():
    """12-month run with met forcing variables."""
    ds = make_met_forcing_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="met_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


@pytest.fixture
def met_run_long():
    """36-month run — required for seasonal and anomaly plots."""
    ds = make_met_forcing_dataset(start_year=2000, n_months=36)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="met_long", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


# ---------------------------------------------------------------------------
# Derived variable: PRECT
# ---------------------------------------------------------------------------


def test_prect_derived_from_run(met_run_short):
    """run.get('PRECT') succeeds via derived path when RAIN and SNOW are present."""
    prect = met_run_short.get("PRECT")
    assert prect is not None
    assert prect.name == "PRECT"
    rain = met_run_short.get("RAIN")
    snow = met_run_short.get("SNOW")
    np.testing.assert_allclose(prect.values, (rain + snow).values, rtol=1e-10)


def test_prect_attrs(met_run_short):
    """PRECT carries expected metadata attributes."""
    prect = met_run_short.get("PRECT")
    assert prect.attrs.get("units") == "mm/s"
    assert "total precipitation" in prect.attrs.get("long_name", "").lower()


def test_prect_missing_rain():
    """compute_total_precip raises ValueError when RAIN is absent."""
    ds = make_single_point_dataset(
        start_year=2000,
        n_months=12,
        variables={
            "SNOW": {
                "data": np.zeros(12),
                "units": "mm/s",
                "cell_methods": "time: mean",
            }
        },
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="no_rain", tape="h0")
        run = Run(tmpdir)
        with pytest.raises(ValueError, match="RAIN"):
            compute_total_precip(run)
        run.close()


def test_prect_missing_snow():
    """compute_total_precip raises ValueError when SNOW is absent."""
    ds = make_single_point_dataset(
        start_year=2000,
        n_months=12,
        variables={
            "RAIN": {
                "data": np.zeros(12),
                "units": "mm/s",
                "cell_methods": "time: mean",
            }
        },
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="no_snow", tape="h0")
        run = Run(tmpdir)
        with pytest.raises(ValueError, match="SNOW"):
            compute_total_precip(run)
        run.close()


# ---------------------------------------------------------------------------
# Default config includes met_forcing group
# ---------------------------------------------------------------------------


def test_default_config_has_met_forcing_group():
    """Default config loads with a met_forcing variable group."""
    config = load_config()
    assert "met_forcing" in config.variable_groups


def test_met_forcing_group_variables():
    """met_forcing group contains all expected variables."""
    config = load_config()
    vg = config.variable_groups["met_forcing"]
    expected = {"TBOT", "RAIN", "SNOW", "PRECT", "FSDS", "FLDS", "WIND", "PBOT", "QBOT"}
    assert expected.issubset(set(vg.variables))


def test_met_forcing_plot_types():
    """met_forcing group enables timeseries, seasonal, histogram; disables others."""
    config = load_config()
    pt = config.variable_groups["met_forcing"].plot_types
    assert pt.timeseries is True
    assert pt.seasonal is True
    assert pt.histogram is True
    assert pt.hovmuller is False
    assert pt.anomaly is False
    assert pt.diurnal is False


# ---------------------------------------------------------------------------
# Timeseries plots for each met variable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("varname", MET_DIRECT_VARS)
def test_timeseries_each_met_var(met_run_short, varname):
    """plot_timeseries works for every direct met forcing variable."""
    fig = plot_timeseries(met_run_short, varname)
    assert fig is not None
    plt.close("all")


def test_timeseries_prect_derived(met_run_short):
    """plot_timeseries works for derived PRECT."""
    fig = plot_timeseries(met_run_short, "PRECT")
    assert fig is not None
    plt.close("all")


# ---------------------------------------------------------------------------
# Seasonal cycle plots for each met variable (needs ≥12 months)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("varname", MET_DIRECT_VARS)
def test_seasonal_each_met_var(met_run_long, varname):
    """plot_seasonal works for every direct met forcing variable (36-month run)."""
    fig = plot_seasonal(met_run_long, varname)
    assert fig is not None
    plt.close("all")


def test_seasonal_prect_derived(met_run_long):
    """plot_seasonal works for derived PRECT."""
    fig = plot_seasonal(met_run_long, "PRECT")
    assert fig is not None
    plt.close("all")


# ---------------------------------------------------------------------------
# Histogram plots for each met variable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("varname", MET_DIRECT_VARS)
def test_histogram_each_met_var(met_run_long, varname):
    """plot_histogram works for every direct met forcing variable."""
    fig = plot_histogram(met_run_long, varname)
    assert fig is not None
    plt.close("all")


def test_histogram_prect_derived(met_run_long):
    """plot_histogram works for derived PRECT."""
    fig = plot_histogram(met_run_long, "PRECT")
    assert fig is not None
    plt.close("all")


# ---------------------------------------------------------------------------
# Report integration: met_forcing section appears in HTML output
# ---------------------------------------------------------------------------


def test_met_forcing_in_report():
    """Report.build() includes a Met Forcing section when the group is enabled."""
    ds = make_met_forcing_dataset(start_year=2000, n_months=24)
    with tempfile.TemporaryDirectory() as rundir:
        save_as_elm_files(ds, Path(rundir), casename="met_report_test", tape="h0")
        run = Run(rundir)

        # Use a config with only met_forcing group enabled to keep the test fast
        config = Config(
            variable_groups={
                "met_forcing": VariableGroupConfig(
                    enabled=True,
                    variables=["TBOT", "RAIN", "SNOW", "PRECT"],
                    plot_types=GroupPlotTypesConfig(
                        timeseries=True,
                        seasonal=True,
                        histogram=True,
                        hovmuller=False,
                        anomaly=False,
                        diurnal=False,
                    ),
                )
            }
        )
        # Disable balance sections so the report builds quickly on minimal data
        config.report.sections.water_balance = False
        config.report.sections.energy_balance = False
        config.report.sections.carbon_balance = False

        rpt = Report(run, config=config)
        with tempfile.TemporaryDirectory() as outdir:
            html_path = rpt.build(outdir)
            assert html_path.exists()
            content = html_path.read_text()
            # Section heading uses the group name, title-cased
            assert "Met Forcing" in content or "met_forcing" in content

        run.close()

    plt.close("all")
