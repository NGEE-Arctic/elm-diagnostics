"""Tests for general variable plotting functions."""

import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from elm_diagnostics.io.run import Run
from elm_diagnostics.plots import (
    plot_anomaly,
    plot_diurnal,
    plot_histogram,
    plot_seasonal,
    plot_timeseries,
)
from tests.fixtures.synthetic_elm import (
    make_single_point_dataset,
    make_water_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def plot_run():
    ds = make_water_balance_dataset(start_year=2000, n_months=36)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="plot_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


@pytest.fixture
def short_run():
    ds = make_water_balance_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="short_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


def test_timeseries(short_run):
    fig = plot_timeseries(short_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_timeseries_multivar(short_run):
    """Timeseries works for different variable types."""
    for varname in ["RAIN", "SOILLIQ", "QFLX_EVAP_TOT"]:
        fig = plot_timeseries(short_run, varname)
        assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_timeseries_vertical_depth_coloring_and_legend():
    """Vertical variables should render one line per depth with a legend."""
    n_months = 24
    n_levels = 12
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.5, 1.5, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    ds = ds.assign_coords(levgrnd=np.linspace(0.02, 3.0, n_levels))

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="vertical_plot_test", tape="h0")
        run = Run(tmpdir)
        fig = plot_timeseries(run, "SOILLIQ")
        ax = fig.axes[0]

        assert len(ax.lines) == n_levels
        assert ax.get_legend() is not None
        # Legend is intentionally thinned for readability.
        assert len(ax.get_legend().get_texts()) <= 8

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_seasonal(plot_run):
    fig = plot_seasonal(plot_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_seasonal_short_data(short_run):
    """Seasonal works even with only 12 months (one year)."""
    fig = plot_seasonal(short_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_anomaly(plot_run):
    fig = plot_anomaly(plot_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_histogram(short_run):
    fig = plot_histogram(short_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_histogram_count_mode(short_run):
    fig = plot_histogram(short_run, "RAIN", density=False)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_diurnal(short_run):
    """Diurnal plot with monthly data should show 'not sub-daily' message."""
    fig = plot_diurnal(short_run, "RAIN")
    assert fig is not None
    # Should complete without error, even though data isn't sub-daily
    import matplotlib.pyplot as plt

    plt.close("all")
