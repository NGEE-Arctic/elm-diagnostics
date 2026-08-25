"""Tests for sub-gridcell faceting helpers."""

import warnings

import matplotlib.pyplot as plt
import numpy as np
import pytest
import xarray as xr

from elm_diagnostics.config.schema import PlotStyleConfig
from elm_diagnostics.plots.subgrid_helpers import (
    calculate_facet_layout,
    create_facet_figure,
    format_subgrid_title,
    get_subgrid_units,
    validate_variable_for_subgrid,
)


class TestCalculateFacetLayout:
    """Test facet layout calculation."""

    def test_single_unit(self):
        """Single unit should be 1x1."""
        assert calculate_facet_layout(1) == (1, 1)

    def test_two_units(self):
        """Two units should be 1x2."""
        assert calculate_facet_layout(2) == (1, 2)

    def test_three_units(self):
        """Three units should be 1x3."""
        assert calculate_facet_layout(3) == (1, 3)

    def test_four_units(self):
        """Four units should be 2x2."""
        assert calculate_facet_layout(4) == (2, 2)

    def test_five_units(self):
        """Five units should be 2x3."""
        assert calculate_facet_layout(5) == (2, 3)

    def test_six_units(self):
        """Six units should be 2x3."""
        assert calculate_facet_layout(6) == (2, 3)

    def test_nine_units(self):
        """Nine units should be 3x3."""
        assert calculate_facet_layout(9) == (3, 3)

    def test_twelve_units(self):
        """Twelve units should be 3x4."""
        assert calculate_facet_layout(12) == (3, 4)

    def test_large_numbers(self):
        """Test layout for larger numbers is roughly square."""
        nrows, ncols = calculate_facet_layout(20)
        # Should be roughly square-ish
        assert nrows * ncols >= 20
        assert abs(nrows - ncols) <= 2  # Not too elongated

    def test_zero_raises(self):
        """Zero units should raise ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            calculate_facet_layout(0)

    def test_negative_raises(self):
        """Negative units should raise ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            calculate_facet_layout(-1)


class TestCreateFacetFigure:
    """Test facet figure creation."""

    def test_creates_figure(self):
        """Should create figure and axes."""
        style = PlotStyleConfig(figsize=[8, 5], dpi=100, palette="tab10")
        fig, axes = create_facet_figure(4, style)
        assert isinstance(fig, plt.Figure)
        assert isinstance(axes, np.ndarray)
        plt.close(fig)

    def test_correct_number_of_axes(self):
        """Should create at least n_units axes."""
        style = PlotStyleConfig(figsize=[8, 5], dpi=100, palette="tab10")
        fig, axes = create_facet_figure(3, style)
        # 3 units → 1x3 layout → 3 axes
        assert len(axes) == 3
        plt.close(fig)

    def test_grid_layout(self):
        """Should create correct grid layout."""
        style = PlotStyleConfig(figsize=[8, 5], dpi=100, palette="tab10")
        fig, axes = create_facet_figure(6, style)
        # 6 units → 2x3 layout → 6 axes
        assert len(axes) == 6
        plt.close(fig)

    def test_warns_for_many_facets(self):
        """Should warn if creating > 16 facets."""
        style = PlotStyleConfig(figsize=[8, 5], dpi=100, palette="tab10")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fig, _axes = create_facet_figure(20, style)
            assert len(w) == 1
            assert "20 faceted subplots" in str(w[0].message)
            plt.close(fig)

    def test_no_warning_for_few_facets(self):
        """Should not warn for ≤16 facets."""
        style = PlotStyleConfig(figsize=[8, 5], dpi=100, palette="tab10")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fig, _axes = create_facet_figure(16, style)
            assert len(w) == 0
            plt.close(fig)

    def test_figsize_scaling(self):
        """Figure size should scale with number of subplots."""
        style = PlotStyleConfig(figsize=[8, 5], dpi=100, palette="tab10")
        fig1, _ = create_facet_figure(1, style)
        fig4, _ = create_facet_figure(4, style)

        # 4-panel figure should be larger than 1-panel
        assert fig4.get_figwidth() > fig1.get_figwidth()
        assert fig4.get_figheight() > fig1.get_figheight()

        plt.close(fig1)
        plt.close(fig4)


class TestValidateVariableForSubgrid:
    """Test variable validation for sub-gridcell faceting."""

    def test_valid_variable(self):
        """Should not raise for variable with requested dimension."""
        da = xr.DataArray(
            np.random.rand(10, 3),
            dims=["time", "column"],
            coords={"column": [1, 2, 3]},
        )
        # Should not raise
        validate_variable_for_subgrid(da, "column", "GPP")

    def test_missing_dimension_with_alternatives(self):
        """Should raise helpful error if dimension missing but others present."""
        da = xr.DataArray(
            np.random.rand(10, 3),
            dims=["time", "column"],
            coords={"column": [1, 2, 3]},
        )
        with pytest.raises(ValueError, match="does not have dimension 'pft'"):
            validate_variable_for_subgrid(da, "pft", "GPP")

        # Error should mention available dimension
        with pytest.raises(ValueError, match="Available.*column"):
            validate_variable_for_subgrid(da, "pft", "GPP")

    def test_missing_dimension_no_subgrid(self):
        """Should raise helpful error if no sub-gridcell dimensions."""
        da = xr.DataArray(
            np.random.rand(10, 5, 5),
            dims=["time", "lat", "lon"],
        )
        with pytest.raises(ValueError, match="no sub-gridcell dimensions"):
            validate_variable_for_subgrid(da, "column", "TSKIN")

    def test_size_one_dimension(self):
        """Should raise error if dimension has size 1."""
        da = xr.DataArray(
            np.random.rand(10, 1),
            dims=["time", "column"],
            coords={"column": [1]},
        )
        with pytest.raises(ValueError, match="size is 1"):
            validate_variable_for_subgrid(da, "column", "GPP")


class TestGetSubgridUnits:
    """Test extracting sub-gridcell unit IDs."""

    def test_gets_unit_ids(self):
        """Should return sorted list of unit IDs."""
        da = xr.DataArray(
            np.random.rand(10, 3),
            dims=["time", "column"],
            coords={"column": [3, 1, 2]},  # Unsorted
        )
        units = get_subgrid_units(da, "column")
        assert units == [1, 2, 3]  # Should be sorted

    def test_handles_large_indices(self):
        """Should handle non-contiguous or large indices."""
        da = xr.DataArray(
            np.random.rand(10, 3),
            dims=["time", "pft"],
            coords={"pft": [5, 12, 8]},
        )
        units = get_subgrid_units(da, "pft")
        assert units == [5, 8, 12]


class TestFormatSubgridTitle:
    """Test subplot title formatting."""

    def test_column_title(self):
        """Should format column titles."""
        assert format_subgrid_title("column", 1) == "Column 1"
        assert format_subgrid_title("column", 5) == "Column 5"

    def test_pft_title(self):
        """Should format PFT titles."""
        assert format_subgrid_title("pft", 12) == "PFT 12"

    def test_landunit_title(self):
        """Should format landunit titles."""
        assert format_subgrid_title("landunit", 3) == "Landunit 3"
