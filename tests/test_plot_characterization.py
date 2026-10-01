"""Characterization tests for plot contents.

These pin what each plot actually draws (line/bar/mesh data, labels, titles)
for Run and Comparison sources, with and without sub-gridcell faceting, so
refactors of the plotting modules can't silently change figures.
"""

import matplotlib.pyplot as plt
import numpy as np
import pytest

from elm_diagnostics import Comparison, Run
from elm_diagnostics.config.schema import load_config
from elm_diagnostics.plots import (
    plot_anomaly,
    plot_histogram,
    plot_hovmuller,
    plot_seasonal,
    plot_timeseries,
)
from tests.fixtures.synthetic_elm import (
    make_multicolumn_dataset,
    make_vertical_profile_dataset,
    make_water_balance_dataset,
    save_as_elm_files,
)

N_MONTHS = 36


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def point_runs(tmp_path):
    """Two single-point runs with different RAIN."""
    ds = make_water_balance_dataset(n_months=N_MONTHS)
    save_as_elm_files(ds, tmp_path / "a", casename="point_a")
    ds_b = ds.copy()
    ds_b["RAIN"] = ds["RAIN"] * 1.5
    save_as_elm_files(ds_b, tmp_path / "b", casename="point_b")
    return Run(tmp_path / "a"), Run(tmp_path / "b")


@pytest.fixture
def column_runs(tmp_path):
    """Two 3-column runs (perfect and imperfect closure)."""
    save_as_elm_files(
        make_multicolumn_dataset(n_columns=3, n_months=N_MONTHS),
        tmp_path / "ca",
        casename="cols_a",
    )
    save_as_elm_files(
        make_multicolumn_dataset(n_columns=3, n_months=N_MONTHS, perfect_closure=False),
        tmp_path / "cb",
        casename="cols_b",
    )
    return Run(tmp_path / "ca"), Run(tmp_path / "cb")


@pytest.fixture
def profile_runs(tmp_path):
    ds = make_vertical_profile_dataset(n_months=N_MONTHS)
    save_as_elm_files(ds, tmp_path / "pa", casename="prof_a")
    ds_b = ds.copy()
    ds_b["SOILLIQ"] = ds["SOILLIQ"] * 1.1
    save_as_elm_files(ds_b, tmp_path / "pb", casename="prof_b")
    return Run(tmp_path / "pa"), Run(tmp_path / "pb")


def _point_values(run, varname):
    return run.get(varname).squeeze(("lat", "lon"), drop=True).values


def _annual_anomalies(run, varname):
    da = run.get(varname).squeeze(("lat", "lon"), drop=True)
    annual = da.groupby("time.year").mean().values
    return annual - annual.mean()


# --------------------------------------------------------------------------
# timeseries
# --------------------------------------------------------------------------


def test_timeseries_run_draws_data_and_labels(point_runs, config):
    run, _ = point_runs
    fig = plot_timeseries(run, "RAIN", config=config)
    ax = fig.axes[0]

    np.testing.assert_allclose(ax.lines[0].get_ydata(), _point_values(run, "RAIN"))
    assert ax.get_ylabel() == "RAIN (mm/s)"
    assert ax.get_title().startswith("RAIN — point_a")
    assert ax.get_xlabel() == "Time"


def test_timeseries_comparison_overlays_both_runs(point_runs, config):
    run_a, run_b = point_runs
    fig = plot_timeseries(Comparison(run_a, run_b), "RAIN", config=config)
    ax = fig.axes[0]

    labels = [line.get_label() for line in ax.lines]
    assert labels == ["point_a", "point_b"]
    np.testing.assert_allclose(ax.lines[0].get_ydata(), _point_values(run_a, "RAIN"))
    np.testing.assert_allclose(ax.lines[1].get_ydata(), _point_values(run_b, "RAIN"))
    assert "point_a vs point_b" in ax.get_title()


def test_timeseries_faceted_by_column(column_runs, config):
    run, _ = column_runs
    fig = plot_timeseries(run, "RAIN", by="column", config=config)
    visible = [ax for ax in fig.axes if ax.get_visible() and ax.lines]

    assert [ax.get_title() for ax in visible] == ["Column 1", "Column 2", "Column 3"]
    rain = run.get("RAIN")
    for col, ax in zip((1, 2, 3), visible):
        np.testing.assert_allclose(
            ax.lines[0].get_ydata(), rain.sel(column=col).squeeze(drop=True).values
        )
    assert fig._suptitle.get_text() == "RAIN by column — cols_a"


def test_timeseries_faceted_comparison_has_two_lines_per_column(column_runs, config):
    run_a, run_b = column_runs
    fig = plot_timeseries(Comparison(run_a, run_b), "RAIN", by="column", config=config)
    visible = [ax for ax in fig.axes if ax.get_visible() and ax.lines]

    assert len(visible) == 3
    for ax in visible:
        assert [line.get_label() for line in ax.lines] == ["cols_a", "cols_b"]


def test_timeseries_multilevel_draws_one_line_per_level(profile_runs, config):
    run, _ = profile_runs
    fig = plot_timeseries(run, "SOILLIQ", config=config)
    ax = fig.axes[0]
    soilliq = run.get("SOILLIQ").squeeze(("lat", "lon"), drop=True)

    assert len(ax.lines) == soilliq.sizes["levgrnd"]
    np.testing.assert_allclose(ax.lines[0].get_ydata(), soilliq.isel(levgrnd=0).values)


# --------------------------------------------------------------------------
# seasonal
# --------------------------------------------------------------------------


def test_seasonal_run_mean_line_matches_monthly_climatology(point_runs, config):
    run, _ = point_runs
    fig = plot_seasonal(run, "RAIN", config=config)
    ax = fig.axes[0]
    da = run.get("RAIN").squeeze(("lat", "lon"), drop=True)
    expected = da.groupby("time.month").mean().values

    mean_lines = [ln for ln in ax.lines if "mean" in ln.get_label().lower()]
    assert len(mean_lines) == 1
    np.testing.assert_allclose(mean_lines[0].get_xdata(), np.arange(1, 13))
    np.testing.assert_allclose(mean_lines[0].get_ydata(), expected)
    # 3 years <= default threshold: one thin line per year plus the mean
    assert len(ax.lines) == 3 + 1
    assert mean_lines[0].get_label() == "Mean (3 years)"


def test_seasonal_comparison_labels_both_runs(point_runs, config):
    run_a, run_b = point_runs
    fig = plot_seasonal(Comparison(run_a, run_b), "RAIN", config=config)
    labels = [
        ln.get_label() for ln in fig.axes[0].lines if not ln.get_label().startswith("_")
    ]

    assert labels == ["point_a mean (3 years)", "point_b mean (3 years)"]


def test_seasonal_faceted_by_column(column_runs, config):
    run, _ = column_runs
    fig = plot_seasonal(run, "RAIN", by="column", config=config)
    visible = [ax for ax in fig.axes if ax.get_visible() and ax.lines]

    assert [ax.get_title() for ax in visible] == ["Column 1", "Column 2", "Column 3"]
    rain = run.get("RAIN")
    for col, ax in zip((1, 2, 3), visible):
        expected = rain.sel(column=col).squeeze(drop=True).groupby("time.month").mean()
        np.testing.assert_allclose(ax.lines[-1].get_ydata(), expected.values)


# --------------------------------------------------------------------------
# anomaly
# --------------------------------------------------------------------------


def test_anomaly_run_bars_are_annual_anomalies(point_runs, config):
    run, _ = point_runs
    fig = plot_anomaly(run, "RAIN", config=config)
    ax = fig.axes[0]
    heights = [p.get_height() for p in ax.patches]

    np.testing.assert_allclose(heights, _annual_anomalies(run, "RAIN"))
    assert ax.get_xlabel() == "Year"


def test_anomaly_comparison_bars_are_difference_of_anomalies(point_runs, config):
    run_a, run_b = point_runs
    fig = plot_anomaly(Comparison(run_a, run_b), "RAIN", config=config)
    heights = [p.get_height() for p in fig.axes[0].patches]
    expected = _annual_anomalies(run_b, "RAIN") - _annual_anomalies(run_a, "RAIN")

    np.testing.assert_allclose(heights, expected)
    assert "(exp - base)" in fig.axes[0].get_title()


def test_anomaly_faceted_by_column(column_runs, config):
    run, _ = column_runs
    fig = plot_anomaly(run, "RAIN", by="column", config=config)
    visible = [ax for ax in fig.axes if ax.get_visible() and ax.patches]

    assert len(visible) == 3
    rain = run.get("RAIN")
    for col, ax in zip((1, 2, 3), visible):
        annual = rain.sel(column=col).squeeze(drop=True).groupby("time.year").mean()
        np.testing.assert_allclose(
            [p.get_height() for p in ax.patches], annual.values - annual.values.mean()
        )


# --------------------------------------------------------------------------
# histogram
# --------------------------------------------------------------------------


def test_histogram_run_is_normalized_density(point_runs, config):
    run, _ = point_runs
    fig = plot_histogram(run, "RAIN", config=config)
    patches = fig.axes[0].patches

    assert len(patches) == 50
    area = sum(p.get_height() * p.get_width() for p in patches)
    assert area == pytest.approx(1.0)


def test_histogram_comparison_draws_two_distributions(point_runs, config):
    run_a, run_b = point_runs
    fig = plot_histogram(Comparison(run_a, run_b), "RAIN", config=config)
    ax = fig.axes[0]

    legend = [t.get_text() for t in ax.get_legend().get_texts()]
    assert legend == ["point_a", "point_b"]


# --------------------------------------------------------------------------
# hovmuller
# --------------------------------------------------------------------------


def test_hovmuller_run_mesh_holds_depth_time_field(profile_runs, config):
    run, _ = profile_runs
    fig = plot_hovmuller(run, "SOILLIQ", config=config)
    ax = fig.axes[0]
    field = (
        run.get("SOILLIQ")
        .squeeze(("lat", "lon"), drop=True)
        .transpose("levgrnd", "time")
    )

    mesh = ax.collections[0]
    np.testing.assert_allclose(
        np.asarray(mesh.get_array()).ravel(), field.values.ravel()
    )
    assert ax.yaxis_inverted()
    assert ax.get_ylabel().startswith("Depth")


def test_hovmuller_comparison_shares_color_limits(profile_runs, config):
    run_a, run_b = profile_runs
    fig = plot_hovmuller(Comparison(run_a, run_b), "SOILLIQ", config=config)
    meshes = [ax.collections[0] for ax in fig.axes[:2]]

    assert len(meshes) == 2
    assert meshes[0].norm.vmin == meshes[1].norm.vmin
    assert meshes[0].norm.vmax == meshes[1].norm.vmax
    assert [ax.get_title() for ax in fig.axes[:2]] == ["prof_a", "prof_b"]
