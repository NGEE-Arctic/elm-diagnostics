"""Tests for Run and Comparison classes."""

import tempfile
from pathlib import Path

import pytest

from elm_diagnostics.io.run import Run
from tests.fixtures.synthetic_elm import (
    make_water_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def elm_case_dir():
    """Create a temporary directory with synthetic ELM files."""
    ds = make_water_balance_dataset(n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="test_case", tape="h0")
        yield Path(tmpdir)


def test_run_discovers_streams(elm_case_dir):
    run = Run(elm_case_dir)
    assert "h0" in run.streams
    assert len(run.streams) == 1
    run.close()


def test_run_extracts_casename(elm_case_dir):
    run = Run(elm_case_dir)
    assert run.name == "test_case"
    run.close()


def test_run_get_existing_variable(elm_case_dir):
    run = Run(elm_case_dir)
    da = run.get("RAIN")
    assert da is not None
    assert "time" in da.dims
    run.close()


def test_run_get_missing_variable(elm_case_dir):
    run = Run(elm_case_dir)
    with pytest.raises(KeyError, match="NONEXISTENT"):
        run.get("NONEXISTENT")
    run.close()


def test_run_has(elm_case_dir):
    run = Run(elm_case_dir)
    assert run.has("RAIN")
    assert not run.has("NONEXISTENT")
    run.close()


def test_run_cadence(elm_case_dir):
    run = Run(elm_case_dir)
    assert run.cadence["h0"] == "monthly"
    run.close()


def test_run_no_files_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(FileNotFoundError):
            Run(tmpdir)


def test_run_repr(elm_case_dir):
    run = Run(elm_case_dir)
    r = repr(run)
    assert "test_case" in r
    assert "h0" in r
    run.close()
