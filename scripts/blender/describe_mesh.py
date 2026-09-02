"""Measure a candidate mesh and unpack its textures. Read-only on the source.

A generated GLB carries its textures inside itself, and a recipe has to point
at files that exist beside the FBX that ships. This reports what the mesh
actually contains -- objects, triangles, materials, bounds -- and writes each
material's base colour out as a PNG so the recipe can name it.

Nothing here judges the mesh or changes it. It answers the questions a recipe
has to answer and stops.

Usage:
  blender -b --factory-startup --python scripts/blender/describe_mesh.py \
      -- <mesh.glb|fbx|obj> <out_dir> <report.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def import_any(path: Path):
    suffix = path.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise SystemExit("unsupported mesh format: " + suffix)


def base_colour_image(material):
    """The image feeding Base Color, not merely the first image present.

    A generated material often carries more than one -- Pixal3D emits two --
    and picking the wrong one gives a recipe that compiles a normal map as
    though it were albedo.
    """
    if not material.use_nodes:
        return None
    bsdf = next((n for n in material.node_tree.nodes
                 if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        socket = bsdf.inputs.get("Base Color")
        if socket is not None and socket.is_linked:
            node = socket.links[0].from_node
            # Step through anything the exporter put in the way.
            for _ in range(4):
                if node.type == "TEX_IMAGE":
                    return node.image
                incoming = [i for i in node.inputs if i.is_linked]
                if not incoming:
                    break
                node = incoming[0].links[0].from_node
    images = [n.image for n in material.node_tree.nodes
              if n.type == "TEX_IMAGE" and n.image]
    return images[0] if images else None


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    source, out_dir, report_path = Path(argv[0]), Path(argv[1]), Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_any(source)

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        print("[DESCRIBE] FAILED: no mesh in {0}".format(source))
        return 1

    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    tris = verts = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        tris += len(obj.data.loop_triangles)
        verts += len(obj.data.vertices)
        for vertex in obj.data.vertices:
            world = obj.matrix_world @ vertex.co
            for axis in range(3):
                lo[axis] = min(lo[axis], world[axis])
                hi[axis] = max(hi[axis], world[axis])

    materials, textures = [], {}
    for material in bpy.data.materials:
        used = any(slot.material is material
                   for obj in meshes for slot in obj.material_slots)
        if not used:
            continue
        materials.append(material.name)
        image = base_colour_image(material)
        if image is None:
            continue
        safe = "".join(c if c.isalnum() else "_" for c in material.name)
        target = out_dir / ("T_{0}_BaseColor.png".format(safe))
        # Resolve before saving: Image.save() writes nothing at all when
        # filepath_raw is relative, and reports no error doing it.
        image.filepath_raw = str(target.resolve())
        image.file_format = "PNG"
        try:
            image.save()
        except RuntimeError as error:
            print("[DESCRIBE] could not write {0}: {1}".format(target.name, error))
            continue
        textures[material.name] = target.name

    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    report = {
        "source": str(source),
        "blender_version": bpy.app.version_string,
        "objects": len(meshes),
        "verts": verts,
        "tris": tris,
        "materials": sorted(materials),
        "textures": textures,
        "has_armature": bool(armatures),
        "bounds_min": [round(v, 5) for v in lo],
        "bounds_max": [round(v, 5) for v in hi],
        "size_m": [round(hi[i] - lo[i], 5) for i in range(3)],
        "height_m": round(hi.z - lo.z, 5),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[DESCRIBE] {0} objects, {1} tris, {2} materials, {3:.3f} m tall".format(
        report["objects"], report["tris"], len(materials), report["height_m"]))
    for name, file in sorted(textures.items()):
        print("[DESCRIBE] {0} -> {1}".format(name, file))
    if armatures:
        print("[DESCRIBE] carries an armature; this is not a static prop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
