"""Energy balance diagnostics (flux-form, no cumulative integration)."""

from __future__ import annotations


import matplotlib.pyplot as plt
import xarray as xr

from elm_diagnostics.balances.base import Balance, _plot_time
from elm_diagnostics.config.schema import EnergyBalanceConfig


class EnergyBalance(Balance):
    """Surface energy balance: Rnet - FSH - EFLX_LH_TOT - FGR ~ 0.

    All quantities are instantaneous fluxes (W/m2).
    No cumulative integration is performed (per user specification).

    Rnet = FSA - FIRA = (FSDS - FSR) + (FLDS - FIRE)
    Closure = Rnet - FSH - EFLX_LH_TOT - FGR
    """

    def _get_balance_config(self) -> EnergyBalanceConfig:
        return self.config.balances.energy

    def _get_variable_names(self) -> list[str]:
        bc = self._balance_config
        return bc.radiation + bc.turbulent + bc.ground

    def _compute_components(self) -> dict[str, xr.DataArray]:
        """Return energy balance components (all in W/m2)."""
        bc = self._balance_config
        result = {}

        for varname in bc.radiation + bc.turbulent + bc.ground:
            try:
                da = self._get_var(varname)
                da = self._select_year(da)
                result[varname] = da
            except KeyError:
                pass

        # Compute derived quantities
        if "FSA" in result and "FIRA" in result:
            result["Rnet"] = result["FSA"] - result["FIRA"]
            result["Rnet"].attrs = {"units": "W/m^2", "long_name": "net radiation"}
            result["Rnet"].name = "Rnet"

        return result

    def _compute_residual(self) -> xr.DataArray:
        """Compute energy closure residual: Rnet - FSH - LE - G."""
        comps = self.components()

        rnet = comps.get("Rnet")
        fsh = comps.get("FSH")
        le = comps.get("EFLX_LH_TOT")
        fgr = comps.get("FGR")

        if rnet is None or fsh is None or le is None or fgr is None:
            missing = []
            if rnet is None:
                missing.append("Rnet (needs FSA, FIRA)")
            if fsh is None:
                missing.append("FSH")
            if le is None:
                missing.append("EFLX_LH_TOT")
            if fgr is None:
                missing.append("FGR")
            raise KeyError(
                f"Cannot compute energy residual: missing {', '.join(missing)}"
            )

        residual = rnet - fsh - le - fgr
        residual.attrs = {"units": "W/m^2", "long_name": "energy balance residual"}
        residual.name = "residual"
        return residual

    def plot(self) -> tuple[plt.Figure, plt.Figure]:
        """Generate energy balance plots.

        Returns
        -------
        (fig_fluxes, fig_closure)
            fig_fluxes: radiation components and turbulent/ground fluxes
            fig_closure: residual time series
        """
        comps = self.components()
        style = self.config.plots.style

        # --- Flux panel ---
        fig1, ax1 = plt.subplots(figsize=style.figsize, dpi=style.dpi)

        # Radiation
        if "Rnet" in comps:
            ax1.plot(
                _plot_time(comps["Rnet"]),
                comps["Rnet"],
                label="Rnet",
                color="orange",
                linewidth=2,
            )
        if "FSH" in comps:
            ax1.plot(_plot_time(comps["FSH"]), comps["FSH"], label="FSH", color="red")
        if "EFLX_LH_TOT" in comps:
            ax1.plot(
                _plot_time(comps["EFLX_LH_TOT"]),
                comps["EFLX_LH_TOT"],
                label="LE",
                color="blue",
            )
        if "FGR" in comps:
            ax1.plot(_plot_time(comps["FGR"]), comps["FGR"], label="FGR", color="brown")

        ax1.set_xlabel("Time")
        ax1.set_ylabel("W/m²")
        title = f"Surface Energy Fluxes — {self.run.name}"
        if self.year:
            title += f" ({self.year})"
        ax1.set_title(title)
        # Only add legend if there are labeled artists
        if ax1.get_legend_handles_labels()[0]:
            ax1.legend(loc="best", fontsize="small")
        ax1.axhline(0, color="gray", linewidth=0.5)
        fig1.tight_layout()

        # --- Closure panel ---
        fig2, ax2 = plt.subplots(figsize=style.figsize, dpi=style.dpi)

        try:
            res = self.residual()
            ax2.plot(_plot_time(res), res, color="black", linewidth=1)
            ax2.axhline(0, color="gray", linewidth=0.5)
            ax2.set_ylabel("W/m²")
            ax2.set_xlabel("Time")
            ax2.set_title(
                f"Energy Balance Residual (Rnet - H - LE - G) — {self.run.name}"
            )
        except KeyError as e:
            ax2.text(
                0.5,
                0.5,
                f"Cannot compute: {e}",
                transform=ax2.transAxes,
                ha="center",
                va="center",
            )
            ax2.set_title("Energy Balance Residual — incomplete data")

        fig2.tight_layout()

        return fig1, fig2
