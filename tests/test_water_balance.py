"""Tests for water balance closure."""

import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from elm_diagnostics.balances.water import WaterBalance
from elm_diagnostics.io.run import Run
from tests.fixtures.synthetic_elm import (
    make_water_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def water_run():
    ds = make_water_balance_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


def test_water_balance_components(water_run):
    wb = WaterBalance(water_run)
    comps = wb.components()
    assert "RAIN" in comps
    assert "SNOW" in comps
    assert "QFLX_EVAP_TOT" in comps
    assert "dS" in comps


def test_water_balance_residual_near_zero(water_run):
    """Synthetic data is constructed to close exactly."""
    wb = WaterBalance(water_run)
    res = wb.residual()
    # Residual at end of year should be very small
    final_residual = float(res.values[-1])
    assert abs(final_residual) < 1e-4, (
        f"Water balance residual too large: {final_residual:.6e} mm"
    )


def test_water_balance_plot(water_run):
    wb = WaterBalance(water_run)
    fig1, fig2 = wb.plot()
    assert fig1 is not None
    assert fig2 is not None
    import matplotlib.pyplot as plt
    plt.close("all")


def test_water_balance_to_netcdf(water_run):
    wb = WaterBalance(water_run)
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
        wb.to_netcdf(f.name)
        import xarray as xr
        ds = xr.open_dataset(f.name)
        assert "residual" in ds
        ds.close()
