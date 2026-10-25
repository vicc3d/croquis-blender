# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The box of colour markers.

A sketcher does not mix colours: they reach for the nearest marker in the
box. Every material of the model goes to the nearest of these; a colour
with little colour in it (white, greys, the default face) gets none, and
the greys of light and shade are left to say it.
"""
from __future__ import annotations

import colorsys

import numpy as np

#: A box of alcohol markers (RGB, 0..255).
MARKERS = (
    (196, 72, 52),     # brick red
    (205, 110, 70),    # terracotta
    (226, 123, 98),    # coral
    (233, 150, 60),    # orange
    (214, 170, 80),    # ochre
    (240, 214, 90),    # yellow
    (225, 205, 160),   # sand
    (205, 160, 110),   # light wood
    (150, 100, 65),    # dark wood
    (120, 85, 60),     # brown
    (150, 160, 90),    # olive
    (110, 160, 90),    # leaf green
    (70, 115, 80),     # dark green
    (150, 200, 170),   # mint
    (130, 175, 215),   # sky blue
    (80, 120, 180),    # blue
    (60, 80, 120),     # navy
    (70, 150, 160),    # teal
    (140, 110, 170),   # violet
    (220, 150, 170),   # pink
)
#: Below this saturation a colour gets no marker.
MIN_SATURATION = 0.16


def nearest_marker(rgb) -> int:
    """The marker for a colour (0..1 floats), or -1 for none."""
    r, g, b = (float(c) for c in rgb[:3])
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s * min(1.0, 2.0 * min(l, 1.0 - l) + 0.2) < MIN_SATURATION or l > 0.93 or l < 0.06:
        return -1
    best, dist = -1, 1e9
    for k, m in enumerate(MARKERS):
        mh, ml, ms = colorsys.rgb_to_hls(*(c / 255.0 for c in m))
        dh = min(abs(h - mh), 1.0 - abs(h - mh))
        d = (3.0 * dh) ** 2 + (l - ml) ** 2 + 0.5 * (s - ms) ** 2
        if d < dist:
            best, dist = k, d
    return best


def _lightness(rgb) -> float:
    r, g, b = (float(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
