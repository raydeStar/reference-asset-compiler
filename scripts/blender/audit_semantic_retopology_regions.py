"""Audit closed semantic regions cut from an approved AI-derived mesh."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("report", type=Path)
    return parser.parse_args(values)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cut_closed_region(
    source: bpy.types.Object, region: dict[str, object], *, cap: bool = True
) -> tuple[bpy.types.Object, list[dict[str, object]]]:
    mesh = bpy.data.meshes.new("SEG_{0}".format(region["id"]))
    bm = bmesh.new()
    bm.from_mesh(source.data)
    cut_results: list[dict[str, object]] = []
    try:
        inherited_boundary = [edge for edge in bm.edges if edge.is_boundary]
        if inherited_boundary:
            fill = bmesh.ops.holes_fill(bm, edges=inherited_boundary, sides=0)
            cut_results.append(
                {
                    "seam": "inherited_source_boundaries",
                    "keep": "closed",
                    "cut_edges": 0,
                    "boundary_edges_filled": len(inherited_boundary),
                    "cap_faces": len(fill.get("faces", [])),
                    "cap_mode": "pre_segmentation_repair",
                }
            )
        for cut in region["cuts"]:
            keep = str(cut["keep"])
            result = bmesh.ops.bisect_plane(
                bm,
                geom=[*bm.verts, *bm.edges, *bm.faces],
                plane_co=Vector(cut["point"]),
                plane_no=Vector(cut["normal"]).normalized(),
                dist=1.0e-6,
                clear_inner=keep == "positive",
                clear_outer=keep == "negative",
                use_snap_center=False,
            )
            cut_edges = [
                item
                for item in result.get("geom_cut", [])
                if isinstance(item, bmesh.types.BMEdge) and item.is_valid
            ]
            boundary_edges = [edge for edge in cut_edges if len(edge.link_faces) == 1]
            fill = (
                bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
                if cap
                else {"faces": []}
            )
            cut_results.append(
                {
                    "seam": cut["seam"],
                    "keep": keep,
                    "cut_edges": len(cut_edges),
                    "boundary_edges_filled": len(boundary_edges) if cap else 0,
                    "cap_faces": len(fill.get("faces", [])),
                    "cap_mode": "pre_solver_closed" if cap else "post_solver_closed",
                }
            )
        seed = Vector(region["seed"])
        nearest = min(bm.verts, key=lambda vertex: (vertex.co - seed).length_squared)
        retained = {nearest}
        frontier = [nearest]
        while frontier:
            vertex = frontier.pop()
            for edge in vertex.link_edges:
                neighbor = edge.other_vert(vertex)
                if neighbor not in retained:
                    retained.add(neighbor)
                    frontier.append(neighbor)
        discarded = [vertex for vertex in bm.verts if vertex not in retained]
        if discarded:
            bmesh.ops.delete(bm, geom=discarded, context="VERTS")
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1.0e-7)
        bm.normal_update()
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.validate(verbose=True)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.matrix_world = source.matrix_world.copy()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj, cut_results


def main() -> int:
    args = parse_args()
    source_path = args.source.resolve()
    profile_path = args.profile.resolve()
    output_path = args.output_blend.resolve()
    report_path = args.report.resolve()
    if any(path.exists() for path in (output_path, report_path)):
        raise RuntimeError("Semantic region audit refuses to overwrite evidence")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    source_hash = sha256(source_path)
    if profile["source_sha256"] != source_hash:
        raise RuntimeError("Profile is not bound to this approved AI-derived source")

    bpy.ops.wm.open_mainfile(filepath=str(source_path))
    sources = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(sources) != 1:
        raise RuntimeError("Semantic region audit requires exactly one mesh object")
    source = sources[0]
    source.name = "SRC_RAC_ApprovedAI_Cleanup"
    records: list[dict[str, object]] = []
    failures: list[str] = []
    for region in profile["regions"]:
        obj, cuts = cut_closed_region(source, region)
        stats = topology(obj)
        if stats["vertices"] == 0 or stats["polygons"] == 0:
            failures.append("{0} is empty".format(region["id"]))
        if stats["boundary_edges"] or stats["nonmanifold_edges"]:
            failures.append("{0} is not closed two-manifold".format(region["id"]))
        records.append(
            {
                "id": region["id"],
                "target_faces": region["target_faces"],
                "topology": stats,
                "cuts": cuts,
            }
        )

    bpy.data.objects.remove(source, do_unlink=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    report = {
        "schema": "reference-asset-compiler.semantic-retopology-region-audit.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "purpose": "Downstream retopology segmentation of approved AI geometry; not image reconstruction.",
        "source": {"path": str(source_path), "sha256": source_hash},
        "profile": {"path": str(profile_path), "sha256": sha256(profile_path)},
        "regions": records,
        "failures": failures,
        "requires_visual_seam_review": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_SEMANTIC_REGION_AUDIT_{0} report={1}".format(
        "OK" if not failures else "REJECTED", report_path
    ))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
