"""Tests for carbon balance."""

import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from elm_diagnostics.balances.carbon import CarbonBalance
from elm_diagnostics.io.run import Run
from tests.fixtures.synthetic_elm import (
    make_carbon_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def carbon_run():
    ds = make_carbon_balance_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="carbon_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


def test_carbon_bgc_detected(carbon_run):
    cb = CarbonBalance(carbon_run)
    assert cb._detect_bgc_mode() is True


def test_carbon_components(carbon_run):
    cb = CarbonBalance(carbon_run)
    comps = cb.components()
    assert "GPP" in comps
    assert "ER" in comps
    assert "TOTECOSYSC" in comps
    assert "dTOTECOSYSC" in comps


def test_carbon_residual_near_zero(carbon_run):
    """Synthetic data closes the carbon balance exactly."""
    cb = CarbonBalance(carbon_run)
    res = cb.residual()
    final_residual = float(res.values[-1])
    assert abs(final_residual) < 0.1, (
        f"Carbon balance residual too large: {final_residual:.6e} gC/m2"
    )


def test_carbon_plot(carbon_run):
    cb = CarbonBalance(carbon_run)
    fig1, fig2 = cb.plot()
    assert fig1 is not None
    assert fig2 is not None
    import matplotlib.pyplot as plt
    plt.close("all")
