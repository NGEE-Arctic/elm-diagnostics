# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Tests for max_levels filtering functionality."""

import numpy as np
import pytest
import xarray as xr

from elm_diagnostics.config.schema import HovmullerConfig, load_config
from elm_diagnostics.plots.dimension_helpers import apply_max_levels


def test_apply_max_levels_basic():
    """Test layer selection masks to top N levels."""
    da = xr.DataArray(
        np.arange(45).reshape(15, 3),
        dims=["levgrnd", "time"],
        coords={"levgrnd": np.arange(15)},
    )
    result = apply_max_levels(da, "levgrnd", 10)
    assert result.sizes["levgrnd"] == 10
    assert result.levgrnd.values.tolist() == list(range(10))


def test_apply_max_levels_with_physical_coords():
    """Test layer selection preserves physical depth coords."""
    zsoi_values = [0.01, 0.04, 0.09, 0.16, 0.26, 0.40, 0.58, 0.80, 1.06, 1.36,
                   1.70, 2.08, 2.50, 2.99, 3.58]
    da = xr.DataArray(
        np.random.rand(15, 12),
        dims=["levgrnd", "time"],
        coords={
            "levgrnd": np.arange(15),
            "zsoi": ("levgrnd", zsoi_values),
        },
    )
    result = apply_max_levels(da, "levgrnd", 10)
    assert result.sizes["levgrnd"] == 10
    assert "zsoi" in result.coords
    assert len(result.zsoi) == 10
    np.testing.assert_allclose(result.zsoi.values, zsoi_values[:10])


def test_apply_max_levels_already_within_limit():
    """Test no-op when data already has fewer levels."""
    da = xr.DataArray(
        np.arange(24).reshape(8, 3),
        dims=["levgrnd", "time"],
        coords={"levgrnd": np.arange(8)},
    )
    result = apply_max_levels(da, "levgrnd", 10)
    assert result.sizes["levgrnd"] == 8
    xr.testing.assert_identical(result, da)


def test_apply_max_levels_zero():
    """Test max_levels=0 returns empty slice."""
    da = xr.DataArray(
        np.arange(45).reshape(15, 3),
        dims=["levgrnd", "time"],
        coords={"levgrnd": np.arange(15)},
    )
    with pytest.warns(UserWarning, match="Limiting levgrnd to 0 of 15 levels"):
        result = apply_max_levels(da, "levgrnd", 0)
    assert result.sizes["levgrnd"] == 0


def test_apply_max_levels_one():
    """Test max_levels=1 returns only surface level."""
    da = xr.DataArray(
        np.arange(45).reshape(15, 3),
        dims=["levgrnd", "time"],
        coords={"levgrnd": np.arange(15)},
    )
    with pytest.warns(UserWarning, match="Limiting levgrnd to 1 of 15 levels"):
        result = apply_max_levels(da, "levgrnd", 1)
    assert result.sizes["levgrnd"] == 1
    assert result.levgrnd.values[0] == 0


def test_apply_max_levels_none():
    """Test that max_levels=None returns data unchanged."""
    da = xr.DataArray(
        np.arange(45).reshape(15, 3),
        dims=["levgrnd", "time"],
        coords={"levgrnd": np.arange(15)},
    )
    result = apply_max_levels(da, "levgrnd", None)
    assert result.sizes["levgrnd"] == 15
    xr.testing.assert_identical(result, da)


def test_apply_max_levels_missing_dim():
    """Test that missing dimension returns data unchanged."""
    da = xr.DataArray(
        np.arange(12).reshape(4, 3),
        dims=["x", "time"],
        coords={"x": np.arange(4)},
    )
    result = apply_max_levels(da, "levgrnd", 10)
    assert "levgrnd" not in result.dims
    xr.testing.assert_identical(result, da)


def test_hovmuller_config_validation_mutual_exclusion():
    """Test max_levels and max_depth_m cannot both be set."""
    with pytest.raises(ValueError, match="Cannot set both"):
        HovmullerConfig(max_levels=10, max_depth_m=3.5)


def test_hovmuller_config_max_levels_only():
    """Test config with only max_levels is valid."""
    cfg = HovmullerConfig(max_levels=10)
    assert cfg.max_levels == 10
    assert cfg.max_depth_m is None


def test_hovmuller_config_max_depth_only():
    """Test config with only max_depth_m is valid."""
    cfg = HovmullerConfig(max_depth_m=3.5)
    assert cfg.max_depth_m == 3.5
    assert cfg.max_levels is None


def test_hovmuller_config_neither():
    """Test config with neither max_levels nor max_depth_m is valid."""
    cfg = HovmullerConfig()
    assert cfg.max_levels is None
    assert cfg.max_depth_m is None


def test_default_config_max_levels_is_none():
    """Test that default config has max_levels unset (null)."""
    cfg = load_config()
    assert cfg.plots.hovmuller.max_levels is None
    assert cfg.plots.hovmuller.max_depth_m is None


def test_user_can_set_max_levels():
    """Test that users can configure max_levels via config."""
    import tempfile
    from pathlib import Path

    import yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.yaml"
        cfg_path.write_text(yaml.safe_dump({"plots": {"hovmuller": {"max_levels": 10}}}))
        cfg = load_config(path=cfg_path)
        assert cfg.plots.hovmuller.max_levels == 10
        assert cfg.plots.hovmuller.max_depth_m is None


def test_group_specific_max_levels():
    """Test that variable groups can have group-specific max_levels."""
    cfg = load_config()

    # Hydrology group should have max_levels: 10
    assert "hydrology" in cfg.variable_groups
    hydro_group = cfg.variable_groups["hydrology"]
    assert hydro_group.hovmuller is not None
    assert hydro_group.hovmuller.max_levels == 10

    # Other groups should not have group-specific hovmuller config
    if "soil_state" in cfg.variable_groups:
        soil_group = cfg.variable_groups["soil_state"]
        assert soil_group.hovmuller is None


def test_get_variable_group_hovmuller_config_hydrology():
    """Test that hydrology variables use group-specific config."""
    cfg = load_config()

    # SOILLIQ is in hydrology group, should get group config
    soilliq_config = cfg.get_variable_group_hovmuller_config("SOILLIQ")
    assert soilliq_config.max_levels == 10

    # H2OSOI is in hydrology group, should get group config
    h2osoi_config = cfg.get_variable_group_hovmuller_config("H2OSOI")
    assert h2osoi_config.max_levels == 10


def test_get_variable_group_hovmuller_config_fallback():
    """Test that non-hydrology variables fall back to global config."""
    cfg = load_config()

    # TSOI is in soil_state group (no group-specific config), should get global
    tsoi_config = cfg.get_variable_group_hovmuller_config("TSOI")
    assert tsoi_config.max_levels is None  # global default

    # GPP not in hydrology, should get global
    gpp_config = cfg.get_variable_group_hovmuller_config("GPP")
    assert gpp_config.max_levels is None


def test_group_config_overrides_global():
    """Test that group-specific config takes precedence over global."""
    import tempfile
    from pathlib import Path

    import yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.yaml"
        cfg_yaml = {
            "plots": {"hovmuller": {"max_levels": 15}},  # Global setting
            "variable_groups": {
                "hydrology": {
                    "hovmuller": {"max_levels": 10}  # Group-specific override
                }
            }
        }
        cfg_path.write_text(yaml.safe_dump(cfg_yaml))
        cfg = load_config(path=cfg_path)

        # Global should be 15
        assert cfg.plots.hovmuller.max_levels == 15

        # But SOILLIQ should use group-specific 10
        soilliq_config = cfg.get_variable_group_hovmuller_config("SOILLIQ")
        assert soilliq_config.max_levels == 10

        # And non-hydrology variable should use global 15
        gpp_config = cfg.get_variable_group_hovmuller_config("GPP")
        assert gpp_config.max_levels == 15
