# `elm-diagnostics` — Design Specification (v1)

**Target implementer:** Claude Code
**Status:** Draft for implementation
**Scope:** v1 only; v2 items collected at end.

---

## 0. Phase 0 tasks (before writing code)

Claude Code **must** complete these before beginning implementation. Ask the user for:

1. **Path to ELM source tree** (likely an E3SM checkout). Needed to:
   - Inspect `components/elm/src/main/elm_varctl.F90` (or equivalent) to confirm the `dov2xy` namelist option and how sub-gridcell hierarchy output is controlled.
   - Inspect `components/elm/src/data_types/ColumnDataType.F90` (user-flagged this file) to build the authoritative energy-balance variable list and confirm water-balance variable names. **The user has explicitly flagged that some energy-balance variable names proposed in this spec may be wrong** — verify against source before locking the YAML defaults.
   - Scrape the master history-field registry (typically in `histFileMod.F90` / `histFldsMod.F90` and any `subgridAveMod.F90`) to build the full candidate variable list for the "general variable plots" module, including long names and units.

2. **Path to the CLM 4.5 technical note** (PDF). Needed to:
   - Cross-reference variable definitions and balance equations.
   - Populate docstrings and YAML `description:` fields with authoritative prose.

3. **One example ELM history file** (h0 preferably; h1 if different cadence exists). Needed to:
   - Verify dimension names (`time`, `lat`, `lon`, `column`, `pft`, `levgrnd`, `levsoi`, …).
   - Confirm time encoding (`cftime` calendar, bounds variable).
   - Inspect `time_bounds` / cell-method attributes used for flux-vs-state disambiguation.

If any of these are unavailable, document the assumption in `docs/assumptions.md` and proceed with the defaults in this spec, marked with `TODO(verify)`.

---

## 1. Package identity

- **Name:** `elm-diagnostics` (PyPI); import as `elm_diagnostics`.
- **Distribution:** pyproject.toml-based, `hatchling` or `setuptools` backend. No conda-forge submission in v1 (deferred; structure the package so it's ready).
- **Python:** ≥ 3.10.
- **License:** user to specify; default to BSD-3-Clause if unspecified.

---

## 2. Dependencies

**Required:** `xarray`, `numpy`, `pandas`, `matplotlib`, `jinja2`, `netcdf4`, `cftime`, `pyyaml`, `pint`, `pint-xarray`.

**Optional extras (declared in pyproject.toml):**
- `[dask]` → `dask`
- `[interactive]` → `plotly`
- `[maps]` → `cartopy`
- `[all]` → union of the above

`pint`/`pint-xarray` promoted from "optional" to "required" because budget closure critically depends on unit handling (fluxes in `kg m-2 s-1`, states in `mm` or `kg m-2`, energy in `W m-2` vs. `J m-2`). Silent unit bugs are the single largest failure mode for this kind of tool; paying the dependency cost is worth it.

---

## 3. Data model and ingest

### 3.1 `Run` object

A `Run` is the atomic unit of analysis. One run = one set of history-file streams from a single ELM case.

```python
elm_diagnostics.Run(
    path: str | Path,                  # directory containing *.elm.h*.nc OR glob
    name: str | None = None,           # display name; default = casename from filename
    streams: dict[str, str] | None = None,  # e.g. {"h0": "*.elm.h0.*.nc", "h1": ...}
    chunks: dict | None = None,        # passed to xr.open_mfdataset
)
```

Internals:
- Each stream opens lazily via `xr.open_mfdataset(..., combine="by_coords", decode_times=True, use_cftime=True)`.
- `Run.streams` → `dict[str, xr.Dataset]` keyed by history tape name (`"h0"`, `"h1"`, ...).
- Cadence is **inferred per stream** from `time_bounds` (not assumed monthly). Stored as `Run.cadence["h0"] = pd.Timedelta` (or `"monthly"` / `"annual"` sentinel for calendar-aware gaps).
- Variables from any tape are resolvable via `Run.get(varname)`, which searches tapes in a configured priority order (finest cadence first by default; overridable in YAML).

### 3.2 Comparison runs

```python
elm_diagnostics.Comparison(
    base: Run,
    experiment: Run,
    align: Literal["intersect", "union"] = "intersect",
)
```

All plotting modules accept either a `Run` or a `Comparison`. When a `Comparison` is passed, plots render both series with a consistent color convention (base = neutral gray, experiment = accent) and add a `Δ` panel where meaningful.

### 3.3 Sub-gridcell hierarchy

If `dov2xy = .false.` for a stream (detected by the presence of `column`, `pft`, or `landunit` dims on relevant variables), plots gain a `by="column" | "pft" | "landunit"` keyword that facets or overlays the subgrid members. If `dov2xy = .true.` (gridcell-averaged output), this keyword raises a clear error. **Phase 0 task 1** confirms the exact dimension names.

### 3.4 Flux vs. state detection and unit-aware integration

Every variable is classified as `flux`, `state`, or `intensive` based on `cell_methods` and units, parsed through `pint-xarray`. Flux integration to cumulative uses `time_bounds` widths, not assumed uniform `dt`. This is non-negotiable — the user explicitly flagged this pitfall.

---

## 4. Configuration (YAML)

Single YAML file, default location `~/.config/elm-diagnostics/config.yaml`, overridable with `--config` CLI flag or `Run(..., config=...)` kwarg. A package-shipped `defaults.yaml` merges underneath user config.

### 4.1 YAML schema (sketch)

```yaml
report:
  title_template: "ELM diagnostics — {casename}"
  output_formats: [png, netcdf]   # png always, netcdf saves the plotted arrays

plots:
  style:
    figsize: [8, 5]
    dpi: 150
    palette: "tab10"
  climatology:
    envelope: "minmax"            # or "p10_p90", "std"

time:
  water_year_start_month: 10      # configurable per user
  analysis_start_year: null       # inclusive lower bound, null = open
  analysis_end_year: null         # inclusive upper bound, null = open

balances:
  water:
    storages: [SOILLIQ, SOILICE, H2OSNO, H2OCAN, H2OSFC]
    inputs:   [RAIN, SNOW]
    outputs:  [QFLX_EVAP_VEG, QFLX_EVAP_SOI, QFLX_EVAP_CAN,
               Q_over, Q_infl, Q_drain, Q_subl, Q_melt, Q_drain_perched]
    residual_against: "dS/dt"     # or a specific variable
    frame: "water_year"           # or "calendar"
  carbon:
    mode: "auto"                  # auto-detect BGC vs SP
    pools:  [LEAFC, LIVESTEMC, DEADSTEMC, FROOTC, LIVECROOTC, DEADCROOTC,
             TOTSOMC, TOTLITC, CWDC]
    fluxes: [GPP, AR, HR, ER, NEE, COL_FIRE_CLOSS, HRV_XSMRPOOL_TO_ATM]
    ch4:    [CH4_SURF_AERE_SOIL, CH4_SURF_DIFF_SOIL, CH4_SURF_EBUL_SOIL]
    residual_against: "TOTECOSYSC"
    frame: "calendar"
  energy:
    # TODO(verify) against ColumnDataType.F90 — variable names below are provisional
    radiation: [FSDS, FSR, FLDS, FIRE, FSA, FIRA]    # plot Rnet components
    turbulent: [FSH, EFLX_LH_TOT]
    ground:    [FGR]
    storage:   [HEAT_FROM_AC, URBAN_HEAT]            # TODO(verify): true soil heat storage term
    frame: "calendar"
    cumulative: false                                  # per user request

variables:
  groups:
    hydrology:   [H2OSOI, QRUNOFF, QDRAI, SNOWDP, ...]
    carbon_pools:  [...]
    carbon_fluxes: [...]
    energy:        [...]
    soil_state:    [...]
    vegetation:    [...]
  # populated by scraping ELM source + CLM 4.5 tech note; user can override
```

**Key design point (flagged by user):** balance equations are *data*, not code. The budget engine reads the YAML and assembles cumulative lines, closure residuals, and labels automatically. Users can add a new budget (e.g., nitrogen) by writing YAML only.

---

## 5. Module layout

```
elm_diagnostics/
├── __init__.py              # re-exports Run, Comparison, Report, WaterBalance, ...
├── io/
│   ├── run.py               # Run, Comparison, stream discovery
│   ├── units.py             # pint registry, flux/state classification
│   └── subgrid.py           # dov2xy detection, column/pft helpers
├── time/
│   ├── calendars.py         # water-year / calendar-year reindexing
│   └── integration.py       # time-bounds-aware cumulative integration
├── balances/
│   ├── base.py              # Balance base class (reads YAML spec, builds plots)
│   ├── water.py             # WaterBalance
│   ├── carbon.py            # CarbonBalance (BGC/SP auto-detect)
│   └── energy.py            # EnergyBalance (fluxes only; no cumulative)
├── plots/
│   ├── timeseries.py        # per-variable TS with climatology envelope
│   ├── seasonal.py          # seasonal cycle with spread
│   ├── anomaly.py           # annual anomalies
│   ├── histogram.py         # PDF / histogram
│   └── diurnal.py           # sub-daily only; skipped otherwise
├── report/
│   ├── build.py             # Report orchestrator
│   ├── templates/
│   │   ├── base.html.j2     # Base template with navigation
│   │   ├── section.html.j2  # Section page template
│   │   └── _section_content.html.j2  # Reusable section content
│   └── assets/              # CSS, JS for TOC sidebar
├── config/
│   ├── schema.py            # YAML schema validation (pydantic)
│   └── defaults.yaml
└── cli.py                   # click or typer entry point
```

---

## 6. Key APIs

### 6.1 Balances

```python
from elm_diagnostics import Run, WaterBalance, CarbonBalance, EnergyBalance

run = Run("/path/to/case/run")

wb = WaterBalance(run, year=2015, frame="water_year")
fig_cumulative, fig_decomposition = wb.plot()   # two subpanels per balance
wb.to_netcdf("wb_2015.nc")                       # save plotted arrays

# Or loop over all years
for fig_c, fig_d in wb.plot_all_years():
    ...
```

Each `Balance` subclass implements:
- `.components() -> dict[str, xr.DataArray]` — unit-normalized, time-aligned.
- `.cumulative() -> xr.Dataset` — one variable per component, cumulative over the frame.
- `.residual() -> xr.DataArray` — closure residual through the year.
- `.plot() -> tuple[Figure, Figure]` — `(cumulative_panel, decomposition_panel)` as per user spec (two subpanels per balance).

### 6.2 Report

```python
from elm_diagnostics import Report

Report(run, config="my_config.yaml").build("out/")
# or with a comparison:
Report(Comparison(base, exp)).build("out/")
```

Produces `out/index.html` (single page, TOC sidebar, thumbnails linking to full-size figures), `out/figures/*.png`, `out/data/*.nc`.

### 6.3 CLI

```
elm-diagnostics report PATH [--compare PATH2] [--out DIR] [--config YAML] \
                      [--verbose] [--debug] [--quiet]
elm-diagnostics balance {water,carbon,energy} PATH [--config YAML] [--out DIR]
elm-diagnostics plot VARNAME PATH [--kind timeseries|seasonal|anomaly|histogram]
```

Implemented with `typer` (cleaner than argparse, auto-generates `--help`).

---

## 7. Testing strategy

- **Framework:** pytest.
- **Synthetic fixtures:** a `tests/fixtures/synthetic_elm.py` module builds minimum-viable `xr.Dataset`s that mimic h0/h1 tapes with realistic dimension structure (time, lat, lon, column, pft, levgrnd), correct `cell_methods` attributes, `time_bounds`, and a cftime calendar. Use three flavors: single-point, 2×2 regional, multi-column sub-grid.
- **Closure tests:** for synthetic data constructed to close exactly, assert `|residual| < tol` at the end of each year for each balance. This is the single highest-value test category.
- **Snapshot tests for plots:** `pytest-mpl` for image-regression on a small set of canonical figures.
- **Config tests:** YAML schema validation round-trips, bad configs produce clear errors.

No CI in v1 (user request). Structure tests so `pytest` runs clean locally; add `.github/workflows/ci.yml` in v2.

---

## 8. Implementation phasing

1. **Phase 0** — Source-code reconnaissance (section 0). Output: confirmed variable lists in `defaults.yaml`.
2. **Phase 1** — `io/` + `time/` + units. Ship `Run`, `Comparison`, unit-aware integration, water-year reindexing. Tests for cadence detection and cumulative integration.
3. **Phase 2** — `balances/water.py` end-to-end (components → cumulative → decomposition → two-panel plot → NetCDF dump). Establishes the pattern.
4. **Phase 3** — `balances/carbon.py` and `balances/energy.py` by extension. BGC/SP auto-detect. Verify energy variables against `ColumnDataType.F90`.
5. **Phase 4** — General variable plots (`plots/`).
6. **Phase 5** — Sub-gridcell support (`by="column"|"pft"`).
7. **Phase 6** — `Report` (Jinja2 template, TOC sidebar, thumbnails).
8. **Phase 7** — CLI.
9. **Phase 8** — Docs (README, a `docs/` with one worked example using a real ELM single-point run).

---

## 9. Open questions / decisions deferred to implementation

- **Climatology envelope definition** — default to min/max band; p10/p90 and ±1σ are config options. Revisit once real data is plotted.
- **Energy storage term** — depends entirely on Phase 0 inspection of `ColumnDataType.F90`. The user flagged this; do not guess.
- **Ensemble support** — explicitly out of scope for v1; `Run` design should not preclude it (consider `Run` as potentially wrapping a list in v2).

---

## 10. v2 spec (captured now, deferred)

- **Observations overlays:** NEON tower fluxes (AmeriFlux AMF BASE files, ONEFlux processing), GRACE/GRACE-FO TWS anomalies, ERA5 reanalysis for forcing comparison, FLUXNET2015 subset. Add an `observations:` YAML block and an `ObsOverlay` mixin on plots.
- **CI:** GitHub Actions matrix (Python 3.10/3.11/3.12, ubuntu/macos), `pytest-mpl` image baselines committed, conda-forge feedstock.
- **Interactive report:** optional Plotly/Panel variant of the single-page report for pan/zoom on time series.
- **Ensemble/multi-site:** `Run` → `RunGroup` with faceted plots and ensemble envelopes.
- **ILAMB-style benchmarking:** comparison against reference datasets with scoring metrics. CLM diagnostics package and ILAMB are the references.
- **Nitrogen and phosphorus budgets:** add as YAML-defined balances once CNP coupling is in scope.

---

## 11. Reference implementations to consult

- **CLM diagnostics package** (NCAR, NCL-based) — structure of the standard diagnostic suite, variable groupings, and the balance closures as historically reported.
- **ILAMB** — benchmark/scoring patterns worth borrowing for v2 obs overlays.
- **`xclim`** — for idioms on cftime-aware climatological operations in xarray.
