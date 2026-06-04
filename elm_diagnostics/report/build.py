"""Report orchestrator: generates a single-page HTML diagnostics report."""

from __future__ import annotations

import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
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
    plot_seasonal,
    plot_timeseries,
)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ASSETS_DIR = Path(__file__).parent / "assets"

_RESAMPLING = getattr(Image, "Resampling", Image)
_PNG_PIL_KWARGS = {"compress_level": 1, "optimize": False}


class _Section:
    """Container for a report section."""

    def __init__(self, title: str, description: str = ""):
        self.title = title
        self.id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        self.description = description
        self.figures: list[dict[str, str]] = []
        self.statistics: dict[str, Any] = {}

    def add_figure(self, path: str, thumb_path: str, caption: str, plot_type: str = "") -> None:
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
        self.figures.append({
            "path": path,
            "thumb_path": thumb_path,
            "caption": caption,
            "plot_type": plot_type,
        })

    def add_statistics(self, stats: dict[str, Any]) -> None:
        """Add statistics table data to section."""
        self.statistics = stats


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
    ):
        self.source = source
        self.year = year
        self._errors: list[dict[str, str]] = []
        self._warnings: list[str] = []
        self._generation_time = datetime.now()
        self._section_timings: list[dict[str, Any]] = []
        self._rendered_section_titles: list[str] = []
        self._build_total_seconds: float | None = None
        self._progress_section_index = 0
        self._progress_total_sections = 0

        if config is None or isinstance(config, (str, Path)):
            self.config = load_config(config)
        else:
            self.config = config

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
            "bbox_inches": "tight",
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
                    "bbox_inches": "tight",
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
        self._errors.append({
            "section": section,
            "error": str(error),
            "type": type(error).__name__,
            "traceback": traceback.format_exc(),
        })

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
        return [
            "Water Balance",
            "Energy Balance",
            "Carbon Balance",
            *[group_name.replace("_", " ").title() for group_name in self.config.variables.groups],
            "Diagnostics",
        ]

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
            # --- Metadata section ---
            if self.config.report.metadata.show_run_info:
                sections.append(self._build_metadata_section())

            # --- Balance sections ---
            sections.extend(self._build_balance_sections(figdir, datadir))

            # --- Variable group sections ---
            sections.extend(self._build_variable_sections(figdir))

            # --- Error diagnostics section ---
            if self._errors or self._warnings:
                sections.append(self._build_diagnostics_section())
            else:
                self._announce_section_progress("Diagnostics skipped")
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

        # Get time range from first stream
        if streams:
            first_stream = next(iter(streams.values()))
            time_coord = first_stream.time
            metadata["Time Range"] = (
                f"{time_coord[0].values} to {time_coord[-1].values}"
            )
            metadata["Number of Time Steps"] = len(time_coord)

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
            metadata["Report Generated"] = self._generation_time.strftime("%Y-%m-%d %H:%M:%S")

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

        # Water Balance
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
            wb = WaterBalance(run, year=self.year, config=self.config)
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
                p3, t3 = self._save_figure(figs[2], figdir, "water_input_decomposition")
                sec.add_figure(p3, t3, "Water input decomposition", "balance")

            if len(figs) >= 4:
                p4, t4 = self._save_figure(figs[3], figdir, "water_storage_decomposition")
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
                nc_file = datadir / f"water_balance{'_' + str(self.year) if self.year else ''}.nc"
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

        # Energy Balance
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
            eb = EnergyBalance(run, year=self.year, config=self.config)
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
                nc_file = datadir / f"energy_balance{'_' + str(self.year) if self.year else ''}.nc"
                # Energy balance doesn't have to_netcdf yet, save components directly
                try:
                    io_start = time.perf_counter()
                    components_ds = xr.Dataset({k: v for k, v in eb.components().items()})
                    components_ds.to_netcdf(nc_file)
                    io_seconds += time.perf_counter() - io_start
                except Exception:
                    pass  # Skip if can't save
            
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

        # Carbon Balance
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
            cb = CarbonBalance(run, year=self.year, config=self.config)
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
                nc_file = datadir / f"carbon_balance{'_' + str(self.year) if self.year else ''}.nc"
                # Carbon balance doesn't have to_netcdf yet, save components directly
                try:
                    io_start = time.perf_counter()
                    components_ds = xr.Dataset({k: v for k, v in cb.components().items()})
                    components_ds.to_netcdf(nc_file)
                    io_seconds += time.perf_counter() - io_start
                except Exception:
                    pass  # Skip if can't save
            
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
        stats = {}
        try:
            components = wb.components()
            reduced_components = {
                name: self._reduce_non_time_dims(da)
                for name, da in components.items()
            }
            residual = self._reduce_non_time_dims(wb.residual())

            # Get final cumulative values
            for name, da in reduced_components.items():
                final_val = self._final_scalar(da)
                stats[name] = f"{final_val:.2f} mm"

            # Add residual info
            final_residual = self._final_scalar(residual)
            stats["Residual"] = f"{final_residual:.2f} mm"

            # Calculate percentage if requested
            if self.config.report.balance_sections.show_residual_percentage:
                # Compute as percentage of inputs
                total_input = 0.0
                for key in ["RAIN", "SNOW"]:
                    if key in reduced_components:
                        total_input += abs(self._final_scalar(reduced_components[key]))
                if total_input > 0:
                    pct = (abs(final_residual) / total_input) * 100
                    stats["Residual (%)"] = f"{pct:.2f}%"
        except Exception as e:
            stats["Error"] = str(e)
        
        return stats

    def _compute_energy_balance_stats(self, eb: EnergyBalance) -> dict[str, Any]:
        """Compute statistics for energy balance section."""
        stats = {}
        try:
            components = {
                name: self._reduce_non_time_dims(da)
                for name, da in eb.components().items()
            }

            # Get mean flux values
            for name, da in components.items():
                mean_val = self._mean_scalar(da)
                stats[name] = f"{mean_val:.2f} W/m²"
        except Exception as e:
            stats["Error"] = str(e)

        return stats

    def _compute_carbon_balance_stats(self, cb: CarbonBalance) -> dict[str, Any]:
        """Compute statistics for carbon balance section."""
        stats = {}
        try:
            components = {
                name: self._reduce_non_time_dims(da)
                for name, da in cb.components().items()
            }

            # Get final cumulative or mean values
            for name, da in components.items():
                if "cumulative" in name.lower() or name in ["GPP", "NEE", "HR"]:
                    final_val = self._final_scalar(da)
                    stats[name] = f"{final_val:.2f} gC/m²"
                else:
                    mean_val = self._mean_scalar(da)
                    stats[name] = f"{mean_val:.2f} gC/m²"
        except Exception as e:
            stats["Error"] = str(e)

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
    def _close_new_figures(existing_fignums: set[int]) -> None:
        """Close figures opened after a snapshot, including leaked ones on errors."""
        for fignum in set(plt.get_fignums()) - existing_fignums:
            plt.close(fignum)

    def _build_variable_sections(self, figdir: Path) -> list[_Section]:
        sections = []
        groups = self.config.variables.groups
        run = self._run
        plot_types = self.config.report.plot_types.include
        max_vars = self.config.report.variable_sections.max_variables_per_group

        for group_name, varnames in groups.items():
            section_start = time.perf_counter()
            io_seconds = 0.0
            compute_seconds = 0.0
            plot_seconds = 0.0
            section_title = group_name.replace("_", " ").title()
            sec = _Section(section_title)
            self._announce_section_progress(section_title)
            
            # Limit number of variables if configured
            varnames_to_plot = varnames[:max_vars]
            if len(varnames) > max_vars:
                self._add_warning(
                    f"Group '{group_name}': showing {max_vars}/{len(varnames)} variables"
                )
            
            for varname in varnames_to_plot:
                compute_start = time.perf_counter()
                has_var = run.has(varname)
                compute_seconds += time.perf_counter() - compute_start
                if not has_var:
                    continue
                
                # Try each plot type
                for plot_type in plot_types:
                    fig: plt.Figure | None = None
                    existing_fignums = set(plt.get_fignums())
                    try:
                        fig, plot_compute_seconds, plot_render_seconds = self._create_plot(
                            plot_type,
                            varname,
                        )
                        compute_seconds += plot_compute_seconds
                        plot_seconds += plot_render_seconds
                        if fig is not None:
                            basename = f"{group_name}_{varname}_{plot_type}"
                            io_start = time.perf_counter()
                            full_path, thumb_path = self._save_figure(fig, figdir, basename)
                            io_seconds += time.perf_counter() - io_start
                            caption = f"{varname} ({plot_type})"
                            sec.add_figure(full_path, thumb_path, caption, plot_type)
                    except Exception as e:
                        # Silently skip individual plot failures
                        # (e.g., diurnal for monthly data, seasonal for insufficient data)
                        pass
                    finally:
                        if fig is not None:
                            plt.close(fig)
                        self._close_new_figures(existing_fignums)
            
            if sec.figures:
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
            run = self._run
            var = run.get(varname)
            if len(var.time) < 12:
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
            run = self._run
            var = run.get(varname)
            if len(var.time) < 24:  # Rough approximation
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
            run = self._run
            var = run.get(varname)
            if len(var.time) < 24:
                return None, time.perf_counter() - compute_start, 0.0
            # Check time resolution
            time_diff = np.diff(var.time.values).astype('timedelta64[h]').astype(int)
            median_hours = np.median(time_diff)
            if median_hours >= 24:
                return None, time.perf_counter() - compute_start, 0.0  # Not sub-daily
            compute_seconds = time.perf_counter() - compute_start
            plot_start = time.perf_counter()
            return (
                plot_diurnal(self.source, varname, config=self.config),
                compute_seconds,
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
            section_title,
            "Errors and warnings encountered during report generation."
        )
        
        # Format errors and warnings for display
        diagnostics = {}
        
        if self._errors:
            diagnostics["Errors"] = [
                f"{err['section']}: {err['type']} - {err['error']}"
                for err in self._errors
            ]
        
        if self._warnings:
            diagnostics["Warnings"] = self._warnings
        
        sec.add_statistics(diagnostics)
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
        total_figures = sum(len(s.figures) for s in sections)
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
                    "statistics": s.statistics,
                }
                for s in sections
            ],
        )

        html_path = outdir / "index.html"
        html_path.write_text(html)
        return html_path
