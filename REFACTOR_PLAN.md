# REFACTOR_PLAN — elm-diagnostics cleanup (Phase 1 deliverable)

## Context

`elm-diagnostics` (~9.8k LOC in `elm_diagnostics/`, 30 modules) was largely LLM-generated. It works
(290 tests), but has heavy duplication, dead code, over-defensive error handling, and several latent
bugs. Goal: refactor for clarity/maintainability **without behavior change**, tests read-only,
public API preserved, each step one focused commit, suite green after every step.

Approved 2026-09-29. Work proceeds on branch `refactor/cleanup`, one commit per step, pausing
before every **high-risk** step. Bugs go to `REFACTOR_NOTES.md`; test additions/changes go to
`TEST_CHANGE_PROPOSALS.md` for approval.

Baseline commit: `9c30a53` (main, clean tree).

---

## 1. Package map

```
cli.py (typer)  ──► config.schema, io.run, balances.*, plots, report.build
report/build.py ──► balances.{water,energy,carbon}, plots.*, io.run, config.schema, PIL, jinja2
balances/base.py ─► io.run, io.subgrid, time.calendars, config.schema
balances/{water,carbon,energy}.py ─► base, time.integration, io.units(water), plots.subgrid_helpers(water)
plots/*.py ──────► io.run, config.schema, plots.{climatology,dimension_helpers,subgrid_helpers}
                   ⚠ timeseries/hovmuller import private `_plot_time` from balances.base (layering inversion)
plots/climatology ► time.calendars
io/run.py ───────► io.derived (lazy import, cycle-avoidance)
io/derived.py ───► io.units
config/schema.py ► defaults.yaml
```

| Module | LOC | Job |
|---|---|---|
| `io/run.py` | 816 | `Run` (stream discovery, lazy `open_mfdataset`, header index, LRU var cache, derivation fallback), `Comparison` |
| `io/derived.py` | 269 | derived vars registry (QFLX_EVAP_TOT, PRECT, TOTAL_SOIL_WATER) |
| `io/units.py` | 248 | unit aliases, classify flux/state, kg/m²→mm relabel |
| `io/subgrid.py` | 76 | sub-grid dim detection/validation |
| `time/calendars.py` | 195 | water year, year selection, climo window |
| `time/integration.py` | 187 | time-bounds dt, cumulative integral, storage change |
| `balances/base.py` | 245 | abstract `Balance`, year/window subsetting, caches, `_plot_time` |
| `balances/water.py` | 506 | water components/residual + 4 figures (single + faceted) |
| `balances/carbon.py` | 213 | carbon components/residual + 2 figures |
| `balances/energy.py` | 161 | energy components/residual + 2 figures |
| `config/schema.py` | 480 | pydantic models, YAML merge, balance-override validation |
| `plots/*.py` | 3.2k | timeseries, seasonal, anomaly, histogram, diurnal, hovmuller + helpers |
| `report/build.py` | 1942 | `Report`: sections, parallel plotting, stats tables, timings, HTML render |
| `cli.py` | 855 | `report`, `balance`, `plot` commands |

**Public API (must preserve):** top-level `__all__` (`Run, Comparison, WaterBalance, CarbonBalance,
EnergyBalance, Report`), `plots.__all__` (6 `plot_*`), `report.__all__`, CLI `elm-diagnostics =
elm_diagnostics.cli:app`. Conservatively also every non-underscore name in modules rendered by
`docs/api/*.rst` automodule (io.derived/subgrid/units, time.*, config.schema, plots.subgrid_helpers,
report.build, cli). **Test-coupled privates** (tests import/patch these, so keep names+signatures):
`cli._compute_max_year_from_files`, `cli._resolve_analysis_year_filter`,
`io.run._filter_stream_files_by_year`, `Run._open_stream/_variable_index/_auto_chunks_for_stream/
_tape_order/_stream_files/_chunk_target_mb`, `CarbonBalance._detect_bgc_mode`,
`Report._detect_git_version`, `report.build._ASSETS_DIR`.

---

## 2. Baseline

| Check | Result |
|---|---|
| `pytest tests/` | **290 passed**, 0 failed, 105 warnings, 11m35s (with coverage) |
| `ruff check elm_diagnostics/` (pinned 0.16.5 via `uvx`; local is 0.15.17) | clean |
| `ruff format --check elm_diagnostics/` | clean (30 files) |
| `mypy` | **not configured**; ad-hoc `mypy --ignore-missing-imports elm_diagnostics/` → 113 errors / 15 files (55 arg-type, 27 union-attr, 18 assignment) — mostly `sum()` → `int \| DataArray`, `Literal` narrowing, xarray kwargs typing |
| Type hints | 19/237 functions missing annotations (4 public: `water_year`, `day_of_year`, `plot_all_years`, `validate_depth_limits`) |
| LOC | 9,764 (package .py) |
| Image-comparison tests | **none** (`pytest-mpl` installed, no `mpl_image_compare`, no `tests/baseline/`) → plotting code guarded only by structural asserts |

Coverage (`--cov-branch`), **total 76.9%** (3755 stmts, 709 missed):

| Module | Cov | Notable gaps |
|---|---|---|
| config/schema | 95% | — |
| plots/subgrid_helpers, `__init__`s | 100% | — |
| plots/dimension_helpers | 88% | |
| report/build | 87.5% | sequential (`n_workers==1`) plot path 1534-1556, thumbnail fallback, error-stat branches |
| balances/carbon · energy · units · derived | 85–87% | |
| balances/base | 83% | `plot_all_years`, window edge cases |
| balances/water | 82% | faceted hide-axes, storage fallback (dead) |
| plots/hovmuller | 82% | |
| plots/histogram | 80% | |
| plots/timeseries | 78% | |
| cli | 75% | **non-quiet spinner paths** of `balance`/`plot` (600-679, 791-839), `--compare` loading |
| plots/climatology | 73% | |
| io/subgrid | 68% | dead helpers |
| plots/anomaly | 66% | Comparison/faceted branches |
| io/run | 66% | **`Comparison.get` (805-812) never run**, `tape_priority`, cadence fallback, dask-retry, year-filter warnings |
| plots/seasonal | 63% | Comparison + faceted branches |
| time/calendars | 59% | numpy-datetime paths, `day_of_year` (dead) |
| time/integration | 54% | no-bounds fallback `_estimate_dt_from_coords`, `_scalar_to_seconds`, W→J units |
| plots/diurnal | **39%** | most of single/faceted bodies (fixtures are monthly) |
| plots/colors | 0% | dead |

Key takeaway: **Comparison code paths are barely exercised anywhere** (Comparison.get uncovered → every plot's Comparison branch is untested).

---

## 3. Code smells (file:line)

### 3.1 Duplicated / near-duplicate helpers
- `_append_long_name_line` ×6: plots/{anomaly:50, diurnal:80, histogram:51, hovmuller:34, seasonal:44, timeseries:47}
- `_format_var_ylabel` ×4: plots/{anomaly:45, diurnal:75, seasonal:39, timeseries:42}
- `_squeeze_spatial` ×3 (anomaly:24, diurnal:25, histogram:24) duplicates `dimension_helpers.squeeze_spatial_dims:23`; same loop again in `balances/base.py:116`
- `_is_index_like`: hovmuller:41 ≡ dimension_helpers:50
- `_legend_level_indices`: timeseries:34 vs seasonal:51 (equivalent output); `_plot_multilevel_lines` (timeseries:54) vs `_plot_multilevel_seasonal_lines` (seasonal:61) near-dup
- `compute_individual_year_seasonal_cycles_faceted` (climatology:173) is byte-for-byte the non-faceted body; `facet_dim` unused
- nested `_check_subdaily` ×2 (diurnal:164, 346); third sub-daily detector in `report/build.py:1289`
- year extraction from time values ×4: `calendars._get_year:27`, `base.py:151-157`, `build.py:371-379`, plus analysis-window masking logic dup'd in `base._select_year:121-179` and `build._apply_analysis_window:348-404`
- time-bounds name detection ×3: `run._TIME_BOUNDS_NAMES:29` (defined, then ignored in `_infer_cadence:52-56`), `integration.get_time_deltas:37-41`
- `CFDatetimeCoder` try/except ×2: run.py:422-427, 499-503; cadence sort key ×2: run.py:518-526, 578-587; monthly/annual threshold ×2: run.py:70-74, 104-108
- vertical-sum-then-mm ×3: `derived.aggregate_vertical_storage:103-132`, `water.py:84-107`, `water.py:161-178`
- flux→cumulative unit string logic ×2 (differ!): `units.convert_flux_to_cumulative_units:153` vs `integration.cumulative_integral:144-153`
- Run construction ×5 with/without spinner (cli.py:419-441, 453-474, 607-629, 798-820); verbose/quiet check + except-block ×3
- 3 near-identical balance section blocks in `build._build_balance_sections:755-1011`; stats error-row dict ×3 (1129, 1166, 1215)
- `_Section.add_figure` ≡ `_Subsection.add_figure`; slug regex ×2 (build.py:106, 198)
- faceted-plot preamble (validate/get units/facet fig/hide axes/suptitle) ×6 plot modules; `by`+`ax` guard ×5
- Hovmuller run vs comparison axis-prep/warnings block dup (hovmuller.py:251-305 vs 344-406)
- water `_plot_single` vs `_plot_faceted` panel drawing (water.py:211-506)
- `_USER_CONFIG_PATH` (schema.py:23) ≡ `_DEFAULT_USER_CONFIG_PATH` (build.py:59)
- `required_subkeys` in `load_config` (schema.py:439-465) hand-copies pydantic model field names
- carbon `flux_colors` (carbon.py:147) duplicates unused `plots/colors.get_balance_colors`

### 3.2 Dead code
- Unreferenced functions: `calendars.day_of_year:158`, `units.get_registry:105`, `subgrid.has_subgrid:38`, `subgrid.get_subgrid_level:71`, `Balance.plot_all_years:229` (also mutates `self.year`), `plots/colors.py` entirely (`lighten_color`, `get_balance_colors`)
- `run._build_open_kwargs:402-409` initial kwargs overwritten; `setdefault("compat"/"join")` at 438-439 unreachable
- `run._extract_casename:115` `if parts:` always true
- `water._storage_decomposition_components:152-183` fallback recompute unreachable (components() always sets that cache)
- `build.py:1509-1511,1526` `has_var = True`/`var is None`; `build.py:451` `thumb_path = full_path` never used; `build.py:384-387` impossible None checks; `hasattr(run,"_variable_cache")` ×4 always true; pil_kwargs `TypeError` fallbacks (mpl≥3.7 pinned)
- `_create_and_save_plot_worker(section_title=…)` unused param; `aggregate_vertical_storage(vertical_dim=…)` unused param (public)
- `convert_flux_to_cumulative_units` second tuple element always `1.0`
- `derive_variable` not-registered branch unreachable from `Run.get` (can_derive checked first)
- Unused config options: `plots.style.palette`, `report.title_template`, `report.comparison.*`, `report.metadata.show_configuration`, `report.performance.{chunk_size_mb,lazy_evaluation,progress_verbosity,slow_operation_threshold_seconds}`, `balances.water.{et_components,residual_against}`, `balances.carbon.ch4`, `balances.energy.{storage,errors,cumulative}` (the balance ones are *required* by `load_config` full-block override validation)
- Tracked junk: `elm_diagnostics/cli.py.bak` (**ships in wheel**), `run/` (CIME/ATS run dir), `test_plots/` (PNG output), `test_plots_demo.py` (hardcoded `/Users/rfiorella/Downloads/run`)

### 3.3 Over-defensive / swallowed errors
- `run._auto_chunks_for_stream:363` and `_cheap_cadence:507` `except Exception` → silent fallback
- `run._open_stream:451` catches all, string-matches "dask"
- `build._detect_git_version:289`, `_diagnostics_config_yaml:300`, `_read_lnd_in_file:321`, `_save_figure:438` broad catches (thumbnail fallback)
- report sections/stats/netCDF export `except Exception` (intentional resilience per ruff BLE001 note — keep, but narrow where cheap)
- `carbon._compute_components:84-107` / `energy:45-50` silently `pass` on KeyError (water logs a warning — inconsistent)
- `time.calendars.day_of_year:184-193` blanket except (dead anyway)
- `diurnal._median_time_step_hours:71` blanket except
- CLI `except Exception` also catches `typer.Exit` (bug B2)

### 3.4 Single-implementation / needless indirection
- `run._lazy_align` one-line wrapper over `xr.align`
- `derived.can_derive` + parallel dicts `DERIVABLE_VARS`/`DERIVABLE_REQUIREMENTS` (must be kept in sync by hand)
- `_seasonal_stats`/`_diurnal_stats` thin wrappers over `compute_climo_stats`
- `Report._cached_get_for_var` monkeypatches `run.get` (shared across worker threads)
- `Balance` ABC is justified (3 impls) — keep

### 3.5 Wrong / stale comments & docs
- build.py:889, 975 "doesn't have to_netcdf yet" — `Balance.to_netcdf` exists (base.py:222)
- units.py:237 "mm H2O variant → mm" guards `mm/s`; `get_available_years` "complete years" (returns all)
- `plot_diurnal` docstring promises `ValueError` for non-sub-daily; it draws a text panel
- `plot_anomaly` "difference (experiment - base)" — actually difference of each run's anomalies
- `Balance._get_var` comment "preserves sub-gridcell dim" — code does nothing for `by`
- CLI `balance` docstring "two-panel plots" (water produces 4)
- CLAUDE.md: "161 tests" (290), "always use pint-xarray" (never imported), balances "support `by` faceting" (carbon/energy ignore it)
- `_KNOWN_STATES` lists `hc_soi`/`hc_soisno`, CLAUDE.md says ELM names are `HC`/`HCSOI`

### 3.6 Naming / magic numbers
- `-1` sentinel for "earliest/latest year" (config + calendars + build `or -1`)
- 30 s slow threshold hardcoded ×3 (build.py:1448, 1521) while `performance.slow_operation_threshold_seconds` exists unused; `>1000 → seconds else days` heuristic ×2 (integration.py:80, 97); `dpi=150` in CLI ignores `plots.style.dpi`; LRU size 15; `min_points` 12/24
- vertical dims lists differ: derived `[levgrnd, levsoi, levdcmp, levlak]`, water `(levgrnd, levsoi)`, hovmuller `_DEPTH_DIMS={levgrnd,levsoi}`
- subgrid dim literals repeated instead of `io.subgrid._SUBGRID_DIMS` (subgrid_helpers.py:168)
- f-string logging (`logger.info(f"...")`) in cli.py / build.py

### 3.7 print-as-logging, hardcoded paths, scattered config
- `Report` progress via `print()` (build.py:474-527, 650) — library code writing stdout
- config loaded 3–4× per CLI command (`_get_run_strict_combine`, `_get_run_chunk_options`, `_resolve_analysis_year_filter`, `load_config` again, then `Report`/`Balance` load again)
- defaults duplicated in `defaults.yaml` and pydantic defaults (two sources of truth)
- `Report` reaches into `Run` privates (`_tape_order`, `_variable_cache`, `bounds_dataset`)

### 3.8 Long functions (≥150 lines)
`seasonal._plot_seasonal_faceted` 334, `build._build_balance_sections` 263, `seasonal._plot_seasonal_single` 261, `cli.report` 195, `water._plot_faceted` 180, `build._build_variable_sections` 169, `cli.balance` 167, `cli.plot` 163, `diurnal._plot_diurnal_single/faceted` 159/156. `report/build.py` (1.9k) mixes orchestration, stats, timing, HTML render.

### 3.9 Dependencies
- Declared, never imported: `pint-xarray`; extras `interactive` (plotly), `maps` (cartopy)
- Imported, not declared: `PIL` (Pillow; transitive via matplotlib)
- `pytest-cov` not in `dev` extras; local ruff 0.15.17 ≠ pinned 0.16.5
- sdist has no excludes → ships `workspace/`, `run/`, `test_plots/` (CLAUDE.md requires workspace excluded); no `MANIFEST.in` (hatch ignores it anyway)

---

## 4. Bugs found (→ `REFACTOR_NOTES.md`, NOT fixed)

| # | Location | Symptom | Suggested fix |
|---|---|---|---|
| B1 | cli.py:123-126, 695, 769-783 | `plot --kind diurnal` advertised (help + completion) but rejected: "Unknown plot kind" (**reproduced**) | add `plot_diurnal` to `plot_funcs` |
| B2 | cli.py:510, 680, 846 | `typer.Exit` (a RuntimeError) raised inside `try` is caught by `except Exception` → extra "Error: " + "Run with --debug" after every validation error (**reproduced**) | `except typer.Exit: raise` before generic handler |
| B3 | schema.py:353-362 | group `hovmuller:` block's *default* fields override user's global settings (global `quantile` → SOILLIQ gets `full_range`) (**reproduced**) | merge only `model_fields_set` |
| B4 | units.py:58,143 | `_FLUX_UNIT_PATTERNS` contains `"s"` → any unit containing letter s (`unitless`, `degrees`) classified flux (**reproduced**) | match `/s`, `s-1`, `s**-1` tokens |
| B5 | schema.py:405-409 | `load_config("missing.yaml")` silently returns defaults | raise `FileNotFoundError` |
| B6 | run.py:641-647 | `get(var, tape="h1")` caches under bare `var`; later `get(var)` returns h1 data regardless of priority; `_cache_variable` never refreshes existing key | key cache by `(var, tape)` |
| B7 | build.py:1343-1416, 1559 | parallel plot workers (default 2 threads) use pyplot global state; `_close_new_figures` in one worker can close another's figure; `run.get` monkeypatched while threads run | per-thread `Figure()` objects or process pool; no global figure sweeps in workers |
| B8 | build.py:694 | `build()` returns `html_paths[0]` — not index.html when metadata section disabled; `IndexError` when all sections disabled | return `outdir/"index.html"` / handle empty |
| B9 | build.py:540-545 vs 1465-1467 | progress total counts enabled groups with no active plot types, which are skipped silently → "[report k/N]" never reaches N | filter same way |
| B10 | timeseries.py:443-453 | climatology envelope drawn on `twinx()` with independent y-scale and hidden ticks → envelope not on data scale | draw on `ax` |
| B11 | water.py:130-137 | if no inputs/outputs/dS resolved, `sum()` → `int 0` → `AttributeError` on `.attrs` | guard / raise informative error |
| B12 | carbon.py:105, 119-127 | residual hardcodes GPP/ER/TOTFIRE/WOOD_HARVESTC/"dTOTECOSYSC" ignoring configured `fluxes`/`residual_against`; can return `int` | derive from config |
| B13 | build.py:1192 | carbon stats: `"cumulative" in name` never true; AR/ER/TOTFIRE cumulative series shown as time-mean of cumulative | treat all fluxes as final values |
| B14 | integration.py:144-153 vs units.py:153 | two different flux→cumulative unit rules (e.g. `"W/m^2"` → `"J/m^2"` vs `"J/m**2"`) | single helper |
| B15 | carbon.py:57-59 | `_detect_bgc_mode` materialises full GPP/LEAFC (`.values`) — memory blow-up on large runs | reduce lazily |
| B16 | energy.py/carbon.py `plot` | `by=` accepted by `Balance` but ignored (no faceting); docs claim support | implement or reject `by` |
| B17 | build.py:367-368 | `analysis_year_min or -1` treats year 0 as unset | `is None` checks |

Docs-only: diurnal `ValueError` claim, anomaly comparison semantics, `get_available_years` "complete", `aggregate_vertical_storage(vertical_dim)` ignored, stale CLAUDE.md facts.

---

## 5. Refactoring sequence (low → high risk)

Each step = one commit (`refactor(<area>): …`), then: full pytest, `uvx ruff@0.16.5 check` + `format --check`, and the out-of-tree **golden check** (see §8). Formatting-only changes never mixed with logic. Any step touching Comparison branches is high risk regardless of module % (those branches are unexercised).

| # | Step | Files | Coverage | Risk |
|---|---|---|---|---|
| 0 | Branch `refactor/cleanup`; add `REFACTOR_PLAN.md`, `REFACTOR_NOTES.md` (bugs §4), `TEST_CHANGE_PROPOSALS.md` | docs only | — | none |
| 1 | Repo hygiene (decided): `git rm elm_diagnostics/cli.py.bak`, `git rm -r run/ test_plots/`, `git mv test_plots_demo.py workspace/`; add `[tool.hatch.build.targets.sdist] exclude = ["workspace"]` | pyproject, tree | n/a | low |
| 2 | Mechanical imports: hoist function-local imports of already-available modules (`numpy` in base.py/build.py, `warnings` in dimension_helpers, `gc`/`shutil` in build, `convert_water_to_mm` in water/derived); lazy `%s` logging instead of f-strings in `logger.*` | build, base, water, derived, dimension_helpers, cli | 75–88% | low |
| 3 | Dead internal code: private §3.2 items (kwargs overwrite, `if parts`, unreachable storage fallback, `has_var`, `thumb_path` local, None checks, `hasattr`s, pil_kwargs fallbacks, unused worker param); fix stale comments §3.5 | run, water, build, units | run 66% (`_build_open_kwargs` default path covered), water 82%, build 87% | low–med |
| 4 | Shared plot helpers → `plots/_common.py` (ylabel, long-name title, legend indices, `by`/`ax` guard, faceted preamble, `check_subdaily`); `_squeeze_spatial`→`squeeze_spatial_dims`; `_is_index_like` single copy; faceted climatology fn becomes alias | plots/* | 39–88%; Comparison branches ~0% | **high** |
| 5a | Neutral `_plot_time` (move to `time/plotting.py`, re-export from `balances.base`); `find_bounds_var()`/`TIME_BOUNDS_NAMES` shared by run & integration; `_cf_decode_kwargs()`, `_cadence_seconds()` in run | time/, balances/base, io/run | run 66% (cadence fallback + `tape_priority` uncovered), integration 54% | **high** |
| 5b | Single year-extraction/window-mask helper in `time.calendars`, used by `base._select_year` and `build._apply_analysis_window` | calendars, base, build | calendars 59%, base 83%; `test_analysis_window_regression` covers main path | med |
| 6 | Config: derive balance `required_subkeys` from `Model.model_fields`; build.py imports `_USER_CONFIG_PATH` from schema; additive `Run.clear_cache()`/`Run.tapes` so Report stops touching privates | config/schema, report/build, io/run | schema 95% | low |
| 7 | CLI: one `load_config` per command (keep `_resolve_analysis_year_filter(config_path, …)` signature as wrapper), `_open_run(...)` replacing 5 Run blocks, shared verbosity check + error handler with byte-identical output/exit codes | cli | 75%; **non-quiet `balance`/`plot` paths and `--compare` uncovered** | **high** |
| 8 | Water balance: one storage-aggregation loop feeding `dS` + decomposition; panel helpers shared by `_plot_single`/`_plot_faceted`; carbon uses `get_balance_colors()` | balances/water, carbon | 82–87%; plot content asserted weakly | **high** |
| 9 | Report: table-driven `_build_balance_section(spec)` preserving per-balance differences (water `to_netcdf` unguarded; energy/carbon components-only, guarded); `_error_stats(e)`; shared `add_figure`/`_slug()` | report/build | 87.5%; balance sections well covered, sequential plot path not | **high** |
| 10 | Hovmuller: shared `_prepare_axis(...)` + `_color_kwargs` for run/comparison | plots/hovmuller | 82%; comparison path partly | **high** |
| 11 | Seasonal/diurnal/timeseries/anomaly single-vs-faceted: per-axes draw functions used by both paths | plots/* | seasonal 63%, diurnal **39%**, anomaly 66% | **high** |
| 12 | Type hints on touched public functions; propose `[tool.mypy]` (see Open Q4) | touched files | — | low |
| 13 | Wrap-up: `REFACTOR_NOTES.md` per-module changes, before/after LOC, lint, mypy count, coverage; confirm `git diff 9c30a53 -- tests/` empty | docs | — | none |

High-risk steps pause for your go-ahead before starting.

---

## 6. Proposed breaking changes (not done without approval)
1. Remove dead public functions: `day_of_year`, `get_registry`, `has_subgrid`, `get_subgrid_level`, `Balance.plot_all_years`, `compute_individual_year_seasonal_cycles_faceted`, `plots/colors.lighten_color`.
2. Remove unused config options (§3.2) — and drop them from the full-block override requirement.
3. `aggregate_vertical_storage`: drop ignored `vertical_dim` param; `convert_flux_to_cumulative_units`: return just the unit string.
4. `Report` progress: replace `print()` with a module logger (or `progress_callback`), CLI renders it — changes stdout of library users.
5. Dependencies: drop `pint-xarray` and extras `interactive`/`maps`; declare `pillow`; add `pytest-cov` to `dev`.
6. Collapse `defaults.yaml` duplicates of pydantic defaults (keep only `variable_groups`) — merged result identical, but file content changes for users who read it.

## 7. Open questions
1. ~~Repo junk~~ — decided: move demo to `workspace/`, remove `run/` and `test_plots/`.
2. Step 7 would emit the "balances override" `UserWarning` once instead of 3–4× per CLI run — acceptable?
3. ~~Safety net~~ — decided: out-of-tree golden script now; T1–T3 go in `TEST_CHANGE_PROPOSALS.md` awaiting per-entry approval.
4. mypy: add `[tool.mypy]` at default strictness with a per-module ignore list and ratchet, or leave unconfigured?
5. Should `CLAUDE.md` stale facts be corrected as part of wrap-up?

## 7b. `TEST_CHANGE_PROPOSALS.md` initial entries (new tests only; no existing test judged wrong)
- **T1 plot characterization**: `tests/test_plot_characterization.py` — fingerprint (titles, labels, line xy arrays rounded, legend texts) for 6 plot kinds × Run/Comparison × `by∈{None,"column"}` on existing fixtures; guards steps 4, 8, 10, 11.
- **T2 report characterization**: build report on fixture, assert section filenames, figure basenames, stats-table rows (normalized), and data/*.nc variable sets; guards step 9.
- **T4 Comparison + sub-daily coverage**: `Comparison.get` alignment (intersect/union) on two fixture Runs; diurnal plot on a synthetic hourly fixture (diurnal at 39%); `get_time_deltas` no-bounds fallback (integration 54%).
- **T5 CLI non-quiet paths**: `balance`/`plot` without `--quiet`, and `report --compare` (spinner branches uncovered).
- **T3 CLI error paths**: pin current stdout/exit codes for unknown kind, missing path, verbose+quiet (documents B1/B2 current behavior so later fixes are deliberate).

## 8. Verification (every step)
- `DASK_SCHEDULER=synchronous HDF5_USE_FILE_LOCKING=FALSE pytest tests/ -q` — same pass/fail set as baseline.
- `uvx ruff@0.16.5 check elm_diagnostics/ && uvx ruff@0.16.5 format --check elm_diagnostics/`.
- **Golden check (scratchpad, not in repo)**: script run at baseline and after each step on the Oak Harbor fixture + synthetic multicolumn fixture: (a) for every `plot_*` × {Run, Comparison} × {by=None, by="column"}: dump figure fingerprint (axes titles/labels, line/collection data arrays, legend texts, suptitle); (b) balances `components()/residual()` → netCDF + `plot()` fingerprints; (c) `Report.build` HTML with timestamps/timings/host stripped + data/*.nc; (d) CLI stdout/exit codes for `report`, `balance`, `plot`, error paths. Diff must be empty.
- After step 13: `git diff 9c30a53 -- tests/` empty.
