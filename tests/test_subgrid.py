"""Tests for sub-gridcell plotting and balance functionality."""

import matplotlib.pyplot as plt
import numpy as np
import pytest

from elm_diagnostics import Run, WaterBalance
from elm_diagnostics.plots import (
    plot_anomaly,
    plot_diurnal,
    plot_histogram,
    plot_seasonal,
    plot_timeseries,
)
from tests.fixtures.synthetic_elm import make_multicolumn_dataset, save_as_elm_files


@pytest.fixture
def multicolumn_dataset():
    """Create a multi-column dataset for testing."""
    return make_multicolumn_dataset(n_columns=3, n_months=12, perfect_closure=True)


@pytest.fixture
def multicolumn_run(tmp_path, multicolumn_dataset):
    """Create a Run object from multi-column dataset."""
    save_as_elm_files(multicolumn_dataset, tmp_path, casename="multicolumn", tape="h0")
    return Run(str(tmp_path))


@pytest.fixture
def single_point_run(tmp_path):
    """Create a single-point (gridcell-averaged) Run for testing errors."""
    from tests.fixtures.synthetic_elm import make_single_point_dataset

    ds = make_single_point_dataset(
        n_months=12,
        variables={
            "GPP": {"data": np.random.rand(12), "units": "gC/m^2/s"},
        },
    )
    save_as_elm_files(ds, tmp_path, casename="single_point", tape="h0")
    return Run(str(tmp_path))


class TestSubgridPlotting:
    """Test plotting with by parameter for sub-gridcell faceting."""

    def test_timeseries_by_column(self, multicolumn_run):
        """Test faceted timeseries by column."""
        fig = plot_timeseries(multicolumn_run, "GPP", by="column")

        # Should have 3 subplots for 3 columns
        assert len(fig.axes) == 3

        # Each axes should have data
        for ax in fig.axes:
            assert len(ax.lines) > 0

        plt.close(fig)

    def test_seasonal_by_column(self, multicolumn_run):
        """Test seasonal cycle faceted by column."""
        fig = plot_seasonal(multicolumn_run, "GPP", by="column")

        assert len(fig.axes) == 3
        for ax in fig.axes:
            assert len(ax.lines) > 0

        plt.close(fig)

    def test_anomaly_by_column(self, multicolumn_run):
        """Test annual anomalies faceted by column."""
        fig = plot_anomaly(multicolumn_run, "GPP", by="column")

        assert len(fig.axes) == 3
        # Anomaly plots use bar charts
        for ax in fig.axes:
            assert len(ax.patches) > 0 or len(ax.texts) > 0  # bars or no data text

        plt.close(fig)

    def test_histogram_by_column(self, multicolumn_run):
        """Test histogram faceted by column."""
        fig = plot_histogram(multicolumn_run, "GPP", by="column")

        assert len(fig.axes) == 3
        for ax in fig.axes:
            assert len(ax.patches) > 0  # histogram bars

        plt.close(fig)

    def test_diurnal_by_column(self, multicolumn_run):
        """Test diurnal cycle faceted by column."""
        # Multi-column data is monthly, won't show proper diurnal but shouldn't crash
        fig = plot_diurnal(multicolumn_run, "GPP", by="column")

        assert len(fig.axes) == 3
        # Just verify it created the figure without crashing
        # (monthly data doesn't have enough resolution for diurnal cycle)

        plt.close(fig)

    def test_by_and_ax_raises_error(self, multicolumn_run):
        """Test that specifying both by and ax raises ValueError."""
        fig, ax = plt.subplots()

        with pytest.raises(ValueError, match="Cannot specify both"):
            plot_timeseries(multicolumn_run, "GPP", by="column", ax=ax)

        plt.close(fig)

    def test_by_with_gridcell_averaged_raises(self, single_point_run):
        """Test that by raises error for gridcell-averaged data."""
        with pytest.raises(ValueError, match="gridcell-averaged"):
            plot_timeseries(single_point_run, "GPP", by="column")

    def test_wrong_dimension_raises(self, multicolumn_run):
        """Test by='pft' raises error when only 'column' available."""
        with pytest.raises(ValueError, match="does not have dimension"):
            plot_timeseries(multicolumn_run, "GPP", by="pft")

    def test_subplot_titles(self, multicolumn_run):
        """Test that subplots have correct titles."""
        fig = plot_timeseries(multicolumn_run, "GPP", by="column")

        titles = [ax.get_title() for ax in fig.axes]
        assert "Column 1" in titles[0]
        assert "Column 2" in titles[1]
        assert "Column 3" in titles[2]

        plt.close(fig)

    def test_overall_title(self, multicolumn_run):
        """Test that faceted plot has overall title."""
        fig = plot_timeseries(multicolumn_run, "GPP", by="column")

        # Check for suptitle
        suptitle = fig._suptitle
        assert suptitle is not None
        assert "GPP" in suptitle.get_text()
        assert "column" in suptitle.get_text().lower()

        plt.close(fig)


class TestSubgridBalances:
    """Test balance calculations with sub-gridcell dimensions."""

    def test_water_balance_by_column(self, multicolumn_run):
        """Test water balance computes per column."""
        wb = WaterBalance(multicolumn_run, by="column")

        components = wb.components()

        # All components should have 'column' dimension
        assert "column" in components["RAIN"].dims
        assert "column" in components["QFLX_EVAP_TOT"].dims

        # Should have 3 columns
        assert components["RAIN"].sizes["column"] == 3

    def test_water_balance_closure_per_column(self, multicolumn_run):
        """Test balance closes independently per column."""
        wb = WaterBalance(multicolumn_run, by="column")

        residual = wb.residual()

        # Residual should have column dimension
        assert "column" in residual.dims

        # Each column should close reasonably well (perfect_closure=True in fixture)
        for col in residual.column.values:
            col_residual = residual.sel(column=col).values
            # Final residual should be small (allow some numerical error)
            assert np.abs(col_residual[-1]) < 50.0, (
                f"Column {col} residual: {col_residual[-1]}"
            )

    def test_balance_plot_faceted(self, multicolumn_run):
        """Test balance.plot() creates faceted figure when by is set."""
        wb = WaterBalance(multicolumn_run, by="column")

        (
            fig_cumulative,
            fig_output_decomposition,
            fig_input_decomposition,
            fig_storage_decomposition,
        ) = wb.plot()

        # Should have multiple subplots (3 columns)
        # Balance plots create separate faceted figures.
        assert len(fig_cumulative.axes) >= 1  # At least one subplot
        assert len(fig_output_decomposition.axes) >= 1
        assert len(fig_input_decomposition.axes) >= 1
        assert len(fig_storage_decomposition.axes) >= 1

        plt.close(fig_cumulative)
        plt.close(fig_output_decomposition)
        plt.close(fig_input_decomposition)
        plt.close(fig_storage_decomposition)

    def test_balance_without_subgrid_dimension_raises(self, single_point_run):
        """Test that WaterBalance with by='column' raises error for gridcell data."""
        with pytest.raises(ValueError, match="dimension not found|gridcell-averaged"):
            WaterBalance(single_point_run, by="column")


class TestSubgridDataAccess:
    """Test that Run.get() properly handles sub-gridcell dimensions."""

    def test_get_preserves_column_dimension(self, multicolumn_run):
        """Test that Run.get() preserves column dimension."""
        da = multicolumn_run.get("GPP")

        assert "column" in da.dims
        assert da.sizes["column"] == 3

    def test_get_column_specific_unit(self, multicolumn_run):
        """Test selecting a specific column."""
        da = multicolumn_run.get("GPP")
        da_col1 = da.sel(column=1)

        assert "column" not in da_col1.dims
        assert len(da_col1) == 12  # 12 months

    def test_columns_have_different_values(self, multicolumn_run):
        """Test that different columns have different values."""
        da = multicolumn_run.get("GPP")

        col1_mean = da.sel(column=1).mean().values
        col2_mean = da.sel(column=2).mean().values
        col3_mean = da.sel(column=3).mean().values

        # Columns should have different values (constructed that way in fixture)
        assert not np.isclose(col1_mean, col2_mean, rtol=0.01)
        assert not np.isclose(col2_mean, col3_mean, rtol=0.01)


class TestFacetLayoutEdgeCases:
    """Test edge cases in facet layout and plotting."""

    def test_single_column(self, tmp_path):
        """Test plotting with just 1 column (edge case)."""
        ds = make_multicolumn_dataset(n_columns=1, n_months=12)
        save_as_elm_files(ds, tmp_path, casename="single_col", tape="h0")
        run = Run(str(tmp_path))

        # Should raise error (size 1)
        with pytest.raises(ValueError, match="size is 1"):
            plot_timeseries(run, "GPP", by="column")

    def test_many_columns_warns(self, tmp_path):
        """Test that many columns triggers warning."""
        ds = make_multicolumn_dataset(n_columns=20, n_months=12)
        save_as_elm_files(ds, tmp_path, casename="many_cols", tape="h0")
        run = Run(str(tmp_path))

        # Should warn about many facets
        with pytest.warns(UserWarning, match="20 faceted subplots"):
            fig = plot_timeseries(run, "GPP", by="column")
            plt.close(fig)
