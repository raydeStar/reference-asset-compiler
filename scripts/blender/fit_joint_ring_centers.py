"""Fit draft joint-ring centers to enclosed cross-sections of an AI mesh.

The draft supplies semantic joint locations and axes. This helper moves each
center only within its ring plane, on a bounded grid, until every radial sample
hits the source surface. It does not invent geometry or interpret an image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def basis(axis: Vector) -> tuple[Vector, Vector]:
    axis = axis.normalized()
    first = Vector((0.0, 1.0, 0.0))
    if abs(axis.dot(first)) > 0.95:
        first = Vector((1.0, 0.0, 0.0))
    first = (first - axis * axis.dot(first)).normalized()
    return first, axis.cross(first).normalized()


def evaluated_tree(obj: bpy.types.Object) -> BVHTree:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    mesh.calc_loop_triangles()
    vertices = [vertex.co.copy() for vertex in mesh.vertices]
    triangles = [tuple(loop.vertices) for loop in mesh.loop_triangles]
    evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(vertices, triangles, all_triangles=True)


def score_center(
    tree: BVHTree,
    center: Vector,
    directions: list[Vector],
    maximum_distance: float,
    offset: float,
    minimum_clearance: float,
) -> tuple[float, list[float]] | None:
    distances = []
    for direction in directions:
        location, _normal, _face, distance = tree.ray_cast(
            center + direction * 1.0e-5, direction, maximum_distance
        )
        if location is None or distance is None:
            return None
        distances.append(float(distance))
    if min(distances) < minimum_clearance:
        return None
    # Prefer a compact, centered section and then the smallest move from the
    # semantic draft. A remote pouch or torso enclosure should not win.
    score = max(distances) + statistics.pstdev(distances) + offset * 0.15
    return score, distances


def main() -> int:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("draft_profile", type=Path)
    parser.add_argument("output_profile", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--search-radius-m", type=float, default=0.12)
    parser.add_argument("--step-m", type=float, default=0.01)
    parser.add_argument("--minimum-clearance-m", type=float, default=0.005)
    args = parser.parse_args(values)

    source = args.source.resolve()
    draft_path = args.draft_profile.resolve()
    output = args.output_profile.resolve()
    report_path = args.report.resolve()
    if output.exists() or report_path.exists():
        raise RuntimeError("Joint-ring fitting refuses to overwrite evidence")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if draft["source_sha256"] != sha256(source):
        raise RuntimeError("Draft profile is not bound to the source mesh")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Joint-ring fitting requires exactly one mesh")
    tree = evaluated_tree(meshes[0])

    steps = int(round(args.search_radius_m / args.step_m))
    fitted = json.loads(json.dumps(draft))
    records = []
    for ring in fitted["rings"]:
        original = Vector(ring["center"])
        axis = Vector(ring["axis"]).normalized()
        first, second = basis(axis)
        samples = int(fitted["samples_per_ring"])
        directions = [
            first * math.cos(2.0 * math.pi * index / samples)
            + second * math.sin(2.0 * math.pi * index / samples)
            for index in range(samples)
        ]
        best = None
        for first_step in range(-steps, steps + 1):
            for second_step in range(-steps, steps + 1):
                delta = first * (first_step * args.step_m) + second * (
                    second_step * args.step_m
                )
                if delta.length > args.search_radius_m + 1.0e-9:
                    continue
                candidate = original + delta
                result = score_center(
                    tree, candidate, directions, float(ring["cast_radius"]) * 3.0,
                    delta.length, args.minimum_clearance_m,
                )
                if result is None:
                    continue
                score, distances = result
                choice = (score, delta.length, candidate, distances)
                if best is None or choice[:2] < best[:2]:
                    best = choice
        if best is None:
            raise RuntimeError("No enclosed local center found for {0}".format(ring["id"]))
        _score, moved, center, distances = best
        ring["center"] = [float(value) for value in center]
        records.append(
            {
                "id": ring["id"],
                "draft_center": list(original),
                "fitted_center": list(center),
                "movement_m": float(moved),
                "minimum_hit_m": min(distances),
                "maximum_hit_m": max(distances),
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(fitted, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(
        json.dumps(
            {
                "schema": "reference-asset-compiler.joint-ring-center-fit.v1",
                "status": "fitted_pending_projected_visual_review",
                "source": {"path": str(source), "sha256": sha256(source)},
                "draft": {"path": str(draft_path), "sha256": sha256(draft_path)},
                "settings": {
                    "search_radius_m": args.search_radius_m,
                    "step_m": args.step_m,
                    "minimum_clearance_m": args.minimum_clearance_m,
                },
                "rings": records,
                "production_grade": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("RAC_JOINT_RING_CENTERS_FIT {0}".format(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
