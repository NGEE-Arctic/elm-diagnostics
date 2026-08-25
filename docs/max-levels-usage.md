# Limiting Vertical Layers in Soil Hydrology Plots

## Problem

When plotting soil variables like `H2OSOI`, `SOILLIQ`, and `SOILICE` that have 15 vertical layers (`levgrnd`), only the top 10 layers are hydrologically active in ELM. Plotting all 15 layers compresses the vertical scale and makes it difficult to see meaningful changes in the active zone.

## Solution

elm-diagnostics supports limiting plotted vertical layers via the `max_levels` configuration parameter, with **variable-group-specific defaults**.

### Default Behavior (No Configuration Needed!)

**Hydrology variables** (H2OSOI, SOILLIQ, SOILICE, etc.) automatically show only the top 10 hydrologically active layers by default.

**Other soil variables** (TSOI, etc.) show all vertical layers by default.

This is configured via variable groups in the defaults, so you don't need to configure anything for typical use cases!

### Per-Group Configuration

To customize a specific variable group, add to `~/.config/elm-diagnostics/config.yaml`:

```yaml
variable_groups:
  hydrology:
    hovmuller:
      max_levels: 12  # Change from default 10 to 12
  soil_state:
    hovmuller:
      max_levels: 10  # Apply same limit to TSOI
```

### Global Configuration

To apply the same limit to ALL variables with vertical structure:

```yaml
plots:
  hovmuller:
    max_levels: 10  # Apply to all variables (unless group overrides)
```

This affects:
- Hovmuller (depth × time) heatmap plots
- Timeseries multilevel line plots

### Alternative: Physical Depth Limit

You can also limit by physical depth (in meters) instead:

```yaml
plots:
  hovmuller:
    max_depth_m: 3.5  # Show only layers within top 3.5 meters
```

**Note:** `max_levels` and `max_depth_m` are mutually exclusive - only set one or the other.

### Python API Example

```python
from elm_diagnostics import Run
from elm_diagnostics.config import Config
from elm_diagnostics.plots import plot_hovmuller, plot_timeseries

# Load your data
run = Run("/path/to/elm/output")

# Configure max_levels
config = Config()
config.plots.hovmuller.max_levels = 10

# Generate plots with limited vertical extent
fig_hov = plot_hovmuller(run, "SOILLIQ", config=config)
fig_ts = plot_timeseries(run, "SOILICE", config=config)

fig_hov.savefig("soilliq_hovmuller_10levels.png")
fig_ts.savefig("soilice_timeseries_10levels.png")
```

### CLI Example

Create a config file:

```bash
cat > my_config.yaml << EOF
plots:
  hovmuller:
    max_levels: 10
EOF
```

Then use it with the CLI:

```bash
# Set as default by placing in ~/.config/elm-diagnostics/config.yaml
elm-diagnostics plot SOILLIQ /path/to/elm/output --kind hovmuller

# Or specify config file explicitly (not yet implemented)
```

### Default Behavior

By default, `max_levels` is `null` (unset), which shows all vertical levels. This preserves backward compatibility and allows existing workflows to continue working unchanged.

To focus on hydrologically active layers for soil hydrology analysis, explicitly set `max_levels: 10` in your user configuration.
