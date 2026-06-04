"""Synthetic ELM history dataset builder for testing.

Builds minimum-viable xr.Datasets that mimic h0/h1 tapes with realistic
dimension structure, correct cell_methods, time_bounds, and a cftime
noleap calendar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import cftime
import numpy as np
import xarray as xr


def make_time_axis(
    start_year: int = 2000,
    n_months: int = 12,
    calendar: str = "noleap",
) -> tuple[np.ndarray, np.ndarray]:
    """Create monthly time axis with mid-month times and bounds.

    Returns (times, time_bounds) where time_bounds has shape (n, 2).
    """
    times = []
    bounds = []
    days_in_month = {
        1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
        7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
    }

    year = start_year
    month = 1
    for _ in range(n_months):
        if month > 12:
            month = 1
            year += 1
        ndays = days_in_month[month]
        t0 = cftime.datetime(year, month, 1, calendar=calendar)
        if month == 12:
            t1 = cftime.datetime(year + 1, 1, 1, calendar=calendar)
        else:
            t1 = cftime.datetime(year, month + 1, 1, calendar=calendar)
        mid = cftime.datetime(year, month, ndays // 2 + 1, calendar=calendar)
        times.append(mid)
        bounds.append([t0, t1])
        month += 1

    return np.array(times), np.array(bounds)


def make_single_point_dataset(
    start_year: int = 2000,
    n_months: int = 12,
    calendar: str = "noleap",
    variables: dict[str, dict] | None = None,
) -> xr.Dataset:
    """Build a single-point (1 lat x 1 lon) ELM-like dataset.

    Parameters
    ----------
    start_year : int
    n_months : int
    calendar : str
    variables : dict, optional
        Mapping of variable name to dict with keys:
        - 'data': np.ndarray of shape (n_months,) or (n_months, nlevgrnd)
        - 'units': str
        - 'long_name': str (optional)
        - 'cell_methods': str (optional)

    Returns
    -------
    xr.Dataset
    """
    times, time_bounds_data = make_time_axis(start_year, n_months, calendar)

    coords = {
        "time": times,
        "lat": [45.0],
        "lon": [270.0],
    }

    ds = xr.Dataset(coords=coords)
    ds["time_bounds"] = xr.DataArray(
        time_bounds_data,
        dims=["time", "ntb"],
    )

    if variables:
        for name, spec in variables.items():
            data = spec["data"]
            attrs = {"units": spec.get("units", "")}
            if "long_name" in spec:
                attrs["long_name"] = spec["long_name"]
            if "cell_methods" in spec:
                attrs["cell_methods"] = spec["cell_methods"]

            if data.ndim == 1:
                da = xr.DataArray(
                    data.reshape(-1, 1, 1),
                    dims=["time", "lat", "lon"],
                    attrs=attrs,
                    name=name,
                )
            elif data.ndim == 2:
                nlev = data.shape[1]
                if "levgrnd" not in ds.dims:
                    ds = ds.assign_coords(levgrnd=np.arange(nlev))
                da = xr.DataArray(
                    data.reshape(data.shape[0], 1, 1, nlev),
                    dims=["time", "lat", "lon", "levgrnd"],
                    attrs=attrs,
                    name=name,
                )
            else:
                raise ValueError(f"Unsupported data shape for {name}: {data.shape}")

            ds[name] = da

    return ds


def make_water_balance_dataset(
    start_year: int = 2000,
    n_months: int = 12,
    calendar: str = "noleap",
    include_model_residual: bool = False,
    include_snow_residual: bool = False,
) -> xr.Dataset:
    """Build a synthetic dataset that closes the water balance exactly.

    The construction ensures: sum(inputs) - sum(outputs) = dS/dt.
    """
    rng = np.random.RandomState(42)
    n = n_months

    # Inputs (mm/s)
    rain = rng.uniform(1e-6, 5e-5, size=n).astype(np.float64)
    snow = rng.uniform(0, 1e-5, size=n).astype(np.float64)
    total_input = rain + snow

    # Output fractions (must sum to <1 of input to allow storage change)
    evap_frac = rng.uniform(0.3, 0.5, size=n)
    runoff_frac = rng.uniform(0.1, 0.2, size=n)
    drain_frac = rng.uniform(0.05, 0.1, size=n)
    # Remaining goes to storage change
    output_frac = evap_frac + runoff_frac + drain_frac
    # Normalize to leave ~10% for storage
    output_frac = np.clip(output_frac, 0, 0.9)
    scale = output_frac / (evap_frac + runoff_frac + drain_frac)
    evap_frac *= scale
    runoff_frac *= scale
    drain_frac *= scale

    evap_tot = total_input * evap_frac
    qover = total_input * runoff_frac
    qdrai = total_input * drain_frac

    # Remaining: storage change rate
    ds_dt_rate = total_input - evap_tot - qover - qdrai

    # Compute time bounds for dt
    _, tb = make_time_axis(start_year, n_months, calendar)
    dts = np.array([
        (tb[i, 1] - tb[i, 0]).days * 86400.0
        for i in range(n)
    ])

    # Cumulative storage
    ds_cumulative = np.cumsum(ds_dt_rate * dts)
    initial_storage = 500.0  # mm
    storage_ts = initial_storage + ds_cumulative

    # Partition storage into components (just split it)
    soilliq = storage_ts * 0.6
    soilice = storage_ts * 0.2
    h2osno = storage_ts * 0.1
    h2ocan = storage_ts * 0.05
    h2osfc = storage_ts * 0.05

    variables = {
        "RAIN": {"data": rain, "units": "mm/s", "cell_methods": "time: mean"},
        "SNOW": {"data": snow, "units": "mm/s", "cell_methods": "time: mean"},
        "QFLX_EVAP_TOT": {"data": evap_tot, "units": "mm/s", "cell_methods": "time: mean"},
        "QOVER": {"data": qover, "units": "mm/s", "cell_methods": "time: mean"},
        "QDRAI": {"data": qdrai, "units": "mm/s", "cell_methods": "time: mean"},
        "QDRAI_PERCH": {"data": np.zeros(n), "units": "mm/s", "cell_methods": "time: mean"},
        "QFLX_SUB_SNOW": {"data": np.zeros(n), "units": "mm/s", "cell_methods": "time: mean"},
        "QSNOMELT": {"data": np.zeros(n), "units": "mm/s", "cell_methods": "time: mean"},
        "SOILLIQ": {"data": soilliq, "units": "kg/m2", "cell_methods": "time: point"},
        "SOILICE": {"data": soilice, "units": "kg/m2", "cell_methods": "time: point"},
        "H2OSNO": {"data": h2osno, "units": "mm", "cell_methods": "time: point"},
        "H2OCAN": {"data": h2ocan, "units": "mm", "cell_methods": "time: point"},
        "H2OSFC": {"data": h2osfc, "units": "mm", "cell_methods": "time: point"},
    }

    if include_model_residual:
        # Synthetic closure is exact; model residual should be near zero.
        variables["ERRH2O"] = {
            "data": np.zeros(n),
            "units": "mm",
            "cell_methods": "time: mean",
        }

    if include_snow_residual:
        variables["ERRH2OSNO"] = {
            "data": np.zeros(n),
            "units": "mm",
            "cell_methods": "time: mean",
        }

    return make_single_point_dataset(
        start_year=start_year,
        n_months=n_months,
        calendar=calendar,
        variables=variables,
    )


def make_energy_balance_dataset(
    start_year: int = 2000,
    n_months: int = 12,
    calendar: str = "noleap",
) -> xr.Dataset:
    """Build a synthetic dataset that closes the surface energy balance.

    Construction: Rnet = FSH + EFLX_LH_TOT + FGR
    where Rnet = FSDS - FSR + FLDS - FIRE = FSA - FIRA
    """
    rng = np.random.RandomState(123)
    n = n_months

    # Incoming radiation
    fsds = rng.uniform(100, 400, size=n).astype(np.float64)
    fsr = fsds * rng.uniform(0.1, 0.3, size=n)
    flds = rng.uniform(200, 350, size=n).astype(np.float64)
    fire = rng.uniform(300, 450, size=n).astype(np.float64)

    fsa = fsds - fsr
    fira = fire - flds  # net LW to atm

    rnet = fsa - fira  # net radiation into surface

    # Partition Rnet into FSH + LE + G
    fsh_frac = rng.uniform(0.2, 0.4, size=n)
    le_frac = rng.uniform(0.3, 0.5, size=n)
    g_frac = 1.0 - fsh_frac - le_frac

    fsh = rnet * fsh_frac
    eflx_lh_tot = rnet * le_frac
    fgr = rnet * g_frac

    variables = {
        "FSDS": {"data": fsds, "units": "W/m^2", "cell_methods": "time: mean"},
        "FSR": {"data": fsr, "units": "W/m^2", "cell_methods": "time: mean"},
        "FLDS": {"data": flds, "units": "W/m^2", "cell_methods": "time: mean"},
        "FIRE": {"data": fire, "units": "W/m^2", "cell_methods": "time: mean"},
        "FSA": {"data": fsa, "units": "W/m^2", "cell_methods": "time: mean"},
        "FIRA": {"data": fira, "units": "W/m^2", "cell_methods": "time: mean"},
        "FSH": {"data": fsh, "units": "W/m^2", "cell_methods": "time: mean"},
        "EFLX_LH_TOT": {"data": eflx_lh_tot, "units": "W/m^2", "cell_methods": "time: mean"},
        "FGR": {"data": fgr, "units": "W/m^2", "cell_methods": "time: mean"},
    }

    return make_single_point_dataset(
        start_year=start_year,
        n_months=n_months,
        calendar=calendar,
        variables=variables,
    )


def make_carbon_balance_dataset(
    start_year: int = 2000,
    n_months: int = 12,
    calendar: str = "noleap",
) -> xr.Dataset:
    """Build a synthetic dataset with carbon pools and fluxes.

    Construction: NEE = ER - GPP = (AR + HR) - GPP
    dTOTECOSYSC/dt = GPP - ER - TOTFIRE - WOOD_HARVESTC
    """
    rng = np.random.RandomState(456)
    n = n_months

    gpp = rng.uniform(1e-7, 5e-7, size=n).astype(np.float64)
    ar = gpp * rng.uniform(0.3, 0.5, size=n)
    hr = rng.uniform(5e-8, 2e-7, size=n).astype(np.float64)
    er = ar + hr
    nee = er - gpp  # positive = source
    totfire = rng.uniform(0, 1e-8, size=n).astype(np.float64)
    harvest = rng.uniform(0, 5e-9, size=n).astype(np.float64)

    # Compute storage change
    _, tb = make_time_axis(start_year, n_months, calendar)
    dts = np.array([(tb[i, 1] - tb[i, 0]).days * 86400.0 for i in range(n)])

    net_c_input = gpp - er - totfire - harvest
    totecosysc_init = 15000.0  # gC/m2
    totecosysc = totecosysc_init + np.cumsum(net_c_input * dts)

    # Simple pool partitioning
    leafc = totecosysc * 0.02
    livestemc = totecosysc * 0.05
    deadstemc = totecosysc * 0.15
    frootc = totecosysc * 0.03
    livecrootc = totecosysc * 0.02
    deadcrootc = totecosysc * 0.05
    totsomc = totecosysc * 0.50
    totlitc = totecosysc * 0.08
    cwdc = totecosysc * 0.10

    variables = {
        "GPP": {"data": gpp, "units": "gC/m^2/s", "cell_methods": "time: mean"},
        "AR": {"data": ar, "units": "gC/m^2/s", "cell_methods": "time: mean"},
        "HR": {"data": hr, "units": "gC/m^2/s", "cell_methods": "time: mean"},
        "ER": {"data": er, "units": "gC/m^2/s", "cell_methods": "time: mean"},
        "NEE": {"data": nee, "units": "gC/m^2/s", "cell_methods": "time: mean"},
        "TOTFIRE": {"data": totfire, "units": "gC/m^2/s", "cell_methods": "time: mean"},
        "WOOD_HARVESTC": {"data": harvest, "units": "gC/m^2/s", "cell_methods": "time: mean"},
        "TOTECOSYSC": {"data": totecosysc, "units": "gC/m^2", "cell_methods": "time: point"},
        "TOTCOLC": {"data": totecosysc * 1.02, "units": "gC/m^2", "cell_methods": "time: point"},
        "LEAFC": {"data": leafc, "units": "gC/m^2", "cell_methods": "time: point"},
        "LIVESTEMC": {"data": livestemc, "units": "gC/m^2", "cell_methods": "time: point"},
        "DEADSTEMC": {"data": deadstemc, "units": "gC/m^2", "cell_methods": "time: point"},
        "FROOTC": {"data": frootc, "units": "gC/m^2", "cell_methods": "time: point"},
        "LIVECROOTC": {"data": livecrootc, "units": "gC/m^2", "cell_methods": "time: point"},
        "DEADCROOTC": {"data": deadcrootc, "units": "gC/m^2", "cell_methods": "time: point"},
        "TOTSOMC": {"data": totsomc, "units": "gC/m^2", "cell_methods": "time: point"},
        "TOTLITC": {"data": totlitc, "units": "gC/m^2", "cell_methods": "time: point"},
        "CWDC": {"data": cwdc, "units": "gC/m^2", "cell_methods": "time: point"},
    }

    return make_single_point_dataset(
        start_year=start_year,
        n_months=n_months,
        calendar=calendar,
        variables=variables,
    )


def make_multicolumn_dataset(
    n_columns: int = 3,
    start_year: int = 2000,
    n_months: int = 12,
    calendar: str = "noleap",
    perfect_closure: bool = True,
) -> xr.Dataset:
    """Build a synthetic multi-column dataset for sub-gridcell testing.
    
    Creates a dataset with sub-gridcell (column) dimension, where each
    column has independent water balance. If perfect_closure=True, the
    water balance closes exactly for each column.
    
    Parameters
    ----------
    n_columns : int, default 3
        Number of columns
    start_year : int, default 2000
    n_months : int, default 12
    calendar : str, default "noleap"
    perfect_closure : bool, default True
        If True, construct water balance to close exactly per column
    
    Returns
    -------
    xr.Dataset
        Dataset with 'column' dimension and water/carbon variables
    """
    rng = np.random.RandomState(42)
    n = n_months
    
    times, time_bounds_data = make_time_axis(start_year, n_months, calendar)
    
    # Compute time deltas for flux integration
    dts = np.array([
        (time_bounds_data[i, 1] - time_bounds_data[i, 0]).days * 86400.0
        for i in range(n)
    ])
    
    # Initialize arrays with (time, column) shape
    # Each column gets different but realistic values
    rain_all = np.zeros((n, n_columns))
    snow_all = np.zeros((n, n_columns))
    evap_all = np.zeros((n, n_columns))
    qover_all = np.zeros((n, n_columns))
    qdrai_all = np.zeros((n, n_columns))
    soilliq_all = np.zeros((n, n_columns))
    soilice_all = np.zeros((n, n_columns))
    h2osno_all = np.zeros((n, n_columns))
    h2ocan_all = np.zeros((n, n_columns))
    h2osfc_all = np.zeros((n, n_columns))
    gpp_all = np.zeros((n, n_columns))
    
    for col in range(n_columns):
        # Use different random seed per column for variation
        col_rng = np.random.RandomState(42 + col * 10)
        
        # Inputs (mm/s) - vary by column
        rain = col_rng.uniform(1e-6, 5e-5, size=n).astype(np.float64) * (1 + col * 0.2)
        snow = col_rng.uniform(0, 1e-5, size=n).astype(np.float64) * (1 + col * 0.3)
        total_input = rain + snow
        
        if perfect_closure:
            # Construct outputs to close balance exactly
            evap_frac = col_rng.uniform(0.3, 0.5, size=n)
            runoff_frac = col_rng.uniform(0.1, 0.2, size=n)
            drain_frac = col_rng.uniform(0.05, 0.1, size=n)
            # Normalize to leave room for storage change
            output_frac = evap_frac + runoff_frac + drain_frac
            output_frac = np.clip(output_frac, 0, 0.9)
            scale = output_frac / (evap_frac + runoff_frac + drain_frac)
            evap_frac *= scale
            runoff_frac *= scale
            drain_frac *= scale
            
            evap = total_input * evap_frac
            qover = total_input * runoff_frac
            qdrai = total_input * drain_frac
            
            # Storage change rate
            ds_dt_rate = total_input - evap - qover - qdrai
        else:
            # Random outputs (balance won't close)
            evap = col_rng.uniform(1e-6, 4e-5, size=n)
            qover = col_rng.uniform(0, 1e-5, size=n)
            qdrai = col_rng.uniform(0, 5e-6, size=n)
            ds_dt_rate = col_rng.uniform(-1e-6, 1e-6, size=n)
        
        # Cumulative storage
        ds_cumulative = np.cumsum(ds_dt_rate * dts)
        initial_storage = 500.0 + col * 50.0  # Different initial storage per column
        storage_ts = initial_storage + ds_cumulative
        
        # Partition storage into components
        soilliq = storage_ts * 0.6
        soilice = storage_ts * 0.2
        h2osno = storage_ts * 0.1
        h2ocan = storage_ts * 0.05
        h2osfc = storage_ts * 0.05
        
        # GPP for carbon plots (just make it seasonal)
        gpp = col_rng.uniform(5e-6, 15e-6, size=n) * (1 + col * 0.1)
        # Add seasonal pattern
        month_of_year = np.arange(n) % 12
        seasonal_factor = 1 + 0.5 * np.sin(2 * np.pi * month_of_year / 12)
        gpp = gpp * seasonal_factor
        
        # Store in column arrays
        rain_all[:, col] = rain
        snow_all[:, col] = snow
        evap_all[:, col] = evap
        qover_all[:, col] = qover
        qdrai_all[:, col] = qdrai
        soilliq_all[:, col] = soilliq
        soilice_all[:, col] = soilice
        h2osno_all[:, col] = h2osno
        h2ocan_all[:, col] = h2ocan
        h2osfc_all[:, col] = h2osfc
        gpp_all[:, col] = gpp
    
    # Build dataset
    coords = {
        "time": times,
        "column": np.arange(1, n_columns + 1),  # 1-indexed like real ELM
        "lndgrid": [1],  # Single gridcell
    }
    
    ds = xr.Dataset(coords=coords)
    ds["time_bounds"] = xr.DataArray(
        time_bounds_data,
        dims=["time", "ntb"],
    )
    
    # Add variables with (time, column) dimensions
    variables = {
        "RAIN": (rain_all, "mm/s", "time: mean"),
        "SNOW": (snow_all, "mm/s", "time: mean"),
        "QFLX_EVAP_TOT": (evap_all, "mm/s", "time: mean"),
        "QOVER": (qover_all, "mm/s", "time: mean"),
        "QDRAI": (qdrai_all, "mm/s", "time: mean"),
        "QDRAI_PERCH": (np.zeros((n, n_columns)), "mm/s", "time: mean"),
        "QSNOMELT": (np.zeros((n, n_columns)), "mm/s", "time: mean"),
        "SOILLIQ": (soilliq_all, "kg/m2", "time: point"),
        "SOILICE": (soilice_all, "kg/m2", "time: point"),
        "H2OSNO": (h2osno_all, "mm", "time: point"),
        "H2OCAN": (h2ocan_all, "mm", "time: point"),
        "H2OSFC": (h2osfc_all, "mm", "time: point"),
        "GPP": (gpp_all, "gC/m^2/s", "time: mean"),
        # Also add ET components for derived variable testing
        "QSOIL": (evap_all * 0.4, "mm/s", "time: mean"),
        "QVEGE": (evap_all * 0.3, "mm/s", "time: mean"),
        "QVEGT": (evap_all * 0.3, "mm/s", "time: mean"),
    }
    
    for name, (data, units, cell_methods) in variables.items():
        da = xr.DataArray(
            data,
            dims=["time", "column"],
            attrs={"units": units, "cell_methods": cell_methods},
            name=name,
        )
        ds[name] = da
    
    return ds


def save_as_elm_files(
    ds: xr.Dataset,
    outdir: Path,
    casename: str = "test_case",
    tape: str = "h0",
) -> list[Path]:
    """Save dataset as ELM-named NetCDF files (one per time step for testing)."""
    outdir.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(len(ds.time)):
        t = ds.time.values[i]
        if hasattr(t, "strftime"):
            datestr = t.strftime("%Y-%m")
        else:
            datestr = str(t)[:7]
        fname = outdir / f"{casename}.elm.{tape}.{datestr}.nc"
        ds.isel(time=slice(i, i + 1)).to_netcdf(fname)
        files.append(fname)
    return files
