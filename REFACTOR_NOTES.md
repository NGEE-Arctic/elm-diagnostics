# Refactor notes

Companion to `REFACTOR_PLAN.md`. Baseline commit: `9c30a53`.

## Bugs found (not fixed — behavior preserved)

Each entry: location, symptom, suggested fix. None of these are fixed on this branch; fixes
belong in separate, explicitly approved commits.

| # | Location | Symptom | Suggested fix |
|---|---|---|---|
| B1 | `cli.py` `complete_plot_kind`, `plot` help text, `plot_funcs` | `elm-diagnostics plot VAR PATH --kind diurnal` is advertised (help + shell completion) but rejected with "Unknown plot kind: diurnal". Reproduced. | Add `"diurnal": plot_diurnal` to `plot_funcs`. |
| B2 | `cli.py` `report`/`balance`/`plot` `except Exception` | `typer.Exit` (subclass of `RuntimeError`) raised inside the `try` for validation errors is caught by the generic handler, so the user sees an extra `Error: ` line and "Run with --debug for full traceback" after the real message. Exit code is still 1. Reproduced. | Add `except typer.Exit: raise` before `except Exception`. |
| B3 | `config/schema.py` `Config.get_variable_group_hovmuller_config` | A group-level `hovmuller:` block is a full `HovmullerConfig` with defaults filled in, so every non-`None` default (e.g. `color_limit_method="full_range"`) overrides the user's global `plots.hovmuller` setting. Global `quantile` → `SOILLIQ` (hydrology group) gets `full_range`. Reproduced. | Merge only `group_config.hovmuller.model_fields_set`. |
| B4 | `io/units.py` `_FLUX_UNIT_PATTERNS`, `classify_variable` | Pattern set contains bare `"s"`, so any unit string containing the letter s (`"unitless"`, `"degrees"`) is classified as a flux. Reproduced. | Match rate tokens (`/s`, `s-1`, `s**-1`) instead of substring `"s"`. |
| B5 | `config/schema.py` `load_config` | An explicit path that doesn't exist is silently ignored and defaults are returned (the CLI validates first, the Python API does not). | Raise `FileNotFoundError` for an explicit missing path. |
| B6 | `io/run.py` `Run.get` / `_cache_variable` | `get(var, tape="h1")` caches under the bare name `var`; a later `get(var)` returns the h1 array regardless of tape priority. `_cache_variable` also never refreshes an existing key. | Key the LRU cache by `(varname, tape)`. |
| B7 | `report/build.py` `_create_and_save_plot_worker`, `_build_variable_sections` | Parallel plot workers (default 2 threads) share pyplot global state; `_close_new_figures` in one worker can close a figure another worker is still drawing; `_cached_get_for_var` monkeypatches `run.get` while threads run. | Use explicit `Figure()` objects per worker, or a process pool; drop global figure sweeps inside workers. |
| B8 | `report/build.py` `Report.build` | Returns `html_paths[0]`, which is not `index.html` when the metadata section is disabled, and raises `IndexError` when every section is disabled. | Return `outdir / "index.html"` or handle the empty case explicitly. |
| B9 | `report/build.py` `_planned_progress_sections` vs `_build_variable_sections` | The progress total counts enabled groups that have no active plot types, but those groups are skipped without an announcement, so "[report k/N]" never reaches N. | Apply the same filter in both places. |
| B10 | `plots/timeseries.py` `_add_climatology_envelope` | The envelope is drawn on `ax.twinx()` with its own y-scale and hidden ticks, so it isn't on the data's scale. | Draw on `ax`. |
| B11 | `balances/water.py` `_compute_residual` | If no inputs, outputs, or dS resolve, `sum()` returns int `0`, then `.attrs` raises `AttributeError`. | Guard and raise an informative error. |
| B12 | `balances/carbon.py` `_compute_components` / `_compute_residual` | The residual hardcodes GPP/ER/TOTFIRE/WOOD_HARVESTC and the key `"dTOTECOSYSC"`, ignoring the configured `fluxes`/`residual_against`; it can also return int `0`. | Derive the terms from config. |
| B13 | `report/build.py` `_compute_carbon_balance_stats` | `"cumulative" in name.lower()` never matches a component name, so cumulative AR/ER/TOTFIRE/WOOD_HARVESTC series are reported as the time-mean of a cumulative curve (only GPP/NEE/HR get final values). | Report final values for all cumulative fluxes. |
| B14 | `time/integration.py` `cumulative_integral` vs `io/units.py` `convert_flux_to_cumulative_units` | Two different flux→cumulative unit rules (`"W/m^2"` → `"J/m^2"` vs `"J/m**2"`). | One shared helper. |
| B15 | `balances/carbon.py` `_detect_bgc_mode` | Loads the full GPP/LEAFC arrays (`.values`) just to test for all-NaN/all-zero, which can blow memory on long runs. | Reduce lazily (`.isnull().all()` etc.). |
| B16 | `balances/energy.py`, `balances/carbon.py` `plot` | `by=` is accepted (and validated) by `Balance` but ignored when plotting; docs say all balances support faceting. | Implement faceting or reject `by`. |
| B17 | `report/build.py` `_apply_analysis_window` | `self.analysis_year_min or -1` treats year 0 as unset. | Use `is None` checks. |
| B18 | `plots/anomaly.py` `_annual_anomaly` / `_plot_anomaly_single` | Any variable with an extra non-time dim (e.g. multi-column `RAIN`, or `SOILLIQ` levels) crashes with `ValueError: The truth value of an array with more than one element is ambiguous` when `by=None`; the long-term mean collapses all dims but the anomalies stay 2-D. Found by the golden check. | Reduce or facet extra dims before building bar colors, or raise an informative error. |
| B19 | `balances/base.py` `_plot_time` / `_PLOT_TIME_CACHE` | The converted-dates cache is keyed by `(id(time_data), len(time_data))` and holds no reference to the array, so after GC a new time array of the same length can reuse the id and get another array's dates. Balance plots then draw lines against the wrong x values. Found by the golden check: identical inputs produced different x-data between runs (e.g. water storage decomposition for `analysis_year_max=2001` vs `2001–2002`). | Drop the cache, or key it on the array object itself (e.g. keep a reference / use a `WeakKeyDictionary` on an object that supports weakrefs). |

Documentation-only inaccuracies: `plot_diurnal` docstring promises a `ValueError` for non-sub-daily
data (it draws a text panel); `plot_anomaly` says it plots experiment − base (it plots the
difference of each run's own anomalies); `get_available_years` says "complete years" (returns all
years); `aggregate_vertical_storage(vertical_dim=...)` is ignored; CLAUDE.md says 161 tests (290),
says pint-xarray is used (never imported), and says all balances support `by` faceting.

## Verification method

Every step: full `pytest tests/` (290 passed each time), `ruff check` + `ruff format --check`
with the pinned ruff 0.16.5, and an out-of-tree golden fingerprint (scratch script, not in the
repo) comparing a baseline worktree at `9c30a53` against the working tree: figure contents for
all plot kinds × Run/Comparison × faceting, balance components/residuals/netCDF, full report
HTML + data files, CLI stdout/exit codes, and helper-function outputs (~31k lines). Diff was
empty for every committed step.

## Changes by step

| Step | Commit | Change |
|---|---|---|
| 0 | `237e2e7` | Plan, notes, test proposals |
| 1 | `b0f2584` | Removed `cli.py.bak` (shipped in wheel), `run/`, `test_plots/`; moved demo script to `workspace/`; sdist excludes `workspace/` |
| 2 | `75ae111` | Hoisted redundant function-local imports; %-style logging args |
| 3 | `900750a` | Dead code out of `io.run`, `balances.water`, `report.build`; stale comments/docstrings fixed |
| 6 | `f104c74` | Balance-override required keys derived from models; `Run.tapes` / `Run.clear_variable_cache()` |
| 5b | `88b6112` | `time.calendars.year_window_mask()` shared by `Balance` and `Report` |

Remaining (all high risk, awaiting go-ahead): 4, 5a, 7, 8, 9, 10, 11; then 12–13.
