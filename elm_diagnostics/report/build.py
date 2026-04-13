"""Report orchestrator: generates a single-page HTML diagnostics report."""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader

from elm_diagnostics.balances.carbon import CarbonBalance
from elm_diagnostics.balances.energy import EnergyBalance
from elm_diagnostics.balances.water import WaterBalance
from elm_diagnostics.config.schema import Config, load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.plots import plot_anomaly, plot_histogram, plot_seasonal, plot_timeseries

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ASSETS_DIR = Path(__file__).parent / "assets"


class _Section:
    """Container for a report section."""

    def __init__(self, title: str, description: str = ""):
        self.title = title
        self.id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        self.description = description
        self.figures: list[dict[str, str]] = []

    def add_figure(self, path: str, caption: str) -> None:
        self.figures.append({"path": path, "caption": caption})


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
        figdir.mkdir(parents=True, exist_ok=True)

        prev_backend = matplotlib.get_backend()
        matplotlib.use("Agg")

        sections: list[_Section] = []

        # --- Balance sections ---
        sections.extend(self._build_balance_sections(figdir))

        # --- Variable group sections ---
        sections.extend(self._build_variable_sections(figdir))

        matplotlib.use(prev_backend)
        plt.close("all")

        # Render HTML
        html_path = self._render_html(outdir, sections)
        return html_path

    def _build_balance_sections(self, figdir: Path) -> list[_Section]:
        sections = []
        run = self._run

        # Water
        try:
            wb = WaterBalance(run, year=self.year, config=self.config)
            sec = _Section("Water Balance", "Column water budget closure.")
            fig1, fig2 = wb.plot()
            p1 = figdir / "water_cumulative.png"
            p2 = figdir / "water_decomposition.png"
            fig1.savefig(p1, bbox_inches="tight")
            fig2.savefig(p2, bbox_inches="tight")
            sec.add_figure(f"figures/water_cumulative.png", "Cumulative water balance")
            sec.add_figure(f"figures/water_decomposition.png", "Water output decomposition")
            sections.append(sec)
            wb.to_netcdf(figdir.parent / "data" / "water_balance.nc")
        except Exception:
            pass

        # Energy
        try:
            eb = EnergyBalance(run, year=self.year, config=self.config)
            sec = _Section("Energy Balance", "Surface energy budget closure.")
            fig1, fig2 = eb.plot()
            p1 = figdir / "energy_fluxes.png"
            p2 = figdir / "energy_residual.png"
            fig1.savefig(p1, bbox_inches="tight")
            fig2.savefig(p2, bbox_inches="tight")
            sec.add_figure(f"figures/energy_fluxes.png", "Surface energy fluxes")
            sec.add_figure(f"figures/energy_residual.png", "Energy balance residual")
            sections.append(sec)
        except Exception:
            pass

        # Carbon
        try:
            cb = CarbonBalance(run, year=self.year, config=self.config)
            sec = _Section("Carbon Balance", "Ecosystem carbon budget closure.")
            fig1, fig2 = cb.plot()
            p1 = figdir / "carbon_cumulative.png"
            p2 = figdir / "carbon_pools.png"
            fig1.savefig(p1, bbox_inches="tight")
            fig2.savefig(p2, bbox_inches="tight")
            sec.add_figure(f"figures/carbon_cumulative.png", "Cumulative carbon balance")
            sec.add_figure(f"figures/carbon_pools.png", "Carbon pools")
            sections.append(sec)
        except Exception:
            pass

        return sections

    def _build_variable_sections(self, figdir: Path) -> list[_Section]:
        sections = []
        groups = self.config.variables.groups
        run = self._run

        for group_name, varnames in groups.items():
            sec = _Section(group_name.replace("_", " ").title())
            for varname in varnames:
                if not run.has(varname):
                    continue
                try:
                    fname = f"{group_name}_{varname}_ts.png"
                    fig = plot_timeseries(self.source, varname, config=self.config)
                    fig.savefig(figdir / fname, bbox_inches="tight")
                    sec.add_figure(f"figures/{fname}", f"{varname} time series")
                    plt.close(fig)
                except Exception:
                    pass
            if sec.figures:
                sections.append(sec)

        return sections

    def _render_html(self, outdir: Path, sections: list[_Section]) -> Path:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )
        template = env.get_template("single_page.html.j2")

        css_path = _ASSETS_DIR / "style.css"
        css = css_path.read_text()

        title = self.config.report.title_template.format(casename=self._casename)

        html = template.render(
            title=title,
            casename=self._casename,
            css=css,
            sections=[
                {
                    "id": s.id,
                    "title": s.title,
                    "description": s.description,
                    "figures": s.figures,
                }
                for s in sections
            ],
        )

        html_path = outdir / "index.html"
        html_path.write_text(html)
        return html_path
