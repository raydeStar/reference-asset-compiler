"""Read-only strict manifold audit for native Blender mesh authorities."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy

QUADRIFLOW_EDGE_TOLERANCE_M = 1.0e-4


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("report", type=Path)
    return parser.parse_args(values)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def connected_components(bm: bmesh.types.BMesh) -> int:
    unseen = set(bm.verts)
    components = 0
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in unseen:
                    unseen.remove(other)
                    stack.append(other)
    return components


def audit(obj: bpy.types.Object) -> dict[str, object]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    boundary = [edge.index for edge in bm.edges if edge.is_boundary]
    nonmanifold_edges = [edge.index for edge in bm.edges if not edge.is_manifold]
    nonmanifold_vertices = [vertex.index for vertex in bm.verts if not vertex.is_manifold]
    inconsistent_winding = [
        edge.index for edge in bm.edges if edge.is_manifold and not edge.is_contiguous
    ]
    wire_edges = [edge.index for edge in bm.edges if not edge.link_faces]
    short_edges = [
        (edge.index, float(edge.calc_length()))
        for edge in bm.edges
        if edge.calc_length() <= QUADRIFLOW_EDGE_TOLERANCE_M
    ]
    invalid_vertices = [
        vertex.index
        for vertex in bm.verts
        if any(not math.isfinite(value) for value in vertex.co)
    ]
    degenerate_faces = [face.index for face in bm.faces if face.calc_area() <= 1.0e-12]
    loose_vertices = [vertex.index for vertex in bm.verts if not vertex.link_edges]
    coordinate_buckets: dict[tuple[float, float, float], list[int]] = {}
    for vertex in bm.verts:
        key = tuple(round(float(value), 12) for value in vertex.co)
        coordinate_buckets.setdefault(key, []).append(vertex.index)
    duplicate_groups = [indices for indices in coordinate_buckets.values() if len(indices) > 1]
    signed_volume = sum(
        face.calc_center_median().dot(face.normal) * face.calc_area() / 3.0
        for face in bm.faces
    )
    determinant = float(obj.matrix_world.to_3x3().determinant())
    result = {
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "faces": len(bm.faces),
        "triangles": sum(max(0, len(face.verts) - 2) for face in bm.faces),
        "smooth_faces": sum(bool(face.smooth) for face in bm.faces),
        "connected_components": connected_components(bm),
        "boundary_edges": len(boundary),
        "nonmanifold_edges": len(nonmanifold_edges),
        "nonmanifold_vertices": len(nonmanifold_vertices),
        "inconsistent_winding_edges": len(inconsistent_winding),
        "wire_edges": len(wire_edges),
        "edges_at_or_below_quadriflow_tolerance": len(short_edges),
        "quadriflow_edge_tolerance_m": QUADRIFLOW_EDGE_TOLERANCE_M,
        "minimum_edge_length_m": min(
            (float(edge.calc_length()) for edge in bm.edges), default=0.0),
        "invalid_vertices": len(invalid_vertices),
        "degenerate_faces": len(degenerate_faces),
        "loose_vertices": len(loose_vertices),
        "duplicate_coordinate_groups": len(duplicate_groups),
        "signed_volume_local_m3": signed_volume,
        "world_transform_determinant": determinant,
        "samples": {
            "boundary_edge_indices": boundary[:20],
            "nonmanifold_edge_indices": nonmanifold_edges[:20],
            "nonmanifold_vertex_indices": nonmanifold_vertices[:20],
            "inconsistent_winding_edge_indices": inconsistent_winding[:20],
            "wire_edge_indices": wire_edges[:20],
            "short_edge_index_and_length_m": short_edges[:20],
            "duplicate_coordinate_groups": duplicate_groups[:20],
        },
    }
    result["quadriflow_preconditions_ok"] = all(
        result[key] == 0
        for key in (
            "boundary_edges",
            "nonmanifold_edges",
            "nonmanifold_vertices",
            "inconsistent_winding_edges",
            "wire_edges",
            "edges_at_or_below_quadriflow_tolerance",
            "invalid_vertices",
            "degenerate_faces",
            "loose_vertices",
            "duplicate_coordinate_groups",
        )
    ) and signed_volume > 0.0 and determinant > 0.0
    bm.free()
    return result


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    report_path = args.report.resolve()
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("Strict manifold audit requires an existing native .blend source")
    if report_path.exists():
        raise RuntimeError("Strict manifold audit refuses to overwrite an existing report")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Strict manifold audit requires exactly one mesh object")
    payload = {
        "schema": "reference-asset-compiler.strict-manifold-audit.v1",
        "source": str(source),
        "source_sha256": sha256_file(source),
        "object": meshes[0].name,
        "audit": audit(meshes[0]),
        "read_only": True,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    status = "OK" if payload["audit"]["quadriflow_preconditions_ok"] else "FAILED"
    print("RAC_STRICT_MANIFOLD_{0} report={1}".format(status, report_path), flush=True)
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
