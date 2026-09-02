"""One image in, a compiled and gated asset out. The chain, not a new pipeline.

Every stage this runs already existed and is unchanged. What was missing was
the two ends: nothing performed `generate_candidates`, and nothing turned a
generated mesh into the recipe the compiler reads. This is those two, plus the
wiring.

    image
      -> rac new            intake: copy, hash, route
      -> generate_geometry  a candidate mesh, from the image
      -> describe_mesh      measure it, unpack its textures
      -> this               write recipes/<asset>.json
      -> compile_prop       join, scale, rename, publish the authority
      -> build_production   heal, remesh, unwrap, bake, gate
      -> promote_production out/<asset>-production/

Two things it will not do, and both are deliberate.

It will not invent a scale. A photograph carries no size: the same chair image
is a doll's chair or a throne, and the compiler's own convention is that a
height has to come with the measurement that justified it. `--height` is
required, and `--height-reason` is recorded in the recipe next to it.

It will not call the result approved. The routing plan puts `modeling_approval`
between generation and production for a reason, and this stops to let a person
look at fixed views. `--yes` skips the pause for an operator who has already
decided; it does not skip the renders.

Static props only. A generated humanoid would need the complete `rig_and_skin`
route. Auto-Rig Pro and a portable existing-mesh candidate driver are present,
but the retained canary proves hands need explicit landmarks, and deformation,
game export, Manny FBX, and UE gates are not yet wired into this chain. A
character without those skeleton contracts is not a character.

Usage:
  python scripts/compile_from_image.py my-crate D:/art/crate.png --height 0.6 \
      --height-reason "Waist height on the 2 m cohort; measured against pelvis at 0.91 m."
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rac_env  # noqa: E402
from reference_asset_compiler.approvals import (  # noqa: E402
    MODELING_VIEW_NAMES,
    record_modeling_derivative,
    texture_evidence_paths,
    validate_generated_candidate,
    validate_modeling_approval,
    validate_texture_approval,
)
from reference_asset_compiler.io import read_json  # noqa: E402
from reference_asset_compiler.workspace import promote_stage  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_path(path):
    resolved = Path(path).resolve()
    legacy = rac_env.legacy_root(required=False)
    if legacy:
        legacy = legacy.resolve()
        try:
            relative = resolved.relative_to(legacy)
        except ValueError:
            pass
        else:
            return "${RAC_LEGACY_ROOT}/" + relative.as_posix()
    return str(resolved).replace("\\", "/")


def camel(asset_id: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[-_]+", asset_id) if part)


def child_env():
    """Put src/ on the path so this runs from a checkout, not just an install.

    `pip install -e .` is one more step between a person and their first
    compiled asset, and the tests already run without it.
    """
    env = dict(os.environ)
    existing = env.get('PYTHONPATH', '')
    src = str(ROOT / 'src')
    env['PYTHONPATH'] = src + (os.pathsep + existing if existing else '')
    return env


def run(command, label):
    print("\n[CHAIN] {0}".format(label))
    done = subprocess.run([str(c) for c in command], cwd=str(ROOT), env=child_env())
    if done.returncode != 0:
        print("[CHAIN] STOPPED at {0} (exit {1})".format(label, done.returncode))
    return done.returncode


def blender(script, *script_args):
    return [rac_env.find_blender(), "-b", "--factory-startup", "--python",
            ROOT / "scripts" / "blender" / script, "--", *script_args]


def geometry_adapter_ids():
    registry = json.loads(
        (ROOT / "configs" / "model-adapters.json").read_text(encoding="utf-8")
    )
    return {
        item["id"] for item in registry["adapters"]
        if item.get("role") in {"geometry", "geometry_and_texture"}
    }


def validate_candidate_lineage(candidate, image, report_path):
    """Fail closed unless a mesh is hash-bound to an AI-conditioned image run."""
    candidate = Path(candidate).resolve()
    image = Path(image).resolve()
    report_path = Path(report_path).resolve()
    if not report_path.is_file():
        raise ValueError("candidate lineage report is missing: {0}".format(report_path))
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    failures = []
    if report.get("schema") != "reference-asset-compiler.geometry-candidate.v1":
        failures.append("unrecognized candidate lineage schema")
    if report.get("ok") is not True:
        failures.append("generation did not finish successfully")
    if report.get("adapter") not in geometry_adapter_ids():
        failures.append("adapter is not registered for AI geometry generation")
    if report.get("candidate_sha256") != sha256(candidate):
        failures.append("candidate hash does not match the lineage report")
    if report.get("image_sha256") != sha256(image):
        failures.append("approved image hash does not match the lineage report")
    if failures:
        raise ValueError("; ".join(failures))
    return report


def write_recipe(asset_id, description, mesh, height, reason, texture_dir,
                 reference_authority, candidate_report, lineage):
    """Turn a measurement into the recipe the compiler already knows how to read.

    The material rename matters more than it looks. A generated mesh calls its
    material `Material_0`, and that name ends up on the shipped asset, in the
    engine, in every material slot anyone ever looks at.
    """
    name = camel(asset_id)
    materials = description["materials"]
    renames = {}
    textures = {}
    for index, source_material in enumerate(materials):
        target = "M_{0}_{1}".format(name, "Body" if index == 0 else "Part{0}".format(index))
        renames[source_material] = target
        file = description["textures"].get(source_material)
        if file:
            textures[source_material] = {"BaseColor": str((texture_dir / file).resolve())}

    recipe = {
        "asset_id": asset_id,
        "kind": "static_prop",
        "articulation": "static",
        "skeleton_profile": None,
        "source": {
            "authority_fbx": portable_path(mesh),
            "reference_authority": portable_path(reference_authority),
            "candidate_lineage_report": portable_path(candidate_report),
            "candidate_lineage_sha256": sha256(candidate_report),
            "geometry_adapter": lineage["adapter"],
            "candidate_sha256": lineage["candidate_sha256"],
            "reference_sha256": lineage["image_sha256"],
            "note": ("Generated candidate, drafted into a recipe by "
                     "compile_from_image.py. {0} objects, {1} triangles, "
                     "{2} material(s) as generated.".format(
                         description["objects"], description["tris"],
                         len(materials))),
        },
        "material_textures": textures,
        "normalize": {
            "mesh_name": "SM_{0}".format(name),
            "target_height_m": height,
            "target_height_reason": reason,
            "recenter": True,
            "yaw_degrees": 0.0,
            "material_renames": renames,
        },
    }
    path = ROOT / "recipes" / "{0}.json".format(asset_id)
    path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_id")
    parser.add_argument("image", type=Path)
    parser.add_argument("--height", type=float, required=True,
                        help="finished height in metres; an image does not carry one")
    parser.add_argument("--height-reason", default=None,
                        help="the measurement behind --height; recorded in the recipe")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--min-free-vram", type=int, default=20000)
    parser.add_argument("--candidate", type=Path, default=None,
                        help="skip generation and use this mesh instead")
    parser.add_argument("--candidate-report", type=Path, default=None,
                        help="AI lineage report; defaults to <candidate>.json")
    parser.add_argument("--yes", action="store_true",
                        help="continue noninteractively after ledger-backed modeling approval")
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--target-triangles", type=int, default=18_000)
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", args.asset_id):
        print("[CHAIN] FAILED: asset_id should be lower-case-hyphenated")
        return 1
    if not args.height_reason:
        print("[CHAIN] FAILED: --height needs --height-reason.")
        print("        Every other scale in this repository carries the measurement")
        print("        that justified it. The chair's came from putting its seat on")
        print("        field-scout-male's knee. An unexplained number is the thing")
        print("        nobody can check later.")
        return 1

    work = ROOT / "work" / args.asset_id
    image = args.image.resolve()

    # --- intake: hash the reference and route it -----------------------------
    intake_path = work / "intake.json"
    if intake_path.is_file():
        intake = json.loads(intake_path.read_text(encoding="utf-8-sig"))
        expected = intake.get("source", {}).get("sha256")
        actual = sha256(image)
        if intake.get("asset_id") != args.asset_id or expected != actual:
            print("[CHAIN] FAILED: existing workspace belongs to a different "
                  "asset or reference hash")
            return 1
        if run([sys.executable, "-m", "reference_asset_compiler.cli", "audit", work],
               "audit retained intake") != 0:
            return 1
    elif run([sys.executable, "-m", "reference_asset_compiler.cli", "new",
              args.asset_id, image, "--kind", "static_prop",
              "--articulation", "static", "--workspace-root", ROOT / "work"],
             "intake and route") != 0:
        return 1

    # --- generate ------------------------------------------------------------
    candidate = args.candidate
    candidate_report = args.candidate_report
    if candidate is None:
        code = run([sys.executable, ROOT / "scripts" / "generate_geometry.py",
                    args.asset_id, image, "--seed", args.seed,
                    "--resolution", args.resolution,
                    "--min-free-vram", args.min_free_vram], "generate geometry")
        if code != 0:
            if code == 2:
                print("[CHAIN] Nothing was generated and nothing was damaged.")
                print("        Free the card and run again, or pass --candidate")
                print("        to compile a mesh you already have.")
            return 1
        stem = "{0}-pixal3d-{1}-seed{2}.glb".format(
            args.asset_id, args.resolution, args.seed)
        candidate = work / "candidates" / stem
        candidate_report = candidate.with_suffix(".json")
    candidate = candidate.resolve()
    if not candidate.is_file():
        print("[CHAIN] FAILED: no candidate mesh at {0}".format(candidate))
        return 1
    if candidate_report is None:
        candidate_report = candidate.with_suffix(".json")
    try:
        lineage = validate_candidate_lineage(candidate, image, candidate_report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("[CHAIN] FAILED: candidate lacks valid image-conditioned AI lineage")
        print("        {0}".format(error))
        print("        --candidate is an import route, not permission to use a")
        print("        manually or procedurally approximated Blender replacement.")
        return 1
    state = read_json(work / "state.json")
    generated = state["stages"]["generate_candidates"]
    if generated["status"] == "pending":
        promote_stage(
            work,
            "generate_candidates",
            [candidate, Path(candidate_report)],
            "Hash-bound image-conditioned AI geometry candidate retained.",
            "compile_from_image.py",
        )
    try:
        validate_generated_candidate(work, candidate, Path(candidate_report))
    except ValueError as error:
        print("[CHAIN] FAILED: generated-candidate ledger does not match this run")
        print("        {0}".format(error))
        return 1

    # --- describe: measure it, unpack its textures ---------------------------
    texture_dir = work / "candidate-textures"
    describe_path = work / "candidate-describe.json"
    if run(blender("describe_mesh.py", candidate, texture_dir, describe_path),
           "measure the candidate") != 0 or not describe_path.exists():
        return 1
    description = json.loads(describe_path.read_text(encoding="utf-8"))
    if description["has_armature"]:
        print("[CHAIN] FAILED: that mesh carries an armature, so it is not a")
        print("        static prop. The character route needs the complete")
        print("        rig_and_skin gate chain; only a reviewed candidate driver")
        print("        exists here today.")
        return 1
    if not description["materials"]:
        print("[CHAIN] FAILED: the candidate has no materials to texture from")
        return 1

    # --- recipe --------------------------------------------------------------
    recipe = write_recipe(args.asset_id, description, candidate,
                          args.height, args.height_reason, texture_dir, image,
                          candidate_report, lineage)
    scale = args.height / max(description["height_m"], 1e-6)
    print("\n[CHAIN] wrote {0}".format(recipe))
    print("[CHAIN] {0} tris, {1} material(s), {2:.3f} m generated -> {3:.3f} m "
          "shipped ({4:.4f}x)".format(description["tris"],
                                      len(description["materials"]),
                                      description["height_m"], args.height, scale))

    # --- intake the authority, then compile ----------------------------------
    if run([sys.executable, ROOT / "scripts" / "compile_prop.py", recipe],
           "normalise into an authority") != 0:
        return 1

    # --- production reduction candidate ------------------------------------
    # Keep the normalized dense authority as the texture donor. The reduced
    # mesh is a separate geometry authority consumed by retopo_bake, which
    # unwraps it and bakes the dense appearance onto it after approval.
    normalized = ROOT / "out" / args.asset_id / (args.asset_id + ".fbx")
    manifest_path = ROOT / "out" / args.asset_id / (args.asset_id + ".ue5import.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if description["tris"] <= args.triangle_budget:
        views = work / "authority-fixed-views"
        if run(blender("render_turnaround.py", normalized, views, 900),
               "render under-budget authority fixed views") != 0:
            return 1
        manifest["production_reduction"] = {
            "status": "not_required",
            "source_triangles": description["tris"],
            "triangle_budget": args.triangle_budget,
            "reason": "normalized authority already meets the triangle budget",
        }
        modeling_candidate = normalized
        modeling_operations = ["normalize_scale_origin"]
        modeling_artifacts = [work / "normalize-prop-report.json"]
    else:
        reduction_dir = work / "reduction-v1"
        reduction_report = reduction_dir / "reduction-report.json"
        reduced = reduction_dir / "voxel-qem-candidate.fbx"
        if reduction_dir.exists() and any(reduction_dir.iterdir()):
            reusable = False
            if reduction_report.is_file() and reduced.is_file():
                retained = json.loads(reduction_report.read_text(encoding="utf-8-sig"))
                reusable = (
                    retained.get("status") == "mechanical_pass"
                    and retained.get("source", {}).get("sha256") == sha256(normalized)
                    and retained.get("output", {}).get("sha256") == sha256(reduced)
                )
            if not reusable:
                print("[CHAIN] FAILED: retained reduction directory is not reusable: {0}".format(
                    reduction_dir))
                print("        Preserve it as evidence and choose a new asset id or version.")
                return 1
            print("[CHAIN] reusing retained mechanical reduction {0}".format(reduced))
        else:
            shell = shutil.which("pwsh") or shutil.which("powershell")
            if not shell:
                print("[CHAIN] FAILED: PowerShell is required for the durable reduction wrapper")
                return 1
            if run([
                shell, "-NoProfile", "-File", ROOT / "scripts" / "run_voxel_qem_reduction.ps1",
                "-InputMesh", normalized,
                "-OutputDirectory", reduction_dir,
                "-TriangleBudget", args.triangle_budget,
                "-TargetTriangles", args.target_triangles,
            ], "voxel-conditioned QEM reduction") != 0:
                return 1

        views = reduction_dir / "fixed-views"
        if run(blender("render_turnaround.py", reduced, views, 900),
               "render reduced fixed views") != 0:
            return 1
        retained = json.loads(reduction_report.read_text(encoding="utf-8-sig"))
        manifest["production_reduction"] = {
            "backend": retained["backend"],
            "candidate": str(reduced.resolve()),
            "candidate_sha256": retained["output"]["sha256"],
            "report": str(reduction_report.resolve()),
            "status": retained["status"],
        }
        modeling_candidate = reduced
        modeling_operations = ["normalize_scale_origin", "voxel_remesh", "collapse_qem"]
        modeling_artifacts = [
            normalized,
            work / "normalize-prop-report.json",
            reduction_report,
        ]

    reduction = manifest["production_reduction"]
    reduction["fixed_views"] = str(views.resolve())
    try:
        modeling_lineage, lineage_artifacts = record_modeling_derivative(
            work, candidate, modeling_candidate, modeling_operations, modeling_artifacts)
    except ValueError as error:
        print("[CHAIN] FAILED: modeling derivative is not bound to the AI candidate")
        print("        {0}".format(error))
        return 1
    try:
        approval = validate_modeling_approval(work, modeling_candidate, views)
    except ValueError as error:
        approval = None
        reduction["modeling_approval"] = {"status": "pending", "reason": str(error)}
    else:
        reduction["modeling_approval"] = approval
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if approval is None:
        print("\n[CHAIN] PAUSE -- modeling approval.")
        print("        out/{0}/ now holds the authority. The plan puts a human"
              .format(args.asset_id))
        print("        here, before production, and a good front view hides a")
        print("        broken side. Render it and look:")
        print("          python scripts/build_production.py {0}".format(args.asset_id))
        print("        Fixed views are already in")
        print("          {0}".format(views.relative_to(ROOT)))
        print("        Record the candidate and neutral fixed views in the ledger:")
        command = [
            sys.executable, "-m", "reference_asset_compiler.cli", "promote", str(work),
            "modeling_approval", "--evidence", str(modeling_candidate),
            "--evidence", str(modeling_lineage),
        ]
        for artifact in lineage_artifacts:
            command.extend(["--evidence", str(artifact)])
        for name in MODELING_VIEW_NAMES:
            command.extend(["--evidence", str(views / name)])
        command.extend([
            "--note", "Approved against immutable source in four neutral fixed views.",
            "--approved-by", "<reviewer-name>",
        ])
        print("          " + " ".join(command))
        print("        --yes cannot create or bypass this approval.")
        return 0

    if not args.yes:
        print("\n[CHAIN] modeling approval is valid and hash-bound.")
        print("        Re-run with --yes to continue through production gates.")
        return 0

    if run([sys.executable, ROOT / "scripts" / "build_production.py", args.asset_id],
           "heal, remesh, unwrap, bake, gate") != 0:
        return 1
    prod = work / "prod-v2"
    retopo = json.loads((prod / "retopo.json").read_text(encoding="utf-8-sig"))
    try:
        validate_texture_approval(work, prod, retopo)
    except ValueError as error:
        print("\n[CHAIN] PAUSE -- texture approval.")
        print("        Automated bake and texture metrics passed, but publish is blocked:")
        print("        {0}".format(error))
        command = [
            sys.executable, "-m", "reference_asset_compiler.cli", "promote", str(work),
            "texture_approval",
        ]
        for evidence in texture_evidence_paths(prod, retopo):
            command.extend(["--evidence", str(evidence)])
        command.extend([
            "--note", "Approved base color and PBR response in four lit fixed views.",
            "--approved-by", "<reviewer-name>",
        ])
        print("          " + " ".join(command))
        print("        Then run: python scripts/promote_production.py {0}".format(args.asset_id))
        return 0
    if run([sys.executable, ROOT / "scripts" / "promote_production.py", args.asset_id],
           "publish") != 0:
        return 1

    print("\n[CHAIN] out/{0}-production/ is ready to import.".format(args.asset_id))
    print("[CHAIN] It carries hash-bound human modeling and texture approvals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
