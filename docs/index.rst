elm-diagnostics documentation
==============================

Budget-closure diagnostics for E3SM's ELM land model.

**elm-diagnostics** computes water, carbon, and energy balances from ELM history files with automatic variable derivation, sub-gridcell support, and HTML report generation.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   tutorials
   api/index

Features
--------

* **Water, Carbon, and Energy Balance Diagnostics** with automatic closure checking
* **Automatic variable derivation**: Computes missing variables like ``QFLX_EVAP_TOT`` from components
* **Handles multiple file formats**: Single-point (``lndgrid``) and gridded (``lat``×``lon``) output
* **Vertical aggregation**: Automatically sums 3D soil variables (SOILLIQ, SOILICE) over depth
* **Unit-aware integration**: Uses ``pint`` for proper unit handling in flux-to-cumulative conversions
* **Water year support**: Configurable water year start month for hydrological analyses
* **Time-bounds-aware**: Uses actual time intervals for accurate flux integration
* **Flexible configuration**: YAML-based configuration with sensible defaults

Installation
------------

.. code-block:: bash

   pip install -e ".[dev]"

For optional features:

.. code-block:: bash

   pip install -e ".[dask,interactive,maps,all]"

Quick Start
-----------

Loading ELM Output
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from elm_diagnostics import Run

   # Load a directory containing ELM history files
   run = Run("/path/to/case/run")
   print(run.streams)  # {'h0': <xr.Dataset>, ...}

   # Get a variable (auto-computes if missing)
   et_total = run.get("QFLX_EVAP_TOT")

Water Balance
~~~~~~~~~~~~~

.. code-block:: python

   from elm_diagnostics import WaterBalance

   # Compute water balance for a specific year
   wb = WaterBalance(run, year=2015, frame="water_year")

   # Get balance components (all cumulative, in mm)
   components = wb.components()

   # Check closure residual
   residual = wb.residual()
   print(f"Residual: {residual.values[-1]:.2f} mm")

   # Plot
   fig_cumulative, fig_decomposition, fig_storage = wb.plot()

Carbon and Energy Balances
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from elm_diagnostics import CarbonBalance, EnergyBalance

   # Carbon balance (auto-detects BGC vs SP mode)
   cb = CarbonBalance(run, year=2015)
   fig_c, fig_d = cb.plot()

   # Energy balance (fluxes only by default)
   eb = EnergyBalance(run, year=2015)
   fig_e, fig_f = eb.plot()

HTML Report Generation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from elm_diagnostics import Report

   # Generate comprehensive HTML report
   run = Run("/path/to/case/run")
   report = Report(run)
   report.build("output_directory/")

Command-Line Interface
----------------------

.. code-block:: bash

   # Generate full diagnostics report
   elm-diagnostics report /path/to/elm/output

   # Compute specific balance
   elm-diagnostics balance water /path/to/elm/output --year 2015

   # Plot single variable
   elm-diagnostics plot GPP /path/to/elm/output --kind seasonal

Requirements
------------

- Python ≥ 3.10
- Core: xarray, numpy, pandas, matplotlib, pint, pint-xarray
- Optional: dask (parallel processing), plotly (interactive plots), cartopy (maps)

License
-------

BSD-3-Clause

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
