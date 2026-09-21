"""Feature-weighted collapse-QEM challenger for an approved clean surface."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import (  # noqa: E402
    sha256_file,
    symmetric_deviation,
    topology,
)
from reduction_verdict import surface_verdict  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--weight-factor", type=float, default=20.0)
    parser.add_argument("--maximum-p99-m", type=float, default=0.005)
    parser.add_argument("--maximum-max-m", type=float, default=0.020)
    # One named mode rather than three loose relaxations, because the three
    # only make sense together and only for one kind of caller.
    #
    # This stage was written to judge a candidate for a production authority:
    # a closed two-manifold surface somebody will build on. A browser or
    # runtime derivative of a mesh that is already in somebody's library is a
    # different thing entirely. That mesh is ordinary game art -- open shells,
    # separate glass, cloth with a free edge -- and it was reviewed and
    # accepted in that state. Judged as an authority it can only ever be
    # rejected, and for a reason that was true before the reduction ran.
    #
    # Under this mode the source's shell is left as the source's shell: its
    # open boundaries are not filled, because filling them invents surface the
    # authority never had and then measures the derivative against an original
    # that does not contain it -- which is how a faithful reduction came back
    # 128 mm out on a 424 mm lantern. An open candidate becomes a recorded
    # finding instead of a failure, but only where the source was open too; a
    # reduction that opens a closed surface is still a failure, because that is
    # damage rather than inheritance. And the review GLB keeps its materials,
    # because here it is the deliverable rather than something to glance at.
    #
    # Nothing about the deviation thresholds is relaxed, and nothing here is
    # ever production_grade.
    parser.add_argument("--runtime-derivative", action="store_true",
                        help="Judge this as a runtime derivative of a reviewed mesh, "
                             "not as a candidate production authority")
    return parser.parse_args(values)


def feature_weights(obj: bpy.types.Object) -> tuple[list[float], dict[str, float]]:
    """Protect curvature and locally dense authored detail during QEM collapse."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    face_areas = [max(face.calc_area(), 1.0e-12) for face in bm.faces]
    median_area = statistics.median(face_areas)
    weights = []
    for vertex in bm.verts:
        linked_faces = list(vertex.link_faces)
        curvature = 0.0
        for edge in vertex.link_edges:
            if len(edge.link_faces) == 2:
                curvature = max(curvature, edge.calc_face_angle(0.0) / math.pi)
        local_area = (
            sum(face.calc_area() for face in linked_faces) / max(1, len(linked_faces)))
        density = min(1.0, median_area / max(local_area, 1.0e-12))
        # Curvature keeps silhouette creases; local density keeps deliberately
        # concentrated construction detail such as fingers, pockets, and hair.
        importance = min(1.0, 0.70 * curvature + 0.30 * density)
        weights.append(max(0.001, importance))
    bm.free()
    ordered = sorted(weights)
    summary = {
        "minimum": ordered[0],
        "median": statistics.median(ordered),
        "p90": ordered[int((len(ordered) - 1) * 0.90)],
        "p99": ordered[int((len(ordered) - 1) * 0.99)],
        "maximum": ordered[-1],
    }
    return weights, summary


def close_inherited_boundaries(obj: bpy.types.Object) -> dict[str, int]:
    """Close only boundary loops inherited from the approved cleanup mesh.

    The cat cleanup authority has 27 boundary edges from the AI export.  A
    surface-preserving reduction should not carry those holes into UE merely
    because the earlier cleanup gate tolerated them.  Filling the loops before
    QEM also lets the decimator optimize the caps as part of the same surface.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        before = [edge for edge in bm.edges if edge.is_boundary]
        if before:
            bmesh.ops.holes_fill(bm, edges=before, sides=0)
            bm.normal_update()
            bm.to_mesh(obj.data)
            obj.data.validate(verbose=True)
            obj.data.update(calc_edges=True)
        after = [edge for edge in bm.edges if edge.is_boundary]
        return {
            "boundary_edges_before": len(before),
            "boundary_edges_after": len(after),
            "filled": len(before) - len(after),
        }
    finally:
        bm.free()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output_blend = args.output_blend.resolve()
    review_glb = args.review_glb.resolve()
    report_path = args.report.resolve()
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("Feature QEM requires a topology-verified .blend source")
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Feature QEM refuses to overwrite an existing attempt")

    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Feature QEM requires exactly one mesh object")
    authority = meshes[0]
    authority.name = "SRC_RAC_ApprovedCleanup"
    authority_topology = topology(authority)
    source_triangles = int(authority_topology["triangles"])
    if not 1_000 <= args.triangle_budget < source_triangles:
        raise RuntimeError("Triangle budget must reduce the source and remain at least 1,000")

    bpy.context.view_layer.objects.active = authority
    bpy.ops.object.select_all(action="DESELECT")
    authority.select_set(True)
    bpy.ops.object.duplicate()
    candidate = bpy.context.view_layer.objects.active
    candidate.name = "GEO_RAC_FeatureQEMCandidate"
    if args.runtime_derivative:
        # Not repaired, and said so rather than reported as zero holes found.
        boundary_repair = {
            "performed": False,
            "boundary_edges_before": int(authority_topology["boundary_edges"]),
            "reason": "A runtime derivative keeps the shell its reviewed source has. "
                      "Filling inherited boundaries would add surface the source never "
                      "had and then measure the difference as error.",
        }
    else:
        boundary_repair = close_inherited_boundaries(candidate)
    healed_triangles = int(topology(candidate)["triangles"])
    weights, weight_summary = feature_weights(candidate)
    group = candidate.vertex_groups.new(name="RAC_FeatureImportance")
    for index, weight in enumerate(weights):
        group.add([index], weight, "REPLACE")

    modifier = candidate.modifiers.new("RAC_FeatureWeightedQEM", "DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = args.triangle_budget / healed_triangles
    modifier.vertex_group = group.name
    modifier.vertex_group_factor = args.weight_factor
    # Blender's contract says inversion collapses lower weights first. High
    # feature-importance weights therefore remain expensive to remove.
    modifier.invert_vertex_group = True
    modifier.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    # Flat polygon flags make a faithful reduction look catastrophically
    # faceted in fixed-view evidence. Normalize review shading here and record
    # it explicitly; this changes normals metadata, never vertex positions or
    # face order.
    for polygon in candidate.data.polygons:
        polygon.use_smooth = True
    candidate.data.update()

    candidate_topology = topology(candidate)
    deviation = symmetric_deviation(authority, candidate)
    finite = all(
        math.isfinite(value)
        for vertex in candidate.data.vertices
        for value in vertex.co
    )
    failures = []
    accepted = []
    if candidate_topology["triangles"] > args.triangle_budget:
        failures.append("triangle budget exceeded")
    surface_failures, surface_accepted = surface_verdict(
        authority_topology, candidate_topology, args.runtime_derivative)
    failures.extend(surface_failures)
    accepted.extend(surface_accepted)
    if not finite:
        failures.append("candidate contains non-finite coordinates")
    if deviation["p99_m"] > args.maximum_p99_m:
        failures.append("p99 surface deviation exceeds {0} m".format(args.maximum_p99_m))
    if deviation["max_m"] > args.maximum_max_m:
        failures.append("maximum surface deviation exceeds {0} m".format(args.maximum_max_m))

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    # Persist the native authority before asking the glTF exporter for a review
    # copy.  Blender's exporter validates its temporary mesh and can remove
    # degenerate transport triangles in-place; saving afterward silently baked
    # that transport cleanup into the production .blend and opened seam edges.
    # The native round trip is the contract, while GLB remains review-only.
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.wm.open_mainfile(filepath=str(output_blend))
    roundtrip_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(roundtrip_meshes) != 1:
        raise RuntimeError("Feature QEM native round-trip changed mesh object count")
    candidate = roundtrip_meshes[0]
    roundtrip_topology = topology(candidate)
    if roundtrip_topology != candidate_topology:
        failures.append(
            "native round-trip changed topology: before={0} after={1}".format(
                candidate_topology, roundtrip_topology))

    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(review_glb), export_format="GLB", use_selection=True,
        # An authority's review copy carries no materials on purpose: it exists
        # so somebody can look at the shape, and the .blend beside it is the
        # contract. A runtime derivative is the opposite -- this file is what
        # gets delivered, and a derivative that arrived with its paint stripped
        # would be a loss nobody asked for.
        export_materials="EXPORT" if args.runtime_derivative else "NONE")
    report = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "mode": "runtime-derivative" if args.runtime_derivative else "production-authority",
        "source": {
            "path": str(source),
            "sha256": sha256_file(source),
            "topology": authority_topology,
        },
        "backend": "Blender feature-weighted collapse QEM",
        "settings": {
            "triangle_budget": args.triangle_budget,
            "ratio": args.triangle_budget / healed_triangles,
            "weight_factor": args.weight_factor,
            "importance": "70% edge curvature plus 30% inverse local face area",
            "invert_vertex_group": True,
            "maximum_p99_m": args.maximum_p99_m,
            "maximum_max_m": args.maximum_max_m,
            "voxelization": False,
        },
        "inherited_boundary_repair": boundary_repair,
        "feature_weight_summary": weight_summary,
        "review_shading": {
            "mode": "smooth_polygons",
            "smooth_faces": sum(polygon.use_smooth for polygon in candidate.data.polygons),
            "geometry_operation": False,
        },
        "output": {
            "path": str(output_blend),
            "sha256": sha256_file(output_blend),
            "review_glb": str(review_glb),
            "review_glb_sha256": sha256_file(review_glb),
            **roundtrip_topology,
        },
        "symmetric_surface_deviation": deviation,
        "failures": failures,
        # What was allowed through, by name. A relaxation nobody can read in
        # the receipt is a relaxation nobody can argue with later.
        "accepted_findings": accepted,
        "requires_fixed_view_review": True,
        "requires_dense_to_runtime_texture_bake": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_FEATURE_QEM_REJECTED report={0}".format(report_path), flush=True)
        return 1
    print("RAC_FEATURE_QEM_CANDIDATE_OK report={0}".format(report_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
