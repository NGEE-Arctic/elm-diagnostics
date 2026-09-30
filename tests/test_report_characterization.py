"""Characterization tests for Report output structure.

Pins the files a report writes, the figures each balance section produces,
the statistics-table rows, and the variables saved to data/*.nc.
"""

import re

import pytest
import xarray as xr

from elm_diagnostics import Comparison, Report, Run
from elm_diagnostics.config.schema import Config, load_config
from tests.fixtures.synthetic_elm import (
    make_carbon_balance_dataset,
    make_energy_balance_dataset,
    make_met_forcing_dataset,
    make_water_balance_dataset,
    save_as_elm_files,
)

_ROW_METRIC = re.compile(
    r'<strong>([^<]*)</strong>|<span class="stats-indent-\d+">([^<]*)</span>'
)


def _combined_dataset(n_months=24):
    ds = make_water_balance_dataset(n_months=n_months)
    for extra in (
        make_energy_balance_dataset(n_months=n_months),
        make_carbon_balance_dataset(n_months=n_months),
        make_met_forcing_dataset(n_months=n_months),
    ):
        for name in extra.data_vars:
            if name not in ds:
                ds[name] = extra[name]
    return ds


def _small_config() -> Config:
    """Default config trimmed to one variable group, plotted sequentially."""
    base = load_config().model_dump()
    base["variable_groups"] = {
        "met_forcing": {
            "enabled": True,
            "variables": ["TBOT", "RAIN", "NOPE"],
            "plot_types": {
                "timeseries": True,
                "hovmuller": False,
                "seasonal": True,
                "anomaly": False,
                "histogram": True,
                "diurnal": False,
            },
        }
    }
    base["report"]["performance"]["parallel_plot_workers"] = 1
    return Config.model_validate(base)


def _stats_metrics(html: str) -> list[str]:
    table = html.split('<table class="stats-table">', 1)[1].split("</table>", 1)[0]
    return [a or b for a, b in _ROW_METRIC.findall(table)]


@pytest.fixture
def report_dir(tmp_path, capsys):
    save_as_elm_files(_combined_dataset(), tmp_path / "run", casename="combo")
    rpt = Report(Run(tmp_path / "run"), config=_small_config())
    index = rpt.build(tmp_path / "out")
    stdout = capsys.readouterr().out
    return tmp_path / "out", index, rpt, stdout


def test_report_writes_expected_pages(report_dir):
    outdir, index, _, _ = report_dir

    assert index == outdir / "index.html"
    pages = sorted(p.name for p in outdir.glob("*.html"))
    assert pages == [
        "carbon-balance.html",
        "diagnostics.html",
        "energy-balance.html",
        "index.html",
        "met-forcing.html",
        "water-balance.html",
    ]
    assert sorted(p.name for p in (outdir / "assets").iterdir()) == [
        "lightbox.js",
        "style.css",
    ]


def test_report_balance_figures(report_dir):
    outdir, _, _, _ = report_dir
    figures = sorted(
        p.name for p in (outdir / "figures").glob("*.png") if "_thumb" not in p.name
    )
    balance_figs = [f for f in figures if not f.startswith("met_forcing_")]

    assert balance_figs == [
        "carbon_cumulative.png",
        "carbon_pools.png",
        "energy_fluxes.png",
        "energy_residual.png",
        "water_cumulative.png",
        "water_decomposition.png",
        "water_input_decomposition.png",
        "water_storage_decomposition.png",
    ]
    assert [f for f in figures if f.startswith("met_forcing_")] == [
        "met_forcing_RAIN_histogram.png",
        "met_forcing_RAIN_seasonal.png",
        "met_forcing_RAIN_timeseries.png",
        "met_forcing_TBOT_histogram.png",
        "met_forcing_TBOT_seasonal.png",
        "met_forcing_TBOT_timeseries.png",
    ]
    for fig in figures:
        assert (outdir / "figures" / fig.replace(".png", "_thumb.png")).exists()


def test_report_water_statistics_rows(report_dir):
    outdir, _, _, _ = report_dir
    metrics = _stats_metrics((outdir / "water-balance.html").read_text())

    assert metrics == [
        "Inputs (subtotal)",
        "RAIN",
        "SNOW",
        "Outputs (subtotal)",
        "QFLX_EVAP_TOT",
        "QOVER",
        "QDRAI",
        "QDRAI_PERCH",
        "Change in Storage (subtotal)",
        "dS",
        "H2OCAN",
        "H2OSFC",
        "H2OSNO",
        "SOILLIQ",
        "SOILICE",
        "Residual",
        "Residual (%)",
    ]


def test_report_energy_and_carbon_statistics_rows(report_dir):
    outdir, _, _, _ = report_dir

    assert _stats_metrics((outdir / "energy-balance.html").read_text()) == [
        "FSDS",
        "FSR",
        "FLDS",
        "FIRE",
        "FSA",
        "FIRA",
        "FSH",
        "EFLX_LH_TOT",
        "FGR",
        "Rnet",
    ]
    carbon = _stats_metrics((outdir / "carbon-balance.html").read_text())
    assert carbon[:7] == ["GPP", "AR", "HR", "ER", "NEE", "TOTFIRE", "WOOD_HARVESTC"]
    assert carbon[-2:] == ["TOTECOSYSC", "dTOTECOSYSC"]


def test_report_data_files(report_dir):
    outdir, _, _, _ = report_dir
    names = sorted(p.name for p in (outdir / "data").iterdir())
    assert names == ["carbon_balance.nc", "energy_balance.nc", "water_balance.nc"]

    with xr.open_dataset(outdir / "data" / "water_balance.nc") as ds:
        assert "residual" in ds and "dS" in ds and "RAIN" in ds
    with xr.open_dataset(outdir / "data" / "energy_balance.nc") as ds:
        assert "residual" not in ds and "Rnet" in ds
    with xr.open_dataset(outdir / "data" / "carbon_balance.nc") as ds:
        assert "residual" not in ds and "dTOTECOSYSC" in ds


def test_report_progress_output_and_warnings(report_dir):
    _, _, rpt, stdout = report_dir
    sections = [ln for ln in stdout.splitlines() if ln.startswith("[report ")]

    assert sections == [
        "[report 1/5] Water Balance",
        "[report 2/5] Energy Balance",
        "[report 3/5] Carbon Balance",
        "[report 4/5] Met Forcing",
        "[report 5/5] Diagnostics",
    ]
    assert "  [Met Forcing] Variable 1/2: TBOT" in stdout
    assert "    [TBOT] Plot 1/3: timeseries" in stdout
    assert rpt._warnings == [
        "Group 'met_forcing': skipping 1 missing variables: ['NOPE']"
    ]
    assert [t["title"] for t in rpt.section_timings] == [
        "Run Information",
        "Water Balance",
        "Energy Balance",
        "Carbon Balance",
        "Met Forcing",
        "Diagnostics",
    ]


def test_comparison_report_metadata(tmp_path, capsys):
    ds = _combined_dataset()
    save_as_elm_files(ds, tmp_path / "a", casename="base_case")
    ds_b = ds.copy()
    ds_b["RAIN"] = ds["RAIN"] * 1.2
    save_as_elm_files(ds_b, tmp_path / "b", casename="exp_case")
    source = Comparison(Run(tmp_path / "a"), Run(tmp_path / "b"))

    index = Report(source, config=_small_config()).build(tmp_path / "out")
    capsys.readouterr()
    html = index.read_text()

    assert "Base vs. Experiment" in html
    assert "base_case" in html and "exp_case" in html
