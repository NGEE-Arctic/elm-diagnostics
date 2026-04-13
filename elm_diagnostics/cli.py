"""CLI entry point for elm-diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="elm-diagnostics",
    help="Diagnostics and budget-closure tools for E3SM's ELM land model.",
)


@app.command()
def report(
    path: str = typer.Argument(..., help="Path to ELM history files directory."),
    compare: Optional[str] = typer.Option(None, "--compare", help="Path to comparison run."),
    out: str = typer.Option("elm_report", "--out", help="Output directory."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to config YAML."),
    year: Optional[int] = typer.Option(None, "--year", help="Specific year to analyze."),
) -> None:
    """Generate a full diagnostics report."""
    from elm_diagnostics.io.run import Comparison, Run
    from elm_diagnostics.report.build import Report

    run = Run(path)
    if compare:
        source = Comparison(run, Run(compare))
    else:
        source = run

    rpt = Report(source, config=config, year=year)
    html_path = rpt.build(out)
    typer.echo(f"Report generated: {html_path}")
    run.close()


@app.command()
def balance(
    kind: str = typer.Argument(..., help="Balance type: water, carbon, or energy."),
    path: str = typer.Argument(..., help="Path to ELM history files directory."),
    year: Optional[int] = typer.Option(None, "--year", help="Specific year."),
    out: Optional[str] = typer.Option(None, "--out", help="Output directory for plots/data."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to config YAML."),
) -> None:
    """Compute and plot a single budget balance."""
    from elm_diagnostics.balances.carbon import CarbonBalance
    from elm_diagnostics.balances.energy import EnergyBalance
    from elm_diagnostics.balances.water import WaterBalance
    from elm_diagnostics.io.run import Run

    run = Run(path)
    balance_classes = {
        "water": WaterBalance,
        "carbon": CarbonBalance,
        "energy": EnergyBalance,
    }

    if kind not in balance_classes:
        typer.echo(f"Unknown balance type: {kind}. Choose from: {', '.join(balance_classes)}")
        raise typer.Exit(code=1)

    bal = balance_classes[kind](run, year=year, config=config)
    fig1, fig2 = bal.plot()

    if out:
        outdir = Path(out)
        outdir.mkdir(parents=True, exist_ok=True)
        fig1.savefig(outdir / f"{kind}_panel1.png", bbox_inches="tight", dpi=150)
        fig2.savefig(outdir / f"{kind}_panel2.png", bbox_inches="tight", dpi=150)
        bal.to_netcdf(outdir / f"{kind}_balance.nc")
        typer.echo(f"Saved to {outdir}/")
    else:
        import matplotlib.pyplot as plt
        plt.show()

    run.close()


@app.command()
def plot(
    varname: str = typer.Argument(..., help="Variable name to plot."),
    path: str = typer.Argument(..., help="Path to ELM history files directory."),
    kind: str = typer.Option("timeseries", "--kind",
                             help="Plot type: timeseries, seasonal, anomaly, or histogram."),
    out: Optional[str] = typer.Option(None, "--out", help="Output file path (e.g. plot.png)."),
    config: Optional[str] = typer.Option(None, "--config", help="Path to config YAML."),
) -> None:
    """Plot a single variable."""
    from elm_diagnostics.io.run import Run
    from elm_diagnostics.plots import plot_anomaly, plot_histogram, plot_seasonal, plot_timeseries

    run = Run(path)
    plot_funcs = {
        "timeseries": plot_timeseries,
        "seasonal": plot_seasonal,
        "anomaly": plot_anomaly,
        "histogram": plot_histogram,
    }

    if kind not in plot_funcs:
        typer.echo(f"Unknown plot kind: {kind}. Choose from: {', '.join(plot_funcs)}")
        raise typer.Exit(code=1)

    fig = plot_funcs[kind](run, varname, config=config)

    if out:
        fig.savefig(out, bbox_inches="tight", dpi=150)
        typer.echo(f"Saved to {out}")
    else:
        import matplotlib.pyplot as plt
        plt.show()

    run.close()


if __name__ == "__main__":
    app()
