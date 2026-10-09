"""Offline, source-checked character review build; every output stays a candidate.

The frozen acquisition is an explicit input, not an implicit model service. A
build needs three things: --inputs (the frozen bundle, hash-checked against the
recipe), the recipe (counts, groom, face paint, tier) and the character profile
(profiles/characters/<name>.json: names, input object names and the
character's measurements). The recipe names its profile; --character overrides.
Run with Python 3.12 and Blender 5.2.2; see docs/CHARACTER_REBUILD.md.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from coat_profile import resolve_coat  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def face_proportions_options(character):
    """transport_face_proportions.py's options from the profile (none: no corner lift)."""
    lift = character.get("face_proportions", {}).get("mouth_corner_lift_mm")
    return ["--mouth-corner-lift", *lift] if lift else []


def body_reduction_options(recipe, character):
    """prepare_body_acquisition.py's counts (recipe) and where the hands begin.

    Recipes from 20261010 give hands and garment their own count (a body block);
    older ones one uniform count. Where the hands begin belongs to the
    character's pose: the profile's body.hands_beyond_abs_x_m. Recipes 20261010
    and 20261011 carry it in their body block, which stands in when the profile
    has none; two different values stop the build.
    """
    if "body" not in recipe:
        return ["--triangles", recipe["body_review_triangles"]]
    body = recipe["body"]
    profile_x = character.get("body", {}).get("hands_beyond_abs_x_m")
    recipe_x = body.get("hands_beyond_abs_x_m")
    if profile_x is not None and recipe_x is not None and profile_x != recipe_x:
        raise ValueError(f"The character profile puts the hands beyond |x| {profile_x} m and the "
                         f"recipe beyond {recipe_x} m; keep one value (the profile's body.hands_beyond_abs_x_m).")
    hands_x = recipe_x if profile_x is None else profile_x
    if hands_x is None:
        raise ValueError("The recipe gives the hands their own count; set where they begin in the "
                         "character profile's body.hands_beyond_abs_x_m.")
    return ["--triangles", body["garment_triangles"], "--hand-triangles", body["hand_triangles"],
            "--hands-beyond-abs-x", hands_x, "--measure-samples", body.get("measure_samples", 0)]


def body_paint_options(character):
    """paint_body_from_views.py's registration and paint options from the profile."""
    camera, paint = character["source_camera"], character["body_paint"]
    options = ["--px-per-m", camera["px_per_m"], "--front-origin", *camera["front_origin_px"],
               "--side-origin", *camera["side_origin_px"], "--side-band", *paint["side_band_abs_x_m"]]
    if paint.get("unmirrored_red"):
        options += ["--unmirrored-red", *paint["unmirrored_red"]]
    if "min_facing" in paint:
        options += ["--min-facing", paint["min_facing"]]
    if "mask_erode_px" in paint:
        options += ["--mask-erode-px", paint["mask_erode_px"]]
    for key, flag in (("fill", "--fill"), ("fill_trust", "--fill-trust"), ("normal_smoothing_m", "--normal-smoothing")):
        if key in paint:
            options += [flag, paint[key]]
    return options


def coat_skeleton_profile(skeleton, coat_receipt):
    """The skeleton contract plus a coat's chain bones, so the rig gate can check the coated FBX.

    The chains are optional bones with their parents expected; everything else
    (required bones, influence cap, triangle budget) stays the skeleton's.
    """
    profile = copy.deepcopy(skeleton)
    bones = coat_receipt["bones"]
    profile["profile_id"] = skeleton["profile_id"] + "+coat"
    profile["optional_bones"] = list(skeleton.get("optional_bones", [])) + [b["name"] for b in bones]
    profile["expected_parents"] = {**skeleton.get("expected_parents", {}),
                                   **{b["name"]: b["parent"] for b in bones}}
    profile["coat_note"] = "Coat chains from add_coat_chains.py added to {0}.".format(skeleton["profile_id"])
    return profile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--blender", required=True)
    p.add_argument("--recipe", required=True, help="e.g. recipes/ennix-open-review-20261011.json")
    p.add_argument("--character", help="character profile, e.g. profiles/characters/ennix.json (default: the one the recipe names)")
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU",
                   help="Cycles device for the review renders; CPU leaves the GPU free (slower)")
    p.add_argument("--manny-dir", help="Manny reference dumps (scripts/ue5/dump_manny_reference.py); enables the UE5 rig stage")
    a = p.parse_args()
    inputs, out = Path(a.inputs).resolve(), Path(a.out).resolve()
    recipe_path = Path(a.recipe).resolve()
    recipe = json.loads(recipe_path.read_text())
    if not (a.character or recipe.get("character")):
        p.error("Name a character profile with --character (profiles/characters/<name>.json).")
    character_path = Path(a.character).resolve() if a.character else ROOT / recipe["character"]
    character = json.loads(character_path.read_text())
    prefix = character["asset_prefix"]
    outfit_params = ROOT / character["outfit_paint_params"]
    try:
        body_args = body_reduction_options(recipe, character)
        coat = resolve_coat(character.get("coat"))
    except ValueError as error:
        p.error(str(error))
    if out.exists():
        p.error("Choose a fresh output directory; old fittings are evidence, sir.")
    for name, info in recipe["inputs"].items():
        source = inputs / name
        if not source.is_file() or sha(source) != info["sha256"]:
            p.error(f"Missing or changed frozen input: {name}")
    out.mkdir(parents=True)
    local = out / "inputs"
    for name in recipe["inputs"]:
        dest = local / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inputs / name, dest)
    # Rewrite only path pointers in disposable copies; frozen sources stay intact.
    for name, key, target in (("head.json", "picture", "front-landmarks.json"),
                              ("front-landmarks.json", "image", "head-front.png"),
                              ("original-landmarks.json", "image", "original-head-crop.png")):
        path = local / name
        data = json.loads(path.read_text())
        if key == "picture":
            data[key]["landmarks"] = str(local / target)
        else:
            data[key] = str(local / target)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    receipt = {"recipe_sha256": sha(recipe_path), "character": character["name"],
               "character_profile_sha256": sha(character_path), "outfit_paint_params_sha256": sha(outfit_params),
               "python": sys.version,
               "blender": subprocess.check_output([a.blender, "--version"], text=True).strip(),
               "input_hashes": {k: v["sha256"] for k, v in recipe["inputs"].items()},
               "commands": [], "production_ready": False, "completed": False}
    receipt["dependencies"] = {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pillow")}
    receipt["skeleton_profile_sha256"] = sha(ROOT / "profiles/skeletons/ue5_manny.json")
    receipt["triangle_budgets_sha256"] = sha(ROOT / "profiles/triangle-budgets.json")
    logs = out / "logs"
    logs.mkdir()

    def save():
        (out / "build-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    def run(script, args, blender=False, allowed_codes=(0,), blend=None):
        source = ROOT / "scripts" / script
        cmd = ([a.blender, "-b", "--factory-startup"] + ([str(blend)] if blend else [])
               + ["--python-exit-code", "1", "--python", str(source), "--"]
               if blender else [sys.executable, str(source)]) + [str(x) for x in args]
        item = {"script": script, "script_sha256": sha(source), "argv": cmd}
        receipt["commands"].append(item)
        log = logs / f"{len(receipt['commands']):02d}-{source.stem}.log"
        print(f"{character['name']}: {script} — the recipe has no secret ingredients, sir.", flush=True)
        save()
        started = time.monotonic()
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(cmd, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        item.update(returncode=result.returncode, seconds=round(time.monotonic() - started, 2), log=str(log))
        save()
        if result.returncode not in allowed_codes:
            raise RuntimeError(f"Stage failed; retained log: {log}")

    def flags(params):
        args = []
        for key, value in params.items():
            args += ["--" + key.replace("_", "-"), *(value if isinstance(value, list) else [value])]
        return args

    run("transport_face_proportions.py", [local / "head.npz", local / "head.json", local / "original-landmarks.json", out / "head.npz",
        *face_proportions_options(character)])
    run("reproject_face_paint.py", ["--template", local / "template.npz", "--head", local / "head.npz",
        "--receipt", local / "head.json", "--texture", local / "head-basecolor.png",
        "--original-landmarks", local / "original-landmarks.json", "--out", out / "paint", "--restore-brows"])
    head_paint = out / "paint/head_basecolor.png"
    if "face_paint" in recipe:
        # Measured colour pass: blush, stubble, hairline root shadow, ear and neck tone.
        run("refine_face_paint.py", ["--template", local / "template.npz", "--head", local / "head.npz",
            "--receipt", local / "head.json", "--texture", head_paint, "--landmarks", local / "front-landmarks.json",
            "--guidance", local / "head-front.png", "--painting", out / "paint/original-aligned.png",
            "--hair-shell", local / "hair.npz", "--out", out / "face-paint", *flags(recipe["face_paint"])])
        head_paint = out / "face-paint/head_basecolor.png"
    run("blender/grow_hair_groom.py", [local / "template.npz", local / "head.npz", local / "hair.npz",
        local / "hair-basecolor.png", out / "strands.npz", *flags(recipe["groom"]), "--coherent-waves"], True)
    run("blender/render_painted_head.py", [local / "template.npz", out / "head.npz", local / "head.json",
        local / "hair.npz", head_paint, local / "hair-basecolor.png", local / "head-front.png",
        out / "head-review", "--strands", out / "strands.npz", "--resolution", recipe["resolution"],
        "--samples", recipe["samples"], "--views", "front", "three-quarter", "side", "back", "top",
        "--subdivision", 1, "--oral-helpers", "--skin-emission", .4, "--hair-tint", .85, .95, 1.05,
        "--hair-roughness", .45, "--save-blend", out / "head-before-anatomy.blend", "--device", a.device], True)
    oral = character["oral_anatomy"]
    run("blender/fit_oral_anatomy.py", [out / "head-before-anatomy.blend", out / "head.npz",
        local / "makehuman", out / "head.blend", "--template", local / "template.npz", "--name", prefix,
        "--mouth-box", *oral["mouth_box_m"], "--neck", *oral["neck_m"]], True)
    run("blender/prepare_body_acquisition.py", [local / "body-acquisition.blend", out / "body", *body_args,
        "--body-object", character["inputs"]["body_object"]], True)
    camera = character["source_camera"]
    run("paint_body_from_views.py", [out / "body/body.npz", local / "body-front.png", local / "body-back.png",
        out / "body/paint", "--side", local / "body-left.png", *body_paint_options(character)])
    # Game garment materials: mask, cleaned albedo and detail normals (the game imports outfit-paint/).
    run("refine_outfit_paint.py", [out / "body/body.npz", out / "body/paint/body_basecolor.png",
        out / "body/paint/coverage.png", out / "outfit-paint", "--params", outfit_params])
    assembly = out / f"assembly/{prefix}_Character_Review.blend"
    neck = character["neck_overlap"]
    run("blender/assemble_character.py", [out / "body/body-uv.blend", out / "body/paint/body_basecolor.png",
        out / "head.blend", out / "assembly", "--samples", recipe["samples"], "--name", prefix,
        "--body-lift", character["body_lift_m"],
        "--source-camera", camera["px_per_m"], *camera["image_px"], *camera["front_origin_px"],
        "--head-placement", local / "placement.json",
        "--clear-neck-overlap", *neck["ellipse_m"], neck["above_z_m"], neck["rim_above_z_m"], neck["rim_abs_x_m"],
        "--device", a.device], True)
    proxy = out / f"rig-input/{prefix}_proxy.fbx"
    run("blender/export_skinning_proxy.py", [assembly, proxy, "--name", prefix], True)
    derived_landmarks = "rig-landmarks.json" not in recipe["inputs"]
    if derived_landmarks:
        # No measured skeleton for this character yet: derive one from this build's proxy.
        # Its review overlays render with EEVEE (a GPU), so a CPU build skips them.
        derived = out / "rig-input/derived"
        run("blender/derive_humanoid_landmarks.py", [proxy, derived, "--profile", ROOT / "profiles/skeletons/ue5_manny.json",
            *(["--no-overlays"] if a.device == "CPU" else [])], True)
        landmarks = json.loads((derived / "humanoid-landmarks.json").read_text())
        landmarks.update(rebuild_note="Derived in this build from its own proxy by derive_humanoid_landmarks.py; "
                         "not measured and not reviewed.")
        receipt["rig_landmarks"] = "derived in this build from its proxy (rig-input/derived/); not measured and not reviewed"
    else:
        landmarks = json.loads((local / "rig-landmarks.json").read_text())
        landmarks.update(payload_fbx=str(proxy), payload_fbx_sha256=sha(proxy),
            based_on_measured_landmarks_sha256=recipe["inputs"]["rig-landmarks.json"]["sha256"],
            rebuild_note="Fixed measured skeleton reused with the same frozen body; fresh proxy includes the recorded collar/head repairs.")
    lm = out / "rig-input/landmarks.json"
    lm.write_text(json.dumps(landmarks, indent=2))
    (out / "proxy-rig").mkdir()
    run("blender/rig_from_landmarks.py", [proxy, lm, ROOT / "profiles/skeletons/ue5_manny.json",
        out / f"proxy-rig/{prefix}_proxy_rigged.fbx", out / "proxy-rig/rig-report.json"], True)
    run("blender/bind_assembly_to_rig.py", [assembly, out / f"proxy-rig/{prefix}_proxy_rigged.blend", out / "rigged",
        "--name", prefix, "--neck-blend", *character["neck_weight_blend_m"],
        "--collar-repair", neck["rim_above_z_m"], neck["rim_abs_x_m"]], True)
    native = out / f"rigged/{prefix}_Rigged.blend"
    run("blender/export_groom_alembic.py", [native, out / f"export/{prefix}_Groom.abc", "--name", prefix], True)
    if a.manny_dir and "ue5" in recipe:
        # Manny-conformant game rig: measured joints, solid-voxel weights, Manny's bone axes.
        run("rig_ue5_character.py", [native, out / "ue5", "--manny-dir", Path(a.manny_dir).resolve(),
            "--template", local / "template.npz", "--head-npz", out / "head.npz", "--name", prefix,
            "--arm-ratio", recipe["ue5"]["arm_ratio"], "--blender", a.blender])
        game = out / f"ue5/fit/{prefix}_UE5.blend"
        game_fbx = out / f"export/{prefix}_UE5.fbx"
        if coat is None:
            run("blender/export_ue5_character.py", [game_fbx], True, blend=game)
        else:
            # A long coat gets bones the game simulates. The plain export stays
            # beside it as .nocoat.fbx; the coated one takes the game's name.
            uncoated = out / f"export/{prefix}_UE5.nocoat.fbx"
            run("blender/export_ue5_character.py", [uncoated], True, blend=game)
            coat_receipt = out / f"export/{prefix}_UE5.coat.json"
            run("blender/add_coat_chains.py", [game_fbx, "--profile", character_path, "--receipt", coat_receipt],
                True, blend=game)
            chains = json.loads(coat_receipt.read_text())
            coat_skeleton = out / "export/skeleton-ue5-coat.json"
            coat_skeleton.write_text(json.dumps(coat_skeleton_profile(
                json.loads((ROOT / "profiles/skeletons/ue5_manny.json").read_text()), chains), indent=2))
            receipt["coat"] = {"fbx": str(game_fbx.relative_to(out)), "uncoated_fbx": str(uncoated.relative_to(out)),
                               "receipt": str(coat_receipt.relative_to(out)),
                               "skeleton_profile": str(coat_skeleton.relative_to(out)),
                               "chains": {name: {key: c[key] for key in ("degrees", "bones", "hem_found", "max_weight")}
                                          for name, c in chains["chains"].items()},
                               "coat_vertices": chains["coat_vertices"]}
            save()
        run("blender/export_groom_alembic.py", [game, out / f"export/{prefix}_Groom_UE5.abc", "--name", prefix], True)
    views = character["review_views"]
    run("blender/pose_character_review.py", [native, out / "pose", "--samples", recipe["samples"], "--device", a.device,
        "--name", prefix, "--held-centre", *views["held_centre_m"], "--head-centre", *views["head_centre_m"],
        "--face-centre", *views["face_centre_m"]], True)
    run("blender/audit_semantic_fingerprint.py", [native, out / "semantic-audit.json"], True)
    run("validate_silhouette.py", [local / "original.png", local / "body-front.png",
        out / "assembly/front_preview.png", out / "visual-validation"])
    # A failed artistic/budget gate is retained review evidence, never a waiver.
    # The tier, when the recipe names one, sets the triangle ceiling in place of
    # the skeleton profile's flat number (profiles/triangle-budgets.json).
    tier = ["--tier", recipe["character_tier"]] if recipe.get("character_tier") else []
    skeleton = ROOT / "profiles/skeletons/ue5_manny.json"
    gates = [(out / f"rigged/{prefix}_Body_Face.fbx", out / "export/gate-rig.json", skeleton)]
    if (out / f"export/{prefix}_UE5.fbx").is_file():
        # A coated FBX is gated against the skeleton plus its coat chains.
        ue5_skeleton = out / "export/skeleton-ue5-coat.json" if "coat" in receipt else skeleton
        gates.append((out / f"export/{prefix}_UE5.fbx", out / "export/gate-rig-ue5.json", ue5_skeleton))
    for fbx, report, profile in gates:
        run("blender/gate_rig.py", [fbx, profile, report, *tier],
            True, allowed_codes=(0, 1))
        if not report.is_file():
            raise RuntimeError("Rig gate crashed before producing its receipt")
    run("blender/deform_test.py", [out / f"rigged/{prefix}_Body_Face.fbx", out / "export/deformation",
        out / "export/deformation.json", 900, "ue5_manny"], True)
    receipt["completed"] = True
    receipt["outputs"] = {str(f.relative_to(out)): sha(f) for f in out.rglob("*")
        if f.is_file() and "inputs" not in f.relative_to(out).parts and f.name != "build-receipt.json"}
    gate = json.loads((out / "export/gate-rig.json").read_text())
    tier_id = (gate["tri_budget_rule"].get("character_tier") or {}).get("id")
    budget_limit = "{0:,} triangles {1} {2} of {3:,}".format(
        gate["total_tris"], "within" if gate["total_tris"] <= gate["tri_budget"] else "exceed",
        "the {0} tier's ceiling".format(tier_id) if tier_id else "the skeleton profile's flat ceiling",
        gate["tri_budget"])
    receipt["limits"] = ["Human likeness and texture approval pending", "No cooked runtime proof",
        budget_limit, "Held inspection pose is not a moving idle"]
    if derived_landmarks:
        receipt["limits"].append("Rig landmarks derived in this build, not measured or reviewed")
    if "coat" in receipt:
        receipt["limits"].append("Coat chains placed and skinned automatically; their cloth physics is unreviewed")
    save()
    print(f"The fitting is reproducible, sir. Review receipt: {out / 'build-receipt.json'}", flush=True)


if __name__ == "__main__":
    main()
