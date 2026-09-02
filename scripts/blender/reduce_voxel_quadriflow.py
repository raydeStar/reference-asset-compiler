"""Create a voxel-conditioned QuadriFlow reduction candidate.

The dense source is immutable. Voxelization supplies the closed, coherent
surface that raw generated triangle soup lacks; QuadriFlow then operates on
that derived surface. This stage emits mechanical evidence only. Fixed-view
review and texture transfer from the dense authority remain mandatory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def triangles(obj: bpy.types.Object) -> int:
    return sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def topology(obj: bpy.types.Object) -> dict[str, int | float | bool]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    boundary_edges = sum(edge.is_boundary for edge in bm.edges)
    nonmanifold_edges = sum(not edge.is_manifold for edge in bm.edges)
    bm.free()
    polygon_count = len(obj.data.polygons)
    quads = sum(len(polygon.vertices) == 4 for polygon in obj.data.polygons)
    return {
        "vertices": len(obj.data.vertices),
        "polygons": polygon_count,
        "triangles": triangles(obj),
        "quads": quads,
        "quad_fraction": quads / max(1, polygon_count),
        "boundary_edges": boundary_edges,
        "nonmanifold_edges": nonmanifold_edges,
        "finite_coordinates": all(
            math.isfinite(component)
            for vertex in obj.data.vertices
            for component in vertex.co
        ),
    }


def remove_tiny_components(obj: bpy.types.Object, minimum_faces: int) -> dict[str, int]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    remaining = set(bm.faces)
    doomed = []
    removed_components = 0
    while remaining:
        seed = remaining.pop()
        component = [seed]
        stack = [seed]
        while stack:
            face = stack.pop()
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.append(neighbor)
                        stack.append(neighbor)
        if len(component) < minimum_faces:
            doomed.extend(component)
            removed_components += 1
    removed_faces = len(doomed)
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
        loose = [vertex for vertex in bm.verts if not vertex.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return {"components": removed_components, "faces": removed_faces}


def manifoldize_dominant_volume(obj: bpy.types.Object) -> dict[str, int]:
    """Keep the coherent volume, close boundaries, and normalize winding."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    remaining = set(bm.faces)
    components = []
    while remaining:
        seed = remaining.pop()
        component = [seed]
        stack = [seed]
        while stack:
            face = stack.pop()
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.append(neighbor)
                        stack.append(neighbor)
        components.append(component)
    largest = max(components, key=len)
    discard = [
        face
        for component in components
        if component is not largest
        for face in component
    ]
    if discard:
        bmesh.ops.delete(bm, geom=discard, context="FACES")
    loose = [vertex for vertex in bm.verts if not vertex.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    degenerate = [face for face in bm.faces if face.calc_area() < 1.0e-12]
    if degenerate:
        bmesh.ops.delete(bm, geom=degenerate, context="FACES")
    boundary = [edge for edge in bm.edges if edge.is_boundary]
    if boundary:
        bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    remaining_boundary = sum(edge.is_boundary for edge in bm.edges)
    nonmanifold = sum(not edge.is_manifold for edge in bm.edges)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return {
        "input_components": len(components),
        "discarded_faces": len(discard),
        "filled_boundary_edges": len(boundary),
        "remaining_boundary_edges": remaining_boundary,
        "nonmanifold_edges": nonmanifold,
    }


def parse_args() -> argparse.Namespace:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--target-quads", type=int, default=9_000)
    parser.add_argument("--voxel-resolution", type=int, default=420)
    parser.add_argument("--smooth-iterations", type=int, default=5)
    parser.add_argument("--smooth-lambda", type=float, default=0.28)
    parser.add_argument("--minimum-component-faces", type=int, default=24)
    parser.add_argument("--condition-only", action="store_true")
    return parser.parse_args(arguments)


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    blend_path = output.with_suffix(".blend")
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists() or blend_path.exists() or report_path.exists():
        raise RuntimeError("Refusing to overwrite an existing reduction candidate")
    if not 1_000 <= args.target_quads <= args.triangle_budget // 2:
        raise RuntimeError("Target quads must be between 1,000 and half the triangle budget")
    if not 128 <= args.voxel_resolution <= 1024:
        raise RuntimeError("Voxel resolution must be between 128 and 1,024")
    if not 1 <= args.smooth_iterations <= 30:
        raise RuntimeError("Smooth iterations must be between 1 and 30")
    if not 0.01 <= args.smooth_lambda <= 0.75:
        raise RuntimeError("Smooth lambda must be between 0.01 and 0.75")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if source.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source))
    elif source.suffix.lower() in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif source.suffix.lower() == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    else:
        raise RuntimeError("Unsupported voxel/QuadriFlow source format: {0}".format(source.suffix))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Source contains no meshes")
    inventory = [
        {"name": obj.name, **topology(obj)}
        for obj in sorted(meshes, key=lambda item: item.name)
    ]
    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    candidate = max(meshes, key=lambda item: len(item.data.polygons))
    bpy.context.view_layer.objects.active = candidate
    if len(meshes) > 1:
        bpy.ops.object.join()
    candidate.name = "GEO_RAC_VoxelQuadriFlowCandidate"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    source_topology = topology(candidate)
    cleanup = remove_tiny_components(candidate, args.minimum_component_faces)

    voxel_size = max(candidate.dimensions) / args.voxel_resolution
    candidate.data.remesh_voxel_size = voxel_size
    candidate.data.remesh_voxel_adaptivity = 0.0
    candidate.data.use_remesh_fix_poles = True
    candidate.data.use_remesh_preserve_volume = True
    result = bpy.ops.object.voxel_remesh()
    if "FINISHED" not in result:
        raise RuntimeError("Voxel remesh failed: {0}".format(sorted(result)))
    voxel_topology = topology(candidate)
    surface_normalization = manifoldize_dominant_volume(candidate)
    candidate.data.validate(verbose=True, clean_customdata=True)
    bpy.context.view_layer.objects.active = candidate
    candidate.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    candidate.data.update()
    normalized_topology = topology(candidate)
    precondition_warnings = []
    if normalized_topology["boundary_edges"] or normalized_topology["nonmanifold_edges"]:
        precondition_warnings.append(
            "voxel-conditioned surface retains {0} boundary and {1} non-manifold "
            "edges; final QuadriFlow output must close them".format(
                normalized_topology["boundary_edges"],
                normalized_topology["nonmanifold_edges"],
            )
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_base = {
        "schema": "reference-asset-compiler.reduction-candidate.v1",
        "status": "conditioned_pending_quadriflow",
        "source": {
            "path": str(source),
            "sha256": sha256(source),
            "parts": inventory,
            "joined_topology": source_topology,
        },
        "backend": "Blender voxel remesh then QuadriFlow",
        "settings": {
            "triangle_budget": args.triangle_budget,
            "target_quads": args.target_quads,
            "voxel_resolution": args.voxel_resolution,
            "voxel_size": voxel_size,
            "smooth_iterations": args.smooth_iterations,
            "smooth_lambda": args.smooth_lambda,
            "minimum_component_faces": args.minimum_component_faces,
            "decimation_fallback": False,
        },
        "cleanup": cleanup,
        "voxel_topology": voxel_topology,
        "surface_normalization": surface_normalization,
        "normalized_topology": normalized_topology,
        "precondition_warnings": precondition_warnings,
        "requires_fixed_view_review": True,
        "requires_texture_bake_from_dense_authority": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report_base, indent=2) + "\n", encoding="utf-8")

    if args.condition_only:
        for polygon in candidate.data.polygons:
            polygon.use_smooth = True
        candidate.data.materials.clear()
        bpy.ops.object.select_all(action="DESELECT")
        candidate.select_set(True)
        bpy.context.view_layer.objects.active = candidate
        bpy.ops.export_scene.gltf(
            filepath=str(output),
            export_format="GLB",
            use_selection=True,
            export_materials="NONE",
        )
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        report = {
            **report_base,
            "status": "conditioned_intermediate",
            "output": {
                "path": str(output),
                "sha256": sha256(output),
                **normalized_topology,
            },
            "failures": [],
            "production_grade": False,
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("RAC_VOXEL_CONDITIONED_OK report={0}".format(report_path))
        return 0

    smooth = candidate.modifiers.new("DenseSurfaceCleanup", "LAPLACIANSMOOTH")
    smooth.lambda_factor = args.smooth_lambda
    smooth.lambda_border = 0.08
    smooth.iterations = args.smooth_iterations
    smooth.use_volume_preserve = True
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    result = bpy.ops.object.quadriflow_remesh(
        use_mesh_symmetry=False,
        use_preserve_sharp=True,
        use_preserve_boundary=False,
        preserve_attributes=False,
        smooth_normals=True,
        mode="FACES",
        target_faces=args.target_quads,
        seed=0,
    )
    if "FINISHED" not in result:
        raise RuntimeError(
            "QuadriFlow refused the voxel-conditioned surface: {0}. "
            "No decimation fallback was attempted.".format(sorted(result))
        )

    candidate_topology = topology(candidate)
    failures = []
    if candidate_topology["triangles"] > args.triangle_budget:
        failures.append(
            "{0} triangles exceeds budget {1}".format(
                candidate_topology["triangles"], args.triangle_budget
            )
        )
    if candidate_topology["quad_fraction"] < 0.95:
        failures.append(
            "quad fraction {0:.3f} is below 0.95".format(
                candidate_topology["quad_fraction"]
            )
        )
    if candidate_topology["boundary_edges"] or candidate_topology["nonmanifold_edges"]:
        failures.append("candidate is not a closed two-manifold surface")
    if not candidate_topology["finite_coordinates"]:
        failures.append("candidate contains non-finite coordinates")

    for polygon in candidate.data.polygons:
        polygon.use_smooth = True
    candidate.data.materials.clear()
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        use_selection=True,
        export_materials="NONE",
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    report = {
        **report_base,
        "status": "mechanical_pass" if not failures else "rejected",
        "output": {
            "path": str(output),
            "sha256": sha256(output),
            **candidate_topology,
        },
        "failures": failures,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_VOXEL_QUADRIFLOW_REJECTED report={0}".format(report_path))
        return 1
    print("RAC_VOXEL_QUADRIFLOW_CANDIDATE_OK report={0}".format(report_path))
    print("The mesh has passed arithmetic; its silhouette must now face the tribunal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
