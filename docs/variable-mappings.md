# ELM Variable Mappings and Definitions

**Last updated:** April 2026  
**Source code reference:** `/code/E3SM/IM1/components/elm/src/`  
**Test file:** `oakharbor_column.elm.elm.h0.2002-01.nc`

This document maps ELM history field names to their definitions, source code locations, and usage in `elm-diagnostics`. All information has been verified against the E3SM IM1 ELM source code.

---

## Table of Contents
1. [Water Balance Variables](#water-balance-variables)
2. [Carbon Balance Variables](#carbon-balance-variables)
3. [Energy Balance Variables](#energy-balance-variables)
4. [Atmospheric Forcing Variables](#atmospheric-forcing-variables)
5. [Computed/Derived Variables](#computedderived-variables)
6. [Common Issues and Solutions](#common-issues-and-solutions)

---

## Water Balance Variables

### Precipitation Inputs

#### `RAIN`
- **Long name:** Atmospheric rain
- **Units:** mm/s
- **Type:** Flux (positive = into column)
- **Source:** `VegetationDataType.F90:5484`
- **In default h0:** Yes ✓
- **Notes:** Liquid precipitation only

#### `SNOW`
- **Long name:** Atmospheric snow
- **Units:** mm/s (water equivalent)
- **Type:** Flux (positive = into column)
- **Source:** `VegetationDataType.F90:5487`
- **In default h0:** Yes ✓
- **Notes:** Solid precipitation (snow, sleet, hail)

### Evapotranspiration Outputs

#### `QFLX_EVAP_TOT` ⚠️
- **Long name:** Total evapotranspiration
- **Units:** mm/s
- **Type:** Flux (positive = to atmosphere)
- **Formula:** `QSOIL + QVEGE + QVEGT`
- **Source:** `VegetationDataType.F90:5550-5552`, `SoilFluxesMod.F90:313`
- **In default h0:** **NO** - marked `default='inactive'`
- **Computed by:** `elm_diagnostics.io.derived.compute_total_et()`
- **Critical note:** Must be explicitly requested in history output OR computed from components

#### `QSOIL`
- **Long name:** Ground evaporation (soil/snow evaporation + soil/snow sublimation - dew)
- **Units:** mm/s
- **Type:** Flux (positive = to atmosphere)
- **Source:** `VegetationDataType.F90:5500-5502`
- **Variable name:** `qflx_evap_soi`
- **In default h0:** Yes ✓
- **Notes:** Includes both liquid evaporation and solid sublimation from ground/snow

#### `QVEGE`
- **Long name:** Canopy evaporation
- **Units:** mm/s
- **Type:** Flux (positive = to atmosphere)
- **Source:** `VegetationDataType.F90:5505-5507`
- **Variable name:** `qflx_evap_can`
- **In default h0:** Yes ✓
- **Notes:** Evaporation from intercepted water on leaves and stems

#### `QVEGT`
- **Long name:** Canopy transpiration
- **Units:** mm/s
- **Type:** Flux (positive = to atmosphere)
- **Source:** `VegetationDataType.F90:5510-5512`
- **Variable name:** `qflx_tran_veg`
- **In default h0:** Yes ✓
- **Notes:** Stomatal transpiration from vegetation

### Runoff Outputs

#### `QOVER`
- **Long name:** Surface runoff
- **Units:** mm/s
- **Type:** Flux (out of column)
- **Source:** `ColumnDataType.F90`, `HydrologyDrainageMod.F90`
- **Variable name:** `qflx_surf`
- **In default h0:** Yes ✓
- **Notes:** Infiltration-excess + saturation-excess runoff

#### `QDRAI`
- **Long name:** Sub-surface drainage
- **Units:** mm/s
- **Type:** Flux (out of column)
- **Source:** `ColumnDataType.F90`, `HydrologyDrainageMod.F90`
- **Variable name:** `qflx_drain`
- **In default h0:** Yes ✓
- **Notes:** Drainage from bottom of soil column

#### `QDRAI_PERCH`
- **Long name:** Perched water table drainage
- **Units:** mm/s
- **Type:** Flux (out of column)
- **Source:** `ColumnDataType.F90`
- **Variable name:** `qflx_drain_perched`
- **In default h0:** Yes ✓
- **Notes:** Lateral drainage from perched saturated layers

### Internal Fluxes (NOT water balance outputs)

#### `QSNOMELT`
- **Long name:** Snow melt
- **Units:** mm/s
- **Type:** Internal flux (NOT a loss from column)
- **Source:** `ColumnDataType.F90`
- **In default h0:** Yes ✓
- **Notes:** Converts H2OSNO → SOILLIQ; does not leave column

#### `QSNWCPICE` ❌ **REMOVED FROM BALANCE**
- **Long name:** Excess snowfall due to snow capping
- **Units:** mm/s
- **Type:** Runoff (when snow depth > max allowed)
- **Source:** `SnowHydrologyMod.F90:2240-2352`, `lnd2atmType.F90:211-213`
- **Variable name:** `qflx_snwcp_ice`
- **In default h0:** May be present
- **Critical correction:** This is **NOT** snow sublimation! It's excess snow removed when depth exceeds `h2osno_max`. It should be included in runoff/outputs if present, not as evaporation.

### Storage Variables

#### `SOILLIQ`
- **Long name:** Soil liquid water
- **Units:** kg/m² (per layer)
- **Dimensions:** `(time, levgrnd, lndgrid)` - 3D with 15 vertical levels
- **Type:** State variable
- **Source:** `ColumnDataType.F90`
- **In default h0:** Yes ✓
- **Notes:** **Must sum over `levgrnd` dimension to get column total**

#### `SOILICE`
- **Long name:** Soil ice content
- **Units:** kg/m² (per layer)
- **Dimensions:** `(time, levgrnd, lndgrid)` - 3D with 15 vertical levels
- **Type:** State variable
- **Source:** `ColumnDataType.F90`
- **In default h0:** Yes ✓
- **Notes:** **Must sum over `levgrnd` dimension to get column total**

#### `H2OSNO`
- **Long name:** Snow water equivalent
- **Units:** kg/m² or mm
- **Type:** State variable
- **Source:** `ColumnDataType.F90`
- **In default h0:** Yes ✓

#### `H2OCAN`
- **Long name:** Intercepted water on canopy
- **Units:** kg/m² or mm
- **Type:** State variable
- **Source:** `ColumnDataType.F90`
- **In default h0:** Yes ✓

#### `H2OSFC`
- **Long name:** Surface water storage
- **Units:** kg/m² or mm
- **Type:** State variable
- **Source:** `ColumnDataType.F90`
- **In default h0:** Yes ✓

---

## Carbon Balance Variables

### Fluxes

#### `GPP`
- **Long name:** Gross primary production
- **Units:** gC/m²/s
- **Type:** Flux (into vegetation)
- **In default h0:** Yes ✓

#### `AR`
- **Long name:** Autotrophic respiration (MR + GR)
- **Units:** gC/m²/s
- **Type:** Flux (to atmosphere)
- **In default h0:** Yes ✓

#### `HR`
- **Long name:** Heterotrophic respiration
- **Units:** gC/m²/s
- **Type:** Flux (to atmosphere)
- **In default h0:** Yes ✓

#### `ER`
- **Long name:** Ecosystem respiration (AR + HR)
- **Units:** gC/m²/s
- **Type:** Flux (to atmosphere)
- **In default h0:** Yes ✓

#### `NEE`
- **Long name:** Net ecosystem exchange (ER - GPP)
- **Units:** gC/m²/s
- **Type:** Flux (positive = to atmosphere)
- **In default h0:** Yes ✓

#### `TOTFIRE`
- **Long name:** Total fire carbon loss
- **Units:** gC/m²/s
- **Type:** Flux (to atmosphere)
- **Source:** Carbon budget modules
- **In default h0:** Yes ✓
- **Note:** Replaces incorrect name `COL_FIRE_CLOSS` from original spec

#### `WOOD_HARVESTC`
- **Long name:** Wood harvest carbon
- **Units:** gC/m²/s
- **Type:** Flux (removal from ecosystem)
- **In default h0:** Yes ✓
- **Note:** Replaces incorrect name `HRV_XSMRPOOL_TO_ATM` from original spec

### Methane Fluxes

All CH4 fluxes have been verified to use `_SAT` / `_UNSAT` suffixes (not `_SOIL` as originally assumed):

#### `CH4_SURF_AERE_SAT` / `CH4_SURF_AERE_UNSAT`
- **Long name:** CH4 surface flux via aerenchyma from saturated/unsaturated zones
- **Units:** gC/m²/s

#### `CH4_SURF_DIFF_SAT` / `CH4_SURF_DIFF_UNSAT`
- **Long name:** CH4 surface flux via diffusion from saturated/unsaturated zones
- **Units:** gC/m²/s

#### `CH4_SURF_EBUL_SAT` / `CH4_SURF_EBUL_UNSAT`
- **Long name:** CH4 surface flux via ebullition from saturated/unsaturated zones
- **Units:** gC/m²/s

---

## Energy Balance Variables

### Radiation Fluxes

#### `FSDS`
- **Long name:** Downward shortwave radiation
- **Units:** W/m²
- **Type:** Flux (into surface)
- **In default h0:** Yes ✓

#### `FSR`
- **Long name:** Reflected shortwave radiation
- **Units:** W/m²
- **Type:** Flux (out of surface)
- **In default h0:** Yes ✓

#### `FSA`
- **Long name:** Absorbed shortwave radiation
- **Units:** W/m²
- **Formula:** `FSDS - FSR`
- **In default h0:** Yes ✓

#### `FLDS`
- **Long name:** Downward longwave radiation
- **Units:** W/m²
- **Type:** Flux (into surface)
- **In default h0:** Yes ✓

#### `FIRE`
- **Long name:** Emitted longwave radiation
- **Units:** W/m²
- **Type:** Flux (out of surface)
- **In default h0:** Yes ✓

#### `FIRA`
- **Long name:** Net longwave radiation
- **Units:** W/m²
- **Formula:** `FIRE - FLDS`
- **In default h0:** Yes ✓

### Turbulent Fluxes

#### `FSH`
- **Long name:** Sensible heat flux
- **Units:** W/m²
- **Type:** Flux (positive = upward to atmosphere)
- **In default h0:** Yes ✓

#### `EFLX_LH_TOT`
- **Long name:** Total latent heat flux
- **Units:** W/m²
- **Type:** Flux (positive = upward to atmosphere)
- **Formula:** `hvap * QFLX_EVAP_TOT`
- **In default h0:** Yes ✓
- **Notes:** Energy equivalent of total evapotranspiration

### Ground Heat Flux

#### `FGR`
- **Long name:** Soil heat flux (downward)
- **Units:** W/m²
- **Type:** Flux (positive = into soil)
- **Source:** `EnergyFluxType.F90`
- **Variable name:** `eflx_fgr`
- **In default h0:** Yes ✓

#### `FGR12`
- **Long name:** Ground heat flux between layers 1 and 2
- **Units:** W/m²
- **Type:** Flux
- **Source:** `ColumnDataType.F90`
- **Variable name:** `eflx_fgr12`
- **In default h0:** Yes ✓

### Heat Storage ⚠️

#### `HC` **NOT in default h0**
- **Long name:** Heat content of soil + snow + lake
- **Units:** MJ/m²
- **Type:** State variable (not flux!)
- **Source:** `ColumnDataType.F90:91`, `SoilTemperatureMod.F90:664-688`
- **Variable name:** `hc_soisno`
- **In default h0:** **NO** - marked `default='inactive'`
- **Calculation:** `Σ cv(j) * T(j) / 1e6` over all layers
- **Notes:** Must be explicitly requested via `fincl1 = 'HC'` in user_nl_elm. To get flux equivalent, compute `dHC/dt`.

#### `HCSOI` **NOT in default h0**
- **Long name:** Heat content of soil only (excludes snow)
- **Units:** MJ/m²
- **Type:** State variable
- **Source:** `ColumnDataType.F90:90`, `SoilTemperatureMod.F90:691`
- **Variable name:** `hc_soi`
- **In default h0:** **NO** - marked `default='inactive'`
- **Notes:** Subset of HC; must be explicitly requested

### Energy Balance Error Diagnostics

#### `ERRSOI`
- **Long name:** Soil/lake energy conservation error
- **Units:** W/m²
- **In default h0:** Check (may need explicit request)

#### `ERRSEB`
- **Long name:** Surface energy balance error
- **Units:** W/m²
- **In default h0:** Check (may need explicit request)

---

## Atmospheric Forcing Variables

These fields are the primary atmospheric inputs that drive ELM.  In offline
(I-case) runs they originate from a meteorological dataset (e.g. GSWP3,
CRUNCEP); in coupled runs they arrive from the atmosphere component.  ELM
writes them back to the history stream so they can be audited alongside model
response variables.

They are grouped in the report under the **`met_forcing`** variable group,
which is enabled by default and generates time-series, seasonal-cycle, and
histogram plots.

| Variable | Long name | Units | Typical h0 availability |
|----------|-----------|-------|--------------------------|
| `TBOT`   | Atmospheric air temperature | K | Yes ✓ |
| `RAIN`   | Atmospheric rain (liquid precip) | mm/s | Yes ✓ |
| `SNOW`   | Atmospheric snow (frozen precip, water equivalent) | mm/s | Yes ✓ |
| `PRECT`  | Total precipitation rate | mm/s | **Derived** (RAIN + SNOW) |
| `FSDS`   | Atmospheric incident solar (shortwave) radiation | W/m² | Yes ✓ |
| `FLDS`   | Atmospheric longwave radiation | W/m² | Yes ✓ |
| `WIND`   | Atmospheric wind speed | m/s | Yes ✓ |
| `PBOT`   | Atmospheric pressure | Pa | Yes ✓ |
| `QBOT`   | Atmospheric specific humidity | kg/kg | Yes ✓ |

### Notes

- `PRECT` is not a direct ELM output; it is derived on-the-fly by
  `elm-diagnostics` as `RAIN + SNOW`.  See the
  [Computed/Derived Variables](#computedderived-variables) section below.
- `FSDS` and `FLDS` also appear in the **`energy`** variable group because
  they are inputs to the surface energy balance.
- If a forcing variable is missing from a particular run's history stream
  (e.g., excluded from `fincl1`), `elm-diagnostics` skips it silently and
  no plot is generated for that variable.
- To disable the entire group or restrict to a subset of variables, override
  `variable_groups.met_forcing` in your user config (see
  [workflow examples](workflow-examples.md#met-forcing-group)).

---

## Computed/Derived Variables

These variables are automatically computed by `elm-diagnostics` if not present in the history output:

### `QFLX_EVAP_TOT` (Total Evapotranspiration)
- **Computation:** `QSOIL + QVEGE + QVEGT`
- **Required components:** All three ET components must be in history output
- **Implementation:** `elm_diagnostics/io/derived.py:compute_total_et()`
- **Usage:** Automatically invoked by `Run.get("QFLX_EVAP_TOT")` if not in file

### `TOTAL_SOIL_WATER` (Total Soil Water Storage)
- **Computation:** `sum(SOILLIQ) + sum(SOILICE)` over `levgrnd` dimension
- **Required components:** SOILLIQ and SOILICE with vertical profiles
- **Implementation:** `elm_diagnostics/io/derived.py:compute_total_soil_water()`

### `PRECT` (Total Precipitation Rate)
- **Computation:** `RAIN + SNOW`
- **Required components:** Both `RAIN` and `SNOW` must be in history output
- **Implementation:** `elm_diagnostics/io/derived.py:compute_total_precip()`
- **Usage:** Automatically invoked by `Run.get("PRECT")`; appears in the
  `met_forcing` variable group alongside its components

### Adding New Derived Variables

To add a new derived variable:

1. Create a function in `elm_diagnostics/io/derived.py`:
   ```python
   def compute_my_variable(run: Run) -> xr.DataArray:
       """Compute MY_VAR from components."""
       ...
       return result
   ```

2. Add to the registry:
   ```python
   DERIVABLE_VARS = {
       ...
       "MY_VAR": compute_my_variable,
   }
   ```

3. The variable will now be accessible via `run.get("MY_VAR")`

---

## Common Issues and Solutions

### Issue: "QFLX_EVAP_TOT not found"

**Solution:** This variable is `default='inactive'` in ELM. Either:
- Add to history field list: `fincl1 = 'QFLX_EVAP_TOT'` in `user_nl_elm`
- Let `elm-diagnostics` compute it from `QSOIL + QVEGE + QVEGT` (automatic)

### Issue: "Storage variables have wrong dimensions"

**Problem:** SOILLIQ and SOILICE are 3D: `(time, levgrnd, lndgrid)`

**Solution:** The water balance code automatically sums over `levgrnd`:
```python
# In elm_diagnostics/balances/water.py
if "levgrnd" in da.dims:
    da = da.sum(dim="levgrnd", keep_attrs=True)
```

### Issue: "Energy storage variables (HC, HCSOI) not in h0 file"

**Solution:** These must be explicitly requested:
```bash
# In user_nl_elm:
fincl1 = 'HC', 'HCSOI'
```

Or, for energy balance fluxes only (default), these aren't needed since cumulative=false.

### Issue: "lndgrid dimension instead of lat/lon"

**Explanation:** Single-point/column runs use `lndgrid` (size 1) instead of `lat` × `lon`.

**Solution:** The code handles this automatically. Use `da.squeeze()` to remove singleton dimensions if needed.

### Issue: "QSNWCPICE in wrong category"

**Correction:** QSNWCPICE is a **runoff term** (excess snow capping), NOT evaporation/sublimation. It has been removed from the water balance ET outputs.

---

## Source Code Reference Table

| Variable | Source File | Lines | Module |
|----------|------------|-------|---------|
| QFLX_EVAP_TOT | VegetationDataType.F90 | 5550-5552 | data_types |
| QSOIL | VegetationDataType.F90 | 5500-5502 | data_types |
| QVEGE | VegetationDataType.F90 | 5505-5507 | data_types |
| QVEGT | VegetationDataType.F90 | 5510-5512 | data_types |
| ET calculation | SoilFluxesMod.F90 | 313 | biogeophys |
| SOILLIQ, SOILICE | ColumnDataType.F90 | various | data_types |
| HC, HCSOI | SoilTemperatureMod.F90 | 664-691 | biogeophys |
| QSNWCPICE | SnowHydrologyMod.F90 | 2240-2352 | biogeophys |
| Water balance check | BalanceCheckMod.F90 | 344 | biogeophys |

---

## Version History

- **April 2026:** Initial creation based on E3SM IM1 ELM source code analysis
- **Verified against:** E3SM IM1 (`4c9b6c38c4`), oakharbor_column test file
- **Key corrections:** QSNWCPICE, QFLX_EVAP_TOT computation, HC/HCSOI variable names
