# elm-diagnostics

Diagnostics and budget-closure tools for E3SM's ELM land model.

## Features

- **Water, Carbon, and Energy Balance Diagnostics** with automatic closure checking
- **Automatic variable derivation**: Computes missing variables like `QFLX_EVAP_TOT` from components
- **Handles multiple file formats**: Single-point (`lndgrid`) and gridded (`lat`×`lon`) output
- **Vertical aggregation**: Automatically sums 3D soil variables (SOILLIQ, SOILICE) over depth
- **Unit-aware integration**: Uses `pint` for proper unit handling in flux-to-cumulative conversions
- **Water year support**: Configurable water year start month for hydrological analyses
- **Time-bounds-aware**: Uses actual time intervals for accurate flux integration
- **Flexible configuration**: YAML-based configuration with sensible defaults

## Installation

```bash
pip install -e ".[dev]"
```

For optional features:
```bash
pip install -e ".[dask,interactive,maps,all]"
```

## Documentation

### Tutorials

- **[Getting Started](docs/tutorial-getting-started.md)** - Installation, core concepts, and first steps
- **[Balance Checking](docs/tutorial-balance-checking.md)** - Water, carbon, and energy budget diagnostics
- **[Experiment Comparison](docs/tutorial-experiment-comparison.md)** - Comparing base vs. modified runs
- **[Workflow Examples](docs/workflow-examples.md)** - Common patterns and automation scripts

### Technical Documentation

- **[Variable Mappings](docs/variable-mappings.md)** - Complete variable definitions and source code references
- **[Assumptions](docs/assumptions.md)** - Verified assumptions from ELM source and real output files
- **[Design Specification](elm-diagnostics-spec.md)** - Detailed design document

### Where to Start

**I'm new to elm-diagnostics:**  
→ Start with [Getting Started](docs/tutorial-getting-started.md)

**I need to check budget closure:**  
→ Jump to [Balance Checking](docs/tutorial-balance-checking.md)

**I want to compare two simulations:**  
→ See [Experiment Comparison](docs/tutorial-experiment-comparison.md)

**I need examples for specific tasks:**  
→ Browse [Workflow Examples](docs/workflow-examples.md)

**I want to understand variable definitions:**  
→ Check [Variable Mappings](docs/variable-mappings.md)

## Configuration Notes

Most users only need settings under `report`, `plots`, `io`, `time`, and
`variables` in `~/.config/elm-diagnostics/config.yaml`.

Balance term definitions are intentionally kept internal (schema defaults) to
reduce fragile user edits.

### Advanced: Expert Balance Overrides

Expert users can still override balance definitions via a `balances` section in
their user config. When `balances` is present, elm-diagnostics always emits a
warning and applies replacement semantics:

- If `balances.water` is provided, that entire water block is used as-is.
- If `balances.carbon` is provided, that entire carbon block is used as-is.
- If `balances.energy` is provided, that entire energy block is used as-is.
- Omitted subblocks continue using internal schema defaults.
- Partial subblocks are rejected; each provided subblock must be complete.

Example (override only water):

```yaml
balances:
  water:
    storages: [SOILLIQ, SOILICE, H2OSNO, H2OCAN, H2OSFC]
    inputs: [RAIN, SNOW]
    outputs: [QFLX_EVAP_TOT, QOVER, QDRAI, QDRAI_PERCH, QH2OSFC]
    et_components: [QSOIL, QVEGE, QVEGT]
    residual_against: "dS/dt"
    frame: "water_year"
```

## Quick Start

### Loading ELM Output

```python
from elm_diagnostics import Run

# Load a directory containing ELM history files
run = Run("/path/to/case/run")
print(run.streams)  # {'h0': <xr.Dataset>, ...}

# Get a variable (auto-computes if missing)
et_total = run.get("QFLX_EVAP_TOT")  # Computed from QSOIL + QVEGE + QVEGT if not in file
```

### Water Balance

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

### Carbon and Energy Balances

```python
from elm_diagnostics import CarbonBalance, EnergyBalance

# Carbon balance (auto-detects BGC vs SP mode)
cb = CarbonBalance(run, year=2015)
fig_c, fig_d = cb.plot()

# Energy balance (fluxes only by default)
eb = EnergyBalance(run, year=2015)
fig_e, fig_f = eb.plot()
```

### Plotting Individual Variables

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

# Multi-panel figure
import matplotlib.pyplot as plt
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
plot_timeseries(run, "GPP", ax=axes[0, 0])
plot_seasonal(run, "RAIN", ax=axes[0, 1])
plot_anomaly(run, "FSH", ax=axes[1, 0])
plot_histogram(run, "EFLX_LH_TOT", ax=axes[1, 1])
fig.tight_layout()
fig.savefig("multi_panel.png")
```

**Available plot types:**
- **`plot_timeseries`**: Time series with optional climatology envelope
- For variables with a vertical dimension (`levgrnd`, `levsoi`, etc.),
  `plot_timeseries` draws one line per depth with color varying by depth
  and an automatically thinned depth legend.
- **`plot_hovmuller`**: Hovmuller diagram (time on x-axis, depth on y-axis,
  colored by variable value)
- **`plot_seasonal`**: Monthly mean seasonal cycle with spread (minmax/p10_p90/std)
- **`plot_anomaly`**: Annual anomalies as bar chart (positive=blue, negative=red)
- **`plot_histogram`**: Distribution histogram or PDF
- **`plot_diurnal`**: Hourly mean diurnal cycle (for sub-daily data)

### Sub-gridcell Plotting (dov2xy = .false.)

For ELM runs with sub-gridcell output, all plot functions and balances support faceting by `column`, `pft`, or `landunit`:

```python
from elm_diagnostics import Run, WaterBalance
from elm_diagnostics.plots import plot_timeseries, plot_seasonal

# Load multi-column run (dov2xy = .false.)
run = Run("/path/to/multicolumn/output")

# ===== FACETED PLOTS =====

# Plot GPP for each column separately (creates 2×2 grid if 3 columns)
fig = plot_timeseries(run, "GPP", by="column")
fig.savefig("gpp_by_column.png")

# Seasonal cycle per PFT
fig = plot_seasonal(run, "GPP", by="pft")
fig.savefig("gpp_seasonal_by_pft.png")

# Annual anomalies by landunit
fig = plot_anomaly(run, "QOVER", by="landunit")
fig.savefig("qover_anomaly_by_landunit.png")

# All plot types support the 'by' parameter:
# - plot_timeseries, plot_seasonal, plot_anomaly
# - plot_histogram, plot_diurnal

# ===== FACETED BALANCES =====

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

**Error handling:**
- Clear error if variable doesn't have the requested dimension
- Clear error if dataset is gridcell-averaged (dov2xy = .true.)
- Cannot combine `by` parameter with `ax` parameter (facets create their own figure)

### HTML Report Generation

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

**Report Features:**
- **Interactive thumbnails**: Click images to view full-size in lightbox modal
- **Comprehensive coverage**: All 3 balance types (water, carbon, energy) + variable groups
- **Multiple plot types**: Timeseries, Hovmuller, seasonal, anomaly, histogram, and diurnal for each variable
- **Grouped plot subsections**: Variable sections include plot-type subheadings
  (for example, Timeseries plots and Hovmuller plots)
- **Statistics tables**: Summary statistics for each balance section
- **Error diagnostics**: Clear reporting of any issues encountered
- **Comparison support**: Side-by-side base vs. experiment analysis
- **Responsive design**: Works on desktop, tablet, and mobile
- **TOC sidebar**: Easy navigation between sections

**Comparison Reports:**
```python
from elm_diagnostics import Run, Comparison, Report

base = Run("/path/to/base/run", name="Control")
experiment = Run("/path/to/exp/run", name="Modified")
comparison = Comparison(base, experiment)

report = Report(comparison)
report.build("comparison_report/")
# Report includes both runs with delta plots
```

**Customization:**
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
```

**Configuration Options (in `~/.config/elm-diagnostics/config.yaml`):**
```yaml
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
  
  metadata:
    show_run_info: true
    show_generation_timestamp: true

plots:
  hovmuller:
    max_depth_m: null  # null keeps full vertical extent from source variable
                      # set a float (meters) to cap plotted depth/height

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

## Command-Line Interface

elm-diagnostics provides a comprehensive command-line interface for common workflows. All CLI commands support progress indicators, helpful error messages, and multiple verbosity levels.

### Installation

The CLI is automatically available after installation:

```bash
pip install -e ".[dev]"
# CLI command is now in your PATH
elm-diagnostics --help
```

### Basic Usage

**Generate a full diagnostics report:**
```bash
elm-diagnostics report /path/to/elm/output
# Creates: elm_report/index.html (with figures and data)
```

**Compute a specific balance:**
```bash
elm-diagnostics balance water /path/to/elm/output --config year_2015.yaml
```

**Plot a single variable:**
```bash
elm-diagnostics plot GPP /path/to/elm/output --kind seasonal
```

### Report Generation

**Basic report:**
```bash
elm-diagnostics report /path/to/elm/output
# Creates: elm_report/index.html
```

**Custom output directory:**
```bash
elm-diagnostics report /path/to/elm/output --out my_diagnostics
```

**Specific analysis window (from config):**
```bash
elm-diagnostics report /path/to/elm/output --config year_2015.yaml
```

**Custom analysis range (from config):**
```bash
elm-diagnostics report /path/to/elm/output --config analysis_2000_2010.yaml
```

**Comparison report:**
```bash
elm-diagnostics report /path/to/experiment --compare /path/to/control
```

**With custom configuration:**
```bash
elm-diagnostics report /path/to/elm/output --config my_config.yaml
```

**Water year customization:**
```bash
elm-diagnostics report /path/to/elm/output --config wy_october.yaml
# Set time.water_year_start_month: 10 in wy_october.yaml
```

### Balance Analysis

**Water balance with a config-defined year window:**
```bash
elm-diagnostics balance water /path/to/elm/output --config year_2015.yaml
# Shows plots interactively (if display available)
```

**Save to directory:**
```bash
elm-diagnostics balance water /path/to/elm/output --out ./results/
# Creates: results/water_panel1.png
#          results/water_panel2.png
#          results/water_balance.nc
```

**Carbon balance:**
```bash
elm-diagnostics balance carbon /path/to/elm/output --out ./carbon_analysis/
```

**Energy balance:**
```bash
elm-diagnostics balance energy /path/to/elm/output --out ./energy_analysis/
```

### Variable Plotting

**Timeseries (default):**
```bash
elm-diagnostics plot GPP /path/to/elm/output
# Shows interactive plot
```

**Save to file:**
```bash
elm-diagnostics plot GPP /path/to/elm/output --out gpp_timeseries.png
```

**Seasonal cycle:**
```bash
elm-diagnostics plot RAIN /path/to/elm/output --kind seasonal --out rain_seasonal.png
```

**Annual anomalies:**
```bash
elm-diagnostics plot FSH /path/to/elm/output --kind anomaly --out fsh_anomalies.png
```

**Histogram:**
```bash
elm-diagnostics plot ER /path/to/elm/output --kind histogram --out er_distribution.png
```

**Available plot types:** `timeseries`, `hovmuller`, `seasonal`, `anomaly`, `histogram`, `diurnal`

### Verbosity Control

**Verbose output (shows timing and details):**
```bash
elm-diagnostics report /path/to/elm/output --verbose
```

Example output:
```
Loading ELM data... ✓
Loaded data in 2.3s
Building diagnostics report...
✓ Report generated in 45.2s

Report generated: /path/to/elm_report/index.html
  Output directory: /Users/user/elm_report
  Figures: /Users/user/elm_report/figures
  Data: /Users/user/elm_report/data
```

**Debug mode (full tracebacks):**
```bash
elm-diagnostics report /path/to/elm/output --debug
# Useful for troubleshooting errors
```

**Quiet mode (minimal output, for scripts):**
```bash
elm-diagnostics report /path/to/elm/output --quiet
# Only shows final result:
# Report generated: /path/to/elm_report/index.html
```

### Progress Indicators

Long-running operations automatically show progress:
- Loading data (if >5 seconds)
- Computing balances (if >5 seconds)
- Generating reports (always shown)

Progress can be suppressed with `--quiet` or enhanced with `--verbose`.

### Error Handling

The CLI provides helpful error messages with suggestions:

```bash
$ elm-diagnostics report /nonexistent/path
Error: Directory not found: /nonexistent/path

The specified path does not exist. Please check:
  • Path is spelled correctly
  • You have permission to access it
  • Current directory: /Users/user/work

Example: elm-diagnostics report /path/to/elm/output
```

```bash
$ elm-diagnostics balance nitrogen /path/to/elm/output
Error: Unknown balance type: nitrogen

Valid options: water, carbon, energy

Example: elm-diagnostics balance water /path/to/elm/output
```

### Shell Completion

Install tab completion for your shell:

```bash
elm-diagnostics --install-completion
# Supports bash, zsh, fish, PowerShell
```

Then use tab completion:
```bash
elm-diagnostics balance <TAB>
# Suggests: water  carbon  energy

elm-diagnostics plot GPP /path --kind <TAB>
# Suggests: timeseries  seasonal  anomaly  histogram  diurnal
```

### Getting Help

**Main help:**
```bash
elm-diagnostics --help
```

**Command-specific help:**
```bash
elm-diagnostics report --help
elm-diagnostics balance --help
elm-diagnostics plot --help
```

All help text includes usage examples and detailed descriptions.

### Common Workflows

**Quick balance check:**
```bash
elm-diagnostics balance water /path/to/elm/output --quiet --out ./quick_check/
# Fast, minimal output, saves figures
```

**Full annual report with verbose output:**
```bash
elm-diagnostics report /path/to/elm/output --config year_2015.yaml --verbose --out annual_2015
```

**Automated script usage:**
```bash
#!/bin/bash
# Process multiple runs
for run in run_*/; do
    elm-diagnostics report "$run" --quiet --out "reports/${run%/}"
done
```

**Comparison workflow:**
```bash
# 1. Generate individual reports
elm-diagnostics report baseline/ --out baseline_report/
elm-diagnostics report experiment/ --out experiment_report/

# 2. Generate comparison report
elm-diagnostics report experiment/ --compare baseline/ --out comparison_report/
```

## Example with Real Data

Using the included test file (`oakharbor_column.elm.elm.h0.2002-01.nc`):

```python
from elm_diagnostics import Run, WaterBalance

# Load the oakharbor test data
run = Run(".", name="oakharbor")

# The file doesn't have QFLX_EVAP_TOT, but it's computed automatically:
et = run.get("QFLX_EVAP_TOT")  # Computes from QSOIL + QVEGE + QVEGT
print(et.attrs["description"])  # "Computed as QSOIL + QVEGE + QVEGT"

# SOILLIQ and SOILICE are 3D (time, levgrnd, lndgrid) - automatically summed:
soilliq = run.get("SOILLIQ")  # Has levgrnd dimension
print(soilliq.dims)  # ('time', 'levgrnd', 'lndgrid')

# Water balance automatically handles vertical aggregation
wb = WaterBalance(run)
components = wb.components()  # SOILLIQ and SOILICE summed over levgrnd
```

## Documentation

- [`docs/assumptions.md`](docs/assumptions.md) - Verified assumptions from ELM source and real h0 files
- [`docs/variable-mappings.md`](docs/variable-mappings.md) - Complete variable definitions and source code references
- [Design Specification](elm-diagnostics-spec.md) - Detailed design document

## Key Corrections from ELM Source Analysis

Based on comprehensive analysis of E3SM IM1 ELM source code (April 2026):

### Water Balance
- ✅ **QFLX_EVAP_TOT** = QSOIL + QVEGE + QVEGT (marked `default='inactive'` in ELM, must compute or request explicitly)
- ✅ **QSNWCPICE is NOT sublimation** - it's excess snow removal (runoff), removed from ET outputs
- ✅ **SOILLIQ and SOILICE** require summing over 15 vertical levels (`levgrnd`)
- ✅ ET components verified: QSOIL (ground evap), QVEGE (canopy evap), QVEGT (transpiration)

### Energy Balance
- ✅ **HC** (soil+snow heat content) and **HCSOI** (soil-only) are correct names (not `hc_soisno`)
- ✅ Both marked `default='inactive'`, must request via `fincl1 = 'HC'` in user_nl_elm
- ✅ These are state variables (MJ/m²), not fluxes - need dHC/dt for flux equivalent

### Carbon Balance
- ✅ **TOTFIRE** (not COL_FIRE_CLOSS)
- ✅ **WOOD_HARVESTC** (not HRV_XSMRPOOL_TO_ATM)
- ✅ CH4 fluxes use **_SAT / _UNSAT** suffixes (not _SOIL)

## Testing

Run the test suite:
```bash
pytest tests/
```

Current status: **161 tests passing** (including 45 sub-gridcell tests, 17 report tests, 35 CLI tests)

### Test Data

Real ELM output files for testing are located in `tests/fixtures/data/`. These include 15 months of Oak Harbor single-point simulation data (Oct 2000 - Dec 2001), providing a complete water year for validation of balance closure and multi-file loading.

See [`tests/fixtures/README.md`](tests/fixtures/README.md) for details about test data.

## Configuration

Create `~/.config/elm-diagnostics/config.yaml` to customize:

```yaml
time:
  water_year_start_month: 10  # October start for water year

balances:
  water:
    storages: [SOILLIQ, SOILICE, H2OSNO, H2OCAN, H2OSFC]
    inputs: [RAIN, SNOW]
    outputs: [QFLX_EVAP_TOT, QOVER, QDRAI, QDRAI_PERCH, QSNOMELT]
    et_components: [QSOIL, QVEGE, QVEGT]  # Used if QFLX_EVAP_TOT missing
```

See [`elm_diagnostics/config/defaults.yaml`](elm_diagnostics/config/defaults.yaml) for all options.

## Requirements

- Python ≥ 3.10
- Core: xarray, numpy, pandas, matplotlib, pint, pint-xarray
- Optional: dask (parallel processing), plotly (interactive plots), cartopy (maps)

## Development Status

**Current Phase:** Phase 6 Complete (HTML Report Generation)

✅ **Completed:**
- Phase 0: ELM source code verification and variable name corrections
- Phase 1: I/O, Run, Comparison classes with auto-derivation
- Phase 2: Time handling, water-year support, unit-aware integration
- Phase 3: Water, Carbon, Energy balance classes
- Phase 3.5: Real data validation with oakharbor h0 file
- Phase 4: General variable plots (timeseries, seasonal, anomaly, histogram, diurnal)
- Phase 5: Sub-gridcell support (column, pft, landunit faceting for all plots and balances)
- Phase 6: HTML report generation (thumbnails, lightbox, statistics, error handling, comprehensive testing)
- **Phase 7: CLI implementation** (rich progress indicators, enhanced error handling, verbose/debug/quiet modes, 35 comprehensive tests)
- All 161 tests passing (35 new CLI tests added in Phase 7)

🚧 **Next Phase:**
- Phase 8: User documentation, tutorials, and worked examples

## License

BSD-3-Clause

## Citation

If you use this tool in your research, please cite:

```
Fiorella, R. (2026). elm-diagnostics: Budget-closure diagnostics for E3SM Land Model.
```

## Contributing

Issues and pull requests welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Acknowledgments

- Variable definitions verified against E3SM IM1 ELM source code
- Design inspired by CLM diagnostics package (NCAR) and ILAMB
- Test data: Oak Harbor single-point simulation
