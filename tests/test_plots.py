"""Tests for general variable plotting functions."""

import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pytest
import yaml

matplotlib.use("Agg")

from elm_diagnostics.config.schema import load_config
from elm_diagnostics.io.run import Comparison, Run
from elm_diagnostics.plots import (
    plot_anomaly,
    plot_diurnal,
    plot_histogram,
    plot_hovmuller,
    plot_seasonal,
    plot_timeseries,
)
from tests.fixtures.synthetic_elm import (
    make_vertical_profile_dataset,
    make_single_point_dataset,
    make_water_balance_dataset,
    save_as_elm_files,
)


@pytest.fixture
def plot_run():
    ds = make_water_balance_dataset(start_year=2000, n_months=36)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="plot_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


@pytest.fixture
def short_run():
    ds = make_water_balance_dataset(start_year=2000, n_months=12)
    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="short_test", tape="h0")
        run = Run(tmpdir)
        yield run
        run.close()


def test_timeseries(short_run):
    fig = plot_timeseries(short_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_timeseries_multivar(short_run):
    """Timeseries works for different variable types."""
    for varname in ["RAIN", "SOILLIQ", "QFLX_EVAP_TOT"]:
        fig = plot_timeseries(short_run, varname)
        assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_timeseries_vertical_depth_coloring_and_legend():
    """Vertical variables should render one line per depth with a legend."""
    n_months = 24
    n_levels = 12
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.5, 1.5, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    ds = ds.assign_coords(levgrnd=np.linspace(0.02, 3.0, n_levels))
    ds["levgrnd"].attrs["units"] = "m"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="vertical_plot_test", tape="h0")
        run = Run(tmpdir)
        fig = plot_timeseries(run, "SOILLIQ")
        ax = fig.axes[0]

        assert len(ax.lines) == n_levels
        assert ax.get_legend() is not None
        # Legend is intentionally thinned for readability.
        assert len(ax.get_legend().get_texts()) <= 8

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_seasonal(plot_run):
    fig = plot_seasonal(plot_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_seasonal_vertical_depth_coloring_and_legend():
    """Seasonal plots should render one colored line per depth with a legend."""
    n_months = 24
    n_levels = 12
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.5, 1.5, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    ds = ds.assign_coords(levgrnd=np.linspace(0.02, 3.0, n_levels))
    ds["levgrnd"].attrs["units"] = "m"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="vertical_seasonal_test", tape="h0")
        run = Run(tmpdir)
        fig = plot_seasonal(run, "SOILLIQ")
        ax = fig.axes[0]

        assert len(ax.lines) == n_levels
        assert ax.get_legend() is not None
        assert len(ax.get_legend().get_texts()) <= 8
        legend_texts = [txt.get_text() for txt in ax.get_legend().get_texts()]
        assert any(" m" in txt for txt in legend_texts)

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_seasonal_short_data(short_run):
    """Seasonal works even with only 12 months (one year)."""
    fig = plot_seasonal(short_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_anomaly(plot_run):
    fig = plot_anomaly(plot_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_histogram(short_run):
    fig = plot_histogram(short_run, "RAIN")
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_histogram_count_mode(short_run):
    fig = plot_histogram(short_run, "RAIN", density=False)
    assert fig is not None
    import matplotlib.pyplot as plt

    plt.close("all")


def test_diurnal(short_run):
    """Diurnal plot with monthly data should show 'not sub-daily' message."""
    fig = plot_diurnal(short_run, "RAIN")
    assert fig is not None
    # Should complete without error, even though data isn't sub-daily
    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_vertical_uses_depth_axis():
    """Hovmuller plot should render a mesh for vertical variables."""
    ds = make_vertical_profile_dataset(n_months=24, n_levels=10)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="hovmuller_test", tape="h0")
        run = Run(tmpdir)

        fig = plot_hovmuller(run, "SOILLIQ")
        ax = fig.axes[0]

        assert fig is not None
        assert ax.collections  # pcolormesh collection exists
        assert "Depth" in ax.get_ylabel()

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_levgrnd_has_zero_top_and_downward_depth():
    """levgrnd Hovmuller should use depth with 0 at top, increasing downward."""
    ds = make_vertical_profile_dataset(n_months=24, n_levels=10)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="hov_depth_test", tape="h0")
        run = Run(tmpdir)

        fig = plot_hovmuller(run, "SOILLIQ")
        ax = fig.axes[0]

        assert "Depth" in ax.get_ylabel()
        # Inverted axis means smaller values (near zero depth) appear at the top.
        y0, y1 = ax.get_ylim()
        assert y0 > y1

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_levgrnd_index_fallback_still_depth_oriented():
    """If levgrnd uses indices only, Hovmuller should still be depth-oriented."""
    n_months = 24
    n_levels = 8
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.4, 1.2, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="hov_index_test", tape="h0")
        run = Run(tmpdir)

        fig = plot_hovmuller(run, "SOILLIQ")
        ax = fig.axes[0]

        assert "Depth" in ax.get_ylabel()
        y0, y1 = ax.get_ylim()
        assert y0 > y1

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_max_depth_m_clips_when_coordinate_available():
    """Configured max_depth_m should clip Hovmuller extent with physical coordinates."""
    ds = make_vertical_profile_dataset(n_months=24, n_levels=10)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="hov_max_depth_test", tape="h0")
        run = Run(tmpdir)

        cfg_default = load_config()
        fig_full = plot_hovmuller(run, "SOILLIQ", config=cfg_default)
        deep_full = max(fig_full.axes[0].get_ylim())

        cfg_path = Path(tmpdir) / "cfg.yaml"
        cfg_path.write_text(yaml.safe_dump({"plots": {"hovmuller": {"max_depth_m": 0.6}}}))
        cfg_limited = load_config(path=cfg_path)
        fig_limited = plot_hovmuller(run, "SOILLIQ", config=cfg_limited)
        deep_limited = max(fig_limited.axes[0].get_ylim())

        assert deep_limited < deep_full
        assert deep_limited < 1.2

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_max_depth_m_warns_and_ignored_for_index_axis():
    """Configured max_depth_m is ignored with warning when only index-like axis exists."""
    n_months = 24
    n_levels = 8
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.4, 1.2, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="hov_index_max_depth_test", tape="h0")
        run = Run(tmpdir)

        cfg_default = load_config()
        fig_full = plot_hovmuller(run, "SOILLIQ", config=cfg_default)
        deep_full = max(fig_full.axes[0].get_ylim())

        cfg_path = Path(tmpdir) / "cfg.yaml"
        cfg_path.write_text(yaml.safe_dump({"plots": {"hovmuller": {"max_depth_m": 0.3}}}))
        cfg_limited = load_config(path=cfg_path)

        with pytest.warns(UserWarning, match="max_depth_m=.*ignored"):
            fig_limited = plot_hovmuller(run, "SOILLIQ", config=cfg_limited)
        deep_limited = max(fig_limited.axes[0].get_ylim())

        assert deep_limited == pytest.approx(deep_full)

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_general_additional_dimension_supports_non_vertical_names():
    """Expanded plotting should work for any additional non-space dimension."""
    n_months = 24
    n_levels = 9
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.4, 1.2, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "LAYER_VAR": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    ds = ds.rename({"levgrnd": "layer"})
    ds = ds.assign_coords(layer_depth=("layer", np.linspace(0.05, 2.5, n_levels)))
    ds["layer_depth"].attrs["units"] = "m"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="layered_test", tape="h0")
        run = Run(tmpdir)

        fig_ts = plot_timeseries(run, "LAYER_VAR")
        ax_ts = fig_ts.axes[0]
        assert len(ax_ts.lines) == n_levels
        assert ax_ts.get_legend() is not None
        legend_texts = [txt.get_text() for txt in ax_ts.get_legend().get_texts()]
        assert any("layer_depth=" in txt for txt in legend_texts)

        fig_seasonal = plot_seasonal(run, "LAYER_VAR")
        ax_seasonal = fig_seasonal.axes[0]
        assert len(ax_seasonal.lines) == n_levels

        fig_hov = plot_hovmuller(run, "LAYER_VAR")
        ax_hov = fig_hov.axes[0]
        assert ax_hov.collections
        assert "Depth" in ax_hov.get_ylabel()

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_timeseries_single_title_and_ylabel_include_long_name_and_varname():
    n_months = 24
    data = np.linspace(0.0, 1.0, n_months)
    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "RAIN": {
                "data": data,
                "units": "mm/s",
                "long_name": "Rainfall rate",
                "cell_methods": "time: mean",
            }
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="title_ts_test", tape="h0")
        run = Run(tmpdir)
        fig = plot_timeseries(run, "RAIN")
        ax = fig.axes[0]

        assert "Rainfall rate" in ax.get_title()
        assert "\n" in ax.get_title()
        assert ax.get_ylabel() == "RAIN (mm/s)"

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_seasonal_single_title_and_ylabel_include_long_name_and_varname():
    n_months = 24
    data = np.linspace(0.0, 1.0, n_months)
    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "RAIN": {
                "data": data,
                "units": "mm/s",
                "long_name": "Rainfall rate",
                "cell_methods": "time: mean",
            }
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="title_seasonal_test", tape="h0")
        run = Run(tmpdir)
        fig = plot_seasonal(run, "RAIN")
        ax = fig.axes[0]

        assert "Rainfall rate" in ax.get_title()
        assert "\n" in ax.get_title()
        assert ax.get_ylabel() == "RAIN (mm/s)"

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_title_includes_long_name_second_line():
    n_months = 24
    n_levels = 10
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.5, 1.5, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "long_name": "Volumetric liquid soil water",
                "cell_methods": "time: point",
            }
        },
    )
    ds = ds.assign_coords(levgrnd=np.linspace(0.02, 3.0, n_levels))
    ds["levgrnd"].attrs["units"] = "m"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="title_hov_hist_test", tape="h0")
        run = Run(tmpdir, chunk_mode="off")

        fig_hov = plot_hovmuller(run, "SOILLIQ")
        ax_hov = fig_hov.axes[0]
        assert "Volumetric liquid soil water" in ax_hov.get_title()
        assert "\n" in ax_hov.get_title()

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_color_limit_quantile_reduces_outlier_influence():
    """Quantile color limits should reduce outlier-driven vmax."""
    n_months = 24
    n_levels = 10
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.5, 1.5, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]
    data[0, 0] = 500.0

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    ds = ds.assign_coords(levgrnd=np.linspace(0.02, 3.0, n_levels))
    ds["levgrnd"].attrs["units"] = "m"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="hov_quantile_color_test", tape="h0")
        run = Run(tmpdir)

        fig_full = plot_hovmuller(run, "SOILLIQ", config=load_config())
        vmax_full = fig_full.axes[0].collections[0].get_clim()[1]
        assert fig_full.axes[0].collections[0].colorbar.extend == "neither"

        cfg_path = Path(tmpdir) / "cfg_quantile.yaml"
        cfg_path.write_text(
            yaml.safe_dump(
                {
                    "plots": {
                        "hovmuller": {
                            "color_limit_method": "quantile",
                            "color_limit_quantile_low": 2.0,
                            "color_limit_quantile_high": 98.0,
                        }
                    }
                }
            )
        )
        cfg_quantile = load_config(path=cfg_path)
        fig_quantile = plot_hovmuller(run, "SOILLIQ", config=cfg_quantile)
        vmax_quantile = fig_quantile.axes[0].collections[0].get_clim()[1]

        assert vmax_quantile < vmax_full
        assert fig_quantile.axes[0].collections[0].colorbar.extend in {"min", "max", "both"}

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_color_limit_sigma_clip_reduces_outlier_influence():
    """Sigma-clip color limits should reduce outlier-driven vmax."""
    n_months = 24
    n_levels = 10
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.5, 1.5, n_levels)
    data = np.sin(phase)[:, None] * profile[None, :]
    data[0, 0] = 500.0

    ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    ds = ds.assign_coords(levgrnd=np.linspace(0.02, 3.0, n_levels))
    ds["levgrnd"].attrs["units"] = "m"

    with tempfile.TemporaryDirectory() as tmpdir:
        save_as_elm_files(ds, Path(tmpdir), casename="hov_sigma_color_test", tape="h0")
        run = Run(tmpdir)

        fig_full = plot_hovmuller(run, "SOILLIQ", config=load_config())
        vmax_full = fig_full.axes[0].collections[0].get_clim()[1]

        cfg_path = Path(tmpdir) / "cfg_sigma.yaml"
        cfg_path.write_text(
            yaml.safe_dump(
                {
                    "plots": {
                        "hovmuller": {
                            "color_limit_method": "sigma_clip",
                            "color_limit_sigma": 2.0,
                        }
                    }
                }
            )
        )
        cfg_sigma = load_config(path=cfg_path)
        fig_sigma = plot_hovmuller(run, "SOILLIQ", config=cfg_sigma)
        vmax_sigma = fig_sigma.axes[0].collections[0].get_clim()[1]

        assert vmax_sigma < vmax_full

        run.close()

    import matplotlib.pyplot as plt

    plt.close("all")


def test_hovmuller_comparison_uses_shared_color_limits_with_robust_method():
    """Comparison Hovmuller panels should share vmin/vmax under robust scaling."""
    n_months = 24
    n_levels = 10
    phase = np.linspace(0.0, 2.0 * np.pi, n_months)
    profile = np.linspace(0.5, 1.5, n_levels)
    base_data = np.sin(phase)[:, None] * profile[None, :]
    exp_data = 1.2 * base_data
    exp_data[1, 1] = 700.0

    base_ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": base_data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    exp_ds = make_single_point_dataset(
        start_year=2000,
        n_months=n_months,
        variables={
            "SOILLIQ": {
                "data": exp_data,
                "units": "kg/m2",
                "cell_methods": "time: point",
            }
        },
    )
    lev = np.linspace(0.02, 3.0, n_levels)
    base_ds = base_ds.assign_coords(levgrnd=lev)
    exp_ds = exp_ds.assign_coords(levgrnd=lev)
    base_ds["levgrnd"].attrs["units"] = "m"
    exp_ds["levgrnd"].attrs["units"] = "m"

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "base"
        exp_dir = Path(tmpdir) / "exp"
        save_as_elm_files(base_ds, base_dir, casename="base_case", tape="h0")
        save_as_elm_files(exp_ds, exp_dir, casename="exp_case", tape="h0")

        base_run = Run(base_dir)
        exp_run = Run(exp_dir)
        comp = Comparison(base_run, exp_run)

        cfg_path = Path(tmpdir) / "cfg_comp_quantile.yaml"
        cfg_path.write_text(
            yaml.safe_dump(
                {
                    "plots": {
                        "hovmuller": {
                            "color_limit_method": "quantile",
                            "color_limit_quantile_low": 2.0,
                            "color_limit_quantile_high": 98.0,
                        }
                    }
                }
            )
        )
        cfg_quantile = load_config(path=cfg_path)

        fig = plot_hovmuller(comp, "SOILLIQ", config=cfg_quantile)
        clim_base = fig.axes[0].collections[0].get_clim()
        clim_exp = fig.axes[1].collections[0].get_clim()

        assert clim_base == pytest.approx(clim_exp)
        assert fig.axes[0].collections[0].colorbar.extend in {"min", "max", "both"}
        assert fig.axes[1].collections[0].colorbar.extend in {"min", "max", "both"}

        base_run.close()
        exp_run.close()

    import matplotlib.pyplot as plt

    plt.close("all")
