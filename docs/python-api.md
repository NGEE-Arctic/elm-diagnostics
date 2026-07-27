# Python API Reference

This document provides detailed information about the Python API for advanced users who want to use `elm-diagnostics` programmatically rather than through the CLI.

**Note:** For most users, the CLI interface is recommended. See the main [README](../README.md) for CLI usage.

## Table of Contents

1. [Loading ELM Output](#loading-elm-output)
2. [Water Balance](#water-balance)
3. [Carbon and Energy Balances](#carbon-and-energy-balances)
4. [Plotting Individual Variables](#plotting-individual-variables)
5. [Sub-gridcell Analysis](#sub-gridcell-analysis)
6. [HTML Report Generation](#html-report-generation)
7. [Configuration](#configuration)

---

## Loading ELM Output

### Basic Usage

```python
from elm_diagnostics import Run

# Load a directory containing ELM history files
run = Run("/path/to/case/run")
print(run.streams)  # {'h0': <xr.Dataset>, ...}

# Get a variable (auto-computes if missing)
et_total = run.get("QFLX_EVAP_TOT")  # Computed from QSOIL + QVEGE + QVEGT if not in file
```

### The `Run` Class

The `Run` class is the main interface for loading and accessing ELM output data.

**Constructor:**
```python
Run(path: str | Path, name: str = None)
```

**Parameters:**
- `path`: Directory containing ELM history files (`*.elm.h*.nc`)
- `name`: Optional name for the run (used in plots and reports)

**Attributes:**
- `streams`: Dictionary of xarray Datasets, keyed by history tape (`h0`, `h1`, etc.)
- `name`: Run name

**Methods:**
- `get(varname: str) -> xr.DataArray`: Get a variable, computing it if missing
- `has(varname: str) -> bool`: Check if a variable is available or can be computed

**Auto-discovery Features:**
- Automatically discovers all `*.elm.h*.nc` files in the directory
- Groups files by history tape number (`h0`, `h1`, ...)
- Lazy-loads data with `xarray.open_mfdataset`
- Auto-computes missing variables (e.g., `QFLX_EVAP_TOT = QSOIL + QVEGE + QVEGT`)
- Auto-aggregates 3D soil variables over vertical dimension

### Example: Working with Variables

```python
from elm_diagnostics import Run

run = Run("./tests/fixtures/data/", name="oakharbor")

# The file doesn't have QFLX_EVAP_TOT, but it's computed automatically:
et = run.get("QFLX_EVAP_TOT")  # Computes from QSOIL + QVEGE + QVEGT
print(et.attrs["description"])  # "Computed as QSOIL + QVEGE + QVEGT"

# SOILLIQ and SOILICE are 3D (time, levgrnd, lndgrid) - automatically summed:
soilliq = run.get("SOILLIQ")  # Has levgrnd dimension
print(soilliq.dims)  # ('time', 'levgrnd', 'lndgrid')

# Check if a variable is available
if run.has("GPP"):
    gpp = run.get("GPP")
```

---

## Water Balance

### Basic Usage

```python
from elm_diagnostics import WaterBalance

# Compute water balance for a specific year
wb = WaterBalance(run, year=2015, frame="water_year")

# Get balance components (all cumulative, in mm)
components = wb.components()
print(components.keys())  # RAIN, SNOW, QFLX_EVAP_TOT, QOVER, QDRAI, dS, ...

# Check closure residual
residual = wb.residual()
print(f"Residual: {residual.values[-1]:.2f} mm")

# Plot
fig_cumulative, fig_decomposition = wb.plot()
fig_cumulative.savefig("water_balance.png")

# Save to NetCDF
wb.to_netcdf("water_balance_2015.nc")
```

### The `WaterBalance` Class

**Constructor:**
```python
WaterBalance(
    run: Run,
    year: int = None,
    frame: Literal["calendar_year", "water_year"] = "water_year",
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
)
```

**Parameters:**
- `run`: Run object containing ELM output
- `year`: Specific year to analyze (default: all years)
- `frame`: Time frame for analysis
  - `"water_year"`: Oct-Sep water year (configurable start month)
  - `"calendar_year"`: Jan-Dec calendar year
- `by`: Sub-gridcell dimension for faceting (default: None = gridcell average)
- `config`: Custom configuration (default: uses defaults merged with user config)

**Methods:**
- `components() -> dict[str, xr.DataArray]`: Get all balance components (cumulative, in mm)
- `residual() -> xr.DataArray`: Compute closure residual
- `plot() -> tuple[Figure, Figure]`: Generate balance plots (cumulative and decomposition)
- `to_netcdf(path: str)`: Save components to NetCDF file

**Balance Components:**
- **Inputs**: `RAIN`, `SNOW` (cumulative precipitation)
- **Outputs**: 
  - `QFLX_EVAP_TOT` (total evapotranspiration)
  - `QOVER` (surface runoff)
  - `QDRAI` (sub-surface drainage)
  - `QDRAI_PERCH` (perched water table drainage)
- **Storage change**: `dS` (change in total water storage)
- **Residual**: `inputs - outputs - dS`

---

## Carbon and Energy Balances

### Carbon Balance

```python
from elm_diagnostics import CarbonBalance

# Carbon balance (auto-detects BGC vs SP mode)
cb = CarbonBalance(run, year=2015)
fig_c, fig_d = cb.plot()
fig_c.savefig("carbon_balance.png")

# Get components
components = cb.components()
print(components.keys())  # GPP, ER, NBP, fire losses, harvest, dC, ...
```

**Constructor:**
```python
CarbonBalance(
    run: Run,
    year: int = None,
    frame: Literal["calendar_year", "water_year"] = "calendar_year",
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
)
```

### Energy Balance

```python
from elm_diagnostics import EnergyBalance

# Energy balance (fluxes only by default)
eb = EnergyBalance(run, year=2015)
fig_e, fig_f = eb.plot()
fig_e.savefig("energy_balance.png")

# Get components
components = eb.components()
print(components.keys())  # FSA, EFLX_LH_TOT, FSH, FGR, ...
```

**Constructor:**
```python
EnergyBalance(
    run: Run,
    year: int = None,
    frame: Literal["calendar_year", "water_year"] = "calendar_year",
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
)
```

---

## Plotting Individual Variables

### Available Plot Functions

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import (
    plot_timeseries,
    plot_hovmuller,
    plot_seasonal,
    plot_anomaly,
    plot_histogram,
    plot_diurnal,
)

run = Run("/path/to/case")

# Time series with climatology envelope (for multi-year data)
fig = plot_timeseries(run, "GPP")
fig.savefig("gpp_timeseries.png")

# Vertically resolved variable: one line per depth level with depth-colored legend
fig = plot_timeseries(run, "SOILLIQ")
fig.savefig("soilliq_depth_timeseries.png")

# Hovmuller plot for vertically resolved variables (time x depth)
fig = plot_hovmuller(run, "SOILLIQ")
fig.savefig("soilliq_hovmuller.png")

# Seasonal cycle (monthly mean with spread)
fig = plot_seasonal(run, "RAIN")
fig.savefig("rain_seasonal.png")

# Annual anomalies (bar chart)
fig = plot_anomaly(run, "FSH")
fig.savefig("fsh_anomalies.png")

# Distribution histogram
fig = plot_histogram(run, "QSOIL", bins=50, density=True)
fig.savefig("qsoil_histogram.png")

# Diurnal cycle (for sub-daily data, e.g., h1 tapes)
fig = plot_diurnal(run, "GPP")  # Shows message if not sub-daily
fig.savefig("gpp_diurnal.png")
```

### Plot Function Signatures

#### `plot_timeseries`
```python
plot_timeseries(
    run: Run,
    varname: str,
    ax: Axes = None,
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
) -> Figure
```

#### `plot_hovmuller`
```python
plot_hovmuller(
    run: Run,
    varname: str,
    ax: Axes = None,
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
) -> Figure
```

#### `plot_seasonal`
```python
plot_seasonal(
    run: Run,
    varname: str,
    ax: Axes = None,
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
) -> Figure
```

#### `plot_anomaly`
```python
plot_anomaly(
    run: Run,
    varname: str,
    ax: Axes = None,
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
) -> Figure
```

#### `plot_histogram`
```python
plot_histogram(
    run: Run,
    varname: str,
    bins: int = 30,
    density: bool = False,
    ax: Axes = None,
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
) -> Figure
```

#### `plot_diurnal`
```python
plot_diurnal(
    run: Run,
    varname: str,
    ax: Axes = None,
    by: Literal["column", "pft", "landunit"] = None,
    config: Config = None
) -> Figure
```

### Multi-Panel Figures

```python
import matplotlib.pyplot as plt
from elm_diagnostics.plots import plot_timeseries, plot_seasonal, plot_anomaly, plot_histogram

fig, axes = plt.subplots(2, 2, figsize=(12, 10))
plot_timeseries(run, "GPP", ax=axes[0, 0])
plot_seasonal(run, "RAIN", ax=axes[0, 1])
plot_anomaly(run, "FSH", ax=axes[1, 0])
plot_histogram(run, "EFLX_LH_TOT", ax=axes[1, 1])
fig.tight_layout()
fig.savefig("multi_panel.png")
```

---

## Sub-gridcell Analysis

For ELM runs with sub-gridcell output (`dov2xy = .false.`), all plot functions and balances support faceting by `column`, `pft`, or `landunit`.

### Sub-gridcell Plots

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import plot_timeseries, plot_seasonal

# Load multi-column run (dov2xy = .false.)
run = Run("/path/to/multicolumn/output")

# Plot GPP for each column separately (creates 2×2 grid if 3 columns)
fig = plot_timeseries(run, "GPP", by="column")
fig.savefig("gpp_by_column.png")

# Seasonal cycle per PFT
fig = plot_seasonal(run, "GPP", by="pft")
fig.savefig("gpp_seasonal_by_pft.png")

# Annual anomalies by landunit
fig = plot_anomaly(run, "QOVER", by="landunit")
fig.savefig("qover_anomaly_by_landunit.png")
```

### Sub-gridcell Balances

```python
from elm_diagnostics import WaterBalance

# Compute water balance for each column independently
wb = WaterBalance(run, year=2015, frame="water_year", by="column")

# Components have 'column' dimension preserved
components = wb.components()
print(components["RAIN"].dims)  # ('time', 'column')

# Check closure per column
residual = wb.residual()
for col in residual.column.values:
    col_residual = residual.sel(column=col).values[-1]
    print(f"Column {col} residual: {col_residual:.2f} mm")

# Plot creates faceted figures (one panel per column)
fig_cumulative, fig_decomposition = wb.plot()
fig_cumulative.savefig("water_balance_by_column.png")

# Carbon and energy balances also support 'by' parameter:
from elm_diagnostics import CarbonBalance, EnergyBalance

cb = CarbonBalance(run, year=2015, by="column")
eb = EnergyBalance(run, year=2015, by="column")
```

### Error Handling

- Clear error if variable doesn't have the requested dimension
- Clear error if dataset is gridcell-averaged (dov2xy = .true.)
- Cannot combine `by` parameter with `ax` parameter (facets create their own figure)

---

## HTML Report Generation

### Basic Usage

Generate comprehensive HTML reports with all diagnostics, figures, and statistics in a single page:

```python
from elm_diagnostics import Run, Report

# Generate report for a single run
run = Run("/path/to/case/run")
report = Report(run)
report.build("output_directory/")
# Creates: output_directory/index.html
#          output_directory/figures/*.png
#          output_directory/data/*.nc
```

### The `Report` Class

**Constructor:**
```python
Report(
    run_or_comparison: Run | Comparison,
    config: Config = None
)
```

**Parameters:**
- `run_or_comparison`: Either a single `Run` object or a `Comparison` object
- `config`: Custom configuration (default: uses defaults merged with user config)

**Methods:**
- `build(output_dir: str) -> Path`: Generate report and return path to index.html

### Report Features

- **Interactive thumbnails**: Click images to view full-size in lightbox modal
- **Comprehensive coverage**: All 3 balance types (water, carbon, energy) + variable groups
- **Multiple plot types**: Timeseries, Hovmuller, seasonal, anomaly, histogram, and diurnal for each variable
- **Grouped plot subsections**: Variable sections include plot-type subheadings
- **Statistics tables**: Summary statistics for each balance section
- **Error diagnostics**: Clear reporting of any issues encountered
- **Comparison support**: Side-by-side base vs. experiment analysis
- **Responsive design**: Works on desktop, tablet, and mobile
- **TOC sidebar**: Easy navigation between sections

### Comparison Reports

```python
from elm_diagnostics import Run, Comparison, Report

base = Run("/path/to/base/run", name="Control")
experiment = Run("/path/to/exp/run", name="Modified")
comparison = Comparison(base, experiment)

report = Report(comparison)
report.build("comparison_report/")
# Report includes both runs with delta plots
```

### Programmatic Customization

```python
from elm_diagnostics.config.schema import Config, load_config

# Load custom configuration
config = load_config("my_config.yaml")
report = Report(run, config=config)

# Or modify programmatically
config.report.thumbnails.enabled = True
config.report.sections.diagnostics = False
config.variable_groups["hydrology"].plot_types.hovmuller = False
config.variable_groups["hydrology"].plot_types.histogram = False
config.report.variable_sections.max_variables_per_group = 5

report = Report(run, config=config)
report.build("output/")
```

---

## Configuration

### Loading Configuration

```python
from elm_diagnostics.config.schema import Config, load_config

# Load from file
config = load_config("my_config.yaml")

# Or use defaults merged with user config
config = load_config()  # Loads ~/.config/elm-diagnostics/config.yaml if exists
```

### The `Comparison` Class

For comparing two runs:

```python
from elm_diagnostics import Run, Comparison

base = Run("/path/to/base", name="Control")
experiment = Run("/path/to/experiment", name="Modified")

comparison = Comparison(base, experiment)

# Access individual runs
print(comparison.base.name)        # "Control"
print(comparison.experiment.name)  # "Modified"

# Get delta for a variable
delta_gpp = comparison.get_delta("GPP")
```

**Constructor:**
```python
Comparison(base: Run, experiment: Run)
```

**Attributes:**
- `base`: Base (control) run
- `experiment`: Experiment (modified) run

**Methods:**
- `get_delta(varname: str) -> xr.DataArray`: Compute experiment - base difference

### Configuration Schema

The configuration system uses Pydantic models for validation. Key configuration sections:

```yaml
time:
  water_year_start_month: 10  # October start for water year

report:
  sections:
    metadata: true
    water_balance: true
    energy_balance: true
    carbon_balance: true
    variable_groups: true
    diagnostics: true

  thumbnails:
    enabled: true
    size: [400, 300]
    dpi: 72
  
  variable_sections:
    max_variables_per_group: 10
    show_statistics_table: true
  
  balance_sections:
    show_statistics_table: true
    show_residual_percentage: true
  
  comparison:
    show_delta_plots: true
    side_by_side_layout: true

plots:
  style:
    figsize: [8.0, 5.0]
    dpi: 150
    palette: "tab10"
  
  climatology:
    include_climos: true
    climo_start_year: -1
    climo_end_year: -1
    envelope: "minmax"  # or "p10_p90", "std"
  
  hovmuller:
    max_depth_m: null
    color_limit_method: "full_range"  # or "quantile", "sigma_clip"

variable_groups:
  hydrology:
    enabled: true
    variables: [H2OSOI, QRUNOFF, SOILLIQ]
    plot_types:
      timeseries: true
      hovmuller: false
      seasonal: true
      anomaly: true
      histogram: false
      diurnal: false
```

---

## Advanced Examples

### Custom Analysis Workflow

```python
from elm_diagnostics import Run, WaterBalance, CarbonBalance
from elm_diagnostics.plots import plot_timeseries
import matplotlib.pyplot as plt

# Load run
run = Run("/path/to/elm/output", name="MyRun")

# Compute balances for multiple years
years = [2010, 2011, 2012]
water_residuals = []
for year in years:
    wb = WaterBalance(run, year=year, frame="water_year")
    residual = wb.residual()
    water_residuals.append(residual.values[-1])
    print(f"{year}: {residual.values[-1]:.2f} mm")

# Plot residuals
fig, ax = plt.subplots()
ax.bar(years, water_residuals)
ax.set_ylabel("Water Balance Residual (mm)")
ax.set_xlabel("Year")
fig.savefig("residuals_by_year.png")

# Detailed carbon balance analysis
cb = CarbonBalance(run, year=2011)
components = cb.components()

# Plot GPP and ER
fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
components["GPP"].plot(ax=axes[0])
axes[0].set_title("Gross Primary Production")
components["ER"].plot(ax=axes[1])
axes[1].set_title("Ecosystem Respiration")
fig.tight_layout()
fig.savefig("gpp_er_comparison.png")
```

### Batch Processing Multiple Runs

```python
from pathlib import Path
from elm_diagnostics import Run, Report

# Process all runs in a directory
base_dir = Path("/path/to/ensemble/runs")
for run_dir in base_dir.glob("run_*"):
    print(f"Processing {run_dir.name}...")
    
    run = Run(run_dir, name=run_dir.name)
    report = Report(run)
    report.build(f"reports/{run_dir.name}")
    
    print(f"  Report saved to reports/{run_dir.name}/index.html")
```

---

## See Also

- [Variable Mappings](variable-mappings.md) - Complete variable definitions
- [Assumptions](assumptions.md) - Verified assumptions from ELM source
- [Main README](../README.md) - CLI usage and quick start
