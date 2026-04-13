"""Tests for calendar and water-year utilities."""

import cftime
import numpy as np

from elm_diagnostics.time.calendars import (
    add_water_year_coord,
    get_available_years,
    select_year,
    water_year,
)
from tests.fixtures.synthetic_elm import make_water_balance_dataset


def test_water_year_oct():
    """October 2014 should be water year 2015."""
    t = cftime.datetime(2014, 10, 15, calendar="noleap")
    assert water_year(t, start_month=10) == 2015


def test_water_year_sep():
    """September 2015 should be water year 2015."""
    t = cftime.datetime(2015, 9, 15, calendar="noleap")
    assert water_year(t, start_month=10) == 2015


def test_water_year_jan():
    """January 2015 should be water year 2015."""
    t = cftime.datetime(2015, 1, 15, calendar="noleap")
    assert water_year(t, start_month=10) == 2015


def test_add_water_year_coord():
    ds = make_water_balance_dataset(start_year=2014, n_months=24)
    ds = add_water_year_coord(ds, start_month=10)
    assert "water_year" in ds.coords
    wy = ds["water_year"].values
    # Fixture starts at Jan 2014 -> WY 2014 (before Oct boundary)
    assert wy[0] == 2014
    # Oct 2014 (index 9) -> WY 2015
    assert wy[9] == 2015


def test_select_calendar_year():
    ds = make_water_balance_dataset(start_year=2000, n_months=24)
    sub = select_year(ds, 2000, frame="calendar")
    assert len(sub.time) == 12


def test_select_water_year():
    ds = make_water_balance_dataset(start_year=1999, n_months=24)
    sub = select_year(ds, 2000, frame="water_year", start_month=10)
    # WY 2000 = Oct 1999 - Sep 2000 = 12 months
    assert len(sub.time) == 12


def test_get_available_years():
    ds = make_water_balance_dataset(start_year=2000, n_months=36)
    years = get_available_years(ds, frame="calendar")
    assert 2000 in years
    assert 2001 in years
    assert 2002 in years
