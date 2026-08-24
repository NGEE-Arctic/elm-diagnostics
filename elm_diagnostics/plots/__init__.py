# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""General-purpose variable plotting functions."""

from elm_diagnostics.plots.anomaly import plot_anomaly
from elm_diagnostics.plots.diurnal import plot_diurnal
from elm_diagnostics.plots.histogram import plot_histogram
from elm_diagnostics.plots.hovmuller import plot_hovmuller
from elm_diagnostics.plots.seasonal import plot_seasonal
from elm_diagnostics.plots.spatial import plot_map, plot_map_comparison
from elm_diagnostics.plots.timeseries import plot_timeseries

__all__ = [
    "plot_anomaly",
    "plot_diurnal",
    "plot_histogram",
    "plot_hovmuller",
    "plot_map",
    "plot_map_comparison",
    "plot_seasonal",
    "plot_timeseries",
]
