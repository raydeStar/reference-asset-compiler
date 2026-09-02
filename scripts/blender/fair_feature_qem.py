"""Feature-aware Taubin fairing for a valid paired-QEM production candidate."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import sha256_file, symmetric_deviation, topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("authority", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument("--lambda-factor", type=float, default=0.25)
    parser.add_argument("--mu-factor", type=float, default=-0.255)
    parser.add_argument("--feature-low", type=float, default=0.27)
    parser.add_argument("--feature-high", type=float, default=0.40)
    parser.add_argument("--maximum-displacement-m", type=float, default=0.004)
    parser.add_argument("--minimum-component-vertices", type=int, default=100)
    return parser.parse_args(values)


def load_single_mesh(path: Path, name: str) -> bpy.types.Object:
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.objects = source.objects
    loaded = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if len(loaded) != 1:
        raise RuntimeError(f"{path} must contain exactly one mesh")
    obj = loaded[0]
    if obj.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    return obj


def adjacency(obj: bpy.types.Object) -> list[list[int]]:
    result: list[list[int]] = [[] for _ in obj.data.vertices]
    for edge in obj.data.edges:
        first, second = edge.vertices
        result[first].append(second)
        result[second].append(first)
    return result


def component_sizes(neighbors: list[list[int]]) -> list[int]:
    sizes = [0] * len(neighbors)
    unseen = set(range(len(neighbors)))
    while unseen:
        root = unseen.pop()
        component = [root]
        cursor = 0
        while cursor < len(component):
            current = component[cursor]
            cursor += 1
            for neighbor in neighbors[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.append(neighbor)
        for index in component:
            sizes[index] = len(component)
    return sizes


def group_weights(obj: bpy.types.Object, name: str) -> list[float]:
    group = obj.vertex_groups.get(name)
    if group is None:
        raise RuntimeError(f"Required feature group is missing: {name}")
    weights = []
    for vertex in obj.data.vertices:
        try:
            weights.append(float(group.weight(vertex.index)))
        except RuntimeError:
            # Vertices added to close thin detail sheets are protected.
            weights.append(1.0)
    return weights


def fairing_influences(
    weights: list[float], sizes: list[int], low: float, high: float,
    minimum_component_vertices: int,
) -> list[float]:
    if not 0.0 <= low < high <= 1.0:
        raise RuntimeError("Feature thresholds must satisfy 0 <= low < high <= 1")
    result = []
    for weight, size in zip(weights, sizes):
        if size < minimum_component_vertices:
            result.append(0.0)
            continue
        normalized = max(0.0, min(1.0, (high - weight) / (high - low)))
        # Quadratic falloff keeps medium/high curvature much more stable than
        # broad low-importance acreage.
        result.append(normalized * normalized)
    return result


def laplacian_magnitudes(
    coordinates: list[Vector], neighbors: list[list[int]], influences: list[float]
) -> list[float]:
    values = []
    for index, linked in enumerate(neighbors):
        if influences[index] <= 0.0 or not linked:
            continue
        average = sum((coordinates[item] for item in linked), Vector()) / len(linked)
        values.append((average - coordinates[index]).length)
    return values


def smoothing_step(
    coordinates: list[Vector], neighbors: list[list[int]], influences: list[float],
    factor: float,
) -> list[Vector]:
    output = [coordinate.copy() for coordinate in coordinates]
    for index, linked in enumerate(neighbors):
        influence = influences[index]
        if influence <= 0.0 or not linked:
            continue
        average = sum((coordinates[item] for item in linked), Vector()) / len(linked)
        output[index] = coordinates[index] + (average - coordinates[index]) * factor * influence
    return output


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[round((len(ordered) - 1) * fraction)]


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    authority_path = args.authority.resolve()
    output_blend = args.output_blend.resolve()
    review_glb = args.review_glb.resolve()
    report_path = args.report.resolve()
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Feature-fairing attempt refuses to overwrite evidence")
    if args.iterations < 1 or args.iterations > 30:
        raise RuntimeError("Fairing iterations must be between 1 and 30")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    source_obj = load_single_mesh(source, "SRC_RAC_PairedQEM")
    authority = load_single_mesh(authority_path, "SRC_RAC_ApprovedAI_Cleanup")
    source_topology = topology(source_obj)
    candidate = source_obj.copy()
    candidate.data = source_obj.data.copy()
    candidate.name = "GEO_RAC_FeatureFairedQEM"
    bpy.context.scene.collection.objects.link(candidate)

    neighbors = adjacency(candidate)
    sizes = component_sizes(neighbors)
    feature_weights = group_weights(candidate, "RAC_FeatureImportance")
    influences = fairing_influences(
        feature_weights, sizes, args.feature_low, args.feature_high,
        args.minimum_component_vertices,
    )
    original = [vertex.co.copy() for vertex in candidate.data.vertices]
    coordinates = [coordinate.copy() for coordinate in original]
    roughness_before = laplacian_magnitudes(coordinates, neighbors, influences)
    for _ in range(args.iterations):
        coordinates = smoothing_step(
            coordinates, neighbors, influences, args.lambda_factor)
        coordinates = smoothing_step(
            coordinates, neighbors, influences, args.mu_factor)

    for vertex, before, after in zip(candidate.data.vertices, original, coordinates):
        displacement = after - before
        if displacement.length > args.maximum_displacement_m:
            displacement.normalize()
            displacement *= args.maximum_displacement_m
        vertex.co = before + displacement
    candidate.data.update(calc_edges=True)

    final_coordinates = [vertex.co.copy() for vertex in candidate.data.vertices]
    roughness_after = laplacian_magnitudes(final_coordinates, neighbors, influences)
    candidate_topology = topology(candidate)
    deviation = symmetric_deviation(authority, candidate)
    final_displacements = [
        (after - before).length for before, after in zip(original, final_coordinates)
    ]
    before_mean = statistics.fmean(roughness_before) if roughness_before else 0.0
    after_mean = statistics.fmean(roughness_after) if roughness_after else 0.0
    reduction = 0.0 if before_mean == 0.0 else 1.0 - after_mean / before_mean

    failures = []
    if candidate_topology != source_topology:
        failures.append("fairing changed topology")
    if deviation["p99_m"] > 0.005 or deviation["max_m"] > 0.020:
        failures.append("candidate exceeds surface-deviation contract")
    # Blender stores coordinates as float32; allow sub-micron rounding above
    # the requested cap while still rejecting any material overshoot.
    if max(final_displacements, default=0.0) > args.maximum_displacement_m + 1.0e-7:
        failures.append("candidate exceeds displacement cap")
    if reduction < 0.15:
        failures.append("low-importance roughness reduction is below 15%")

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.data.objects.remove(source_obj, do_unlink=True)
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.wm.open_mainfile(filepath=str(output_blend))
    roundtrip = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(roundtrip) != 1 or topology(roundtrip[0]) != candidate_topology:
        failures.append("native round-trip changed topology")
    candidate = roundtrip[0]
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(review_glb), export_format="GLB", use_selection=True,
        export_materials="NONE")

    report = {
        "schema": "reference-asset-compiler.feature-fairing-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "source": {
            "path": str(source), "sha256": sha256_file(source),
            "topology": source_topology,
        },
        "authority": {
            "path": str(authority_path), "sha256": sha256_file(authority_path),
        },
        "settings": {
            "iterations": args.iterations,
            "lambda_factor": args.lambda_factor,
            "mu_factor": args.mu_factor,
            "feature_low": args.feature_low,
            "feature_high": args.feature_high,
            "maximum_displacement_m": args.maximum_displacement_m,
            "minimum_component_vertices": args.minimum_component_vertices,
        },
        "protection": {
            "vertices_fully_protected": sum(value == 0.0 for value in influences),
            "vertices_faired": sum(value > 0.0 for value in influences),
            "small_components_fully_protected": len({
                size for size in sizes if size < args.minimum_component_vertices
            }),
        },
        "roughness": {
            "mean_before_m": before_mean,
            "mean_after_m": after_mean,
            "mean_reduction_fraction": reduction,
            "p95_before_m": percentile(roughness_before, 0.95),
            "p95_after_m": percentile(roughness_after, 0.95),
        },
        "displacement": {
            "maximum_m": max(final_displacements, default=0.0),
            "p95_m": percentile(final_displacements, 0.95),
            "cap_mode": "per_vertex",
        },
        "output": {
            "path": str(output_blend), "sha256": sha256_file(output_blend),
            "review_glb": str(review_glb),
            "review_glb_sha256": sha256_file(review_glb),
            **candidate_topology,
        },
        "symmetric_surface_deviation": deviation,
        "failures": failures,
        "requires_fixed_view_review": True,
        "requires_deformation_flow_review": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_FEATURE_FAIRING_{0} report={1}".format(
        "CANDIDATE_OK" if not failures else "REJECTED", report_path))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
