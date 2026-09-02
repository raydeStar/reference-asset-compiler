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
from .workspace import audit_workspace, create_workspace, promote_stage

ROOT = Path(__file__).resolve().parents[2]


def registry_path() -> Path:
    return ROOT / "configs" / "model-adapters.json"


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
    geometry_preflight.add_argument("--repo-root", type=Path, default=ROOT)
    geometry_preflight.add_argument("--output", type=Path)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = read_json(registry_path())
    try:
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
                args.job, args.stage, args.evidence, args.note, args.approved_by, args.status
            )
            print(f"RAC_STAGE_RECORDED {args.stage}={state['stages'][args.stage]['status']}")
            return 0
        if args.command == "audit":
            payload = audit_workspace(args.job)
            if args.output:
                write_json(args.output, payload)
            print_payload(payload)
            return 0 if payload["ok"] else 2
        if args.command == "cohort-audit":
            payload = audit_cohort(args.manifest, args.workspace_root)
            if args.output:
                write_json(args.output, payload)
            print_payload(payload)
            return 0 if payload["production_ready"] else 1
        if args.command == "geometry-preflight":
            payload = validate_geometry_request(
                args.request, args.legacy_root, args.repo_root)
            if args.output:
                write_json(args.output, payload)
            print_payload(payload)
            return 0
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
            ))
            return 0
    except (FileExistsError, FileNotFoundError, KeyError, ValueError) as error:
        print(f"RAC_ERROR {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
