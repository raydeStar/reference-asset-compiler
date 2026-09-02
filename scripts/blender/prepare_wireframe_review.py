"""Prepare a non-destructive solid-plus-wireframe Blender review scene."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy


def material(name: str, color: tuple[float, float, float, float], roughness: float):
    value = bpy.data.materials.new(name)
    value.diffuse_color = color
    value.use_nodes = True
    bsdf = value.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    return value


def main() -> int:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--thickness", type=float, default=0.0007)
    args = parser.parse_args(values)
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("Wireframe review refuses to overwrite evidence")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        candidates = [obj for obj in meshes if obj.name.startswith("GEO_RAC_")]
        if len(candidates) != 1:
            raise RuntimeError("Wireframe review requires one unambiguous candidate mesh")
        solid = candidates[0]
        for obj in meshes:
            if obj != solid:
                bpy.data.objects.remove(obj, do_unlink=True)
    else:
        solid = meshes[0]
    solid.name = "REVIEW_Solid"
    clay = material("REVIEW_Clay", (0.62, 0.64, 0.68, 1.0), 0.48)
    ink = material("REVIEW_Topology", (0.018, 0.022, 0.028, 1.0), 0.32)
    solid.data.materials.clear()
    solid.data.materials.append(clay)
    wire = solid.copy()
    wire.data = solid.data.copy()
    wire.name = "REVIEW_Wireframe"
    wire.data.materials.clear()
    wire.data.materials.append(ink)
    bpy.context.collection.objects.link(wire)
    modifier = wire.modifiers.new("REVIEW_Wireframe", "WIREFRAME")
    modifier.thickness = args.thickness
    modifier.use_replace = True
    modifier.use_even_offset = True
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print("RAC_WIREFRAME_REVIEW_SCENE_OK {0}".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
