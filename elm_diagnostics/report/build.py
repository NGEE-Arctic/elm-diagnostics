# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Report orchestrator: generates a single-page HTML diagnostics report."""

from __future__ import annotations

import getpass
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import yaml
from jinja2 import Environment, FileSystemLoader
from PIL import Image

from elm_diagnostics.balances.carbon import CarbonBalance
from elm_diagnostics.balances.energy import EnergyBalance
from elm_diagnostics.balances.water import WaterBalance
from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.plots import (
    plot_anomaly,
    plot_diurnal,
    plot_histogram,
    plot_hovmuller,
    plot_seasonal,
    plot_timeseries,
)

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ASSETS_DIR = Path(__file__).parent / "assets"
_DEFAULT_USER_CONFIG_PATH = Path.home() / ".config" / "elm-diagnostics" / "config.yaml"

_RESAMPLING = getattr(Image, "Resampling", Image)
_PNG_PIL_KWARGS = {"compress_level": 1, "optimize": False}


class _Section:
    """Container for a report section."""

    def __init__(self, title: str, description: str = ""):
        self.title = title
        self.id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        self.description = description
        self.figures: list[dict[str, str]] = []
        self.subsections: list[_Subsection] = []
        self.statistics: Any = {}
        self.extra_tables: list[dict[str, Any]] = []
        self.extra_text_blocks: list[dict[str, str]] = []

    def add_subsection(self, title: str) -> _Subsection:
        """Create a named subsection for grouped figures."""
        subsection = _Subsection(self.id, title)
        self.subsections.append(subsection)
        return subsection

    def add_figure(
        self, path: str, thumb_path: str, caption: str, plot_type: str = ""
    ) -> None:
        """Add a figure to the section.

        Parameters
        ----------
        path : str
            Relative path to full-size image.
        thumb_path : str
            Relative path to thumbnail image.
        caption : str
            Figure caption.
        plot_type : str, optional
            Type of plot (timeseries, seasonal, etc.).
        """
        self.figures.append(
            {
                "path": path,
                "thumb_path": thumb_path,
                "caption": caption,
                "plot_type": plot_type,
            }
        )

    def add_statistics(self, stats: Any) -> None:
        """Add statistics table data to section."""
        self.statistics = stats

    def add_table(self, title: str, columns: list[str], rows: list[list[str]]) -> None:
        """Add an additional table to render beneath the primary statistics."""
        self.extra_tables.append(
            {
                "title": title,
                "columns": columns,
                "rows": rows,
            }
        )

    def add_text_block(self, title: str, content: str) -> None:
        """Add a preformatted text block beneath section tables."""
        self.extra_text_blocks.append({"title": title, "content": content})


class _Subsection:
    """Container for grouped figures within a report section."""

    def __init__(self, section_id: str, title: str):
        self.title = title
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        self.id = f"{section_id}-{slug}"
        self.figures: list[dict[str, str]] = []

    def add_figure(
        self, path: str, thumb_path: str, caption: str, plot_type: str = ""
    ) -> None:
        """Add a figure to the subsection."""
        self.figures.append(
            {
                "path": path,
                "thumb_path": thumb_path,
                "caption": caption,
                "plot_type": plot_type,
            }
        )


class Report:
    """Diagnostics report generator.

    Parameters
    ----------
    source : Run or Comparison
    config : Config or path, optional
    year : int, optional
        Specific year to analyze.
    """

    def __init__(
        self,
        source: Run | Comparison,
        config: Config | str | Path | None = None,
        year: int | None = None,
        invocation_command: str | None = None,
        config_path: str | Path | None = None,
        analysis_year_min: int | None = None,
        analysis_year_max: int | None = None,
    ):
        self.source = source
        self.year = year
        self.analysis_year_min = analysis_year_min
        self.analysis_year_max = analysis_year_max
        self._errors: list[dict[str, str]] = []
        self._warnings: list[str] = []
        self._generation_time = datetime.now()
        self._section_timings: list[dict[str, Any]] = []
        self._plot_timings: list[dict[str, Any]] = []
        self._rendered_section_titles: list[str] = []
        self._build_total_seconds: float | None = None
        self._progress_section_index = 0
        self._progress_total_sections = 0
        self._invocation_command = invocation_command or "Unavailable"
        self._git_version = self._detect_git_version()
        self._working_directory = os.getcwd()
        self._user = getpass.getuser()
        self._machine = socket.gethostname()
        self._config_source_path: Path | None = None

        if config_path is not None:
            self._config_source_path = Path(config_path).expanduser().resolve()
        elif isinstance(config, (str, Path)):
            self._config_source_path = Path(config).expanduser().resolve()
        elif config is None and _DEFAULT_USER_CONFIG_PATH.exists():
            self._config_source_path = _DEFAULT_USER_CONFIG_PATH

        if config is None or isinstance(config, (str, Path)):
            self.config = load_config(config)
        else:
            self.config = config

    def _detect_git_version(self) -> str:
        """Return repository git describe string, or 'Unavailable'."""
        repo_root = Path(__file__).resolve().parents[2]
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "describe",
                    "--always",
                    "--dirty",
                    "--tags",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            version = result.stdout.strip()
            return version or "Unavailable"
        except Exception:
            return "Unavailable"

    def _diagnostics_config_yaml(self) -> tuple[str, str]:
        """Return a title/content pair for reported config YAML."""
        if self._config_source_path is not None and self._config_source_path.exists():
            try:
                return (
                    f"Configuration file contents ({self._config_source_path})",
                    self._config_source_path.read_text(),
                )
            except Exception:
                logger.debug(
                    "Could not read config source file for report", exc_info=True
                )

        merged_yaml = yaml.safe_dump(self.config.model_dump(), sort_keys=False)
        return ("Configuration (merged)", merged_yaml)

    def _read_lnd_in_file(self) -> tuple[str, str] | None:
        """Read lnd_in namelist file from run directory.

        Returns:
            Tuple of (title, content) if file exists and is readable, None otherwise.
        """
        lnd_in_path = self._run.path / "lnd_in"
        if not lnd_in_path.exists():
            logger.warning(f"lnd_in file not found in run directory: {self._run.path}")
            return None

        try:
            return ("lnd_in namelist file", lnd_in_path.read_text())
        except Exception:
            logger.debug("Could not read lnd_in file for report", exc_info=True)
            return None

    @property
    def _run(self) -> Run:
        if isinstance(self.source, Comparison):
            return self.source.experiment
        return self.source

    @property
    def _casename(self) -> str:
        return self._run.name

    @property
    def _is_comparison(self) -> bool:
        """Check if this is a comparison report."""
        return isinstance(self.source, Comparison)

    def _apply_analysis_window(self, ds: xr.Dataset) -> xr.Dataset:
        """Apply analysis_year_min/max window to a dataset.

        Parameters
        ----------
        ds : xr.Dataset
            Dataset with time dimension.

        Returns
        -------
        xr.Dataset
            Subset to the analysis window if bounds are set.
        """
        if self.analysis_year_min is None and self.analysis_year_max is None:
            return ds

        if "time" not in ds.dims or len(ds["time"]) == 0:
            return ds

        start_year = self.analysis_year_min or -1
        end_year = self.analysis_year_max or -1

        # Convert actual years to sentinel format for subset_climo_years
        times = ds["time"].values
        years = []
        for t in times:
            if hasattr(t, "year"):
                years.append(int(t.year))
            else:
                import numpy as np

                years.append(int(np.datetime64(t, "Y").astype(int) + 1970))

        if not years:
            return ds

        min_year = min(years) if years else None
        max_year = max(years) if years else None
        if min_year is None or max_year is None:
            return ds

        # Create mask for time dimension
        import numpy as np

        mask = np.array(
            [
                (start_year == -1 or y >= start_year)
                and (end_year == -1 or y <= end_year)
                for y in years
            ]
        )

        if not mask.any():
            # No data in window, return empty
            return ds.isel(time=slice(0, 0))

        return ds.isel(time=mask)

    def _save_figure(
        self, fig: plt.Figure, figdir: Path, basename: str
    ) -> tuple[str, str]:
        """Save figure at full resolution and thumbnail.

        Returns
        -------
        tuple[str, str]
            Relative paths (full, thumbnail) for HTML.
        """
        full_path = figdir / f"{basename}.png"
        thumb_path = figdir / f"{basename}_thumb.png"

        # Save full resolution with faster PNG settings when supported.
        savefig_kwargs = {
            "dpi": self.config.plots.style.dpi,
            "pil_kwargs": _PNG_PIL_KWARGS,
        }
        try:
            fig.savefig(full_path, **savefig_kwargs)
        except TypeError:
            savefig_kwargs.pop("pil_kwargs", None)
            fig.savefig(full_path, **savefig_kwargs)

        # Save thumbnail by resizing the already-written full image.
        if self.config.report.thumbnails.enabled:
            thumb_size = tuple(self.config.report.thumbnails.size)
            try:
                with Image.open(full_path) as image:
                    thumb = image.copy()
                    thumb.thumbnail(thumb_size, _RESAMPLING.LANCZOS)
                    thumb.save(thumb_path, **_PNG_PIL_KWARGS)
            except Exception:
                # Fall back to legacy behavior if image resize fails.
                fallback_kwargs = {
                    "dpi": self.config.report.thumbnails.dpi,
                    "pil_kwargs": _PNG_PIL_KWARGS,
                }
                try:
                    fig.savefig(thumb_path, **fallback_kwargs)
                except TypeError:
                    fallback_kwargs.pop("pil_kwargs", None)
                    fig.savefig(thumb_path, **fallback_kwargs)
        else:
            # If thumbnails disabled, use same file for both
            thumb_path = full_path

        return f"figures/{basename}.png", f"figures/{basename}_thumb.png"

    def _record_error(self, section: str, error: Exception) -> None:
        """Record an error that occurred during report generation."""
        self._errors.append(
            {
                "section": section,
                "error": str(error),
                "type": type(error).__name__,
                "traceback": traceback.format_exc(),
            }
        )

    def _add_warning(self, message: str) -> None:
        """Add a warning message."""
        self._warnings.append(message)

    def _announce_section_progress(self, title: str) -> None:
        """Write a one-line section progress message to stdout immediately."""
        self._progress_section_index += 1
        total = self._progress_total_sections
        print(
            f"[report {self._progress_section_index}/{total}] {title}",
            flush=True,
        )

    def _planned_progress_sections(self) -> list[str]:
        """Return configured section titles announced during report generation."""
        sections = self.config.report.sections
        planned: list[str] = []

        if sections.water_balance:
            planned.append("Water Balance")
        if sections.energy_balance:
            planned.append("Energy Balance")
        if sections.carbon_balance:
            planned.append("Carbon Balance")
        if sections.variable_groups:
            planned.extend(
                group_name.replace("_", " ").title()
                for group_name, group in self.config.variable_groups.items()
                if group.enabled
            )
        if sections.diagnostics:
            planned.append("Diagnostics")
        return planned

    def _record_section_timing(
        self,
        title: str,
        start_time: float,
        *,
        io_seconds: float | None = None,
        compute_seconds: float | None = None,
        plot_seconds: float | None = None,
    ) -> None:
        """Record timing information for a report section."""
        self._section_timings.append(
            {
                "title": title,
                "total_seconds": time.perf_counter() - start_time,
                "io_seconds": io_seconds,
                "compute_seconds": compute_seconds,
                "plot_seconds": plot_seconds,
            }
        )

    def _record_plot_timing(
        self,
        *,
        section_title: str,
        varname: str,
        plot_type: str,
        compute_seconds: float,
        plot_seconds: float,
        io_seconds: float,
    ) -> None:
        """Record timing details for a single variable/plot-type build."""
        self._plot_timings.append(
            {
                "section": section_title,
                "variable": varname,
                "plot_type": plot_type,
                "compute_seconds": compute_seconds,
                "plot_seconds": plot_seconds,
                "io_seconds": io_seconds,
                "total_seconds": compute_seconds + plot_seconds + io_seconds,
            }
        )

    @property
    def section_timings(self) -> list[dict[str, Any]]:
        """Return section timing summaries in report order."""
        if not self._rendered_section_titles:
            return list(self._section_timings)

        ordered: list[dict[str, Any]] = []
        remaining = list(self._section_timings)
        for title in self._rendered_section_titles:
            for idx, entry in enumerate(remaining):
                if entry["title"] == title:
                    ordered.append(entry)
                    remaining.pop(idx)
                    break
        ordered.extend(remaining)
        return ordered

    @property
    def build_total_seconds(self) -> float | None:
        """Return the total elapsed time for Report.build()."""
        return self._build_total_seconds

    def build(self, outdir: str | Path) -> Path:
        """Generate the full report.

        Parameters
        ----------
        outdir : path
            Output directory. Created if needed.

        Returns
        -------
        Path to generated index.html.
        """
        outdir = Path(outdir)
        figdir = outdir / "figures"
        datadir = outdir / "data"
        figdir.mkdir(parents=True, exist_ok=True)
        datadir.mkdir(parents=True, exist_ok=True)
        self._section_timings = []
        self._rendered_section_titles = []
        self._build_total_seconds = None
        self._progress_section_index = 0
        self._progress_total_sections = len(self._planned_progress_sections())
        build_start = time.perf_counter()

        # Patch threading.excepthook to tolerate C-extension threads that
        # don't call Thread.__init__() (Python 3.14 incompatibility with
        # matplotlib/netCDF4 background threads).
        _orig_excepthook = threading.excepthook

        def _resilient_excepthook(args):
            try:
                _orig_excepthook(args)
            except AssertionError:
                print(
                    f"Unhandled exception in background thread: {args.exc_value}",
                    file=sys.stderr,
                )

        threading.excepthook = _resilient_excepthook

        prev_backend = matplotlib.get_backend()
        matplotlib.use("Agg")

        sections: list[_Section] = []
        try:
            section_flags = self.config.report.sections
            # --- Metadata section ---
            if section_flags.metadata and self.config.report.metadata.show_run_info:
                sections.append(self._build_metadata_section())

            # --- Balance sections ---
            if (
                section_flags.water_balance
                or section_flags.energy_balance
                or section_flags.carbon_balance
            ):
                sections.extend(self._build_balance_sections(figdir, datadir))

            # --- Variable group sections ---
            if section_flags.variable_groups:
                sections.extend(self._build_variable_sections(figdir))

            # --- Diagnostics section ---
            if section_flags.diagnostics:
                sections.append(self._build_diagnostics_section())
        finally:
            matplotlib.use(prev_backend)
            plt.close("all")
            threading.excepthook = _orig_excepthook

        # Render HTML
        self._rendered_section_titles = [section.title for section in sections]
        html_path = self._render_html(outdir, sections)
        self._build_total_seconds = time.perf_counter() - build_start
        return html_path

    def _build_metadata_section(self) -> _Section:
        """Build metadata section with run information."""
        start_time = time.perf_counter()
        sec = _Section("Run Information", "Metadata about the ELM simulation(s).")

        run = self._run
        streams = run.streams

        # Collect metadata
        metadata = {}
        metadata["Case Name"] = run.name

        # Get time range from first stream, respecting analysis window
        if streams:
            first_stream = next(iter(streams.values()))
            # Apply analysis window filter to get the actual reported time range
            filtered_stream = self._apply_analysis_window(first_stream)
            if len(filtered_stream.time) > 0:
                metadata["Time Range"] = (
                    f"{filtered_stream.time[0].values} to {filtered_stream.time[-1].values}"
                )
                metadata["Number of Time Steps"] = len(filtered_stream.time)
            else:
                metadata["Time Range"] = "No data in analysis window"
                metadata["Number of Time Steps"] = 0

        # List available streams
        if streams:
            metadata["History Streams"] = ", ".join(streams.keys())

        # Add comparison info if applicable
        if self._is_comparison:
            comp = self.source
            metadata["Comparison Mode"] = "Base vs. Experiment"
            metadata["Base Case"] = comp.base.name
            metadata["Experiment Case"] = comp.experiment.name

        # Generation info
        if self.config.report.metadata.show_generation_timestamp:
            metadata["Report Generated"] = self._generation_time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        sec.add_statistics(metadata)
        self._record_section_timing(
            "Run Information",
            start_time,
            io_seconds=time.perf_counter() - start_time,
        )
        return sec

    def _build_balance_sections(self, figdir: Path, datadir: Path) -> list[_Section]:
        sections = []
        run = self._run

        if self.config.report.sections.water_balance:
            section_title = "Water Balance"
            section_start = time.perf_counter()
            compute_seconds = 0.0
            plot_seconds = 0.0
            io_seconds = 0.0
            figs: tuple[plt.Figure, ...] = ()
            existing_fignums = set(plt.get_fignums())
            self._announce_section_progress(section_title)
            try:
                compute_start = time.perf_counter()
                wb = WaterBalance(
                    run,
                    year=self.year,
                    config=self.config,
                    analysis_year_min=self.analysis_year_min,
                    analysis_year_max=self.analysis_year_max,
                )
                sec = _Section(section_title, "Column water budget closure.")
                if self.config.report.balance_sections.show_statistics_table:
                    wb.components()
                    wb.residual()
                compute_seconds += time.perf_counter() - compute_start

                # Generate plots
                plot_start = time.perf_counter()
                figs = wb.plot()
                p1, t1 = self._save_figure(figs[0], figdir, "water_cumulative")
                p2, t2 = self._save_figure(figs[1], figdir, "water_decomposition")
                sec.add_figure(p1, t1, "Cumulative water balance", "balance")
                sec.add_figure(p2, t2, "Water output decomposition", "balance")

                if len(figs) >= 3:
                    p3, t3 = self._save_figure(
                        figs[2], figdir, "water_input_decomposition"
                    )
                    sec.add_figure(p3, t3, "Water input decomposition", "balance")

                if len(figs) >= 4:
                    p4, t4 = self._save_figure(
                        figs[3], figdir, "water_storage_decomposition"
                    )
                    sec.add_figure(p4, t4, "Water storage decomposition", "balance")

                for fig in figs:
                    plt.close(fig)
                plot_seconds += time.perf_counter() - plot_start

                # Add statistics if enabled
                if self.config.report.balance_sections.show_statistics_table:
                    compute_start = time.perf_counter()
                    stats = self._compute_water_balance_stats(wb)
                    sec.add_statistics(stats)
                    compute_seconds += time.perf_counter() - compute_start

                # Save NetCDF data
                if "netcdf" in self.config.report.output_formats:
                    io_start = time.perf_counter()
                    nc_file = (
                        datadir
                        / f"water_balance{'_' + str(self.year) if self.year else ''}.nc"
                    )
                    wb.to_netcdf(nc_file)
                    io_seconds += time.perf_counter() - io_start

                sections.append(sec)
            except Exception as e:
                self._record_error("Water Balance", e)
            finally:
                for fig in figs:
                    plt.close(fig)
                self._close_new_figures(existing_fignums)
                self._record_section_timing(
                    "Water Balance",
                    section_start,
                    io_seconds=io_seconds,
                    compute_seconds=compute_seconds,
                    plot_seconds=plot_seconds,
                )

        if self.config.report.sections.energy_balance:
            section_title = "Energy Balance"
            section_start = time.perf_counter()
            compute_seconds = 0.0
            plot_seconds = 0.0
            io_seconds = 0.0
            fig1 = None
            fig2 = None
            existing_fignums = set(plt.get_fignums())
            self._announce_section_progress(section_title)
            try:
                compute_start = time.perf_counter()
                eb = EnergyBalance(
                    run,
                    year=self.year,
                    config=self.config,
                    analysis_year_min=self.analysis_year_min,
                    analysis_year_max=self.analysis_year_max,
                )
                sec = _Section(section_title, "Surface energy budget closure.")
                if self.config.report.balance_sections.show_statistics_table:
                    eb.components()
                    eb.residual()
                compute_seconds += time.perf_counter() - compute_start

                plot_start = time.perf_counter()
                fig1, fig2 = eb.plot()
                p1, t1 = self._save_figure(fig1, figdir, "energy_fluxes")
                p2, t2 = self._save_figure(fig2, figdir, "energy_residual")
                sec.add_figure(p1, t1, "Surface energy fluxes", "balance")
                sec.add_figure(p2, t2, "Energy balance residual", "balance")
                plt.close(fig1)
                plt.close(fig2)
                plot_seconds += time.perf_counter() - plot_start

                # Add statistics if enabled
                if self.config.report.balance_sections.show_statistics_table:
                    compute_start = time.perf_counter()
                    stats = self._compute_energy_balance_stats(eb)
                    sec.add_statistics(stats)
                    compute_seconds += time.perf_counter() - compute_start

                # Save NetCDF data
                if "netcdf" in self.config.report.output_formats:
                    nc_file = (
                        datadir
                        / f"energy_balance{'_' + str(self.year) if self.year else ''}.nc"
                    )
                    # Energy balance doesn't have to_netcdf yet, save components directly
                    try:
                        io_start = time.perf_counter()
                        components_ds = xr.Dataset(
                            {k: v for k, v in eb.components().items()}
                        )
                        components_ds.to_netcdf(nc_file)
                        io_seconds += time.perf_counter() - io_start
                    except Exception:
                        # Skip if can't save
                        logger.debug(
                            "Could not save energy balance components to netCDF",
                            exc_info=True,
                        )

                sections.append(sec)
            except Exception as e:
                self._record_error("Energy Balance", e)
            finally:
                if fig1 is not None:
                    plt.close(fig1)
                if fig2 is not None:
                    plt.close(fig2)
                self._close_new_figures(existing_fignums)
                self._record_section_timing(
                    "Energy Balance",
                    section_start,
                    io_seconds=io_seconds,
                    compute_seconds=compute_seconds,
                    plot_seconds=plot_seconds,
                )

        if self.config.report.sections.carbon_balance:
            section_title = "Carbon Balance"
            section_start = time.perf_counter()
            compute_seconds = 0.0
            plot_seconds = 0.0
            io_seconds = 0.0
            fig1 = None
            fig2 = None
            existing_fignums = set(plt.get_fignums())
            self._announce_section_progress(section_title)
            try:
                compute_start = time.perf_counter()
                cb = CarbonBalance(
                    run,
                    year=self.year,
                    config=self.config,
                    analysis_year_min=self.analysis_year_min,
                    analysis_year_max=self.analysis_year_max,
                )
                sec = _Section(section_title, "Ecosystem carbon budget closure.")
                if self.config.report.balance_sections.show_statistics_table:
                    cb.components()
                    cb.residual()
                compute_seconds += time.perf_counter() - compute_start

                plot_start = time.perf_counter()
                fig1, fig2 = cb.plot()
                p1, t1 = self._save_figure(fig1, figdir, "carbon_cumulative")
                p2, t2 = self._save_figure(fig2, figdir, "carbon_pools")
                sec.add_figure(p1, t1, "Cumulative carbon balance", "balance")
                sec.add_figure(p2, t2, "Carbon pools", "balance")
                plt.close(fig1)
                plt.close(fig2)
                plot_seconds += time.perf_counter() - plot_start

                # Add statistics if enabled
                if self.config.report.balance_sections.show_statistics_table:
                    compute_start = time.perf_counter()
                    stats = self._compute_carbon_balance_stats(cb)
                    sec.add_statistics(stats)
                    compute_seconds += time.perf_counter() - compute_start

                # Save NetCDF data
                if "netcdf" in self.config.report.output_formats:
                    nc_file = (
                        datadir
                        / f"carbon_balance{'_' + str(self.year) if self.year else ''}.nc"
                    )
                    # Carbon balance doesn't have to_netcdf yet, save components directly
                    try:
                        io_start = time.perf_counter()
                        components_ds = xr.Dataset(
                            {k: v for k, v in cb.components().items()}
                        )
                        components_ds.to_netcdf(nc_file)
                        io_seconds += time.perf_counter() - io_start
                    except Exception:
                        # Skip if can't save
                        logger.debug(
                            "Could not save carbon balance components to netCDF",
                            exc_info=True,
                        )

                sections.append(sec)
            except Exception as e:
                self._record_error("Carbon Balance", e)
            finally:
                if fig1 is not None:
                    plt.close(fig1)
                if fig2 is not None:
                    plt.close(fig2)
                self._close_new_figures(existing_fignums)
                self._record_section_timing(
                    "Carbon Balance",
                    section_start,
                    io_seconds=io_seconds,
                    compute_seconds=compute_seconds,
                    plot_seconds=plot_seconds,
                )

        return sections

    def _compute_water_balance_stats(self, wb: WaterBalance) -> dict[str, Any]:
        """Compute statistics for water balance section."""
        stats: dict[str, Any] = {"table_kind": "balance_grouped", "rows": []}
        try:
            components = wb.components()
            reduced_components = {
                name: self._reduce_non_time_dims(da) for name, da in components.items()
            }
            residual = self._reduce_non_time_dims(wb.residual())
            storage_components = {
                name: self._reduce_non_time_dims(da)
                for name, da in wb._storage_decomposition_components().items()
            }
            rows: list[dict[str, Any]] = []

            def _add_group(
                title: str,
                keys: list[str],
                source: dict[str, xr.DataArray],
                units: str,
            ) -> None:
                available = [(k, source[k]) for k in keys if k in source]
                if not available:
                    return

                subtotal = sum(self._final_scalar(da) for _, da in available)
                rows.append(
                    self._make_stats_row(
                        metric=f"{title} (subtotal)",
                        long_name="",
                        value=f"{subtotal:.2f} {units}",
                        kind="group",
                        indent=0,
                    )
                )
                for key, da in available:
                    rows.append(
                        self._make_stats_row(
                            metric=key,
                            long_name=self._long_name_from_da(da),
                            value=f"{self._final_scalar(da):.2f} {units}",
                            kind="item",
                            indent=1,
                        )
                    )

            bc = wb._balance_config
            _add_group("Inputs", bc.inputs, reduced_components, "mm")
            _add_group("Outputs", bc.outputs, reduced_components, "mm")

            if "dS" in reduced_components:
                ds_da = reduced_components["dS"]
                rows.append(
                    self._make_stats_row(
                        metric="Change in Storage (subtotal)",
                        long_name="",
                        value=f"{self._final_scalar(ds_da):.2f} mm",
                        kind="group",
                        indent=0,
                    )
                )
                rows.append(
                    self._make_stats_row(
                        metric="dS",
                        long_name=self._long_name_from_da(ds_da),
                        value=f"{self._final_scalar(ds_da):.2f} mm",
                        kind="item",
                        indent=1,
                    )
                )
                for storage_name in bc.storages:
                    if storage_name in storage_components:
                        da = storage_components[storage_name]
                        rows.append(
                            self._make_stats_row(
                                metric=storage_name,
                                long_name=self._long_name_from_da(da),
                                value=f"{self._final_scalar(da):.2f} mm",
                                kind="item",
                                indent=2,
                            )
                        )

            final_residual = self._final_scalar(residual)
            rows.append(
                self._make_stats_row(
                    metric="Residual",
                    long_name=self._long_name_from_da(residual),
                    value=f"{final_residual:.2f} mm",
                    kind="summary",
                    indent=0,
                )
            )

            # Calculate percentage if requested
            if self.config.report.balance_sections.show_residual_percentage:
                # Compute as percentage of inputs
                total_input = 0.0
                for key in ["RAIN", "SNOW"]:
                    if key in reduced_components:
                        total_input += abs(self._final_scalar(reduced_components[key]))
                if total_input > 0:
                    pct = (abs(final_residual) / total_input) * 100
                    rows.append(
                        self._make_stats_row(
                            metric="Residual (%)",
                            long_name="",
                            value=f"{pct:.2f}%",
                            kind="summary",
                            indent=0,
                        )
                    )
            stats["rows"] = rows
        except Exception as e:
            stats = {
                "table_kind": "balance_flat",
                "rows": [
                    self._make_stats_row(
                        metric="Error",
                        long_name="",
                        value=str(e),
                        kind="summary",
                        indent=0,
                    )
                ],
            }

        return stats

    def _compute_energy_balance_stats(self, eb: EnergyBalance) -> dict[str, Any]:
        """Compute statistics for energy balance section."""
        stats: dict[str, Any] = {"table_kind": "balance_flat", "rows": []}
        try:
            components = {
                name: self._reduce_non_time_dims(da)
                for name, da in eb.components().items()
            }

            # Get mean flux values
            for name, da in components.items():
                mean_val = self._mean_scalar(da)
                stats["rows"].append(
                    self._make_stats_row(
                        metric=name,
                        long_name=self._long_name_from_da(da),
                        value=f"{mean_val:.2f} W/m²",
                        kind="item",
                        indent=0,
                    )
                )
        except Exception as e:
            stats = {
                "table_kind": "balance_flat",
                "rows": [
                    self._make_stats_row(
                        metric="Error",
                        long_name="",
                        value=str(e),
                        kind="summary",
                        indent=0,
                    )
                ],
            }

        return stats

    def _compute_carbon_balance_stats(self, cb: CarbonBalance) -> dict[str, Any]:
        """Compute statistics for carbon balance section."""
        stats: dict[str, Any] = {"table_kind": "balance_flat", "rows": []}
        try:
            components = {
                name: self._reduce_non_time_dims(da)
                for name, da in cb.components().items()
            }

            # Get final cumulative or mean values
            for name, da in components.items():
                if "cumulative" in name.lower() or name in ["GPP", "NEE", "HR"]:
                    final_val = self._final_scalar(da)
                    stats["rows"].append(
                        self._make_stats_row(
                            metric=name,
                            long_name=self._long_name_from_da(da),
                            value=f"{final_val:.2f} gC/m²",
                            kind="item",
                            indent=0,
                        )
                    )
                else:
                    mean_val = self._mean_scalar(da)
                    stats["rows"].append(
                        self._make_stats_row(
                            metric=name,
                            long_name=self._long_name_from_da(da),
                            value=f"{mean_val:.2f} gC/m²",
                            kind="item",
                            indent=0,
                        )
                    )
        except Exception as e:
            stats = {
                "table_kind": "balance_flat",
                "rows": [
                    self._make_stats_row(
                        metric="Error",
                        long_name="",
                        value=str(e),
                        kind="summary",
                        indent=0,
                    )
                ],
            }

        return stats

    @staticmethod
    def _reduce_non_time_dims(da: xr.DataArray) -> xr.DataArray:
        """Average over non-time dimensions so report stats use one time series."""
        reduce_dims = [dim for dim in da.dims if dim != "time"]
        if reduce_dims:
            return da.mean(dim=reduce_dims)
        return da

    @staticmethod
    def _final_scalar(da: xr.DataArray) -> float:
        """Return the final time-step value as a Python float."""
        return float(da.isel(time=-1).values)

    @staticmethod
    def _mean_scalar(da: xr.DataArray) -> float:
        """Return the time mean as a Python float."""
        return float(da.mean().values)

    @staticmethod
    def _long_name_from_da(da: xr.DataArray | None) -> str:
        """Return best-available descriptive name for a variable."""
        if da is None:
            return ""

        for attr_name in ("long_name", "description", "standard_name"):
            raw = da.attrs.get(attr_name)
            if raw:
                description = " ".join(str(raw).split())
                if "__tmp" in description:
                    description = description.replace("__tmp", "total water storage")
                return description

        return ""

    @staticmethod
    def _make_stats_row(
        metric: str,
        long_name: str,
        value: str,
        *,
        kind: str,
        indent: int,
    ) -> dict[str, Any]:
        """Create a normalized row for report statistics tables."""
        return {
            "metric": metric,
            "long_name": long_name,
            "value": value,
            "kind": kind,
            "indent": indent,
        }

    @staticmethod
    def _close_new_figures(existing_fignums: set[int]) -> None:
        """Close figures opened after a snapshot, including leaked ones on errors."""
        for fignum in set(plt.get_fignums()) - existing_fignums:
            plt.close(fignum)

    @staticmethod
    def _build_var_plot_context(var: xr.DataArray) -> dict[str, Any]:
        """Precompute reusable time metadata for plot eligibility checks."""
        n_time = len(var.time)
        is_subdaily = False
        if n_time >= 24:
            time_diff = np.diff(var.time.values).astype("timedelta64[h]").astype(int)
            if time_diff.size > 0:
                is_subdaily = bool(np.median(time_diff) < 24)

        return {
            "n_time": n_time,
            "is_subdaily": is_subdaily,
        }

    @staticmethod
    @contextmanager
    def _cached_get_for_var(run: Run, varname: str, var: xr.DataArray):
        """Temporarily memoize one variable lookup on a Run instance."""
        original_get = run.get

        def _get_with_cache(name: str) -> xr.DataArray:
            if name == varname:
                return var
            return original_get(name)

        run.get = _get_with_cache  # type: ignore[assignment]
        try:
            yield
        finally:
            run.get = original_get  # type: ignore[assignment]

    @contextmanager
    def _plot_source_cache_context(
        self,
        varname: str,
        experiment_var: xr.DataArray,
        base_var: xr.DataArray | None,
    ):
        """Cache active variable lookups for plot helpers during one plot call."""
        if isinstance(self.source, Comparison) and base_var is not None:
            with (
                self._cached_get_for_var(
                    self.source.experiment,
                    varname,
                    experiment_var,
                ),
                self._cached_get_for_var(self.source.base, varname, base_var),
            ):
                yield
            return

        with self._cached_get_for_var(self._run, varname, experiment_var):
            yield

    def _build_variable_sections(self, figdir: Path) -> list[_Section]:
        sections = []
        groups = self.config.variable_groups
        run = self._run
        max_vars = self.config.report.variable_sections.max_variables_per_group

        for group_name, group in groups.items():
            if not group.enabled:
                continue

            plot_types = group.plot_types.active_plot_types
            if not plot_types:
                continue

            varnames = group.variables
            section_start = time.perf_counter()
            io_seconds = 0.0
            compute_seconds = 0.0
            plot_seconds = 0.0
            section_title = group_name.replace("_", " ").title()
            sec = _Section(section_title)
            subsection_by_plot_type = {
                plot_type: sec.add_subsection(
                    f"{plot_type.replace('_', ' ').title()} plots"
                )
                for plot_type in plot_types
            }
            self._announce_section_progress(section_title)

            # Limit number of variables if configured
            varnames_to_plot = varnames[:max_vars]
            if len(varnames) > max_vars:
                self._add_warning(
                    f"Group '{group_name}': showing {max_vars}/{len(varnames)} variables"
                )

            for varname in varnames_to_plot:
                compute_start = time.perf_counter()
                var = None
                base_var = None
                var_context: dict[str, Any] | None = None
                has_var = run.has(varname)
                if has_var:
                    # Load once so validation checks do not repeatedly call run.get(varname).
                    var = run.get(varname)
                    if isinstance(self.source, Comparison):
                        base_var = self.source.base.get(varname)
                    var_context = self._build_var_plot_context(var)
                compute_seconds += time.perf_counter() - compute_start
                if var is None:
                    continue

                # Try each plot type
                with self._plot_source_cache_context(varname, var, base_var):
                    for plot_type in plot_types:
                        fig: plt.Figure | None = None
                        existing_fignums = set(plt.get_fignums())
                        try:
                            fig, plot_compute_seconds, plot_render_seconds = (
                                self._create_plot(
                                    plot_type,
                                    varname,
                                    var,
                                    base_var,
                                    var_context,
                                )
                            )
                            compute_seconds += plot_compute_seconds
                            plot_seconds += plot_render_seconds
                            io_elapsed = 0.0
                            if fig is not None:
                                basename = f"{group_name}_{varname}_{plot_type}"
                                io_start = time.perf_counter()
                                full_path, thumb_path = self._save_figure(
                                    fig, figdir, basename
                                )
                                io_elapsed = time.perf_counter() - io_start
                                io_seconds += io_elapsed
                                caption = f"{varname}"
                                subsection_by_plot_type[plot_type].add_figure(
                                    full_path,
                                    thumb_path,
                                    caption,
                                    plot_type,
                                )
                            self._record_plot_timing(
                                section_title=section_title,
                                varname=varname,
                                plot_type=plot_type,
                                compute_seconds=plot_compute_seconds,
                                plot_seconds=plot_render_seconds,
                                io_seconds=io_elapsed,
                            )
                        except Exception:
                            # Silently skip individual plot failures
                            # (e.g., diurnal for monthly data, seasonal for insufficient data)
                            logger.debug(
                                "Skipping individual plot after failure", exc_info=True
                            )
                        finally:
                            if fig is not None:
                                plt.close(fig)
                            self._close_new_figures(existing_fignums)

            has_grouped_figures = any(sub.figures for sub in sec.subsections)
            if sec.figures or has_grouped_figures:
                sections.append(sec)

            self._record_section_timing(
                sec.title,
                section_start,
                io_seconds=io_seconds,
                compute_seconds=compute_seconds,
                plot_seconds=plot_seconds,
            )

        return sections

    def _create_plot(
        self,
        plot_type: str,
        varname: str,
        var: xr.DataArray,
        base_var: xr.DataArray | None,
        var_context: dict[str, Any] | None,
    ) -> tuple[plt.Figure | None, float, float]:
        """Create one plot and return aggregated compute and render timings.

        Returns
        -------
        Tuple of ``(figure, compute_seconds, plot_seconds)``.
        """
        if plot_type == "timeseries":
            plot_start = time.perf_counter()
            return (
                plot_timeseries(self.source, varname, config=self.config),
                0.0,
                time.perf_counter() - plot_start,
            )
        elif plot_type == "seasonal":
            # Check if we have enough data
            compute_start = time.perf_counter()
            n_time = int((var_context or {}).get("n_time", len(var.time)))
            if n_time < 12:
                return None, time.perf_counter() - compute_start, 0.0
            compute_seconds = time.perf_counter() - compute_start
            plot_start = time.perf_counter()
            return (
                plot_seasonal(self.source, varname, config=self.config),
                compute_seconds,
                time.perf_counter() - plot_start,
            )
        elif plot_type == "anomaly":
            # Check if we have enough data (need at least 2 years)
            compute_start = time.perf_counter()
            n_time = int((var_context or {}).get("n_time", len(var.time)))
            if n_time < 24:  # Rough approximation
                return None, time.perf_counter() - compute_start, 0.0
            compute_seconds = time.perf_counter() - compute_start
            plot_start = time.perf_counter()
            return (
                plot_anomaly(self.source, varname, config=self.config),
                compute_seconds,
                time.perf_counter() - plot_start,
            )
        elif plot_type == "histogram":
            plot_start = time.perf_counter()
            return (
                plot_histogram(self.source, varname, config=self.config),
                0.0,
                time.perf_counter() - plot_start,
            )
        elif plot_type == "diurnal":
            # Check if data is sub-daily
            compute_start = time.perf_counter()
            n_time = int((var_context or {}).get("n_time", len(var.time)))
            if n_time < 24:
                return None, time.perf_counter() - compute_start, 0.0
            is_subdaily = bool((var_context or {}).get("is_subdaily", False))
            if not is_subdaily:
                return None, time.perf_counter() - compute_start, 0.0  # Not sub-daily
            compute_seconds = time.perf_counter() - compute_start
            plot_start = time.perf_counter()
            return (
                plot_diurnal(self.source, varname, config=self.config),
                compute_seconds,
                time.perf_counter() - plot_start,
            )
        elif plot_type == "hovmuller":
            plot_start = time.perf_counter()
            return (
                plot_hovmuller(self.source, varname, config=self.config),
                0.0,
                time.perf_counter() - plot_start,
            )
        else:
            return None, 0.0, 0.0

    def _build_diagnostics_section(self) -> _Section:
        """Build diagnostics section showing errors and warnings."""
        section_title = "Diagnostics"
        start_time = time.perf_counter()
        self._announce_section_progress(section_title)
        sec = _Section(
            section_title, "Errors and warnings encountered during report generation."
        )

        # Format errors and warnings for display
        diagnostics = {
            "Git version": self._git_version,
            "Invocation command": self._invocation_command,
            "Analysis run at": self._generation_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Working directory": self._working_directory,
            "User": self._user,
            "Machine": self._machine,
        }

        if self._errors:
            diagnostics["Errors"] = [
                f"{err['section']}: {err['type']} - {err['error']}"
                for err in self._errors
            ]

        if self._warnings:
            diagnostics["Warnings"] = self._warnings

        timings = list(self._section_timings)
        diagnostics_elapsed = time.perf_counter() - start_time
        timings.append(
            {
                "title": section_title,
                "total_seconds": diagnostics_elapsed,
                "io_seconds": None,
                "compute_seconds": None,
                "plot_seconds": None,
            }
        )
        attributed_total = sum(float(entry["total_seconds"]) for entry in timings)
        timing_rows: list[list[str]] = []
        for entry in timings:
            total = float(entry["total_seconds"])
            pct = 100.0 * total / attributed_total if attributed_total > 0 else 0.0
            timing_rows.append(
                [
                    str(entry["title"]),
                    f"{total:.2f}",
                    f"{pct:.1f}%",
                    ""
                    if entry.get("io_seconds") is None
                    else f"{float(entry['io_seconds']):.2f}",
                    ""
                    if entry.get("compute_seconds") is None
                    else f"{float(entry['compute_seconds']):.2f}",
                    ""
                    if entry.get("plot_seconds") is None
                    else f"{float(entry['plot_seconds']):.2f}",
                ]
            )
        timing_rows.append(
            ["Grand total", f"{attributed_total:.2f}", "100.0%", "", "", ""]
        )

        sec.add_statistics(diagnostics)
        sec.add_table(
            title="Section timings",
            columns=[
                "Section",
                "Total (s)",
                "% of attributed",
                "Export/Write (s)",
                "Prep/Checks (s)",
                "Plot Build (s)",
            ],
            rows=timing_rows,
        )
        if self._plot_timings:
            top_plot_rows = []
            for entry in sorted(
                self._plot_timings,
                key=lambda row: float(row["total_seconds"]),
                reverse=True,
            )[:15]:
                top_plot_rows.append(
                    [
                        str(entry["section"]),
                        str(entry["variable"]),
                        str(entry["plot_type"]),
                        f"{float(entry['total_seconds']):.2f}",
                        f"{float(entry['compute_seconds']):.2f}",
                        f"{float(entry['plot_seconds']):.2f}",
                        f"{float(entry['io_seconds']):.2f}",
                    ]
                )
            sec.add_table(
                title="Top variable plot timings",
                columns=[
                    "Section",
                    "Variable",
                    "Plot",
                    "Total (s)",
                    "Prep/Checks (s)",
                    "Plot Build (s)",
                    "Export/Write (s)",
                ],
                rows=top_plot_rows,
            )
        config_title, config_yaml = self._diagnostics_config_yaml()
        sec.add_text_block(config_title, config_yaml)

        lnd_in_data = self._read_lnd_in_file()
        if lnd_in_data is not None:
            lnd_in_title, lnd_in_content = lnd_in_data
            sec.add_text_block(lnd_in_title, lnd_in_content)

        self._record_section_timing(section_title, start_time)
        return sec

    def _render_html(self, outdir: Path, sections: list[_Section]) -> Path:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )
        template = env.get_template("single_page.html.j2")

        # Load CSS
        css_path = _ASSETS_DIR / "style.css"
        css = css_path.read_text()

        # Load JavaScript for lightbox
        js_path = _ASSETS_DIR / "lightbox.js"
        if js_path.exists():
            js = js_path.read_text()
        else:
            js = ""  # Will be created next

        title = self.config.report.title_template.format(casename=self._casename)

        # Generate summary statistics
        total_figures = sum(
            len(s.figures) + sum(len(sub.figures) for sub in s.subsections)
            for s in sections
        )
        total_errors = len(self._errors)
        total_warnings = len(self._warnings)

        # Determine status
        if total_errors > 5:
            status = "error"
            status_message = f"{total_errors} errors encountered"
        elif total_errors > 0:
            status = "warning"
            status_message = f"{total_errors} errors, report partially complete"
        elif total_warnings > 0:
            status = "warning"
            status_message = f"{total_warnings} warnings"
        else:
            status = "success"
            status_message = "All sections generated successfully"

        html = template.render(
            title=title,
            casename=self._casename,
            css=css,
            js=js,
            thumbnails_enabled=self.config.report.thumbnails.enabled,
            summary={
                "total_sections": len(sections),
                "total_figures": total_figures,
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "status": status,
                "status_message": status_message,
            },
            sections=[
                {
                    "id": s.id,
                    "title": s.title,
                    "description": s.description,
                    "figures": s.figures,
                    "subsections": [
                        {
                            "id": sub.id,
                            "title": sub.title,
                            "figures": sub.figures,
                        }
                        for sub in s.subsections
                    ],
                    "statistics": s.statistics,
                    "extra_tables": s.extra_tables,
                    "extra_text_blocks": s.extra_text_blocks,
                }
                for s in sections
            ],
        )

        html_path = outdir / "index.html"
        html_path.write_text(html)
        return html_path
