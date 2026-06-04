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
        return (
            bc.inputs
            + bc.outputs
            + bc.detailed_outputs
            + bc.supplemental_outputs
            + bc.storages
            + bc.optional_storages
        )

    def _active_output_terms(self) -> list[str]:
        """Return output terms for this run with safe no-double-counting rules.

          Selection rules:
        1) Keep baseline non-runoff terms (e.g., QFLX_EVAP_TOT).
        2) If detailed runoff is enabled and at least one detailed runoff term exists,
           use available detailed runoff terms.
          3) Otherwise, use available baseline runoff terms.
          4) Include available supplemental output terms (e.g., QSNWCPICE).
        """
        key = self._cache_key()
        cached_key = getattr(self, "_active_outputs_cache_key", None)
        if cached_key == key and hasattr(self, "_active_outputs_cache"):
            return self._active_outputs_cache

        bc = self._balance_config
        baseline_outputs = list(dict.fromkeys(bc.outputs))
        detailed_outputs = list(dict.fromkeys(bc.detailed_outputs))

        baseline_runoff = [v for v in baseline_outputs if v != "QFLX_EVAP_TOT"]
        detailed_runoff = [v for v in detailed_outputs if v != "QFLX_EVAP_TOT"]
        non_runoff_outputs = [v for v in baseline_outputs if v not in baseline_runoff]

        outputs = list(non_runoff_outputs)

        if bc.use_detailed_outputs_when_available:
            available_detailed_runoff = [v for v in detailed_runoff if self.run.has(v)]
            if available_detailed_runoff:
                outputs.extend(available_detailed_runoff)
            else:
                outputs.extend([v for v in baseline_runoff if self.run.has(v)])
        else:
            outputs.extend([v for v in baseline_runoff if self.run.has(v)])

        outputs.extend([v for v in bc.supplemental_outputs if self.run.has(v)])

        outputs = list(dict.fromkeys(outputs))
        self._active_outputs_cache_key = key
        self._active_outputs_cache = outputs
        return outputs

    def _storage_variable_names(self) -> list[str]:
        """Return ordered storage variable names including optional candidates."""
        bc = self._balance_config
        names = bc.storages + bc.optional_storages
        # Preserve order while removing duplicates.
        return list(dict.fromkeys(names))

    def _compute_components(self) -> dict[str, xr.DataArray]:
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

        # Cumulative outputs (choose one family to avoid double counting)
        for varname in self._active_output_terms():
            try:
                da = self._get_var(varname)
                da = self._select_year(da)
                result[varname] = cumulative_integral(da, parent_ds)
            except KeyError:
                pass  # Variable not available in this run

        # Storage change
        total_storage = None
        for varname in self._storage_variable_names():
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

    def to_netcdf(self, path: str | Path) -> None:
        """Save water balance components and residual diagnostics to NetCDF."""
        ds = xr.Dataset(self.components())
        ds["residual"] = self.residual()

        model_res = self.model_residual()
        if model_res is not None:
            ds["model_residual"] = model_res

        model_aligned, mode = self.aligned_model_residual()
        if model_aligned is not None:
            model_aligned = model_aligned.copy()
            if mode is not None:
                model_aligned.attrs["comparison_mode"] = mode
            ds["model_residual_aligned"] = model_aligned

        residual_diff = self.residual_difference()
        if residual_diff is not None:
            ds["residual_difference"] = residual_diff

        snow_res = self.model_snow_residual()
        if snow_res is not None:
            ds["model_snow_residual"] = snow_res

        ds.to_netcdf(path)

    def _compute_residual(self) -> xr.DataArray:
        """Compute closure residual: cumul(inputs) - cumul(outputs) - dS."""
        comps = self.components()
        output_terms = self._active_output_terms()

        total_in = sum(comps[v] for v in self._balance_config.inputs if v in comps)
        total_out = sum(comps[v] for v in output_terms if v in comps)
        ds_change = comps.get("dS", 0)

        residual = total_in - total_out - ds_change
        residual.attrs["long_name"] = "water balance residual"
        residual.attrs["units"] = "mm"
        residual.name = "residual"
        return residual

    def _get_optional_var(self, candidates: list[str]) -> xr.DataArray | None:
        """Return first available variable among candidates, or None."""
        for varname in candidates:
            try:
                da = self._get_var(varname)
                da = self._select_year(da)
                return da
            except KeyError:
                continue
        return None

    def _model_diag_cache_key(self) -> tuple[object, ...]:
        """Return cache key for model residual diagnostics."""
        return (
            self._cache_key(),
            tuple(self._balance_config.model_residual_candidates),
            tuple(self._balance_config.snow_residual_candidates),
            self._balance_config.model_residual_compare_mode,
            float(self._balance_config.model_residual_sign),
        )

    def model_residual(self) -> xr.DataArray | None:
        """Return model-reported water residual if available (e.g., ERRH2O)."""
        key = self._model_diag_cache_key()
        cached_key = getattr(self, "_model_residual_cache_key", None)
        if cached_key == key and hasattr(self, "_model_residual_cache"):
            return self._model_residual_cache

        da = self._get_optional_var(self._balance_config.model_residual_candidates)
        if da is None:
            self._model_residual_cache_key = key
            self._model_residual_cache = None
            return None

        da = da.copy()
        da.attrs.setdefault("long_name", "model-reported water residual")
        da.attrs.setdefault("units", "mm")
        da.name = "model_residual"
        self._model_residual_cache_key = key
        self._model_residual_cache = da
        return da

    def model_snow_residual(self) -> xr.DataArray | None:
        """Return model-reported snow imbalance residual if available."""
        key = self._model_diag_cache_key()
        cached_key = getattr(self, "_model_snow_residual_cache_key", None)
        if cached_key == key and hasattr(self, "_model_snow_residual_cache"):
            return self._model_snow_residual_cache

        da = self._get_optional_var(self._balance_config.snow_residual_candidates)
        if da is None:
            self._model_snow_residual_cache_key = key
            self._model_snow_residual_cache = None
            return None

        da = da.copy()
        da.attrs.setdefault("long_name", "model-reported snow imbalance residual")
        da.attrs.setdefault("units", "mm")
        da.name = "model_snow_residual"
        self._model_snow_residual_cache_key = key
        self._model_snow_residual_cache = da
        return da

    @staticmethod
    def _rmse(da: xr.DataArray) -> float:
        """Return root-mean-square value, ignoring NaNs."""
        vals = np.asarray(da.values, dtype=float)
        return float(np.sqrt(np.nanmean(vals ** 2)))

    @staticmethod
    def _as_cumulative(da: xr.DataArray) -> xr.DataArray:
        """Convert a time series to cumulative form anchored at zero."""
        if "time" not in da.dims:
            return da
        cumul = da.cumsum(dim="time")
        return cumul - cumul.isel(time=0)

    def aligned_model_residual(self) -> tuple[xr.DataArray | None, str | None]:
        """Return model residual aligned to Python residual basis.

        Returns
        -------
        (aligned, mode)
            aligned : DataArray or None
                Aligned model residual series, or None if unavailable.
            mode : str or None
                One of {"direct", "cumulative"}, or None if unavailable.
        """
        key = self._model_diag_cache_key()
        cached_key = getattr(self, "_aligned_model_residual_cache_key", None)
        if cached_key == key and hasattr(self, "_aligned_model_residual_cache"):
            return self._aligned_model_residual_cache

        model_res = self.model_residual()
        if model_res is None:
            self._aligned_model_residual_cache_key = key
            self._aligned_model_residual_cache = (None, None)
            return None, None

        sign = float(self._balance_config.model_residual_sign)
        if sign != 1.0:
            model_res = model_res * sign

        mode_cfg = self._balance_config.model_residual_compare_mode
        if mode_cfg == "direct":
            aligned = model_res
            mode = "direct"
        elif mode_cfg == "cumulative":
            aligned = self._as_cumulative(model_res)
            mode = "cumulative"
        else:
            py_res = self.residual()
            direct = model_res
            cumulative = self._as_cumulative(model_res)

            rmse_direct = self._rmse(py_res - direct)
            rmse_cumulative = self._rmse(py_res - cumulative)

            if rmse_direct <= rmse_cumulative:
                aligned = direct
                mode = "direct"
            else:
                aligned = cumulative
                mode = "cumulative"

        aligned = aligned.copy()
        aligned.name = "model_residual_aligned"
        aligned.attrs["comparison_mode"] = mode
        aligned.attrs.setdefault("units", "mm")
        self._aligned_model_residual_cache_key = key
        self._aligned_model_residual_cache = (aligned, mode)
        return aligned, mode

    def _has_meaningful_model_residual(self, model_aligned: xr.DataArray) -> bool:
        """Return True when model residual magnitude warrants diff plotting."""
        model_scale = self._rmse(model_aligned)
        py_scale = self._rmse(self.residual())
        abs_tol = 1e-6
        rel_tol = 1e-3
        return model_scale > max(abs_tol, rel_tol * py_scale)

    def residual_difference(self) -> xr.DataArray | None:
        """Return Python residual minus aligned model residual, if available."""
        key = self._model_diag_cache_key()
        cached_key = getattr(self, "_residual_difference_cache_key", None)
        if cached_key == key and hasattr(self, "_residual_difference_cache"):
            return self._residual_difference_cache

        model_aligned, _ = self.aligned_model_residual()
        if model_aligned is None:
            self._residual_difference_cache_key = key
            self._residual_difference_cache = None
            return None

        diff = self.residual() - model_aligned
        diff.name = "residual_difference"
        diff.attrs["long_name"] = "python residual minus model residual"
        diff.attrs["units"] = "mm"
        self._residual_difference_cache_key = key
        self._residual_difference_cache = diff
        return diff

    def _storage_decomposition_components(self) -> dict[str, xr.DataArray]:
        """Return per-storage cumulative change components in mm.

        Each returned variable is a storage-change time series with the same
        definition used for dS: S(t) - S(0).
        """
        bc = self._balance_config
        storage_components: dict[str, xr.DataArray] = {}

        for varname in self._storage_variable_names():
            try:
                da = self._get_var(varname)

                if "levgrnd" in da.dims or "levsoi" in da.dims:
                    vdim = "levgrnd" if "levgrnd" in da.dims else "levsoi"
                    da = da.sum(dim=vdim, keep_attrs=True)

                from elm_diagnostics.io.units import convert_water_to_mm

                da = convert_water_to_mm(da)
                da = self._select_year(da)
                storage_components[varname] = storage_change(da)
            except KeyError:
                pass

        return storage_components

    def plot(self) -> tuple[plt.Figure, plt.Figure, plt.Figure, plt.Figure]:
        """Generate water balance plots.
        
        If by parameter is set, creates faceted plots with one panel per
        sub-gridcell unit.

        Returns
        -------
        (fig_cumulative, fig_output_decomposition, fig_input_decomposition,
         fig_storage_decomposition)
            fig_cumulative: cumulative inputs, outputs, dS, and residual
            fig_output_decomposition: breakdown of output components
            fig_input_decomposition: breakdown of input components
            fig_storage_decomposition: breakdown of storage-change components
        """
        comps = self.components()
        storage_comps = self._storage_decomposition_components()
        bc = self._balance_config
        style = self.config.plots.style

        # Check if we have sub-gridcell dimension
        if self.by is not None:
            return self._plot_faceted(comps, storage_comps, bc, style)
        else:
            return self._plot_single(comps, storage_comps, bc, style)
    
    def _plot_single(
        self,
        comps: dict[str, xr.DataArray],
        storage_comps: dict[str, xr.DataArray],
        bc: WaterBalanceConfig,
        style,
    ) -> tuple[plt.Figure, plt.Figure, plt.Figure, plt.Figure]:
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
        outputs_available = [v for v in self._active_output_terms() if v in comps]
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

        # Optional model residual (e.g., ERRH2O), aligned for comparison
        model_res, model_mode = self.aligned_model_residual()
        if model_res is not None:
            label = "Model residual"
            if model_mode is not None:
                label += f" ({model_mode})"
            ax1.plot(
                _plot_time(model_res),
                model_res,
                label=label,
                color="purple",
                linestyle=":",
            )

            diff = self.residual_difference()
            if diff is not None and self._has_meaningful_model_residual(model_res):
                ax1.plot(
                    _plot_time(diff),
                    diff,
                    label="Residual diff",
                    color="orange",
                    linestyle="-.",
                )

        ax1.set_xlabel("Time")
        ax1.set_ylabel("Cumulative (mm)")
        title = f"Water Balance — {self.run.name}"
        if self.year:
            title += f" ({self.frame} {self.year})"
        ax1.set_title(title)
        ax1.legend(loc="best", fontsize="small")
        ax1.axhline(0, color="gray", linewidth=0.5)
        fig1.tight_layout()

        # --- Output decomposition panel ---
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

        # --- Input decomposition panel ---
        fig3, ax3 = plt.subplots(figsize=style.figsize, dpi=style.dpi)

        for i, varname in enumerate(inputs_available):
            ax3.plot(
                _plot_time(comps[varname]),
                comps[varname],
                label=varname,
                color=colors[i % len(colors)],
            )

        ax3.set_xlabel("Time")
        ax3.set_ylabel("Cumulative (mm)")
        ax3.set_title(f"Water Input Decomposition — {self.run.name}")
        ax3.legend(loc="best", fontsize="small")
        fig3.tight_layout()

        # --- Storage decomposition panel ---
        fig4, ax4 = plt.subplots(figsize=style.figsize, dpi=style.dpi)
        storage_available = [v for v in bc.storages if v in storage_comps]

        for i, varname in enumerate(storage_available):
            ax4.plot(
                _plot_time(storage_comps[varname]),
                storage_comps[varname],
                label=varname,
                color=colors[i % len(colors)],
            )

        ax4.set_xlabel("Time")
        ax4.set_ylabel("Change (mm)")
        ax4.set_title(f"Water Storage Decomposition — {self.run.name}")
        ax4.legend(loc="best", fontsize="small")
        ax4.axhline(0, color="gray", linewidth=0.5)
        fig4.tight_layout()

        return fig1, fig2, fig3, fig4
    
    def _plot_faceted(
        self,
        comps: dict[str, xr.DataArray],
        storage_comps: dict[str, xr.DataArray],
        bc: WaterBalanceConfig,
        style,
    ) -> tuple[plt.Figure, plt.Figure, plt.Figure, plt.Figure]:
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
        fig3, axes3 = create_facet_figure(len(units), style)
        fig4, axes4 = create_facet_figure(len(units), style)
        
        # Plot each subgrid unit
        res_all = self.residual()
        model_res_all, model_mode = self.aligned_model_residual()
        diff_all = self.residual_difference()
        show_diff = (
            model_res_all is not None
            and diff_all is not None
            and self._has_meaningful_model_residual(model_res_all)
        )

        for unit_id, ax1, ax2, ax3, ax4 in zip(
            units,
            axes1.flat,
            axes2.flat,
            axes3.flat,
            axes4.flat,
        ):
            # Select this unit from all components
            comps_unit = {k: v.sel({self.by: unit_id}) for k, v in comps.items()}
            storage_unit = {
                k: v.sel({self.by: unit_id})
                for k, v in storage_comps.items()
            }
            
            # --- Cumulative panel ---
            inputs_available = [v for v in bc.inputs if v in comps_unit]
            if inputs_available:
                total_in = sum(comps_unit[v] for v in inputs_available)
                ax1.plot(
                    _plot_time(total_in), total_in, label="P", color="blue", linewidth=1
                )
            
            outputs_available = [v for v in self._active_output_terms() if v in comps_unit]
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
            res_unit = res_all.sel({self.by: unit_id})
            ax1.plot(_plot_time(res_unit), res_unit, label="Res", color="black", linestyle="--", linewidth=1)

            if model_res_all is not None:
                model_res_unit = model_res_all.sel({self.by: unit_id})
                label = "Model"
                if model_mode is not None:
                    label += f" ({model_mode})"
                ax1.plot(
                    _plot_time(model_res_unit),
                    model_res_unit,
                    label=label,
                    color="purple",
                    linestyle=":",
                    linewidth=1,
                )

                if show_diff:
                    diff_unit = diff_all.sel({self.by: unit_id})
                    ax1.plot(
                        _plot_time(diff_unit),
                        diff_unit,
                        label="Diff",
                        color="orange",
                        linestyle="-.",
                        linewidth=1,
                    )
            
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

            # --- Input decomposition panel ---
            for i, varname in enumerate(inputs_available):
                ax3.plot(
                    _plot_time(comps_unit[varname]),
                    comps_unit[varname],
                    label=varname,
                    color=colors[i % len(colors)],
                    linewidth=1,
                )

            ax3.set_xlabel("Time", fontsize="small")
            ax3.set_ylabel("Cumulative (mm)", fontsize="small")
            ax3.set_title(format_subgrid_title(self.by, unit_id), fontsize="medium")
            ax3.legend(loc="best", fontsize="x-small")
            ax3.tick_params(labelsize="small")

            # --- Storage decomposition panel ---
            storage_available = [v for v in bc.storages if v in storage_unit]
            for i, varname in enumerate(storage_available):
                ax4.plot(
                    _plot_time(storage_unit[varname]),
                    storage_unit[varname],
                    label=varname,
                    color=colors[i % len(colors)],
                    linewidth=1,
                )

            ax4.set_xlabel("Time", fontsize="small")
            ax4.set_ylabel("Change (mm)", fontsize="small")
            ax4.set_title(format_subgrid_title(self.by, unit_id), fontsize="medium")
            ax4.legend(loc="best", fontsize="x-small")
            ax4.axhline(0, color="gray", linewidth=0.5)
            ax4.tick_params(labelsize="small")
        
        # Hide unused subplots
        for ax1 in axes1.flat[len(units):]:
            ax1.set_visible(False)
        for ax2 in axes2.flat[len(units):]:
            ax2.set_visible(False)
        for ax3 in axes3.flat[len(units):]:
            ax3.set_visible(False)
        for ax4 in axes4.flat[len(units):]:
            ax4.set_visible(False)
        
        # Overall titles
        title_base = f"Water Balance — {self.run.name}"
        if self.year:
            title_base += f" ({self.frame} {self.year})"
        
        fig1.suptitle(f"{title_base} by {self.by}", fontsize="large")
        fig2.suptitle(f"Water Output Decomposition — {self.run.name} by {self.by}", fontsize="large")
        fig3.suptitle(f"Water Input Decomposition — {self.run.name} by {self.by}", fontsize="large")
        fig4.suptitle(f"Water Storage Decomposition — {self.run.name} by {self.by}", fontsize="large")
        
        fig1.tight_layout()
        fig2.tight_layout()
        fig3.tight_layout()
        fig4.tight_layout()
        
        return fig1, fig2, fig3, fig4
