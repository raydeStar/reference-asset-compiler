"""Export the staged asset as a self-contained GLB a browser studio can load.

The FBX export beside this one is for Unreal and applies UE's axis convention.
A browser wants the opposite: glTF's own +Y up, metres, one file with its
textures inside it. Blender's glTF exporter converts the Z-up staged scene on
the way out, so the payload arrives in browser convention without anything
downstream converting it -- which is exactly what the browser studio contract
requires, because an import that converts is an import that can convert wrongly.

Nothing is judged here and the source is not modified. The stage exports, counts
what it exported, and stops; the skeleton fingerprint is taken from the written
file afterwards by the compiler, never from this scene's memory.

Usage:
  blender -b --factory-startup --python scripts/blender/export_browser_payload.py \
      -- <source.fbx|blend|glb> <payload.glb> <report.json>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy


def import_any(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path))
    elif suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise SystemExit("unsupported source format: " + suffix)


def scene_counts() -> dict:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    vertices = 0
    triangles = 0
    materials = set()
    for obj in meshes:
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        vertices += len(mesh.vertices)
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        evaluated.to_mesh_clear()
        for slot in obj.material_slots:
            if slot.material:
                materials.add(slot.material.name)
    return {
        "mesh_objects": len(meshes),
        "armatures": len(armatures),
        "bones": sum(len(obj.data.bones) for obj in armatures),
        "vertices": vertices,
        "triangles": triangles,
        "materials": sorted(materials),
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 3:
        print("[PAYLOAD] FAILED: expected <source> <payload.glb> <report.json>")
        return 2

    source = Path(argv[0])
    payload = Path(argv[1])
    report_path = Path(argv[2])
    if not source.is_file():
        print("[PAYLOAD] FAILED: source does not exist: {0}".format(source))
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    import_any(source)

    before = scene_counts()
    if before["mesh_objects"] == 0:
        print("[PAYLOAD] FAILED: the source carries no mesh to export")
        return 1

    payload.parent.mkdir(parents=True, exist_ok=True)
    # A self-contained GLB: one file, textures inside it, no external URIs, and
    # the exporter's own Z-up to Y-up conversion rather than a hand-rolled one.
    bpy.ops.export_scene.gltf(
        filepath=str(payload),
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_texture_dir="",
        export_skins=before["armatures"] > 0,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
    )
    if not payload.is_file():
        print("[PAYLOAD] FAILED: the exporter wrote no file")
        return 1

    report = {
        "schema": "reference-asset-compiler.browser-payload.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "payload": str(payload),
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "payload_bytes": payload.stat().st_size,
        "convention": {"up": "+Y", "units": "metres", "self_contained": True},
        "exported": before,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[PAYLOAD] wrote {0} ({1} bytes, {2} triangles)".format(
        payload.name, report["payload_bytes"], before["triangles"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
