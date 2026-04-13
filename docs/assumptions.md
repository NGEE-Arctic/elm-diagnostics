# Assumptions (Phase 0)

These assumptions were made in the absence of a real ELM history file.
They should be verified once a sample h0 file is available.

## Dimension names

- Time dimension: `time`
- Spatial (gridded): `lat`, `lon`
- Sub-gridcell: `column`, `pft`, `landunit`
- Vertical soil: `levgrnd` (or `levsoi` for a subset)
- Snow layers: `levsno`

## Time encoding

- Calendar: assumed `noleap` (ELM default); code handles all cftime calendars.
- Time bounds variable: assumed `time_bounds` with shape `(time, 2)`.
- Flux variables are time-averaged; states are instantaneous snapshots.
  Disambiguation via `cell_methods` attribute where present.

## File naming convention

- Pattern: `{casename}.elm.h{N}.{date}.nc` where N = 0, 1, 2, ...
- Stream auto-discovery glob: `*.elm.h*.*.nc`

## Variable names

All variable names in `defaults.yaml` were verified against the ELM source at
`/code/E3SM/IM1/components/elm/src/` (Phase 0 reconnaissance, April 2026).
Key corrections from the original spec:

- Water outputs: QOVER (not Q_over), QDRAI (not Q_drain), QDRAI_PERCH (not Q_drain_perched),
  QFLX_SUB_SNOW (not Q_subl), QSNOMELT (not Q_melt), QFLX_EVAP_GRND (not QFLX_EVAP_SOI)
- Carbon: TOTFIRE (not COL_FIRE_CLOSS), WOOD_HARVESTC (not HRV_XSMRPOOL_TO_ATM)
- CH4: uses SAT/UNSAT suffixes, not SOIL suffix
- Energy storage: hc_soisno (MJ/m2, column-level), not HEAT_FROM_AC/URBAN_HEAT
