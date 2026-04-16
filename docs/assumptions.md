# Assumptions (Phase 0)

These assumptions were made in the absence of a real ELM history file.
They have been **verified and updated** based on the oakharbor_column h0 file and ELM source code (April 2026).

## Dimension names

### Verified from oakharbor_column.elm.elm.h0.2002-01.nc:
- Time dimension: `time` ✓
- Spatial (single-point): `lndgrid` (NOT separate `lat`/`lon` for column output)
- Sub-gridcell: `column`, `pft`, `landunit`, `topounit` ✓
- Vertical soil: `levgrnd=15`, `levsoi=10` ✓
- Decomposition layers: `levdcmp=15` ✓
- Snow layers: `levsno=5` ✓
- Lake layers: `levlak=10` ✓

### Note on spatial dimensions:
- Single-point/column runs use `lndgrid` dimension (size 1)
- Gridded runs use `lat` × `lon` or potentially `ncol`/`lndgrid` depending on dycore
- The Run class handles both cases transparently

## Time encoding

- Calendar: `noleap` (verified in h0 file) ✓
- Time bounds variable: `time_bounds` with shape `(time, hist_interval)` where `hist_interval=2` ✓
- Flux variables have `cell_methods = "time: mean"` ✓
- States are instantaneous snapshots (no cell_methods attribute)

## File naming convention

- Pattern verified: `{casename}.elm.h{N}.{date}.nc` ✓
  - Example: `oakharbor_column.elm.elm.h0.2002-01.nc`
  - Stream: `h0`
  - Date: `2002-01` (monthly)

## Variable names

**All variable names verified against E3SM IM1 ELM source code at `/code/E3SM/IM1/components/elm/src/` (April 2026).**

### Water Balance (verified against BalanceCheckMod.F90, VegetationDataType.F90):

#### **Total Evapotranspiration - CORRECTED**
- **`QFLX_EVAP_TOT`** is marked `default='inactive'` in ELM history output
- **Must be computed if not available**: `QFLX_EVAP_TOT = QSOIL + QVEGE + QVEGT`
  - `QSOIL`: Ground evaporation (soil/snow evap + sublimation - dew)
  - `QVEGE`: Canopy evaporation (from leaves and stems)
  - `QVEGT`: Canopy transpiration (stomatal)
- Source: SoilFluxesMod.F90 line 313, VegetationDataType.F90 lines 5550-5552

#### **Water Balance Components**
- **Inputs**: `RAIN`, `SNOW` ✓
- **Outputs**: 
  - `QFLX_EVAP_TOT` (or computed from components) ✓
  - `QOVER` (surface runoff) ✓
  - `QDRAI` (sub-surface drainage) ✓
  - `QDRAI_PERCH` (perched water table drainage) ✓
  - `QSNOMELT` (snow melt, but NOT a loss from column) ✓
- **Storage**: 
  - `SOILLIQ` (liquid water, needs vertical sum over `levgrnd`) ✓
  - `SOILICE` (ice, needs vertical sum over `levgrnd`) ✓
  - `H2OSNO` (snow water equivalent) ✓
  - `H2OCAN` (canopy water) ✓
  - `H2OSFC` (surface water) ✓

#### **CRITICAL CORRECTION - QSNWCPICE**
- **`QSNWCPICE` is NOT snow sublimation** (user was correct to flag this!)
- It represents **excess snowfall removed due to snow capping** (runoff term)
- Source: SnowHydrologyMod.F90 lines 2240-2352, lnd2atmType.F90 lines 211-213
- **Removed from water balance output list**

### Carbon Balance (verified against VegetationDataType.F90, CNBalanceCheckMod.F90):
- Pools: `LEAFC`, `LIVESTEMC`, `DEADSTEMC`, `FROOTC`, `LIVECROOTC`, `DEADCROOTC`, `TOTSOMC`, `TOTLITC`, `CWDC` ✓
- Fluxes: `GPP`, `AR`, `HR`, `ER`, `NEE` ✓
- Fire losses: `TOTFIRE` (NOT `COL_FIRE_CLOSS`) ✓
- Harvest: `WOOD_HARVESTC` (NOT `HRV_XSMRPOOL_TO_ATM`) ✓
- CH4 fluxes use `_SAT` / `_UNSAT` suffixes (NOT `_SOIL`) ✓

### Energy Balance (verified against ColumnDataType.F90, EnergyFluxType.F90):
- **Radiation**: `FSDS`, `FSR`, `FLDS`, `FIRE`, `FSA`, `FIRA` ✓
- **Turbulent**: `FSH`, `EFLX_LH_TOT` ✓
- **Ground heat flux**: `FGR` (soil heat flux) ✓, `FGR12` (flux between layers 1-2) ✓
- **Storage** (verified from SoilTemperatureMod.F90 lines 664-691):
  - `HC` (total heat content: soil + snow + lake, units: MJ/m²) ✓
  - `HCSOI` (soil-only heat content, units: MJ/m²) ✓
  - **Both marked `default='inactive'` - must be explicitly requested in fincl**
  - These are **state variables** - need dHC/dt for flux equivalent
- **Energy balance errors**: `ERRSOI`, `ERRSEB` ✓

## Computed Variables

The following variables are automatically computed if not present in history output:

1. **`QFLX_EVAP_TOT`**: Computed from `QSOIL + QVEGE + QVEGT`
2. **`TOTAL_SOIL_WATER`**: Computed from `sum(SOILLIQ) + sum(SOILICE)` over vertical levels

See `elm_diagnostics/io/derived.py` for implementation details.

## Source Code References

All corrections verified against:
- `/code/E3SM/IM1/components/elm/src/biogeophys/SoilFluxesMod.F90`
- `/code/E3SM/IM1/components/elm/src/biogeophys/BalanceCheckMod.F90`
- `/code/E3SM/IM1/components/elm/src/biogeophys/SnowHydrologyMod.F90`
- `/code/E3SM/IM1/components/elm/src/biogeophys/SoilTemperatureMod.F90`
- `/code/E3SM/IM1/components/elm/src/data_types/ColumnDataType.F90`
- `/code/E3SM/IM1/components/elm/src/data_types/VegetationDataType.F90`
- `/code/E3SM/IM1/components/elm/src/cpl/lnd2atmType.F90`
- `/code/E3SM/IM1/components/elm/src/cpl/lnd2atmMod.F90`
