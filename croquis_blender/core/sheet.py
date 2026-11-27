# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""A presentation sheet: four drawings of the model on one sheet of paper,
in two rows (top and the 3D view above, front and side below), each with
its name lettered under it by hand, if asked."""
from __future__ import annotations

import unicodedata

import numpy as np

from . import paper as pp
from . import strokes as st
from .drawing import Layers

#: Room round the sheet's edge and between the drawings, as a share of its
#: width; the names' capital height, as a share of a drawing's width
#: (times 0.6).
GAP = 0.03
CAP = 0.055

# Capital letters as a hand letters them on a drawing: strokes on a grid
# 4 wide and 6 high (y up), each a polyline.
_O = [(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]
_P = [(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]
LETTERS = {
    "A": [[(0, 0), (2, 6), (4, 0)], [(0.8, 2.4), (3.2, 2.4)]],
    "B": [[(0, 3), (0, 6), (2.8, 6), (3.6, 5.2), (3.6, 3.8), (2.8, 3), (0, 3)],
          [(0, 3), (0, 0), (3, 0), (3.8, 0.8), (3.8, 2.2), (2.8, 3)]],
    "C": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 6), (2.5, 6), (4, 4.5), (4, 1.5), (2.5, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2.6),
           (2.4, 2.6)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(0, 0), (0, 6)]],
    "J": [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 2)], [(1.3, 3.3), (4, 0)]],
    "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    "O": [_O],
    "P": [_P],
    "Q": [_O, [(2.5, 1.5), (4.3, -0.3)]],
    "R": [_P, [(2, 3), (4, 0)]],
    "S": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1),
           (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "U": [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 4), (3, 0), (4, 6)]],
    "X": [[(0, 0), (4, 6)], [(0, 6), (4, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
}
#: The marks over (or under) a letter, by the combining character, for a
#: letter 4 wide.
MARKS = {
    "́": [[(1.6, 7), (2.6, 8.2)]],                                   # acute
    "̀": [[(2.4, 7), (1.4, 8.2)]],                                   # grave
    "̂": [[(1, 7), (2, 8), (3, 7)]],                                 # circumflex
    "̃": [[(0.8, 7.2), (1.6, 8), (2.4, 7.4), (3.2, 8.1)]],           # tilde
    "̈": [[(1.2, 7.4), (1.2, 8)], [(2.8, 7.4), (2.8, 8)]],           # diaeresis
    "̧": [[(2, 0), (2.4, -0.8), (1.6, -1.4)]],                       # cedilla
}
TRACK = 1.8     # between letters, in grid units
SPACE = 3.0


def _width(ch: str) -> float:
    return 0.0 if ch == "I" else 4.0


def letter_segments(text: str, centre, cap: float) -> np.ndarray:
    """``text`` in capitals as segments ((N, 4) pixels, y down), ``cap``
    pixels high, centred on ``centre``. Letters it does not know are left
    out."""
    chars = []
    for base in unicodedata.normalize("NFD", text.upper()):
        if unicodedata.combining(base):
            if chars:
                chars[-1][1].append(base)
        elif base == " " or base in LETTERS:
            chars.append([base, []])
    lines, x = [], 0.0
    for base, marks in chars:
        if base == " ":
            x += SPACE
            continue
        w = _width(base)
        for poly in LETTERS[base]:
            lines.append([(x + px, py) for px, py in poly])
        for m in marks:
            for poly in MARKS.get(m, ()):
                lines.append([(x + px - 2 + w / 2, py) for px, py in poly])
        x += w + TRACK
    width = max(0.0, x - TRACK)
    k = cap / 6.0
    cx, cy = centre
    segs = []
    for poly in lines:
        p = np.array([(cx + (px - width / 2) * k, cy + (3 - py) * k) for px, py in poly])
        segs += [np.concatenate([a, b]) for a, b in zip(p[:-1], p[1:])]
    return np.array(segs, dtype=np.float64).reshape(-1, 4)


def lettering_style(style: st.LineStyle) -> st.LineStyle:
    """The hand of the drawing, steadier for letters: no overshoot, once."""
    return st.LineStyle(hand=min(style.hand, 0.35), width=max(style.width, 2.0),
                        profile_scale=1.0, overshoot=0.0, double_stroke=False,
                        breaks=False)


def layout(width: int, aspects, names: bool) -> tuple:
    """The sheet for drawings of ``aspects`` (width over height: top, 3D
    view, front, side): ``(sheet_w, sheet_h), cell_w, heights, spots,
    band``, the drawings' width, their heights and where each one sits,
    and the room under each for its name."""
    gap = max(4, int(round(width * GAP)))
    cell_w = max(16, (width - 3 * gap) // 2)
    heights = [max(16, int(round(cell_w / max(a, 1e-6)))) for a in aspects]
    band = int(round(cell_w * CAP * 1.6)) if names else 0
    rows = (max(heights[:2]), max(heights[2:]))
    spots, y = [], gap
    for r in (0, 1):
        spots += [(gap + col * (cell_w + gap), y) for col in (0, 1)]
        y += rows[r] + band + gap
    return (width, y), cell_w, heights, spots, band


def compose(cells, width: int, paper_kind: str = "cream", paper_image: str = "",
            names=None, style: st.LineStyle | None = None,
            transparent: bool = False) -> Layers:
    """The four drawings (:class:`Layers`, top, 3D view, front, side, each
    drawn at the cell's size) on one sheet ``width`` wide, with ``names``
    (four, or None) lettered under them in ink."""
    (sw, sh), _cw, _heights, spots, band = layout(
        width, [c.size[0] / c.size[1] for c in cells], bool(names))
    sheet = pp.make(paper_kind, sw, sh, image=paper_image)
    fill = np.ones((sh, sw, 3)) if any(c.fill is not None for c in cells) else None
    solid = np.zeros((sh, sw)) if any(c.solid is not None for c in cells) else None
    strokes = []
    for cell, (x, y) in zip(cells, spots):
        w, h = cell.size
        if fill is not None and cell.fill is not None:
            fill[y:y + h, x:x + w] = cell.fill
        if solid is not None and cell.solid is not None:
            solid[y:y + h, x:x + w] = cell.solid
        shift = np.array([x, y], dtype=np.float64)
        strokes += [st.Stroke(s.outline + shift, s.opacity) for s in cell.strokes]
    if names:
        hand = lettering_style(style or st.LineStyle())
        cw = cells[0].size[0]
        cap = cw * CAP * 0.6
        rows = (max(c.size[1] for c in cells[:2]), max(c.size[1] for c in cells[2:]))
        for i, (name, (x, y)) in enumerate(zip(names, spots)):
            segs = letter_segments(name, (x + cw / 2, y + rows[i // 2] + band / 2), cap)
            strokes += st.strokes_for(segs, None, hand, cw * 0.6)
    return Layers(sheet, fill, strokes, (0, 0), (sw, sh), transparent, solid)
