# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The styles as the panel shows them: the ready-made ones with their
thumbnails, and your own, saved under a name.

Your own styles live in the extension's user folder (``styles.json``, and
a thumbnail of each from the last drawing), so they outlast updates and
serve every .blend."""

import json
from pathlib import Path

import bpy
import bpy.utils.previews
import numpy as np
from bpy.props import StringProperty

from . import i18n
from .core import presets as ps

#: The ready-made styles and «Custom», in the order that numbers them in a
#: saved .blend (Blender saves a choice by its number).
BUILT_IN = [*ps.PRESETS, "custom"]
#: Styles of your own are numbered from here, clear of the ready-made ones.
OWN_FIRST = 100
#: A thumbnail's side, in pixels.
THUMB = 256
#: Where your own styles are kept; tests point it elsewhere.
folder_override = None

_previews = None
_own: dict = {}        # id → {"name", "number", "settings"}
_items: list = []      # Blender wants the list kept alive while it is shown


def folder() -> Path:
    """The folder of your own styles, made if missing."""
    if folder_override:
        path = Path(folder_override)
    else:
        try:
            path = Path(bpy.utils.extension_path_user(__package__, create=True))
        except Exception:                # noqa: BLE001 (not installed as an extension)
            path = Path(bpy.utils.user_resource("CONFIG", path="croquis", create=True))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _thumb_path(number: int) -> Path:
    return folder() / f"style-{number}.png"


def is_own(key: str) -> bool:
    return key in _own


def own_name(key: str) -> str:
    return _own[key]["name"] if key in _own else ""


def own_settings(key: str) -> dict:
    return dict(_own[key]["settings"])


def load() -> None:
    """Your own styles from their file; one that cannot be read is left
    out, never the panel."""
    _own.clear()
    try:
        data = json.loads((folder() / "styles.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for entry in data.get("styles", []) if isinstance(data, dict) else []:
        try:
            number = int(entry["number"])
            name = str(entry["name"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if number >= OWN_FIRST and name:
            _own[f"own_{number}"] = {"name": name, "number": number,
                                     "settings": ps.own_style(entry.get("settings"))}


def _write() -> None:
    path = folder() / "styles.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"styles": sorted(_own.values(), key=lambda e: e["number"])},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _icon(key: str, path: Path):
    """A thumbnail's icon id, or None when there is no picture."""
    if _previews is None or not path.is_file():
        return None
    if key in _previews:
        del _previews[key]
    return _previews.load(key, str(path), "IMAGE").icon_id


def _reload_icons() -> None:
    if _previews is None:
        return
    _previews.clear()
    here = Path(__file__).parent / "thumbnails"
    for key in ps.PRESETS:
        _icon(key, here / f"{key}.jpg")
    for key, entry in _own.items():
        _icon(key, _thumb_path(entry["number"]))


def enum_items(_self, _context):
    """The panel's styles: the ready-made ones, «Custom», then your own."""
    _items.clear()
    for number, key in enumerate(BUILT_IN):
        if key == "custom":
            _items.append((key, "Custom", "Your own choices", "PREFERENCES", number))
        else:
            icon = _previews[key].icon_id if _previews and key in _previews else "BRUSH_DATA"
            _items.append((key, ps.PRESETS[key][0], "", icon, number))
    for key, entry in sorted(_own.items(), key=lambda kv: kv[1]["name"].lower()):
        icon = _previews[key].icon_id if _previews and key in _previews else "USER"
        _items.append((key, entry["name"], "A style of your own", icon, entry["number"]))
    return _items


def matching(state: dict, current: str) -> str:
    """The style the settings still are: the one chosen if it still holds,
    else a ready-made one, else one of your own, else «Custom»."""
    mine = ps.own_style(state)
    if current in _own and _own[current]["settings"] == mine:
        return current
    built = ps.matching_preset(state)
    if built != "custom":
        return built
    for key, entry in _own.items():
        if entry["settings"] == mine:
            return key
    return "custom"


def _save_thumbnail(layers, path: Path) -> None:
    """The middle of the last drawing, squared and made small."""
    rgb = layers.pixels()
    h, w = rgb.shape[:2]
    side = min(h, w)
    y0, x0 = (h - side) // 2, (w - side) // 2
    pick = np.linspace(0, side - 1, THUMB).astype(int)
    small = rgb[y0:y0 + side, x0:x0 + side][pick][:, pick]
    img = bpy.data.images.new("croquis-style-thumbnail", THUMB, THUMB, alpha=False)
    try:
        px = np.ones((THUMB, THUMB, 4), np.float32)
        px[:, :, :3] = small[::-1] / 255.0          # Blender's rows go up
        img.pixels.foreach_set(px.reshape(-1))
        img.filepath_raw = str(path)
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def save_style(name: str, state: dict, layers=None) -> str:
    """Your choices saved as the style ``name`` (one of that name is
    replaced); its id. A thumbnail from ``layers``, the last drawing."""
    key = next((k for k, e in _own.items() if e["name"].lower() == name.lower()), None)
    if key is None:
        number = max([e["number"] for e in _own.values()] + [OWN_FIRST - 1]) + 1
        key = f"own_{number}"
    else:
        number = _own[key]["number"]
    _own[key] = {"name": name, "number": number, "settings": ps.own_style(state)}
    _write()
    thumb = _thumb_path(number)
    if layers is not None:
        try:
            _save_thumbnail(layers, thumb)
        except (OSError, RuntimeError):
            pass
    _icon(key, thumb)
    return key


def delete_style(key: str) -> None:
    entry = _own.pop(key, None)
    if entry is None:
        return
    _write()
    try:
        _thumb_path(entry["number"]).unlink()
    except OSError:
        pass
    if _previews is not None and key in _previews:
        del _previews[key]


class CROQUIS_OT_style_save(bpy.types.Operator):
    """Save these choices as a style of your own"""
    bl_idname = "croquis.style_save"
    bl_label = "Save as a style"

    name: StringProperty(name="Name")

    def invoke(self, context, _event):
        s = context.scene.croquis
        self.name = own_name(s.preset) or i18n.tr("My style")
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        from . import ops, props
        name = self.name.strip()
        if not name:
            self.report({"WARNING"}, i18n.tr("Give the style a name"))
            return {"CANCELLED"}
        s = context.scene.croquis
        key = save_style(name, props.settings_dict(s), ops.last_layers())
        props.choose(s, key)
        self.report({"INFO"}, i18n.tr("Saved the style {name}", name=name))
        return {"FINISHED"}


class CROQUIS_OT_style_delete(bpy.types.Operator):
    """Delete this style of your own"""
    bl_idname = "croquis.style_delete"
    bl_label = "Delete the style"

    @classmethod
    def poll(cls, context):
        return is_own(context.scene.croquis.preset)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from . import props
        s = context.scene.croquis
        name = own_name(s.preset)
        delete_style(s.preset)
        props.choose(s, matching(props.settings_dict(s), ""))
        self.report({"INFO"}, i18n.tr("Deleted the style {name}", name=name))
        return {"FINISHED"}


classes = (CROQUIS_OT_style_save, CROQUIS_OT_style_delete)


def register() -> None:
    global _previews
    _previews = bpy.utils.previews.new()
    load()
    _reload_icons()
    for c in classes:
        bpy.utils.register_class(c)


def unregister() -> None:
    global _previews
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    _items.clear()
