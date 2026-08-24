# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""CLI entry point for elm-diagnostics."""

from __future__ import annotations

import logging
import shlex
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

app = typer.Typer(
    name="elm-diagnostics",
    help="Diagnostics and budget-closure tools for E3SM's ELM land model.",
)


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging based on verbosity flags."""
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def validate_path(path: str, require_elm_files: bool = True) -> Path:
    """
    Validate that a path exists and optionally contains ELM files.

    Parameters
    ----------
    path : str
        Path to validate.
    require_elm_files : bool, optional
        If True, check for ELM history files.

    Returns
    -------
    Path
        Validated path object.

    Raises
    ------
    typer.Exit
        If path is invalid.
    """
    p = Path(path).expanduser().resolve()

    if not p.exists():
        console.print(f"[red]Error:[/red] Directory not found: {path}\n")
        console.print("The specified path does not exist. Please check:")
        console.print("  • Path is spelled correctly")
        console.print("  • You have permission to access it")
        console.print(f"  • Current directory: {Path.cwd()}\n")
        console.print("Example: elm-diagnostics report /path/to/elm/output")
        raise typer.Exit(code=1)

    if require_elm_files:
        # Check for ELM files in this directory or subdirectories
        elm_files = list(p.glob("*.elm.h*.nc"))
        if not elm_files:
            # Try subdirectories
            elm_files = list(p.glob("*/*.elm.h*.nc"))

        if not elm_files:
            console.print(
                f"[yellow]Warning:[/yellow] No ELM history files found in {path}"
            )
            console.print("  Looking for files matching: *.elm.h*.nc")
            console.print(
                "  The directory will be searched, but this may cause errors.\n"
            )

    return p


def validate_config(config_path: str) -> Path:
    """Validate that a config file exists and is readable."""
    p = Path(config_path).expanduser().resolve()

    if not p.exists():
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        raise typer.Exit(code=1)

    if not p.is_file():
        console.print(f"[red]Error:[/red] Config path is not a file: {config_path}")
        raise typer.Exit(code=1)

    return p


def complete_balance_type(incomplete: str) -> list[str]:
    """Auto-complete balance types."""
    types = ["water", "carbon", "energy"]
    return [t for t in types if t.startswith(incomplete)]


def complete_plot_kind(incomplete: str) -> list[str]:
    """Auto-complete plot kinds."""
    kinds = ["timeseries", "hovmuller", "seasonal", "anomaly", "histogram", "diurnal"]
    return [k for k in kinds if k.startswith(incomplete)]


def _get_run_strict_combine(config_path: str | None) -> bool:
    """Resolve strict_combine from merged defaults/user config."""
    from elm_diagnostics.config.schema import load_config

    cfg = load_config(path=config_path) if config_path else load_config()
    return cfg.io.strict_combine


def _get_run_chunk_options(
    config_path: str | None,
) -> tuple[str, dict[str, int] | None, int]:
    """Resolve chunking mode/settings from merged defaults/user config."""
    from elm_diagnostics.config.schema import load_config

    cfg = load_config(path=config_path) if config_path else load_config()
    mode = cfg.io.chunk_mode
    target_mb = cfg.io.chunk_target_mb
    manual_chunks = cfg.io.chunks or None
    if mode == "manual" and manual_chunks is None:
        mode = "off"
    if mode != "manual":
        manual_chunks = None
    return mode, manual_chunks, target_mb


def _resolve_analysis_year_filter(
    config_path: str | None,
) -> tuple[int | None, int | None]:
    """Return inclusive year range for early loader narrowing when safe."""
    from elm_diagnostics.config.schema import load_config

    cfg = load_config(path=config_path) if config_path else load_config()
    lo = cfg.time.analysis_start_year
    hi = cfg.time.analysis_end_year

    if lo is None and hi is None:
        return None, None

    # If any balance uses water-year framing and the water year does not
    # begin in January, we must include the previous calendar year so the
    # selected window can start at the configured boundary (e.g., Oct 1).
    balance_frames = (
        cfg.balances.water.frame,
        cfg.balances.carbon.frame,
        cfg.balances.energy.frame,
    )
    needs_prev_year = (
        "water_year" in balance_frames and cfg.time.water_year_start_month > 1
    )

    if lo is not None and needs_prev_year:
        lo -= 1

    if cfg.plots.climatology.include_climos:
        start = cfg.plots.climatology.climo_start_year
        end = cfg.plots.climatology.climo_end_year
        if start == -1 or end == -1:
            return None, None
        if lo is None:
            lo = min(start, end)
        else:
            lo = min(lo, start, end)

        if hi is None:
            hi = max(start, end)
        else:
            hi = max(hi, start, end)
        return lo, hi
    return lo, hi


def _print_report_section_timings(
    timings: list[dict[str, float | str | None]],
    build_total_seconds: float | None = None,
) -> None:
    """Print a section-level timing summary for report generation."""
    if not timings:
        return

    grand_total = sum(float(entry["total_seconds"]) for entry in timings)
    title_width = max(len(str(entry["title"])) for entry in timings)
    show_phase_breakdown = any(
        any(
            entry.get(key) is not None
            for key in ("io_seconds", "compute_seconds", "plot_seconds")
        )
        for entry in timings
    )

    console.print("\n[bold]Section timings[/bold]")
    for entry in timings:
        title = str(entry["title"])
        total = float(entry["total_seconds"])
        pct = 100.0 * total / grand_total if grand_total > 0 else 0.0
        line = f"  {title:<{title_width}}  total {total:6.2f}s  {pct:5.1f}%"
        if show_phase_breakdown:
            parts = []
            if entry.get("io_seconds") is not None:
                parts.append(f"export/write {float(entry['io_seconds']):.2f}s")
            if entry.get("compute_seconds") is not None:
                parts.append(f"prep/checks {float(entry['compute_seconds']):.2f}s")
            if entry.get("plot_seconds") is not None:
                parts.append(f"plot build {float(entry['plot_seconds']):.2f}s")
            if parts:
                line += "  (" + ", ".join(parts) + ")"
        console.print(line)

    console.print(
        f"  {'Grand total':<{title_width}}  total {grand_total:6.2f}s  100.0%"
    )
    if build_total_seconds is not None:
        overhead = build_total_seconds - grand_total
        console.print(
            f"  {'Report build total':<{title_width}}  total {build_total_seconds:6.2f}s"
        )
        if abs(overhead) >= 0.01:
            console.print(
                f"  {'Unattributed overhead':<{title_width}}  total {overhead:6.2f}s"
            )


@app.command()
def report(
    path: str = typer.Argument(..., help="Path to ELM history files directory."),
    compare: str | None = typer.Option(
        None, "--compare", help="Path to comparison run."
    ),
    out: str = typer.Option("elm_report", "--out", help="Output directory."),
    config: str | None = typer.Option(None, "--config", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
    debug: bool = typer.Option(
        False, "--debug", help="Debug mode with full tracebacks."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress output."
    ),
) -> None:
    """
    Generate a full diagnostics report.

    Creates an HTML report with water, carbon, and energy balance diagnostics,
    along with plots for individual variables. The report includes balance
    closure statistics, time series plots, seasonal cycles, and more.

    Examples:

        # Basic report
        elm-diagnostics report /path/to/elm/output

        # Report using year window from config
        elm-diagnostics report /path/to/elm/output --config config.yaml

        # Comparison report
        elm-diagnostics report /path/to/exp --compare /path/to/control

        # Custom output directory
        elm-diagnostics report /path/to/output --out my_report
    """
    setup_logging(verbose=verbose, debug=debug)
    logger = logging.getLogger(__name__)

    if verbose and quiet:
        console.print("[red]Error:[/red] Cannot specify both --verbose and --quiet")
        raise typer.Exit(code=1)

    try:
        # Validate paths
        elm_path = validate_path(path)
        if compare:
            compare_path = validate_path(compare)

        if config:
            validate_config(config)

        strict_combine = _get_run_strict_combine(config)
        chunk_mode, manual_chunks, chunk_target_mb = _get_run_chunk_options(config)

        # Extract original analysis window from config before file-narrowing transformation
        from elm_diagnostics.config.schema import load_config

        original_cfg = load_config(path=config) if config else load_config()
        original_analysis_year_min = original_cfg.time.analysis_start_year
        original_analysis_year_max = original_cfg.time.analysis_end_year

        analysis_year_min, analysis_year_max = _resolve_analysis_year_filter(config)

        # Import here to avoid slow startup
        from elm_diagnostics.io.run import Comparison, Run
        from elm_diagnostics.report.build import Report

        # Load data with optional progress
        start_time = time.time()

        if not quiet:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Loading ELM data...", total=None)
                run = Run(
                    str(elm_path),
                    strict_combine=strict_combine,
                    chunk_mode=chunk_mode,
                    chunks=manual_chunks,
                    chunk_target_mb=chunk_target_mb,
                    analysis_year_min=analysis_year_min,
                    analysis_year_max=analysis_year_max,
                )
                progress.update(task, completed=True)
                elapsed = time.time() - start_time
                if verbose:
                    logger.info(f"Loaded data in {elapsed:.1f}s")
        else:
            run = Run(
                str(elm_path),
                strict_combine=strict_combine,
                chunk_mode=chunk_mode,
                chunks=manual_chunks,
                chunk_target_mb=chunk_target_mb,
                analysis_year_min=analysis_year_min,
                analysis_year_max=analysis_year_max,
            )

        # Load comparison run if specified
        if compare:
            if not quiet:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                    transient=True,
                ) as progress:
                    task = progress.add_task("Loading comparison data...", total=None)
                    compare_run = Run(
                        str(compare_path),
                        strict_combine=strict_combine,
                        chunk_mode=chunk_mode,
                        chunks=manual_chunks,
                        chunk_target_mb=chunk_target_mb,
                        analysis_year_min=analysis_year_min,
                        analysis_year_max=analysis_year_max,
                    )
                    source = Comparison(run, compare_run)
                    progress.update(task, completed=True)
            else:
                compare_run = Run(
                    str(compare_path),
                    strict_combine=strict_combine,
                    chunk_mode=chunk_mode,
                    chunks=manual_chunks,
                    chunk_target_mb=chunk_target_mb,
                    analysis_year_min=analysis_year_min,
                    analysis_year_max=analysis_year_max,
                )
                source = Comparison(run, compare_run)
        else:
            source = run

        # Build report
        if not quiet:
            console.print("\n[bold]Building diagnostics report...[/bold]")
            start_time = time.time()

        rpt = Report(
            source,
            config=config,
            invocation_command=shlex.join(sys.argv),
            config_path=config,
            analysis_year_min=original_analysis_year_min,
            analysis_year_max=original_analysis_year_max,
        )
        html_path = rpt.build(out)

        if not quiet:
            elapsed = time.time() - start_time
            console.print(f"[green]✓[/green] Report generated in {elapsed:.1f}s")

        console.print(f"\n[bold green]Report generated:[/bold green] {html_path}")
        _print_report_section_timings(rpt.section_timings, rpt.build_total_seconds)

        if verbose:
            logger.info(f"Output directory: {Path(out).resolve()}")
            logger.info(f"Figures: {Path(out) / 'figures'}")
            logger.info(f"Data: {Path(out) / 'data'}")

        run.close()

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            raise
        console.print(f"\n[red]Error:[/red] {e!s}")
        console.print("\nRun with --debug for full traceback")
        raise typer.Exit(code=1)


@app.command()
def balance(
    kind: str = typer.Argument(
        ...,
        help="Balance type: water, carbon, or energy.",
        autocompletion=complete_balance_type,
    ),
    path: str = typer.Argument(..., help="Path to ELM history files directory."),
    out: str | None = typer.Option(
        None, "--out", help="Output directory for plots/data."
    ),
    config: str | None = typer.Option(None, "--config", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
    debug: bool = typer.Option(
        False, "--debug", help="Debug mode with full tracebacks."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress output."
    ),
) -> None:
    """
    Compute and plot a single budget balance.

    Calculates water, carbon, or energy balance closure and generates
    two-panel plots: cumulative components and decomposition.

    Examples:

        # Carbon balance, save to directory
        elm-diagnostics balance carbon /path/to/output --out ./results/

        # Energy balance, all available years
        elm-diagnostics balance energy /path/to/output
    """
    setup_logging(verbose=verbose, debug=debug)
    logger = logging.getLogger(__name__)

    if verbose and quiet:
        console.print("[red]Error:[/red] Cannot specify both --verbose and --quiet")
        raise typer.Exit(code=1)

    try:
        # Validate inputs
        elm_path = validate_path(path)
        if config:
            validate_config(config)

        strict_combine = _get_run_strict_combine(config)
        chunk_mode, manual_chunks, chunk_target_mb = _get_run_chunk_options(config)
        analysis_year_min, analysis_year_max = _resolve_analysis_year_filter(config)

        from elm_diagnostics.balances.carbon import CarbonBalance
        from elm_diagnostics.balances.energy import EnergyBalance
        from elm_diagnostics.balances.water import WaterBalance
        from elm_diagnostics.io.run import Run

        balance_classes = {
            "water": WaterBalance,
            "carbon": CarbonBalance,
            "energy": EnergyBalance,
        }

        if kind not in balance_classes:
            console.print(f"[red]Error:[/red] Unknown balance type: {kind}\n")
            console.print(f"Valid options: {', '.join(balance_classes.keys())}")
            console.print("\nExample: elm-diagnostics balance water /path/to/output")
            raise typer.Exit(code=1)

        # Load data
        start_time = time.time()
        if not quiet:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Loading ELM data...", total=None)
                run = Run(
                    str(elm_path),
                    strict_combine=strict_combine,
                    chunk_mode=chunk_mode,
                    chunks=manual_chunks,
                    chunk_target_mb=chunk_target_mb,
                    analysis_year_min=analysis_year_min,
                    analysis_year_max=analysis_year_max,
                )
                progress.update(task, completed=True)
                elapsed = time.time() - start_time
                if verbose:
                    logger.info(f"Loaded data in {elapsed:.1f}s")
        else:
            run = Run(
                str(elm_path),
                strict_combine=strict_combine,
                chunk_mode=chunk_mode,
                chunks=manual_chunks,
                chunk_target_mb=chunk_target_mb,
                analysis_year_min=analysis_year_min,
                analysis_year_max=analysis_year_max,
            )

        # Compute balance
        if not quiet:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(f"Computing {kind} balance...", total=None)
                bal = balance_classes[kind](run, config=config)
                progress.update(task, completed=True)
        else:
            bal = balance_classes[kind](run, config=config)

        if verbose:
            logger.info(f"Balance type: {kind}")

        # Generate plots
        if not quiet:
            console.print("Generating plots...")

        figures = bal.plot()

        if out:
            outdir = Path(out)
            outdir.mkdir(parents=True, exist_ok=True)
            for i, fig in enumerate(figures, start=1):
                fig.savefig(
                    outdir / f"{kind}_panel{i}.png", bbox_inches="tight", dpi=150
                )
            bal.to_netcdf(outdir / f"{kind}_balance.nc")

            console.print(f"[green]✓[/green] Saved to {outdir.resolve()}/")
            if verbose:
                for i in range(1, len(figures) + 1):
                    logger.info(f"  - {kind}_panel{i}.png")
                logger.info(f"  - {kind}_balance.nc")
        else:
            import matplotlib.pyplot as plt

            if not quiet:
                console.print("Displaying plots...")
            plt.show()

        run.close()

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            raise
        console.print(f"\n[red]Error:[/red] {e!s}")
        console.print("\nRun with --debug for full traceback")
        raise typer.Exit(code=1)


@app.command()
def plot(
    varname: str = typer.Argument(..., help="Variable name to plot."),
    path: str = typer.Argument(..., help="Path to ELM history files directory."),
    kind: str = typer.Option(
        "timeseries",
        "--kind",
        help="Plot type: timeseries, hovmuller, seasonal, anomaly, histogram, or diurnal.",
        autocompletion=complete_plot_kind,
    ),
    out: str | None = typer.Option(
        None, "--out", help="Output file path (e.g. plot.png)."
    ),
    config: str | None = typer.Option(None, "--config", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
    debug: bool = typer.Option(
        False, "--debug", help="Debug mode with full tracebacks."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress output."
    ),
) -> None:
    """
    Plot a single variable.

    Generate various plot types for ELM output variables including time series,
    Hovmuller diagrams, seasonal cycles, annual anomalies, histograms,
    and diurnal cycles.

    Examples:

        # Time series plot (default)
        elm-diagnostics plot GPP /path/to/output

        # Seasonal cycle
        elm-diagnostics plot RAIN /path/to/output --kind seasonal

        # Save to file
        elm-diagnostics plot GPP /path/to/output --out gpp_timeseries.png

        # Histogram with verbose output
        elm-diagnostics plot ER /path/to/output --kind histogram --verbose
    """
    setup_logging(verbose=verbose, debug=debug)
    logger = logging.getLogger(__name__)

    if verbose and quiet:
        console.print("[red]Error:[/red] Cannot specify both --verbose and --quiet")
        raise typer.Exit(code=1)

    try:
        # Validate inputs
        elm_path = validate_path(path)
        if config:
            validate_config(config)

        strict_combine = _get_run_strict_combine(config)
        chunk_mode, manual_chunks, chunk_target_mb = _get_run_chunk_options(config)

        from elm_diagnostics.config.schema import load_config as load_config_obj
        from elm_diagnostics.io.run import Run
        from elm_diagnostics.plots import (
            plot_anomaly,
            plot_histogram,
            plot_hovmuller,
            plot_seasonal,
            plot_timeseries,
        )

        plot_funcs = {
            "timeseries": plot_timeseries,
            "hovmuller": plot_hovmuller,
            "seasonal": plot_seasonal,
            "anomaly": plot_anomaly,
            "histogram": plot_histogram,
        }

        if kind not in plot_funcs:
            console.print(f"[red]Error:[/red] Unknown plot kind: {kind}\n")
            console.print(f"Valid options: {', '.join(plot_funcs.keys())}")
            console.print(
                "\nExample: elm-diagnostics plot GPP /path/to/output --kind seasonal"
            )
            raise typer.Exit(code=1)

        # Load config object
        cfg = load_config_obj(path=config) if config else load_config_obj()

        # Load data
        start_time = time.time()
        if not quiet:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Loading ELM data...", total=None)
                run = Run(
                    str(elm_path),
                    strict_combine=strict_combine,
                    chunk_mode=chunk_mode,
                    chunks=manual_chunks,
                    chunk_target_mb=chunk_target_mb,
                )
                progress.update(task, completed=True)
                elapsed = time.time() - start_time
                if verbose:
                    logger.info(f"Loaded data in {elapsed:.1f}s")
        else:
            run = Run(
                str(elm_path),
                strict_combine=strict_combine,
                chunk_mode=chunk_mode,
                chunks=manual_chunks,
                chunk_target_mb=chunk_target_mb,
            )

        if verbose:
            logger.info(f"Variable: {varname}")
            logger.info(f"Plot type: {kind}")

        # Generate plot
        if not quiet:
            console.print(f"Generating {kind} plot for {varname}...")

        fig = plot_funcs[kind](run, varname, config=cfg)

        if out:
            fig.savefig(out, bbox_inches="tight", dpi=150)
            console.print(f"[green]✓[/green] Saved to {Path(out).resolve()}")
        else:
            import matplotlib.pyplot as plt

            console.print("Displaying plot...")
            plt.show()

        run.close()

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            raise
        console.print(f"\n[red]Error:[/red] {e!s}")
        console.print("\nRun with --debug for full traceback")
        raise typer.Exit(code=1)


@app.command()
def map(
    varname: str = typer.Argument(..., help="Variable name to map."),
    path: str = typer.Argument(..., help="Path to ELM history files directory."),
    time_agg: str = typer.Option(
        "mean",
        "--time-agg",
        help="Time aggregation: mean, median, sum, std, min, max, or integer index.",
    ),
    projection: str = typer.Option(
        "PlateCarree", "--projection", help="Cartopy projection name."
    ),
    boundary: str | None = typer.Option(
        None, "--boundary", help="Path to watershed boundary file (GeoJSON/shapefile)."
    ),
    domain_file: str | None = typer.Option(
        None, "--domain-file", help="Path to ELM domain file (for lndgrid data)."
    ),
    out: str | None = typer.Option(
        None, "--out", help="Output file path (e.g. map.png)."
    ),
    config: str | None = typer.Option(None, "--config", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
    debug: bool = typer.Option(
        False, "--debug", help="Debug mode with full tracebacks."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress output."
    ),
) -> None:
    """
    Create spatial map of a variable for multi-gridcell data.

    Generate spatial maps showing the distribution of variables across
    a watershed or region. Requires multi-gridcell ELM output (lat/lon
    or lndgrid format).

    Examples:

        # Mean GPP across watershed
        elm-diagnostics map GPP /path/to/output

        # Median RAIN with custom projection
        elm-diagnostics map RAIN /path/to/output --time-agg median --projection Orthographic

        # With watershed boundary overlay
        elm-diagnostics map QOVER /path/to/output --boundary watershed.geojson

        # Save to file
        elm-diagnostics map TWS /path/to/output --out tws_map.png

        # Specific timestep
        elm-diagnostics map GPP /path/to/output --time-agg 0
    """
    setup_logging(verbose=verbose, debug=debug)

    if verbose and quiet:
        console.print("[red]Error:[/red] Cannot specify both --verbose and --quiet")
        raise typer.Exit(code=1)

    try:
        # Validate inputs
        elm_path = validate_path(path)
        if config:
            validate_config(config)

        # Check cartopy availability
        try:
            import cartopy  # noqa: F401
        except ImportError:
            console.print(
                "[red]Error:[/red] Spatial mapping requires cartopy. "
                "Install with: pip install 'elm-diagnostics[maps]'"
            )
            raise typer.Exit(code=1)

        strict_combine = _get_run_strict_combine(config)
        chunk_mode, manual_chunks, chunk_target_mb = _get_run_chunk_options(config)

        from elm_diagnostics.config.schema import load_config as load_config_obj
        from elm_diagnostics.io.run import Run
        from elm_diagnostics.plots import plot_map
        from elm_diagnostics.plots.dimension_helpers import has_multiple_spatial_cells

        cfg = load_config_obj(config)

        if not quiet:
            with Progress() as progress:
                task = progress.add_task("[cyan]Loading ELM data...", total=None)
                run = Run(
                    str(elm_path),
                    strict_combine=strict_combine,
                    chunk_mode=chunk_mode,
                    chunks=manual_chunks,
                    chunk_target_mb=chunk_target_mb,
                )
                progress.update(task, completed=True)
        else:
            run = Run(
                str(elm_path),
                strict_combine=strict_combine,
                chunk_mode=chunk_mode,
                chunks=manual_chunks,
                chunk_target_mb=chunk_target_mb,
            )

        # Check if variable exists
        if not run.has(varname):
            console.print(f"[red]Error:[/red] Variable '{varname}' not found")
            raise typer.Exit(code=1)

        # Check if data has spatial variation
        var = run.get(varname)
        if not has_multiple_spatial_cells(var):
            console.print(
                f"[red]Error:[/red] Variable '{varname}' has no spatial variation "
                "(single-point data). Spatial maps require multi-gridcell output."
            )
            raise typer.Exit(code=1)

        # Parse time aggregation (could be string method or integer index)
        time_agg_parsed: str | int = time_agg
        try:
            time_agg_parsed = int(time_agg)
        except ValueError:
            pass  # Keep as string

        # Create the map
        if not quiet:
            with Progress() as progress:
                task = progress.add_task("[cyan]Creating spatial map...", total=None)
                fig = plot_map(
                    run,
                    varname,
                    time_agg=time_agg_parsed,
                    projection=projection,
                    watershed_boundary=Path(boundary) if boundary else None,
                    domain_file=Path(domain_file) if domain_file else None,
                    config=cfg,
                )
                progress.update(task, completed=True)
        else:
            fig = plot_map(
                run,
                varname,
                time_agg=time_agg_parsed,
                projection=projection,
                watershed_boundary=Path(boundary) if boundary else None,
                domain_file=Path(domain_file) if domain_file else None,
                config=cfg,
            )

        # Save or show
        if out:
            import matplotlib.pyplot as plt

            out_path = Path(out)
            fig.savefig(out_path, bbox_inches="tight", dpi=cfg.plots.style.dpi)
            if not quiet:
                console.print(f"[green]✓[/green] Saved map to {out_path}")
        else:
            import matplotlib.pyplot as plt

            plt.show()

    except Exception as e:
        if debug:
            raise
        console.print(f"\n[red]Error:[/red] {e!s}")
        console.print("\nRun with --debug for full traceback")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
