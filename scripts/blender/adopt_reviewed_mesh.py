"""Take a reviewed transport mesh into a .blend, changing nothing about it.

A mesh already in somebody's library is not a generator's guess. It has been
looked at, it carries real metres, and it has UVs and materials somebody chose.
What it does not have is a form the reduction stage will open: that stage takes
a .blend and insists on exactly one mesh object, because glTF is transport and
may split shared vertices at face-corner normals.

So this converts, and only converts. It does not scale -- the size is already
the size, and a staging step that re-fitted it to a human height would silently
resize an asset a person already approved. It does not weld, triangulate,
reorder or reproject. The one transform it applies is baking the importer's own
object scale into the vertex data, which leaves world-space geometry where it
was and makes what the reduction gate measures the mesh's own.

It also writes down what the derivative will later be compared against: the
counts, the extent, the UV layers, and the materials with their images. A
reduction that quietly drops the second UV map or half the materials is a real
loss, and nobody can see that loss without a record of what was there first.

Usage:
  blender -b --factory-startup --python scripts/blender/adopt_reviewed_mesh.py \
      -- <source.glb> <output.blend> <report.json> [--require-uvs]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy


def counts(mesh_object) -> dict:
    mesh = mesh_object.data
    mesh.calc_loop_triangles()
    return {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "faces": len(mesh.polygons),
        "triangles": len(mesh.loop_triangles),
    }


def surface(mesh_object) -> dict:
    """What a later comparison needs in order to notice a loss.

    Materials are listed with whether anything actually feeds their base
    colour, because a slot that survived a reduction with its image gone is a
    material in name only.
    """
    mesh = mesh_object.data
    materials = []
    for slot in mesh_object.material_slots:
        material = slot.material
        if material is None:
            materials.append({"name": None, "images": []})
            continue
        images = []
        if material.use_nodes and material.node_tree is not None:
            images = sorted({
                node.image.name for node in material.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image is not None})
        materials.append({"name": material.name, "images": images})
    return {
        "uv_layers": [layer.name for layer in mesh.uv_layers],
        "colour_attributes": [attribute.name for attribute in mesh.color_attributes],
        "materials": materials,
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [item for index, item in enumerate(argv)
                  if not item.startswith("--")
                  and (index == 0 or not argv[index - 1].startswith("--"))]
    if len(positional) < 3:
        print("[ADOPT] FAILED: expected <source> <output.blend> <report.json>")
        return 2

    source = Path(positional[0])
    output = Path(positional[1])
    report_path = Path(positional[2])
    require_uvs = "--require-uvs" in argv

    if not source.is_file():
        print("[ADOPT] FAILED: source does not exist: {0}".format(source))
        return 1
    if output.exists():
        # The reduction that follows is measured against this file's hash. A
        # second write into the same name would leave an older receipt naming
        # bytes nobody can produce again.
        print("[ADOPT] FAILED: refusing to overwrite {0}".format(output))
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0

    suffix = source.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        print("[ADOPT] FAILED: unsupported source format: {0}".format(suffix))
        return 1

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        print("[ADOPT] FAILED: the source carries no mesh")
        return 1
    if len(meshes) != 1:
        # Joining them would merge material slots and rewrite UV layers, which
        # is a decision about somebody's asset. A route that needs one mesh
        # from several should say so where a person can review it.
        print("[ADOPT] FAILED: expected one mesh object, found {0}: {1}".format(
            len(meshes), ", ".join(sorted(obj.name for obj in meshes))))
        return 1

    mesh = meshes[0]
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh

    before = tuple(round(value, 6) for value in mesh.dimensions)
    # Baking the importer's object scale moves no world-space vertex; it moves
    # the number out of the object and into the data, so the reduction gate's
    # millimetres are measured against the geometry rather than against a
    # scale somebody else already applied.
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    after = tuple(round(value, 6) for value in mesh.dimensions)
    drift = max(abs(a - b) for a, b in zip(before, after))
    if drift > 1e-5:
        print("[ADOPT] FAILED: applying the import scale moved the extent by {0:.6f} m".format(drift))
        return 1

    described = surface(mesh)
    if require_uvs and not described["uv_layers"]:
        # Said out loud rather than shrugged off: a reduction preserving UVs is
        # the whole reason this route exists, and there is nothing to preserve.
        print("[ADOPT] FAILED: this mesh has no UV layer, so nothing downstream can preserve one")
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))

    report = {
        "schema": "reference-asset-compiler.adopted-mesh.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "mesh_object": mesh.name,
        "adopted": counts(mesh),
        "surface": described,
        "dimensions_m": list(after),
        "extent_drift_m": round(drift, 9),
        # Stated as a fact a reader can rely on, because everything downstream
        # is entitled to assume the derivative began from these exact bytes.
        "geometry_changed": False,
        "note": "Converted only. No vertex moved, no UV reprojected, no material dropped.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[ADOPT] wrote {0}: {1} triangles, {2} UV layers, {3} materials, {4} m tall".format(
        output.name, report["adopted"]["triangles"], len(described["uv_layers"]),
        len(described["materials"]), round(max(after), 3)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
