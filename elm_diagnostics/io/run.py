# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Run and Comparison classes for loading ELM history-file streams."""

from __future__ import annotations

import re
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Literal

import cftime
import numpy as np
import pandas as pd
import xarray as xr

_FILE_STAMP_PATTERN = re.compile(r"\.h\d+\.([^.]+)\.nc$")

# Time-bounds variable names, in preference order.
_TIME_BOUNDS_NAMES = ("time_bounds", "time_bnds")


def _discover_streams(path: Path) -> dict[str, list[Path]]:
    """Auto-discover ELM history streams from a directory.

    Groups files by history tape number (h0, h1, ...).
    """
    pattern = re.compile(r"\.elm\.(h\d+)\.")
    streams: dict[str, list[Path]] = {}
    for f in sorted(path.glob("*.elm.h*.nc")):
        m = pattern.search(f.name)
        if m:
            tape = m.group(1)
            streams.setdefault(tape, []).append(f)
    return streams


def _infer_cadence(ds: xr.Dataset) -> str | pd.Timedelta:
    """Infer temporal cadence from time_bounds.

    Returns 'monthly', 'annual', or a pd.Timedelta for uniform sub-monthly.
    """
    if "time_bounds" in ds:
        bounds_var = "time_bounds"
    elif "time_bnds" in ds:
        bounds_var = "time_bnds"
    else:
        # Fall back to diff of time coordinate
        times = ds["time"].values
        if len(times) < 2:
            return "monthly"
        if isinstance(times[0], cftime.datetime):
            diffs = []
            for i in range(min(len(times) - 1, 12)):
                dt = times[i + 1] - times[i]
                diffs.append(dt.days)
            median_days = np.median(diffs)
        else:
            td = np.diff(times[:13])
            median_days = np.median(td / np.timedelta64(1, "D"))
        if 28 <= median_days <= 31:
            return "monthly"
        if 360 <= median_days <= 366:
            return "annual"
        return pd.Timedelta(days=float(median_days))

    bounds = ds[bounds_var]
    # Compute dt from bounds
    if len(bounds.dims) == 2:
        dts = bounds[:, 1] - bounds[:, 0]
    else:
        return "monthly"

    # Sample first few time steps
    sample = min(len(dts), 12)

    import datetime

    day_diffs = []
    for i in range(sample):
        val = dts.values[i]
        if isinstance(val, datetime.timedelta):
            day_diffs.append(val.days + val.seconds / 86400.0)
        elif isinstance(val, np.timedelta64):
            day_diffs.append(val / np.timedelta64(1, "D"))
        elif hasattr(val, "days"):
            day_diffs.append(val.days)
        elif isinstance(val, (int, float, np.integer, np.floating)):
            day_diffs.append(float(val))
        else:
            day_diffs.append(float(val) / 86400.0)

    median_days = float(np.median(day_diffs))

    if 28 <= median_days <= 31:
        return "monthly"
    if 360 <= median_days <= 366:
        return "annual"
    return pd.Timedelta(days=float(median_days))


def _extract_casename(path: Path) -> str:
    """Extract ELM case name from the first history file found."""
    for f in sorted(path.glob("*.elm.h*.nc")):
        parts = f.name.split(".elm.")
        if parts:
            return parts[0]
    return path.name


def _extract_file_year(path: Path) -> int | None:
    """Extract YYYY from an ELM history filename, if present."""
    stamp_match = _FILE_STAMP_PATTERN.search(path.name)
    if not stamp_match:
        return None

    # Common ELM stamps include:
    # - YYYY-MM
    # - YYYY-MM-DD-SSSSS
    # - YYYY-MM-DD
    stamp = stamp_match.group(1)
    year_match = re.match(r"(\d{4})", stamp)
    if not year_match:
        return None

    return int(year_match.group(1))


def _filter_stream_files_by_year(
    files: list[Path],
    *,
    year_min: int | None,
    year_max: int | None,
    tolerance_years: int,
    tape: str,
) -> list[Path]:
    """Return files narrowed to a year range with safe fallback behavior."""
    parsed: list[tuple[Path, int]] = []
    unparsed_count = 0
    for file in files:
        file_year = _extract_file_year(file)
        if file_year is None:
            unparsed_count += 1
        else:
            parsed.append((file, file_year))

    if not parsed:
        warnings.warn(
            (
                f"Stream {tape} has no parseable year tokens; "
                "skipping early year file narrowing."
            ),
            RuntimeWarning,
        )
        return files

    if unparsed_count > 0:
        warnings.warn(
            (
                f"Stream {tape} has {unparsed_count} files with unparseable years; "
                "skipping early year file narrowing for safety."
            ),
            RuntimeWarning,
        )
        return files

    lo = None if year_min is None else year_min - tolerance_years
    hi = None if year_max is None else year_max + tolerance_years

    filtered = []
    for path, file_year in parsed:
        if lo is not None and file_year < lo:
            continue
        if hi is not None and file_year > hi:
            continue
        filtered.append(path)

    if filtered:
        return filtered

    if year_min is None and year_max is None:
        return files

    if year_min is None:
        year_range_label = f"<= {year_max}"
    elif year_max is None:
        year_range_label = f">= {year_min}"
    else:
        year_range_label = f"{year_min}:{year_max}"

    warnings.warn(
        (
            f"Early year filter for stream {tape} matched no files for "
            f"year_range={year_range_label}; "
            "using all files instead."
        ),
        RuntimeWarning,
    )
    return files


class Run:
    """Atomic unit of analysis: one ELM case's history-file streams.

    Parameters
    ----------
    path : str or Path
        Directory containing ``*.elm.h*.nc`` files, or a glob pattern.
    name : str, optional
        Display name. Defaults to the case name extracted from filenames.
    streams : dict, optional
        Explicit stream mapping, e.g. ``{"h0": "*.elm.h0.*.nc"}``.
        If None, streams are auto-discovered.
    chunks : dict, optional
        Passed to ``xr.open_mfdataset`` for dask-backed lazy loading.
    analysis_year : int, optional
        Requested analysis year for early file narrowing before open.
    analysis_year_min : int, optional
        Inclusive lower bound for year-aware file narrowing.
    analysis_year_max : int, optional
        Inclusive upper bound for year-aware file narrowing.
    analysis_year_tolerance : int, optional
        Year-window half-width when narrowing files (0 means exact year).
    strict_combine : bool, optional
        If True, open streams using stricter multi-file combine options.
        Defaults to False.
    """

    def __init__(
        self,
        path: str | Path,
        name: str | None = None,
        streams: dict[str, str] | None = None,
        chunks: dict | None = None,
        chunk_mode: Literal["off", "auto", "manual"] = "auto",
        chunk_target_mb: int = 64,
        analysis_year: int | None = None,
        analysis_year_min: int | None = None,
        analysis_year_max: int | None = None,
        analysis_year_tolerance: int = 0,
        strict_combine: bool = False,
    ):
        self.path = Path(path)
        self.name = name or _extract_casename(self.path)
        self._chunks = chunks
        self._chunk_mode = chunk_mode
        self._chunk_target_mb = chunk_target_mb
        if (
            analysis_year_min is None
            and analysis_year_max is None
            and analysis_year is not None
        ):
            analysis_year_min = analysis_year
            analysis_year_max = analysis_year
        if (
            analysis_year_min is not None
            and analysis_year_max is not None
            and analysis_year_min > analysis_year_max
        ):
            analysis_year_min, analysis_year_max = (
                analysis_year_max,
                analysis_year_min,
            )
        self._analysis_year_min = analysis_year_min
        self._analysis_year_max = analysis_year_max
        self._analysis_year_tolerance = max(0, int(analysis_year_tolerance))
        self._strict_combine = strict_combine
        self._datasets: dict[str, xr.Dataset] = {}
        self._cadence: dict[str, str | pd.Timedelta] = {}
        self._streams_cache: dict[str, xr.Dataset] | None = None
        # LRU cache with max 15 variables to prevent OOM on large datasets
        # Each variable can be ~1GB metadata for 167-year datasets (167 files)
        # Balance components (~10 vars) + recent plot vars (~5) = 15 total (~15GB peak)
        self._variable_cache: OrderedDict[str, xr.DataArray] = OrderedDict()
        self._variable_cache_maxsize = 15
        # Per-tape variable-name index (from files[0] header only) so get()/has()
        # can check existence and route to the owning tape without opening every
        # stream's full dataset.
        self._var_index: dict[str, set[str]] = {}

        if streams is not None:
            self._stream_files: dict[str, list[Path]] = {}
            for tape, pattern in streams.items():
                self._stream_files[tape] = sorted(self.path.glob(pattern))
        else:
            self._stream_files = _discover_streams(self.path)

        if self._analysis_year_min is not None or self._analysis_year_max is not None:
            self._stream_files = {
                tape: _filter_stream_files_by_year(
                    files,
                    year_min=self._analysis_year_min,
                    year_max=self._analysis_year_max,
                    tolerance_years=self._analysis_year_tolerance,
                    tape=tape,
                )
                for tape, files in self._stream_files.items()
            }

        if not self._stream_files:
            raise FileNotFoundError(
                f"No ELM history files found in {self.path}. "
                "Expected files matching *.elm.h*.nc"
            )

        # Sort tapes by name for deterministic ordering
        self._tape_order = sorted(self._stream_files.keys())

    def _auto_chunks_for_stream(self, files: list[Path]) -> dict[str, int] | None:
        """Estimate a conservative time-chunk map for a stream.

        Sizes the time chunk so that a single chunk of the *largest* time-
        varying variable stays near ``chunk_target_mb``.

        The per-timestep footprint is the maximum, over time-varying data
        variables, of the product of that variable's own non-time dimension
        sizes. It must NOT be the product of *all* the dataset's dimensions:
        different variables use different vertical/sub-grid dimensions
        (``levgrnd``, ``levsoi``, ``levlak``, ``ltype``, ``natpft`` ...), and no
        single variable spans them all. Multiplying every dimension together
        over-counts the footprint by orders of magnitude (~5e7 vs a real max of
        a few hundred), which collapses the estimate to ``{"time": 1}`` — one
        chunk per timestep. On a 60k-timestep stream that produces tens of
        thousands of dask chunks per variable and was a major driver of the
        open-time memory blow-up.
        """
        if not files:
            return None

        try:
            with xr.open_dataset(files[0], decode_times=False) as ds0:
                if "time" not in ds0.dims:
                    return None
                time_dim = "time"

                # Largest per-timestep element count across time-varying vars.
                max_non_time_elems = 1
                for var in ds0.data_vars.values():
                    if time_dim not in var.dims:
                        continue
                    elems = 1
                    for dim in var.dims:
                        if dim != time_dim:
                            elems *= max(1, int(ds0.sizes[dim]))
                    max_non_time_elems = max(max_non_time_elems, elems)

                target_bytes = max(1, int(self._chunk_target_mb)) * 1024 * 1024
                # 8 bytes/element is a conservative (float64) upper bound.
                bytes_per_step = max(8, max_non_time_elems * 8)
                est_chunk = max(1, target_bytes // bytes_per_step)
                time_len = max(1, int(ds0.sizes.get(time_dim, 1)))
                time_chunk = int(min(time_len, est_chunk))
                return {time_dim: time_chunk}
        except Exception:
            return None

    def _build_open_kwargs(
        self,
        files: list[Path],
        strict_combine: bool | None = None,
        *,
        chunks: object = "default",
    ) -> dict:
        """Build the kwargs dict for ``xr.open_mfdataset``.

        Parameters
        ----------
        files : list[Path]
            Stream files (used for auto-chunk estimation).
        strict_combine : bool, optional
            Override ``self._strict_combine`` when not None.
        chunks : object
            ``"default"`` (sentinel) applies the existing ``self._chunks`` /
            ``self._chunk_mode`` logic. Any other value (including ``None``)
            is used verbatim as the ``chunks`` kwarg.

        Notes
        -----
        The default (non-strict) combine uses ``compat="override"`` +
        ``coords="minimal"`` + ``join="override"``. ELM history streams are
        homogeneous (identical grid/coords in every timestep file), so the
        cross-file equality checks that ``compat="equals"`` / ``join="exact"``
        perform are pure cost: they force xarray to *materialize* and compare
        every coordinate and non-time data variable across all files. On a
        many-file stream (e.g. 167 files × 554 vars) that dominated both time
        and memory (~300 s and >10 GB just to open). ``override`` trusts the
        first file's coords and skips the comparison, cutting that to ~25 s and
        ~1 GB with identical data values. ``strict_combine=True`` restores the
        equality-checking path for debugging suspect files.
        """
        if strict_combine is None:
            strict_combine = self._strict_combine
        kwargs: dict = {
            "combine": "by_coords",
            "data_vars": "all",
        }
        if strict_combine:
            # Strict: verify coords/vars are equal across files (debugging).
            kwargs["combine"] = "by_coords"
            kwargs["data_vars"] = "all"
            kwargs["join"] = "override"
            kwargs["compat"] = "equals"
        else:
            # Performance path: trust the files to be consistent and skip the
            # cross-file equality materialization (see Notes above).
            kwargs["combine"] = "nested"
            kwargs["concat_dim"] = "time"
            kwargs["data_vars"] = "minimal"
            kwargs["coords"] = "minimal"
            kwargs["join"] = "override"
            kwargs["compat"] = "override"
        # Use CFDatetimeCoder for cftime decoding (xarray >= 2024)
        try:
            coder = xr.coders.CFDatetimeCoder(use_cftime=True)
            kwargs["decode_times"] = coder
        except AttributeError:
            kwargs["decode_times"] = True
            kwargs["use_cftime"] = True
        if chunks != "default":
            kwargs["chunks"] = chunks
        elif self._chunks is not None:
            kwargs["chunks"] = self._chunks
        else:
            if self._chunk_mode == "auto":
                kwargs["chunks"] = self._auto_chunks_for_stream(files)
            else:
                # Avoid requiring dask when not explicitly requested
                kwargs["chunks"] = None
        kwargs.setdefault("compat", "no_conflicts")
        kwargs.setdefault("join", "outer")
        return kwargs

    def _open_stream(self, tape: str, strict_combine: bool | None = None) -> xr.Dataset:
        """Lazily open a stream's files as a single dataset."""
        if tape not in self._datasets:
            files = self._stream_files[tape]
            if not files:
                raise FileNotFoundError(f"No files for stream {tape}")
            kwargs = self._build_open_kwargs(files, strict_combine)
            try:
                self._datasets[tape] = xr.open_mfdataset(files, **kwargs)
            except Exception as e:
                if kwargs.get("chunks") is not None and (
                    "dask" in str(e).lower() or "chunk manager" in str(e).lower()
                ):
                    warnings.warn(
                        f"Chunked loading requested but unavailable (chunk_mode={self._chunk_mode}). "
                        f"Retrying without chunks. For better performance with large datasets, "
                        f"install dask: pip install elm-diagnostics[dask]",
                        RuntimeWarning,
                    )
                    kwargs["chunks"] = None
                    self._datasets[tape] = xr.open_mfdataset(files, **kwargs)
                else:
                    raise
            self._cadence[tape] = _infer_cadence(self._datasets[tape])
        return self._datasets[tape]

    def _variable_index(self, tape: str) -> set[str]:
        """Return the set of variable names in a stream, from files[0] only.

        Reads a single file header (no dask graph, no concat) so ``get()`` /
        ``has()`` can test existence and route to the owning tape without
        opening every tape's full dataset. Assumes ELM history streams are
        homogeneous (same fields in every timestep file); callers fall back to a
        full ``_open_stream`` check on an index miss to preserve exact semantics.
        """
        if tape not in self._var_index:
            files = self._stream_files[tape]
            if not files:
                self._var_index[tape] = set()
            else:
                with xr.open_dataset(files[0], decode_times=False) as ds0:
                    # Include coords + data_vars: membership is all we need.
                    self._var_index[tape] = set(ds0.variables)
        return self._var_index[tape]

    def _cheap_cadence(self, tape: str) -> str | pd.Timedelta:
        """Infer cadence for a tape from files[0] only, cached in _cadence.

        Avoids the full-stream open that the ``cadence`` / ``tape_priority``
        properties trigger. If a full open has already populated ``_cadence``
        for this tape, that (more authoritative) value is reused.
        """
        if tape not in self._cadence:
            files = self._stream_files[tape]
            if not files:
                self._cadence[tape] = "monthly"
            else:
                try:
                    coder = xr.coders.CFDatetimeCoder(use_cftime=True)
                    open_kwargs = {"decode_times": coder}
                except AttributeError:
                    open_kwargs = {"decode_times": True, "use_cftime": True}
                try:
                    with xr.open_dataset(files[0], **open_kwargs) as ds0:
                        self._cadence[tape] = _infer_cadence(ds0)
                except Exception:
                    self._cadence[tape] = "monthly"
        return self._cadence[tape]

    def _cheap_tape_priority(self) -> list[str]:
        """Tapes ordered finest-cadence-first using header-only cadence.

        Mirrors the ``tape_priority`` property's ordering but without opening
        full streams (used on the ``get()`` hot path).
        """

        def _key(tape: str) -> float:
            c = self._cheap_cadence(tape)
            if isinstance(c, pd.Timedelta):
                return c.total_seconds()
            if c == "monthly":
                return 30 * 86400
            if c == "annual":
                return 365 * 86400
            return 30 * 86400

        return sorted(self._tape_order, key=_key)

    def _first_tape_with_bounds(self) -> str:
        """First tape whose files[0] header contains a time-bounds variable.

        Falls back to the first tape if none advertise bounds (cadence-only
        streams); callers still handle a missing-bounds dataset gracefully.
        """
        for tape in self._tape_order:
            if _TIME_BOUNDS_NAMES[0] in self._variable_index(
                tape
            ) or _TIME_BOUNDS_NAMES[1] in self._variable_index(tape):
                return tape
        return self._tape_order[0]

    def bounds_dataset(self, tape: str | None = None) -> xr.Dataset:
        """Return the stream dataset used for flux-integration time bounds.

        Balance modules need ``time_bounds`` (and the ``time`` coordinate) for
        cumulative integration. This returns the cached full stream for the
        tape that carries the bounds, opened once via ``_open_stream``. With the
        ``compat="override"`` combine strategy, that open is already cheap even
        for many-file, many-variable streams, so no separate bounds-only open
        is needed.
        """
        if tape is None:
            tape = self._first_tape_with_bounds()
        return self._open_stream(tape)

    @property
    def streams(self) -> dict[str, xr.Dataset]:
        """All streams as open datasets, keyed by tape name."""
        if self._streams_cache is None:
            self._streams_cache = {
                tape: self._open_stream(tape) for tape in self._tape_order
            }
        return self._streams_cache

    @property
    def cadence(self) -> dict[str, str | pd.Timedelta]:
        """Cadence per stream (inferred from time_bounds)."""
        # Ensure all streams are opened to populate cadence
        for tape in self._tape_order:
            self._open_stream(tape)
        return dict(self._cadence)

    @property
    def tape_priority(self) -> list[str]:
        """Tapes ordered by cadence (finest first)."""

        def _cadence_key(tape: str) -> float:
            self._open_stream(tape)
            c = self._cadence[tape]
            if isinstance(c, pd.Timedelta):
                return c.total_seconds()
            if c == "monthly":
                return 30 * 86400
            if c == "annual":
                return 365 * 86400
            return 30 * 86400

        return sorted(self._tape_order, key=_cadence_key)

    def _cache_variable(self, varname: str, data: xr.DataArray) -> None:
        """Add variable to LRU cache, evicting oldest if at capacity."""
        # Move to end (most recently used) if already in cache
        if varname in self._variable_cache:
            self._variable_cache.move_to_end(varname)
        else:
            # Add new entry
            self._variable_cache[varname] = data
            # Evict oldest if over capacity
            if len(self._variable_cache) > self._variable_cache_maxsize:
                self._variable_cache.popitem(last=False)

    def get(self, varname: str, tape: str | None = None) -> xr.DataArray:
        """Retrieve a variable, searching tapes in priority order.

        If the variable is not found, attempts to derive it from available
        components (e.g., compute QFLX_EVAP_TOT from QSOIL + QVEGE + QVEGT).

        Variables are cached with an LRU policy (max 15 variables) to balance
        performance and memory usage on large datasets.

        The per-tape variable-name index (single file header) is used to route
        to the tape that owns ``varname`` without opening the other tapes'
        datasets. The owning stream is then opened once (cached via
        ``_open_stream``) and the variable sliced out; the open is cheap thanks
        to the ``compat="override"`` combine strategy.

        Parameters
        ----------
        varname : str
            History field name (e.g. ``"GPP"``, ``"SOILLIQ"``).
        tape : str, optional
            Specific tape to search. If None, searches all tapes
            in cadence-priority order (finest first).

        Returns
        -------
        xr.DataArray

        Raises
        ------
        KeyError
            If the variable is not found in any tape and cannot be derived.
        """
        # Check cache first (only for non-tape-specific requests)
        if tape is None and varname in self._variable_cache:
            # Move to end (mark as recently used)
            self._variable_cache.move_to_end(varname)
            return self._variable_cache[varname]

        if tape is not None:
            ds = self._open_stream(tape)
            if varname in ds:
                result = ds[varname]
                self._cache_variable(varname, result)
                return result
            raise KeyError(f"{varname!r} not found in stream {tape}")

        # Route via the header index (cheap) to the owning tape, in cadence
        # priority order, then open only that stream.
        for t in self._cheap_tape_priority():
            if varname in self._variable_index(t):
                ds = self._open_stream(t)
                if varname in ds:
                    result = ds[varname]
                    self._cache_variable(varname, result)
                    return result

        # Not in any tape's index. Try derivation next (it routes back through
        # get() for the components) before the last-resort full-open scan, so
        # derivable variables never trigger unnecessary opens.
        from elm_diagnostics.io.derived import can_derive, derive_variable

        if can_derive(varname):
            try:
                result = derive_variable(self, varname)
                # Cache derived variables
                self._cache_variable(varname, result)
                return result
            except (ValueError, KeyError) as e:
                # Derivation failed - fall through to original error
                available_tapes = ", ".join(self._tape_order)
                raise KeyError(
                    f"{varname!r} not found in any stream and derivation failed: {e}. "
                    f"Searched tapes: {available_tapes}"
                ) from e

        # Last resort: full opens in case a stream is non-homogeneous
        # (variable present only in some files, so absent from files[0] index).
        for t in self._cheap_tape_priority():
            ds = self._open_stream(t)
            if varname in ds:
                result = ds[varname]
                self._cache_variable(varname, result)
                return result

        available_tapes = ", ".join(self._tape_order)
        raise KeyError(
            f"{varname!r} not found in any stream. Searched tapes: {available_tapes}"
        )

    def has(self, varname: str) -> bool:
        """Check whether a variable exists in any tape or can be derived.

        Uses the per-tape header index (single file read) rather than opening
        full streams, and checks derivability via component availability
        (``DERIVABLE_REQUIREMENTS``) instead of executing the derivation. Both
        keep this cheap on high-variable-count datasets.
        """
        # Check cache first
        if varname in self._variable_cache:
            return True

        # Check each tape's variable-name index (header-only).
        for t in self._tape_order:
            if varname in self._variable_index(t):
                return True

        # Check derivability by component availability (recurses through has()
        # on the components, which stays index-cheap) instead of executing
        # derive_variable.
        from elm_diagnostics.io.derived import (
            DERIVABLE_REQUIREMENTS,
            can_derive,
        )

        if can_derive(varname):
            requirements = DERIVABLE_REQUIREMENTS.get(varname)
            if requirements is not None:
                return all(self.has(component) for component in requirements)
            # No requirements mapping: conservatively report available and let
            # get() surface any derivation failure.
            return True

        return False

    def close(self) -> None:
        """Close all open datasets and clear caches."""
        for ds in self._datasets.values():
            ds.close()
        self._datasets.clear()
        self._streams_cache = None
        self._var_index.clear()
        self._cadence.clear()
        self._variable_cache.clear()

    def __repr__(self) -> str:
        tapes = ", ".join(self._tape_order)
        return f"Run(name={self.name!r}, tapes=[{tapes}])"


def _lazy_align(
    da_base: xr.DataArray,
    da_exp: xr.DataArray,
    join: Literal["inner", "outer"],
) -> tuple[xr.DataArray, xr.DataArray]:
    """Align arrays on coordinates while preserving chunking.

    Uses xarray's align with copy=False to avoid triggering computation
    on dask-backed arrays.

    Parameters
    ----------
    da_base, da_exp : xr.DataArray
        Arrays to align, potentially with dask chunks
    join : {"inner", "outer"}
        How to combine coordinate indices

    Returns
    -------
    tuple of aligned arrays, still chunked if inputs were chunked
    """
    # copy=False is critical - returns views/references rather than
    # materializing new arrays
    aligned = xr.align(da_base, da_exp, join=join, copy=False)
    return aligned


class Comparison:
    """Pair of runs for side-by-side diagnostics.

    Parameters
    ----------
    base : Run
        Reference / control run.
    experiment : Run
        Experiment / perturbation run.
    align : {'intersect', 'union'}
        How to align time axes. ``'intersect'`` keeps only overlapping
        times; ``'union'`` fills missing times with NaN.
    """

    def __init__(
        self,
        base: Run,
        experiment: Run,
        align: Literal["intersect", "union"] = "intersect",
    ):
        self.base = base
        self.experiment = experiment
        self.align = align

    def get(
        self, varname: str, tape: str | None = None
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """Retrieve a variable from both runs, time-aligned.

        Alignment preserves dask chunks for lazy evaluation. Computation
        is deferred until the data is actually used in plot generation.

        Returns
        -------
        tuple of (base_da, experiment_da)
        """
        da_base = self.base.get(varname, tape=tape)
        da_exp = self.experiment.get(varname, tape=tape)

        join = "inner" if self.align == "intersect" else "outer"
        return _lazy_align(da_base, da_exp, join=join)

    def __repr__(self) -> str:
        return (
            f"Comparison(base={self.base.name!r}, "
            f"experiment={self.experiment.name!r}, "
            f"align={self.align!r})"
        )
