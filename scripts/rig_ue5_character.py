"""Rig any T-posed character blend onto the UE5 Manny skeleton, end to end.

  py -3.12 scripts/rig_ue5_character.py <character.blend> <out_dir> \
      --manny-dir <dir with manny_refpose.json + manny_anim_poses.json> \
      [--template hm08.npz --head-npz head.npz] [--arm-ratio 0.42] [--plan-ignore OBJECT ...]

Stages (each writes into <out_dir>, which must not exist):
  1. ortho/      calibrated orthographic renders  (blender/render_ortho_views.py)
  2. keypoints/  DWPose body keypoints, front + side  (detect_body_landmarks_dwpose.py)
  3. plan.json   joint plan from keypoints + mesh slices  (blender/plan_ue5_joints.py);
                 --plan-ignore leaves objects (mesh hair) out of its measurements
  4. fit/        skin + Manny-axis export rig  (blender/fit_ue5_manny_rig.py)
  5. fit/poses/  real Manny animation frames on the result  (blender/pose_ue5_anim_test.py)

The Manny dumps come from scripts/ue5/dump_manny_reference.py (Epic content,
kept out of Git). The keypoint stage needs a Python with torch and the DWPose
TorchScript weights, both normally from a ComfyUI portable install with
comfyui_controlnet_aux:

  --comfyui DIR / RAC_COMFYUI   the install (python_embeded/ and ComfyUI/ inside)
  --torch-python / RAC_TORCH_PYTHON, --dwpose / RAC_DWPOSE   override each piece
  --blender / RAC_BLENDER

With RAC_COMFYUI unset the install defaults to the original workstation's
path (LOCAL_COMFYUI below), which exists nowhere else: set it on yours.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_BLENDER = r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
# The original workstation's install, used only when RAC_COMFYUI is unset.
LOCAL_COMFYUI = r"C:\Users\Ayric\Source\Repos\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable"
DWPOSE_WEIGHTS = "ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/DWPose-TorchScript-BatchSize5/dw-ll_ucoco_384_bs5.torchscript.pt"


def run(cmd, log):
    with open(log, "w", encoding="utf-8") as fh:
        proc = subprocess.run([str(c) for c in cmd], stdout=fh, stderr=subprocess.STDOUT)
    if proc.returncode:
        raise RuntimeError(f"Stage failed ({proc.returncode}); see {log}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("blend")
    p.add_argument("out")
    p.add_argument("--manny-dir", required=True)
    p.add_argument("--template")
    p.add_argument("--head-npz")
    p.add_argument("--arm-ratio", default="0.42")
    p.add_argument("--name", default="Character")
    p.add_argument("--plan-ignore", nargs="*", default=[],
                   help="objects the joint plan leaves out of its measurements (mesh hair); they are still "
                        "weighted, rigidly to the head")
    p.add_argument("--blender", default=os.environ.get("RAC_BLENDER", DEFAULT_BLENDER))
    p.add_argument("--comfyui", default=os.environ.get("RAC_COMFYUI", LOCAL_COMFYUI),
                   help="ComfyUI portable install with comfyui_controlnet_aux (env RAC_COMFYUI)")
    p.add_argument("--torch-python", default=os.environ.get("RAC_TORCH_PYTHON"),
                   help="Python with torch (env RAC_TORCH_PYTHON; default: the install's python_embeded)")
    p.add_argument("--dwpose", default=os.environ.get("RAC_DWPOSE"),
                   help="DWPose TorchScript weights (env RAC_DWPOSE; default: the install's controlnet_aux checkpoint)")
    a = p.parse_args()
    comfyui = Path(a.comfyui)
    a.torch_python = a.torch_python or str(comfyui / "python_embeded" / "python.exe")
    a.dwpose = a.dwpose or str(comfyui / DWPOSE_WEIGHTS)
    out = Path(a.out).resolve()
    if out.exists():
        raise SystemExit("Choose a new output directory; earlier rigs are evidence.")
    (out / "logs").mkdir(parents=True)
    blend = Path(a.blend).resolve()
    manny = Path(a.manny_dir).resolve()
    blender = [a.blender, "--background", "--factory-startup"]
    run(blender + [blend, "--python-exit-code", "1", "--python", SCRIPTS / "blender/render_ortho_views.py", "--",
                   out / "ortho", "2048"], out / "logs/1-ortho.log")
    (out / "keypoints").mkdir()
    for view in ("front", "left"):
        run([a.torch_python, "-I", SCRIPTS / "detect_body_landmarks_dwpose.py", out / "ortho" / f"{view}.png",
             out / "keypoints" / f"{view}.json", "--model", a.dwpose, "--overlay", out / "keypoints" / f"{view}.png"],
            out / f"logs/2-keypoints-{view}.log")
    plan_args = ["--front-kp", out / "keypoints/front.json", "--side-kp", out / "keypoints/left.json",
                 "--ortho", out / "ortho/ortho.json", "--out", out / "plan.json", "--arm-ratio", a.arm_ratio]
    if a.plan_ignore:
        plan_args += ["--ignore", *a.plan_ignore]
    fit_extra = []
    if a.template and a.head_npz:
        plan_args += ["--template", Path(a.template).resolve(), "--head-npz", Path(a.head_npz).resolve()]
        fit_extra = ["--template", Path(a.template).resolve(), "--head-npz", Path(a.head_npz).resolve()]
    run(blender + [blend, "--python-exit-code", "1", "--python", SCRIPTS / "blender/plan_ue5_joints.py", "--"] + plan_args,
        out / "logs/3-plan.log")
    run(blender + [blend, "--python-exit-code", "1", "--python", SCRIPTS / "blender/fit_ue5_manny_rig.py", "--",
                   "--plan", out / "plan.json", "--manny", manny / "manny_refpose.json", "--out", out / "fit",
                   "--name", a.name] + fit_extra,
        out / "logs/4-fit.log")
    run(blender + [out / "fit" / f"{a.name}_UE5.blend", "--python-exit-code", "1", "--python", SCRIPTS / "blender/pose_ue5_anim_test.py",
                   "--", manny / "manny_refpose.json", manny / "manny_anim_poses.json", out / "fit/poses", "--res", "720",
                   "--lens", "70"], out / "logs/5-poses.log")
    report = json.loads((out / "fit/fit-report.json").read_text())
    receipts = json.loads((out / "fit/poses/pose-receipts.json").read_text())
    summary = {"blend": str(blend), "plan": json.loads((out / "plan.json").read_text())["derivation"],
               "bones": report["bone_count"], "deform_bones": report["deform_bones"],
               "idle_fingertip_cm": next((r["fingertip_height_cm"] for r in receipts if r["pose"].startswith("MM_Idle")), None),
               "export_blend": report["outputs"]["export_blend"]}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.exit(main())
