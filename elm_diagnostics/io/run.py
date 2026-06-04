"""Run and Comparison classes for loading ELM history-file streams."""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Literal

import cftime
import numpy as np
import pandas as pd
import xarray as xr

_FILE_STAMP_PATTERN = re.compile(r"\.h\d+\.([^.]+)\.nc$")


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
    first_val = dts.values.flat[0]

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
    year_min: int,
    year_max: int,
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

    filtered = [
        path for path, file_year in parsed
        if (year_min - tolerance_years) <= file_year <= (year_max + tolerance_years)
    ]
    if filtered:
        return filtered

    warnings.warn(
        (
            f"Early year filter for stream {tape} matched no files for "
            f"year_range={year_min}:{year_max}; "
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
        chunk_mode: Literal["off", "auto", "manual"] = "off",
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
        if analysis_year_min is None and analysis_year_max is None and analysis_year is not None:
            analysis_year_min = analysis_year
            analysis_year_max = analysis_year
        if analysis_year_min is not None and analysis_year_max is not None:
            if analysis_year_min > analysis_year_max:
                analysis_year_min, analysis_year_max = analysis_year_max, analysis_year_min
        self._analysis_year_min = analysis_year_min
        self._analysis_year_max = analysis_year_max
        self._analysis_year_tolerance = max(0, int(analysis_year_tolerance))
        self._strict_combine = strict_combine
        self._datasets: dict[str, xr.Dataset] = {}
        self._cadence: dict[str, str | pd.Timedelta] = {}
        self._streams_cache: dict[str, xr.Dataset] | None = None

        if streams is not None:
            self._stream_files: dict[str, list[Path]] = {}
            for tape, pattern in streams.items():
                self._stream_files[tape] = sorted(self.path.glob(pattern))
        else:
            self._stream_files = _discover_streams(self.path)

        if self._analysis_year_min is not None and self._analysis_year_max is not None:
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
        """Estimate a conservative chunk map for a stream.

        Uses a time-only chunk with target size budget in MiB.
        """
        if not files:
            return None

        try:
            with xr.open_dataset(files[0], decode_times=False) as ds0:
                if "time" not in ds0.dims:
                    return None
                time_dim = "time"
                non_time_size = 1
                for dim, size in ds0.sizes.items():
                    if dim != time_dim:
                        non_time_size *= max(1, int(size))

                target_bytes = max(1, int(self._chunk_target_mb)) * 1024 * 1024
                bytes_per_step = max(8, non_time_size * 8)
                est_chunk = max(1, target_bytes // bytes_per_step)
                time_len = max(1, int(ds0.sizes.get(time_dim, 1)))
                time_chunk = int(min(time_len, est_chunk))
                return {time_dim: time_chunk}
        except Exception:
            return None

    def _open_stream(self, tape: str, strict_combine: bool | None = None) -> xr.Dataset:
        """Lazily open a stream's files as a single dataset."""
        if tape not in self._datasets:
            files = self._stream_files[tape]
            if not files:
                raise FileNotFoundError(f"No files for stream {tape}")
            if strict_combine is None:
                strict_combine = self._strict_combine
            kwargs: dict = dict(
                combine="by_coords",
                data_vars="all",
            )
            if strict_combine:
                # Set options to strict choice for debugging
                kwargs["combine"] = "by_coords"
                kwargs["data_vars"] = "all"
                kwargs["join"] = "override"
                kwargs["compat"] = "equals"
            else:
                # Set options to the performance-oriented choice when we
                # trust the files to be consistent
                kwargs["combine"] = "nested"
                kwargs["concat_dim"] = "time"
                kwargs["data_vars"] = "minimal"
                kwargs["join"] = "exact"
                kwargs["compat"] = "equals"
            # Use CFDatetimeCoder for cftime decoding (xarray >= 2024)
            try:
                coder = xr.coders.CFDatetimeCoder(use_cftime=True)
                kwargs["decode_times"] = coder
            except AttributeError:
                kwargs["decode_times"] = True
                kwargs["use_cftime"] = True
            if self._chunks is not None:
                kwargs["chunks"] = self._chunks
            else:
                if self._chunk_mode == "auto":
                    kwargs["chunks"] = self._auto_chunks_for_stream(files)
                else:
                    # Avoid requiring dask when not explicitly requested
                    kwargs["chunks"] = None
            kwargs.setdefault("compat", "no_conflicts")
            kwargs.setdefault("join", "outer")
            try:
                self._datasets[tape] = xr.open_mfdataset(files, **kwargs)
            except Exception as e:
                if kwargs.get("chunks") is not None and (
                    "dask" in str(e).lower() or "chunk manager" in str(e).lower()
                ):
                    warnings.warn(
                        "Chunked loading unavailable in this environment; retrying "
                        "without chunks.",
                        RuntimeWarning,
                    )
                    kwargs["chunks"] = None
                    self._datasets[tape] = xr.open_mfdataset(files, **kwargs)
                else:
                    raise
            self._cadence[tape] = _infer_cadence(self._datasets[tape])
        return self._datasets[tape]

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

    def get(self, varname: str, tape: str | None = None) -> xr.DataArray:
        """Retrieve a variable, searching tapes in priority order.

        If the variable is not found, attempts to derive it from available
        components (e.g., compute QFLX_EVAP_TOT from QSOIL + QVEGE + QVEGT).

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
        if tape is not None:
            ds = self._open_stream(tape)
            if varname in ds:
                return ds[varname]
            raise KeyError(f"{varname!r} not found in stream {tape}")

        for t in self.tape_priority:
            ds = self._open_stream(t)
            if varname in ds:
                return ds[varname]

        # Try to derive the variable if it's not directly available
        from elm_diagnostics.io.derived import can_derive, derive_variable

        if can_derive(varname):
            try:
                return derive_variable(self, varname)
            except (ValueError, KeyError) as e:
                # Derivation failed - fall through to original error
                available_tapes = ", ".join(self._tape_order)
                raise KeyError(
                    f"{varname!r} not found in any stream and derivation failed: {e}. "
                    f"Searched tapes: {available_tapes}"
                ) from e

        available_tapes = ", ".join(self._tape_order)
        raise KeyError(
            f"{varname!r} not found in any stream. Searched tapes: {available_tapes}"
        )

    def has(self, varname: str) -> bool:
        """Check whether a variable exists in any tape."""
        for t in self._tape_order:
            ds = self._open_stream(t)
            if varname in ds:
                return True
        return False

    def close(self) -> None:
        """Close all open datasets."""
        for ds in self._datasets.values():
            ds.close()
        self._datasets.clear()
        self._streams_cache = None

    def __repr__(self) -> str:
        tapes = ", ".join(self._tape_order)
        return f"Run(name={self.name!r}, tapes=[{tapes}])"


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

        Returns
        -------
        tuple of (base_da, experiment_da)
        """
        da_base = self.base.get(varname, tape=tape)
        da_exp = self.experiment.get(varname, tape=tape)

        if self.align == "intersect":
            common = xr.align(da_base, da_exp, join="inner")
        else:
            common = xr.align(da_base, da_exp, join="outer")

        return common  # type: ignore[return-value]

    def __repr__(self) -> str:
        return (
            f"Comparison(base={self.base.name!r}, "
            f"experiment={self.experiment.name!r}, "
            f"align={self.align!r})"
        )
