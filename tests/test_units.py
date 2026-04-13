"""Tests for unit handling."""

import numpy as np
import xarray as xr

from elm_diagnostics.io.units import (
    classify_variable,
    convert_flux_to_cumulative_units,
    normalize_unit_string,
    parse_units,
)


def test_normalize_common_units():
    assert normalize_unit_string("mm/s") == "mm/s"
    assert normalize_unit_string("mm H2O/s") == "mm/s"
    assert normalize_unit_string("W/m^2") == "W/m**2"
    assert normalize_unit_string("gC/m^2/s") == "g/m**2/s"
    assert normalize_unit_string("unitless") == "dimensionless"


def test_parse_units():
    u = parse_units("W/m^2")
    assert str(u) == "watt / meter ** 2"


def test_classify_flux():
    da = xr.DataArray(
        np.zeros(10),
        attrs={"units": "mm/s", "cell_methods": "time: mean"},
        name="RAIN",
    )
    assert classify_variable(da) == "flux"


def test_classify_state():
    da = xr.DataArray(
        np.zeros(10),
        attrs={"units": "kg/m2", "cell_methods": "time: point"},
        name="SOILLIQ",
    )
    assert classify_variable(da) == "state"


def test_classify_known_state():
    da = xr.DataArray(
        np.zeros(10),
        attrs={"units": "mm"},
        name="H2OSNO",
    )
    assert classify_variable(da) == "state"


def test_classify_known_intensive():
    da = xr.DataArray(
        np.zeros(10),
        attrs={"units": "K"},
        name="TSOI",
    )
    assert classify_variable(da) == "intensive"


def test_flux_to_cumulative_mm():
    target, mult = convert_flux_to_cumulative_units("mm/s")
    assert target == "mm"
    assert mult == 1.0


def test_flux_to_cumulative_watts():
    target, mult = convert_flux_to_cumulative_units("W/m^2")
    assert "J" in target
    assert mult == 1.0
