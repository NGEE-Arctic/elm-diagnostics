"""General-purpose variable plotting functions."""

from elm_diagnostics.plots.timeseries import plot_timeseries
from elm_diagnostics.plots.seasonal import plot_seasonal
from elm_diagnostics.plots.anomaly import plot_anomaly
from elm_diagnostics.plots.histogram import plot_histogram
from elm_diagnostics.plots.diurnal import plot_diurnal
from elm_diagnostics.plots.hovmuller import plot_hovmuller

__all__ = [
    "plot_timeseries",
    "plot_seasonal",
    "plot_anomaly",
    "plot_histogram",
    "plot_diurnal",
    "plot_hovmuller",
]
