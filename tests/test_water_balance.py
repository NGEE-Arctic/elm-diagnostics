"""Tests for water balance closure."""

import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from elm_diagnostics.balances.water import WaterBalance
from elm_diagnostics.config.schema import Config
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


@pytest.fixture
def water_run_with_model_residual():
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_model_residual=True,
        include_snow_residual=True,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_model_res", tape="h0")
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
    fig1, fig2, fig3, fig4 = wb.plot()
    assert fig1 is not None
    assert fig2 is not None
    assert fig3 is not None
    assert fig4 is not None
    import matplotlib.pyplot as plt
    plt.close("all")


def test_water_balance_model_residual_absent_returns_none(water_run):
    wb = WaterBalance(water_run)
    assert wb.model_residual() is None
    assert wb.model_snow_residual() is None


def test_water_balance_model_residual_available(water_run_with_model_residual):
    wb = WaterBalance(water_run_with_model_residual)
    model_res = wb.model_residual()
    snow_res = wb.model_snow_residual()

    assert model_res is not None
    assert snow_res is not None
    assert model_res.attrs.get("units") == "mm"
    assert snow_res.attrs.get("units") == "mm"


def test_water_balance_plot_with_model_residual(water_run_with_model_residual):
    wb = WaterBalance(water_run_with_model_residual)
    fig1, fig2, fig3, fig4 = wb.plot()
    assert fig1 is not None
    assert fig2 is not None
    assert fig3 is not None
    assert fig4 is not None
    import matplotlib.pyplot as plt
    plt.close("all")


def test_model_residual_alignment_auto_prefers_direct():
    model_vals = np.linspace(0.0, 2.0, 12)
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_model_residual=True,
        model_residual_values=model_vals,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_align_auto", tape="h0")
        run = Run(tmpdir)
        wb = WaterBalance(run)

        aligned, mode = wb.aligned_model_residual()
        assert aligned is not None
        assert mode == "direct"

        aligned_vals = np.asarray(aligned.squeeze().values)
        np.testing.assert_allclose(aligned_vals, model_vals)
        run.close()


def test_model_residual_alignment_forced_cumulative():
    model_vals = np.ones(12) * 0.5
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_model_residual=True,
        model_residual_values=model_vals,
    )
    cfg = Config()
    cfg.balances.water.model_residual_compare_mode = "cumulative"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_align_cum", tape="h0")
        run = Run(tmpdir)
        wb = WaterBalance(run, config=cfg)

        aligned, mode = wb.aligned_model_residual()
        assert aligned is not None
        assert mode == "cumulative"
        assert np.allclose(np.asarray(aligned.isel(time=0).values), 0.0)
        run.close()


def test_model_residual_alignment_sign_flip():
    model_vals = np.linspace(0.0, 1.0, 12)
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_model_residual=True,
        model_residual_values=model_vals,
    )
    cfg = Config()
    cfg.balances.water.model_residual_compare_mode = "direct"
    cfg.balances.water.model_residual_sign = -1.0

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_sign", tape="h0")
        run = Run(tmpdir)
        wb = WaterBalance(run, config=cfg)

        aligned, mode = wb.aligned_model_residual()
        assert aligned is not None
        assert mode == "direct"
        np.testing.assert_allclose(np.asarray(aligned.squeeze().values), -model_vals)
        run.close()


def test_water_balance_includes_optional_wa_storage():
    wa_vals = np.linspace(0.0, 11.0, 12)
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_wa_storage=True,
        wa_storage_values=wa_vals,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_wa", tape="h0")
        run = Run(tmpdir)
        wb = WaterBalance(run)

        # With WA added as optional storage, closure residual now reflects WA change.
        final_residual = float(wb.residual().values[-1])
        assert np.isclose(final_residual, -11.0, atol=1e-3)

        storage_comps = wb._storage_decomposition_components()
        assert "WA" in storage_comps
        run.close()


def test_water_balance_prefers_detailed_runoff_family_when_available():
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_detailed_runoff=True,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_detailed_runoff", tape="h0")
        run = Run(tmpdir)
        wb = WaterBalance(run)
        comps = wb.components()

        assert "QFLX_ROFLIQ_QSUR" in comps
        assert "QFLX_ROFLIQ_QSURP" in comps
        assert "QFLX_ROFLIQ_QSUB" in comps
        assert "QFLX_ROFLIQ_QSUBP" in comps
        assert "QFLX_ROFLIQ_QGWL" in comps
        assert "QFLX_ROFICE" in comps

        # Baseline lumped runoff/drainage terms should not be used when detailed
        # family is complete.
        assert "QOVER" not in comps
        assert "QDRAI" not in comps
        assert "QDRAI_PERCH" not in comps

        run.close()


def test_water_balance_uses_partial_detailed_runoff_when_available():
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_detailed_runoff=True,
    )
    # Emulate real runs where only subset of detailed runoff terms are present and
    # baseline runoff outputs are absent.
    ds = ds.drop_vars(
        [
            "QOVER",
            "QDRAI",
            "QDRAI_PERCH",
            "QFLX_ROFLIQ_QSURP",
            "QFLX_ROFLIQ_QSUBP",
            "QFLX_ROFICE",
        ]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_partial_detailed", tape="h0")
        run = Run(tmpdir)
        wb = WaterBalance(run)
        comps = wb.components()

        # Available detailed runoff terms should still be used.
        assert "QFLX_ROFLIQ_QSUR" in comps
        assert "QFLX_ROFLIQ_QSUB" in comps
        assert "QFLX_ROFLIQ_QGWL" in comps

        # Missing baseline runoff terms should not appear.
        assert "QOVER" not in comps
        assert "QDRAI" not in comps
        assert "QDRAI_PERCH" not in comps

        run.close()


def test_water_balance_includes_supplemental_runoff_term_when_present():
    ds = make_water_balance_dataset(
        start_year=2000,
        n_months=12,
        include_supplemental_runoff=True,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="water_test_supp_runoff", tape="h0")
        run = Run(tmpdir)
        wb = WaterBalance(run)
        comps = wb.components()

        assert "QSNWCPICE" in comps
        run.close()


def test_water_balance_to_netcdf(water_run):
    wb = WaterBalance(water_run)
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
        wb.to_netcdf(f.name)
        import xarray as xr
        ds = xr.open_dataset(f.name)
        assert "residual" in ds
        ds.close()


def test_water_balance_to_netcdf_with_model_residual(water_run_with_model_residual):
    wb = WaterBalance(water_run_with_model_residual)
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
        wb.to_netcdf(f.name)
        import xarray as xr

        ds = xr.open_dataset(f.name)
        assert "residual" in ds
        assert "model_residual" in ds
        assert "model_residual_aligned" in ds
        assert "residual_difference" in ds
        assert "model_snow_residual" in ds
        ds.close()
