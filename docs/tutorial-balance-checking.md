# Budget Balance Checking

This tutorial covers water, carbon, and energy balance diagnostics using `elm-diagnostics`. Balance closure is essential for verifying the physical consistency of ELM simulations and identifying potential issues in model configuration or output.

## Introduction

### Why Balance Closure Matters

Budget balance closure ensures that:
- Mass and energy are conserved in the simulation
- Output variables are internally consistent
- No numerical issues corrupt the solution
- Results are physically meaningful

Poor closure can indicate:
- Missing output variables
- Incorrect model timestep or output frequency
- Bugs in the model code
- Numerical instability

### Interpreting Residuals

The **residual** is the difference between computed change in storage and the balance of inputs minus outputs:

```
Residual = ΔS - (Inputs - Outputs)
```

For a perfectly closed budget, residual = 0. In practice, small non-zero residuals occur due to:
- Rounding errors in floating-point arithmetic
- Temporal averaging effects
- Unit conversions

### Typical Closure Tolerances

**Water balance:**
- **Good**: |residual| < 1 mm/year
- **Acceptable**: |residual| < 10 mm/year
- **Poor**: |residual| > 10 mm/year (investigate)

**Carbon balance:**
- **Good**: |residual| < 1 gC/m²/year
- **Acceptable**: |residual| < 10 gC/m²/year
- **Poor**: |residual| > 10 gC/m²/year (investigate)

**Energy balance:**
- Typically evaluated as instantaneous flux balance rather than cumulative
- **Good**: Mean |residual| < 5 W/m²

## Water Balance

### Quick Water Balance Check

The fastest way to check water balance closure:

**Python (3 lines):**
```python
from elm_diagnostics import Run, WaterBalance

run = Run("tests/fixtures/data")
wb = WaterBalance(run, year=2001)
print(f"Residual: {wb.residual().values[-1]:.2f} mm")
```

**Command-line (1 line):**
```bash
elm-diagnostics balance water tests/fixtures/data --config year_2001.yaml
```

This will display the cumulative water balance plots and report the final residual.

### Detailed Water Balance Analysis

#### Creating a WaterBalance Object

```python
from elm_diagnostics import Run, WaterBalance

# Load the Oak Harbor test data
run = Run("tests/fixtures/data", name="Oak Harbor")

# Create water balance for Water Year 2001 (Oct 2000 - Sep 2001)
wb = WaterBalance(run, year=2001, frame="water_year")
```

**Parameters:**
- `run`: Run object containing the simulation data
- `year`: Year to analyze (water year or calendar year depending on frame)
- `frame`: Either `"water_year"` (default) or `"calendar"`
- `by`: Optional faceting by column, pft, or landunit (for sub-gridcell output)

#### Understanding Components

The water balance equation:

```
ΔS = P - ET - Q
```

Where:
- **ΔS**: Change in storage (soil water + snow + canopy + surface)
- **P**: Precipitation (rain + snow)
- **ET**: Evapotranspiration (soil evap + canopy evap + transpiration)
- **Q**: Runoff (surface + subsurface drainage)

Get all components:

```python
components = wb.components()
print(components.keys())
```

**Output:**
```
dict_keys(['RAIN', 'SNOW', 'QFLX_EVAP_TOT', 'QSOIL', 'QVEGE', 'QVEGT', 
           'QOVER', 'QDRAI', 'QDRAI_PERCH', 'QSNOMELT', 'dS'])
```

**Storage components** (automatically aggregated):
- `SOILLIQ`: Soil liquid water (summed over 15 levels)
- `SOILICE`: Soil ice (summed over 15 levels)
- `H2OSNO`: Snow water equivalent
- `H2OCAN`: Canopy water storage
- `H2OSFC`: Surface water storage

**Input components:**
- `RAIN`: Liquid precipitation
- `SNOW`: Solid precipitation

**Output components:**
- `QFLX_EVAP_TOT`: Total ET (or sum of QSOIL + QVEGE + QVEGT)
- `QOVER`: Surface runoff
- `QDRAI`: Subsurface drainage
- `QDRAI_PERCH`: Perched water table drainage
- `QSNOMELT`: Snow melt (internal flux, tracked separately)

**Derived components:**
- `dS`: Change in total storage (computed from storage variables)

#### Computing Cumulative Fluxes

All components are returned as cumulative values (integrated over time):

```python
# Get cumulative precipitation
precip_cumulative = components["RAIN"] + components["SNOW"]
print(f"Annual precipitation: {precip_cumulative.values[-1]:.1f} mm")

# Get cumulative ET
et_cumulative = components["QFLX_EVAP_TOT"]
print(f"Annual ET: {et_cumulative.values[-1]:.1f} mm")

# Runoff
runoff_cumulative = components["QOVER"] + components["QDRAI"]
print(f"Annual runoff: {runoff_cumulative.values[-1]:.1f} mm")

# Storage change
storage_change = components["dS"]
print(f"Storage change: {storage_change.values[-1]:.1f} mm")
```

Fluxes in ELM output are typically in `mm/s` or `kg/m²/s`. The package automatically integrates these to cumulative values in `mm` using actual time intervals from `time_bounds`.

#### Checking Closure Residuals

```python
# Compute the residual
residual = wb.residual()

# Check final residual (end of year)
final_residual = float(residual.values[-1])
print(f"Water balance residual: {final_residual:.3f} mm")

if abs(final_residual) < 1.0:
    print("✓ Excellent closure")
elif abs(final_residual) < 10.0:
    print("✓ Acceptable closure")
else:
    print("✗ Poor closure - investigate")
```

The residual is computed as:
```
residual = (RAIN + SNOW) - QFLX_EVAP_TOT - QOVER - QDRAI - dS
```

#### Generating Diagnostic Plots

```python
# Generate two-panel figure
fig_cumulative, fig_decomposition = wb.plot()

# Save figures
fig_cumulative.savefig("water_balance_cumulative.png", dpi=300, bbox_inches="tight")
fig_decomposition.savefig("water_balance_decomposition.png", dpi=300, bbox_inches="tight")
```

**Panel 1 (Cumulative):** Shows cumulative inputs, outputs, storage change, and residual over the water year.

**Panel 2 (Decomposition):** Shows ET broken into components (QSOIL, QVEGE, QVEGT) and runoff components.

#### Saving Results to NetCDF

```python
# Save all balance components to NetCDF for further analysis
wb.to_netcdf("water_balance_2001.nc")

# Can be reopened with xarray
import xarray as xr
ds = xr.open_dataset("water_balance_2001.nc")
print(ds)
```

The saved file contains all cumulative components plus the residual as xarray DataArrays with proper metadata.

### Water Year vs Calendar Year

#### Water Year Analysis (Default)

Water year is the standard frame for hydrological analysis, starting in October:

```python
# Water Year 2001 = Oct 1, 2000 through Sep 30, 2001
wb = WaterBalance(run, year=2001, frame="water_year")
```

The start month is configurable (default is October, month 10):

```python
from elm_diagnostics.config.schema import load_config

config = load_config()  # Load default or user config
config.time.water_year_start_month = 10  # October
```

Or in `~/.config/elm-diagnostics/config.yaml`:
```yaml
time:
  water_year_start_month: 10
```

#### Calendar Year Analysis

For calendar year (January through December):

```python
# Calendar Year 2001 = Jan 1, 2001 through Dec 31, 2001
wb = WaterBalance(run, year=2001, frame="calendar")
```

#### Multi-Year Analysis

Analyze multiple years in a loop:

```python
years = [2001, 2002, 2003]
residuals = {}

for year in years:
    wb = WaterBalance(run, year=year, frame="water_year")
    residual = float(wb.residual().values[-1])
    residuals[year] = residual
    print(f"WY{year}: {residual:.2f} mm")

# Check consistency across years
import numpy as np
mean_residual = np.mean(list(residuals.values()))
std_residual = np.std(list(residuals.values()))
print(f"\nMulti-year closure: {mean_residual:.2f} ± {std_residual:.2f} mm")
```

### Interpreting Results

#### Oak Harbor Example

Using the test data:

```python
from elm_diagnostics import Run, WaterBalance

run = Run("tests/fixtures/data", name="Oak Harbor")
wb = WaterBalance(run, year=2001, frame="water_year")

# Get all metrics
components = wb.components()
residual = wb.residual()

# Print summary
print("\n=== Water Year 2001 Budget ===")
print(f"Precipitation:  {components['RAIN'].values[-1] + components['SNOW'].values[-1]:7.1f} mm")
print(f"ET:             {components['QFLX_EVAP_TOT'].values[-1]:7.1f} mm")
print(f"Runoff:         {components['QOVER'].values[-1] + components['QDRAI'].values[-1]:7.1f} mm")
print(f"Storage change: {components['dS'].values[-1]:7.1f} mm")
print(f"Residual:       {residual.values[-1]:7.1f} mm")

# Calculate ET ratio
et_ratio = components['QFLX_EVAP_TOT'].values[-1] / (components['RAIN'].values[-1] + components['SNOW'].values[-1])
print(f"\nET/P ratio:     {et_ratio:7.3f}")
```

**Expected patterns:**
- Precipitation > 0 (inputs)
- ET > 0 (typically 50-80% of precipitation in temperate climates)
- Runoff > 0 (remaining precipitation not evapotranspired)
- Storage change ~ 0 for full water year (seasonal storage changes cancel out)
- Small residual (< 1 mm for good closure)

#### Common Causes of Poor Closure

**Large positive residual** (inputs > outputs + ΔS):
- Missing output flux (e.g., QDRAI_PERCH not included)
- Incorrect ET calculation (missing components)
- Storage terms not properly aggregated (forgot to sum over levgrnd)

**Large negative residual** (inputs < outputs + ΔS):
- Missing input flux (e.g., irrigation, dew)
- Double-counting output fluxes
- Initial/final storage computed incorrectly

**Growing residual over time**:
- Consistent bias in flux or storage calculation
- Time integration error
- Model drift (rare, but possible)

### Troubleshooting Strategies

#### Strategy 1: Check Variable Availability

```python
# Verify all required variables are present
required_vars = ["RAIN", "SNOW", "QSOIL", "QVEGE", "QVEGT", 
                 "QOVER", "QDRAI", "SOILLIQ", "SOILICE", "H2OSNO"]

for var in required_vars:
    if run.has(var):
        print(f"✓ {var}")
    else:
        print(f"✗ {var} MISSING")
```

#### Strategy 2: Examine Individual Components

```python
components = wb.components()

print("\n=== Component Magnitudes ===")
for name, comp in components.items():
    final = float(comp.values[-1])
    print(f"{name:20s}: {final:8.2f} mm")
```

Look for:
- Unrealistic values (e.g., ET > precipitation by large margin)
- Missing components (zero or NaN)
- Unexpected signs (negative precipitation, etc.)

#### Strategy 3: Check Units

```python
# Verify units of raw variables
rain = run.get("RAIN")
print(f"RAIN units: {rain.attrs.get('units', 'UNKNOWN')}")

et = run.get("QFLX_EVAP_TOT")
print(f"ET units: {et.attrs.get('units', 'UNKNOWN')}")
```

Should be `mm/s` or `kg/m²/s` for fluxes. The package handles conversion automatically, but it's good to verify.

#### Strategy 4: Check Time Coverage

```python
# Verify time range covers full year
time = run.streams["h0"]["time"]
print(f"Time range: {time.values[0]} to {time.values[-1]}")
print(f"Number of timesteps: {len(time)}")

# For water year 2001, should have Oct 2000 through Sep 2001
# That's 12 monthly values
```

## Carbon Balance

### Auto-detection: BGC vs SP Mode

ELM can run in two carbon modes:
- **BGC**: Biogeochemistry active (full carbon-nitrogen cycle)
- **SP**: Satellite Phenology (prescribed LAI, simplified carbon)

The package auto-detects the mode based on available variables:

```python
from elm_diagnostics import CarbonBalance

run = Run("tests/fixtures/data")
cb = CarbonBalance(run, year=2001)

# Mode is detected automatically
print(f"Carbon mode: {cb.mode}")  # 'BGC' or 'SP'
```

Manual override if needed:
```python
cb = CarbonBalance(run, year=2001, mode="BGC")
```

### Carbon Balance Components

The carbon balance equation:

```
ΔC = GPP - AR - HR - Fire - Harvest
```

Where:
- **ΔC**: Change in ecosystem carbon storage
- **GPP**: Gross primary production (photosynthesis)
- **AR**: Autotrophic respiration (plant respiration)
- **HR**: Heterotrophic respiration (soil decomposition)
- **Fire**: Carbon loss to fire
- **Harvest**: Carbon removal by harvest

**Key fluxes:**
- `GPP`: Gross primary production
- `AR`: Autotrophic respiration
- `HR`: Heterotrophic respiration
- `ER`: Ecosystem respiration (AR + HR)
- `NEE`: Net ecosystem exchange (= ER - GPP, negative = carbon sink)
- `NBP`: Net biome production (= -NEE - Fire - Harvest)
- `TOTFIRE`: Total fire carbon loss
- `WOOD_HARVESTC`: Wood harvest carbon loss

**Storage pools:**
- `LEAFC`, `LIVESTEMC`, `DEADSTEMC`: Vegetation carbon
- `FROOTC`, `LIVECROOTC`, `DEADCROOTC`: Root carbon
- `TOTSOMC`: Total soil organic matter carbon
- `TOTLITC`: Total litter carbon
- `CWDC`: Coarse woody debris carbon
- `TOTECOSYSC`: Total ecosystem carbon (sum of all pools)

### Carbon Balance Example

```python
from elm_diagnostics import Run, CarbonBalance

run = Run("tests/fixtures/data")
cb = CarbonBalance(run, year=2001, frame="calendar")

# Get components
components = cb.components()

# Check closure
residual = cb.residual()
print(f"Carbon balance residual: {residual.values[-1]:.2f} gC/m²")

# Plot
fig_cumulative, fig_decomposition = cb.plot()
fig_cumulative.savefig("carbon_balance.png", dpi=300)

# Extract key metrics
gpp_annual = float(components["GPP"].values[-1])
nee_annual = float(components["NEE"].values[-1])

print(f"Annual GPP: {gpp_annual:.0f} gC/m²")
print(f"Annual NEE: {nee_annual:.0f} gC/m² (negative = sink)")
```

### Common Carbon Balance Issues

- **BGC vs SP confusion**: Ensure correct mode is detected
- **Missing fire/harvest**: Not all simulations include these fluxes
- **CH4 fluxes**: For wetland simulations, CH4 is a separate carbon pathway
- **Nitrogen limitation**: In BGC mode, N limitation affects closure

## Energy Balance

### Energy Balance Considerations

Energy balance in ELM is more complex than water or carbon:

**Key differences:**
1. **Flux balance** rather than cumulative (by default)
2. **Instantaneous** rather than integrated over time
3. **Multiple components**: radiation, turbulent, ground heat flux
4. **Storage terms** often not in standard output (HC, HCSOI marked inactive)

The energy balance equation:

```
R_net = H + LE + G + ΔE
```

Where:
- **R_net**: Net radiation (shortwave + longwave)
- **H**: Sensible heat flux
- **LE**: Latent heat flux (evaporation)
- **G**: Ground heat flux
- **ΔE**: Change in heat storage (soil + snow)

### Energy Balance Components

**Radiation fluxes:**
- `FSDS`: Downward shortwave radiation (incoming)
- `FSR`: Reflected shortwave radiation (outgoing)
- `FSA`: Absorbed shortwave radiation (= FSDS - FSR)
- `FLDS`: Downward longwave radiation (incoming)
- `FIRE`: Upward longwave radiation (outgoing, emitted)
- `FIRA`: Absorbed longwave radiation (= FLDS - FIRE)

**Turbulent fluxes:**
- `FSH`: Sensible heat flux
- `EFLX_LH_TOT`: Latent heat flux (total evaporation)

**Ground heat flux:**
- `FGR`: Ground heat flux
- `FGR12`: Ground heat flux at 12cm depth (alternative)

**Storage terms** (not in default h0 output):
- `HC`: Heat content (soil + snow)
- `HCSOI`: Heat content (soil only)

**Error diagnostics:**
- `ERRSOI`: Soil energy balance error
- `ERRSEB`: Surface energy balance error

### Energy Balance Example

```python
from elm_diagnostics import Run, EnergyBalance

run = Run("tests/fixtures/data")
eb = EnergyBalance(run, year=2001, frame="calendar")

# By default, cumulative=False (instantaneous fluxes)
# Can set cumulative=True for integrated energy

# Get components
components = eb.components()

# Plot
fig_fluxes, fig_components = eb.plot()
fig_fluxes.savefig("energy_balance.png", dpi=300)

# Check mean flux balance
rnet = components["FSA"] + components["FIRA"]  # Net radiation
h = components["FSH"]
le = components["EFLX_LH_TOT"]
g = components["FGR"]

residual = rnet - h - le - g
mean_residual = float(residual.mean())
print(f"Mean energy balance residual: {mean_residual:.2f} W/m²")
```

### Energy Balance Interpretation

Unlike water and carbon, energy balance:
- Does not accumulate over annual cycles
- Should close instantaneously at each timestep
- Storage terms often negligible for monthly averages
- Residuals typically larger (5-10 W/m² acceptable)

**Common patterns:**
- Net radiation > 0 during growing season, < 0 in winter
- Sensible heat flux (H) dominates in dry conditions
- Latent heat flux (LE) dominates in wet conditions
- Ground heat flux (G) stores energy in spring, releases in fall

## CLI Workflows

### Quick Balance Checks

**Check all three balances:**
```bash
# Water balance
elm-diagnostics balance water tests/fixtures/data --config year_2001.yaml

# Carbon balance  
elm-diagnostics balance carbon tests/fixtures/data --config year_2001.yaml

# Energy balance
elm-diagnostics balance energy tests/fixtures/data --config year_2001.yaml
```

**Save outputs:**
```bash
elm-diagnostics balance water tests/fixtures/data --config year_2001.yaml --out ./results/
# Creates: results/water_panel1.png, results/water_panel2.png, results/water_balance.nc
```

**Quiet mode for scripts:**
```bash
elm-diagnostics balance water tests/fixtures/data --config year_2001.yaml --quiet --out ./results/
# Minimal output, suitable for batch processing
```

### Batch Processing Script

Process multiple years automatically:

```bash
#!/bin/bash
# check_balances.sh - Check water balance for multiple years

DATA_DIR="tests/fixtures/data"
OUTPUT_DIR="./balance_results"

mkdir -p "$OUTPUT_DIR"

for year in 2001 2002 2003; do
    echo "Checking water balance for year $year..."
    elm-diagnostics balance water "$DATA_DIR" \
    --config "$OUTPUT_DIR/year_${year}.yaml" \
        --out "$OUTPUT_DIR/year_$year" \
        --quiet
done

echo "All balances complete. Results in $OUTPUT_DIR/"
```

### Report Generation

Generate comprehensive HTML report with all balances:

```bash
# Single year
elm-diagnostics report tests/fixtures/data --config year_2001.yaml

# Multi-year analysis window from config
elm-diagnostics report tests/fixtures/data --config years_2000_2005.yaml

# Custom output location
elm-diagnostics report tests/fixtures/data --out ./diagnostics_report/

# With custom water year start + year window
elm-diagnostics report tests/fixtures/data --config wy_october_2001.yaml
```

## Best Practices

### 1. Always Check Closure First

Before analyzing results, verify budget closure:

```python
run = Run("./simulation_output")

# Quick closure check
wb = WaterBalance(run, year=2001)
wb_residual = wb.residual().values[-1]

cb = CarbonBalance(run, year=2001)
cb_residual = cb.residual().values[-1]

print(f"Water residual: {wb_residual:.2f} mm (target: <1 mm)")
print(f"Carbon residual: {cb_residual:.2f} gC/m² (target: <1 gC/m²)")

if abs(wb_residual) > 10 or abs(cb_residual) > 10:
    print("WARNING: Poor closure - investigate before using results")
```

### 2. Use Water Years for Water Balance

Water balance should use hydrologic year:

```python
# Correct
wb = WaterBalance(run, year=2001, frame="water_year")

# Also valid for calendar year comparisons
wb = WaterBalance(run, year=2001, frame="calendar")
```

### 3. Multi-Year Consistency Checks

Check that closure is consistent across multiple years:

```python
residuals = []
for year in range(2000, 2010):
    wb = WaterBalance(run, year=year)
    residuals.append(wb.residual().values[-1])

import numpy as np
print(f"Mean residual: {np.mean(residuals):.2f} mm")
print(f"Std residual: {np.std(residuals):.2f} mm")

# Should have low standard deviation for consistent closure
```

### 4. Document Closure for Publications

When publishing results, report closure metrics:

```python
# Generate reproducible metrics
from elm_diagnostics import Run, WaterBalance

run = Run("./publication_data", name="Site X")
wb = WaterBalance(run, year=2001, frame="water_year")

# Save report
wb.to_netcdf("paper_water_balance_WY2001.nc")

# Save figure
fig_cumulative, fig_decomposition = wb.plot()
fig_cumulative.savefig("Figure1_water_balance.png", dpi=300, bbox_inches="tight")

# Print metrics for manuscript
print(f"Water balance closure residual: {wb.residual().values[-1]:.2f} mm/year")
```

## Summary

**Quick reference:**

```python
# Water balance (most common)
from elm_diagnostics import Run, WaterBalance
run = Run("./data")
wb = WaterBalance(run, year=2001, frame="water_year")
print(f"Residual: {wb.residual().values[-1]:.2f} mm")

# Carbon balance
from elm_diagnostics import CarbonBalance
cb = CarbonBalance(run, year=2001)
print(f"Residual: {cb.residual().values[-1]:.2f} gC/m²")

# Energy balance
from elm_diagnostics import EnergyBalance
eb = EnergyBalance(run, year=2001)
components = eb.components()
```

**Command-line:**
```bash
elm-diagnostics balance water ./data --config year_2001.yaml
elm-diagnostics balance carbon ./data --config year_2001.yaml
elm-diagnostics balance energy ./data --config year_2001.yaml
```

**Next steps:**
- [Experiment Comparison](tutorial-experiment-comparison.md) - Compare base vs modified runs
- [Workflow Examples](workflow-examples.md) - Practical automation patterns
