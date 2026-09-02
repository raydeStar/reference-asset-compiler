"""Run an immutable AniGen authority candidate with recorded provenance.

This wrapper is intended to run inside AniGen's isolated Linux environment.
It deliberately treats AniGen as a candidate generator, not as an automatic
production-asset promotion step.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import torch


BASE_REQUIRED_CHECKPOINTS = (
    "ckpts/anigen/ss_dae/ckpts/encoder_final.pt",
    "ckpts/anigen/ss_dae/ckpts/decoder_final.pt",
    "ckpts/anigen/slat_dae/ckpts/encoder_final.pt",
    "ckpts/anigen/slat_dae/ckpts/decoder_final.pt",
    "ckpts/dinov2/dinov2_vitl14/dinov2_vitl14_reg4_pretrain.pth",
    "ckpts/dsine/dsine.pt",
    "ckpts/dsine/tf_efficientnet_b5_ap-9e82fae8.pth",
    "ckpts/vgg/vgg16-397923af.pth",
)

FLOW_CHECKPOINTS = {
    "ss_flow_solo": "ckpts/anigen/ss_flow_solo/ckpts/denoiser.pt",
    "ss_flow_duet": "ckpts/anigen/ss_flow_duet/ckpts/denoiser.pt",
    "ss_flow_epic": "ckpts/anigen/ss_flow_epic/ckpts/denoiser.pt",
    "slat_flow_auto": "ckpts/anigen/slat_flow_auto/ckpts/denoiser.pt",
    "slat_flow_control": "ckpts/anigen/slat_flow_control/ckpts/denoiser.pt",
}

REQUIRED_MODULES = (
    "nvdiffrast",
    "pytorch3d",
    "rtree",
    "spconv",
    "trimesh",
    "xformers",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_runtime_dependencies() -> dict[str, str]:
    """Import every late-stage dependency before spending GPU time."""
    versions: dict[str, str] = {}
    failures: list[str] = []
    for module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
            versions[module_name] = str(getattr(module, "__version__", "import-ok"))
        except Exception as exc:  # pragma: no cover - exact loader errors vary by host
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")
    if failures:
        raise RuntimeError(
            "AniGen runtime dependency preflight failed before inference: "
            + "; ".join(failures)
        )
    return versions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--ss-flow",
        choices=("ss_flow_solo", "ss_flow_duet", "ss_flow_epic"),
        default="ss_flow_solo",
        help="AniGen sparse-structure checkpoint; duet favors detailed skeletons.",
    )
    parser.add_argument(
        "--slat-flow",
        choices=("slat_flow_auto", "slat_flow_control"),
        default="slat_flow_auto",
    )
    parser.add_argument(
        "--joints-density",
        type=int,
        choices=range(0, 5),
        help="Optional 0..4 density level; valid only with slat_flow_control.",
    )
    parser.add_argument("--minimum-free-vram-mib", type=int, default=18_000)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    upstream = args.upstream.resolve()
    image = args.image.resolve()
    output_dir = args.output_dir.resolve()
    final_mesh = output_dir / "mesh.glb"
    report_path = output_dir / "run-report.json"

    if not image.is_file():
        raise FileNotFoundError(image)
    if not (upstream / "example.py").is_file():
        raise FileNotFoundError(upstream / "example.py")
    if args.joints_density is not None and args.slat_flow != "slat_flow_control":
        raise RuntimeError("--joints-density requires --slat-flow slat_flow_control")
    required_checkpoints = (
        *BASE_REQUIRED_CHECKPOINTS,
        FLOW_CHECKPOINTS[args.ss_flow],
        FLOW_CHECKPOINTS[args.slat_flow],
    )
    missing = [item for item in required_checkpoints if not (upstream / item).is_file()]
    if missing:
        raise RuntimeError(f"AniGen checkpoint set is incomplete: {missing}")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.force:
        raise RuntimeError(f"Refusing to overwrite non-empty candidate directory: {output_dir}")
    dependency_versions = verify_runtime_dependencies()
    if not torch.cuda.is_available():
        raise RuntimeError("AniGen requires CUDA")

    free_bytes, total_bytes = torch.cuda.mem_get_info()
    free_mib = free_bytes // (1024 * 1024)
    if free_mib < args.minimum_free_vram_mib:
        raise RuntimeError(
            f"AniGen requires {args.minimum_free_vram_mib} MiB free VRAM; found {free_mib} MiB"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(upstream / "example.py"),
        "--image_path",
        str(image),
        "--output_dir",
        str(output_dir.parent),
        "--output_name",
        output_dir.name,
        "--seed",
        str(args.seed),
        "--ss_flow_path",
        f"ckpts/anigen/{args.ss_flow}",
        "--slat_flow_path",
        f"ckpts/anigen/{args.slat_flow}",
        "--deterministic",
    ]
    if args.joints_density is not None:
        command.extend(("--joints_density", str(args.joints_density)))
    started_at = datetime.now(timezone.utc)
    inference_env = os.environ.copy()
    inference_env.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    completed = subprocess.run(command, cwd=upstream, check=False, env=inference_env)
    completed_at = datetime.now(timezone.utc)
    if completed.returncode != 0:
        failure_report = {
            "schema": "reference-studio.model-candidate-run.v1",
            "generator": "AniGen",
            "status": "failed",
            "retry_policy": "manual_or_later_goal_turn_only",
            "input": {"path": str(image), "sha256": sha256(image)},
            "configuration": {
                "seed": args.seed,
                "ss_flow": args.ss_flow,
                "slat_flow": args.slat_flow,
                "joints_density": args.joints_density,
                "deterministic": True,
            },
            "runtime": {
                "python": sys.version,
                "torch": torch.__version__,
                "cuda": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(),
                "free_vram_mib_at_start": free_mib,
                "dependencies": dependency_versions,
                "cublas_workspace_config": inference_env["CUBLAS_WORKSPACE_CONFIG"],
                "started_at": started_at.isoformat(),
                "failed_at": completed_at.isoformat(),
            },
            "failure": {
                "exit_code": completed.returncode,
                "stage": "upstream_inference_process",
            },
        }
        report_path.write_text(
            json.dumps(failure_report, indent=2) + "\n", encoding="utf-8"
        )
        raise RuntimeError(f"AniGen inference failed with exit code {completed.returncode}; not retrying")
    if not final_mesh.is_file():
        raise RuntimeError(f"AniGen completed without the expected mesh: {final_mesh}")

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "schema": "reference-studio.model-candidate-run.v1",
        "generator": "AniGen",
        "role": "geometry_and_rig_challenger_not_automatic_authority",
        "upstream": str(upstream),
        "upstream_commit": commit,
        "input": {
            "path": str(image),
            "sha256": sha256(image),
        },
        "configuration": {
            "seed": args.seed,
            "ss_flow": args.ss_flow,
            "slat_flow": args.slat_flow,
            "joints_density": args.joints_density,
            "deterministic": True,
        },
        "runtime": {
            "python": sys.version,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(),
            "free_vram_mib_at_start": free_mib,
            "total_vram_mib": total_bytes // (1024 * 1024),
            "dependencies": dependency_versions,
            "cublas_workspace_config": inference_env["CUBLAS_WORKSPACE_CONFIG"],
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": (completed_at - started_at).total_seconds(),
        },
        "outputs": {
            "mesh": str(final_mesh),
            "mesh_bytes": final_mesh.stat().st_size,
            "mesh_sha256": sha256(final_mesh),
            "processed_image": str(output_dir / "processed_image.png"),
        },
        "promotion": {
            "status": "unreviewed",
            "requires_fixed_view_review": True,
            "requires_human_approval": True,
        },
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"ANIGEN_CANDIDATE_OK report={report_path}")
    print("A candidate may impress, but only evidence earns the title of authority.")


if __name__ == "__main__":
    main()
