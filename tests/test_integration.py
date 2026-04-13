"""Tests for time-bounds-aware integration."""

import numpy as np
import xarray as xr

from elm_diagnostics.time.integration import (
    cumulative_integral,
    get_time_deltas,
    storage_change,
)
from tests.fixtures.synthetic_elm import make_water_balance_dataset


def test_get_time_deltas_from_bounds():
    ds = make_water_balance_dataset(n_months=3)
    dt = get_time_deltas(ds)
    assert len(dt) == 3
    # January = 31 days = 31*86400 seconds
    assert abs(dt.values[0] - 31 * 86400) < 1


def test_get_time_deltas_nonuniform():
    """Verify that dt varies between months (not assumed uniform)."""
    ds = make_water_balance_dataset(n_months=12)
    dt = get_time_deltas(ds)
    # Feb (28 days) != Jan (31 days) != Apr (30 days)
    unique_dts = len(set(dt.values))
    assert unique_dts > 1, "Time deltas should not all be the same"


def test_cumulative_integral_simple():
    """A constant flux integrated cumulatively, starting at 0."""
    ds = make_water_balance_dataset(n_months=3)
    da = ds["RAIN"].isel(lat=0, lon=0) * 0 + 1e-5  # constant 1e-5 mm/s
    da.attrs["units"] = "mm/s"
    result = cumulative_integral(da, ds)
    dt = get_time_deltas(ds)
    raw_cumsum = np.cumsum(1e-5 * dt.values)
    # cumulative_integral starts at 0 (same reference as storage_change)
    expected = raw_cumsum - raw_cumsum[0]
    np.testing.assert_allclose(result.values, expected, rtol=1e-10)
    assert result.values[0] == 0.0


def test_cumulative_integral_updates_units():
    ds = make_water_balance_dataset(n_months=3)
    da = ds["RAIN"].isel(lat=0, lon=0)
    result = cumulative_integral(da, ds)
    assert "/s" not in result.attrs.get("units", "/s")


def test_storage_change():
    ds = make_water_balance_dataset(n_months=6)
    da = ds["SOILLIQ"].isel(lat=0, lon=0)
    dS = storage_change(da)
    # First value should be 0
    assert abs(dS.values[0]) < 1e-12
    # Last value should be da[-1] - da[0]
    expected = da.values[-1] - da.values[0]
    np.testing.assert_allclose(dS.values[-1], expected, rtol=1e-10)
