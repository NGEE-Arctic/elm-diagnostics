"""Water balance diagnostics."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from elm_diagnostics.balances.base import Balance, _plot_time
from elm_diagnostics.config.schema import Config, WaterBalanceConfig
from elm_diagnostics.io.derived import aggregate_vertical_storage
from elm_diagnostics.io.run import Run
from elm_diagnostics.time.integration import (
    cumulative_integral,
    get_time_deltas,
    storage_change,
)


class WaterBalance(Balance):
    """Column water balance: dS/dt = P - ET - R.

    Default equation (from ELM BalanceCheckMod.F90):
        residual = cumul(inputs) - cumul(outputs) - dS

    where:
        inputs  = RAIN + SNOW
        outputs = QFLX_EVAP_TOT + QOVER + QDRAI + QDRAI_PERCH
                  (QFLX_EVAP_TOT = QSOIL + QVEGE + QVEGT if not available)
        dS      = change in (SOILLIQ + SOILICE + H2OSNO + H2OCAN + H2OSFC)
                  (SOILLIQ and SOILICE are summed over vertical levels)
    """

    def _get_balance_config(self) -> WaterBalanceConfig:
        return self.config.balances.water

    def _get_variable_names(self) -> list[str]:
        bc = self._balance_config
        return bc.inputs + bc.outputs + bc.storages

    def components(self) -> dict[str, xr.DataArray]:
        """Return cumulative water balance components (all in mm)."""
        bc = self._balance_config
        result = {}

        # Get parent dataset for time_bounds
        first_input = bc.inputs[0]
        parent_ds = self.run.get(first_input).to_dataset(name=first_input)
        if "time_bounds" not in parent_ds:
            for tape in self.run._tape_order:
                ds = self.run._open_stream(tape)
                if "time_bounds" in ds or "time_bnds" in ds:
                    parent_ds = ds
                    break

        # Cumulative inputs
        for varname in bc.inputs:
            da = self._get_var(varname)
            da = self._select_year(da)
            result[varname] = cumulative_integral(da, parent_ds)

        # Cumulative outputs
        for varname in bc.outputs:
            try:
                da = self._get_var(varname)
                da = self._select_year(da)
                result[varname] = cumulative_integral(da, parent_ds)
            except KeyError:
                pass  # Variable not available in this run

        # Storage change
        total_storage = None
        for varname in bc.storages:
            try:
                da = self._get_var(varname)
                # Aggregate over vertical dimensions if present (SOILLIQ, SOILICE have levgrnd)
                if "levgrnd" in da.dims or "levsoi" in da.dims:
                    vdim = "levgrnd" if "levgrnd" in da.dims else "levsoi"
                    da = da.sum(dim=vdim, keep_attrs=True)
                
                # Convert storage to mm for consistency (kg/m² → mm for water)
                from elm_diagnostics.io.units import convert_water_to_mm
                da = convert_water_to_mm(da)
                
                da = self._select_year(da)
                if total_storage is None:
                    total_storage = da.copy()
                else:
                    total_storage = total_storage + da
            except KeyError:
                pass

        if total_storage is not None:
            result["dS"] = storage_change(total_storage)

        return result

    def cumulative(self) -> xr.Dataset:
        """Return cumulative balance components as a Dataset."""
        return xr.Dataset(self.components())

    def residual(self) -> xr.DataArray:
        """Compute closure residual: cumul(inputs) - cumul(outputs) - dS."""
        comps = self.components()
        bc = self._balance_config

        total_in = sum(comps[v] for v in bc.inputs if v in comps)
        total_out = sum(comps[v] for v in bc.outputs if v in comps)
        ds_change = comps.get("dS", 0)

        residual = total_in - total_out - ds_change
        residual.attrs["long_name"] = "water balance residual"
        residual.attrs["units"] = "mm"
        residual.name = "residual"
        return residual

    def plot(self) -> tuple[plt.Figure, plt.Figure]:
        """Generate water balance plots.
        
        If by parameter is set, creates faceted plots with one panel per
        sub-gridcell unit.

        Returns
        -------
        (fig_cumulative, fig_decomposition)
            fig_cumulative: cumulative inputs, outputs, dS, and residual
            fig_decomposition: breakdown of output components
        """
        comps = self.components()
        bc = self._balance_config
        style = self.config.plots.style

        # Check if we have sub-gridcell dimension
        if self.by is not None:
            return self._plot_faceted(comps, bc, style)
        else:
            return self._plot_single(comps, bc, style)
    
    def _plot_single(
        self, comps: dict[str, xr.DataArray], bc: WaterBalanceConfig, style
    ) -> tuple[plt.Figure, plt.Figure]:
        """Plot single water balance (no faceting)."""
        # --- Cumulative panel ---
        fig1, ax1 = plt.subplots(figsize=style.figsize, dpi=style.dpi)

        # Sum inputs
        inputs_available = [v for v in bc.inputs if v in comps]
        if inputs_available:
            total_in = sum(comps[v] for v in inputs_available)
            ax1.plot(
                _plot_time(total_in), total_in, label="P (total input)", color="blue"
            )

        # Sum outputs
        outputs_available = [v for v in bc.outputs if v in comps]
        if outputs_available:
            total_out = sum(comps[v] for v in outputs_available)
            ax1.plot(
                _plot_time(total_out), total_out, label="Total output", color="red"
            )

        # Storage change
        if "dS" in comps:
            ax1.plot(
                _plot_time(comps["dS"]),
                comps["dS"],
                label="dS (storage change)",
                color="green",
            )

        # Residual
        res = self.residual()
        ax1.plot(_plot_time(res), res, label="Residual", color="black", linestyle="--")

        ax1.set_xlabel("Time")
        ax1.set_ylabel("Cumulative (mm)")
        title = f"Water Balance — {self.run.name}"
        if self.year:
            title += f" ({self.frame} {self.year})"
        ax1.set_title(title)
        ax1.legend(loc="best", fontsize="small")
        ax1.axhline(0, color="gray", linewidth=0.5)
        fig1.tight_layout()

        # --- Decomposition panel ---
        fig2, ax2 = plt.subplots(figsize=style.figsize, dpi=style.dpi)

        colors = plt.cm.tab10.colors
        for i, varname in enumerate(outputs_available):
            ax2.plot(
                _plot_time(comps[varname]),
                comps[varname],
                label=varname,
                color=colors[i % len(colors)],
            )

        ax2.set_xlabel("Time")
        ax2.set_ylabel("Cumulative (mm)")
        ax2.set_title(f"Water Output Decomposition — {self.run.name}")
        ax2.legend(loc="best", fontsize="small")
        fig2.tight_layout()

        return fig1, fig2
    
    def _plot_faceted(
        self, comps: dict[str, xr.DataArray], bc: WaterBalanceConfig, style
    ) -> tuple[plt.Figure, plt.Figure]:
        """Plot faceted water balance by sub-gridcell dimension."""
        from elm_diagnostics.plots.subgrid_helpers import (
            create_facet_figure,
            format_subgrid_title,
            get_subgrid_units,
        )
        
        # Get subgrid units from first component
        first_comp = list(comps.values())[0]
        units = get_subgrid_units(first_comp, self.by)
        
        # Create faceted figures
        fig1, axes1 = create_facet_figure(len(units), style)
        fig2, axes2 = create_facet_figure(len(units), style)
        
        # Plot each subgrid unit
        for unit_id, ax1, ax2 in zip(units, axes1.flat, axes2.flat):
            # Select this unit from all components
            comps_unit = {k: v.sel({self.by: unit_id}) for k, v in comps.items()}
            
            # --- Cumulative panel ---
            inputs_available = [v for v in bc.inputs if v in comps_unit]
            if inputs_available:
                total_in = sum(comps_unit[v] for v in inputs_available)
                ax1.plot(
                    _plot_time(total_in), total_in, label="P", color="blue", linewidth=1
                )
            
            outputs_available = [v for v in bc.outputs if v in comps_unit]
            if outputs_available:
                total_out = sum(comps_unit[v] for v in outputs_available)
                ax1.plot(
                    _plot_time(total_out), total_out, label="Out", color="red", linewidth=1
                )
            
            if "dS" in comps_unit:
                ax1.plot(
                    _plot_time(comps_unit["dS"]),
                    comps_unit["dS"],
                    label="dS",
                    color="green",
                    linewidth=1,
                )
            
            # Residual for this unit
            res_unit = self.residual().sel({self.by: unit_id})
            ax1.plot(_plot_time(res_unit), res_unit, label="Res", color="black", linestyle="--", linewidth=1)
            
            ax1.set_xlabel("Time", fontsize="small")
            ax1.set_ylabel("Cumulative (mm)", fontsize="small")
            ax1.set_title(format_subgrid_title(self.by, unit_id), fontsize="medium")
            ax1.legend(loc="best", fontsize="x-small")
            ax1.axhline(0, color="gray", linewidth=0.5)
            ax1.tick_params(labelsize="small")
            
            # --- Decomposition panel ---
            colors = plt.cm.tab10.colors
            for i, varname in enumerate(outputs_available):
                ax2.plot(
                    _plot_time(comps_unit[varname]),
                    comps_unit[varname],
                    label=varname,
                    color=colors[i % len(colors)],
                    linewidth=1,
                )
            
            ax2.set_xlabel("Time", fontsize="small")
            ax2.set_ylabel("Cumulative (mm)", fontsize="small")
            ax2.set_title(format_subgrid_title(self.by, unit_id), fontsize="medium")
            ax2.legend(loc="best", fontsize="x-small")
            ax2.tick_params(labelsize="small")
        
        # Hide unused subplots
        for ax1 in axes1.flat[len(units):]:
            ax1.set_visible(False)
        for ax2 in axes2.flat[len(units):]:
            ax2.set_visible(False)
        
        # Overall titles
        title_base = f"Water Balance — {self.run.name}"
        if self.year:
            title_base += f" ({self.frame} {self.year})"
        
        fig1.suptitle(f"{title_base} by {self.by}", fontsize="large")
        fig2.suptitle(f"Water Output Decomposition — {self.run.name} by {self.by}", fontsize="large")
        
        fig1.tight_layout()
        fig2.tight_layout()
        
        return fig1, fig2
