# Comparing Experiments

This tutorial covers comparing base vs. experiment runs using `elm-diagnostics`. Comparison analysis is essential for understanding the impact of model changes, parameter sensitivity, and experimental treatments.

## Introduction

### Use Cases for Comparison

Common comparison scenarios:
- **Parameter sensitivity**: Effect of changing model parameters
- **Code modifications**: Impact of model development changes
- **Experimental treatments**: Irrigation, fertilization, land management
- **Climate scenarios**: Different forcing datasets or future scenarios
- **Configuration changes**: Different timesteps, spatial resolution, etc.

### The Comparison Object

The `Comparison` class pairs two runs for side-by-side analysis:

```python
from elm_diagnostics import Run, Comparison

base = Run("./control", name="Control")
experiment = Run("./treatment", name="Treatment")

comparison = Comparison(base, experiment)
```

All plotting and analysis functions accept either a `Run` or `Comparison` object, automatically adapting their output for comparison visualization.

### Visualization Strategies

Comparison plots use consistent conventions:
- **Base run**: Neutral color (gray or light blue)
- **Experiment run**: Accent color (orange or dark blue)
- **Difference (Δ)**: Separate panel or subplot showing experiment - base

## Basic Comparison Setup

### Loading Two Runs

```python
from elm_diagnostics import Run, Comparison

# Load base run
base = Run("tests/fixtures/data", name="Control")

# Load experiment run
# For demonstration, we'll use different year subsets from same data
# In practice, these would be different simulation outputs
experiment = Run("tests/fixtures/data", name="Experiment")

# Create comparison
comparison = Comparison(base, experiment)

print(f"Comparing: {comparison.base.name} vs {comparison.experiment.name}")
```

**Important**: Both runs should have:
- Same variable names (or compatible variables)
- Overlapping or identical time periods
- Same spatial dimensions (both single-point or both gridded)

### Alignment Options

The `align` parameter controls how time periods are matched:

```python
# Default: only use overlapping time period
comparison = Comparison(base, experiment, align="intersect")

# Alternative: use all time periods (with NaN where missing)
comparison = Comparison(base, experiment, align="union")
```

**intersect** (recommended):
- Uses only time periods present in both runs
- Ensures fair comparison
- Default behavior

**union**:
- Uses all time periods from either run
- Fills missing periods with NaN
- Useful when runs have different lengths

### Checking Time Overlap

```python
# Check time ranges
base_time = base.streams["h0"]["time"]
exp_time = experiment.streams["h0"]["time"]

print(f"Base: {base_time.values[0]} to {base_time.values[-1]}")
print(f"Exp:  {exp_time.values[0]} to {exp_time.values[-1]}")

# For intersect mode, check overlap
import numpy as np
overlap_start = max(base_time.values[0], exp_time.values[0])
overlap_end = min(base_time.values[-1], exp_time.values[-1])
print(f"Overlap: {overlap_start} to {overlap_end}")
```

## Comparing Individual Variables

### Using Plot Functions

All plot functions in `elm_diagnostics.plots` accept `Comparison` objects:

```python
from elm_diagnostics import Run, Comparison
from elm_diagnostics.plots import (
    plot_timeseries, 
    plot_seasonal, 
    plot_anomaly,
    plot_histogram
)

# Setup comparison (using Oak Harbor data as example)
base = Run("tests/fixtures/data", name="Control")
experiment = Run("tests/fixtures/data", name="Treatment")
comparison = Comparison(base, experiment)

# Time series comparison
fig = plot_timeseries(comparison, "GPP")
fig.savefig("gpp_timeseries_comparison.png", dpi=300)

# Seasonal cycle comparison
fig = plot_seasonal(comparison, "QFLX_EVAP_TOT")
fig.savefig("et_seasonal_comparison.png", dpi=300)

# Annual anomaly comparison
fig = plot_anomaly(comparison, "FSH")
fig.savefig("fsh_anomaly_comparison.png", dpi=300)

# Distribution comparison
fig = plot_histogram(comparison, "RAIN")
fig.savefig("rain_histogram_comparison.png", dpi=300)
```

**Note**: For demonstration purposes using the same dataset, these would show identical results. In practice with different simulation outputs, you would see clear differences.

### Interpretation

**Time series plots:**
- Two overlaid lines (base and experiment)
- Legend distinguishes runs
- Look for systematic offsets or trends

**Seasonal plots:**
- Monthly means with spread (min/max or percentiles)
- Compare seasonality patterns
- Identify months with largest differences

**Anomaly plots:**
- Annual deviations from climatology
- Bar charts with positive/negative indicators
- Compare inter-annual variability

**Histogram plots:**
- Overlaid distributions
- Compare mean, spread, and shape
- Identify shifts in distribution

### Quantifying Differences

Manually compute differences for any variable:

```python
# Get the same variable from both runs
gpp_base = base.get("GPP")
gpp_exp = experiment.get("GPP")

# Compute difference (ensure aligned time)
gpp_diff = gpp_exp - gpp_base

# Statistics
mean_diff = float(gpp_diff.mean())
max_diff = float(gpp_diff.max())
min_diff = float(gpp_diff.min())

print(f"Mean difference: {mean_diff:.2f} {gpp_base.attrs['units']}")
print(f"Max difference:  {max_diff:.2f} {gpp_base.attrs['units']}")
print(f"Min difference:  {min_diff:.2f} {gpp_base.attrs['units']}")

# Percent change
mean_base = float(gpp_base.mean())
pct_change = (mean_diff / mean_base) * 100
print(f"Percent change: {pct_change:.1f}%")
```

### Example: Multi-Variable Comparison

Compare several related variables:

```python
import matplotlib.pyplot as plt
from elm_diagnostics.plots import plot_seasonal

variables = ["GPP", "QFLX_EVAP_TOT", "FSH", "EFLX_LH_TOT"]

fig, axes = plt.subplots(2, 2, figsize=(12, 10))
axes = axes.flatten()

for i, var in enumerate(variables):
    plot_seasonal(comparison, var, ax=axes[i])
    axes[i].set_title(f"{var} Seasonal Cycle")

fig.suptitle("Seasonal Comparison: Control vs Treatment", 
             fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig("multi_variable_seasonal_comparison.png", dpi=300)
```

## Comparing Balances

### Water Balance Comparison

Compare water balance closure between runs:

```python
from elm_diagnostics import Run, WaterBalance

# Load runs
base = Run("tests/fixtures/data", name="Control")
experiment = Run("tests/fixtures/data", name="Irrigation")

# Compute water balance for both
wb_base = WaterBalance(base, year=2001, frame="water_year")
wb_exp = WaterBalance(experiment, year=2001, frame="water_year")

# Compare closure
res_base = wb_base.residual()
res_exp = wb_exp.residual()

print(f"Control residual:   {res_base.values[-1]:.2f} mm")
print(f"Treatment residual: {res_exp.values[-1]:.2f} mm")

# Generate plots for each
fig_base_1, fig_base_2 = wb_base.plot()
fig_exp_1, fig_exp_2 = wb_exp.plot()

# Save comparison
fig_base_1.savefig("water_balance_control.png", dpi=300)
fig_exp_1.savefig("water_balance_treatment.png", dpi=300)
```

### Comparing Components

Compare individual water balance components:

```python
# Get components from both
comps_base = wb_base.components()
comps_exp = wb_exp.components()

# Compare annual totals
print("\n=== Annual Water Balance Comparison ===")
print(f"{'Component':<20s} {'Control':>10s} {'Treatment':>10s} {'Difference':>10s}")
print("-" * 55)

for key in ["RAIN", "SNOW", "QFLX_EVAP_TOT", "QOVER", "QDRAI"]:
    if key in comps_base and key in comps_exp:
        base_val = comps_base[key].values[-1]
        exp_val = comps_exp[key].values[-1]
        diff = exp_val - base_val
        print(f"{key:<20s} {base_val:10.1f} {exp_val:10.1f} {diff:10.1f} mm")

# Calculate key metrics
precip_base = comps_base["RAIN"].values[-1] + comps_base["SNOW"].values[-1]
precip_exp = comps_exp["RAIN"].values[-1] + comps_exp["SNOW"].values[-1]
et_base = comps_base["QFLX_EVAP_TOT"].values[-1]
et_exp = comps_exp["QFLX_EVAP_TOT"].values[-1]

print(f"\n{'ET/P ratio':<20s} {et_base/precip_base:10.3f} {et_exp/precip_exp:10.3f} {(et_exp/precip_exp)-(et_base/precip_base):10.3f}")
```

### Difference Time Series

Plot the difference between balance components over time:

```python
import matplotlib.pyplot as plt

# Get ET from both runs
et_base = comps_base["QFLX_EVAP_TOT"]
et_exp = comps_exp["QFLX_EVAP_TOT"]

# Compute difference
et_diff = et_exp - et_base

# Plot
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# Panel 1: Both time series
ax1.plot(et_base.time, et_base.values, label="Control", color="gray", linewidth=2)
ax1.plot(et_exp.time, et_exp.values, label="Treatment", color="coral", linewidth=2)
ax1.set_ylabel("Cumulative ET (mm)")
ax1.legend()
ax1.grid(True, alpha=0.3)
ax1.set_title("Cumulative Evapotranspiration")

# Panel 2: Difference
ax2.plot(et_diff.time, et_diff.values, color="steelblue", linewidth=2)
ax2.axhline(0, color="black", linestyle="--", linewidth=1)
ax2.set_ylabel("Difference (mm)")
ax2.set_xlabel("Time")
ax2.grid(True, alpha=0.3)
ax2.set_title("Treatment - Control")

fig.tight_layout()
fig.savefig("et_comparison_with_diff.png", dpi=300)
```

### Carbon and Energy Balance Comparison

Similar workflow for other balances:

```python
from elm_diagnostics import CarbonBalance, EnergyBalance

# Carbon balance comparison
cb_base = CarbonBalance(base, year=2001)
cb_exp = CarbonBalance(experiment, year=2001)

print(f"Carbon residual (control):   {cb_base.residual().values[-1]:.2f} gC/m²")
print(f"Carbon residual (treatment): {cb_exp.residual().values[-1]:.2f} gC/m²")

# Compare GPP
gpp_base = cb_base.components()["GPP"].values[-1]
gpp_exp = cb_exp.components()["GPP"].values[-1]
print(f"GPP difference: {gpp_exp - gpp_base:.1f} gC/m² ({((gpp_exp/gpp_base)-1)*100:.1f}%)")

# Energy balance comparison
eb_base = EnergyBalance(base, year=2001)
eb_exp = EnergyBalance(experiment, year=2001)

# Compare net radiation
comps_eb_base = eb_base.components()
comps_eb_exp = eb_exp.components()

rnet_base = (comps_eb_base["FSA"] + comps_eb_base["FIRA"]).mean()
rnet_exp = (comps_eb_exp["FSA"] + comps_eb_exp["FIRA"]).mean()
print(f"Mean net radiation difference: {rnet_exp - rnet_base:.2f} W/m²")
```

## Generating Comparison Reports

### HTML Report with Comparison

Generate a comprehensive HTML report comparing two runs:

```python
from elm_diagnostics import Run, Comparison, Report

# Load runs
base = Run("tests/fixtures/data", name="Control")
experiment = Run("tests/fixtures/data", name="Treatment")

# Create comparison
comparison = Comparison(base, experiment)

# Generate report
report = Report(comparison)
report.build("./comparison_report/")

print("Comparison report generated at: ./comparison_report/index.html")
```

The report includes:
- Side-by-side plots for all variables
- Difference/delta plots where meaningful
- Balance comparisons with closure metrics
- Statistics tables for both runs
- Interactive thumbnails and navigation

### CLI Version

```bash
# Generate comparison report from command line
elm-diagnostics report tests/fixtures/data \
    --compare tests/fixtures/data \
    --out ./comparison_report/

# With specific year
elm-diagnostics report ./experiment \
    --compare ./control \
    --config year_2001.yaml \
    --out ./comparison_WY2001/

# With custom configuration
elm-diagnostics report ./experiment \
    --compare ./control \
    --config custom_config.yaml \
    --out ./comparison/
```

### Report Customization

Customize comparison report settings in configuration file:

```yaml
# ~/.config/elm-diagnostics/config.yaml

report:
  comparison:
    show_delta_plots: true        # Include difference plots
    side_by_side_layout: true     # Side-by-side vs stacked
  
  balance_sections:
    show_statistics_table: true
    show_residual_percentage: true

variable_groups:
    soil_state:
        enabled: true
        variables: [TSOI, SOILLIQ, SOILICE]
        plot_types:
            timeseries: true
            hovmuller: true
            seasonal: true
            anomaly: true
            histogram: false
            diurnal: false
```

## Oak Harbor Comparison Example

Since the Oak Harbor test dataset is a single simulation, we can demonstrate comparison workflow by using different time periods:

### Simulated Experiment Setup

```python
from elm_diagnostics import Run, WaterBalance, Comparison
import xarray as xr

# Load full dataset
run_full = Run("tests/fixtures/data", name="Full Period")

# Create "base" using first water year
# Note: This is for demonstration - normally you'd have separate simulations
base = Run("tests/fixtures/data", name="Period 1")
experiment = Run("tests/fixtures/data", name="Period 2")

# Compare water balance
wb_base = WaterBalance(base, year=2001, frame="water_year")
wb_exp = WaterBalance(experiment, year=2001, frame="water_year")

# Generate plots
fig_base_cum, fig_base_dec = wb_base.plot()
fig_exp_cum, fig_exp_dec = wb_exp.plot()

# Save
fig_base_cum.savefig("demo_base_water_balance.png", dpi=300)
fig_exp_cum.savefig("demo_exp_water_balance.png", dpi=300)
```

### Expected Patterns

In a real experiment comparison (e.g., irrigation vs no irrigation), you would expect:

**Water balance changes:**
- **Increased ET**: Irrigation provides more water for evapotranspiration
- **Decreased runoff**: More water consumed by ET, less reaches streams
- **Increased storage**: Soil moisture levels higher
- **Similar closure**: Both should close well if properly simulated

**Carbon balance changes:**
- **Increased GPP**: More water → less water stress → higher photosynthesis
- **Increased respiration**: Higher plant activity, warmer/wetter soil
- **Net effect variable**: Depends on which increases more

**Energy balance changes:**
- **Increased LE**: More evaporation uses energy
- **Decreased H**: Less energy available for sensible heat
- **Cooler surface**: Evaporative cooling effect

## Quantifying Differences

### Computing Statistics

Extract key comparison metrics for publication:

```python
from elm_diagnostics import Run, WaterBalance
import numpy as np

base = Run("tests/fixtures/data", name="Control")
experiment = Run("tests/fixtures/data", name="Treatment")

wb_base = WaterBalance(base, year=2001)
wb_exp = WaterBalance(experiment, year=2001)

# Get components
comps_base = wb_base.components()
comps_exp = wb_exp.components()

# Create comparison dictionary
comparison_metrics = {}

for key in comps_base.keys():
    if key in comps_exp:
        base_val = float(comps_base[key].values[-1])
        exp_val = float(comps_exp[key].values[-1])
        diff = exp_val - base_val
        
        if base_val != 0:
            pct_change = (diff / base_val) * 100
        else:
            pct_change = np.nan
        
        comparison_metrics[key] = {
            "control": base_val,
            "treatment": exp_val,
            "difference": diff,
            "percent_change": pct_change
        }

# Print table
print("\n=== Water Balance Comparison Metrics ===")
print(f"{'Component':<20s} {'Control':>10s} {'Treatment':>10s} {'Diff':>10s} {'% Change':>10s}")
print("-" * 65)

for key, metrics in comparison_metrics.items():
    print(f"{key:<20s} "
          f"{metrics['control']:10.1f} "
          f"{metrics['treatment']:10.1f} "
          f"{metrics['difference']:10.1f} "
          f"{metrics['percent_change']:10.1f}%")
```

### Example Analysis Script

Complete script for publication-ready comparison:

```python
#!/usr/bin/env python3
"""
Quantitative comparison of irrigation experiment.

Compares water and carbon balance between control and irrigation treatment
for Water Year 2001.
"""

from elm_diagnostics import Run, WaterBalance, CarbonBalance
import numpy as np
import pandas as pd

# Setup
BASE_DIR = "tests/fixtures/data"
EXP_DIR = "tests/fixtures/data"
YEAR = 2001

# Load runs
control = Run(BASE_DIR, name="Control")
treatment = Run(EXP_DIR, name="Irrigation")

# Water balance
print("\n=== WATER BALANCE ===")
wb_ctrl = WaterBalance(control, year=YEAR, frame="water_year")
wb_trt = WaterBalance(treatment, year=YEAR, frame="water_year")

# Check closure
print(f"Control residual:   {wb_ctrl.residual().values[-1]:6.2f} mm")
print(f"Treatment residual: {wb_trt.residual().values[-1]:6.2f} mm")

# Extract annual totals
comps_ctrl = wb_ctrl.components()
comps_trt = wb_trt.components()

# Key metrics
metrics = {
    "Precipitation": {
        "ctrl": comps_ctrl["RAIN"].values[-1] + comps_ctrl["SNOW"].values[-1],
        "trt": comps_trt["RAIN"].values[-1] + comps_trt["SNOW"].values[-1]
    },
    "ET": {
        "ctrl": comps_ctrl["QFLX_EVAP_TOT"].values[-1],
        "trt": comps_trt["QFLX_EVAP_TOT"].values[-1]
    },
    "Runoff": {
        "ctrl": comps_ctrl["QOVER"].values[-1] + comps_ctrl["QDRAI"].values[-1],
        "trt": comps_trt["QOVER"].values[-1] + comps_trt["QDRAI"].values[-1]
    }
}

# Print table
print(f"\n{'Metric':<15s} {'Control':>10s} {'Treatment':>10s} {'Difference':>12s} {'% Change':>10s}")
print("-" * 60)

for name, vals in metrics.items():
    diff = vals["trt"] - vals["ctrl"]
    pct = (diff / vals["ctrl"]) * 100 if vals["ctrl"] != 0 else np.nan
    print(f"{name:<15s} {vals['ctrl']:10.1f} {vals['trt']:10.1f} {diff:12.1f} {pct:10.1f}%")

# Carbon balance
print("\n=== CARBON BALANCE ===")
cb_ctrl = CarbonBalance(control, year=YEAR)
cb_trt = CarbonBalance(treatment, year=YEAR)

comps_c_ctrl = cb_ctrl.components()
comps_c_trt = cb_trt.components()

gpp_ctrl = comps_c_ctrl["GPP"].values[-1]
gpp_trt = comps_c_trt["GPP"].values[-1]
gpp_diff = gpp_trt - gpp_ctrl

print(f"GPP (control):   {gpp_ctrl:.0f} gC/m²")
print(f"GPP (treatment): {gpp_trt:.0f} gC/m²")
print(f"GPP difference:  {gpp_diff:.0f} gC/m² ({(gpp_diff/gpp_ctrl)*100:.1f}%)")

# Save results to CSV
results_df = pd.DataFrame([
    {"metric": k, "control": v["ctrl"], "treatment": v["trt"]} 
    for k, v in metrics.items()
])
results_df["difference"] = results_df["treatment"] - results_df["control"]
results_df["percent_change"] = (results_df["difference"] / results_df["control"]) * 100

results_df.to_csv("comparison_metrics_WY2001.csv", index=False)
print("\nResults saved to: comparison_metrics_WY2001.csv")

# Clean up
control.close()
treatment.close()
```

### Statistical Significance

For rigorous comparison, test statistical significance:

```python
from scipy import stats
import numpy as np

# Get time series for both runs
gpp_base = base.get("GPP")
gpp_exp = experiment.get("GPP")

# Ensure aligned time
gpp_base_values = gpp_base.values.flatten()
gpp_exp_values = gpp_exp.values.flatten()

# Paired t-test (if same time points)
t_stat, p_value = stats.ttest_rel(gpp_exp_values, gpp_base_values)

print(f"Paired t-test:")
print(f"  t-statistic: {t_stat:.3f}")
print(f"  p-value: {p_value:.4f}")

if p_value < 0.05:
    print("  Result: Significant difference (p < 0.05)")
else:
    print("  Result: No significant difference (p >= 0.05)")

# Effect size (Cohen's d)
mean_diff = np.mean(gpp_exp_values - gpp_base_values)
std_diff = np.std(gpp_exp_values - gpp_base_values)
cohens_d = mean_diff / std_diff

print(f"\nEffect size (Cohen's d): {cohens_d:.3f}")
```

## Advanced Topics

### Multi-Variable Comparison Matrix

Compare many variables systematically:

```python
from elm_diagnostics import Run
import pandas as pd

base = Run("tests/fixtures/data", name="Control")
experiment = Run("tests/fixtures/data", name="Treatment")

# Define variables to compare
variables = [
    "GPP", "ER", "NEE",
    "QFLX_EVAP_TOT", "QOVER", "QDRAI",
    "FSH", "EFLX_LH_TOT",
    "RAIN", "SNOW"
]

# Compute statistics for each
results = []
for var in variables:
    if base.has(var) and experiment.has(var):
        var_base = base.get(var)
        var_exp = experiment.get(var)
        
        mean_base = float(var_base.mean())
        mean_exp = float(var_exp.mean())
        diff = mean_exp - mean_base
        pct_change = (diff / mean_base * 100) if mean_base != 0 else np.nan
        
        results.append({
            "Variable": var,
            "Control_Mean": mean_base,
            "Treatment_Mean": mean_exp,
            "Difference": diff,
            "Percent_Change": pct_change
        })

# Create DataFrame
df = pd.DataFrame(results)
df = df.sort_values("Percent_Change", key=abs, ascending=False)

print(df.to_string(index=False))
df.to_csv("multi_variable_comparison.csv", index=False)
```

### Batch Comparison Plots

Generate comparison plots for many variables automatically:

```bash
#!/bin/bash
# generate_comparison_plots.sh

BASE_DIR="./control"
EXP_DIR="./treatment"
OUTPUT_DIR="./comparison_plots"

mkdir -p "$OUTPUT_DIR"

variables=(
    "GPP" "ER" "NEE" "QFLX_EVAP_TOT" 
    "FSH" "EFLX_LH_TOT" "RAIN" "QOVER"
)

for var in "${variables[@]}"; do
    echo "Plotting $var..."
    python -c "
from elm_diagnostics import Run, Comparison
from elm_diagnostics.plots import plot_seasonal
comparison = Comparison(
    Run('$BASE_DIR', name='Control'),
    Run('$EXP_DIR', name='Treatment')
)
fig = plot_seasonal(comparison, '$var')
fig.savefig('$OUTPUT_DIR/${var}_seasonal_comparison.png', dpi=300, bbox_inches='tight')
"
done

echo "All plots saved to $OUTPUT_DIR/"
```

## Best Practices

### 1. Check Both Runs Close Individually First

Before comparing, verify both runs have good closure:

```python
# Check base
wb_base = WaterBalance(base, year=2001)
res_base = wb_base.residual().values[-1]
assert abs(res_base) < 10, f"Base closure poor: {res_base:.2f} mm"

# Check experiment
wb_exp = WaterBalance(experiment, year=2001)
res_exp = wb_exp.residual().values[-1]
assert abs(res_exp) < 10, f"Experiment closure poor: {res_exp:.2f} mm"

# Now proceed with comparison
```

### 2. Document Baseline Period Carefully

Be explicit about time periods:

```python
# Good: Clear specification
base = Run("./control_1990-2000", name="Control (1990-2000)")
exp = Run("./treatment_1990-2000", name="Treatment (1990-2000)")

# Include in reports
print(f"Baseline: {base.name}")
print(f"Experiment: {exp.name}")
print(f"Analysis period: WY 2001")
```

### 3. Consider Natural Variability

Inter-annual variability can mask or mimic treatment effects:

```python
# Multi-year comparison to account for variability
years = range(2000, 2005)
gpp_diffs = []

for year in years:
    gpp_base = base.get("GPP").sel(time=str(year)).mean()
    gpp_exp = experiment.get("GPP").sel(time=str(year)).mean()
    gpp_diffs.append(float(gpp_exp - gpp_base))

print(f"Mean GPP difference: {np.mean(gpp_diffs):.1f} ± {np.std(gpp_diffs):.1f} gC/m²/day")
```

### 4. Statistical Testing for Significance

Use appropriate statistical tests:

```python
from scipy import stats

# For paired samples (same time points)
t_stat, p_val = stats.ttest_rel(exp_data, base_data)

# For independent samples
t_stat, p_val = stats.ttest_ind(exp_data, base_data)

# Report results
print(f"Statistical test: p = {p_val:.4f}")
if p_val < 0.05:
    print("Difference is statistically significant")
```

## Summary

**Quick reference:**

```python
# Basic comparison
from elm_diagnostics import Run, Comparison

base = Run("./control", name="Control")
experiment = Run("./treatment", name="Treatment")
comparison = Comparison(base, experiment)

# Plot comparisons
from elm_diagnostics.plots import plot_seasonal
fig = plot_seasonal(comparison, "GPP")

# Compare balances
from elm_diagnostics import WaterBalance
wb_base = WaterBalance(base, year=2001)
wb_exp = WaterBalance(experiment, year=2001)

# Generate report
from elm_diagnostics import Report
report = Report(comparison)
report.build("./comparison_report/")
```

**Command-line:**
```bash
elm-diagnostics report ./experiment --compare ./control --out ./comparison/
```

**Next steps:**
- [Workflow Examples](workflow-examples.md) - Practical automation patterns
- [Getting Started](tutorial-getting-started.md) - Review basics
- [Balance Checking](tutorial-balance-checking.md) - Detailed balance diagnostics
