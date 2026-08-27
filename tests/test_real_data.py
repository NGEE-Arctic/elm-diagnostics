"""Tests using real ELM h0 output file (oakharbor_column).

These tests verify that the package works correctly with actual ELM output,
including handling of:
- lndgrid dimension (instead of lat/lon)
- Vertical dimensions (levgrnd) that need aggregation
- Missing QFLX_EVAP_TOT (computed from components)
- Sub-gridcell dimensions (column, pft, landunit)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import xarray as xr

from elm_diagnostics import Run, WaterBalance
from elm_diagnostics.io.derived import (
    DERIVABLE_REQUIREMENTS,
    DERIVABLE_VARS,
    compute_total_et,
)
from elm_diagnostics.time.integration import get_time_deltas

# Path to the real h0 file (any file from the set will work - Run auto-discovers all)
REAL_H0_FILE = (
    Path(__file__).parent
    / "fixtures"
    / "data"
    / "oakharbor_column.elm.elm.h0.2000-10.nc"
)


@pytest.fixture
def real_run():
    """Run object from real oakharbor h0 file."""
    if not REAL_H0_FILE.exists():
        pytest.skip(f"Real h0 file not found: {REAL_H0_FILE}")
    return Run(REAL_H0_FILE.parent, name="oakharbor_test")


def test_real_file_loads(real_run):
    """Test that the real h0 file loads successfully."""
    assert real_run.name == "oakharbor_test"
    assert "h0" in real_run.streams
    ds = real_run.streams["h0"]
    assert "time" in ds.dims
    assert "lndgrid" in ds.dims


def test_real_file_dimensions(real_run):
    """Test dimension handling for single-point run with lndgrid."""
    ds = real_run.streams["h0"]

    # Single-point dimensions
    assert ds.sizes["lndgrid"] == 1
    assert ds.sizes["time"] == 15  # 15 months: Oct 2000 - Dec 2001

    # NOTE: Sub-gridcell dimensions (column, pft, landunit) are not present
    # as separate dimensions in the oakharbor file - variables are gridcell-averaged.
    # This is fine - the file uses lndgrid aggregation.

    # Vertical dimensions
    assert "levgrnd" in ds.sizes
    assert "levsoi" in ds.sizes
    assert ds.sizes["levgrnd"] == 15
    assert ds.sizes["levsoi"] == 10


def test_real_file_has_expected_variables(real_run):
    """Test that expected water balance variables are present."""
    # Inputs
    assert real_run.has("RAIN")
    assert real_run.has("SNOW")

    # ET components
    assert real_run.has("QSOIL")
    assert real_run.has("QVEGE")
    assert real_run.has("QVEGT")

    # Other outputs
    assert real_run.has("QOVER")
    assert real_run.has("QDRAI")

    # Storage
    assert real_run.has("SOILLIQ")
    assert real_run.has("SOILICE")
    assert real_run.has("H2OSNO")


def test_real_file_missing_qflx_evap_tot(real_run):
    """Verify that QFLX_EVAP_TOT is not in the file but can be derived."""
    # Check that it's not in any of the raw streams
    for tape in real_run._tape_order:
        ds = real_run._open_stream(tape)
        assert "QFLX_EVAP_TOT" not in ds

    # But has() should return True because it can be derived
    assert real_run.has("QFLX_EVAP_TOT")


def test_compute_et_from_real_data(real_run):
    """Test computing total ET from components using real data."""
    et_total = compute_total_et(real_run)

    assert et_total.name == "QFLX_EVAP_TOT"
    assert "units" in et_total.attrs
    assert et_total.dims == ("time", "lndgrid")

    # ET can be slightly negative (dew formation), but should be mostly positive
    # Need to compute dask arrays before checking
    et_values = et_total.compute()
    mean_et = float(et_values.mean())
    assert mean_et > 0, f"Mean ET should be positive, got {mean_et}"


def test_get_with_derivation(real_run):
    """Test that Run.get() auto-derives QFLX_EVAP_TOT."""
    # Should not raise, should compute from components
    et_total = real_run.get("QFLX_EVAP_TOT")

    assert et_total is not None
    assert et_total.dims == ("time", "lndgrid")

    # Verify it equals sum of components
    qsoil = real_run.get("QSOIL")
    qvege = real_run.get("QVEGE")
    qvegt = real_run.get("QVEGT")

    expected = qsoil + qvege + qvegt
    xr.testing.assert_allclose(et_total, expected)


def test_vertical_aggregation_soilliq(real_run):
    """Test that SOILLIQ vertical aggregation works."""
    soilliq = real_run.get("SOILLIQ")

    # Should have levgrnd dimension
    assert "levgrnd" in soilliq.dims
    assert soilliq.sizes["levgrnd"] == 15

    # Sum over levels
    total = soilliq.sum(dim="levgrnd")
    assert "levgrnd" not in total.dims
    assert total.dims == ("time", "lndgrid")

    # Should be positive (water content)
    assert (total >= 0).all()


def test_vertical_aggregation_soilice(real_run):
    """Test that SOILICE vertical aggregation works."""
    soilice = real_run.get("SOILICE")

    # Should have levgrnd dimension
    assert "levgrnd" in soilice.dims
    assert soilice.sizes["levgrnd"] == 15

    # Sum over levels
    total = soilice.sum(dim="levgrnd")
    assert "levgrnd" not in total.dims
    assert total.dims == ("time", "lndgrid")

    # Should be non-negative (ice content)
    assert (total >= 0).all()


def test_water_balance_with_real_data(real_run):
    """Test water balance calculation with real data.

    Uses 15 months of data (Oct 2000 - Dec 2001) including
    complete Water Year 2001 (Oct 2000 - Sep 2001).
    """
    wb = WaterBalance(real_run)
    comps = wb.components()

    assert "RAIN" in comps
    assert "SNOW" in comps
    assert "dS" in comps

    residual = wb.residual()
    assert residual is not None


def test_time_bounds_present(real_run):
    """Test that time_bounds are present for integration."""
    ds = real_run.streams["h0"]
    assert "time_bounds" in ds

    time_bounds = ds["time_bounds"]
    assert time_bounds.dims == ("time", "hist_interval")
    assert time_bounds.sizes["hist_interval"] == 2


def test_cell_methods_attributes(real_run):
    """Test that flux variables have proper cell_methods."""
    # Flux variables should have cell_methods = "time: mean"
    rain = real_run.get("RAIN")
    assert "cell_methods" in rain.attrs
    assert "time: mean" in rain.attrs["cell_methods"]

    gpp = real_run.get("GPP")
    assert "cell_methods" in gpp.attrs
    assert "time: mean" in gpp.attrs["cell_methods"]


def test_water_balance_unit_standardization(real_run):
    """Test that all water balance components are standardized to mm with real data.

    This test verifies that:
    1. SOILLIQ/SOILICE (kg/m² with vertical dims) are converted to mm
    2. H2OSNO/H2OCAN/H2OSFC (already mm) remain unchanged
    3. Fluxes (mm/s) are integrated to cumulative mm
    4. All components have consistent mm units
    """
    from elm_diagnostics.io.derived import aggregate_vertical_storage

    # Test raw SOILLIQ has kg/m² with vertical dimension
    soilliq_raw = real_run.get("SOILLIQ")
    assert soilliq_raw.attrs.get("units") == "kg/m2"
    assert "levgrnd" in soilliq_raw.dims
    assert soilliq_raw.sizes["levgrnd"] == 15

    # Test aggregation converts to mm
    soilliq_agg = aggregate_vertical_storage(real_run, "SOILLIQ")
    assert soilliq_agg.attrs.get("units") == "mm"
    assert "levgrnd" not in soilliq_agg.dims

    # Test SOILICE too
    soilice_raw = real_run.get("SOILICE")
    assert soilice_raw.attrs.get("units") == "kg/m2"
    assert "levgrnd" in soilice_raw.dims

    soilice_agg = aggregate_vertical_storage(real_run, "SOILICE")
    assert soilice_agg.attrs.get("units") == "mm"

    # Test variables already in mm remain unchanged
    h2osno = real_run.get("H2OSNO")
    assert h2osno.attrs.get("units") == "mm"

    h2ocan = real_run.get("H2OCAN")
    assert h2ocan.attrs.get("units") == "mm"

    # Test full water balance has all mm units
    wb = WaterBalance(real_run)
    comps = wb.components()

    # All components should be in mm
    for varname, da in comps.items():
        assert da.attrs.get("units") == "mm", (
            f"Component '{varname}' has units '{da.attrs.get('units')}', expected 'mm'"
        )

    # Residual should also be mm
    res = wb.residual()
    assert res.attrs.get("units") == "mm"

    # Verify values are reasonable (not zero, not insanely large)
    if "RAIN" in comps:
        rain_final = float(comps["RAIN"].values[-1])
        assert 0 < rain_final < 10000, f"RAIN cumulative out of range: {rain_final}"

    if "dS" in comps:
        ds_final = float(comps["dS"].values[-1])
        assert abs(ds_final) < 5000, f"dS out of range: {ds_final}"


# ---------------------------------------------------------------------------
# Memory optimization: cheap combine strategy, sane chunking, index routing
# ---------------------------------------------------------------------------


def test_bounds_dataset_carries_time_bounds(real_run):
    """bounds_dataset() exposes time + time_bounds and matches full-stream dt."""
    bounds = real_run.bounds_dataset()
    assert "time" in bounds.dims
    assert "time_bounds" in bounds or "time_bnds" in bounds

    full = real_run.streams["h0"]
    dt_full = get_time_deltas(full)
    dt_bounds = get_time_deltas(bounds)
    xr.testing.assert_allclose(dt_bounds, dt_full)


def test_has_does_not_open_full_streams(real_run):
    """has() routes through the header index, never _open_stream."""
    calls = []
    orig = real_run._open_stream

    def _spy(tape, *args, **kwargs):
        calls.append(tape)
        return orig(tape, *args, **kwargs)

    real_run._open_stream = _spy  # type: ignore[method-assign]
    try:
        assert real_run.has("SOILLIQ") is True
        # QFLX_EVAP_TOT is absent from files but derivable from components.
        assert real_run.has("QFLX_EVAP_TOT") is True
        assert real_run.has("NONEXISTENT") is False
    finally:
        real_run._open_stream = orig  # type: ignore[method-assign]

    assert calls == [], f"has() opened full streams for tapes: {calls}"


def test_get_uses_index_to_route_before_opening(real_run):
    """get() consults the header index and opens only the owning tape once."""
    index_calls = []
    open_calls = []
    orig_index = real_run._variable_index
    orig_open = real_run._open_stream

    def _spy_index(tape, *a, **k):
        index_calls.append(tape)
        return orig_index(tape, *a, **k)

    def _spy_open(tape, *a, **k):
        open_calls.append(tape)
        return orig_open(tape, *a, **k)

    real_run._variable_index = _spy_index  # type: ignore[method-assign]
    real_run._open_stream = _spy_open  # type: ignore[method-assign]
    try:
        da = real_run.get("SOILLIQ")
    finally:
        real_run._variable_index = orig_index  # type: ignore[method-assign]
        real_run._open_stream = orig_open  # type: ignore[method-assign]

    assert "levgrnd" in da.dims
    # Routed via the index, then opened the single owning tape exactly once.
    assert "h0" in index_calls
    assert open_calls == ["h0"], f"expected one open of h0, got {open_calls}"


def test_auto_chunks_sizes_from_largest_variable(tmp_path):
    """_auto_chunks_for_stream sizes from the largest variable, not the dim product.

    The old bug multiplied every non-time dimension in the dataset together
    (all vertical/sub-grid dims across all variables), producing a bogus
    per-timestep footprint that forced ``{"time": 1}`` — one chunk per timestep.
    Here a synthetic file has several *disjoint* extra dimensions (levgrnd=15,
    levlak=10, natpft=17) used by different variables. Their product (2550) is
    far larger than any single variable's footprint (max 17), so the buggy
    formula would collapse the chunk while the fix keeps it large.
    """
    import numpy as np
    from elm_diagnostics.io.run import Run

    n_time = 400
    ds = xr.Dataset(
        {
            "A": (("time", "levgrnd"), np.zeros((n_time, 15), dtype="float32")),
            "B": (("time", "levlak"), np.zeros((n_time, 10), dtype="float32")),
            "C": (("time", "natpft"), np.zeros((n_time, 17), dtype="float32")),
        },
        coords={"time": np.arange(n_time)},
    )
    f = tmp_path / "case.elm.h0.0001-01-01-00000.nc"
    ds.to_netcdf(f)

    run = Run(str(tmp_path))
    # target so that 17 elems (largest var) * 8 bytes fits many timesteps, but
    # 2550 elems (bogus dim-product) * 8 bytes would force time_chunk == 1.
    run._chunk_target_mb = 1
    chunks = run._auto_chunks_for_stream([f])
    run.close()

    assert chunks is not None and "time" in chunks
    # 1 MiB / (17*8 B) ~= 7710, capped at n_time=400. The dim-product bug would
    # give 1 MiB / (2550*8 B) ~= 51 — this asserts we are NOT sizing that way.
    assert chunks["time"] > 51, f"time chunk sized from dim-product bug: {chunks}"
    assert chunks["time"] == n_time


def test_get_missing_variable_raises_keyerror(real_run):
    """A truly absent, non-derivable variable still raises KeyError with its name."""
    with pytest.raises(KeyError, match="TOTALLY_ABSENT_VAR"):
        real_run.get("TOTALLY_ABSENT_VAR")


def test_derivable_requirements_consistent_with_registry():
    """Every derivable variable has a matching requirements entry."""
    assert set(DERIVABLE_REQUIREMENTS.keys()) == set(DERIVABLE_VARS.keys())
    for varname, components in DERIVABLE_REQUIREMENTS.items():
        assert isinstance(components, list) and components, (
            f"{varname} must list at least one required component"
        )
