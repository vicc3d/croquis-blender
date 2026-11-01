# SPDX-License-Identifier: GPL-3.0-or-later
"""The style thumbnails of the panel, drawn by Croquis on a small scene
made here:

    blender -b --factory-startup --python tools/thumbnails.py

Leaves croquis_blender/thumbnails/<style>.jpg, one for each ready-made
style."""
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import croquis_blender as croquis  # noqa: E402
from croquis_blender import ops  # noqa: E402
from croquis_blender.core import presets as ps  # noqa: E402

OUT = ROOT / "croquis_blender" / "thumbnails"
SIZE = 256


def material(name, rgba):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = rgba
    return m


def box(size, location, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o = bpy.context.object
    o.scale = size
    o.data.materials.append(mat)
    return o


# A small house with a pergola beside it, on a terrace.
scene = bpy.context.scene
for o in list(scene.objects):
    bpy.data.objects.remove(o)
wall = material("Wall", (0.75, 0.62, 0.45, 1))
roof = material("Roof", (0.45, 0.12, 0.08, 1))
wood = material("Wood", (0.30, 0.16, 0.07, 1))
stone = material("Stone", (0.55, 0.55, 0.52, 1))
glass = material("Glass", (0.10, 0.28, 0.55, 1))
box((8, 7, 0.2), (0.5, 0, 0.1), stone)
box((3.2, 3, 2.6), (-1, 0.5, 1.5), wall)
box((3.6, 3.4, 0.25), (-1, 0.5, 2.9), roof)
box((1.0, 0.05, 1.6), (-1, -1.03, 1.2), glass)
for x in (1.2, 3.6):
    for y in (-1.4, 1.4):
        box((0.15, 0.15, 2.4), (x, y, 1.4), wood)
for i in range(7):
    box((2.9, 0.12, 0.2), (2.4, -1.5 + i * 0.5, 2.7), wood)
bpy.ops.object.camera_add(location=(10, -8, 5.5))
cam = bpy.context.object
cam.rotation_euler = (math.radians(66), 0, math.radians(47))
cam.data.lens = 48
scene.camera = cam
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(45), 0, math.radians(-35)))
scene.render.resolution_x = scene.render.resolution_y = 1000

croquis.register()
s = scene.croquis
s.hand = 50
OUT.mkdir(exist_ok=True)
for key in ps.PRESETS:
    s.preset = key
    layers, secs = ops.draw(bpy.context, width=4 * SIZE)
    img = ops.to_image(layers, f"thumb-{key}")
    img.scale(SIZE, SIZE)
    img.file_format = "JPEG"
    img.save(filepath=str(OUT / f"{key}.jpg"), quality=88)
    print(f"{key}: {secs:.1f} s")
