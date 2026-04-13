"""Tests for configuration loading and validation."""

import tempfile
from pathlib import Path

import yaml

from elm_diagnostics.config.schema import Config, load_config, load_defaults


def test_load_defaults():
    defaults = load_defaults()
    assert "balances" in defaults
    assert "water" in defaults["balances"]
    assert "RAIN" in defaults["balances"]["water"]["inputs"]


def test_default_config_validates():
    config = load_config()
    assert isinstance(config, Config)
    assert config.balances.water.frame == "water_year"
    assert config.balances.energy.cumulative is False


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
            "water": {"frame": "calendar"},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(override, f)
        f.flush()
        config = load_config(path=f.name)

    assert config.time.water_year_start_month == 4
    assert config.balances.water.frame == "calendar"
    # Defaults should still be present for non-overridden fields
    assert "RAIN" in config.balances.water.inputs


def test_invalid_envelope_rejected():
    import pytest
    bad = {"plots": {"climatology": {"envelope": "invalid_value"}}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(bad, f)
        f.flush()
        with pytest.raises(Exception):
            load_config(path=f.name)
