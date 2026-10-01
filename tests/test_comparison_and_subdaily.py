"""Characterization tests for Comparison alignment, sub-daily plots, and dt fallback."""

import cftime
import matplotlib.pyplot as plt
import numpy as np
import pytest
import xarray as xr

from elm_diagnostics import Comparison, Run
from elm_diagnostics.config.schema import load_config
from elm_diagnostics.plots import plot_diurnal
from elm_diagnostics.time.integration import get_time_deltas
from tests.fixtures.synthetic_elm import make_water_balance_dataset, save_as_elm_files


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _write_hourly_run(outdir, casename, scale=1.0, n_days=3):
    """Write an hourly single-point h1 stream (one file per day)."""
    outdir.mkdir(parents=True)
    enc = {
        "time": {"units": "days since 2001-01-01", "calendar": "noleap"},
        "time_bounds": {"units": "days since 2001-01-01", "calendar": "noleap"},
    }
    hours = np.arange(24)
    for day in range(n_days):
        start = cftime.DatetimeNoLeap(2001, 1, 1 + day)
        lo = np.array([start + np.timedelta64(int(h), "h").item() for h in hours])
        hi = np.array([t + np.timedelta64(1, "h").item() for t in lo])
        mid = np.array([t + np.timedelta64(30, "m").item() for t in lo])
        fsh = scale * (100.0 * np.sin((hours - 6) / 24 * 2 * np.pi) + day)
        ds = xr.Dataset(
            {
                "FSH": (("time", "lndgrid"), fsh[:, None], {"units": "W/m^2"}),
                "time_bounds": (("time", "hist_interval"), np.stack([lo, hi], 1)),
            },
            coords={"time": mid},
        )
        ds.to_netcdf(
            outdir / f"{casename}.elm.h1.{start.strftime('%Y-%m-%d')}-00000.nc",
            encoding=enc,
        )
    return Run(outdir)


@pytest.fixture
def monthly_runs(tmp_path):
    ds = make_water_balance_dataset(n_months=36)
    save_as_elm_files(ds, tmp_path / "a", casename="full")
    save_as_elm_files(ds.isel(time=slice(12, 24)), tmp_path / "b", casename="middle")
    return Run(tmp_path / "a"), Run(tmp_path / "b")


# --------------------------------------------------------------------------
# Comparison.get
# --------------------------------------------------------------------------


def test_comparison_intersect_keeps_overlapping_times(monthly_runs):
    full, middle = monthly_runs
    base, exp = Comparison(full, middle).get("RAIN")

    assert base.sizes["time"] == exp.sizes["time"] == 12
    np.testing.assert_array_equal(base.time.values, exp.time.values)
    np.testing.assert_allclose(base.values, exp.values)


def test_comparison_union_pads_missing_times_with_nan(monthly_runs):
    full, middle = monthly_runs
    base, exp = Comparison(full, middle, align="union").get("RAIN")

    assert base.sizes["time"] == exp.sizes["time"] == 36
    assert np.isnan(exp.values[:12]).all()
    assert np.isfinite(exp.values[12:24]).all()
    assert np.isfinite(base.values).all()


def test_comparison_repr(monthly_runs):
    full, middle = monthly_runs
    assert repr(Comparison(full, middle)) == (
        "Comparison(base='full', experiment='middle', align='intersect')"
    )


# --------------------------------------------------------------------------
# plot_diurnal
# --------------------------------------------------------------------------


def test_diurnal_run_mean_matches_hourly_climatology(tmp_path):
    run = _write_hourly_run(tmp_path / "h", "hourly")
    fig = plot_diurnal(run, "FSH", config=load_config())
    ax = fig.axes[0]
    expected = run.get("FSH").squeeze("lndgrid", drop=True).groupby("time.hour").mean()

    line = ax.lines[0]
    np.testing.assert_allclose(line.get_xdata(), expected.hour.values)
    np.testing.assert_allclose(line.get_ydata(), expected.values)


def test_diurnal_comparison_overlays_both_runs(tmp_path):
    run_a = _write_hourly_run(tmp_path / "a", "hourly_a")
    run_b = _write_hourly_run(tmp_path / "b", "hourly_b", scale=2.0)
    fig = plot_diurnal(Comparison(run_a, run_b), "FSH", config=load_config())

    labels = [ln.get_label() for ln in fig.axes[0].lines]
    assert labels == ["hourly_a", "hourly_b"]


def test_diurnal_monthly_data_shows_notice(monthly_runs):
    full, _ = monthly_runs
    fig = plot_diurnal(full, "RAIN", config=load_config())
    texts = [t.get_text() for t in fig.axes[0].texts]

    assert texts == ["Data is not sub-daily\n(need hourly or finer resolution)"]


# --------------------------------------------------------------------------
# get_time_deltas without time bounds
# --------------------------------------------------------------------------


def test_time_deltas_without_bounds_repeat_last_diff():
    times = xr.date_range(
        "2000-01-01", periods=3, freq="D", calendar="noleap", use_cftime=True
    )
    dt = get_time_deltas(xr.Dataset(coords={"time": times}))

    np.testing.assert_allclose(dt.values, [86400.0, 86400.0, 86400.0])


def test_time_deltas_single_step_without_bounds_assumes_30_days():
    times = xr.date_range("2000-01-01", periods=1, calendar="noleap", use_cftime=True)
    dt = get_time_deltas(xr.Dataset(coords={"time": times}))

    np.testing.assert_allclose(dt.values, [30 * 86400.0])


def test_time_deltas_numeric_bounds_small_values_are_days():
    ds = xr.Dataset(
        {"time_bnds": (("time", "nb"), np.array([[0.0, 1.0], [1.0, 3.0]]))},
        coords={"time": [0.5, 2.0]},
    )
    np.testing.assert_allclose(get_time_deltas(ds).values, [86400.0, 172800.0])


def test_time_deltas_numeric_bounds_large_values_are_seconds():
    ds = xr.Dataset(
        {"time_bnds": (("time", "nb"), np.array([[0.0, 3600.0], [3600.0, 9000.0]]))},
        coords={"time": [1800.0, 6300.0]},
    )
    np.testing.assert_allclose(get_time_deltas(ds).values, [3600.0, 5400.0])
