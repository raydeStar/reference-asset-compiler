"""Normalize review shading while proving mesh geometry remains byte-identical."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import sha256_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("output_glb", type=Path)
    parser.add_argument("report", type=Path)
    return parser.parse_args(values)


def geometry_fingerprint(obj: bpy.types.Object) -> str:
    digest = hashlib.sha256()
    digest.update(struct.pack("<16d", *(value for row in obj.matrix_world for value in row)))
    digest.update(struct.pack("<QQ", len(obj.data.vertices), len(obj.data.polygons)))
    for vertex in obj.data.vertices:
        digest.update(struct.pack("<3d", *(float(value) for value in vertex.co)))
    for polygon in obj.data.polygons:
        digest.update(struct.pack("<Q", len(polygon.vertices)))
        digest.update(struct.pack("<{0}I".format(len(polygon.vertices)), *polygon.vertices))
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output_blend = args.output_blend.resolve()
    output_glb = args.output_glb.resolve()
    report_path = args.report.resolve()
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("Smooth review preparation requires a native .blend source")
    if any(path.exists() for path in (output_blend, output_glb, report_path)):
        raise RuntimeError("Smooth review preparation refuses to overwrite an attempt")

    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Smooth review preparation requires exactly one mesh object")
    candidate = meshes[0]
    before_fingerprint = geometry_fingerprint(candidate)
    before_smooth = sum(polygon.use_smooth for polygon in candidate.data.polygons)
    for polygon in candidate.data.polygons:
        polygon.use_smooth = True
    candidate.data.update()
    after_fingerprint = geometry_fingerprint(candidate)
    if after_fingerprint != before_fingerprint:
        raise RuntimeError("Review shading unexpectedly changed mesh geometry")

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(output_glb), export_format="GLB", use_selection=True,
        export_materials="NONE")
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    payload = {
        "schema": "reference-asset-compiler.smooth-review-derivative.v1",
        "source": str(source),
        "source_sha256": sha256_file(source),
        "output_blend": str(output_blend),
        "output_blend_sha256": sha256_file(output_blend),
        "output_glb": str(output_glb),
        "output_glb_sha256": sha256_file(output_glb),
        "geometry_fingerprint_before": before_fingerprint,
        "geometry_fingerprint_after": after_fingerprint,
        "geometry_unchanged": True,
        "smooth_faces_before": before_smooth,
        "smooth_faces_after": len(candidate.data.polygons),
        "operation": "set_polygon_smooth_flags_only",
        "production_grade": False,
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("RAC_SMOOTH_REVIEW_OK report={0}".format(report_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
