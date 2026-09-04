"""Run the reference-image pipeline without an AI coding agent.

The command is deliberately resumable. It advances deterministic stages until
it reaches a visual gate, prints the evidence to inspect, and exits cleanly.
Run the same command again with the matching ``--approve-*-by`` option after a
person has reviewed those images.

Static props can advance from one image through a packaged UE5 payload. The
articulated route currently stops after modeling approval because generic,
deformation-aware retopology and rig export are not production-complete.

Example:
  python scripts/crank_from_image.py brass-lantern D:/art/lantern.png \
      --kind static_prop --height 0.55 \
      --height-reason "Measured against the 0.9 m table in the concept sheet."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import rac_env  # noqa: E402
from reference_asset_compiler.approvals import (  # noqa: E402
    MODELING_VIEW_NAMES,
    record_modeling_derivative,
    texture_evidence_paths,
)
from reference_asset_compiler.io import read_json, sha256_file  # noqa: E402
from reference_asset_compiler.retopology import record_retopology_receipt  # noqa: E402
from reference_asset_compiler.workspace import (  # noqa: E402
    audit_workspace,
    create_workspace,
    promote_stage,
)

OPERATOR_SCHEMA = "reference-asset-compiler.operator-run.v1"
SUPPORTED_COMPLETE_KINDS = {"static_prop"}
ARTICULATED_KINDS = {"humanoid", "mascot"}


def child_env(studio_root: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + existing if existing else "")
    if studio_root is not None:
        env["RAC_LEGACY_ROOT"] = str(studio_root)
    return env


def run(command: list[Any], label: str, studio_root: Path | None = None) -> None:
    print("\n[OPERATOR] {0}".format(label), flush=True)
    completed = subprocess.run(
        [str(value) for value in command], cwd=ROOT, env=child_env(studio_root)
    )
    if completed.returncode:
        raise RuntimeError("{0} failed with exit code {1}".format(label, completed.returncode))


def powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        raise RuntimeError("PowerShell 5.1 or 7 is required on the current Windows route")
    return executable


def require_source_match(job: Path, image: Path) -> dict[str, Any]:
    intake = read_json(job / "intake.json")
    if intake.get("source", {}).get("sha256") != sha256_file(image):
        raise ValueError("existing workspace belongs to a different reference image")
    report = audit_workspace(job)
    if not report["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(report["failures"])))
    return intake


def ensure_workspace(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    job = ROOT / "work" / args.asset_id
    image = args.image.resolve()
    if job.exists() and any(job.iterdir()):
        return job, require_source_match(job, image)
    registry = read_json(ROOT / "configs" / "model-adapters.json")
    articulation = "static" if args.kind == "static_prop" else "required"
    backbone = "auto_rig_pro" if args.kind == "humanoid" else None
    created = create_workspace(
        ROOT / "work",
        image,
        args.asset_id,
        args.kind,
        articulation,
        registry,
        ["hunyuan3d_2_1"],
        backbone,
        args.skeleton_profile,
        args.maximum_vertices,
        args.maximum_triangles,
    )
    print("[OPERATOR] workspace {0}".format(created))
    return created, read_json(created / "intake.json")


def generation_request(
    args: argparse.Namespace, job: Path, intake: dict[str, Any]
) -> tuple[Path, Path, Path]:
    attempt_name = "hy3d-single-seed{0}-attempt{1:03d}".format(args.seed, args.attempt)
    output = job / "candidates" / attempt_name
    request = job / "requests" / (attempt_name + ".json")
    payload = {
        "schema": "reference-asset-compiler.hy3d-geometry-request.v1",
        "mode": "single_view",
        "asset_id": args.asset_id,
        "workspace": "${{RAC_REPO_ROOT}}/work/{0}".format(args.asset_id),
        "source_authority": {
            "path": "${{RAC_REPO_ROOT}}/work/{0}/{1}".format(
                args.asset_id, intake["source"]["path"]
            ),
            "sha256": intake["source"]["sha256"],
        },
        "inputs": [
            {
                "view": "primary",
                "path": "${{RAC_REPO_ROOT}}/work/{0}/{1}".format(
                    args.asset_id, intake["source"]["path"]
                ),
                "sha256": intake["source"]["sha256"],
            }
        ],
        "parameters": {
            "seed": args.seed,
            "steps": args.steps,
            "octree_resolution": args.octree_resolution,
            "chunks": args.chunks,
        },
        "output_directory": "${{RAC_REPO_ROOT}}/work/{0}/candidates/{1}".format(
            args.asset_id, attempt_name
        ),
    }
    encoded = json.dumps(payload, indent=2) + "\n"
    request.parent.mkdir(parents=True, exist_ok=True)
    if request.exists() and request.read_text(encoding="utf-8") != encoded:
        raise ValueError("attempt request already exists with different settings: {0}".format(request))
    request.write_text(encoded, encoding="utf-8")
    return request, output / "candidate.glb", output / "candidate-receipt.json"


def ensure_geometry(
    args: argparse.Namespace, job: Path, request: Path, candidate: Path, receipt: Path
) -> None:
    state = read_json(job / "state.json")
    if candidate.is_file() and receipt.is_file():
        if read_json(receipt).get("candidate_sha256") != sha256_file(candidate):
            raise ValueError("retained geometry candidate no longer matches its receipt")
    elif candidate.exists() or receipt.exists() or candidate.parent.exists():
        raise ValueError(
            "geometry attempt is partial; preserve it and choose --attempt {0}".format(args.attempt + 1)
        )
    else:
        run(
            [
                powershell(),
                "-NoProfile",
                "-File",
                ROOT / "scripts" / "run_hy3d_geometry.ps1",
                "-Request",
                request,
                "-LegacyRoot",
                args.studio_root,
            ],
            "direct Hunyuan3D single-view geometry",
            args.studio_root,
        )
    if state["stages"]["generate_candidates"]["status"] == "pending":
        promote_stage(
            job,
            "generate_candidates",
            [candidate, receipt],
            "Hash-bound single-image Hunyuan3D candidate retained.",
            "crank_from_image.py",
        )


def blender(script: str, *values: Any) -> list[Any]:
    return [
        rac_env.find_blender(),
        "-b",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        ROOT / "scripts" / "blender" / script,
        "--",
        *values,
    ]


def write_static_recipe(
    args: argparse.Namespace,
    job: Path,
    intake: dict[str, Any],
    candidate: Path,
    receipt: Path,
    description: dict[str, Any],
) -> Path:
    recipe = job / "operator" / "static-prop-recipe.json"
    materials = description.get("materials") or []
    renames = {
        name: "M_{0}_{1}".format(
            "".join(part.capitalize() for part in args.asset_id.split("-")),
            "Body" if index == 0 else "Part{0}".format(index),
        )
        for index, name in enumerate(materials)
    }
    payload = {
        "asset_id": args.asset_id,
        "kind": "static_prop",
        "articulation": "static",
        "skeleton_profile": None,
        "source": {
            "authority_fbx": str(candidate),
            "reference_authority": str((job / intake["source"]["path"]).resolve()),
            "candidate_lineage_report": str(receipt),
            "candidate_lineage_sha256": sha256_file(receipt),
            "geometry_adapter": "hunyuan3d_2_1",
            "candidate_sha256": sha256_file(candidate),
            "reference_sha256": intake["source"]["sha256"],
            "note": "Direct single-image Hunyuan geometry; texture is authored after retopology.",
        },
        "material_textures": {},
        "normalize": {
            "mesh_name": "SM_" + "".join(
                part.capitalize() for part in args.asset_id.split("-")
            ),
            "target_height_m": args.height,
            "target_height_reason": args.height_reason,
            "recenter": True,
            "yaw_degrees": 0.0,
            "material_renames": renames,
        },
    }
    encoded = json.dumps(payload, indent=2) + "\n"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    if recipe.exists() and recipe.read_text(encoding="utf-8") != encoded:
        raise ValueError("operator recipe changed; use a new asset id rather than overwriting it")
    recipe.write_text(encoded, encoding="utf-8")
    return recipe


def ensure_modeling_review(
    args: argparse.Namespace,
    job: Path,
    intake: dict[str, Any],
    candidate: Path,
    receipt: Path,
) -> tuple[Path, Path]:
    if args.kind == "static_prop":
        describe = job / "operator" / "candidate-description.json"
        texture_dir = job / "operator" / "candidate-textures"
        if not describe.is_file():
            run(blender("describe_mesh.py", candidate, texture_dir, describe), "measure geometry")
        description = read_json(describe)
        if description.get("has_armature"):
            raise ValueError("generated candidate unexpectedly contains an armature")
        recipe = write_static_recipe(args, job, intake, candidate, receipt, description)
        normalized = ROOT / "out" / args.asset_id / (args.asset_id + ".fbx")
        manifest = normalized.with_suffix(".ue5import.json")
        if not normalized.is_file() or not manifest.is_file():
            run([sys.executable, ROOT / "scripts" / "compile_prop.py", recipe], "normalize prop")
        artifact = job / "normalize-prop-report.json"
        modeling = normalized
        operations = ["normalize_scale_origin"]
        artifacts = [artifact]
    else:
        modeling = candidate
        operations = ["direct_ai_candidate"]
        artifacts = []

    views = job / "modeling" / "fixed-views"
    if not all((views / name).is_file() for name in MODELING_VIEW_NAMES):
        if views.exists() and any(views.iterdir()):
            raise ValueError("modeling review directory is partial; preserve it and use a new asset id")
        run(blender("render_turnaround.py", modeling, views, 1024), "render modeling review")
    lineage, lineage_artifacts = record_modeling_derivative(
        job, candidate, modeling, operations, artifacts
    )
    if args.approve_modeling_by:
        state = read_json(job / "state.json")
        if state["stages"]["modeling_approval"]["status"] == "pending":
            promote_stage(
                job,
                "modeling_approval",
                [modeling, lineage, *lineage_artifacts,
                 *(views / name for name in MODELING_VIEW_NAMES)],
                args.modeling_note,
                args.approve_modeling_by,
            )
    return modeling, views


def write_passthrough_retopology(
    cleaned: Path, topology: dict[str, Any], description: dict[str, Any], output: Path
) -> None:
    after = topology.get("roundtrip") or topology.get("after") or {}
    failures = []
    if after.get("boundary_edges") != 0:
        failures.append("boundary edges remain")
    if after.get("non_manifold_edges") != 0:
        failures.append("non-manifold edges remain")
    payload = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "failed",
        "backend": "under-budget semantic-cleanup passthrough",
        "source": {"path": str(cleaned), "sha256": sha256_file(cleaned)},
        "output": {
            "path": str(cleaned),
            "sha256": sha256_file(cleaned),
            "vertices": int(description["vertices"]),
            "triangles": int(description["tris"]),
            "quad_fraction": 0.0,
            "boundary_edges": int(after.get("boundary_edges", -1)),
            "nonmanifold_edges": int(after.get("non_manifold_edges", -1)),
        },
        "failures": failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_retopology(
    args: argparse.Namespace, job: Path, modeling: Path
) -> tuple[Path, Path, Path]:
    cleanup_dir = job / "cleanup" / "operator-attempt001"
    cleaned = cleanup_dir / "cleaned.blend"
    cleanup_report = cleanup_dir / "topology.json"
    if not cleaned.is_file() or not cleanup_report.is_file():
        if cleanup_dir.exists() and any(cleanup_dir.iterdir()):
            raise ValueError("cleanup attempt is partial; preserve it and use a new asset id")
        run(
            [
                powershell(), "-NoProfile", "-File",
                ROOT / "scripts" / "run_semantic_cleanup.ps1",
                "-Job", job, "-InputMesh", modeling,
                "-OutputDirectory", cleanup_dir,
            ],
            "semantic cleanup",
        )

    description_path = cleanup_dir / "description.json"
    if not description_path.is_file():
        run(
            blender("describe_mesh.py", cleaned, cleanup_dir / "textures", description_path),
            "measure cleaned geometry",
        )
    description = read_json(description_path)
    retopo_dir = job / "retopology" / "operator-attempt001"
    if description["tris"] > args.maximum_triangles:
        retopo = retopo_dir / "voxel-qem-candidate.glb"
        report = retopo_dir / "reduction-report.json"
        if not retopo.is_file() or not report.is_file():
            if retopo_dir.exists() and any(retopo_dir.iterdir()):
                raise ValueError("retopology attempt is partial; preserve it and choose a new asset id")
            run(
                [
                    powershell(), "-NoProfile", "-File",
                    ROOT / "scripts" / "run_voxel_qem_reduction.ps1",
                    "-InputMesh", cleaned, "-OutputDirectory", retopo_dir,
                    "-TriangleBudget", args.maximum_triangles,
                    "-TargetTriangles", args.target_triangles,
                ],
                "voxel/QEM runtime reduction",
            )
    else:
        retopo = cleaned
        report = retopo_dir / "passthrough-report.json"
        if not report.is_file():
            write_passthrough_retopology(cleaned, read_json(cleanup_report), description, report)

    review = retopo_dir / "fixed-views"
    if not all((review / name).is_file() for name in MODELING_VIEW_NAMES):
        if review.exists() and any(review.iterdir()):
            raise ValueError("retopology review is partial; preserve it and use a new asset id")
        run(blender("render_turnaround.py", retopo, review, 1024), "render topology review")

    if args.approve_retopology_by:
        state = read_json(job / "state.json")
        if state["stages"]["production_retopology"]["status"] == "pending":
            receipt = record_retopology_receipt(
                job,
                cleaned,
                retopo,
                report,
                [review / name for name in MODELING_VIEW_NAMES],
                args.approve_retopology_by,
                args.retopology_note,
            )
            receipt_path = Path(receipt["receipt"])
            promote_stage(
                job,
                "production_retopology",
                [cleaned, retopo, report, receipt_path,
                 *(review / name for name in MODELING_VIEW_NAMES)],
                args.retopology_note,
                args.approve_retopology_by,
            )
    return retopo, report, review


def ensure_texture(
    args: argparse.Namespace, job: Path, intake: dict[str, Any], retopo: Path
) -> Path:
    uv_dir = job / "texture" / "operator-uv-attempt001"
    uv_blend = uv_dir / "uv-authority.blend"
    uv_obj = uv_dir / "texture-transport.obj"
    uv_report = uv_dir / "uv-transport-report.json"
    if not all(path.is_file() for path in (uv_blend, uv_obj, uv_report)):
        if uv_dir.exists() and any(uv_dir.iterdir()):
            raise ValueError("UV attempt is partial; preserve it and use a new asset id")
        run(
            [
                powershell(), "-NoProfile", "-File",
                ROOT / "scripts" / "run_texture_uv_prep.ps1",
                "-InputMesh", retopo, "-OutputDirectory", uv_dir,
            ],
            "geometry-locked UV preparation",
        )

    paint_dir = job / "texture" / "operator-hy3d21-attempt001"
    paint_obj = paint_dir / "painted.obj"
    validation = paint_dir / "painted.validation.json"
    if not validation.is_file():
        if paint_dir.exists() and any(paint_dir.iterdir()):
            raise ValueError("paint attempt is partial; preserve it and use a new asset id")
        paint_dir.mkdir(parents=True, exist_ok=True)
        run(
            [
                powershell(), "-NoProfile", "-File",
                ROOT / "scripts" / "run_hy3d21_texture.ps1",
                "-Mesh", uv_obj,
                "-Reference", (job / intake["source"]["path"]).resolve(),
                "-OutputObj", paint_obj,
                "-LegacyRoot", args.studio_root,
                "-Views", args.texture_views,
                "-Resolution", args.texture_resolution,
                "-DiagnosticsDir", paint_dir / "diagnostics",
            ],
            "direct Hunyuan3D-Paint PBR texturing",
            args.studio_root,
        )

    prod = job / "prod-v2"
    if not (prod / "retopo.json").is_file():
        run(
            [
                sys.executable,
                ROOT / "scripts" / "package_character_texture.py",
                args.asset_id,
                "--uv-authority", uv_blend,
                "--base-color", paint_obj.with_suffix(".jpg"),
                "--metallic", paint_obj.with_name(paint_obj.stem + "_metallic.jpg"),
                "--roughness", paint_obj.with_name(paint_obj.stem + "_roughness.jpg"),
                "--profile", ROOT / "profiles" / "skeletons" / "static_prop.json",
                "--output-name", "prod-v2",
                "--target-height", args.height,
                "--height-reason", args.height_reason,
            ],
            "package PBR texture payload",
        )

    retopo_payload = read_json(prod / "retopo.json")
    if not retopo_payload.get("ok"):
        raise ValueError(
            "retained texture package did not pass its mechanical gate; "
            "inspect {0} and do not approve it".format(prod / "gate-tex.json")
        )
    state = read_json(job / "state.json")
    if state["stages"]["unwrap_and_bake"]["status"] == "pending":
        evidence = [uv_blend, uv_obj, uv_report, validation, prod / "retopo.json",
                    prod / "gate-tex.json"]
        evidence.extend(prod / value for value in retopo_payload["baked"].values())
        promote_stage(
            job,
            "unwrap_and_bake",
            evidence,
            "UV transport and topology-locked Hunyuan PBR maps passed mechanical gates.",
            "crank_from_image.py",
        )
    if args.approve_texture_by:
        state = read_json(job / "state.json")
        if state["stages"]["texture_approval"]["status"] == "pending":
            promote_stage(
                job,
                "texture_approval",
                texture_evidence_paths(prod, retopo_payload),
                args.texture_note,
                args.approve_texture_by,
            )
    return prod


def import_ue5(args: argparse.Namespace) -> None:
    project = (args.ue5_project or (ROOT / "work" / "ue5-validate" / "RacValidate.uproject"))
    if not project.is_file():
        raise FileNotFoundError(
            "UE5 validation project is missing; run scripts/setup_ue5_project.ps1 first"
        )
    unreal = Path(rac_env.find_unreal_cmd())
    env = child_env(args.studio_root)
    env["RAC_ROOT"] = str(ROOT)
    completed = subprocess.run(
        [
            str(unreal), str(project),
            "-ExecutePythonScript=" + str(ROOT / "scripts" / "ue5" / "import_and_verify.py"),
            "-unattended", "-nop4", "-nosplash", "-stdout",
        ],
        cwd=ROOT,
        env=env,
    )
    if completed.returncode:
        raise RuntimeError("UE5 import and verification failed")
    run([sys.executable, ROOT / "scripts" / "record_ue5_import.py", args.asset_id],
        "record manifest-bound UE5 import")


def write_operator_receipt(
    args: argparse.Namespace, job: Path, request: Path, status: str, next_gate: str | None
) -> None:
    path = job / "operator" / "operator-run.json"
    payload = {
        "schema": OPERATOR_SCHEMA,
        "asset_id": args.asset_id,
        "source_image": str(args.image.resolve()),
        "source_sha256": sha256_file(args.image.resolve()),
        "geometry_request": str(request),
        "geometry_request_sha256": sha256_file(request),
        "status": status,
        "next_gate": next_gate,
        "codex_required": False,
        "comfyui_required": False,
        "complete_route_supported": args.kind in SUPPORTED_COMPLETE_KINDS,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def print_gate(gate: str, directory: Path, option: str) -> None:
    print("\n[OPERATOR] PAUSE -- {0}".format(gate))
    print("[OPERATOR] Review the four views in {0}".format(directory))
    print("[OPERATOR] Then rerun the same command with {0} \"Your Name\".".format(option))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_id")
    parser.add_argument("image", type=Path)
    parser.add_argument("--kind", choices=("static_prop", "humanoid", "mascot"),
                        default="static_prop")
    parser.add_argument("--height", type=float)
    parser.add_argument("--height-reason")
    parser.add_argument("--skeleton-profile")
    parser.add_argument("--studio-root", type=Path,
                        default=Path(os.environ["RAC_LEGACY_ROOT"])
                        if os.environ.get("RAC_LEGACY_ROOT") else None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--octree-resolution", type=int, choices=(256, 384, 512), default=512)
    parser.add_argument("--chunks", type=int, default=20000)
    parser.add_argument("--maximum-vertices", type=int, default=15000)
    parser.add_argument("--maximum-triangles", type=int, default=20000)
    parser.add_argument("--target-triangles", type=int, default=18000)
    parser.add_argument("--texture-views", type=int, choices=range(6, 13), default=6)
    parser.add_argument("--texture-resolution", type=int, choices=(512, 768), default=512)
    parser.add_argument("--approve-modeling-by")
    parser.add_argument("--modeling-note", default="Approved against the source in four views.")
    parser.add_argument("--approve-retopology-by")
    parser.add_argument("--retopology-note", default="Runtime topology approved in four views.")
    parser.add_argument("--approve-texture-by")
    parser.add_argument("--texture-note", default="PBR texture approved in four calibrated views.")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--import-ue5", action="store_true")
    parser.add_argument("--ue5-project", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.asset_id):
        print("[OPERATOR] FAILED: asset_id must be lower-case-hyphenated")
        return 2
    if not args.image.resolve().is_file():
        print("[OPERATOR] FAILED: image does not exist: {0}".format(args.image.resolve()))
        return 2
    if args.attempt < 1:
        print("[OPERATOR] FAILED: --attempt must be at least 1")
        return 2
    if args.kind == "static_prop" and (not args.height or not args.height_reason):
        print("[OPERATOR] FAILED: static props require --height and --height-reason")
        return 2
    if args.height is not None and args.height <= 0:
        print("[OPERATOR] FAILED: --height must be greater than zero")
        return 2
    if (args.maximum_vertices <= 0 or args.maximum_triangles <= 0
            or args.target_triangles <= 0
            or args.target_triangles > args.maximum_triangles):
        print("[OPERATOR] FAILED: topology budgets must be positive and target triangles "
              "cannot exceed the maximum")
        return 2
    if args.kind == "mascot" and not args.skeleton_profile:
        print("[OPERATOR] FAILED: mascots require --skeleton-profile")
        return 2
    try:
        job, intake = ensure_workspace(args)
        request, candidate, candidate_receipt = generation_request(args, job, intake)
        if args.prepare_only:
            write_operator_receipt(args, job, request, "prepared", "geometry")
            print("[OPERATOR] PREPARED {0}".format(request))
            print("[OPERATOR] No GPU work was launched. The spellbook remains closed.")
            return 0
        if args.studio_root is None:
            raise ValueError("set RAC_LEGACY_ROOT or pass --studio-root")
        ensure_geometry(args, job, request, candidate, candidate_receipt)
        modeling, modeling_views = ensure_modeling_review(
            args, job, intake, candidate, candidate_receipt
        )
        state = read_json(job / "state.json")
        if state["stages"]["modeling_approval"]["status"] != "passed":
            write_operator_receipt(args, job, request, "waiting_for_review", "modeling_approval")
            print_gate("modeling approval", modeling_views, "--approve-modeling-by")
            return 0

        if args.kind not in SUPPORTED_COMPLETE_KINDS:
            write_operator_receipt(args, job, request, "blocked", "articulated_retopology")
            print("\n[OPERATOR] STOP -- articulated automation is not production-complete.")
            print("[OPERATOR] The approved AI mesh is retained at {0}".format(modeling))
            print("[OPERATOR] Generic joint-loop retopology, rig export, and deformation gates remain.")
            return 3

        retopo, _, retopo_views = ensure_retopology(args, job, modeling)
        state = read_json(job / "state.json")
        if state["stages"]["production_retopology"]["status"] != "passed":
            write_operator_receipt(
                args, job, request, "waiting_for_review", "production_retopology"
            )
            print_gate("production retopology", retopo_views, "--approve-retopology-by")
            return 0

        prod = ensure_texture(args, job, intake, retopo)
        state = read_json(job / "state.json")
        if state["stages"]["texture_approval"]["status"] != "passed":
            write_operator_receipt(args, job, request, "waiting_for_review", "texture_approval")
            print_gate("texture approval", prod / "turn", "--approve-texture-by")
            return 0

        production_manifest = (
            ROOT / "out" / (args.asset_id + "-production")
            / (args.asset_id + "-production.ue5import.json")
        )
        if not production_manifest.is_file():
            run([sys.executable, ROOT / "scripts" / "promote_production.py", args.asset_id],
                "publish production payload")
        if args.import_ue5:
            import_ue5(args)
        write_operator_receipt(args, job, request, "packaged", None)
        print("\n[OPERATOR] READY {0}".format(production_manifest))
        if not args.import_ue5:
            print("[OPERATOR] Add --import-ue5 to import and verify it in the UE5 project.")
        return 0
    except (FileExistsError, FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as error:
        print("[OPERATOR] FAILED: {0}".format(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
