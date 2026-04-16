# Test Fixtures

This directory contains test data and fixtures for `elm-diagnostics`.

## Directory Structure

```
fixtures/
├── data/              # Real ELM output files for testing
│   └── oakharbor_column.elm.elm.h0.*.nc  (15 files, ~2.7 MB total)
├── synthetic_elm.py   # Synthetic dataset generator for unit tests
└── __init__.py
```

## Real Test Data

### Oak Harbor Single-Point Simulation

**Location:** `data/oakharbor_column.elm.elm.h0.*.nc`

**Description:**
- Single-point ELM simulation at Oak Harbor, WA
- 15 monthly h0 files covering Oct 2000 - Dec 2001
- Includes complete Water Year 2001 (Oct 2000 - Sep 2001)
- File size: ~180 KB per file, 2.7 MB total

**Coverage:**
- Complete water year for balance closure testing
- Complete calendar year 2001
- Sufficient data for seasonal cycle analysis

**Variables:**
- 535 variables per file
- Standard ELM h0 output (monthly averages)
- Includes water, carbon, and energy variables
- Dimensions: `time=1`, `lndgrid=1`, `levgrnd=15`, etc.

**Used by tests:**
- `tests/test_real_data.py` - All 11 tests use this dataset
- Validates real-world functionality with actual ELM output
- Tests multi-file loading, auto-derivation, dimension handling

## Synthetic Test Data

**Location:** `synthetic_elm.py`

**Description:**
- Python module for generating synthetic ELM-like datasets
- Used for unit tests with controlled/perfect data
- Faster than loading real files
- Allows testing edge cases and boundary conditions

**Functions:**
- `make_time_axis()` - Creates realistic time coordinates
- `make_single_point_dataset()` - Single-point synthetic data
- `make_water_balance_dataset()` - Perfect water balance closure
- `save_as_elm_files()` - Writes synthetic data to NetCDF

**Used by tests:**
- Most unit tests in `tests/` use synthetic data
- Allows testing balance closure with zero residual
- Fast test execution

## Adding New Test Data

If you need to add new test data:

1. **Small files (<10 MB):** Add to `data/` directory
2. **Large files (>10 MB):** Consider:
   - External storage (Zenodo, institutional server)
   - Download on demand in tests
   - Git LFS (if using GitHub)
3. **Update this README** with new dataset description
4. **Update `.gitignore`** if files should not be committed

## Size Considerations

Current total: ~2.7 MB (acceptable for git repository)

**Guidelines:**
- ✅ Keep test fixtures small (<10 MB total preferred)
- ✅ Use synthetic data when possible for unit tests
- ✅ Real data for integration/validation tests only
- ⚠️ Consider external storage if total >50 MB
