# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`elm-diagnostics` is a Python package for budget-closure diagnostics of E3SM Land Model (ELM) output. It validates water, carbon, and energy budgets by computing cumulative balances, checking closure residuals, and generating comprehensive HTML reports with plots.

**Key features:**
- Automatic variable derivation (e.g., computing `QFLX_EVAP_TOT` from components if missing)
- Vertical aggregation of 3D soil variables (`SOILLIQ`, `SOILICE`)
- Unit-aware flux-to-cumulative integration using `pint`
- Water year support with configurable start month
- Sub-gridcell support (column, PFT, landunit faceting)
- HTML report generation with thumbnails, lightbox modal, and statistics tables

## Architecture

### Core Components

```
elm_diagnostics/
├── io/              # Data loading and preprocessing
│   ├── run.py       # Run and Comparison classes: auto-discover history streams
│   ├── derived.py   # Compute missing variables (e.g., QFLX_EVAP_TOT)
│   ├── units.py     # Unit-aware integration using pint
│   └── subgrid.py   # Sub-gridcell dimension handling
├── balances/        # Budget balance computations
│   ├── base.py      # Abstract Balance class
│   ├── water.py     # WaterBalance
│   ├── carbon.py    # CarbonBalance
│   └── energy.py    # EnergyBalance
├── time/            # Time handling
│   ├── calendars.py # Water year, year selection
│   └── integration.py # Time-bounds-aware flux integration
├── plots/           # Plotting functions
│   ├── timeseries.py, seasonal.py, anomaly.py, ...
│   ├── hovmuller.py # Depth × time heatmaps
│   └── subgrid_helpers.py # Faceting logic
├── report/          # HTML report generation
│   └── build.py     # Report class: thumbnails, lightbox, statistics
├── config/          # Configuration management
│   ├── schema.py    # Pydantic models for YAML config
│   └── defaults.yaml # Default balance definitions
└── cli.py           # Typer CLI with rich progress indicators
```

### Workspace Directory

The `workspace/` directory is a holding area for specialized or in-progress analyses that `elm-diagnostics` does not currently support. This includes:
- Exploratory analysis notebooks
- Experimental plotting or diagnostic functions
- Custom analysis scripts for specific research questions
- Work-in-progress features being prototyped before integration into the main package

The workspace is **outside the core Python package** and not part of the installed distribution. Files here are local to the repository and should not import from or depend on being imported by the main `elm_diagnostics/` package structure. **The workspace folder must never be bundled in Python package releases** — verify that `MANIFEST.in` and `pyproject.toml` exclude it.

Use `workspace/` for:
- Quick one-off analyses that don't warrant a full package feature
- Prototyping new balance types or plot kinds before formalizing
- Project-specific diagnostics that aren't generalizable
- Testing ideas that may or may not make it into the package

Do NOT use `workspace/` for:
- Core package functionality (belongs in `elm_diagnostics/`)
- Tests (belongs in `tests/`)
- Documentation (belongs in `docs/`)

### Data Flow

1. **Load**: `Run` class auto-discovers `*.elm.h*.nc` files, groups by history tape (`h0`, `h1`, ...), lazy-loads with `xarray.open_mfdataset`
2. **Derive**: If variable missing, `derived.py` computes it (e.g., `QFLX_EVAP_TOT = QSOIL + QVEGE + QVEGT`)
3. **Aggregate**: 3D soil variables (`levgrnd` dimension) summed vertically
4. **Integrate**: Fluxes converted to cumulative using time bounds via `pint-xarray`
5. **Balance**: Components grouped as inputs/outputs/storage, residual computed
6. **Plot**: Matplotlib figures for each variable and balance
7. **Report**: HTML with thumbnails, lightbox modal, and statistics tables

### Key Classes

- **`Run`**: Lazy-loads ELM history files, provides `.get(varname)` with auto-derivation
- **`Comparison`**: Holds base and experiment runs, computes deltas
- **`WaterBalance`, `CarbonBalance`, `EnergyBalance`**: Compute balance components, residuals, and plots
- **`Report`**: Generates comprehensive HTML reports with figures and data exports
- **`Config`**: Pydantic model for user config (defaults merge from `~/.config/elm-diagnostics/config.yaml`)

### Critical Design Points

**Variable Name Corrections (Phase 0):**
All variable names verified against E3SM IM1 ELM source (`/code/E3SM/IM1/components/elm/src/`). Key corrections:
- `QFLX_EVAP_TOT` is marked `default='inactive'` in ELM, must compute from `QSOIL + QVEGE + QVEGT`
- `QSNWCPICE` is NOT sublimation (it's excess snow removal/runoff), removed from ET outputs
- Energy: `HC` and `HCSOI` (not `hc_soisno`), both marked `default='inactive'`
- Carbon: `TOTFIRE` (not `COL_FIRE_CLOSS`), `WOOD_HARVESTC` (not `HRV_XSMRPOOL_TO_ATM`)

**Vertical Aggregation:**
`SOILLIQ` and `SOILICE` have `levgrnd` dimension (15 levels). Must sum over depth before balance computations.

**Vertical Dimension Handling (Plotting):**
- Soil variables with `levgrnd` dimension (15 levels) can be limited via config for clearer visualization
- `max_depth_m`: physical depth limit in meters (e.g., 3.5) - limits by actual depth coordinate
- `max_levels`: layer count limit (e.g., 10 for hydrologically active zone) - limits by index
- **Group-specific config**: `hydrology` variable group has `max_levels: 10` by default (hydrologically active zone)
- Other groups (e.g., `soil_state` with TSOI) use global config (null = all levels)
- Can override per-group via `variable_groups.<group>.hovmuller.max_levels` in user config
- `max_levels` and `max_depth_m` are mutually exclusive - only one can be set at a time
- Applies to hovmuller and timeseries multilevel plots

**Time Handling:**
- Monthly h0 files use `noleap` calendar
- Integration uses `time_bounds` (shape `(time, hist_interval)`) for accurate flux-to-cumulative
- Water year support: configurable start month (default October)

**Unit System:**
`pint-xarray` for unit-aware operations. Fluxes in `mm/s`, storage in `mm`, integration to cumulative `mm`.

**Sub-gridcell:**
For runs with `dov2xy = .false.`, all plots and balances support faceting via `by="column"`, `by="pft"`, or `by="landunit"`.

## Development Commands

### Installation
```bash
pip install -e ".[dev]"          # Core + development dependencies
pip install -e ".[all]"          # Include dask, plotly, cartopy
```

### Testing
```bash
pytest tests/                    # Run all tests (161 tests)
pytest tests/test_water_balance.py -v  # Specific module
pytest -k "sub_gridcell"         # Keyword filter
pytest --mpl                     # Include image comparison tests
```

**Test data:** Real ELM output in `tests/fixtures/data/` (Oak Harbor single-point simulation, Oct 2000 - Dec 2001).

### Code Quality
```bash
# No linter configured yet; use project conventions
python -m pytest tests/         # Tests enforce correctness
```

### CLI Usage
```bash
elm-diagnostics report /path/to/elm/output            # Full report
elm-diagnostics balance water /path/to/elm/output     # Water balance only
elm-diagnostics plot GPP /path/to/elm/output --kind seasonal  # Variable plot
elm-diagnostics --help                                 # Full help
```

### Configuration
User config at `~/.config/elm-diagnostics/config.yaml` (optional). Defaults in `elm_diagnostics/config/defaults.yaml`.

**Warning:** Balance definitions are intentionally internal (schema defaults). Overriding via user config's `balances` section is allowed but discouraged and triggers a warning.

## Development Patterns

### Adding a New Variable Derivation

1. Verify variable name against ELM source (`/code/E3SM/IM1/components/elm/src/`)
2. Add function to `elm_diagnostics/io/derived.py`:
   ```python
   def compute_my_variable(run: Run) -> xr.DataArray:
       """Compute MY_VAR from components.
       
       Based on ELM source (MyModule.F90:123):
           MY_VAR = COMP1 + COMP2
       """
       # Check components, compute, set attrs
   ```
3. Register in `Run.get()` fallback chain (in `io/run.py`)
4. Add test in `tests/test_real_data.py` or new test file
5. Update `docs/variable-mappings.md` with source code reference

### Adding a New Plot Type

1. Create `elm_diagnostics/plots/my_plot.py` with `plot_my_thing(run: Run, varname: str, ...)`
2. Export in `elm_diagnostics/plots/__init__.py`
3. Add test in `tests/test_plots.py` (use `@pytest.mark.mpl_image_compare` for image tests)
4. Update `Config.VariableGroupConfig.PlotTypeConfig` in `config/schema.py` if group-level toggle needed

### Adding a New Balance Type

1. Create `elm_diagnostics/balances/my_balance.py` inheriting from `balances/base.py:Balance`
2. Implement abstract methods: `components()`, `residual()`, `plot()`
3. Export in `elm_diagnostics/balances/__init__.py` and top-level `__init__.py`
4. Add default balance definition to `config/defaults.yaml` under `balances.my_balance`
5. Add Pydantic model to `config/schema.py:BalanceConfig`
6. Add CLI command in `cli.py` under `balance` subcommand
7. Add tests in `tests/test_my_balance.py`

### Modifying Configuration Schema

1. Edit Pydantic models in `config/schema.py`
2. Update `config/defaults.yaml` with new defaults
3. Run `pytest tests/test_config.py` to ensure schema validates
4. Update docstrings and README configuration examples

### Working with Real ELM Output

**Test data location:** `tests/fixtures/data/oakharbor_column.elm.elm.h*.nc` (15 months, Oct 2000 - Dec 2001)

**Common issues:**
- Missing `QFLX_EVAP_TOT`: Auto-computed from `QSOIL + QVEGE + QVEGT`
- 3D soil variables: Auto-summed over `levgrnd`
- Gridded vs single-point: `Run` handles both (`lat`×`lon` or `lndgrid`)
- Sub-gridcell: Check for `column`, `pft`, `landunit` dimensions

## Important Conventions

- **Variable names:** Use exact ELM history field names (verified against source code)
- **Units:** Always use `pint-xarray` for unit-aware operations; never assume units
- **Time handling:** Use `time_bounds` for integration, not `time` coordinate alone
- **Vertical aggregation:** Check for `levgrnd`/`levsoi` dimension before summing
- **Water year:** Default start month is October (configurable via `time.water_year_start_month`)
- **Sub-gridcell:** Support `by` parameter for faceting when appropriate
- **Balance overrides:** Warn user when they override balance definitions in config

## Testing Notes

- **161 tests passing** (35 CLI, 17 report, 45 sub-gridcell, 21 plots, 20 balance/integration, 23 config/data)
- Image comparison tests use `pytest-mpl` (baseline images in `tests/baseline/`)
- Real data tests use Oak Harbor fixture (15 months, complete water year)
- CLI tests use `typer.testing.CliRunner` with captured output
- Sub-gridcell tests validate faceting logic for column/PFT/landunit

## Documentation Files

- `README.md`: User-facing CLI documentation with quick start and examples
- `docs/python-api.md`: Complete Python API reference for programmatic usage
- `docs/assumptions.md`: Verified assumptions from ELM source and real output
- `docs/variable-mappings.md`: Complete variable definitions with source code references
- `docs/elm-diagnostics-spec.md`: Detailed design specification
- `docs/tutorial-*.md`: Getting started, balance checking, experiment comparison
- `docs/workflow-examples.md`: Common automation patterns

## License

BSD-3-Clause with LANL/Triad National Security copyright disclosure (see `LICENSE`).

## Important Notes for Future Development

- **Phase 7 complete:** CLI with progress indicators, error handling, verbose/debug/quiet modes
- **Next phase (Phase 8):** User documentation, tutorials, worked examples (partially complete)
- **Variable name stability:** All names verified against E3SM IM1 source; changes require re-verification
- **Balance definitions:** Keep in schema defaults, discourage user overrides
- **Test coverage:** Maintain 100% pass rate; add tests for all new features
- **Real data validation:** Use Oak Harbor fixture for integration tests
