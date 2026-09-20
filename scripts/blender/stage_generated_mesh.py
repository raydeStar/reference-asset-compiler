"""Put a generated mesh at its real size, in a form a reviewed stage can open.

Two things a generator's answer is missing before anything else can judge it.

It is glTF, which is transport: it may split shared vertices at face-corner
normals, and it is not an editable topology authority. The reduction stage
opens a .blend and insists on exactly one mesh object, which is right of it to
insist on, so something has to convert.

And it has no size. Whatever the subject, the output arrives about two metres
tall, because the generator normalises. A reduction gate that allows a
millimetre of surface deviation cannot mean anything against a lantern six
times its real size, so the height comes in from a caller who was asked a
question they could answer -- where it comes up to on a person -- and is
applied here, once, before any gate measures anything.

Nothing here judges geometry or changes its shape. It converts, scales
uniformly, counts, and says what it did.

Usage:
  blender -b --factory-startup --python scripts/blender/stage_generated_mesh.py \
      -- <source.glb> <output.blend> <report.json> --height-m <metres> [--size <name>]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy


def read_option(argv: list[str], name: str, default: str | None = None) -> str | None:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def counts(mesh_objects) -> dict:
    vertices = 0
    triangles = 0
    for obj in mesh_objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        vertices += len(mesh.vertices)
        triangles += len(mesh.loop_triangles)
    return {"vertices": vertices, "triangles": triangles}


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [item for index, item in enumerate(argv)
                  if not item.startswith("--")
                  and (index == 0 or not argv[index - 1].startswith("--"))]
    if len(positional) < 3:
        print("[STAGE] FAILED: expected <source> <output.blend> <report.json> --height-m <metres>")
        return 2

    source = Path(positional[0])
    output = Path(positional[1])
    report_path = Path(positional[2])
    height_text = read_option(argv, "--height-m")
    size_name = read_option(argv, "--size")

    if not source.is_file():
        print("[STAGE] FAILED: source does not exist: {0}".format(source))
        return 1
    if output.exists():
        print("[STAGE] FAILED: refusing to overwrite {0}".format(output))
        return 1
    try:
        height_m = float(height_text)
    except (TypeError, ValueError):
        print("[STAGE] FAILED: --height-m must be a number of metres, got {0!r}".format(height_text))
        return 1
    if not 0.001 <= height_m <= 100.0:
        print("[STAGE] FAILED: a real-world height of {0} m is not plausible".format(height_m))
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0

    suffix = source.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    else:
        print("[STAGE] FAILED: unsupported source format: {0}".format(suffix))
        return 1

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        print("[STAGE] FAILED: the source carries no mesh")
        return 1
    if len(meshes) != 1:
        # Joining them would be a decision about the asset, and this step does
        # not make decisions about assets. Anything wanting one mesh from
        # several should say so where a person can review it.
        print("[STAGE] FAILED: expected one mesh object, found {0}: {1}".format(
            len(meshes), ", ".join(sorted(obj.name for obj in meshes))))
        return 1

    mesh = meshes[0]
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    # Bake whatever transform the import left, so the dimensions read below are
    # the mesh's own and the factor is computed against geometry, not a scale
    # somebody else already applied.
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    before = tuple(round(value, 6) for value in mesh.dimensions)
    tallest = max(before)
    if tallest <= 0:
        print("[STAGE] FAILED: the mesh has no extent to scale")
        return 1
    factor = height_m / tallest
    mesh.scale = (factor, factor, factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    after = tuple(round(value, 6) for value in mesh.dimensions)

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))

    report = {
        "schema": "reference-asset-compiler.staged-mesh.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "mesh_object": mesh.name,
        "scale": {
            "requested_size": size_name,
            "requested_height_m": height_m,
            "factor": round(factor, 8),
            "dimensions_before_m": list(before),
            "dimensions_after_m": list(after),
        },
        "exported": counts([mesh]),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[STAGE] wrote {0}: {1} triangles, {2} m tall (x{3:.4f})".format(
        output.name, report["exported"]["triangles"], round(max(after), 3), factor))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
