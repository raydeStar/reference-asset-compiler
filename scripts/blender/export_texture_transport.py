"""Export a reviewed static mesh to OBJ without silently changing its surface.

Hunyuan3D-Paint's local runner reads OBJ/GLB through trimesh but cannot read
FBX.  This adapter keeps the reviewed FBX/BLEND as authority, emits an OBJ
transport derivative, reimports it, and records a symmetric vertex-surface
check plus UV completeness before texture inference may begin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils.kdtree import KDTree


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_obj", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--maximum-delta-m", type=float, default=1e-6)
    return parser.parse_args(values)


def import_mesh(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix in {".glb", ".gltf"}:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise RuntimeError("Source must be BLEND, FBX, GLB, GLTF, or OBJ")


def mesh_object():
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Texture transport requires exactly one mesh; found {0}".format(
            len(meshes)))
    return meshes[0]


def snapshot(obj) -> dict:
    mesh = obj.data
    mesh.calc_loop_triangles()
    positions = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    uv = mesh.uv_layers.active
    uv_values = [tuple(value.uv) for value in uv.data] if uv else []
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.loop_triangles),
        "positions": positions,
        "uv_layer": uv.name if uv else None,
        "uv_loops": len(uv_values),
        "uv_finite": bool(uv_values) and all(
            all(float("-inf") < coordinate < float("inf") for coordinate in pair)
            for pair in uv_values
        ),
        "uv_min": min((min(pair) for pair in uv_values), default=None),
        "uv_max": max((max(pair) for pair in uv_values), default=None),
    }


def one_way_max(source, target) -> float:
    tree = KDTree(len(target))
    for index, point in enumerate(target):
        tree.insert(point, index)
    tree.balance()
    maximum = 0.0
    for point in source:
        _nearest, _index, distance = tree.find(point)
        maximum = max(maximum, float(distance))
    return maximum


def public(snapshot_value: dict) -> dict:
    return {key: value for key, value in snapshot_value.items() if key != "positions"}


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output_obj.resolve()
    report_path = args.report.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.suffix.lower() != ".obj":
        raise RuntimeError("Texture transport output must be OBJ")
    if output.exists() or report_path.exists():
        raise RuntimeError("Refusing to overwrite texture transport evidence")

    import_mesh(source)
    authority_obj = mesh_object()
    authority = snapshot(authority_obj)
    if not authority["uv_layer"] or not authority["uv_finite"]:
        raise RuntimeError("Texture transport source lacks a complete finite UV layout")

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    authority_obj.select_set(True)
    bpy.context.view_layer.objects.active = authority_obj
    bpy.ops.wm.obj_export(
        filepath=str(output),
        export_selected_objects=True,
        export_materials=True,
        export_uv=True,
        export_normals=True,
        export_triangulated_mesh=True,
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )

    import_mesh(output)
    transported_obj = mesh_object()
    transported = snapshot(transported_obj)
    forward = one_way_max(authority["positions"], transported["positions"])
    reverse = one_way_max(transported["positions"], authority["positions"])
    maximum_delta = max(forward, reverse)
    failures = []
    if authority["triangles"] != transported["triangles"]:
        failures.append("triangle count changed during OBJ transport")
    if not transported["uv_layer"] or not transported["uv_finite"]:
        failures.append("OBJ transport lacks a complete finite UV layout")
    if transported["uv_min"] is None or transported["uv_min"] < -1e-6:
        failures.append("OBJ transport UVs fall below zero")
    if transported["uv_max"] is None or transported["uv_max"] > 1.0 + 1e-6:
        failures.append("OBJ transport UVs exceed one")
    if maximum_delta > args.maximum_delta_m:
        failures.append("OBJ transport changed the reviewed surface")

    report = {
        "schema": "reference-asset-compiler.texture-transport.v1",
        "status": "passed" if not failures else "rejected",
        "source": {"path": str(source), "sha256": sha256(source), **public(authority)},
        "output": {"path": str(output), "sha256": sha256(output), **public(transported)},
        "maximum_symmetric_vertex_delta_m": maximum_delta,
        "maximum_allowed_delta_m": args.maximum_delta_m,
        "failures": failures,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_TEXTURE_TRANSPORT_REJECTED {0}".format("; ".join(failures)))
        return 1
    print("RAC_TEXTURE_TRANSPORT_OK triangles={0} delta_m={1:.9f} -- the porter changed the trunk, not the luggage.".format(
        transported["triangles"], maximum_delta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
