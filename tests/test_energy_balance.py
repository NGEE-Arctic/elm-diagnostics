"""Tests for energy balance closure."""

import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from elm_diagnostics.balances.energy import EnergyBalance
from elm_diagnostics.io.run import Run
from tests.fixtures.synthetic_elm import (
    make_energy_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def energy_run():
    ds = make_energy_balance_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="energy_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


def test_energy_components(energy_run):
    eb = EnergyBalance(energy_run)
    comps = eb.components()
    assert "FSH" in comps
    assert "EFLX_LH_TOT" in comps
    assert "FGR" in comps
    assert "Rnet" in comps


def test_energy_residual_near_zero(energy_run):
    """Synthetic data closes the energy balance exactly."""
    eb = EnergyBalance(energy_run)
    res = eb.residual()
    max_residual = float(np.max(np.abs(res.values)))
    assert max_residual < 1e-10, (
        f"Energy balance residual too large: {max_residual:.6e} W/m2"
    )


def test_energy_plot(energy_run):
    eb = EnergyBalance(energy_run)
    fig1, fig2 = eb.plot()
    assert fig1 is not None
    assert fig2 is not None
    import matplotlib.pyplot as plt
    plt.close("all")
