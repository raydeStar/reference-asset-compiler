"""Retopologize audited source-derived regions with independent density budgets."""

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


def object_topology(obj: bpy.types.Object) -> dict[str, int | float | bool]:
    triangles = sum(max(0, len(face.vertices) - 2) for face in obj.data.polygons)
    quads = sum(len(face.vertices) == 4 for face in obj.data.polygons)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    boundary = sum(edge.is_boundary for edge in bm.edges)
    nonmanifold = sum(not edge.is_manifold for edge in bm.edges)
    bm.free()
    return {
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "triangles": triangles,
        "quads": quads,
        "quad_fraction": quads / max(1, len(obj.data.polygons)),
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "finite_coordinates": all(
            math.isfinite(component)
            for vertex in obj.data.vertices
            for component in vertex.co
        ),
    }


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("segmented", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("output_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--maximum-vertices", type=int, default=15000)
    parser.add_argument("--maximum-triangles", type=int, default=20000)
    parser.add_argument("--adaptivity", type=float, default=0.75)
    return parser.parse_args(values)


def main() -> int:
    args = parse_args()
    paths = [
        args.source.resolve(),
        args.segmented.resolve(),
        args.profile.resolve(),
        args.audit.resolve(),
    ]
    source, segmented, profile_path, audit_path = paths
    output_blend = args.output_blend.resolve()
    output_glb = args.output_glb.resolve()
    report_path = args.report.resolve()
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    if any(path.exists() for path in (output_blend, output_glb, report_path)):
        raise RuntimeError("Regional AutoRemesher refuses to overwrite evidence")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if profile.get("source_sha256") != sha256(source):
        raise RuntimeError("Regional profile is not bound to semantic cleanup output")
    if audit.get("status") != "mechanical_pass":
        raise RuntimeError("Regional segmentation audit has not passed")
    if audit.get("source", {}).get("sha256") != sha256(source):
        raise RuntimeError("Regional audit is not bound to semantic cleanup output")
    if audit.get("profile", {}).get("sha256") != sha256(profile_path):
        raise RuntimeError("Regional audit is not bound to this profile")
    if not hasattr(bpy.context.scene, "autoremesher"):
        raise RuntimeError("AutoRemesher extension is not enabled")

    bpy.ops.wm.open_mainfile(filepath=str(segmented))
    objects_by_name = {
        obj.name: obj for obj in bpy.context.scene.objects if obj.type == "MESH"
    }
    settings = bpy.context.scene.autoremesher
    settings.edge_scaling = 1.0
    settings.adaptivity = args.adaptivity
    settings.sharp_edge = math.radians(70.0)
    settings.smooth_normal = math.radians(55.0)
    settings.island_detail = 20
    settings.preserve_thin = True
    settings.weld_shells = False

    region_records = []
    outputs = []
    for region in profile["regions"]:
        region_id = str(region["id"])
        source_obj = objects_by_name.get("SEG_{0}".format(region_id))
        if source_obj is None:
            raise RuntimeError("Missing audited region: {0}".format(region_id))
        input_stats = object_topology(source_obj)
        mode = str(region.get("mode", "remesh"))
        if mode == "preserve_source":
            candidate = source_obj
            candidate.name = "GEO_RAC_{0}_Preserved".format(region_id)
        elif mode == "remesh":
            before = set(bpy.context.scene.objects)
            bpy.ops.object.select_all(action="DESELECT")
            source_obj.select_set(True)
            bpy.context.view_layer.objects.active = source_obj
            settings.target_quad_count = int(region["target_faces"])
            result = bpy.ops.object.autoremesher_remesh()
            if "FINISHED" not in result:
                raise RuntimeError(
                    "AutoRemesher failed for {0}: {1}".format(region_id, sorted(result))
                )
            created = [
                obj
                for obj in bpy.context.scene.objects
                if obj.type == "MESH" and obj not in before
            ]
            if len(created) != 1:
                raise RuntimeError(
                    "Expected one candidate for {0}, found {1}".format(
                        region_id, len(created)
                    )
                )
            candidate = created[0]
            candidate.name = "GEO_RAC_{0}_Retopo".format(region_id)
            bpy.data.objects.remove(source_obj, do_unlink=True)
        else:
            raise RuntimeError("Unknown regional retopology mode: {0}".format(mode))
        for polygon in candidate.data.polygons:
            polygon.use_smooth = True
        candidate.data.materials.clear()
        stats = object_topology(candidate)
        outputs.append(candidate)
        region_records.append(
            {
                "id": region_id,
                "mode": mode,
                "target_faces": int(region["target_faces"]),
                "input": input_stats,
                "output": stats,
            }
        )

    totals = {
        key: sum(int(record["output"][key]) for record in region_records)
        for key in ("vertices", "polygons", "triangles", "quads", "boundary_edges", "nonmanifold_edges")
    }
    totals["quad_fraction"] = totals["quads"] / max(1, totals["polygons"])
    failures = []
    if totals["vertices"] > args.maximum_vertices:
        failures.append("{0} vertices exceeds budget {1}".format(
            totals["vertices"], args.maximum_vertices))
    if totals["triangles"] > args.maximum_triangles:
        failures.append("{0} triangles exceeds budget {1}".format(
            totals["triangles"], args.maximum_triangles))
    if totals["quad_fraction"] < 0.80:
        failures.append("quad fraction {0:.3f} is below 0.80".format(
            totals["quad_fraction"]))
    if totals["boundary_edges"] or totals["nonmanifold_edges"]:
        failures.append("regional output is not closed two-manifold")
    if any(not record["output"]["finite_coordinates"] for record in region_records):
        failures.append("regional output contains non-finite coordinates")

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in outputs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = outputs[0]
    bpy.ops.export_scene.gltf(
        filepath=str(output_glb),
        export_format="GLB",
        use_selection=True,
        export_materials="NONE",
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "source": {"path": str(source), "sha256": sha256(source)},
        "derivation": {
            "segmented": {"path": str(segmented), "sha256": sha256(segmented)},
            "profile": {"path": str(profile_path), "sha256": sha256(profile_path)},
            "audit": {"path": str(audit_path), "sha256": sha256(audit_path)},
            "backend": "source-derived regional segmentation plus AutoRemesher",
            "adaptivity": args.adaptivity,
        },
        "regions": region_records,
        "output": {
            "path": str(output_glb),
            "sha256": sha256(output_glb),
            **totals,
        },
        "failures": failures,
        "requires_fixed_view_review": True,
        "requires_wireframe_review": True,
        "requires_dense_to_runtime_texture_bake": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_REGIONAL_AUTOREMESHER_{0} report={1}".format(
        "OK" if not failures else "REJECTED", report_path
    ))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
