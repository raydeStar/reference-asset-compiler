"""Offline, source-checked Ennix review build; every output stays a candidate.

The frozen acquisition is an explicit input, not an implicit model service.
Run with Python 3.12 and Blender 5.2.2; see docs/ENNIX_REBUILD.md.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--blender", required=True)
    p.add_argument("--recipe", default=str(ROOT / "recipes/ennix-open-review-20261009.json"))
    p.add_argument("--manny-dir", help="Manny reference dumps (scripts/ue5/dump_manny_reference.py); enables the UE5 rig stage")
    a = p.parse_args()
    inputs, out = Path(a.inputs).resolve(), Path(a.out).resolve()
    recipe_path = Path(a.recipe).resolve()
    recipe = json.loads(recipe_path.read_text())
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
    receipt = {"recipe_sha256": sha(recipe_path), "python": sys.version,
               "blender": subprocess.check_output([a.blender, "--version"], text=True).strip(),
               "input_hashes": {k: v["sha256"] for k, v in recipe["inputs"].items()},
               "commands": [], "production_ready": False, "completed": False}
    receipt["dependencies"] = {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pillow")}
    receipt["skeleton_profile_sha256"] = sha(ROOT / "profiles/skeletons/ue5_manny.json")
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
        print(f"Ennix: {script} — the recipe has no secret ingredients, sir.", flush=True)
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

    run("refine_ennix_proportions.py", [local / "head.npz", local / "head.json", local / "original-landmarks.json", out / "head.npz"])
    run("refine_ennix_surface.py", ["--template", local / "template.npz", "--head", local / "head.npz",
        "--receipt", local / "head.json", "--texture", local / "head-basecolor.png",
        "--original-landmarks", local / "original-landmarks.json", "--out", out / "paint", "--restore-brows"])
    head_paint = out / "paint/head_basecolor.png"
    if "face_paint" in recipe:
        # Measured colour pass: blush, stubble, hairline root shadow, ear and neck tone.
        run("refine_ennix_face_paint.py", ["--template", local / "template.npz", "--head", local / "head.npz",
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
        "--hair-roughness", .45, "--save-blend", out / "head-before-anatomy.blend"], True)
    run("blender/finish_ennix_anatomy.py", [out / "head-before-anatomy.blend", out / "head.npz",
        local / "makehuman", out / "head.blend", "--template", local / "template.npz"], True)
    run("blender/prepare_ennix_body.py", [local / "body-acquisition.blend", out / "body", "--triangles", recipe["body_review_triangles"]], True)
    run("paint_ennix_body.py", [out / "body/body.npz", local / "body-front.png", local / "body-back.png",
        out / "body/paint", "--side", local / "body-left.png"])
    assembly = out / "assembly/Ennix_Character_Review.blend"
    run("blender/assemble_ennix_character.py", [out / "body/body-uv.blend", out / "body/paint/body_basecolor.png",
        out / "head.blend", out / "assembly", "--samples", recipe["samples"],
        "--head-placement", local / "placement.json", "--clear-neck-overlap"], True)
    proxy = out / "rig-input/Ennix_proxy.fbx"
    run("blender/export_ennix_rig_proxy.py", [assembly, proxy], True)
    landmarks = json.loads((local / "rig-landmarks.json").read_text())
    landmarks.update(payload_fbx=str(proxy), payload_fbx_sha256=sha(proxy),
        based_on_measured_landmarks_sha256=recipe["inputs"]["rig-landmarks.json"]["sha256"],
        rebuild_note="Fixed measured skeleton reused with the same frozen body; fresh proxy includes the recorded collar/head repairs.")
    lm = out / "rig-input/landmarks.json"
    lm.write_text(json.dumps(landmarks, indent=2))
    (out / "proxy-rig").mkdir()
    run("blender/rig_from_landmarks.py", [proxy, lm, ROOT / "profiles/skeletons/ue5_manny.json",
        out / "proxy-rig/Ennix_proxy_rigged.fbx", out / "proxy-rig/rig-report.json"], True)
    run("blender/bind_ennix_assembly.py", [assembly, out / "proxy-rig/Ennix_proxy_rigged.blend", out / "rigged"], True)
    native = out / "rigged/Ennix_Rigged.blend"
    run("blender/export_ennix_groom.py", [native, out / "export/Ennix_Groom.abc"], True)
    if a.manny_dir and "ue5" in recipe:
        # Manny-conformant game rig: measured joints, solid-voxel weights, Manny's bone axes.
        run("rig_ue5_character.py", [native, out / "ue5", "--manny-dir", Path(a.manny_dir).resolve(),
            "--template", local / "template.npz", "--head-npz", out / "head.npz", "--name", "Ennix",
            "--arm-ratio", recipe["ue5"]["arm_ratio"], "--blender", a.blender])
        game = out / "ue5/fit/Ennix_UE5.blend"
        run("blender/export_ue5_character.py", [out / "export/Ennix_UE5.fbx"], True, blend=game)
        run("blender/export_ennix_groom.py", [game, out / "export/Ennix_Groom_UE5.abc"], True)
    run("blender/pose_ennix_review.py", [native, out / "pose", "--samples", recipe["samples"]], True)
    run("blender/audit_ennix_repeatability.py", [native, out / "semantic-audit.json"], True)
    run("validate_ennix_visuals.py", [local / "original.png", local / "body-front.png",
        out / "assembly/front_preview.png", out / "visual-validation"])
    # A failed artistic/budget gate is retained review evidence, never a waiver.
    run("blender/gate_rig.py", [out / "rigged/Ennix_Body_Face.fbx", ROOT / "profiles/skeletons/ue5_manny.json",
        out / "export/gate-rig.json"], True, allowed_codes=(0, 1))
    if not (out / "export/gate-rig.json").is_file():
        raise RuntimeError("Rig gate crashed before producing its receipt")
    run("blender/deform_test.py", [out / "rigged/Ennix_Body_Face.fbx", out / "export/deformation",
        out / "export/deformation.json", 900, "ue5_manny"], True)
    receipt["completed"] = True
    receipt["outputs"] = {str(f.relative_to(out)): sha(f) for f in out.rglob("*")
        if f.is_file() and "inputs" not in f.relative_to(out).parts and f.name != "build-receipt.json"}
    receipt["limits"] = ["Human likeness and texture approval pending", "No cooked runtime proof",
        "120k outfit review budget exceeds the current strict 20k skeleton profile ceiling", "Held inspection pose is not a moving idle"]
    save()
    print(f"The fitting is reproducible, sir. Review receipt: {out / 'build-receipt.json'}", flush=True)


if __name__ == "__main__":
    main()
