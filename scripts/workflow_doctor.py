"""Inspect the selected route without inference, downloads, or asset changes."""
from __future__ import annotations

import argparse
# `datetime.UTC` is 3.11+. Spelled the 3.10 way so an older interpreter reaches
# the version check below and is told about it, instead of dying on import.
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import rac_env  # noqa: E402
from reference_asset_compiler.io import sha256_file  # noqa: E402

GEOMETRY_HASHES = {
    "single_view": ("run_hy3d_single_view.py",
                    "119b41dd0df2ab4e1c9f75a6159f3f8a2c7d47dfc7a20309ac7fbf0519a2af6c"),
    "multiview": ("run_hy3d_multiview.py",
                  "ebe3900b671a1a32416cfb650aa57967150aceb8ae2994fc252da9c61356c207"),
}
PAINT_HASH = "b039065ea96e0e63effecba4379f63b8228f830b036ef1392790e5bf6b8f8a8b"
PROFILES = ("ledger", "geometry", "texture", "ue", "all")


def probe_addon(blender: Path, script: str, prefix: str) -> tuple[bool, str]:
    try:
        result = subprocess.run([str(blender), "--background", "--factory-startup",
                                 "--python-exit-code", "1", "--python",
                                 str(ROOT / "scripts" / "blender" / script)],
                                capture_output=True, text=True, errors="replace", timeout=45)
        line = next((line for line in reversed(result.stdout.splitlines())
                     if line.startswith(prefix)), None)
        if line:
            report = json.loads(line[len(prefix):])
            return result.returncode == 0 and report.get("ok") is True, json.dumps(report)
        return False, f"No probe report; exit={result.returncode}"
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return False, str(error)


def collect(profile="all", legacy_root=None, comfy_root=None, blender=None,
            unreal_cmd=None, probe_addons=True):
    checks = []

    def add(identifier, available, routes, detail):
        checks.append({"id": identifier, "available": bool(available),
                       "required_for": ", ".join(routes) if routes else "optional",
                       "required": bool(routes) and (profile == "all" or profile in routes),
                       "detail": str(detail)})

    def component(identifier, root, relative, routes, variable, exact=None):
        path = Path(root) / relative if root else None
        is_file = exact or Path(relative).suffix.lower() in {".exe", ".json", ".py"}
        exists = path is not None and (path.is_file() if is_file else path.is_dir())
        if exact:
            actual = sha256_file(path) if exists else "missing"
            add(identifier, actual == exact, routes,
                f"{path or variable + ' not set'} sha256={actual}")
        else:
            add(identifier, exists, routes, path or f"{variable} not set")

    add("python", sys.version_info >= (3, 11), PROFILES, sys.executable)
    for dependency in ("numpy", "PIL", "scipy"):
        add(f"python.{dependency}", importlib.util.find_spec(dependency) is not None,
            PROFILES, f"Install compiler dependencies with {sys.executable} -m pip install -e .")
    legacy_root = legacy_root or os.environ.get("RAC_LEGACY_ROOT")
    comfy_root = comfy_root or os.environ.get("RAC_COMFY_ROOT")
    blender = Path(blender) if blender else rac_env.find_blender(required=False)
    unreal_cmd = Path(unreal_cmd) if unreal_cmd else rac_env.find_unreal_cmd(required=False)
    add("blender", blender and blender.is_file(), ("geometry", "texture", "ue"),
        blender or "Set RAC_BLENDER to the Blender executable")
    add("unreal.commandlet", unreal_cmd and unreal_cmd.is_file(), ("ue",),
        unreal_cmd or "Set RAC_UNREAL_CMD to UnrealEditor-Cmd.exe")
    component("hy3d2mv.python", legacy_root, ".venv-hy3d/Scripts/python.exe",
              ("geometry",), "RAC_LEGACY_ROOT")
    component("hy3d2mv.upstream", legacy_root, "upstream/Hunyuan3D-2",
              ("geometry",), "RAC_LEGACY_ROOT")
    for mode, (name, expected) in GEOMETRY_HASHES.items():
        identifier = "hy3d2mv.runner_exact" if mode == "multiview" else "hy3d2.runner_exact"
        component(identifier, ROOT, f"workflows/geometry/hunyuan3d/{name}",
                  ("geometry",), "repository", expected)
    for identifier, path in (("python", ".venv-hy3d21/Scripts/python.exe"),
                             ("upstream", "upstream/Hunyuan3D-2.1"),
                             ("model", "models/hy3d21/Hunyuan3D-2.1")):
        component(f"hy3d21.{identifier}", legacy_root, path, ("texture",), "RAC_LEGACY_ROOT")
    component("hy3d21.runner_exact", legacy_root, "scripts/run_hy3d21_pbr.py",
              ("texture",), "RAC_LEGACY_ROOT", PAINT_HASH)
    component("workflow.hy3d_final_cut", ROOT, "workflows/geometry/comfyui/hy3d_final_cut.json",
              (), "repository")
    component("comfy.node.Hunyuan3DWrapper", comfy_root, "custom_nodes/ComfyUI-Hunyuan3DWrapper",
              (), "RAC_COMFY_ROOT")
    add("wsl", shutil.which("wsl"), (), "Optional texture challengers")
    add("nvidia-smi", shutil.which("nvidia-smi"), ("geometry", "texture"),
        "Required by inference launch guards; GPU ownership is checked at launch")
    for identifier, script, prefix in (
        ("auto_rig_pro.operational", "preflight_arp.py", "RAC_ARP_PREFLIGHT_JSON="),
        ("autoremesher.operational", "preflight_autoremesher.py", "RAC_AUTOREMESHER_PREFLIGHT_JSON="),
    ):
        available, detail = False, "Optional probe skipped for this profile"
        if profile == "all" and probe_addons and blender and blender.is_file():
            available, detail = probe_addon(blender, script, prefix)
        add(identifier, available, (), detail)
    missing = [c["id"] for c in checks if c["required"] and not c["available"]]
    return {"schema": "reference-asset-compiler.workflow-doctor.v1",
            "timestamp": datetime.now(timezone.utc).isoformat(), "profile": profile,
            "ok": not missing, "required_missing": missing, "inference_launched": False,
            "checks": checks, "routing": {
                "geometry": "guarded direct Hunyuan single-view or multiview runner",
                "texture": "Hunyuan3D-Paint 2.1 existing-mesh runner",
                "comfyui": "optional historical geometry workflow",
                "rigging": "landmark rig or optional Auto-Rig Pro; downstream gates remain",
                "post_authority": "compiler scripts and UE5 verification"}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="all")
    parser.add_argument("--legacy-root")
    parser.add_argument("--comfy-root")
    parser.add_argument("--blender")
    parser.add_argument("--unreal-cmd")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skip-addon-probes", action="store_true")
    args = parser.parse_args(argv)
    report = collect(args.profile, args.legacy_root, args.comfy_root, args.blender,
                     args.unreal_cmd, not args.skip_addon_probes)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for check in report["checks"]:
            mark = "OK" if check["available"] else "MISSING" if check["required"] else "OPTIONAL"
            print(f"[{mark}] {check['id']} -- {check['detail']}")
        print("WORKFLOW_DOCTOR_OK -- the selected route has its keys; no inference launched."
              if report["ok"] else "WORKFLOW_DOCTOR_INCOMPLETE -- missing: "
              + ", ".join(report["required_missing"]))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
