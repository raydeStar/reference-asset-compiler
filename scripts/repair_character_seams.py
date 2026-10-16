"""Rebuild the bounded Character02 seam candidate from pinned acquired inputs.

No inference or engine installation. Each invocation requires a fresh directory;
the receipt records every command, script/input hash, and failure as it happens.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--device", choices=("CPU", "GPU"), default="CPU")
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
    inputs = {}
    for key, entry in recipe["inputs"].items():
        path = (ROOT / entry["path"]).resolve()
        if sha(path) != entry["sha256"]:
            raise ValueError(f"Input changed: {key}; preserve the pinned customer, sir.")
        inputs[key] = path
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "scripts").mkdir()
    shutil.copy2(args.recipe, out / "recipe.json")
    receipt = {"recipe_sha256": sha(args.recipe), "inputs": recipe["inputs"],
               "driver_sha256": sha(__file__), "commands": [], "script_hashes": {},
               "production_ready": False, "human_review": "pending", "state": "running"}
    shutil.copy2(__file__, out / "scripts" / Path(__file__).name)

    def save():
        (out / "repair.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    def run(name, parameters, blend=None):
        script = ROOT / "scripts/blender" / name
        receipt["script_hashes"][name] = sha(script)
        shutil.copy2(script, out / "scripts" / name)
        command = [str(args.blender.resolve()), "--background", "--factory-startup"]
        if blend:
            command.append(str(blend))
        command += ["--python-exit-code", "1", "--python", str(script), "--"]
        command += [str(p) for p in parameters]
        entry = {"argv": command, "exit_code": None}
        receipt["commands"].append(entry)
        save()
        log = out / f"{len(receipt['commands']):02d}-{Path(name).stem}.log"
        print(f"Repair: {name}; the evidence travels with the tailoring.", flush=True)
        with log.open("w", encoding="utf-8") as stream:
            entry["exit_code"] = subprocess.run(command, cwd=ROOT, stdout=stream,
                                                stderr=subprocess.STDOUT, check=False).returncode
        save()
        if entry["exit_code"]:
            receipt["state"] = "failed"
            save()
            raise RuntimeError(f"Repair stopped: inspect {log}")

    def run_py(name, parameters):
        script = ROOT / "scripts" / name
        receipt["script_hashes"][name] = sha(script)
        shutil.copy2(script, out / "scripts" / name)
        command = [sys.executable, str(script)] + [str(p) for p in parameters]
        entry = {"argv": command, "exit_code": None}
        receipt["commands"].append(entry)
        save()
        log = out / f"{len(receipt['commands']):02d}-{Path(name).stem}.log"
        print(f"Repair: {name}; the evidence travels with the tailoring.", flush=True)
        with log.open("w", encoding="utf-8") as stream:
            entry["exit_code"] = subprocess.run(command, cwd=ROOT, stdout=stream,
                                                stderr=subprocess.STDOUT, check=False).returncode
        save()
        if entry["exit_code"]:
            receipt["state"] = "failed"
            save()
            raise RuntimeError(f"Repair stopped: inspect {log}")

    # Imported helpers also belong to the reproducibility record.
    for relative in ("src/reference_asset_compiler/template_hands.py",
                     "src/reference_asset_compiler/budgets.py",
                     "profiles/triangle-budgets.json",
                     "scripts/blender/review_character_seams.py",
                     "scripts/blender/export_ue5_character.py"):
        path = ROOT / relative
        receipt["script_hashes"][relative] = sha(path)
        shutil.copy2(path, out / "scripts" / path.name)
    hands = out / "Character02_UE5_hands.blend"
    run("transplant_template_hands.py", ["--template", inputs["template"],
        "--skin-texture", inputs["skin_texture"], "--cut-beyond-m", recipe["cut_beyond_m"],
        "--save-blend", hands, "--receipt", out / "hands.json"], blend=inputs["shoulders"])
    collar = recipe["collar"]
    run("fair_character_collar.py", [hands, out / "collar", "--source-sha256", sha(hands),
        "--object", collar["object"], "--box", *collar["box"],
        "--max-displacement-m", collar["max_displacement_m"], "--iterations", collar["iterations"]])
    candidate = out / "collar/Character02_UE5_seams.blend"
    repack = recipe.get("repack")
    if repack:
        helper = ROOT / "scripts/blender/outfit_uv_islands.py"
        receipt["script_hashes"]["scripts/blender/outfit_uv_islands.py"] = sha(helper)
        shutil.copy2(helper, out / "scripts" / helper.name)
        repack_dir = out / "repack"
        run_py("repack_outfit_coherent.py", [
            "--blend", candidate, "--object", collar["object"],
            "--basecolor", inputs["outfit_basecolor"],
            "--mask", inputs["outfit_mask"],
            "--head-basecolor", inputs["skin_texture"],
            "--stage-dir", inputs["outfit_stage_json"].parent,
            "--scale", repack.get("scale", 2),
            "--pad", repack.get("pad", 2),
            "--blender", args.blender.resolve(),
            "--out", repack_dir,
        ])
        candidate = repack_dir / "Character02_UE5_seams.blend"
        shutil.copytree(repack_dir / "outfit-paint", out / "outfit-paint")
    if recipe.get("pbr_bake"):
        run_py("bake_outfit_pbr.py", [
            "--islands", out / "repack/islands-repacked.npz",
            "--basecolor", out / "outfit-paint/body_basecolor.png",
            "--mask", out / "outfit-paint/garment_mask.png",
            "--out", out / "outfit-paint",
        ])
    manny = inputs["manny_reference"].parent
    if inputs["manny_poses"].parent != manny:
        raise ValueError("Manny reference and poses must share their source directory")
    run("verify_character_hand_repair.py", [inputs["original"], inputs["shoulders"], candidate,
        out / "hand-verification.json", "--manny-dir", manny])
    exported = out / "export/Character02_UE5.fbx"
    coat = out / "Character02_UE5_coat.blend"
    run("add_coat_chains.py", [exported, "--profile", inputs["character_profile"],
        "--receipt", out / "coat.json", "--save-blend", coat], blend=candidate)
    if "skin_texture" in inputs:
        (out / "hands-paint").mkdir(exist_ok=True)
        shutil.copy2(inputs["skin_texture"], out / "hands-paint/head_basecolor.png")
    if "hair_basecolor" in inputs:
        shutil.copy2(inputs["hair_basecolor"], out / "export/hair-mesh-basecolor.png")
    if "hair_normal" in inputs:
        shutil.copy2(inputs["hair_normal"], out / "export/hair-mesh-normal.png")
    run("gate_rig.py", [exported, inputs["skeleton_profile"], out / "gate-rig.json", "--tier", "hero"])
    run("review_character_seams.py", [coat, out / "review", "--manny-dir", manny,
        "--device", args.device, "--samples", "32"])
    run("review_character_seams.py", [coat, out / "attack-review", "--manny-dir", manny,
        "--device", args.device, "--samples", "32", "--animation", "MM_Attack_01",
        "--only", "wrist-l,wrist-r,wrist-l-outer,wrist-r-outer"])
    receipt.update(state="review_candidate", candidate_sha256=sha(candidate),
                   coat_blend_sha256=sha(coat), fbx_sha256=sha(exported))
    save()
    print(f"Candidate ready for inspection at {out}; AAA remains an earned title, sir.")


if __name__ == "__main__":
    main()
