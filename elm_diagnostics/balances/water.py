# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Water balance diagnostics."""

from __future__ import annotations

import logging
from typing import Any

import matplotlib.pyplot as plt
import xarray as xr

from elm_diagnostics.balances.base import Balance
from elm_diagnostics.config.schema import PlotStyleConfig, WaterBalanceConfig
from elm_diagnostics.io.units import convert_water_to_mm
from elm_diagnostics.plots._common import hide_unused_axes
from elm_diagnostics.plots.subgrid_helpers import (
    create_facet_figure,
    format_subgrid_title,
    get_subgrid_units,
)
from elm_diagnostics.time.integration import (
    cumulative_integral,
    storage_change,
)
from elm_diagnostics.time.plotting import plot_times

logger = logging.getLogger(__name__)


class WaterBalance(Balance):
    """Column water balance: dS/dt = P - ET - R.

    Default equation (from ELM BalanceCheckMod.F90):
        residual = cumul(inputs) - cumul(outputs) - dS

    where:

    - inputs  = RAIN + SNOW
    - outputs = QFLX_EVAP_TOT + QOVER + QDRAI + QDRAI_PERCH
      (QFLX_EVAP_TOT = QSOIL + QVEGE + QVEGT if not available)
    - dS      = change in (SOILLIQ + SOILICE + H2OSNO + H2OCAN + H2OSFC)
      (SOILLIQ and SOILICE are summed over vertical levels)
    """

    def _get_balance_config(self) -> WaterBalanceConfig:
        return self.config.balances.water

    def _get_variable_names(self) -> list[str]:
        bc = self._balance_config
        return bc.inputs + bc.outputs + bc.storages

    def _compute_components(self) -> dict[str, xr.DataArray]:
        """Return cumulative water balance components (all in mm)."""
        bc = self._balance_config
        result = {}
        storage_components: dict[str, xr.DataArray] = {}

        # Dataset carrying time_bounds for flux integration. (A
        # DataArray.to_dataset() would NOT carry time_bounds, since it is a
        # separate data variable, so bounds_dataset() is the correct source.)
        parent_ds = self.run.bounds_dataset()

        # Cumulative inputs
        for varname in bc.inputs:
            da = self._get_var(varname)
            da = self._select_year(da)
            result[varname] = cumulative_integral(da, parent_ds)
            logger.info("Input variable '%s' included in balance components.", varname)

        # Cumulative outputs
        for varname in bc.outputs:
            try:
                da = self._get_var(varname)
                da = self._select_year(da)
                result[varname] = cumulative_integral(da, parent_ds)
                logger.info(
                    "Output variable '%s' included in balance components.", varname
                )
            except KeyError:
                logger.warning("Missing expected water output variable '%s'", varname)

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
                da = convert_water_to_mm(da)

                da = self._select_year(da)
                storage_components[varname] = storage_change(da)
                logger.info(
                    "Storage component '%s' included in storage decomposition.", varname
                )
                if total_storage is None:
                    total_storage = da
                else:
                    total_storage = total_storage + da
            except KeyError:
                logger.warning("Missing expected water storage variable '%s'", varname)

        if total_storage is not None:
            ds_change = storage_change(total_storage)
            ds_change.attrs["long_name"] = "change in total water storage"
            ds_change.attrs["units"] = "mm"
            ds_change.name = "dS"
            result["dS"] = ds_change

        self._storage_components_cache = storage_components

        return result

    def cumulative(self) -> xr.Dataset:
        """Return cumulative balance components as a Dataset."""
        return xr.Dataset(self.components())

    def _compute_residual(self) -> xr.DataArray:
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

    def _storage_decomposition_components(self) -> dict[str, xr.DataArray]:
        """Return per-storage cumulative change components in mm.

        Each returned variable is a storage-change time series with the same
        definition used for dS: S(t) - S(0).
        """
        # _compute_components() fills this cache alongside the components, so
        # making sure the components are current is enough.
        self.components()
        return self._storage_components_cache

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
        style: PlotStyleConfig,
    ) -> tuple[plt.Figure, plt.Figure, plt.Figure, plt.Figure]:
        """Plot single water balance (no faceting)."""
        name = self.run.name
        title = f"Water Balance — {name}"
        if self.year:
            title += f" ({self.frame} {self.year})"

        fig1, ax1 = plt.subplots(figsize=style.figsize, dpi=style.dpi)
        _plot_budget_lines(ax1, comps, self.residual(), bc, _SINGLE_BUDGET_LABELS)
        _decorate(ax1, "Cumulative (mm)", title, zero_line=True)
        fig1.tight_layout()

        fig2, ax2 = plt.subplots(figsize=style.figsize, dpi=style.dpi)
        _plot_series(ax2, comps, _available(bc.outputs, comps))
        _decorate(ax2, "Cumulative (mm)", f"Water Output Decomposition — {name}")
        fig2.tight_layout()

        fig3, ax3 = plt.subplots(figsize=style.figsize, dpi=style.dpi)
        _plot_series(ax3, comps, _available(bc.inputs, comps))
        _decorate(ax3, "Cumulative (mm)", f"Water Input Decomposition — {name}")
        fig3.tight_layout()

        fig4, ax4 = plt.subplots(figsize=style.figsize, dpi=style.dpi)
        _plot_storage(ax4, storage_comps, _available(bc.storages, storage_comps))
        _decorate(
            ax4, "Change (mm)", f"Water Storage Decomposition — {name}", zero_line=True
        )
        fig4.tight_layout()

        return fig1, fig2, fig3, fig4

    def _plot_faceted(
        self,
        comps: dict[str, xr.DataArray],
        storage_comps: dict[str, xr.DataArray],
        bc: WaterBalanceConfig,
        style: PlotStyleConfig,
    ) -> tuple[plt.Figure, plt.Figure, plt.Figure, plt.Figure]:
        """Plot faceted water balance by sub-gridcell dimension."""
        # Get subgrid units from first component
        first_comp = next(iter(comps.values()))
        units = get_subgrid_units(first_comp, self.by)

        fig1, axes1 = create_facet_figure(len(units), style)
        fig2, axes2 = create_facet_figure(len(units), style)
        fig3, axes3 = create_facet_figure(len(units), style)
        fig4, axes4 = create_facet_figure(len(units), style)

        residual = self.residual()
        for unit_id, ax1, ax2, ax3, ax4 in zip(
            units, axes1.flat, axes2.flat, axes3.flat, axes4.flat
        ):
            comps_unit = {k: v.sel({self.by: unit_id}) for k, v in comps.items()}
            storage_unit = {
                k: v.sel({self.by: unit_id}) for k, v in storage_comps.items()
            }
            unit_title = format_subgrid_title(self.by, unit_id)

            _plot_budget_lines(
                ax1,
                comps_unit,
                residual.sel({self.by: unit_id}),
                bc,
                _FACET_BUDGET_LABELS,
                linewidth=1,
            )
            _decorate(ax1, "Cumulative (mm)", unit_title, zero_line=True, facet=True)

            _plot_series(
                ax2, comps_unit, _available(bc.outputs, comps_unit), linewidth=1
            )
            _decorate(ax2, "Cumulative (mm)", unit_title, facet=True)

            _plot_series(
                ax3, comps_unit, _available(bc.inputs, comps_unit), linewidth=1
            )
            _decorate(ax3, "Cumulative (mm)", unit_title, facet=True)

            _plot_storage(
                ax4,
                storage_unit,
                _available(bc.storages, storage_unit),
                linewidth=1,
            )
            _decorate(ax4, "Change (mm)", unit_title, zero_line=True, facet=True)

        for axes in (axes1, axes2, axes3, axes4):
            hide_unused_axes(axes, len(units))

        name = self.run.name
        title_base = f"Water Balance — {name}"
        if self.year:
            title_base += f" ({self.frame} {self.year})"

        fig1.suptitle(f"{title_base} by {self.by}", fontsize="large")
        fig2.suptitle(
            f"Water Output Decomposition — {name} by {self.by}", fontsize="large"
        )
        fig3.suptitle(
            f"Water Input Decomposition — {name} by {self.by}", fontsize="large"
        )
        fig4.suptitle(
            f"Water Storage Decomposition — {name} by {self.by}", fontsize="large"
        )

        for fig in (fig1, fig2, fig3, fig4):
            fig.tight_layout()

        return fig1, fig2, fig3, fig4


_SINGLE_BUDGET_LABELS = (
    "P (total input)",
    "Total output",
    "dS (storage change)",
    "Residual",
)
_FACET_BUDGET_LABELS = ("P", "Out", "dS", "Res")


def _available(names: list[str], comps: dict[str, xr.DataArray]) -> list[str]:
    """Names from ``names`` (in order) that have a component."""
    return [v for v in names if v in comps]


def _plot_budget_lines(
    ax: plt.Axes,
    comps: dict[str, xr.DataArray],
    residual: xr.DataArray,
    bc: WaterBalanceConfig,
    labels: tuple[str, str, str, str],
    **line_kw,
) -> None:
    """Draw total input, total output, dS, and residual on one axes."""
    inputs = _available(bc.inputs, comps)
    if inputs:
        total_in = sum(comps[v] for v in inputs)
        ax.plot(
            plot_times(total_in), total_in, label=labels[0], color="blue", **line_kw
        )

    outputs = _available(bc.outputs, comps)
    if outputs:
        total_out = sum(comps[v] for v in outputs)
        ax.plot(
            plot_times(total_out), total_out, label=labels[1], color="red", **line_kw
        )

    if "dS" in comps:
        ax.plot(
            plot_times(comps["dS"]),
            comps["dS"],
            label=labels[2],
            color="green",
            **line_kw,
        )

    ax.plot(
        plot_times(residual),
        residual,
        label=labels[3],
        color="black",
        linestyle="--",
        **line_kw,
    )


def _plot_series(
    ax: plt.Axes, comps: dict[str, xr.DataArray], names: list[str], **line_kw
) -> None:
    """Draw one line per named component, colored by tab10 position."""
    colors = plt.cm.tab10.colors
    for i, varname in enumerate(names):
        ax.plot(
            plot_times(comps[varname]),
            comps[varname],
            label=varname,
            color=colors[i % len(colors)],
            **line_kw,
        )


def _plot_storage(
    ax: plt.Axes, storage_comps: dict[str, xr.DataArray], names: list[str], **line_kw
) -> None:
    """Draw per-storage changes plus their bold black total."""
    _plot_series(ax, storage_comps, names, **line_kw)
    if names:
        total = sum(storage_comps[v] for v in names)
        ax.plot(plot_times(total), total, label="Total", color="black", linewidth=2.5)


def _decorate(
    ax: plt.Axes,
    ylabel: str,
    title: str,
    *,
    zero_line: bool = False,
    facet: bool = False,
) -> None:
    """Axis labels, title, legend, and optional zero line; smaller when faceted."""
    label_kw: dict[str, Any] = {"fontsize": "small"} if facet else {}
    title_kw: dict[str, Any] = {"fontsize": "medium"} if facet else {}
    ax.set_xlabel("Time", **label_kw)
    ax.set_ylabel(ylabel, **label_kw)
    ax.set_title(title, **title_kw)
    ax.legend(loc="best", fontsize="x-small" if facet else "small")
    if zero_line:
        ax.axhline(0, color="gray", linewidth=0.5)
    if facet:
        ax.tick_params(labelsize="small")
