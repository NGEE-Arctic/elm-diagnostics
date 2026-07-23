# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Carbon balance diagnostics."""

from __future__ import annotations


import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.balances.base import Balance, _plot_time
from elm_diagnostics.config.schema import CarbonBalanceConfig
from elm_diagnostics.time.integration import cumulative_integral, storage_change


class CarbonBalance(Balance):
    """Ecosystem carbon balance.

    For BGC mode:
        dTOTECOSYSC/dt = GPP - ER - TOTFIRE - WOOD_HARVESTC
        NEE = ER - GPP (positive = source to atmosphere)

    For SP mode (satellite phenology):
        Carbon pools are not prognostic. Raises an informative error.
    """

    def _get_balance_config(self) -> CarbonBalanceConfig:
        return self.config.balances.carbon

    def _get_variable_names(self) -> list[str]:
        bc = self._balance_config
        return bc.fluxes + bc.pools + [bc.residual_against]

    def _detect_bgc_mode(self) -> bool:
        """Detect whether the run has active BGC (vs satellite phenology).

        Checks if GPP and LEAFC exist and have non-fill values.
        """
        bc = self._balance_config
        if bc.mode == "bgc":
            return True
        if bc.mode == "sp":
            return False

        # Auto-detect
        for varname in ["GPP", "LEAFC"]:
            if not self.run.has(varname):
                return False
            da = self.run.get(varname)
            vals = da.values
            if np.all(np.isnan(vals)) or np.all(vals == 0):
                return False
        return True

    def _compute_components(self) -> dict[str, xr.DataArray]:
        """Return carbon balance components.

        Fluxes are cumulative-integrated to gC/m2.
        Pools are raw state variables in gC/m2.
        """
        if not self._detect_bgc_mode():
            raise RuntimeError(
                "Carbon balance requires BGC mode. This run appears to use "
                "satellite phenology (SP) — carbon pools are not prognostic. "
                "Check that the run was configured with BGC."
            )

        bc = self._balance_config
        result = {}

        # Get parent dataset for time_bounds
        parent_ds = None
        for tape in self.run._tape_order:
            ds = self.run._open_stream(tape)
            if "time_bounds" in ds or "time_bnds" in ds:
                parent_ds = ds
                break
        if parent_ds is None:
            parent_ds = self.run._open_stream(self.run._tape_order[0])

        # Cumulative fluxes
        for varname in bc.fluxes:
            try:
                da = self._get_var(varname)
                da = self._select_year(da)
                result[varname] = cumulative_integral(da, parent_ds)
            except KeyError:
                pass

        # State pools
        for varname in bc.pools:
            try:
                da = self._get_var(varname)
                da = self._select_year(da)
                result[varname] = da
            except KeyError:
                pass

        # Total ecosystem carbon (residual target)
        try:
            da = self._get_var(bc.residual_against)
            da = self._select_year(da)
            result[bc.residual_against] = da
            result["dTOTECOSYSC"] = storage_change(da)
        except KeyError:
            pass

        return result

    def _compute_residual(self) -> xr.DataArray:
        """Compute carbon closure residual.

        residual = cumul(GPP) - cumul(ER) - cumul(TOTFIRE)
                   - cumul(WOOD_HARVESTC) - dTOTECOSYSC
        """
        comps = self.components()

        gpp = comps.get("GPP", 0)
        er = comps.get("ER", 0)
        fire = comps.get("TOTFIRE", 0)
        harvest = comps.get("WOOD_HARVESTC", 0)
        ds_change = comps.get("dTOTECOSYSC", 0)

        residual = gpp - er - fire - harvest - ds_change
        if isinstance(residual, xr.DataArray):
            residual.attrs = {"units": "gC/m^2", "long_name": "carbon balance residual"}
            residual.name = "residual"
        return residual

    def plot(self) -> tuple[plt.Figure, plt.Figure]:
        """Generate carbon balance plots.

        Returns
        -------
        (fig_cumulative, fig_pools)
            fig_cumulative: cumulative fluxes and storage change
            fig_pools: carbon pool time series
        """
        comps = self.components()
        bc = self._balance_config
        style = self.config.plots.style

        # --- Cumulative flux panel ---
        fig1, ax1 = plt.subplots(figsize=style.figsize, dpi=style.dpi)

        flux_colors = {
            "GPP": "green",
            "ER": "red",
            "HR": "orange",
            "AR": "salmon",
            "NEE": "purple",
            "TOTFIRE": "gray",
            "WOOD_HARVESTC": "brown",
        }

        for varname in bc.fluxes:
            if varname in comps:
                c = flux_colors.get(varname, None)
                ax1.plot(
                    _plot_time(comps[varname]), comps[varname], label=varname, color=c
                )

        if "dTOTECOSYSC" in comps:
            ax1.plot(
                _plot_time(comps["dTOTECOSYSC"]),
                comps["dTOTECOSYSC"],
                label="dTOTECOSYSC",
                color="black",
                linestyle="--",
            )

        res = self.residual()
        if isinstance(res, xr.DataArray):
            ax1.plot(
                _plot_time(res),
                res,
                label="Residual",
                color="black",
                linestyle=":",
                linewidth=2,
            )

        ax1.set_xlabel("Time")
        ax1.set_ylabel("Cumulative (gC/m²)")
        title = f"Carbon Balance — {self.run.name}"
        if self.year:
            title += f" ({self.year})"
        ax1.set_title(title)
        ax1.legend(loc="best", fontsize="small")
        ax1.axhline(0, color="gray", linewidth=0.5)
        fig1.tight_layout()

        # --- Pool panel ---
        fig2, ax2 = plt.subplots(figsize=style.figsize, dpi=style.dpi)

        pool_colors = plt.cm.Set2.colors
        for i, varname in enumerate(bc.pools):
            if varname in comps:
                ax2.plot(
                    _plot_time(comps[varname]),
                    comps[varname],
                    label=varname,
                    color=pool_colors[i % len(pool_colors)],
                )

        ax2.set_xlabel("Time")
        ax2.set_ylabel("gC/m²")
        ax2.set_title(f"Carbon Pools — {self.run.name}")
        ax2.legend(loc="best", fontsize="small", ncol=2)
        fig2.tight_layout()

        return fig1, fig2
