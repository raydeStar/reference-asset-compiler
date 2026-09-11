"""Package an accepted, topology-locked AI texture without repainting it.

``package_accepted_texture.py`` remains the legacy static-prop remediation path.
This script is the generated-asset path: it accepts either an unrigged character
or static prop after retopology and UV transport, then builds the texture-review
payload directly:

  1. stage the accepted BaseColor, Roughness, and Metallic maps as PNG under
     their shipped names (JPEG sources are decoded once; nothing is repainted);
  2. bind them to the geometry-locked UV authority and export the production
     FBX, optionally normalizing physical height and floor origin;
  3. export per-triangle UV regions and run the texture gate against the
     skeleton profile (a waiver, if any, must name a human approver);
  4. render the four lit fixed views with the calibrated display profile;
  5. write ``retopo.json`` and a hash-bound receipt.

It stops there. Recording ``texture_approval`` in the ledger is a separate
``rac promote`` by the human reviewer.

Usage:
  python scripts/package_character_texture.py orange-adventurer-cat-ai-v2 \
      --uv-authority work/.../uv-authority.blend \
      --base-color work/.../cat-painted.jpg \
      --metallic work/.../cat-painted_metallic.jpg \
      --roughness work/.../cat-painted_roughness.jpg \
      --profile profiles/skeletons/mascot_biped_tail.json \
      --output-name prod-v1 [--target-height 1.0 --height-reason "..."] \
      [--waiver-reason "..." --waiver-approved-by Ayric]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rac_env  # noqa: E402
from reference_asset_compiler.approvals import TEXTURE_VIEW_NAMES  # noqa: E402
from reference_asset_compiler.io import sha256_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sha256 = sha256_file


def require_file(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"required input is missing: {resolved}")
    return resolved


def run(command: list[str], label: str, allow_failure: bool = False) -> int:
    completed = subprocess.run(command, cwd=ROOT, text=True)
    if completed.returncode and not allow_failure:
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")
    return completed.returncode


def run_blender(script: str, label: str, outputs: list[Path], *arguments: object,
                blender: Path, timeout: float | None) -> None:
    """One Blender stage, with `--python-exit-code 1` and its outputs required back.

    Everything here writes into a production directory this run created, so
    there is nothing retained to clear first; a stage that exits 0 without its
    report is still a failed stage.
    """
    code, stdout, stderr = rac_env.run_blender(script, *arguments, blender=blender,
                                               timeout=timeout, cwd=ROOT)
    if code:
        for line in (stdout + "\n" + stderr).splitlines()[-20:]:
            print("    " + line, file=sys.stderr)
        raise RuntimeError(f"{label} failed with exit code {code}")
    missing = [str(path) for path in outputs if not path.is_file()]
    if missing:
        raise RuntimeError(f"{label} exited 0 without writing {', '.join(missing)}")


def pascal(asset: str) -> str:
    return "".join(part.capitalize() for part in asset.split("-"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset")
    parser.add_argument("--uv-authority", type=Path, required=True)
    parser.add_argument("--base-color", type=Path, required=True)
    parser.add_argument("--metallic", type=Path, required=True)
    parser.add_argument("--roughness", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-name", default="prod-v1")
    parser.add_argument("--target-height", type=float, default=None)
    parser.add_argument("--height-reason", default=None)
    parser.add_argument("--no-recenter", action="store_true")
    parser.add_argument("--waiver-reason", default=None)
    parser.add_argument("--waiver-approved-by", default=None)
    parser.add_argument("--blender", type=Path, default=None)
    parser.add_argument("--render-resolution", type=int, default=1024)
    parser.add_argument("--address-mode", choices=("clamp", "repeat"), default="clamp",
                        help="Explicit tiled-material sampling; leaves legacy atlas behavior unchanged.")
    args = parser.parse_args()

    if (args.waiver_reason is None) != (args.waiver_approved_by is None):
        raise ValueError("a texture waiver needs both a reason and a human approver")
    if args.waiver_approved_by and args.waiver_approved_by.lower() in {
            "pipeline", "compiler", "automation", "package_character_texture.py"}:
        raise ValueError("a texture waiver must name a human approver")
    if args.target_height is not None and not args.height_reason:
        raise ValueError("--target-height needs --height-reason")

    work = ROOT / "work" / args.asset
    if not (work / "state.json").is_file():
        raise ValueError(f"no workspace ledger at {work}")
    prod = work / args.output_name
    if prod.exists():
        raise ValueError(f"refusing to overwrite retained production directory: {prod}")

    uv_authority = require_file(args.uv_authority)
    sources = {
        "BaseColor": require_file(args.base_color),
        "Roughness": require_file(args.roughness),
        "Metallic": require_file(args.metallic),
    }
    profile_path = require_file(args.profile)
    blender = Path(args.blender) if args.blender else Path(rac_env.find_blender())
    require_file(blender)

    # Validate every map before a single byte lands in the production
    # directory, so a rejected set leaves no half-written package behind.
    decoded: dict[str, Image.Image] = {}
    sizes = set()
    for channel, source in sources.items():
        image = Image.open(source)
        image = image.convert("RGB") if channel == "BaseColor" else image.convert("L")
        sizes.add(image.size)
        decoded[channel] = image
    if len(sizes) != 1 or len({s for size in sizes for s in size}) != 1:
        raise ValueError(f"texture maps must be one square resolution, found {sorted(sizes)}")
    resolution = next(iter(sizes))[0]

    prod.mkdir(parents=True)
    staged: dict[str, Path] = {}
    for channel, image in decoded.items():
        target = prod / f"T_{args.asset}_{channel}.png"
        image.save(target)
        staged[channel] = target

    intake = json.loads((work / "intake.json").read_text(encoding="utf-8-sig"))
    asset_kind = intake.get("asset_kind")
    static_prop = asset_kind == "static_prop"
    material_name = f"M_{pascal(args.asset)}_Body"
    mesh_name = f"{'SM' if static_prop else 'SK'}_{pascal(args.asset)}"
    textures_json = prod / "production-texture-map.json"
    textures_json.write_text(json.dumps(
        {material_name: {channel: str(path) for channel, path in staged.items()}}, indent=2
    ) + "\n", encoding="utf-8")

    production_fbx = prod / f"{args.asset}_production.fbx"
    bind_report_path = prod / "texture-payload-binding.json"
    bind_arguments: list[object] = [
        uv_authority, production_fbx, bind_report_path, textures_json,
        "--material-name", material_name, "--mesh-name", mesh_name,
    ]
    if args.target_height is not None:
        bind_arguments += ["--target-height", str(args.target_height)]
    if not args.no_recenter:
        bind_arguments.append("--recenter")
    run_blender("bind_texture_payload.py", "texture payload binding",
                [production_fbx, bind_report_path], *bind_arguments,
                blender=blender, timeout=rac_env.BLENDER_STEP_TIMEOUT)
    bind_report = json.loads(bind_report_path.read_text(encoding="utf-8-sig"))

    regions_path = prod / "uv-regions.npz"
    run_blender("export_uv_regions.py", "UV region export", [regions_path],
                production_fbx, regions_path,
                blender=blender, timeout=rac_env.BLENDER_STEP_TIMEOUT)

    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    gate_profile_path = profile_path
    if args.waiver_reason:
        profile["texture_waiver"] = {
            "reason": args.waiver_reason,
            "approved_by": args.waiver_approved_by,
            "asset_id": args.asset,
            "source_profile": str(profile_path),
            "source_profile_sha256": sha256(profile_path),
        }
        gate_profile_path = prod / "texture-gate-profile.json"
        gate_profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    gate_path = prod / "gate-tex.json"
    gate_exit = run([
        sys.executable, str(ROOT / "scripts" / "gate_texture.py"),
        str(regions_path), str(staged["BaseColor"]), str(gate_profile_path), str(gate_path),
        "--material-name", material_name,
        "--address-mode", args.address_mode,
    ], "texture gate", allow_failure=True)
    gate = json.loads(gate_path.read_text(encoding="utf-8-sig"))

    turn = prod / "turn"
    run_blender("render_turnaround.py", "fixed-view render",
                [turn / name for name in TEXTURE_VIEW_NAMES],
                production_fbx, turn, args.render_resolution, "albedo", "smooth", "calibrated",
                blender=blender, timeout=rac_env.BLENDER_STEP_TIMEOUT)

    # Hunyuan3D-Paint emits base color, metallic and roughness but no AO map.
    # White is the physically neutral AO value: it adds no invented shadowing
    # and lets the UE packer keep one explicit R/G/B contract for every asset.
    ao_path = prod / f"T_{args.asset}_AO.png"
    Image.new("L", (resolution, resolution), 255).save(ao_path)
    staged["AO"] = ao_path

    retopo = {
        "schema": ("reference-asset-compiler.generated-texture-payload.v1"
                   if static_prop else
                   "reference-asset-compiler.character-texture-payload.v1"),
        "asset_id": args.asset,
        "asset_kind": asset_kind,
        "source_uv_authority": str(uv_authority),
        "source_uv_authority_sha256": sha256(uv_authority),
        "uv_layer": bind_report["uv_layer"],
        "resolution": resolution,
        "low_tris": bind_report["triangles"],
        "vertices": bind_report["vertices"],
        "output_fbx": production_fbx.name,
        "mesh_name": bind_report["mesh_name"],
        "material_name": material_name,
        "physical_scale": {
            "uniform_scale": bind_report["uniform_scale_applied"],
            "translation_m": bind_report["translation_applied"],
            "height_m": bind_report["after"]["height_m"],
            "source_height_m": bind_report["before"]["height_m"],
            "reason": args.height_reason or "source scale retained; height is unreviewed art direction",
        },
        "baked": {channel: path.name for channel, path in staged.items()},
        "texture_lineage": {
            "address_mode": args.address_mode,
            "operation": "stage accepted AI maps as PNG and bind to the unchanged UV authority",
            "sources": {channel: {"path": str(source), "sha256": sha256(source)}
                        for channel, source in sources.items()},
            "uv_operation": "unchanged UVs; geometry moved only by the recorded similarity transform",
        },
        "texture_gate": {"ok": bool(gate.get("ok")), "exit_code": gate_exit,
                         "waived": bool(gate.get("texture_waived")),
                         "profile": str(gate_profile_path)},
        "ok": bool(gate.get("ok")),
    }
    from reference_asset_compiler.texture_payload import bind_texture_payload
    retopo = bind_texture_payload(retopo, uv_authority, production_fbx, gate_path)
    retopo_path = prod / "retopo.json"
    retopo_path.write_text(json.dumps(retopo, indent=2) + "\n", encoding="utf-8")

    receipt = {
        "schema": ("reference-asset-compiler.accepted-generated-texture.v1"
                   if static_prop else
                   "reference-asset-compiler.accepted-character-texture.v1"),
        "asset_id": args.asset,
        "source_uv_authority_sha256": retopo["source_uv_authority_sha256"],
        "source_texture_sha256": {c: v["sha256"] for c, v in retopo["texture_lineage"]["sources"].items()},
        "staged_texture_sha256": {channel: sha256(path) for channel, path in staged.items()},
        "production_fbx_sha256": sha256(production_fbx),
        "binding_report_sha256": sha256(bind_report_path),
        "retopo_sha256": sha256(retopo_path),
        "gate_texture_sha256": sha256(gate_path),
        "uv_regions_sha256": sha256(regions_path),
        "fixed_views_sha256": {p.name: sha256(p) for p in sorted((prod / "turn").glob("*.png"))},
        "uniform_scale": bind_report["uniform_scale_applied"],
        "height_m": bind_report["after"]["height_m"],
        "triangles": bind_report["triangles"],
        "texture_gate_ok": bool(gate.get("ok")),
        "operations": [
            "decode accepted AI maps once and stage as PNG under shipped names",
            "write neutral white AO because the painter does not author occlusion",
            "bind maps to the unchanged UV authority as one Principled material",
            "apply only the recorded uniform scale and floor-origin translation",
            "export FBX with relative texture references beside the payload",
        ],
    }
    (prod / "accepted-texture-payload.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    status = "gate passed" if gate.get("ok") else "GATE FAILED (no ledger promotion)"
    print(
        f"[GENERATED TEXTURE] {args.asset}: {retopo['low_tris']} tris, "
        f"{retopo['physical_scale']['height_m']:.3f} m, {resolution} atlas -- {status}."
    )
    return 0 if gate.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
