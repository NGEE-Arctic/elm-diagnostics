# © 2026. Triad National Security, LLC. All rights reserved.
# This program was produced under U.S. Government contract 89233218CNA000001 for Los Alamos
# National Laboratory (LANL), which is operated by Triad National Security, LLC for the U.S.
# Department of Energy/National Nuclear Security Administration. All rights in the program are
# reserved by Triad National Security, LLC, and the U.S. Department of Energy/National Nuclear
# Security Administration. The Government is granted for itself and others acting on its behalf
# a nonexclusive, paid-up, irrevocable worldwide license in this material to reproduce, prepare
# derivative works, distribute copies to the public, perform publicly and display publicly, and
# to permit others to do so.

"""Color utilities for balance plot comparisons."""

from __future__ import annotations

import colorsys
from typing import Any

import matplotlib.colors as mcolors


def lighten_color(color: Any, factor: float = 0.3) -> tuple[float, float, float]:
    """Lighten a matplotlib color by a given factor.

    Parameters
    ----------
    color : Any
        A matplotlib color (string name, hex, RGB tuple, etc.)
    factor : float, optional
        Amount to lighten (0 = no change, 1 = pure white). Default is 0.3.

    Returns
    -------
    tuple[float, float, float]
        RGB tuple with values in [0, 1]

    Examples
    --------
    >>> lighten_color('blue', 0.3)
    (0.3, 0.3, 1.0)
    >>> lighten_color('#1f77b4', 0.3)
    (0.4215..., 0.5843..., 0.7568...)
    """
    # Convert to RGB
    rgb = mcolors.to_rgb(color)

    # Convert to HLS (Hue, Lightness, Saturation)
    h, lightness, s = colorsys.rgb_to_hls(*rgb)

    # Increase lightness by moving toward 1.0 (white)
    # lightness_new = lightness + (1.0 - lightness) * factor
    lightness_new = min(1.0, lightness + (1.0 - lightness) * factor)

    # Convert back to RGB
    rgb_new = colorsys.hls_to_rgb(h, lightness_new, s)

    return rgb_new


def get_balance_colors() -> dict[str, dict[str, str]]:
    """Get standard color mapping for balance plots.

    Returns
    -------
    dict[str, dict[str, str]]
        Nested dictionary mapping balance type to component colors.

    Examples
    --------
    >>> colors = get_balance_colors()
    >>> colors['water']['input']
    'blue'
    >>> colors['carbon']['GPP']
    'green'
    """
    return {
        "water": {
            "input": "blue",
            "output": "red",
            "storage": "green",
            "residual": "black",
        },
        "carbon": {
            "GPP": "green",
            "ER": "red",
            "HR": "orange",
            "AR": "salmon",
            "NEE": "purple",
            "TOTFIRE": "gray",
            "WOOD_HARVESTC": "brown",
            "dTOTECOSYSC": "black",
            "residual": "black",
        },
        "energy": {
            "Rnet": "orange",
            "FSH": "red",
            "LE": "blue",
            "FGR": "brown",
            "residual": "black",
        },
    }
