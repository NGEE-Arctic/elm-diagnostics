"""Tests for configuration loading and validation."""

import tempfile

import pytest
import yaml
from pydantic import ValidationError

from elm_diagnostics.config.schema import Config, load_config, load_defaults


def test_load_defaults():
    defaults = load_defaults()
    assert "report" in defaults
    assert "time" in defaults
    assert "variable_groups" in defaults
    assert "variables" not in defaults
    assert "balances" not in defaults


def test_default_config_validates():
    config = load_config()
    assert isinstance(config, Config)
    assert config.balances.water.frame == "water_year"
    assert config.balances.energy.cumulative is False


def test_variable_group_defaults():
    config = load_config()
    hydrology = config.variable_groups["hydrology"]
    assert hydrology.enabled is True
    assert "SOILLIQ" in hydrology.variables
    assert "timeseries" in hydrology.plot_types.active_plot_types


def test_variable_group_override_and_report_sections():
    override = {
        "report": {"sections": {"diagnostics": False}},
        "variable_groups": {
            "hydrology": {
                "enabled": False,
                "variables": ["SOILLIQ"],
                "plot_types": {
                    "timeseries": True,
                    "hovmuller": False,
                    "seasonal": False,
                    "anomaly": False,
                    "histogram": False,
                    "diurnal": False,
                },
            }
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        config = load_config(path=f.name)

    assert config.report.sections.diagnostics is False
    assert config.variable_groups["hydrology"].enabled is False
    assert config.variable_groups["hydrology"].plot_types.active_plot_types == [
        "timeseries"
    ]


def test_corrected_variable_names():
    config = load_config()
    water = config.balances.water
    assert "QOVER" in water.outputs
    assert "QDRAI" in water.outputs
    assert "QDRAI_PERCH" in water.outputs
    assert "QFLX_EVAP_TOT" in water.outputs
    # Old wrong names should not be present
    assert "Q_over" not in water.outputs
    assert "Q_drain" not in water.outputs


def test_ch4_corrected_names():
    config = load_config()
    ch4 = config.balances.carbon.ch4
    assert "CH4_SURF_AERE_SAT" in ch4.aerenchyma
    assert "CH4_SURF_AERE_UNSAT" in ch4.aerenchyma
    # Old wrong names
    assert not any("SOIL" in v for v in ch4.aerenchyma)


def test_user_config_override():
    override = {
        "time": {"water_year_start_month": 4},
        "balances": {
            "water": {
                "storages": ["SOILLIQ", "SOILICE", "H2OSNO", "H2OCAN", "H2OSFC"],
                "inputs": ["RAIN", "SNOW"],
                "outputs": [
                    "QFLX_EVAP_TOT",
                    "QOVER",
                    "QDRAI",
                    "QDRAI_PERCH",
                    "QH2OSFC",
                ],
                "et_components": ["QSOIL", "QVEGE", "QVEGT"],
                "residual_against": "dS/dt",
                "frame": "calendar",
            }
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        config = load_config(path=f.name)

    assert config.time.water_year_start_month == 4
    assert config.balances.water.frame == "calendar"
    # Omitted subblocks still resolve from schema defaults.
    assert config.balances.carbon.frame == "calendar"
    assert "RAIN" in config.balances.water.inputs


def test_option_b_rejects_partial_balance_subblock():
    override = {
        "balances": {
            "water": {
                "frame": "calendar",
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        with pytest.raises(ValueError, match="full block"):
            load_config(path=f.name)


def test_balances_override_always_warns():
    override = {
        "balances": {
            "energy": {
                "radiation": ["FSDS", "FSR", "FLDS", "FIRE", "FSA", "FIRA"],
                "turbulent": ["FSH", "EFLX_LH_TOT"],
                "ground": ["FGR", "FGR12"],
                "storage": ["HC", "HCSOI"],
                "errors": ["ERRSOI", "ERRSEB"],
                "frame": "calendar",
                "cumulative": False,
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        with pytest.warns(UserWarning, match="Advanced override detected"):
            config = load_config(path=f.name)

    assert config.balances.energy.cumulative is False


def test_invalid_envelope_rejected():
    bad = {"plots": {"climatology": {"envelope": "invalid_value"}}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(bad, f)
        f.flush()
        with pytest.raises((ValueError, ValidationError)):
            load_config(path=f.name)


def test_hovmuller_max_depth_default_none():
    config = load_config()
    assert config.plots.hovmuller.max_depth_m is None


def test_hovmuller_max_depth_override():
    override = {"plots": {"hovmuller": {"max_depth_m": 2.5}}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        config = load_config(path=f.name)

    assert config.plots.hovmuller.max_depth_m == 2.5


def test_hovmuller_color_limit_defaults():
    config = load_config()
    hov = config.plots.hovmuller
    assert hov.color_limit_method == "full_range"
    assert hov.color_limit_quantile_low == 2.0
    assert hov.color_limit_quantile_high == 98.0
    assert hov.color_limit_sigma == 2.0


def test_hovmuller_color_limit_override():
    override = {
        "plots": {
            "hovmuller": {
                "color_limit_method": "quantile",
                "color_limit_quantile_low": 5.0,
                "color_limit_quantile_high": 95.0,
                "color_limit_sigma": 3.0,
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        config = load_config(path=f.name)

    hov = config.plots.hovmuller
    assert hov.color_limit_method == "quantile"
    assert hov.color_limit_quantile_low == 5.0
    assert hov.color_limit_quantile_high == 95.0
    assert hov.color_limit_sigma == 3.0


def test_analysis_year_window_defaults():
    config = load_config()
    assert config.time.analysis_start_year is None
    assert config.time.analysis_end_year is None


def test_analysis_year_window_override():
    override = {
        "time": {
            "analysis_start_year": 2000,
            "analysis_end_year": 2010,
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        config = load_config(path=f.name)

    assert config.time.analysis_start_year == 2000
    assert config.time.analysis_end_year == 2010


def test_analysis_year_window_rejects_inverted_bounds():
    override = {
        "time": {
            "analysis_start_year": 2010,
            "analysis_end_year": 2000,
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        with pytest.raises(ValueError, match="analysis_start_year"):
            load_config(path=f.name)


def test_water_year_start_month_validation():
    override = {
        "time": {
            "water_year_start_month": 13,
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        with pytest.raises(ValueError, match="water_year_start_month"):
            load_config(path=f.name)
