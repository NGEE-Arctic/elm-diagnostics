# Common Workflows

This document provides copy-paste ready workflows and automation examples for common `elm-diagnostics` tasks. Examples are organized by complexity and use the Oak Harbor test dataset for reproducibility.

## Overview

Workflows covered:
- [Time Series Analysis](#time-series-analysis) - Seasonal patterns, anomalies, trends
- [Batch Processing](#batch-processing) - Multiple runs and years
- [Custom Analysis Scripts](#custom-analysis-scripts) - Publication-ready metrics
- [Troubleshooting](#troubleshooting-workflows) - Diagnosing issues
- [Configuration](#configuration-examples) - Customizing behavior
- [Performance](#performance-tips) - Handling large datasets
- [Documentation](#documentation-and-reproducibility) - Publication scripts

## Time Series Analysis

### Seasonal Patterns

Analyze seasonal cycle for multiple variables:

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import plot_seasonal

run = Run("tests/fixtures/data", name="Oak Harbor")

# Define variables of interest
variables = ["GPP", "QFLX_EVAP_TOT", "FSH", "RAIN"]

# Generate seasonal plots
for var in variables:
    fig = plot_seasonal(run, var)
    fig.savefig(f"seasonal_{var}.png", dpi=300, bbox_inches="tight")
    print(f"Saved seasonal_{var}.png")
```

**Customize seasonal plot envelope:**

```python
from elm_diagnostics.plots import plot_seasonal

# Min/max envelope (default)
fig = plot_seasonal(run, "GPP")

# Could customize via config file to use percentiles or std
# See Configuration section below
```

### Annual Anomalies

Calculate anomalies relative to multi-year climatology:

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import plot_anomaly

run = Run("tests/fixtures/data")

# Plot annual anomalies (deviations from mean)
fig = plot_anomaly(run, "GPP")
fig.savefig("gpp_anomalies.png", dpi=300)
```

**Manual anomaly calculation:**

```python
import xarray as xr

# Get variable
gpp = run.get("GPP")

# Compute climatology (multi-year mean)
climatology = gpp.groupby("time.month").mean("time")

# Compute anomalies
anomalies = gpp.groupby("time.month") - climatology

# Annual mean anomalies
annual_anomalies = anomalies.groupby("time.year").mean()

print("Annual GPP anomalies (gC/m²/day):")
for year, value in zip(annual_anomalies.year.values, annual_anomalies.values):
    print(f"  {year}: {value.item():+.2f}")
```

### Multi-Year Trends

Analyze long-term trends:

```python
from elm_diagnostics import Run
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt

run = Run("tests/fixtures/data")
gpp = run.get("GPP")

# Compute annual means
annual_mean = gpp.groupby("time.year").mean()

# Extract values
years = annual_mean.year.values
values = annual_mean.values.flatten()

# Linear trend
slope, intercept, r_value, p_value, std_err = stats.linregress(years, values)

print(f"Trend: {slope:.3f} gC/m²/day per year")
print(f"R² = {r_value**2:.3f}")
print(f"p-value = {p_value:.4f}")

# Plot with trend line
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(years, values, 'o-', label='Annual mean', markersize=8)
ax.plot(years, intercept + slope * years, '--', label=f'Trend ({slope:.3f}/yr)', color='red')
ax.set_xlabel('Year')
ax.set_ylabel('GPP (gC/m²/day)')
ax.set_title('GPP Trend Analysis')

### Vertical Time Series (Depth-Resolved Variables)

For variables with a vertical dimension (for example `SOILLIQ(time, levgrnd)`),
`plot_timeseries` draws one line per depth and uses color to encode depth.
The legend is thinned to representative levels when many depths are present.

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import plot_timeseries

run = Run("tests/fixtures/data")

fig = plot_timeseries(run, "SOILLIQ")
fig.savefig("soilliq_depth_timeseries.png", dpi=300, bbox_inches="tight")
```

### Hovmuller (Time x Depth) Visualization

Use Hovmuller plots for a compact view of temporal evolution across depth.

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import plot_hovmuller

run = Run("tests/fixtures/data")

fig = plot_hovmuller(run, "SOILLIQ")
fig.savefig("soilliq_hovmuller.png", dpi=300, bbox_inches="tight")
```

Optional config to cap plotted depth/height extent:

```yaml
plots:
    hovmuller:
        max_depth_m: 3.0
```

If the plotted vertical axis is index-based (no coordinate variable to convert
indices to physical depth/height), this setting is ignored with a warning.
ax.legend()
ax.grid(True, alpha=0.3)
fig.savefig("gpp_trend.png", dpi=300, bbox_inches="tight")
```

### Diurnal Cycles (Sub-daily Data)

For h1 or h2 streams with sub-daily output:

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import plot_diurnal

# Load run with sub-daily data
run = Run("./subdaily_output")

# Plot diurnal cycle (hourly mean)
fig = plot_diurnal(run, "GPP")
fig.savefig("gpp_diurnal.png", dpi=300)

# If data is not sub-daily, plot_diurnal will show a message
```

**Manual diurnal analysis:**

```python
# Get variable from high-frequency stream
gpp = run.get("GPP")  # Will use h1 if available and sub-daily

# Check if sub-daily
time_diff = (gpp.time.values[1] - gpp.time.values[0])
is_subdaily = time_diff < np.timedelta64(1, 'D')

if is_subdaily:
    # Compute hourly mean
    diurnal = gpp.groupby("time.hour").mean()
    
    # Plot
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(diurnal.hour, diurnal.values, 'o-', linewidth=2, markersize=6)
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('GPP (gC/m²/s)')
    ax.set_title('Mean Diurnal Cycle')
    ax.set_xticks(range(0, 24, 3))
    ax.grid(True, alpha=0.3)
    fig.savefig("manual_diurnal.png", dpi=300)
else:
    print("Data is not sub-daily; diurnal cycle not meaningful")
```

### Monthly Mean Time Series

Compute and plot monthly means:

```python
from elm_diagnostics import Run
import matplotlib.pyplot as plt

run = Run("tests/fixtures/data")

# Get variable
gpp = run.get("GPP")

# Monthly mean (already monthly in h0, but this works for any frequency)
monthly = gpp.resample(time="1M").mean()

# Plot
fig, ax = plt.subplots(figsize=(12, 6))
monthly.plot(ax=ax, linewidth=2)
ax.set_ylabel(f"GPP ({gpp.attrs.get('units', '')})")
ax.set_title("Monthly Mean GPP")
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig("gpp_monthly.png", dpi=300)
```

## Batch Processing

### Processing Multiple Runs (Bash)

Process multiple ELM simulations in parallel:

```bash
#!/bin/bash
# batch_process_runs.sh - Process multiple runs with elm-diagnostics

# Define simulation directories
runs=(
    "baseline_run"
    "sensitivity_run1"
    "sensitivity_run2"
    "sensitivity_run3"
)

# Output directory
OUTPUT_BASE="./reports"
mkdir -p "$OUTPUT_BASE"

# Process in parallel (adjust -j for number of cores)
for run in "${runs[@]}"; do
    echo "Processing $run..."
    elm-diagnostics report "./simulations/$run" \
        --out "$OUTPUT_BASE/$run" \
        --config year_2001.yaml \
        --quiet &
done

# Wait for all background jobs to complete
wait

echo "All reports complete. Results in $OUTPUT_BASE/"

# Generate summary
echo -e "\n=== Summary ==="
for run in "${runs[@]}"; do
    if [ -f "$OUTPUT_BASE/$run/index.html" ]; then
        echo "✓ $run: $OUTPUT_BASE/$run/index.html"
    else
        echo "✗ $run: FAILED"
    fi
done
```

**Make executable and run:**
```bash
chmod +x batch_process_runs.sh
./batch_process_runs.sh
```

### Processing Multiple Runs (Python)

Python-based batch processing with error handling:

```python
#!/usr/bin/env python3
"""
Batch process multiple ELM runs and generate summary.
"""

from pathlib import Path
from elm_diagnostics import Run, WaterBalance
import pandas as pd
import sys

# Configuration
SIM_BASE_DIR = Path("./simulations")
OUTPUT_DIR = Path("./balance_results")
YEAR = 2001

# Create output directory
OUTPUT_DIR.mkdir(exist_ok=True)

# Find all simulation directories
sim_dirs = sorted(SIM_BASE_DIR.glob("run_*/"))

if not sim_dirs:
    print(f"No simulation directories found in {SIM_BASE_DIR}")
    sys.exit(1)

print(f"Found {len(sim_dirs)} simulations to process")

# Process each simulation
results = []
for sim_dir in sim_dirs:
    print(f"\nProcessing {sim_dir.name}...", end=" ")
    
    try:
        # Load run
        run = Run(sim_dir, name=sim_dir.name)
        
        # Compute water balance
        wb = WaterBalance(run, year=YEAR, frame="water_year")
        
        # Extract metrics
        residual = float(wb.residual().values[-1])
        components = wb.components()
        precip = float(components["RAIN"].values[-1] + components["SNOW"].values[-1])
        et = float(components["QFLX_EVAP_TOT"].values[-1])
        runoff = float(components["QOVER"].values[-1] + components["QDRAI"].values[-1])
        
        # Closure status
        closure = "good" if abs(residual) < 1.0 else "acceptable" if abs(residual) < 10.0 else "poor"
        
        results.append({
            "simulation": sim_dir.name,
            "residual_mm": residual,
            "closure": closure,
            "precipitation_mm": precip,
            "et_mm": et,
            "runoff_mm": runoff,
            "et_ratio": et / precip if precip > 0 else None
        })
        
        # Save balance plots
        fig_cum, fig_dec = wb.plot()
        fig_cum.savefig(OUTPUT_DIR / f"{sim_dir.name}_water_balance.png", dpi=300, bbox_inches="tight")
        
        print("✓")
        run.close()
        
    except Exception as e:
        print(f"✗ Error: {e}")
        results.append({
            "simulation": sim_dir.name,
            "residual_mm": None,
            "closure": "error",
            "precipitation_mm": None,
            "et_mm": None,
            "runoff_mm": None,
            "et_ratio": None
        })

# Create summary DataFrame
df = pd.DataFrame(results)

# Print summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(df.to_string(index=False))

# Save to CSV
summary_file = OUTPUT_DIR / "balance_summary.csv"
df.to_csv(summary_file, index=False)
print(f"\nSummary saved to: {summary_file}")

# Print statistics
print(f"\nClosure Statistics:")
print(f"  Good:       {(df['closure'] == 'good').sum()} runs")
print(f"  Acceptable: {(df['closure'] == 'acceptable').sum()} runs")
print(f"  Poor:       {(df['closure'] == 'poor').sum()} runs")
print(f"  Errors:     {(df['closure'] == 'error').sum()} runs")
```

### Processing Multiple Years

Loop over multiple years for a single run:

```python
from elm_diagnostics import Run, WaterBalance
import pandas as pd

run = Run("tests/fixtures/data")

# Define years to analyze
years = [2001]  # Expand as needed for your data

# Collect results
results = []

for year in years:
    try:
        wb = WaterBalance(run, year=year, frame="water_year")
        components = wb.components()
        
        metrics = {
            "year": year,
            "precipitation": components["RAIN"].values[-1] + components["SNOW"].values[-1],
            "et": components["QFLX_EVAP_TOT"].values[-1],
            "runoff": components["QOVER"].values[-1] + components["QDRAI"].values[-1],
            "storage_change": components["dS"].values[-1],
            "residual": wb.residual().values[-1]
        }
        
        results.append(metrics)
        print(f"WY{year}: residual = {metrics['residual']:.2f} mm")
        
    except Exception as e:
        print(f"WY{year}: Error - {e}")

# Create summary
df = pd.DataFrame(results)
df["et_ratio"] = df["et"] / df["precipitation"]

print("\n" + df.to_string(index=False))
df.to_csv("multi_year_balance.csv", index=False)
```

## Custom Analysis Scripts

### Extracting Key Metrics for Publications

Extract publication-ready metrics:

```python
#!/usr/bin/env python3
"""
Extract key water balance metrics for publication.

Output: Table 1 values for manuscript
"""

from elm_diagnostics import Run, WaterBalance
import numpy as np

# Configuration
DATA_DIR = "tests/fixtures/data"
YEAR = 2001

# Load data
run = Run(DATA_DIR, name="Oak Harbor")
wb = WaterBalance(run, year=YEAR, frame="water_year")

# Get components
components = wb.components()

# Calculate metrics
metrics = {
    "Precipitation": {
        "value": components["RAIN"].values[-1] + components["SNOW"].values[-1],
        "unit": "mm"
    },
    "  Rain": {
        "value": components["RAIN"].values[-1],
        "unit": "mm"
    },
    "  Snow": {
        "value": components["SNOW"].values[-1],
        "unit": "mm"
    },
    "Evapotranspiration": {
        "value": components["QFLX_EVAP_TOT"].values[-1],
        "unit": "mm"
    },
    "  Soil evaporation": {
        "value": components["QSOIL"].values[-1],
        "unit": "mm"
    },
    "  Canopy evaporation": {
        "value": components["QVEGE"].values[-1],
        "unit": "mm"
    },
    "  Transpiration": {
        "value": components["QVEGT"].values[-1],
        "unit": "mm"
    },
    "Runoff": {
        "value": components["QOVER"].values[-1] + components["QDRAI"].values[-1],
        "unit": "mm"
    },
    "  Surface": {
        "value": components["QOVER"].values[-1],
        "unit": "mm"
    },
    "  Subsurface": {
        "value": components["QDRAI"].values[-1],
        "unit": "mm"
    },
    "Storage change": {
        "value": components["dS"].values[-1],
        "unit": "mm"
    },
    "Closure residual": {
        "value": wb.residual().values[-1],
        "unit": "mm"
    }
}

# Add derived metrics
precip = metrics["Precipitation"]["value"]
et = metrics["Evapotranspiration"]["value"]
runoff = metrics["Runoff"]["value"]

metrics["ET/P ratio"] = {"value": et / precip, "unit": "-"}
metrics["Runoff ratio"] = {"value": runoff / precip, "unit": "-"}

# Print formatted table
print("\n" + "="*60)
print(f"Water Year {YEAR} Budget - Oak Harbor")
print("="*60)

for name, data in metrics.items():
    if data["unit"] == "mm":
        print(f"{name:<30s} {data['value']:8.1f} {data['unit']}")
    elif data["unit"] == "-":
        print(f"{name:<30s} {data['value']:8.3f}")
    else:
        print(f"{name:<30s} {data['value']:8.1f} {data['unit']}")

print("="*60)

# Save LaTeX table
with open("table1_water_balance.tex", "w") as f:
    f.write("\\begin{table}\n")
    f.write("\\caption{Water Year 2001 budget components for Oak Harbor site.}\n")
    f.write("\\begin{tabular}{lr}\n")
    f.write("\\hline\n")
    f.write("Component & Value (mm) \\\\\n")
    f.write("\\hline\n")
    
    for name, data in metrics.items():
        if not name.startswith("  ") and data["unit"] == "mm":
            f.write(f"{name} & {data['value']:.1f} \\\\\n")
    
    f.write("\\hline\n")
    f.write("\\end{tabular}\n")
    f.write("\\end{table}\n")

print("\nLaTeX table saved to: table1_water_balance.tex")
```

### Custom Multi-Panel Figures

Create publication-quality multi-panel figures:

```python
from elm_diagnostics import Run
from elm_diagnostics.plots import plot_timeseries, plot_seasonal
import matplotlib.pyplot as plt

run = Run("tests/fixtures/data", name="Oak Harbor")

# Create 2x2 figure
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# Panel A: GPP time series
plot_timeseries(run, "GPP", ax=axes[0, 0])
axes[0, 0].set_title("(a) GPP Time Series")

# Panel B: ET seasonal cycle
plot_seasonal(run, "QFLX_EVAP_TOT", ax=axes[0, 1])
axes[0, 1].set_title("(b) ET Seasonal Cycle")

# Panel C: Sensible heat time series
plot_timeseries(run, "FSH", ax=axes[1, 0])
axes[1, 0].set_title("(c) Sensible Heat Flux")

# Panel D: Precipitation seasonal cycle
plot_seasonal(run, "RAIN", ax=axes[1, 1])
axes[1, 1].set_title("(d) Precipitation Seasonal Cycle")

# Overall title
fig.suptitle("Oak Harbor Site - Water Year 2001", 
             fontsize=14, fontweight="bold", y=0.995)

fig.tight_layout()
fig.savefig("figure_multipanel_oak_harbor.png", dpi=300, bbox_inches="tight")
print("Saved: figure_multipanel_oak_harbor.png")
```

### Integration with Existing Workflows

Export data for use with other analysis tools:

```python
from elm_diagnostics import Run, WaterBalance
import pandas as pd
import xarray as xr

run = Run("tests/fixtures/data")
wb = WaterBalance(run, year=2001)

# Export balance components to NetCDF
wb.to_netcdf("water_balance_WY2001.nc")
print("Saved NetCDF: water_balance_WY2001.nc")

# Export time series to CSV for spreadsheet analysis
components = wb.components()

# Create DataFrame with all components
df = pd.DataFrame({
    "time": components["RAIN"].time.values,
    "precipitation": (components["RAIN"] + components["SNOW"]).values.flatten(),
    "rain": components["RAIN"].values.flatten(),
    "snow": components["SNOW"].values.flatten(),
    "et": components["QFLX_EVAP_TOT"].values.flatten(),
    "et_soil": components["QSOIL"].values.flatten(),
    "et_canopy": components["QVEGE"].values.flatten(),
    "et_transpiration": components["QVEGT"].values.flatten(),
    "runoff": (components["QOVER"] + components["QDRAI"]).values.flatten(),
    "runoff_surface": components["QOVER"].values.flatten(),
    "runoff_subsurface": components["QDRAI"].values.flatten(),
    "storage_change": components["dS"].values.flatten(),
    "residual": wb.residual().values.flatten()
})

df.to_csv("water_balance_timeseries_WY2001.csv", index=False)
print("Saved CSV: water_balance_timeseries_WY2001.csv")

# Export raw variables for custom analysis
gpp = run.get("GPP")
gpp.to_netcdf("gpp_WY2001.nc")
print("Saved GPP: gpp_WY2001.nc")
```

## Troubleshooting Workflows

### Debugging Poor Closure

Systematic approach to diagnosing closure issues:

```python
#!/usr/bin/env python3
"""
Diagnose water balance closure problems.
"""

from elm_diagnostics import Run, WaterBalance
import numpy as np

# Load run
run = Run("./problem_run")
wb = WaterBalance(run, year=2001)

print("="*70)
print("WATER BALANCE CLOSURE DIAGNOSTICS")
print("="*70)

# 1. Check final residual
residual = wb.residual()
final_residual = residual.values[-1]
print(f"\n1. Final residual: {final_residual:.2f} mm")

if abs(final_residual) < 1.0:
    print("   Status: ✓ Excellent closure")
elif abs(final_residual) < 10.0:
    print("   Status: ✓ Acceptable closure")
else:
    print("   Status: ✗ Poor closure - investigate further")

# 2. Examine all components
print("\n2. Component magnitudes:")
components = wb.components()

for name, comp in components.items():
    final_value = float(comp.values[-1])
    print(f"   {name:<20s}: {final_value:10.2f} mm")

# 3. Check for missing variables
print("\n3. Variable availability:")
required = ["RAIN", "SNOW", "QSOIL", "QVEGE", "QVEGT", "QOVER", "QDRAI",
            "SOILLIQ", "SOILICE", "H2OSNO", "H2OCAN", "H2OSFC"]

for var in required:
    if run.has(var):
        print(f"   ✓ {var}")
    else:
        print(f"   ✗ {var} MISSING - this may cause poor closure")

# 4. Verify units
print("\n4. Unit check:")
for var in ["RAIN", "QFLX_EVAP_TOT", "QOVER"]:
    if run.has(var):
        var_data = run.get(var)
        units = var_data.attrs.get("units", "UNKNOWN")
        print(f"   {var}: {units}")
        if units not in ["mm/s", "kg/m2/s", "kg/m^2/s"]:
            print(f"      WARNING: Unexpected units for {var}")

# 5. Check time coverage
print("\n5. Time coverage:")
time = run.streams["h0"]["time"]
print(f"   Start: {time.values[0]}")
print(f"   End:   {time.values[-1]}")
print(f"   Steps: {len(time)}")

# For WY 2001, should have 12 monthly values from Oct 2000 - Sep 2001
# Adjust this check based on your expected coverage

# 6. Check for unrealistic values
print("\n6. Sanity checks:")
precip = components["RAIN"].values[-1] + components["SNOW"].values[-1]
et = components["QFLX_EVAP_TOT"].values[-1]
runoff = components["QOVER"].values[-1] + components["QDRAI"].values[-1]

print(f"   ET/P ratio: {et/precip:.3f}")
if et/precip > 1.5:
    print("      WARNING: ET >> Precip (unusual)")
elif et/precip < 0.1:
    print("      WARNING: ET << Precip (unusual)")
else:
    print("      ✓ ET/P ratio is reasonable")

print(f"   Runoff/P ratio: {runoff/precip:.3f}")
if runoff/precip > 0.9:
    print("      WARNING: Most precip becomes runoff (unusual for vegetated sites)")

# 7. Plot residual evolution
print("\n7. Residual evolution:")
print("   Creating diagnostic plot...")

import matplotlib.pyplot as plt

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

# Cumulative residual
ax1.plot(residual.time, residual.values, linewidth=2, color="red")
ax1.axhline(0, color="black", linestyle="--", linewidth=1)
ax1.set_ylabel("Cumulative Residual (mm)")
ax1.set_title("Water Balance Closure Residual")
ax1.grid(True, alpha=0.3)

# Rate of residual growth
residual_rate = np.diff(residual.values, prepend=0)
ax2.plot(residual.time, residual_rate, linewidth=2, color="darkred")
ax2.axhline(0, color="black", linestyle="--", linewidth=1)
ax2.set_ylabel("Residual Rate (mm/timestep)")
ax2.set_xlabel("Time")
ax2.grid(True, alpha=0.3)

fig.tight_layout()
fig.savefig("closure_diagnostics.png", dpi=300)
print("   Saved: closure_diagnostics.png")

print("\n" + "="*70)
print("DIAGNOSTICS COMPLETE")
print("="*70)
```

### Checking Variable Availability

Quick inventory of available variables:

```python
#!/usr/bin/env python3
"""
Inventory variables in ELM output.
"""

from elm_diagnostics import Run
import pandas as pd

run = Run("tests/fixtures/data")

# List all variables in each stream
print("="*70)
print("VARIABLE INVENTORY")
print("="*70)

for stream_name, ds in run.streams.items():
    print(f"\n{stream_name.upper()} Stream: {len(ds.data_vars)} variables")
    print("-" * 70)
    
    # Check for key balance variables
    balance_vars = {
        "Water": ["RAIN", "SNOW", "QFLX_EVAP_TOT", "QSOIL", "QVEGE", "QVEGT",
                  "QOVER", "QDRAI", "SOILLIQ", "SOILICE", "H2OSNO"],
        "Carbon": ["GPP", "AR", "HR", "ER", "NEE", "TOTECOSYSC", "TOTFIRE"],
        "Energy": ["FSDS", "FSA", "FIRA", "FSH", "EFLX_LH_TOT", "FGR"]
    }
    
    for balance_type, vars_list in balance_vars.items():
        available = [v for v in vars_list if v in ds]
        missing = [v for v in vars_list if v not in ds]
        
        print(f"\n  {balance_type} Balance: {len(available)}/{len(vars_list)} available")
        
        if missing:
            print(f"    Missing: {', '.join(missing)}")
        
        # Show available with units
        if available:
            print(f"    Available:")
            for var in available:
                units = ds[var].attrs.get("units", "N/A")
                long_name = ds[var].attrs.get("long_name", "N/A")
                print(f"      {var:<20s} [{units:<15s}] {long_name[:40]}")

# Export full variable list to CSV
all_vars = []
for stream_name, ds in run.streams.items():
    for var in ds.data_vars:
        all_vars.append({
            "stream": stream_name,
            "variable": var,
            "units": ds[var].attrs.get("units", "N/A"),
            "long_name": ds[var].attrs.get("long_name", "N/A"),
            "dimensions": str(ds[var].dims)
        })

df = pd.DataFrame(all_vars)
df.to_csv("variable_inventory.csv", index=False)
print(f"\n\nFull inventory saved to: variable_inventory.csv")
```

## Configuration Examples

### Custom Configuration File

Create `~/.config/elm-diagnostics/config.yaml` for persistent settings:

```yaml
# Custom elm-diagnostics configuration

# Time handling
time:
  water_year_start_month: 10  # October start for hydrologic year

# Plot appearance
plots:
  style:
    figsize: [10, 6]  # Larger figures
    dpi: 300          # Publication quality
    palette: "tab10"
  
  climatology:
    envelope: "minmax"  # or "p10_p90", "std"

# Balance configuration
balances:
  water:
    frame: "water_year"  # Default to water years
    
  carbon:
    mode: "auto"  # Auto-detect BGC vs SP
  
  energy:
    cumulative: false  # Flux balance only

# Report generation
report:
  thumbnails:
    enabled: true
    size: [400, 300]
    dpi: 72
  
  metadata:
    show_run_info: true
    show_generation_timestamp: true

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

### Using Custom Config in Scripts

Load and use custom configuration:

```python
from elm_diagnostics import Run, WaterBalance
from elm_diagnostics.config.schema import load_config

# Load custom configuration
config = load_config("./my_project_config.yaml")

# Use with Run
run = Run("tests/fixtures/data", config=config)

# Configuration automatically propagates to WaterBalance
wb = WaterBalance(run, year=2001)
# Uses water_year frame from config

# Access config settings
print(f"Water year start month: {config.time.water_year_start_month}")
print(f"Figure DPI: {config.plots.style.dpi}")
```

### Project-Specific Configuration

Create project-specific config for reproducibility:

```yaml
# project_config.yaml - Configuration for Smith et al. (2026) analysis

time:
  water_year_start_month: 10  # October water year

plots:
  style:
    figsize: [8, 6]
    dpi: 300
    palette: "Set2"

balances:
  water:
    frame: "water_year"
    storages: [SOILLIQ, SOILICE, H2OSNO, H2OCAN, H2OSFC]
    inputs: [RAIN, SNOW]
    outputs: [QFLX_EVAP_TOT, QOVER, QDRAI]

report:
  title_template: "Oak Harbor Analysis - {casename}"
  thumbnails:
    enabled: true

variable_groups:
    hydrology:
        enabled: true
        variables: [H2OSOI, QRUNOFF, SOILLIQ]
        plot_types:
            timeseries: true
            hovmuller: false
            seasonal: true
            anomaly: false
            histogram: false
            diurnal: false
```

Use in analysis script:

```python
#!/usr/bin/env python3
"""
Analysis for Smith et al. (2026).
Uses project-specific configuration.
"""

from elm_diagnostics import Run, WaterBalance
from elm_diagnostics.config.schema import load_config

# Load project config
config = load_config("./project_config.yaml")

# Analysis
run = Run("tests/fixtures/data", config=config)
wb = WaterBalance(run, year=2001)

# Results use config settings
fig_cum, fig_dec = wb.plot()
fig_cum.savefig("paper_figure1.png")  # DPI=300 from config
```

## Performance Tips

### For Large Datasets

Use dask for lazy loading with large gridded outputs:

```python
from elm_diagnostics import Run

# Enable dask chunking
run = Run("./large_gridded_output", chunks={"time": 12, "lat": 50, "lon": 50})

# Operations are lazy until compute() or plotting
var = run.get("GPP")  # Returns dask array, not loaded yet

# Compute when needed
result = var.mean().compute()
```

### Parallel Processing with GNU Parallel

Use GNU parallel for batch processing:

```bash
#!/bin/bash
# parallel_batch.sh - Process runs in parallel with GNU parallel

# Find all run directories
find ./simulations -type d -name "run_*" | \
    parallel -j 4 \
        elm-diagnostics report {} \
            --out reports/{/} \
            --config year_2001.yaml \
            --quiet

echo "Parallel processing complete"
```

**Install GNU parallel:**
```bash
# Ubuntu/Debian
sudo apt-get install parallel

# macOS
brew install parallel
```

### Memory Management

For scripts processing many runs:

```python
from elm_diagnostics import Run, WaterBalance
import gc

runs = [...]  # List of run directories

for run_dir in runs:
    # Process run
    run = Run(run_dir)
    wb = WaterBalance(run, year=2001)
    
    # Save results
    wb.to_netcdf(f"{run_dir.name}_balance.nc")
    
    # Explicitly close and clean up
    run.close()
    del run, wb
    gc.collect()
```

## Documentation and Reproducibility

### Publication-Ready Analysis Script

Complete template for reproducible analysis:

```python
#!/usr/bin/env python3
"""
Reproduce water balance analysis for Smith et al. (2026).

Dataset: Oak Harbor single-point simulation
Period: Water Year 2001 (Oct 2000 - Sep 2001)
Contact: [email]
Date: 2026-04-15
"""

from elm_diagnostics import Run, WaterBalance
from elm_diagnostics.config.schema import load_config
import matplotlib.pyplot as plt

# ============================================================================
# Configuration
# ============================================================================

DATA_DIR = "tests/fixtures/data"
OUTPUT_DIR = "./figures"
YEAR = 2001
WATER_YEAR_START = 10  # October

# ============================================================================
# Setup
# ============================================================================

print("="*70)
print("Water Balance Analysis - Oak Harbor WY2001")
print("="*70)

# Load data
print(f"\nLoading data from: {DATA_DIR}")
run = Run(DATA_DIR, name="Oak Harbor WY2001")

# Verify data
print(f"Time range: {run.streams['h0'].time.values[0]} to {run.streams['h0'].time.values[-1]}")
print(f"Spatial dims: {run.streams['h0'].dims}")

# ============================================================================
# Water Balance Analysis
# ============================================================================

print(f"\nComputing water balance for WY{YEAR}...")
wb = WaterBalance(run, year=YEAR, frame="water_year")

# Check closure
residual = wb.residual()
final_residual = float(residual.values[-1])
print(f"Closure residual: {final_residual:.2f} mm")

if abs(final_residual) > 10:
    print("WARNING: Poor closure - review results carefully")

# Get components
components = wb.components()

# ============================================================================
# Generate Figures
# ============================================================================

print("\nGenerating figures...")

# Figure 1: Water balance cumulative
fig_cumulative, fig_decomposition = wb.plot()
fig_cumulative.savefig(f"{OUTPUT_DIR}/figure1_water_balance.png", 
                       dpi=300, bbox_inches="tight")
fig_decomposition.savefig(f"{OUTPUT_DIR}/figure1_water_decomposition.png",
                          dpi=300, bbox_inches="tight")
print(f"  Saved: {OUTPUT_DIR}/figure1_water_balance.png")

# Close plots to free memory
plt.close("all")

# ============================================================================
# Extract Metrics for Table 1
# ============================================================================

print("\nExtracting metrics for Table 1...")

# Calculate annual totals
precip = float(components["RAIN"].values[-1] + components["SNOW"].values[-1])
et = float(components["QFLX_EVAP_TOT"].values[-1])
runoff = float(components["QOVER"].values[-1] + components["QDRAI"].values[-1])
storage_change = float(components["dS"].values[-1])

# Print formatted output
print(f"\nTable 1 - Water Year {YEAR} Budget:")
print(f"  Precipitation:        {precip:7.1f} mm")
print(f"  Evapotranspiration:   {et:7.1f} mm")
print(f"  Runoff:               {runoff:7.1f} mm")
print(f"  Storage change:       {storage_change:7.1f} mm")
print(f"  Closure residual:     {final_residual:7.1f} mm")
print(f"  ET/P ratio:           {et/precip:7.3f}")

# ============================================================================
# Save Data
# ============================================================================

print("\nSaving data...")

# Save balance components
wb.to_netcdf(f"{OUTPUT_DIR}/water_balance_WY{YEAR}.nc")
print(f"  Saved: {OUTPUT_DIR}/water_balance_WY{YEAR}.nc")

# ============================================================================
# Cleanup
# ============================================================================

run.close()

print("\n" + "="*70)
print("Analysis complete")
print("="*70)
```

### README for Analysis Repository

Create a README for your analysis repository:

```markdown
# Oak Harbor Water Balance Analysis

Analysis code and results for Smith et al. (2026).

## Requirements

- Python >= 3.10
- elm-diagnostics >= 0.1.0
- See `requirements.txt` for full list

## Installation

```bash
pip install -r requirements.txt
```

## Data

ELM output data should be placed in `data/`:
- `data/oakharbor/` - Oak Harbor simulation output

## Reproducing Analysis

Run the main analysis script:

```bash
python analyze_water_balance.py
```

This generates:
- `figures/figure1_water_balance.png` - Main water balance figure
- `figures/water_balance_WY2001.nc` - Balance components (NetCDF)

## Configuration

Analysis uses `config.yaml` for reproducibility. Key settings:
- Water year start: October (month 10)
- Target year: 2001
- Figure DPI: 300

## Citation

If you use this code, please cite:

Smith, J. et al. (2026). "Water balance analysis..." Journal, vol(issue), pages.
```

## Summary

This document covered:

✓ **Time series analysis** - Seasonal patterns, anomalies, trends  
✓ **Batch processing** - Shell and Python approaches  
✓ **Custom analysis** - Publication-ready metrics and figures  
✓ **Troubleshooting** - Systematic diagnostics  
✓ **Configuration** - Project-specific settings  
✓ **Performance** - Large datasets and parallel processing  
✓ **Reproducibility** - Publication-ready scripts and documentation

**Next steps:**
- [Getting Started](tutorial-getting-started.md) - Review package basics
- [Balance Checking](tutorial-balance-checking.md) - Detailed balance diagnostics  
- [Experiment Comparison](tutorial-experiment-comparison.md) - Compare runs
