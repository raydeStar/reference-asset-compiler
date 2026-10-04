"""Feature-weighted collapse-QEM challenger for an approved clean surface."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import (  # noqa: E402
    sha256_file,
    symmetric_deviation,
    topology,
)
from reduction_verdict import surface_verdict  # noqa: E402

# The budget rule is written once, in the package, and read here by path:
# Blender's interpreter cannot import the package itself.
_BUDGETS_PATH = (Path(__file__).resolve().parents[2]
                 / "src" / "reference_asset_compiler" / "budgets.py")


def _load_budgets():
    spec = importlib.util.spec_from_file_location("rac_budgets", _BUDGETS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def budget_argument(value: str) -> int | str:
    """A whole number of triangles, or 'auto' to let the asset decide."""
    if str(value).strip().lower() == "auto":
        return "auto"
    return int(value)


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    # 'auto' (the default) decides from what the asset is and its real size --
    # profiles/triangle-budgets.json -- and climbs that table's ladder when the
    # surface gates refuse a rung. A number is a single, explicit attempt.
    parser.add_argument("--triangle-budget", type=budget_argument, default="auto")
    parser.add_argument("--asset-name", help="Names the asset for the budget; defaults to the file")
    parser.add_argument("--role", help="prop, modular, vegetation, hero or character")
    parser.add_argument("--asset-notes", default="", help="Text that may promote the role")
    parser.add_argument("--weight-factor", type=float, default=20.0)
    # Unset: scaled to the object under 'auto', 5 mm / 20 mm for a number.
    parser.add_argument("--maximum-p99-m", type=float)
    parser.add_argument("--maximum-max-m", type=float)
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


def weld_seams(obj: bpy.types.Object) -> dict[str, int]:
    """Put back together what the transport format split apart.

    glTF stores a UV per vertex, so an exporter has to split a vertex at every
    seam; a mesh arrives from the importer already torn along each one. Blender
    stores UVs per face corner instead, so welding those vertices back by
    position is lossless -- the seams remain, because the corners still carry
    their own coordinates.

    Doing it changes two things and both matter for a reduction. The gate stops
    counting seams as holes: the Ayric sword read 3,888 boundary and 3,888
    non-manifold edges as imported and exactly zero of each welded, and the
    lantern read 12,358 against 6. Both are closed surfaces. And the decimator
    stops treating every seam as a wall it may not collapse across, which is
    the difference between reducing a surface and reducing a few thousand
    disconnected patches.
    """
    before = len(obj.data.vertices)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bm.normal_update()
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update(calc_edges=True)
    return {"vertices_before": before, "vertices_after": len(obj.data.vertices),
            "seam_splits_rejoined": before - len(obj.data.vertices)}


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


def object_dimensions(obj: bpy.types.Object) -> tuple[float, float, float]:
    """Real extent in metres, measured on the world-space mesh."""
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return tuple(max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3))


def choose_budget(args: argparse.Namespace, authority: bpy.types.Object, source: Path):
    """The rungs to try and the gates to hold them to.

    'auto' asks the budget table, from the asset's name and real size; a number
    is one explicit attempt under the gates it names (or the old fixed ones).
    """
    if args.triangle_budget != "auto":
        return (None, [int(args.triangle_budget)],
                args.maximum_p99_m if args.maximum_p99_m is not None else 0.005,
                args.maximum_max_m if args.maximum_max_m is not None else 0.020)
    budgets = _load_budgets()
    decision = budgets.decide(
        args.asset_name or source.stem, object_dimensions(authority), args.role,
        args.asset_notes, int(topology(authority)["triangles"]))
    rungs = list(decision["ladder"]) or [decision["triangle_budget"]]
    maximum_p99 = args.maximum_p99_m if args.maximum_p99_m is not None else decision["maximum_p99_m"]
    maximum_max = args.maximum_max_m if args.maximum_max_m is not None else decision["maximum_max_m"]
    return decision, rungs, maximum_p99, maximum_max


def reduce_once(template, authority, authority_topology, budget, healed_triangles, group_name,
                args, maximum_p99, maximum_max):
    """Collapse a copy of the weighted template to one budget and judge it."""
    bpy.ops.object.select_all(action="DESELECT")
    template.hide_set(False)
    template.select_set(True)
    bpy.context.view_layer.objects.active = template
    bpy.ops.object.duplicate()
    template.hide_set(True)
    candidate = bpy.context.view_layer.objects.active
    candidate.name = "GEO_RAC_FeatureQEMCandidate"
    modifier = candidate.modifiers.new("RAC_FeatureWeightedQEM", "DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = budget / healed_triangles
    modifier.vertex_group = group_name
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
    if candidate_topology["triangles"] > budget:
        failures.append("triangle budget exceeded")
    surface_failures, surface_accepted = surface_verdict(
        authority_topology, candidate_topology, args.runtime_derivative)
    failures.extend(surface_failures)
    accepted.extend(surface_accepted)
    if not finite:
        failures.append("candidate contains non-finite coordinates")
    if deviation["p99_m"] > maximum_p99:
        failures.append("p99 surface deviation exceeds {0} m".format(maximum_p99))
    if deviation["max_m"] > maximum_max:
        failures.append("maximum surface deviation exceeds {0} m".format(maximum_max))
    return candidate, candidate_topology, deviation, failures, accepted


def keep_source(args, authority, source, authority_topology, decision,
                output_blend, review_glb, report_path, seam_repair) -> int:
    """The source is already within reach of its budget: deliver it unreduced."""
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.object.select_all(action="DESELECT")
    authority.select_set(True)
    bpy.context.view_layer.objects.active = authority
    bpy.ops.export_scene.gltf(
        filepath=str(review_glb), export_format="GLB", use_selection=True,
        export_materials="EXPORT" if args.runtime_derivative else "NONE")
    report = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass",
        "mode": "runtime-derivative" if args.runtime_derivative else "production-authority",
        "budget_decision": {**decision, "attempts": []},
        "reduction": "kept the source: it is already within reach of its budget",
        "source": {"path": str(source), "sha256": sha256_file(source),
                   "topology": authority_topology},
        "seam_repair": seam_repair,
        "output": {"path": str(output_blend), "sha256": sha256_file(output_blend),
                   "review_glb": str(review_glb), "review_glb_sha256": sha256_file(review_glb),
                   **authority_topology},
        "failures": [],
        "accepted_findings": [],
        "requires_fixed_view_review": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_FEATURE_QEM_CANDIDATE_OK report={0}".format(report_path), flush=True)
    return 0


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
    # Before anything measures or collapses it. A surface split along every UV
    # seam is not the surface; it is the transport format's copy of it.
    seam_repair = weld_seams(authority)
    authority_topology = topology(authority)
    source_triangles = int(authority_topology["triangles"])
    decision, rungs, maximum_p99, maximum_max = choose_budget(args, authority, source)
    if decision is not None and decision.get("triangle_budget") is None:
        raise RuntimeError(decision["summary"])
    if decision is not None and decision.get("keep_source"):
        return keep_source(args, authority, source, authority_topology, decision,
                           output_blend, review_glb, report_path, seam_repair)
    for rung in rungs:
        if not 1_000 <= rung < source_triangles:
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
    template = candidate
    template.hide_set(True)

    # One rung at a time: the first budget the surface gates accept is the
    # answer, and every refused rung stays in the receipt as the reason the
    # next one was tried.
    attempts = []
    for rung in rungs:
        candidate, candidate_topology, deviation, failures, accepted = reduce_once(
            template, authority, authority_topology, rung, healed_triangles, group.name,
            args, maximum_p99, maximum_max)
        attempts.append({
            "triangle_budget": rung,
            "triangles": candidate_topology["triangles"],
            "p99_m": deviation["p99_m"],
            "max_m": deviation["max_m"],
            "failures": list(failures),
        })
        if not failures or rung == rungs[-1]:
            break
        bpy.data.objects.remove(candidate, do_unlink=True)
    bpy.data.objects.remove(template, do_unlink=True)
    triangle_budget = attempts[-1]["triangle_budget"]

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
        "budget_decision": None if decision is None else {**decision, "attempts": attempts},
        "source": {
            "path": str(source),
            "sha256": sha256_file(source),
            "topology": authority_topology,
        },
        "backend": "Blender feature-weighted collapse QEM",
        "settings": {
            "triangle_budget": triangle_budget,
            "triangle_budget_requested": args.triangle_budget,
            "ratio": triangle_budget / healed_triangles,
            "weight_factor": args.weight_factor,
            "importance": "70% edge curvature plus 30% inverse local face area",
            "invert_vertex_group": True,
            "maximum_p99_m": maximum_p99,
            "maximum_max_m": maximum_max,
            "voxelization": False,
        },
        "seam_repair": seam_repair,
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
