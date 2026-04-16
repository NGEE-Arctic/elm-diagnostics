# Getting Started with elm-diagnostics

This tutorial covers the fundamentals of `elm-diagnostics`, including installation, core concepts, and basic operations. By the end, you will be able to load ELM output, access variables, and perform basic diagnostics.

## Prerequisites

- **Python** ≥ 3.10
- **Working knowledge** of xarray and pandas
- **Familiarity** with ELM model output structure
- **ELM simulation output** (h0, h1, or other history files)

## Installation

### Standard Installation

From the package directory:

```bash
pip install -e ".[dev]"
```

This installs the core package with development dependencies including pytest.

### Optional Dependencies

For additional features:

```bash
# Parallel processing with dask
pip install -e ".[dask]"

# Interactive plots with plotly
pip install -e ".[interactive]"

# Spatial maps with cartopy
pip install -e ".[maps]"

# Install everything
pip install -e ".[all]"
```

### Verify Installation

```bash
# Check CLI is available
elm-diagnostics --help

# Run test suite
pytest tests/
```

If all tests pass (161 tests), your installation is working correctly.

## Core Concepts

### The Run Object

The `Run` class is the primary interface for working with ELM output. It represents a single ELM simulation case.

```python
from elm_diagnostics import Run

# Load from a directory containing ELM history files
run = Run("/path/to/simulation/output")

# Optionally provide a descriptive name
run = Run("/path/to/simulation/output", name="Oak Harbor 2001")
```

The `Run` object automatically:
- Discovers all history files (`*.elm.h*.nc`) in the directory
- Organizes them by stream (h0, h1, h2, etc.)
- Opens them lazily using xarray's `open_mfdataset`
- Handles time coordinate decoding with cftime

### History Streams

ELM typically produces multiple history file streams with different output frequencies:
- **h0**: Monthly averages (standard)
- **h1**: Daily or sub-daily output (if configured)
- **h2+**: Additional custom streams

Access streams via the `streams` dictionary:

```python
# View available streams
print(run.streams.keys())  # dict_keys(['h0', 'h1'])

# Access a specific stream as xarray Dataset
h0_data = run.streams["h0"]
print(h0_data)
```

### Variable Access

Variables can be accessed in two ways:

**1. Direct from streams (xarray):**
```python
rain = run.streams["h0"]["RAIN"]
```

**2. Using the `get()` method (recommended):**
```python
rain = run.get("RAIN")
```

The `get()` method is preferred because it:
- Searches across all streams in priority order (finest cadence first)
- Automatically derives missing variables (e.g., `QFLX_EVAP_TOT`)
- Provides consistent interface regardless of which stream contains the variable

### Checking Variable Availability

```python
# Check if a variable exists
if run.has("QFLX_EVAP_TOT"):
    et = run.get("QFLX_EVAP_TOT")
else:
    print("Variable not available")
```

## Hands-On Example: Oak Harbor Test Data

The package includes real ELM output from a single-point simulation at Oak Harbor, WA. This data is used for testing and examples throughout the documentation.

### Loading the Test Dataset

```python
from elm_diagnostics import Run
from pathlib import Path

# Path to test data (adjust based on your installation)
test_data = Path("tests/fixtures/data")
run = Run(test_data, name="Oak Harbor")

print(f"Loaded: {run.name}")
print(f"Streams: {list(run.streams.keys())}")
```

**Expected output:**
```
Loaded: Oak Harbor
Streams: ['h0']
```

### Exploring the Dataset

```python
# Access the h0 stream
h0 = run.streams["h0"]

# Check dimensions
print(f"Time steps: {h0.sizes['time']}")        # 15 months
print(f"Spatial points: {h0.sizes['lndgrid']}") # 1 (single-point)
print(f"Soil levels: {h0.sizes['levgrnd']}")    # 15 levels

# Check time range
print(f"Start: {h0.time.values[0]}")   # 2000-10-16 (mid-October)
print(f"End: {h0.time.values[-1]}")    # 2001-12-16 (mid-December)
```

This dataset spans 15 months from October 2000 through December 2001, providing:
- Complete Water Year 2001 (October 2000 - September 2001)
- Complete calendar year 2001
- Sufficient data for seasonal cycle analysis

### Understanding Spatial Dimensions

ELM output has different spatial dimensions depending on configuration:

**Single-point or column runs** (like Oak Harbor):
- Use `lndgrid` dimension (typically size 1)
- No `lat`/`lon` as separate dimensions

**Gridded runs:**
- Use `lat` × `lon` dimensions
- Or `ncol`/`lndgrid` for unstructured grids (depending on dycore)

The `Run` class handles both cases transparently.

### Getting Variables with Auto-Derivation

One of the key features of `elm-diagnostics` is automatic variable derivation. For example, `QFLX_EVAP_TOT` (total evapotranspiration) is marked `inactive` by default in ELM output, but can be computed from components.

```python
# This variable is NOT in the Oak Harbor file
print(run.has("QFLX_EVAP_TOT"))  # False

# But get() will compute it automatically
et_total = run.get("QFLX_EVAP_TOT")
print(et_total.name)  # QFLX_EVAP_TOT
print(et_total.attrs["description"])  # "Computed as QSOIL + QVEGE + QVEGT"

# Verify it matches manual computation
qsoil = run.get("QSOIL")  # Ground evaporation
qvege = run.get("QVEGE")  # Canopy evaporation
qvegt = run.get("QVEGT")  # Transpiration

manual_et = qsoil + qvege + qvegt
print(f"Auto-derived matches manual: {et_total.equals(manual_et)}")  # True
```

**Automatically derived variables include:**
- `QFLX_EVAP_TOT`: Total evapotranspiration (QSOIL + QVEGE + QVEGT)
- Additional derivations as needed (see `elm_diagnostics/io/derived.py`)

### Working with 3D Soil Variables

Many soil variables have vertical structure with 15 soil layers (`levgrnd` dimension):

```python
# Get soil liquid water content (3D: time × levgrnd × lndgrid)
soilliq = run.get("SOILLIQ")
print(soilliq.dims)   # ('time', 'levgrnd', 'lndgrid')
print(soilliq.shape)  # (15, 15, 1)

# Sum over all soil layers to get total column water
total_soilliq = soilliq.sum(dim="levgrnd")
print(total_soilliq.dims)   # ('time', 'lndgrid')
print(total_soilliq.shape)  # (15, 1)

# Plot total soil liquid water over time
import matplotlib.pyplot as plt

total_soilliq.plot()
plt.title("Total Soil Liquid Water")
plt.ylabel("kg/m²")
plt.tight_layout()
plt.savefig("soilliq_timeseries.png")
```

**Water balance calculations automatically aggregate 3D variables** (more in [Balance Checking tutorial](tutorial-balance-checking.md)).

### Understanding Time Coordinates

ELM uses `cftime` for calendar-aware time handling:

```python
# Time coordinates use cftime
print(type(h0.time.values[0]))  # <class 'cftime.DatetimeNoLeap'>

# The Oak Harbor data uses 'noleap' calendar (365 days/year)
print(h0.time.encoding["calendar"])  # noleap

# Time bounds indicate averaging period
print(h0.time_bounds)  # Shape: (time, 2) with start/end of each period
```

### Water Year vs Calendar Year

Water year (hydrological year) often starts in October rather than January. This is important for water balance calculations:

```python
from elm_diagnostics import WaterBalance

# Water year 2001 = Oct 2000 through Sep 2001
wb_wy = WaterBalance(run, year=2001, frame="water_year")

# Calendar year 2001 = Jan 2001 through Dec 2001  
wb_cy = WaterBalance(run, year=2001, frame="calendar")
```

The default water year start month is October (month 10), but this is configurable. See [Balance Checking tutorial](tutorial-balance-checking.md) for details.

## Common Operations

### Accessing Raw xarray Datasets

Sometimes you need direct access to the underlying xarray Dataset:

```python
# Get the raw Dataset for custom analysis
h0 = run.streams["h0"]

# Use all xarray methods
gpp = h0["GPP"]
annual_gpp = gpp.groupby("time.year").mean()

# Select specific time ranges
year_2001 = h0.sel(time=slice("2001-01", "2001-12"))
```

### Time Subsetting

```python
# Get a specific variable for a time range
gpp = run.get("GPP")
summer_2001 = gpp.sel(time=slice("2001-06", "2001-08"))

print(f"Summer mean GPP: {summer_2001.mean().values:.2f} {gpp.attrs['units']}")
```

### Working with Units

Variables include unit information in attributes:

```python
rain = run.get("RAIN")
print(f"Units: {rain.attrs['units']}")        # mm/s
print(f"Long name: {rain.attrs['long_name']}")  # atmospheric rain

# The package uses pint for unit-aware calculations
# Flux integration automatically handles mm/s → mm conversions
```

### Handling Missing Variables

```python
# Check before accessing
if run.has("QSNWCPICE"):
    snow_compaction = run.get("QSNWCPICE")
else:
    print("QSNWCPICE not available in output")
    
# Or use try/except
try:
    var = run.get("SOME_VARIABLE")
except KeyError:
    print("Variable not found and cannot be derived")
```

### Closing Runs

When done with a `Run` object, especially in scripts processing many files:

```python
run.close()
```

This closes the underlying xarray datasets and frees memory.

## Next Steps

Now that you understand the basics, you can:

1. **[Check budget closure](tutorial-balance-checking.md)** - Learn water, carbon, and energy balance diagnostics
2. **[Compare experiments](tutorial-experiment-comparison.md)** - Analyze differences between simulations
3. **[Explore workflows](workflow-examples.md)** - See practical examples and automation patterns

### Quick Reference

**Essential imports:**
```python
from elm_diagnostics import Run, WaterBalance, CarbonBalance, EnergyBalance
from elm_diagnostics import Comparison, Report
from elm_diagnostics.plots import (
    plot_timeseries, plot_seasonal, plot_anomaly,
    plot_histogram, plot_diurnal
)
```

**Basic workflow:**
```python
# 1. Load data
run = Run("/path/to/output", name="Descriptive Name")

# 2. Check what's available
print(run.streams.keys())

# 3. Get variables
var = run.get("VARIABLE_NAME")

# 4. Analyze (see other tutorials)
# ...

# 5. Clean up
run.close()
```

### Getting Help

- **Command-line help**: `elm-diagnostics --help`
- **Function help**: `help(WaterBalance)` in Python
- **Variable definitions**: See [Variable Mappings](variable-mappings.md)
- **Design details**: See [Design Specification](../elm-diagnostics-spec.md)
