"""Create a voxel-conditioned collapse-QEM reduction candidate.

Unlike direct decimation of generated triangle soup, this route first derives a
coherent closed surface. It is the explicit form of the triangle fallback that
produced the visually accepted legacy 48k chair. Mechanical success is not
promotion: fixed-view comparison and dense-to-runtime texture baking remain
mandatory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reduce_voxel_quadriflow import (
    manifoldize_dominant_volume,
    remove_tiny_components,
    sha256,
    topology,
)


def parse_args() -> argparse.Namespace:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--target-triangles", type=int, default=18_000)
    parser.add_argument("--voxel-resolution", type=int, default=420)
    parser.add_argument("--smooth-iterations", type=int, default=5)
    parser.add_argument("--smooth-lambda", type=float, default=0.28)
    parser.add_argument("--minimum-component-faces", type=int, default=24)
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
    if not 1_000 <= args.target_triangles <= args.triangle_budget:
        raise RuntimeError("Target triangles must be between 1,000 and the budget")
    if not 128 <= args.voxel_resolution <= 1024:
        raise RuntimeError("Voxel resolution must be between 128 and 1,024")
    if not 1 <= args.smooth_iterations <= 30:
        raise RuntimeError("Smooth iterations must be between 1 and 30")
    if not 0.01 <= args.smooth_lambda <= 0.75:
        raise RuntimeError("Smooth lambda must be between 0.01 and 0.75")

    source_suffix = source.suffix.lower()
    if source_suffix == ".blend":
        # Semantic cleanup deliberately emits a native Blender authority so
        # shared vertices and face topology survive serialization.  Opening
        # that file is therefore the canonical production path, not a
        # convenience fallback through a lossy transport format.
        bpy.ops.wm.open_mainfile(filepath=str(source))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    if source_suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif source_suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif source_suffix != ".blend":
        raise RuntimeError("Source must be BLEND, FBX, GLB, or GLTF")
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
    candidate.name = "GEO_RAC_VoxelQEMCandidate"
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

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_base = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "conditioned_pending_qem",
        "source": {
            "path": str(source),
            "sha256": sha256(source),
            "parts": inventory,
            "joined_topology": source_topology,
        },
        "backend": "Blender voxel remesh then collapse QEM",
        "lineage": "explicit form of accepted legacy chair triangle fallback",
        "settings": {
            "triangle_budget": args.triangle_budget,
            "target_triangles": args.target_triangles,
            "voxel_resolution": args.voxel_resolution,
            "voxel_size": voxel_size,
            "smooth_iterations": args.smooth_iterations,
            "smooth_lambda": args.smooth_lambda,
            "minimum_component_faces": args.minimum_component_faces,
        },
        "cleanup": cleanup,
        "voxel_topology": voxel_topology,
        "surface_normalization": surface_normalization,
        "normalized_topology": normalized_topology,
        "requires_fixed_view_review": True,
        "requires_texture_bake_from_dense_authority": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report_base, indent=2) + "\n", encoding="utf-8")

    smooth = candidate.modifiers.new("DenseSurfaceCleanup", "LAPLACIANSMOOTH")
    smooth.lambda_factor = args.smooth_lambda
    smooth.lambda_border = 0.08
    smooth.iterations = args.smooth_iterations
    smooth.use_volume_preserve = True
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    before_qem = topology(candidate)
    modifier = candidate.modifiers.new("GameTriangleBudget", "DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = min(1.0, args.target_triangles / before_qem["triangles"])
    modifier.use_collapse_triangulate = True
    modifier.use_symmetry = False
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    candidate_topology = topology(candidate)

    failures = []
    if candidate_topology["triangles"] > args.triangle_budget:
        failures.append(
            "{0} triangles exceeds budget {1}".format(
                candidate_topology["triangles"], args.triangle_budget
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
    if output.suffix.lower() == ".fbx":
        bpy.ops.export_scene.fbx(
            filepath=str(output),
            use_selection=True,
            add_leaf_bones=False,
            bake_anim=False,
            object_types={"MESH"},
            mesh_smooth_type="FACE",
            path_mode="COPY",
            embed_textures=False,
        )
    elif output.suffix.lower() == ".glb":
        bpy.ops.export_scene.gltf(
            filepath=str(output),
            export_format="GLB",
            use_selection=True,
            export_materials="NONE",
        )
    else:
        raise RuntimeError("Output must be FBX or GLB")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    report = {
        **report_base,
        "status": "mechanical_pass" if not failures else "rejected",
        "before_qem": before_qem,
        "output": {
            "path": str(output),
            "sha256": sha256(output),
            **candidate_topology,
        },
        "failures": failures,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_VOXEL_QEM_REJECTED report={0}".format(report_path))
        return 1
    print("RAC_VOXEL_QEM_CANDIDATE_OK report={0}".format(report_path))
    print("The budget is met; now let the silhouette cross-examine the arithmetic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
