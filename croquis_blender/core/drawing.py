# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The view of the model as a freehand drawing on paper.

One depth buffer of the view (:mod:`.visibility`) gives everything: the
visible parts of the edges, which become ink strokes (:mod:`.strokes`,
outlines heavier, straight runs joined into one stroke), and the face seen
at every pixel, which gets its value in grey marker (:mod:`.marker`). The
layers go down as on paper: the sheet, the marker, the ink.
"""
from __future__ import annotations

import numpy as np

from . import compose as cp
from . import hatch
from . import ink
from . import marker as mk
from . import paper as pp
from . import shadow as sh
from . import strokes as st
from . import visibility as vis
from . import watercolour as wc

PAPER = (247, 243, 234)          # a warm, slightly cream sheet
INK = (29, 26, 23)               # not black: a warm dark ink
#: The depth buffer is never wider than this (lines and fills are scaled up
#: from it): enough for a sketch, and quick.
MAX_BUFFER_WIDTH = 2000


class View:
    """What one view of the model gives the drawing, at the buffer's size
    (``scale`` = buffer pixels per drawing pixel)."""

    def __init__(self, viewport, width: int, height: int) -> None:
        cam = viewport.camera
        self.width, self.height = width, height
        self.scale = min(1.0, MAX_BUFFER_WIDTH / max(1, width))
        self.bw = max(1, int(round(width * self.scale)))
        self.bh = max(1, int(round(height * self.scale)))
        self.camera = cam
        self.scene = viewport.scene
        self.geom = viewport.hlr_geometry()
        # The scene hands the faces with their colours (scene_view.py).
        coloured = getattr(viewport, "croquis_colours", None)
        if coloured is not None:
            self.tris, self.colour, self.tone = coloured
        else:
            self.tris = np.asarray(self.geom[0], dtype=np.float64).reshape(-1, 3, 3)
            self.colour = self.tone = None
        self.M = vis.clip_matrix(cam)
        self.zbuf, self.index = vis.depth_buffer(self.tris, self.M, self.bw,
                                                 self.bh, bool(cam.perspective))
        segs, outline = vis.visible_lines(self.geom, cam, self.bw, self.bh,
                                          zbuf=self.zbuf)
        segs, outline = vis.merge_collinear(segs, outline, tol=1.5)
        self.segs = segs / self.scale
        self.outline = outline

    def __len__(self) -> int:
        return len(self.segs)


def paper(width: int, height: int, seed: int = 7) -> np.ndarray:
    """A sheet of paper, (H, W, 3) floats: the paper tone, soft grain."""
    rng = np.random.default_rng(seed)
    gh, gw = max(2, height // 3 + 1), max(2, width // 3 + 1)
    grain = rng.normal(0.0, 1.0, (gh, gw))
    pad = np.pad(grain, 1, mode="edge")
    grain = sum(pad[i:i + gh, j:j + gw] for i in range(3) for j in range(3)) / 9.0
    grain = np.kron(grain, np.ones((3, 3)))[:height, :width]
    tone = 1.0 + 0.035 * grain
    return np.array(PAPER, dtype=np.float64)[None, None, :] * tone[:, :, None]


def _resize(rgb: np.ndarray, width: int, height: int) -> np.ndarray:
    """Smoothly scale an (h, w, 3) float image."""
    if rgb.shape[1] == width and rgb.shape[0] == height:
        return rgb
    return resize_array(rgb, width, height)


def shade_maps(view: View, style: mk.MarkerStyle) -> dict:
    """What the light does to the view, at the buffer's size: ``values``
    (0 lit, 1 turned, 2 away, 3 cast shadow, -1 nothing; the shadows on
    the ground under the model too), ``plane`` ids (the ground's is the
    last), ``angles`` of the strokes per plane, ``jitter`` per plane (a
    natural hand, or zeros), ``colour`` (a marker per pixel, or None) and
    ``tone`` (the material's lightness per pixel, or None)."""
    light = mk.light_direction(view.camera, view.scene, style.light)
    values, plane, normals, plane_of = mk.face_values(view.index, view.tris,
                                                      view.camera, light)
    n_planes = int(plane_of.max()) + 1 if len(plane_of) else 0
    if style.shadows and len(view.tris):
        pack = sh.shadow_map(view.tris, light)
        # Each shadow looked at four points of a pixel and settled within
        # where it falls (the model, the ground): no moiré of dots where a
        # railing's bars cast stripes finer than the pixels.
        model = view.index >= 0
        cast = sh.settled(lambda at: sh.cast_shadow(view, normals, light, pack, at),
                          model)
        values = np.where(cast & (values >= 0), 3, values).astype(np.int8)
        ground = sh.settled(lambda at: sh.ground_shadow(view, light, pack=pack, at=at),
                            ~model)
        values = np.where(ground, 3, values).astype(np.int8)
        plane = np.where(ground, n_planes, plane)
    colour = tone = None
    model = view.index >= 0
    ix = np.clip(view.index, 0, None)
    if view.colour is not None:
        colour = np.where(model, view.colour[ix], -1)
    if view.tone is not None:
        tone = np.where(model, view.tone[ix], -1.0)
    angles = mk.stroke_angles(normals, plane_of, n_planes, view.camera,
                              view.M, view.bw, view.bh)
    angles = np.r_[angles[:n_planes],
                   mk.level_angle(view.camera, view.M, view.bw, view.bh)]
    # Long, narrow areas (boards, slats): along their length.
    angles = mk.long_axis_angles(np.where(plane < n_planes, plane, -1), angles)
    if style.natural:
        rng = np.random.default_rng(97)
        jitter = rng.normal(0.0, 0.14, len(angles))
    else:
        jitter = np.zeros(len(angles))
    return {"values": values, "plane": plane, "angles": angles,
            "jitter": jitter, "colour": colour, "tone": tone}


def fill_layer(view: View, style: mk.MarkerStyle, maps: dict | None = None,
               fade: np.ndarray | None = None) -> np.ndarray:
    """The fill's effect (marker or watercolour), (H, W, 3) factors to
    multiply the paper by, at the drawing's size; ``fade`` (at the
    buffer's size) thins it out toward the edges."""
    maps = maps if maps is not None else shade_maps(view, style)
    ones = np.full((view.bh, view.bw, 3), 255.0)
    scale = view.bh / st.REFERENCE_HEIGHT
    if mk.colour_mode(style) == "contrast":
        # High contrast is its own technique: contour and solid ink.
        factor = ink.paint(ones, maps["values"], maps["tone"], scale, INK,
                           texture=style.ink_texture, strength=min(1.0, style.strength))
    elif style.medium == "watercolour":
        factor = wc.paint(ones, maps["values"], maps["colour"], style, scale,
                          tone=maps["tone"])
    else:
        factor = mk.paint(ones, maps["values"], maps["plane"], maps["angles"],
                          style, scale, colour=maps["colour"], tone=maps["tone"],
                          jitter=maps["jitter"])
    if fade is not None:
        factor = 255.0 - (255.0 - factor) * fade[:, :, None]
    return _resize(factor, view.width, view.height) / 255.0


def resize_array(rgb: np.ndarray, width: int, height: int) -> np.ndarray:
    """:func:`_resize`: bilinear, with the pixel centres aligned."""
    h, w = rgb.shape[:2]
    ys = np.clip((np.arange(height) + 0.5) * h / height - 0.5, 0, h - 1)
    xs = np.clip((np.arange(width) + 0.5) * w / width - 0.5, 0, w - 1)
    y0 = np.floor(ys).astype(np.int64)
    x0 = np.floor(xs).astype(np.int64)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = rgb[y0][:, x0] * (1 - fx) + rgb[y0][:, x1] * fx
    bottom = rgb[y1][:, x0] * (1 - fx) + rgb[y1][:, x1] * fx
    return top * (1 - fy) + bottom * fy


#: The name it had in 0.3.0.
marker_layer = fill_layer


def drawing_size(camera, width: int) -> tuple:
    return width, max(1, int(round(width / max(camera.aspect, 1e-6))))


class Layers:
    """A drawing kept as its layers, as the exporters need them: the sheet
    of paper (H, W, 3), the fill as the factors it multiplies the paper by
    (or None), and the ink strokes (polygons, in the sheet's pixels). The
    drawing sits at ``origin`` on the sheet, ``size`` big (a page format
    leaves a margin round it). ``transparent``: drawn on clear film, to lay
    over another picture, instead of on the paper (:meth:`rgba`), with
    ``solid`` (h, w) how much the model hides of what lies behind each
    pixel (its share of the pixel, times its opacity), or None when the
    model is see-through where it is white."""

    def __init__(self, sheet, fill, strokes, origin, size, transparent=False,
                 solid=None) -> None:
        self.sheet = sheet
        self.fill = fill
        self.strokes = strokes
        self.origin = origin
        self.size = size
        self.transparent = transparent
        self.solid = solid

    @property
    def width(self) -> int:
        return self.sheet.shape[1]

    @property
    def height(self) -> int:
        return self.sheet.shape[0]

    def coloured_sheet(self) -> np.ndarray:
        """The paper with the fill laid on it."""
        if self.fill is None:
            return self.sheet
        out = self.sheet.copy()
        ox, oy = self.origin
        w, h = self.size
        out[oy:oy + h, ox:ox + w] *= self.fill
        return out

    def pixels(self) -> np.ndarray:
        """The drawing as (H, W, 3) bytes: the paper with its colour, and the
        strokes laid on it by :mod:`.raster`."""
        from . import raster
        rgb = np.array(self.coloured_sheet(), dtype=np.float64)
        raster.lay_strokes(rgb, self.strokes, INK)
        return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)

    def film_rgba(self) -> np.ndarray:
        """The colour on clear film, (h, w, 4) floats 0..1, where the drawing
        sits: the shadows and washes see-through (white taken out as
        transparency, as a marker on tracing film), and the model as far as
        it is opaque (``solid``) on its paper, the drawing cut out along its
        outline, so it hides what lies behind it and sits on a background
        drawn on the same paper. Over white, a see-through model looks as
        the drawing on white paper."""
        w, h = self.size
        ox, oy = self.origin
        f = np.ones((h, w, 3)) if self.fill is None else np.clip(self.fill, 0.0, 1.0)
        f = np.broadcast_to(f, (h, w, 3))
        a = (1.0 - f).max(axis=2)
        safe = np.where(a > 1e-6, a, 1.0)[:, :, None]
        wash = np.clip(1.0 - (1.0 - f) / safe, 0.0, 1.0)
        solid = np.zeros((h, w)) if self.solid is None else np.clip(self.solid, 0.0, 1.0)
        on_paper = self.sheet[oy:oy + h, ox:ox + w] / 255.0 * f
        alpha = solid + (1.0 - solid) * a
        rgb = (on_paper * solid[:, :, None] + wash * ((1.0 - solid) * a)[:, :, None]) \
            / np.where(alpha > 1e-6, alpha, 1.0)[:, :, None]
        return np.concatenate([rgb, alpha[:, :, None]], axis=2)

    def rgba(self) -> np.ndarray:
        """The drawing on clear film as (H, W, 4) bytes: no paper, the fill
        as colour with its transparency, the ink over it."""
        from . import raster
        h, w = self.height, self.width
        film = np.zeros((h, w, 4))
        ox, oy = self.origin
        fw, fh = self.size
        film[oy:oy + fh, ox:ox + fw] = self.film_rgba()
        cover = np.zeros((h, w, 3))
        raster.lay_strokes(cover, self.strokes, (255, 255, 255))
        ink_a = cover[:, :, 0] / 255.0
        under = film[:, :, 3] * (1.0 - ink_a)
        a = ink_a + under
        safe = np.where(a > 1e-6, a, 1.0)
        rgb = (np.array(INK) / 255.0 * ink_a[:, :, None]
               + film[:, :, :3] * under[:, :, None]) / safe[:, :, None]
        out = np.concatenate([rgb, a[:, :, None]], axis=2)
        return np.clip(np.rint(out * 255.0), 0, 255).astype(np.uint8)


def page_size(fmt: str, dpi: int, landscape: bool) -> tuple:
    """A paper format's size in pixels: ``A5``, ``A4`` or ``A3`` at ``dpi``."""
    mm = {"A5": (148, 210), "A4": (210, 297), "A3": (297, 420)}[fmt]
    w, h = (mm[1], mm[0]) if landscape else mm
    return int(round(w / 25.4 * dpi)), int(round(h / 25.4 * dpi))


def render(viewport, style: st.LineStyle, width: int, view: View | None = None,
           marker: mk.MarkerStyle | None = None,
           composition: cp.Composition | None = None,
           paper_kind: str = "cream", paper_image: str = "",
           page: tuple | None = None, transparent: bool = False,
           opacity: float = 0.0) -> Layers:
    """The current view as a freehand drawing, as its :class:`Layers`:
    ``width`` pixels wide (the height follows the view), on a sheet that
    size, or centred on a ``page`` = (width, height) sheet. Paper, the fill
    (``marker``: marker or watercolour or high contrast, if on), the ink:
    construction and ground strokes, hatching, then the lines. ``view``: a
    :class:`View` the caller already made. A line width of 0 leaves the
    lines and construction lines out: the colour and shade alone, as for a
    background. ``transparent``: on clear film (:meth:`Layers.rgba`), the
    model see-through where it is white, or as far as ``opacity`` (0..1)
    says, on its paper, hiding what lies behind it."""
    width, height = drawing_size(viewport.camera, width)
    view = view if view is not None else View(viewport, width, height)
    comp = composition if composition is not None else cp.Composition(
        unfinished=False, construction=False, ground=False)
    pw, ph = page if page is not None else (width, height)
    ox, oy = (pw - width) // 2, (ph - height) // 2
    sheet = pp.make(paper_kind, pw, ph, image=paper_image)
    subject = cp.subject_mask(view.index, view.tris) \
        if (comp.unfinished or comp.ground) else None
    fade = (cp.fade_map(subject, view.bh / st.REFERENCE_HEIGHT)
            if comp.unfinished else None)
    maps = fill = None
    if marker is not None and (marker.enabled or marker.hatching) and len(view.tris):
        maps = shade_maps(view, marker)
        if marker.enabled:
            fill = fill_layer(view, marker, maps, fade)
    # Fine detail where lines crowd, as a hand would: fewer, lighter.
    segs, outline, weight = st.simplify(view.segs, view.outline, height)
    kinds = outline if style.profile_scale != 1.0 else None
    strokes = []
    lines = style.width > 0
    if comp.construction and lines:
        strokes += cp.construction_strokes(view.segs, height, width, style.hand,
                                           index=view.index, to_buffer=view.scale)
    if comp.ground:
        strokes += cp.ground_strokes(view, height, style.hand)
    if maps is not None and marker.hatching:
        shade = hatch.hatch_strokes(maps, marker, view.scale, height, style.hand)
        if fade is not None:
            shade = cp.thin_out(shade, fade, view.scale)
        strokes += shade
    if lines:
        strokes += st.strokes_for(segs, kinds, style, height, weight)
    if ox or oy:
        shift = np.array([ox, oy], dtype=np.float64)
        strokes = [st.Stroke(s.outline + shift, s.opacity) for s in strokes]
    solid = (resize_array((view.index >= 0)[:, :, None].astype(np.float64),
                          width, height)[:, :, 0] * min(max(opacity, 0.0), 1.0)
             if transparent and opacity > 0 else None)
    return Layers(sheet, fill, strokes, (ox, oy), (width, height), transparent, solid)
