# Test change proposals

No existing file under `tests/` is modified on the refactor branch. Each entry below needs explicit
approval before it is added.

No existing test was judged wrong or redundant during the survey.

## T1 — Plot characterization tests — **approved, added** (`tests/test_plot_characterization.py`, 15 tests)
- **File:** new `tests/test_plot_characterization.py`
- **What:** for each of the 6 plot kinds × {`Run`, `Comparison`} × `by ∈ {None, "column"}` (where
  supported), build the figure from existing fixtures and assert a fingerprint: axes titles, x/y
  labels, suptitle, legend texts, and line/collection data arrays (rounded).
- **Why:** plot tests mostly assert `fig is not None`; no image-comparison tests exist. Guards
  refactor steps 4, 8, 10, 11.

## T2 — Report characterization test — **approved, added** (`tests/test_report_characterization.py`, 7 tests)
- **File:** new test in a new module, e.g. `tests/test_report_characterization.py`
- **What:** build a report on the fixture; assert section filenames, figure basenames, normalized
  statistics-table rows, and the variable sets in `data/*.nc`.
- **Why:** guards step 9 (table-driven balance sections).

## T3 — CLI error-path tests — **approved, added** (`tests/test_cli_paths.py`)
- **What:** pin current stdout and exit codes for unknown `--kind`, missing path, and
  `--verbose --quiet`.
- **Why:** documents bugs B1/B2 as current behavior so later fixes are deliberate.

## T4 — Comparison and sub-daily coverage — **approved, added** (`tests/test_comparison_and_subdaily.py`, 10 tests)
- **What:** `Comparison.get` alignment (`intersect`/`union`) on two fixture runs (currently never
  executed); diurnal plot on a synthetic hourly fixture (`plots/diurnal.py` at 39% coverage);
  `get_time_deltas` without time bounds (`time/integration.py` at 54%).
- **Why:** every plot's Comparison branch is currently unexercised.

## T5 — CLI non-quiet paths — **approved, added** (`tests/test_cli_paths.py`; T3+T5 = 8 tests)
- **What:** `balance` and `plot` without `--quiet`, and `report --compare`.
- **Why:** spinner branches in `cli.py` are uncovered; guards step 7.
