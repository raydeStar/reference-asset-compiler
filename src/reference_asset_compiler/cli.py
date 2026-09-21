"""Command-line entry point for the Reference Asset Compiler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cohort import audit_cohort
from .cleanup import record_cleanup_receipt, validate_cleanup_input
from .contracts import ARTICULATION_MODES, ASSET_KINDS
from .geometry_request import validate_geometry_request
from .io import read_json, write_json
from .planner import plan
from .retopology import record_retopology_receipt
from .resources import checkout_root, load_registry
from .stages import STAGES, describe_stages, run_stage
from .workspace import audit_workspace, create_workspace, promote_stage

def print_payload(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rac", description="Reference-image to 3D gate ledger")
    subcommands = parser.add_subparsers(dest="command", required=True)

    new = subcommands.add_parser("new", help="Create an immutable-reference asset workspace")
    new.add_argument("asset_id")
    new.add_argument("reference", type=Path)
    new.add_argument("--kind", required=True, choices=sorted(ASSET_KINDS))
    new.add_argument("--articulation", default="auto", choices=sorted(ARTICULATION_MODES))
    new.add_argument("--workspace-root", type=Path, default=Path("work"))
    new.add_argument("--adapter", action="append", dest="adapters")
    new.add_argument("--rig-backbone")
    new.add_argument("--skeleton-profile")
    new.add_argument("--maximum-vertices", type=int, default=15_000)
    new.add_argument("--maximum-triangles", type=int, default=20_000)

    route = subcommands.add_parser("plan", help="Generate a routing decision from an intake JSON")
    route.add_argument("manifest", type=Path)
    route.add_argument("--output", type=Path)

    promote = subcommands.add_parser(
        "promote", help="Record a reviewed stage and immutable evidence"
    )
    promote.add_argument("job", type=Path)
    promote.add_argument("stage")
    promote.add_argument("--evidence", action="append", type=Path, default=[])
    promote.add_argument("--note", required=True)
    promote.add_argument("--approved-by", required=True)
    promote.add_argument(
        "--status", choices=("passed", "rejected", "blocked", "in_progress"), default="passed"
    )
    promote.add_argument(
        "--replace", action="store_true",
        help="Supersede an already passed stage; the prior ledger is snapshotted first",
    )

    audit = subcommands.add_parser(
        "audit", help="Verify source and evidence hashes plus stage order"
    )
    audit.add_argument("job", type=Path)
    audit.add_argument("--output", type=Path)

    cohort_audit = subcommands.add_parser(
        "cohort-audit", help="Require every asset in a release cohort to be production-ready"
    )
    cohort_audit.add_argument("manifest", type=Path)
    cohort_audit.add_argument("--workspace-root", type=Path, default=Path("work"))
    cohort_audit.add_argument("--output", type=Path)

    geometry_preflight = subcommands.add_parser(
        "geometry-preflight", help="Validate a one-attempt Hunyuan multiview request"
    )
    geometry_preflight.add_argument("request", type=Path)
    geometry_preflight.add_argument("--legacy-root", type=Path, required=True)
    geometry_preflight.add_argument("--repo-root", type=Path,
                                    help="Pipeline checkout; required outside a source installation")
    geometry_preflight.add_argument("--workspace-root", type=Path,
                                    help="Directory holding asset workspaces (default: <repo-root>/work)")
    geometry_preflight.add_argument("--output", type=Path)

    stage = subcommands.add_parser(
        "run-stage", help="Run one named pipeline stage and return its receipt"
    )
    stage.add_argument("stage", nargs="?", choices=sorted(STAGES),
                       help="The stage to run; omit with --list to see what is available")
    stage.add_argument("--source", type=Path, help="The staged asset the stage reads")
    stage.add_argument("--output", type=Path, help="Where the stage writes its artifact")
    stage.add_argument("--report", type=Path, help="Where the stage writes its receipt")
    stage.add_argument("--textures", type=Path,
                       help="A texture manifest to bind instead of the one beside the source")
    stage.add_argument("--legacy-root", type=Path,
                       help="Studio tree holding Hunyuan; defaults to $RAC_LEGACY_ROOT")
    stage.add_argument("--asset-name",
                       help="Names the workspace a generated asset lives in; defaults to the image")
    stage.add_argument("--seed", type=int, help="Geometry seed (default: 42)")
    stage.add_argument("--steps", type=int, help="Geometry steps, 20..60 (default: 30)")
    stage.add_argument("--octree-resolution", type=int, choices=(256, 384, 512),
                       help="Geometry octree resolution (default: 512)")
    stage.add_argument("--chunks", type=int, help="Geometry chunks, 1000..50000 (default: 20000)")
    stage.add_argument("--size", help="Real size as a landmark on a person, e.g. knee, waist, head")
    stage.add_argument("--size-adjust", type=float,
                       help="Nudge the named size, e.g. 0.85 for a little under it")
    stage.add_argument("--triangle-budget", type=int, help="Runtime triangle budget for reduction")
    stage.add_argument("--weight-factor", type=float, help="How much reduction protects detail")
    stage.add_argument("--maximum-p99-m", type=float, help="Reduction p99 surface deviation ceiling")
    stage.add_argument("--maximum-max-m", type=float, help="Reduction maximum surface deviation ceiling")
    stage.add_argument("--runtime-derivative", action="store_true",
                       help="Reduce a reviewed mesh for runtime use rather than judging it "
                            "as a candidate production authority")
    stage.add_argument("--samples", type=int, help="Bake quality in samples (default: 64)")
    stage.add_argument("--distance", type=float, help="How far occlusion looks for a shadower, in metres")
    stage.add_argument("--edge-wear", type=float, help="How hard curvature lifts edges in the albedo, 0..1")
    stage.add_argument("--relief-from-paint", type=float,
                       help="Raise the relief somebody painted into a normal map, 0..2")
    stage.add_argument("--assign", action="append",
                       help="A part and the surface it should be, as colour[:tone]=surface. "
                            "Repeatable, for example --assign blue:dark=crystal")
    stage.add_argument("--require-uvs", action="store_true",
                       help="Refuse to adopt a mesh that has no UV layer to preserve")
    stage.add_argument("--allow-triangulated-glb", action="store_true",
                       help="Accept an approved static triangle mesh for UV unwrapping as it stands")
    stage.add_argument("--reference", type=Path, help="The image a paint stage paints from")
    stage.add_argument("--views", type=int, help="Paint views, 6..12 (default: 6)")
    stage.add_argument("--resolution", type=int,
                       help="Paint resolution, 512 or 768; or fixed-view render size")
    stage.add_argument("--target-triangles", type=int, help="Remesh target before the budget check")
    stage.add_argument("--voxel-resolution", type=int, help="Remesh grid resolution (default: 420)")
    stage.add_argument("--smooth-iterations", type=int, help="Remesh smoothing passes (default: 5)")
    stage.add_argument("--smooth-lambda", type=float, help="Remesh smoothing strength (default: 0.28)")
    stage.add_argument("--colour", help="The colour a model's glass was painted, e.g. teal")
    stage.add_argument("--transmission", type=float, help="How much the glass transmits, 0..1 (default: 0.85)")
    stage.add_argument("--minimum-share", type=float,
                       help="Refuse if the colour covers less of the model than this (default: 0.005)")
    stage.add_argument("--repo-root", type=Path,
                       help="Pipeline checkout; required outside a source installation")
    stage.add_argument("--blender", help="Blender executable; defaults to $RAC_BLENDER")
    stage.add_argument("--timeout", type=int, default=3600,
                       help="Seconds before the stage is abandoned (default: 3600)")
    stage.add_argument("--list", action="store_true",
                       help="Report the runnable stages and what is missing, and run nothing")

    cleanup_preflight = subcommands.add_parser(
        "cleanup-preflight", help="Verify an approved modeling mesh before cleanup"
    )
    cleanup_preflight.add_argument("job", type=Path)
    cleanup_preflight.add_argument("input_mesh", type=Path)

    cleanup_receipt = subcommands.add_parser(
        "cleanup-receipt", help="Record a conservative semantic-cleanup derivative"
    )
    cleanup_receipt.add_argument("job", type=Path)
    cleanup_receipt.add_argument("input_mesh", type=Path)
    cleanup_receipt.add_argument("output_mesh", type=Path)
    cleanup_receipt.add_argument("topology_report", type=Path)
    cleanup_receipt.add_argument("--output", type=Path)

    retopology_receipt = subcommands.add_parser(
        "retopology-receipt", help="Record a reviewed production-retopology derivative"
    )
    retopology_receipt.add_argument("job", type=Path)
    retopology_receipt.add_argument("input_mesh", type=Path)
    retopology_receipt.add_argument("output_mesh", type=Path)
    retopology_receipt.add_argument("report", type=Path)
    retopology_receipt.add_argument("--view", action="append", type=Path, required=True)
    retopology_receipt.add_argument("--topology-view", action="append", type=Path)
    retopology_receipt.add_argument("--approved-by", required=True)
    retopology_receipt.add_argument("--note", required=True)
    retopology_receipt.add_argument("--output", type=Path)
    retopology_receipt.add_argument("--authorization", type=Path,
                                    help="Hash-bound user delegation for an automation reviewer")
    retopology_receipt.add_argument(
        "--deformation-topology-reviewed", action="store_true",
        help="Attest that joint edge flow was inspected; required for articulated kinds")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"new", "plan"}:
            registry = load_registry()
        if args.command == "new":
            job = create_workspace(
                args.workspace_root,
                args.reference,
                args.asset_id,
                args.kind,
                args.articulation,
                registry,
                args.adapters,
                args.rig_backbone,
                args.skeleton_profile,
                args.maximum_vertices,
                args.maximum_triangles,
            )
            print(f"RAC_WORKSPACE_OK {job}")
            return 0
        if args.command == "plan":
            payload = plan(read_json(args.manifest), registry)
            if args.output:
                write_json(args.output, payload)
                print(f"RAC_PLAN_OK {args.output.resolve()}")
            else:
                print_payload(payload)
            return 0
        if args.command == "promote":
            state = promote_stage(
                args.job, args.stage, args.evidence, args.note, args.approved_by, args.status,
                replace=args.replace,
            )
            print(f"RAC_STAGE_RECORDED {args.stage}={state['stages'][args.stage]['status']}")
            return 0
        if args.command == "audit":
            payload = audit_workspace(args.job)
            if args.output:
                write_json(args.output, payload)
            print_payload(payload)
            return 0 if payload["ok"] else 1
        if args.command == "cohort-audit":
            payload = audit_cohort(args.manifest, args.workspace_root)
            if args.output:
                write_json(args.output, payload)
            print_payload(payload)
            return 0 if payload["ok"] and payload["production_ready"] else 1
        if args.command == "geometry-preflight":
            repo_root = args.repo_root or checkout_root()
            if repo_root is None or not (repo_root / "workflows" / "geometry").is_dir():
                raise ValueError("Geometry preflight needs pipeline scripts: pass --repo-root "
                                 "pointing to a Reference Asset Compiler checkout")
            payload = validate_geometry_request(
                args.request, args.legacy_root, repo_root, args.workspace_root)
            if args.output:
                write_json(args.output, payload)
            print_payload(payload)
            return 0
        if args.command == "run-stage":
            if args.list or not args.stage:
                # Capability preflight: what could run here, and what is
                # missing if it could not. Nothing is executed.
                payload = describe_stages(args.repo_root, args.blender, args.legacy_root)
                print_payload(payload)
                return 0
            for required, name in ((args.source, "--source"), (args.output, "--output"),
                                   (args.report, "--report")):
                if required is None:
                    raise ValueError("Running a stage needs {0}".format(name))
            payload = run_stage(
                args.stage, args.source, args.output, args.report,
                args.repo_root, args.blender, args.timeout, args.textures,
                args.legacy_root, {
                    "asset_name": args.asset_name,
                    "seed": args.seed,
                    "steps": args.steps,
                    "octree_resolution": args.octree_resolution,
                    "chunks": args.chunks,
                    "size": args.size,
                    "size_adjust": args.size_adjust,
                    "triangle_budget": args.triangle_budget,
                    "weight_factor": args.weight_factor,
                    "maximum_p99_m": args.maximum_p99_m,
                    "maximum_max_m": args.maximum_max_m,
                    "allow_triangulated_glb": args.allow_triangulated_glb or None,
                    "require_uvs": args.require_uvs or None,
                    "assign": args.assign or None,
                    "samples": args.samples,
                    "distance": args.distance,
                    "edge_wear": args.edge_wear,
                    "relief_from_paint": args.relief_from_paint,
                    "runtime_derivative": args.runtime_derivative or None,
                    "reference": args.reference,
                    "views": args.views,
                    "resolution": args.resolution,
                    "target_triangles": args.target_triangles,
                    "voxel_resolution": args.voxel_resolution,
                    "smooth_iterations": args.smooth_iterations,
                    "smooth_lambda": args.smooth_lambda,
                    "colour": args.colour,
                    "transmission": args.transmission,
                    "minimum_share": args.minimum_share,
                })
            print_payload(payload)
            return 0 if payload["ok"] else 1
        if args.command == "cleanup-preflight":
            print_payload(validate_cleanup_input(args.job, args.input_mesh))
            return 0
        if args.command == "cleanup-receipt":
            print_payload(record_cleanup_receipt(
                args.job,
                args.input_mesh,
                args.output_mesh,
                args.topology_report,
                args.output,
            ))
            return 0
        if args.command == "retopology-receipt":
            print_payload(record_retopology_receipt(
                args.job, args.input_mesh, args.output_mesh, args.report,
                args.view, args.approved_by, args.note, args.topology_view, args.output,
                args.authorization, args.deformation_topology_reviewed,
            ))
            return 0
    except (OSError, KeyError, ValueError, TypeError) as error:
        print(f"RAC_ERROR {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
