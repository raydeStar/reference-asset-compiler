"""Project explicit joint-ring guides onto an approved AI-derived surface."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_instant_meshes import evaluated_triangles, sha256_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("report", type=Path)
    return parser.parse_args(values)


def basis(axis: Vector) -> tuple[Vector, Vector]:
    axis = axis.normalized()
    first = Vector((0.0, 1.0, 0.0))
    if abs(axis.dot(first)) > 0.95:
        first = Vector((1.0, 0.0, 0.0))
    first = (first - axis * axis.dot(first)).normalized()
    return first, axis.cross(first).normalized()


def project_ring(tree: BVHTree, ring: dict[str, object], samples: int):
    center = Vector(ring["center"])
    axis = Vector(ring["axis"]).normalized()
    first, second = basis(axis)
    radius = float(ring["cast_radius"])
    hits = []
    for index in range(samples):
        angle = 2.0 * math.pi * index / samples
        radial = first * math.cos(angle) + second * math.sin(angle)
        origin = center + radial * 1.0e-5
        location, normal, face_index, distance = tree.ray_cast(
            origin, radial, radius * 3.0
        )
        if location is None or normal is None or face_index is None:
            raise RuntimeError("Guide {0} missed at sample {1}".format(ring["id"], index))
        hits.append(
            {
                "position": list(location),
                "normal": list(normal.normalized()),
                "face": int(face_index),
                "cast_distance": float(distance),
            }
        )
    hits.append(dict(hits[0]))
    return hits


def add_curve(name: str, hits: list[dict[str, object]], color, bevel: float):
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(hits) - 1)
    for point, hit in zip(spline.points, hits, strict=True):
        position = hit["position"]
        point.co = (*position, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    material = bpy.data.materials.new("MAT_{0}".format(name))
    material.diffuse_color = color
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = 0.35
    curve.materials.append(material)


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    profile_path = args.profile.resolve()
    output = args.output_blend.resolve()
    report_path = args.report.resolve()
    if output.exists() or report_path.exists():
        raise RuntimeError("Joint-guide audit refuses to overwrite evidence")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    source_hash = sha256_file(source)
    if profile["source_sha256"] != source_hash:
        raise RuntimeError("Joint-guide profile is not bound to this AI-derived source")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Joint-guide audit requires exactly one mesh")
    authority = meshes[0]
    vertices, triangles = evaluated_triangles(authority)
    tree = BVHTree.FromPolygons(vertices.tolist(), triangles.tolist(), all_triangles=True)
    records = []
    samples = int(profile["samples_per_ring"])
    palette = ((1.0, 0.12, 0.05, 1.0), (0.05, 0.45, 1.0, 1.0))
    for index, ring in enumerate(profile["rings"]):
        hits = project_ring(tree, ring, samples)
        add_curve("GUIDE_{0}".format(ring["id"]), hits, palette[index % 2], 0.0025)
        records.append({"id": ring["id"], "axis": ring["axis"], "hits": hits})
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    report = {
        "schema": "reference-asset-compiler.joint-ring-guide-audit.v1",
        "status": "projected_pending_visual_review",
        "purpose": "Orientation and output-edge guides for downstream retopology of AI-derived geometry.",
        "source": {"path": str(source), "sha256": source_hash},
        "profile": {"path": str(profile_path), "sha256": sha256_file(profile_path)},
        "projection_mode": "inside_out_first_local_surface",
        "rings": records,
        "requires_human_landmark_review": True,
        "solver_launched": False,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_JOINT_GUIDE_AUDIT_OK {0}".format(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
