"""Make the parts a painter painted as glass behave like glass.

A painter answers in one material: the whole lantern, brass and panes alike,
arrives opaque. Nothing in the geometry says which faces are glass -- a pane and
the frame around it are the same surface as far as the mesh is concerned.

What does say so is the paint. A lantern's panes are cool where its body is
warm, and the split is not subtle: on the Trial Lantern, 16,818 faces sit in a
tight gold cluster and 1,651 sit in the cool one. So the faces are chosen by the
colour they were given, in a hue family a person can name, and handed a second
material that keeps every texture the first one had and adds transmission.

Which colour is glass is not something to infer. A blue vase is not a window,
and a brass lantern with a green patina is not six green windows. The caller
names the family, the same way it names how big the thing is, and a run that
names nothing does nothing.

Usage:
  blender -b --factory-startup --python scripts/blender/assign_transparent_material.py \
      -- <painted.glb> <output.glb> <report.json> --colour teal [--transmission 0.85] [--minimum-share 0.005]
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

# Hue families as a person names them, in Blender's 0..1 hue. They overlap at
# the edges on purpose: somebody who says "teal" about something a shade bluer
# should still get their glass.
FAMILIES: dict[str, tuple[float, float]] = {
    "red": (0.94, 1.04),
    "amber": (0.03, 0.10),
    "yellow": (0.10, 0.19),
    "green": (0.19, 0.44),
    "teal": (0.40, 0.60),
    "blue": (0.54, 0.74),
    "violet": (0.70, 0.86),
    "pink": (0.84, 0.97),
}

MINIMUM_SATURATION = 0.12
"""Below this a colour has no hue worth reading, and reading one anyway would
scatter transparent faces through every grey part of the model."""


def read_option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def in_family(hue: float, span: tuple[float, float]) -> bool:
    low, high = span
    # A family may wrap past 1.0, because red does.
    return low <= hue <= high or low <= hue + 1.0 <= high


def base_colour_image(material):
    """The image feeding base colour, which is the one that says what a face is."""
    tree = material.node_tree
    for link in tree.links:
        if link.to_socket.name != "Base Color":
            continue
        node = link.from_node
        if node.type == "TEX_IMAGE" and node.image:
            return node.image
    return next((n.image for n in tree.nodes if n.type == "TEX_IMAGE" and n.image), None)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [item for index, item in enumerate(argv)
                  if not item.startswith("--")
                  and (index == 0 or not argv[index - 1].startswith("--"))]
    if len(positional) < 3:
        print("[GLASS] FAILED: expected <source> <output.glb> <report.json> --colour <family>")
        return 2

    source, output, report_path = (Path(positional[0]), Path(positional[1]), Path(positional[2]))
    colour = (read_option(argv, "--colour") or "").strip().lower()
    transmission = float(read_option(argv, "--transmission", "0.85"))
    minimum_share = float(read_option(argv, "--minimum-share", "0.005"))

    if colour not in FAMILIES:
        print("[GLASS] FAILED: name the colour the glass was painted, one of: {0}".format(
            ", ".join(sorted(FAMILIES))))
        return 1
    if not 0.0 < transmission <= 1.0:
        print("[GLASS] FAILED: transmission must be above 0 and at most 1")
        return 1
    if not source.is_file():
        print("[GLASS] FAILED: source does not exist: {0}".format(source))
        return 1
    if output.exists():
        print("[GLASS] FAILED: refusing to overwrite {0}".format(output))
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        print("[GLASS] FAILED: expected one mesh object, found {0}".format(len(meshes)))
        return 1

    mesh_object = meshes[0]
    mesh = mesh_object.data
    if not mesh.materials:
        print("[GLASS] FAILED: the mesh carries no material to read")
        return 1
    if not mesh.uv_layers.active:
        print("[GLASS] FAILED: the mesh has no UVs, so its paint cannot be read per face")
        return 1

    painted = mesh.materials[0]
    image = base_colour_image(painted)
    if image is None:
        print("[GLASS] FAILED: the material has no base colour image to read")
        return 1

    width, height = image.size
    pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
    uv_layer = mesh.uv_layers.active.data

    span = FAMILIES[colour]
    chosen = []
    for polygon in mesh.polygons:
        centre = Vector((0.0, 0.0))
        for loop in polygon.loop_indices:
            centre += uv_layer[loop].uv
        centre /= len(polygon.loop_indices)
        x = min(width - 1, max(0, int(centre.x * width)))
        y = min(height - 1, max(0, int(centre.y * height)))
        red, green, blue = (float(value) for value in pixels[y, x, :3])
        hue, saturation, _ = colorsys.rgb_to_hsv(red, green, blue)
        if saturation >= MINIMUM_SATURATION and in_family(hue, span):
            chosen.append(polygon.index)

    share = len(chosen) / max(len(mesh.polygons), 1)
    if share < minimum_share:
        # Finding almost nothing means the named colour is not on this model.
        # Turning three faces to glass and calling it done would be worse than
        # saying so: the caller would believe it had worked.
        print("[GLASS] FAILED: {0} is {1:.2%} of this model's faces, which is not a glazed part. "
              "Name the colour its glass was actually painted.".format(colour, share))
        return 1

    glass = painted.copy()
    glass.name = "{0}_Glass".format(painted.name)
    surface = next(n for n in glass.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    # Keeps every texture the painted material had, so the etching in a pane
    # survives; transmission is added rather than substituted.
    for name, value in (("Transmission Weight", transmission), ("Roughness", 0.08), ("IOR", 1.45)):
        if name in surface.inputs:
            surface.inputs[name].default_value = value
    glass.blend_method = "BLEND" if hasattr(glass, "blend_method") else glass.blend_method
    mesh.materials.append(glass)
    glass_index = len(mesh.materials) - 1
    for index in chosen:
        mesh.polygons[index].material_index = glass_index

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(output), export_format="GLB", export_yup=True, export_apply=True,
        export_animations=False, export_cameras=False, export_lights=False)
    if not output.is_file():
        print("[GLASS] FAILED: the exporter wrote no file")
        return 1

    report = {
        "schema": "reference-asset-compiler.transparent-material.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "colour": colour,
        "hue_span": list(span),
        "transmission": transmission,
        "faces": {
            "total": len(mesh.polygons),
            "transparent": len(chosen),
            "share": round(share, 5),
        },
        "materials": [material.name for material in mesh.materials],
        "geometry_unchanged": True,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[GLASS] {0} of {1} faces are {2} and now transmit at {3}".format(
        len(chosen), len(mesh.polygons), colour, transmission))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
