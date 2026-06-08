"""Tests for water balance unit standardization to mm."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from elm_diagnostics import Run, WaterBalance
from elm_diagnostics.io.derived import aggregate_vertical_storage
from elm_diagnostics.io.units import convert_water_to_mm
from tests.fixtures.synthetic_elm import make_water_balance_dataset, save_as_elm_files


class TestConvertWaterToMM:
    """Test the convert_water_to_mm() function."""

    def test_convert_kgm2_to_mm(self):
        """Test kg/m² → mm conversion."""
        data = np.array([100.0, 150.0, 200.0])
        da = xr.DataArray(
            data,
            dims=["time"],
            attrs={"units": "kg/m2", "long_name": "soil liquid water"},
        )

        result = convert_water_to_mm(da)

        # Units should be updated
        assert result.attrs["units"] == "mm"
        # Values should be unchanged (1:1 conversion)
        np.testing.assert_array_equal(result.values, data)
        # Other attributes preserved
        assert result.attrs["long_name"] == "soil liquid water"
        # Original should be unchanged
        assert da.attrs["units"] == "kg/m2"

    def test_convert_kgm2_variants_to_mm(self):
        """Test kg/m^2 and kg/m**2 variants → mm conversion."""
        data = np.array([50.0])

        # Test kg/m^2
        da1 = xr.DataArray(data, attrs={"units": "kg/m^2"})
        result1 = convert_water_to_mm(da1)
        assert result1.attrs["units"] == "mm"
        np.testing.assert_array_equal(result1.values, data)

        # Test kg/m**2 (pint format)
        da2 = xr.DataArray(data, attrs={"units": "kg/m**2"})
        result2 = convert_water_to_mm(da2)
        assert result2.attrs["units"] == "mm"
        np.testing.assert_array_equal(result2.values, data)

    def test_convert_mm_to_mm_noop(self):
        """Test mm → mm (no-op, returns same object)."""
        data = np.array([10.0, 20.0])
        da = xr.DataArray(
            data,
            dims=["time"],
            attrs={"units": "mm", "long_name": "snow water equivalent"},
        )

        result = convert_water_to_mm(da)

        # Should be same object (no copy needed)
        assert result is da
        assert result.attrs["units"] == "mm"
        np.testing.assert_array_equal(result.values, data)

    def test_convert_no_units_raises_error(self):
        """Test that missing units attribute raises error."""
        da = xr.DataArray([100.0], attrs={})

        with pytest.raises(ValueError, match="no 'units' attribute"):
            convert_water_to_mm(da)

    def test_convert_invalid_units_raises_error(self):
        """Test that incompatible units raise error."""
        # Temperature
        da1 = xr.DataArray([273.15], attrs={"units": "K"})
        with pytest.raises(ValueError, match="Cannot convert units 'K'"):
            convert_water_to_mm(da1)

        # Pressure
        da2 = xr.DataArray([101325.0], attrs={"units": "Pa"})
        with pytest.raises(ValueError, match="Cannot convert units 'Pa'"):
            convert_water_to_mm(da2)

    def test_convert_flux_units_raises_error(self):
        """Test that flux units (mm/s) raise helpful error."""
        da = xr.DataArray([0.001], attrs={"units": "mm/s"})

        with pytest.raises(ValueError, match="Cannot convert flux units"):
            convert_water_to_mm(da)

    def test_convert_preserves_coordinates(self):
        """Test that coordinates are preserved."""
        time = np.arange(5)
        lndgrid = np.array([0])
        data = np.random.rand(5, 1) * 100

        da = xr.DataArray(
            data,
            dims=["time", "lndgrid"],
            coords={"time": time, "lndgrid": lndgrid},
            attrs={"units": "kg/m2"},
        )

        result = convert_water_to_mm(da)

        assert result.attrs["units"] == "mm"
        assert list(result.dims) == ["time", "lndgrid"]
        np.testing.assert_array_equal(result.coords["time"], time)
        np.testing.assert_array_equal(result.coords["lndgrid"], lndgrid)

    def test_convert_multidimensional(self):
        """Test conversion with multidimensional data (time, levgrnd, lndgrid)."""
        data = np.random.rand(12, 15, 1) * 50  # 12 months, 15 levels, 1 gridcell
        da = xr.DataArray(
            data,
            dims=["time", "levgrnd", "lndgrid"],
            attrs={"units": "kg/m2", "long_name": "soil liquid water"},
        )

        result = convert_water_to_mm(da)

        assert result.attrs["units"] == "mm"
        assert result.shape == (12, 15, 1)
        np.testing.assert_array_equal(result.values, data)


class TestWaterBalanceUnitStandardization:
    """Integration tests for water balance unit standardization."""

    @pytest.fixture
    def water_run_with_mixed_units(self):
        """Create a water balance run with mixed units (kg/m² and mm)."""
        ds = make_water_balance_dataset(start_year=2000, n_months=12)
        with tempfile.TemporaryDirectory() as tmpdir:
            save_as_elm_files(ds, Path(tmpdir), casename="mixed_units", tape="h0")
            run = Run(tmpdir)
            yield run
            run.close()

    def test_water_balance_all_components_have_mm_units(
        self, water_run_with_mixed_units
    ):
        """Test that all water balance components are standardized to mm."""
        wb = WaterBalance(water_run_with_mixed_units)
        comps = wb.components()

        # Check that all components exist
        assert "RAIN" in comps
        assert "SNOW" in comps
        assert "QFLX_EVAP_TOT" in comps
        assert "QOVER" in comps
        assert "QDRAI" in comps
        assert "dS" in comps

        # Check that all have mm units
        for varname, da in comps.items():
            assert da.attrs.get("units") == "mm", (
                f"{varname} has units {da.attrs.get('units')}, expected 'mm'"
            )

    def test_water_balance_residual_has_mm_units(self, water_run_with_mixed_units):
        """Test that residual has mm units."""
        wb = WaterBalance(water_run_with_mixed_units)
        res = wb.residual()

        assert res.attrs["units"] == "mm"

    def test_water_balance_still_closes(self, water_run_with_mixed_units):
        """Test that water balance still closes after unit conversion."""
        wb = WaterBalance(water_run_with_mixed_units)
        res = wb.residual()

        # Synthetic data is constructed to close exactly
        final_residual = float(res.values[-1])
        assert abs(final_residual) < 1e-4, (
            f"Water balance residual too large: {final_residual:.6e} mm"
        )

    def test_vertical_aggregation_converts_to_mm(self, water_run_with_mixed_units):
        """Test that vertical aggregation converts SOILLIQ/SOILICE to mm."""
        run = water_run_with_mixed_units

        # Get raw SOILLIQ (should have kg/m² units from synthetic data)
        soilliq_raw = run.get("SOILLIQ")
        assert soilliq_raw.attrs.get("units") == "kg/m2"

        # Note: Simple synthetic data doesn't have vertical dimensions
        # This is tested separately with real data in test_real_data.py

        # Aggregate should still work and convert to mm
        soilliq_agg = aggregate_vertical_storage(run, "SOILLIQ")
        assert soilliq_agg.attrs.get("units") == "mm"

    def test_storage_variables_keep_correct_values(self, water_run_with_mixed_units):
        """Test that storage values are preserved during conversion (1:1)."""
        run = water_run_with_mixed_units

        # Get SOILLIQ before and after aggregation
        soilliq_raw = run.get("SOILLIQ")
        soilliq_agg = aggregate_vertical_storage(run, "SOILLIQ")

        # Sum manually to verify (only if vertical dimensions exist)
        if "levgrnd" in soilliq_raw.dims:
            expected = soilliq_raw.sum(dim="levgrnd")
        elif "levsoi" in soilliq_raw.dims:
            expected = soilliq_raw.sum(dim="levsoi")
        else:
            # No vertical dimension - should be unchanged
            expected = soilliq_raw

        # Values should match (kg/m² = mm numerically)
        np.testing.assert_allclose(
            soilliq_agg.values, expected.values, rtol=1e-10, atol=1e-10
        )
