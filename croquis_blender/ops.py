# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Drawing the view, and saving the drawing; drawing an animation, frame
by frame."""

import os
import shutil
import time

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import i18n, props
from . import scene_view as sv

IMAGE_NAME = "Croquis"
#: The last drawing's layers, to save as SVG or PDF without drawing again.
_last = {"layers": None}
FORMATS = [("PNG", "PNG", "The drawing as a picture"),
           ("SVG", "SVG in layers", "Paper, colour and the ink as vector paths"),
           ("PDF", "PDF", "One page at 300 dpi, the ink as vector paths")]


def _read_image(path: str):
    """An image of your own for the paper, through Blender."""
    try:
        img = bpy.data.images.load(path, check_existing=True)
    except RuntimeError:
        return None
    w, h = img.size
    px = np.empty(w * h * img.channels, np.float32)
    img.pixels.foreach_get(px)
    rgb = px.reshape(h, w, img.channels)[::-1, :, :3]
    if img.is_float:
        rgb = sv._to_srgb(rgb)
    return rgb * 255.0


def last_layers():
    """The last drawing's layers, or None before the first drawing."""
    return _last["layers"]


def view_area(context):
    """The 3D viewport to draw from: this one, or the first in the window."""
    if context.area and context.area.type == "VIEW_3D":
        return context.area
    for a in context.screen.areas if context.screen else ():
        if a.type == "VIEW_3D":
            return a
    return None


def camera_for(context, source: str):
    """``(camera, None)`` or ``(None, why)``."""
    depsgraph = context.evaluated_depsgraph_get()
    scene = context.scene
    if source == "camera":
        if scene.camera is None:
            return None, "The scene has no camera: add one, or draw from this view"
        return sv.camera_from_object(scene.camera.evaluated_get(depsgraph),
                                     depsgraph, scene), None
    area = view_area(context)
    if area is None:
        return None, "No 3D viewport to draw from"
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    return sv.camera_from_view(region, area.spaces.active.region_3d), None


def draw(context, settings=None, width: int | None = None):
    """The drawing of the view as Croquis's layers, and how long it took.
    Raises ``ValueError`` when there is nothing to draw from."""
    from .core import drawing
    from .core import paper as pp
    from .core import presets as ps
    panel = settings or context.scene.croquis
    s = props.settings_dict(panel)
    camera, why = camera_for(context, panel.source)
    if camera is None:
        raise ValueError(why)
    t = time.perf_counter()
    # From the camera, as a render: what is turned off for renders stays out.
    # From this view, in its local view (/): only what that shows.
    area = view_area(context) if panel.source == "view" else None
    space = area.spaces.active if area else None
    view_src = sv.BlenderView(context, context.evaluated_depsgraph_get(), camera,
                              render=panel.source == "camera",
                              selected=panel.only_selected,
                              local=space if space and space.local_view else None)
    if not len(view_src):
        raise ValueError("Nothing to draw: nothing selected is a visible mesh"
                         if panel.only_selected else
                         "Nothing to draw: the scene has no visible mesh")
    pp.IMAGE_READER = _read_image
    if width is None:
        width = s["size"] or s["custom_width"]
    layers = drawing.render(
        view_src, ps.line_style(s), width, marker=ps.marker_style(s),
        composition=ps.composition(s), paper_kind=s["paper"],
        paper_image=bpy.path.abspath(s["paper_image"]) if s["paper_image"] else "",
        transparent=context.scene.render.film_transparent, opacity=s["opacity"] / 100.0)
    return layers, time.perf_counter() - t


def blender_encode(rgb, fmt: str, quality: int = 90) -> bytes:
    """A picture encoded by Blender (JPEG or PNG), for the SVG and PDF."""
    import os
    import tempfile
    h, w, n = rgb.shape
    img = bpy.data.images.new("croquis-encode", w, h, alpha=n == 4)
    try:
        px = np.ones((h, w, 4), np.float32)
        px[:, :, :n] = np.asarray(rgb, np.float32)[::-1] / 255.0
        img.pixels.foreach_set(px.reshape(-1))
        ext = ".jpg" if fmt == "JPG" else ".png"
        fd, path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        try:
            img.filepath_raw = path
            img.file_format = "JPEG" if fmt == "JPG" else "PNG"
            if fmt == "JPG" and quality > 0:
                img.save(filepath=path, quality=quality)
            else:
                img.save(filepath=path)
            with open(path, "rb") as fh:
                return fh.read()
        finally:
            os.remove(path)
    finally:
        bpy.data.images.remove(img)


def save_drawing(layers, path: str, fmt: str) -> bool:
    """``layers`` saved at ``path`` as PNG, SVG or PDF."""
    from .core import vector
    if fmt == "PNG":
        img = to_image(layers)
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        return True
    return vector.save(layers, path, encode=blender_encode, dpi=300)


def to_image(layers, name: str = IMAGE_NAME):
    """The drawing in Blender's image ``name`` (made or replaced); on clear
    film, with its transparency."""
    clear = getattr(layers, "transparent", False)
    rgb = layers.rgba() if clear else layers.pixels()
    h, w, n = rgb.shape
    img = bpy.data.images.get(name)
    if img is None or tuple(img.size) != (w, h) or (img.depth == 32) != clear:
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, w, h, alpha=clear)
    px = np.ones((h, w, 4), np.float32)
    px[:, :, :n] = rgb[::-1] / 255.0              # Blender's rows go up
    img.pixels.foreach_set(px.reshape(-1))
    img.update()
    return img


def show(context, img) -> None:
    """In an image editor: one already open, else a window of its own."""
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.spaces.active.image = img
                return
    with context.temp_override():
        bpy.ops.wm.window_new()
    win = context.window_manager.windows[-1]
    area = win.screen.areas[0]
    area.type = "IMAGE_EDITOR"
    area.spaces.active.image = img


class CROQUIS_OT_draw(bpy.types.Operator):
    """Draw the view as a freehand sketch"""
    bl_idname = "croquis.draw"
    bl_label = "Draw the view"
    bl_options = {"REGISTER"}

    def execute(self, context):
        wm = context.window_manager
        wm.progress_begin(0, 1)
        try:
            layers, secs = draw(context)
        except ValueError as exc:
            self.report({"WARNING"}, i18n.tr(str(exc)))
            return {"CANCELLED"}
        finally:
            wm.progress_end()
        img = to_image(layers)
        _last["layers"] = layers
        context.scene.croquis_last = img.name
        show(context, img)
        self.report({"INFO"}, i18n.tr("Croquis: {w}×{h} in {s} s", w=img.size[0],
                                      h=img.size[1], s=f"{secs:.1f}"))
        return {"FINISHED"}


class CROQUIS_OT_save(bpy.types.Operator):
    """Save the last drawing as PNG, SVG in layers or PDF"""
    bl_idname = "croquis.save"
    bl_label = "Save the drawing…"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.png;*.svg;*.pdf", options={"HIDDEN"})
    format: EnumProperty(name="Format", items=FORMATS, default="PNG")

    @classmethod
    def poll(cls, context):
        return _last["layers"] is not None

    def _ext(self) -> str:
        return "." + self.format.lower()

    def check(self, _context) -> bool:
        """The file name follows the format chosen."""
        new = bpy.path.ensure_ext(self.filepath.rsplit(".", 1)[0]
                                  if self.filepath.lower().endswith((".png", ".svg", ".pdf"))
                                  else self.filepath, self._ext())
        if new != self.filepath:
            self.filepath = new
            return True
        return False

    def invoke(self, context, _event):
        if not self.filepath:
            self.filepath = (bpy.path.display_name_from_filepath(bpy.data.filepath)
                             or "croquis") + self._ext()
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = bpy.path.ensure_ext(self.filepath, self._ext())
        if not save_drawing(_last["layers"], path, self.format):
            self.report({"ERROR"}, i18n.tr("Could not save {path}", path=path))
            return {"CANCELLED"}
        self.report({"INFO"}, i18n.tr("Saved {path}", path=path))
        return {"FINISHED"}


def animation_frames(scene, twos: bool = False) -> list:
    """The frames to draw, ``(frame, held)``: the scene's range by its step;
    on twos, one drawing for every two frames, ``held`` the frames that
    repeat it."""
    frames = list(range(scene.frame_start, scene.frame_end + 1, max(1, scene.frame_step)))
    if not twos:
        return [(f, []) for f in frames]
    return [(frames[i], frames[i + 1:i + 2]) for i in range(0, len(frames), 2)]


def frame_path(folder: str, frame: int) -> str:
    return os.path.join(folder, f"croquis_{frame:04d}.png")


def draw_frame(context, frame: int, folder: str, held=()):
    """Frame ``frame`` drawn and saved as a PNG in ``folder`` (and copied
    for the ``held`` frames): its layers and how long it took."""
    context.scene.frame_set(frame)
    layers, secs = draw(context)
    path = frame_path(folder, frame)
    if not save_drawing(layers, path, "PNG"):
        raise OSError(path)
    for f in held:
        shutil.copyfile(path, frame_path(folder, f))
    return layers, secs


class CROQUIS_OT_draw_animation(bpy.types.Operator):
    """Draw every frame of the scene's animation, each one a PNG in a folder"""
    bl_idname = "croquis.draw_animation"
    bl_label = "Draw the animation…"

    directory: StringProperty(subtype="DIR_PATH")
    twos: BoolProperty(name="On twos", default=False,
                       description="One drawing for every two frames, held for "
                                   "both, as in hand-drawn animation: half the time")

    def invoke(self, context, _event):
        if not self.directory and bpy.data.filepath:
            self.directory = bpy.path.abspath("//croquis" + os.sep)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        folder = bpy.path.abspath(self.directory)
        if not folder:
            self.report({"WARNING"}, i18n.tr("Choose a folder for the frames"))
            return {"CANCELLED"}
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            self.report({"ERROR"}, i18n.tr("Could not save {path}", path=folder))
            return {"CANCELLED"}
        self._folder = folder
        self._todo = animation_frames(context.scene, self.twos)
        self._done = 0      # drawings
        self._frames = 0    # frames saved, the held ones too
        self._was = context.scene.frame_current
        self._t = time.perf_counter()
        wm = context.window_manager
        wm.progress_begin(0, len(self._todo))
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _finish(self, context, message):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_end()
        context.workspace.status_text_set(None)
        context.scene.frame_set(self._was)
        self.report(*message)
        return {"FINISHED"} if message[0] == {"INFO"} else {"CANCELLED"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._finish(context, ({"WARNING"}, i18n.tr(
                "Stopped: {n} frames drawn in {path}", n=self._frames, path=self._folder)))
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if self._done == len(self._todo):
            return self._finish(context, ({"INFO"}, i18n.tr(
                "Drew {n} frames in {path}", n=self._frames, path=self._folder)))
        frame, held = self._todo[self._done]
        try:
            layers, _secs = draw_frame(context, frame, self._folder, held)
        except ValueError as exc:
            return self._finish(context, ({"WARNING"}, i18n.tr(str(exc))))
        except OSError:
            return self._finish(context, ({"ERROR"}, i18n.tr(
                "Could not save {path}", path=frame_path(self._folder, frame))))
        self._done += 1
        self._frames += 1 + len(held)
        _last["layers"] = layers
        show(context, to_image(layers))
        context.window_manager.progress_update(self._done)
        context.workspace.status_text_set(i18n.tr(
            "Croquis: frame {n} of {total}, Esc to stop", n=self._done, total=len(self._todo)))
        return {"RUNNING_MODAL"}


classes = (CROQUIS_OT_draw, CROQUIS_OT_save, CROQUIS_OT_draw_animation)


def register() -> None:
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.croquis_last = StringProperty(options={"HIDDEN", "SKIP_SAVE"})


def unregister() -> None:
    del bpy.types.Scene.croquis_last
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
