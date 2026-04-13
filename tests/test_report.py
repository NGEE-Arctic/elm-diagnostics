"""Tests for report generation."""

import tempfile
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

from elm_diagnostics.io.run import Run
from elm_diagnostics.report.build import Report
from tests.fixtures.synthetic_elm import (
    make_water_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def report_run():
    ds = make_water_balance_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="report_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


def test_report_build(report_run):
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        html_path = rpt.build(outdir)
        assert html_path.exists()
        assert html_path.name == "index.html"
        content = html_path.read_text()
        assert "report_test" in content
        assert "Water Balance" in content


def test_report_creates_figures(report_run):
    rpt = Report(report_run)
    with tempfile.TemporaryDirectory() as outdir:
        rpt.build(outdir)
        figdir = Path(outdir) / "figures"
        assert figdir.exists()
        pngs = list(figdir.glob("*.png"))
        assert len(pngs) > 0
