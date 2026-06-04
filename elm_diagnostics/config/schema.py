"""Pydantic models for YAML configuration and defaults merging."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import warnings
import yaml
from pydantic import BaseModel, Field

_DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"
_USER_CONFIG_PATH = Path.home() / ".config" / "elm-diagnostics" / "config.yaml"


# ---------------------------------------------------------------------------
# Schema models
# ---------------------------------------------------------------------------


class PlotStyleConfig(BaseModel):
    figsize: list[float] = [8.0, 5.0]
    dpi: int = 150
    palette: str = "tab10"


class ClimatologyConfig(BaseModel):
    include_climos: bool = True
    climo_start_year: int = -1
    climo_end_year: int = -1
    envelope: Literal["minmax", "p10_p90", "std"] = "minmax"


class PlotsConfig(BaseModel):
    style: PlotStyleConfig = PlotStyleConfig()
    climatology: ClimatologyConfig = ClimatologyConfig()


class ThumbnailConfig(BaseModel):
    enabled: bool = True
    size: list[int] = [400, 300]
    dpi: int = 72


class ReportPlotTypesConfig(BaseModel):
    include: list[str] = ["timeseries", "seasonal", "anomaly", "histogram", "diurnal"]


class VariableSectionsConfig(BaseModel):
    max_variables_per_group: int = 10
    show_statistics_table: bool = True


class BalanceSectionsConfig(BaseModel):
    show_statistics_table: bool = True
    show_residual_percentage: bool = True


class ComparisonConfig(BaseModel):
    show_delta_plots: bool = True
    side_by_side_layout: bool = True


class MetadataConfig(BaseModel):
    show_configuration: bool = True
    show_run_info: bool = True
    show_generation_timestamp: bool = True


class ReportConfig(BaseModel):
    title_template: str = "ELM diagnostics — {casename}"
    output_formats: list[str] = ["png", "netcdf"]
    thumbnails: ThumbnailConfig = ThumbnailConfig()
    plot_types: ReportPlotTypesConfig = ReportPlotTypesConfig()
    variable_sections: VariableSectionsConfig = VariableSectionsConfig()
    balance_sections: BalanceSectionsConfig = BalanceSectionsConfig()
    comparison: ComparisonConfig = ComparisonConfig()
    metadata: MetadataConfig = MetadataConfig()


class TimeConfig(BaseModel):
    water_year_start_month: int = 10
    cumulative_years: str | list[int] = "all"


class WaterBalanceConfig(BaseModel):
    storages: list[str] = Field(
        default_factory=lambda: [
            "H2OCAN",
            # canopy snow water is missing
            "H2OSFC",
            "H2OSNO",
            "SOILLIQ",
            "SOILICE",
            # water in unconfined aquifer is missing
        ]
    )
    inputs: list[str] = Field(
        default_factory=lambda: [
            "RAIN",
            "SNOW"
        ]
    )
    outputs: list[str] = Field(
        default_factory=lambda: [
            "QFLX_EVAP_TOT",
            "QOVER",
            "QH2OSFC",
            "QDRAI",
            "QDRAI_PERCH",
        ]
    )
    et_components: list[str] = Field(
        default_factory=lambda: ["QSOIL", "QVEGE", "QVEGT"]
    )
    residual_against: str = "dS/dt"
    frame: Literal["water_year", "calendar"] = "water_year"


class CH4Config(BaseModel):
    aerenchyma: list[str] = Field(
        default_factory=lambda: ["CH4_SURF_AERE_SAT", "CH4_SURF_AERE_UNSAT"]
    )
    diffusion: list[str] = Field(
        default_factory=lambda: ["CH4_SURF_DIFF_SAT", "CH4_SURF_DIFF_UNSAT"]
    )
    ebullition: list[str] = Field(
        default_factory=lambda: ["CH4_SURF_EBUL_SAT", "CH4_SURF_EBUL_UNSAT"]
    )


class CarbonBalanceConfig(BaseModel):
    mode: Literal["auto", "bgc", "sp"] = "auto"
    pools: list[str] = Field(
        default_factory=lambda: [
            "LEAFC",
            "LIVESTEMC",
            "DEADSTEMC",
            "FROOTC",
            "LIVECROOTC",
            "DEADCROOTC",
            "TOTSOMC",
            "TOTLITC",
            "CWDC",
        ]
    )
    fluxes: list[str] = Field(
        default_factory=lambda: [
            "GPP",
            "AR",
            "HR",
            "ER",
            "NEE",
            "TOTFIRE",
            "WOOD_HARVESTC",
        ]
    )
    ch4: CH4Config = CH4Config()
    residual_against: str = "TOTECOSYSC"
    frame: Literal["water_year", "calendar"] = "calendar"


class EnergyBalanceConfig(BaseModel):
    radiation: list[str] = Field(
        default_factory=lambda: ["FSDS", "FSR", "FLDS", "FIRE", "FSA", "FIRA"]
    )
    turbulent: list[str] = Field(default_factory=lambda: ["FSH", "EFLX_LH_TOT"])
    ground: list[str] = Field(default_factory=lambda: ["FGR", "FGR12"])
    storage: list[str] = Field(default_factory=lambda: ["HC", "HCSOI"])
    errors: list[str] = Field(default_factory=lambda: ["ERRSOI", "ERRSEB"])
    frame: Literal["water_year", "calendar"] = "calendar"
    cumulative: bool = False


class BalancesConfig(BaseModel):
    water: WaterBalanceConfig = WaterBalanceConfig()
    carbon: CarbonBalanceConfig = CarbonBalanceConfig()
    energy: EnergyBalanceConfig = EnergyBalanceConfig()


class VariableGroupsConfig(BaseModel):
    groups: dict[str, list[str]] = Field(default_factory=dict)


class IOConfig(BaseModel):
    strict_combine: bool = False
    chunk_mode: Literal["off", "auto", "manual"] = "auto"
    chunk_target_mb: int = 64
    chunks: dict[str, int] = Field(default_factory=dict)


class Config(BaseModel):
    """Top-level configuration."""

    report: ReportConfig = ReportConfig()
    plots: PlotsConfig = PlotsConfig()
    io: IOConfig = IOConfig()
    time: TimeConfig = TimeConfig()
    balances: BalancesConfig = BalancesConfig()
    variables: VariableGroupsConfig = VariableGroupsConfig()


# ---------------------------------------------------------------------------
# Loading and merging
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_defaults() -> dict[str, Any]:
    """Load the package-shipped defaults.yaml."""
    with open(_DEFAULTS_PATH) as f:
        return yaml.safe_load(f) or {}


def load_config(
    path: str | Path | None = None,
) -> Config:
    """Load and validate configuration, merging user config over defaults.

    Parameters
    ----------
    path : str or Path, optional
        Path to user config YAML. Falls back to
        ``~/.config/elm-diagnostics/config.yaml`` if it exists,
        otherwise uses defaults only.
    """
    defaults = load_defaults()

    user_config: dict = {}
    if path is not None:
        p = Path(path)
        if p.exists():
            with open(p) as f:
                user_config = yaml.safe_load(f) or {}
    elif _USER_CONFIG_PATH.exists():
        with open(_USER_CONFIG_PATH) as f:
            user_config = yaml.safe_load(f) or {}

    user_balances = user_config.pop("balances", None)
    merged = _deep_merge(defaults, user_config)

    # Balance definitions are internal schema defaults. Expert users may
    # override per-balance blocks (water/carbon/energy) atomically.
    balance_defaults = BalancesConfig().model_dump()
    merged_balances = dict(balance_defaults)
    if user_balances is not None:
        warnings.warn(
            "Advanced override detected: 'balances' in user config. "
            "Provided balances.<type> blocks replace that entire balance definition.",
            UserWarning,
            stacklevel=2,
        )
        if not isinstance(user_balances, dict):
            raise ValueError("'balances' must be a mapping with optional keys: water, carbon, energy")

        allowed_balance_keys = {"water", "carbon", "energy"}
        unknown_balance_keys = set(user_balances) - allowed_balance_keys
        if unknown_balance_keys:
            unknown = ", ".join(sorted(unknown_balance_keys))
            raise ValueError(f"Unknown balances subblock(s): {unknown}")

        required_subkeys = {
            "water": {
                "storages",
                "inputs",
                "outputs",
                "et_components",
                "residual_against",
                "frame",
            },
            "carbon": {
                "mode",
                "pools",
                "fluxes",
                "ch4",
                "residual_against",
                "frame",
            },
            "energy": {
                "radiation",
                "turbulent",
                "ground",
                "storage",
                "errors",
                "frame",
                "cumulative",
            },
        }

        for balance_name, block in user_balances.items():
            if not isinstance(block, dict):
                raise ValueError(f"'balances.{balance_name}' must be a mapping")
            missing_subkeys = required_subkeys[balance_name] - set(block)
            if missing_subkeys:
                missing = ", ".join(sorted(missing_subkeys))
                raise ValueError(
                    f"'balances.{balance_name}' must provide a full block for replacement of a balance definition. "
                    f"Missing key(s): {missing}"
                )
            merged_balances[balance_name] = block

    merged["balances"] = merged_balances
    return Config.model_validate(merged)
