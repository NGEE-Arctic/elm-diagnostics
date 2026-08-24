# elm-diagnostics

Diagnostics and budget-closure tools for E3SM's ELM land model.

## Features

- **Water, Carbon, and Energy Balance Diagnostics** with automatic closure checking
- **Automatic variable derivation**: Computes missing variables like `QFLX_EVAP_TOT` from components
- **Spatial mapping for watersheds**: Georeferenced maps with cartopy for multi-gridcell output
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

## Quick Start

### Generate a Full Diagnostics Report

```bash
elm-diagnostics report /path/to/elm/output
# Creates: elm_report/index.html (with figures and data)
```

### Compare Two Simulations

```bash
elm-diagnostics report /path/to/experiment --compare /path/to/control --out comparison_report/
```

### Check a Specific Balance

```bash
elm-diagnostics balance water /path/to/elm/output --out ./water_analysis/
```

### Plot a Single Variable

```bash
elm-diagnostics plot GPP /path/to/elm/output --kind seasonal --out gpp_seasonal.png
```

### Create Spatial Maps (for Watershed-Scale Data)

```bash
elm-diagnostics map GPP /path/to/watershed/output --out gpp_map.png
```

## Command-Line Interface

elm-diagnostics provides a comprehensive command-line interface for common workflows. All CLI commands support progress indicators, helpful error messages, and multiple verbosity levels.

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

**With custom configuration:**
```bash
elm-diagnostics report /path/to/elm/output --config my_config.yaml
```

**Comparison report:**
```bash
elm-diagnostics report /path/to/experiment --compare /path/to/control --out comparison/
```

### Balance Analysis

**Water balance:**
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
elm-diagnostics plot GPP /path/to/elm/output --out gpp_timeseries.png
```

**Available plot types:**
```bash
elm-diagnostics plot RAIN /path/to/elm/output --kind seasonal --out rain_seasonal.png
elm-diagnostics plot FSH /path/to/elm/output --kind anomaly --out fsh_anomalies.png
elm-diagnostics plot ER /path/to/elm/output --kind histogram --out er_distribution.png
elm-diagnostics plot SOILLIQ /path/to/elm/output --kind hovmuller --out soilliq_hovmuller.png
```

**Available plot types:** `timeseries`, `hovmuller`, `seasonal`, `anomaly`, `histogram`, `diurnal`

### Spatial Mapping (Watershed-Scale Visualization)

**For multi-gridcell data** (watersheds, regions), generate spatial maps:

```bash
# Mean GPP across watershed
elm-diagnostics map GPP /path/to/watershed/output --out gpp_map.png

# Median precipitation with custom time aggregation
elm-diagnostics map RAIN /path/to/watershed/output --time-agg median --out rain_map.png

# Specific timestep (e.g., peak event)
elm-diagnostics map QOVER /path/to/watershed/output --time-agg 0 --out qover_t0.png

# With watershed boundary overlay
elm-diagnostics map TWS /path/to/watershed/output --boundary watershed.geojson --out tws_map.png

# Custom projection
elm-diagnostics map GPP /path/to/watershed/output --projection Orthographic --out gpp_ortho.png
```

**Time aggregation options:** `mean`, `median`, `sum`, `std`, `min`, `max`, or integer timestep index

**Requirements:** Install with maps support: `pip install 'elm-diagnostics[maps]'`

Spatial maps automatically appear in reports when multi-gridcell data is detected. Configure via `config.yaml`:

```yaml
plots:
  spatial:
    enabled: true
    time_aggregation: mean  # or median, sum, etc.
    projection: PlateCarree  # Cartopy projection name
    watershed_boundary: /path/to/boundary.geojson  # optional
    variables:  # Variables to map in reports
      - GPP
      - QFLX_EVAP_TOT
      - QOVER
      - TWS
```

### Verbosity Control

**Verbose output (shows timing and details):**
```bash
elm-diagnostics report /path/to/elm/output --verbose
```

**Debug mode (full tracebacks):**
```bash
elm-diagnostics report /path/to/elm/output --debug
```

**Quiet mode (minimal output, for scripts):**
```bash
elm-diagnostics report /path/to/elm/output --quiet
```

### Common Workflows

**Quick balance check:**
```bash
elm-diagnostics balance water /path/to/elm/output --quiet --out ./quick_check/
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

### Getting Help

```bash
elm-diagnostics --help                # Main help
elm-diagnostics report --help         # Report command help
elm-diagnostics balance --help        # Balance command help
elm-diagnostics plot --help           # Plot command help
```

### Shell Completion

Install tab completion for your shell:

```bash
elm-diagnostics --install-completion
# Supports bash, zsh, fish, PowerShell
```

## Configuration

### Basic Configuration

Create `~/.config/elm-diagnostics/config.yaml` to customize behavior:

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

plots:
  hovmuller:
    max_depth_m: null  # null keeps full vertical extent from source variable

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

See [`elm_diagnostics/config/defaults.yaml`](elm_diagnostics/config/defaults.yaml) for all options.

### Advanced: Expert Balance Overrides

Balance term definitions are intentionally kept internal (schema defaults) to reduce fragile user edits. Expert users can still override balance definitions via a `balances` section in their user config. When `balances` is present, elm-diagnostics always emits a warning and applies replacement semantics:

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

## Documentation

### Tutorials

- **[Getting Started](docs/tutorial-getting-started.md)** - Installation, core concepts, and first steps
- **[Balance Checking](docs/tutorial-balance-checking.md)** - Water, carbon, and energy budget diagnostics
- **[Experiment Comparison](docs/tutorial-experiment-comparison.md)** - Comparing base vs. modified runs
- **[Workflow Examples](docs/workflow-examples.md)** - Common patterns and automation scripts

### Technical Documentation

- **[Python API Reference](docs/python-api.md)** - Programmatic interface for advanced users
- **[Variable Mappings](docs/variable-mappings.md)** - Complete variable definitions and source code references
- **[Assumptions](docs/assumptions.md)** - Verified assumptions from ELM source and real output files
- **[Design Specification](elm-diagnostics-spec.md)** - Detailed design document

## Testing

Run the test suite:
```bash
pytest tests/
```

### Test Data

Real ELM output files for testing are located in `tests/fixtures/data/`. These include 15 months of Oak Harbor single-point simulation data (Oct 2000 - Dec 2001), providing a complete water year for validation of balance closure and multi-file loading.

See [`tests/fixtures/README.md`](tests/fixtures/README.md) for details about test data.

## Requirements

- Python ≥ 3.10
- Core: xarray, numpy, pandas, matplotlib, pint, pint-xarray, typer, rich
- Optional: dask (parallel processing), plotly (interactive plots), cartopy (maps)

## License

BSD-3-Clause

## Citation

If you use this tool in your research, please cite:

```
Fiorella, R., Hoffman, M. (2026). elm-diagnostics: Budget-closure diagnostics for E3SM Land Model.
```

## Contributing

Issues and pull requests welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Acknowledgments

- Variable definitions verified against E3SM IM1 ELM source code
- Design inspired by packages such as  CLM diagnostics package (NCAR) and ILAMB
- Test data: Oak Harbor single-point simulation

---

© 2026. Triad National Security, LLC. All rights reserved.
This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S. Department of Energy/National Nuclear Security Administration. All rights in the program are reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear Security Administration. The Government is granted for itself and others acting on its behalf a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare. derivative works, distribute copies to the public, perform publicly and display publicly, and to permit others to do so.
