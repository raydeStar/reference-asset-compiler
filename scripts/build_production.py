"""Build the game-ready version of an accepted asset, and gate it.

The accepted assets in out/ are generated-and-repaired meshes: 70k triangles of
near-uniform density, no normal map, and a UV atlas of 300-900 tiny islands.
They are correct likenesses and bad game assets. This stage keeps the likeness
and fixes the rest -- heal, quad remesh, semantic UV charts weighted toward the
face, bake the existing art down onto the result, then re-run every gate the
source asset already passes so a regression cannot ship quietly.

Nothing here generates art. The albedo is the accepted albedo, resampled.

Usage:
  python scripts/build_production.py <asset> [<asset> ...]
      [--budget 12000] [--resolution 4096] [--samples 24] [--skip-render]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rac_env  # noqa: E402
from reference_asset_compiler.approvals import validate_modeling_approval  # noqa: E402
from reference_asset_compiler.io import read_json, sha256_file  # noqa: E402
from reference_asset_compiler.evidence import record_evidence_paths, stage_receipt  # noqa: E402
from reference_asset_compiler.texture_payload import bind_texture_payload  # noqa: E402
from reference_asset_compiler.workspace import audit_workspace, promote_stage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sha256 = sha256_file


def load_json(path):
    """Receipts written by the PowerShell launchers may carry a UTF-8 BOM."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def clear_outputs(*paths):
    """Delete the per-run files a stage is about to rewrite, and nothing else.

    A stage that crashes leaves no report behind -- and the driver must then
    notice, rather than read the report of the previous run. Only the outputs
    the SAME call regenerates are removed; retained evidence is never touched.
    """
    for path in paths:
        path = Path(path)
        if path.is_file():
            path.unlink()


def missing_outputs(*paths):
    return [str(path) for path in paths if not Path(path).is_file()]

# Strategy per asset, where visual review overrides what the gates allow.
#
# ninja-man passes every automated gate as a retopology -- 54,220 -> 28,704
# triangles -- and his head comes out as flat grey tiles. He heals into 24
# shells, so QuadriFlow refuses him whole and the per-shell budget cuts the
# 22,000-face shell his head sits inside by 4.8x. Budget sweeps, seam angles,
# ray lengths, a bake cage and a per-region split were all tried and are
# recorded in docs/EXPERIMENT-retopo-ninja.md. None recovered the head, so he
# keeps his geometry and his UVs and takes the rest of the stage: ambient
# occlusion, and a weight clamp that matters because UE5 silently truncates
# his eight influences to four.
# fox-mascot is passthrough for a different reason, and it is the more useful
# one: quad remeshing suits a smooth silhouette and not a spiky one. His ears,
# whisker spikes and brow tufts are thin protrusions a uniform quad field
# cannot hold, so he comes out visibly faceted at any budget -- 4.6mm from the
# original at 12,000 quads, 2.7mm at 24,000, 7.5mm at 36,000, and choppy at all
# three. Removing his normal map was tried, in case the faceting was shading
# rather than shape; it changed nothing, which is what settled it. His
# authority is 69,545 triangles because he needs them.
# fox-mascot is NOT passthrough, though he should be.
#
# Quad remeshing suits a smooth silhouette and not a spiky one. His ears,
# whisker spikes and brow tufts are thin protrusions a uniform quad field
# cannot hold, so he comes out faceted at any budget -- 4.6mm from the
# original at 12,000 quads, 2.7mm at 24,000, 7.5mm at 36,000, and choppy at
# all three. Removing his normal map was tried in case the faceting was
# shading rather than shape; it changed nothing, which settled it.
#
# Passthrough restores his geometry exactly, and on him ALONE it also
# brightens the baked albedo 3.35x -- 20.9% of texels clip, where the source
# has none above 240. The same path is faithful for field-scout-male (0.95x)
# and ninja-man (1.03x), so it is something about this character and not the
# path. Until that is understood he ships remeshed at the budget that
# measured closest, because a faceted fox beats a blown-out one.
STRATEGY = {"ninja-man": "passthrough"}

# Prop shells that are meant to be seated INSIDE the surface they sit in, and
# on this character are not. field-scout-male's eyeballs are modelled 6 cm
# proud of his face: head on they line up over the sockets and read correctly,
# and from three-quarters the far one clears the bridge of his nose and hangs
# in open air beside his cheek.
#
# This is opt-in per asset on purpose. The geometric description -- a small
# shell sitting outside the body it belongs to -- fits ninja-man's shoulder
# plates and fox-mascot's flat eye decals just as well, and both of those are
# correct where they are. Sinking them would be the compiler inventing a defect.
# The distance is not configured here; the compiler measures the smallest
# setback that stops the assembly breaking the head's silhouette, and records
# it in the report.
SETTLE_PROPS = {"field-scout-male": "eye"}

# Geometry to hold out of the remesh and put back untouched. fox-mascot's eyes
# are four flat plates stacked 5 mm apart in front of orange fur; QuadriFlow
# absorbs them into the head, and the bake then has to pick between surfaces a
# fraction of a millimetre apart and picks wrongly in patches -- brown wedges
# bitten out of his eyes. They are 248 triangles of flat colour and there is
# nothing to gain by remeshing them.
PRESERVE_PROPS = {"fox-mascot": "eye"}

# Characters whose remesh should be sealed before it is unwrapped. fox-mascot's
# head keeps 181 boundary edges through the heal, in a crescent around each eye
# socket, and you can see into his skull through them.
#
# Not the default. An open boundary loop is not always a defect -- it is how
# field-scout-male's eyelid aperture is modelled, and capping that would seal
# his eyes inside his head.
CLOSE_HOLES = {"fox-mascot": True}

# Assets that are not characters. A static prop goes through the same stage --
# heal, unwrap, bake, package -- with every step that reads a skeleton removed:
# no weight transfer, no influence cap, no semantic charts cut at body regions,
# no rig gate and no deformation suite. That is the contract in
# tests/test_planner.py::test_static_prop_never_enters_rigging, not a shortcut.
def asset_kind(asset):
    """humanoid or static_prop, taken from the asset rather than a table here.

    The kind is declared once, in the recipe, and carried into
    out/<asset>/<asset>.ue5import.json by intake. Reading it back means a new
    prop needs a recipe and nothing else -- keeping a hard-coded list here
    would mean every asset anyone else compiles requires editing this file,
    and the failure when they forget is "need a mesh and an armature" several
    minutes into a build.
    """
    manifest = ROOT / "out" / asset / (asset + ".ue5import.json")
    if manifest.exists():
        try:
            declared = json.loads(manifest.read_text(encoding="utf-8-sig")).get(
                "asset_kind")
        except (ValueError, OSError):
            declared = None
        if declared:
            return declared
    return "humanoid"
# Resolved rather than hard-coded: see scripts/rac_env.py. A path that is
# right on one machine is what makes a repo unrunnable on every other.
BLENDER = None

PROBE = (
    "import bpy, sys\n"
    "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
    "bpy.ops.import_scene.fbx(filepath=sys.argv[sys.argv.index(chr(45)*2)+1])\n"
    "o = max([x for x in bpy.data.objects if x.type == 'MESH'],\n"
    "        key=lambda x: len(x.data.polygons))\n"
    "for s in o.material_slots:\n"
    "    if s.material:\n"
    "        print('[SLOT]', s.material.name)\n"
)


def normalise(name):
    """M_FieldScoutFemale_Body and T_FieldScoutFemaleBody_BaseColor agree here."""
    for prefix in ("M_", "T_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    for suffix in ("_BaseColor", "_ORM", "_Normal"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.replace("_", "").replace("-", "").lower()


def blender(script, *script_args, quiet=True, timeout=None, outputs=()):
    """Run one Blender stage and return (returncode, interesting lines).

    `outputs` are the files this call is expected to (re)write. They are
    deleted first and required back afterwards; a missing one is reported as
    a non-zero code even when Blender itself exited 0.
    """
    clear_outputs(*outputs)
    code, stdout, stderr = rac_env.run_blender(
        script, *script_args, blender=BLENDER, timeout=timeout, cwd=ROOT)
    text = stdout + "\n" + stderr
    lines = [ln for ln in text.splitlines()
             if ln.startswith("[") or "Error" in ln or "Traceback" in ln
             or ln.strip().startswith("File \"")]
    missing = missing_outputs(*outputs) if code == 0 else []
    if missing:
        code = 1
        lines.append("[BUILD] {0} exited 0 without writing: {1}".format(
            script, ", ".join(missing)))
    if not quiet or code != 0:
        print("\n".join(lines[-25:]))
    return code, lines


def material_slots(fbx):
    """Material names on the mesh, via a throwaway Blender read."""
    with tempfile.TemporaryDirectory(prefix="rac-material-probe-") as temporary:
        probe = Path(temporary) / "list_materials.py"
        probe.write_text(PROBE, encoding="utf-8")
        code, lines = blender(probe, fbx, timeout=rac_env.BLENDER_STEP_TIMEOUT)
        if code != 0:
            raise RuntimeError("material probe failed with exit {0}".format(code))
        return [ln.split(" ", 1)[1] for ln in lines if ln.startswith("[SLOT] ")]


def build_texmap(asset, fbx, out_path):
    """Map each material to the accepted BaseColor it should be baked from."""
    textures = {normalise(p.stem): p for p in
                (ROOT / "out" / asset / "textures").glob("*_BaseColor.png")}
    mapping, unmatched = {}, []
    for name in material_slots(fbx):
        hit = textures.get(normalise(name))
        if hit is None:
            # Do NOT fall back to "the only texture there is". The eye
            # materials are flat-coloured and have no texture on disk, and
            # handing them the body atlas bakes fur onto the eyeballs.
            # retopo_bake reads their base colour off the material instead.
            unmatched.append(name)
        else:
            mapping[name] = str(hit).replace("\\", "/")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    return mapping, unmatched


def build(asset, args):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", asset):
        raise ValueError("Asset id must be a lowercase slug, not a filesystem path")
    src = ROOT / "out" / asset / (asset + ".fbx")
    work = ROOT / "work" / asset
    production_name = getattr(args, "production_name", "prod-v2")
    if not re.fullmatch(r"prod-[a-z0-9]+(?:-[a-z0-9]+)*", production_name):
        raise ValueError("Production name must be a local prod-* directory name")
    prod = work / production_name
    if prod.exists():
        raise ValueError("Refusing to overwrite retained production attempt: {0}. "
                         "Choose a new --production-name prod-* directory.".format(prod))
    profile = work / "resolved-profile.json"
    published_profile = ROOT / "out" / asset / "resolved-profile.json"
    if published_profile.is_file():
        profile = published_profile
    if asset_kind(asset) == "static_prop" and not profile.exists():
        # The humanoid intake resolves a skeleton profile per asset and folds
        # in that asset's waivers. A prop has no skeleton to resolve, but the
        # texture gate still reads its limits from a profile, so give it one.
        work.mkdir(parents=True, exist_ok=True)
        profile.write_bytes(
            (ROOT / "profiles" / "skeletons" / "static_prop.json").read_bytes())
    if not src.exists():
        print("[BUILD] {0}: no source at {1}".format(asset, src))
        return None
    result = {"asset": asset, "source": str(src), "out_dir": str(prod)}
    manifest_path = ROOT / "out" / asset / (asset + ".ue5import.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    reduction = manifest.get("production_reduction") or {}
    prebuilt_low = Path(reduction["candidate"]) if reduction.get("candidate") else None
    prebuilt_args = []
    ledgered = (work / "state.json").is_file()
    if ledgered:
        audit = audit_workspace(work)
        if not audit["ok"]:
            raise ValueError("Workspace audit failed: " + "; ".join(audit["failures"]))
        state = read_json(work / "state.json")
        receipt = stage_receipt(work, state, "production_retopology",
                                "reference-asset-compiler.production-retopology.v1")
        prebuilt_low = next((path for path in record_evidence_paths(
            work, state["stages"]["production_retopology"])
            if sha256(path) == receipt["output_mesh_sha256"]), None)
        if prebuilt_low is None:
            raise ValueError("Approved production retopology mesh is missing")
        if state["stages"]["unwrap_and_bake"]["status"] != "pending":
            raise ValueError("unwrap_and_bake is already recorded; use a new asset id")
        prebuilt_args = ["--prebuilt-low", prebuilt_low]
        result["approved_retopology_sha256"] = receipt["output_mesh_sha256"]
    elif reduction:
        modeling_candidate = prebuilt_low or src
        fixed_views = Path(reduction.get("fixed_views") or "")
        try:
            approval = validate_modeling_approval(work, modeling_candidate, fixed_views)
        except (OSError, KeyError, ValueError) as error:
            print("[BUILD] {0}: fixed views lack valid human modeling approval: {1}".format(
                asset, error))
            return {**result, "ok": False, "stage": "modeling-approval"}
        result["modeling_approval"] = approval
    if prebuilt_low and not ledgered:
        if not prebuilt_low.is_file():
            print("[BUILD] {0}: declared reduction candidate missing at {1}".format(
                asset, prebuilt_low))
            return {**result, "ok": False, "stage": "reduction-authority"}
        if reduction.get("status") != "mechanical_pass":
            print("[BUILD] {0}: reduction candidate has not passed its mechanical gate".format(
                asset))
            return {**result, "ok": False, "stage": "reduction-authority"}
        expected_hash = reduction.get("candidate_sha256")
        actual_hash = sha256(prebuilt_low)
        if not expected_hash or actual_hash.lower() != expected_hash.lower():
            print("[BUILD] {0}: reduction candidate hash drifted; expected {1}, got {2}".format(
                asset, expected_hash, actual_hash))
            return {**result, "ok": False, "stage": "reduction-authority"}
        prebuilt_args = ["--prebuilt-low", prebuilt_low]
        result["production_reduction"] = reduction

    # The atlas must not be stepped down below what the texture gate will then
    # demand of it, so the stage is told the floor rather than guessing.
    min_density = 0.0
    if profile.exists():
        limits = load_json(profile).get("texture_limits", {})
        min_density = float(limits.get("min_texel_density_per_cm2", 0.0) or 0.0)

    try:
        prod.mkdir(parents=True)
        mapping, unmatched = build_texmap(asset, src, prod / "texmap.json")
    except RuntimeError as error:
        print("[BUILD] {0}: {1}".format(asset, error))
        return {**result, "ok": False, "stage": "material-probe", "failure": str(error)}
    result["texmap"] = mapping
    result["materials_without_texture"] = unmatched
    if unmatched:
        print("[BUILD] {0}: flat-coloured materials, baked from their own "
              "base colour: {1}".format(asset, ", ".join(unmatched)))

    # Without `--python-exit-code 1` Blender exits 0 even when the script it
    # was handed raised, so a crashed stage looks like a successful one and
    # the next step happily reads the report left behind by the PREVIOUS run.
    # That is how a build that died on an UnboundLocalError reported PASS with
    # stale numbers. Every call below passes the flag through rac_env, deletes
    # its own report first, and requires it back.
    report_path = prod / "retopo.json"
    clear_outputs(report_path)

    # Try a couple of budgets and keep whichever lands closest to the original.
    #
    # More triangles is NOT reliably better: fox-mascot measures 4.6mm from
    # his original at 12,000 quads, 2.7mm at 24,000, and 7.5mm at 36,000.
    # QuadriFlow's quad field is not monotonic in the target, so the budget
    # cannot be tuned by feedback -- an earlier attempt to do exactly that
    # failed, and failed twice over because the metric was nearest-VERTEX
    # distance, which mostly reports how densely the original happens to be
    # sampled. Point-to-surface distance is honest, so a short sweep works
    # where a loop did not.
    #
    # The sweep stops early when the first attempt reverts to passthrough,
    # since a character that is not being remeshed has no budget to tune.
    candidates = ([args.budget] if args.no_sweep or prebuilt_low
                  else [args.budget, args.budget * 2])
    attempts, best = [], None
    for candidate in candidates:
        print("[BUILD] {0}: retopologising at {1}".format(asset, candidate))
        trial_dir = prod / ("budget-" + str(candidate))
        trial_dir.mkdir()
        trial_report = trial_dir / "retopo.json"
        code, lines = blender(
            "retopo_bake.py", src, trial_dir, trial_report,
            "--budget", candidate, "--resolution", args.resolution,
            "--samples", args.samples, "--texmap", prod / "texmap.json",
            "--strategy", STRATEGY.get(asset, args.strategy),
            "--settle-props", SETTLE_PROPS.get(asset, ""),
            "--preserve-props", PRESERVE_PROPS.get(asset, ""),
            "--close-holes", "yes" if CLOSE_HOLES.get(asset) else "",
            "--kind", asset_kind(asset),
            "--min-density", min_density,
            *prebuilt_args, outputs=(trial_report,))
        for line in lines:
            if line.startswith("[RETOPO]"):
                print("   " + line)
        if code != 0 or not trial_report.exists():
            return {**result, "ok": False, "stage": "retopo",
                    "failure": "Retopology failed; attempt retained, no automatic retry",
                    "budget_attempts": attempts}
        trial = load_json(trial_report)
        if trial.get("ok") is not True:
            return {**result, "ok": False, "stage": "retopo",
                    "failure": "Retopology report did not pass", "budget_attempts": attempts}
        drift = (trial.get("deviation") or {}).get("p99_m")
        attempts.append({"budget": candidate, "tris": trial.get("low_tris"),
                         "deviation_p99_m": drift,
                         "reduced": trial.get("reduced")})
        if best is None or (drift is not None
                            and (best[1] is None or drift < best[1])):
            best = (candidate, drift, trial_dir)
        if not trial.get("reduced"):
            break
    result["budget_attempts"] = attempts

    # Keep every trial and copy the measured winner; a second bake is new evidence.
    if best is not None:
        for path in best[2].iterdir():
            destination = prod / path.name
            if path.is_dir():
                shutil.copytree(path, destination)
            else:
                shutil.copy2(path, destination)
    crashed = [ln for ln in lines if "Traceback" in ln or "Error" in ln]
    if code != 0 or not report_path.exists() or crashed:
        result["ok"] = False
        result["stage"] = "retopo"
        result["failure"] = ("retopo produced no report"
                             if not report_path.exists() else "; ".join(crashed[:3]))
        print("[BUILD] {0}: retopo FAILED -- {1}".format(asset, result["failure"]))
        for line in lines[-12:]:
            print("   " + line)
        return result
    result["retopo"] = load_json(report_path)

    retopo_fbx = prod / (asset + "_retopo.fbx")
    shipped = prod / (asset + "_production.fbx")
    baked = result["retopo"]["baked"]

    def failed(stage, code, lines):
        result["ok"] = False
        result["stage"] = stage
        result["failure"] = "{0} exited {1}".format(stage, code)
        print("[BUILD] {0}: {1} FAILED (exit {2})".format(asset, stage, code))
        for line in lines[-12:]:
            print("   " + line)
        return result

    code, lines = blender(
        "apply_production_material.py", retopo_fbx,
        prod / baked["BaseColor"], prod / baked.get("Normal", "none.png"),
        prod / baked.get("AO", "none.png"),
        prod / baked.get("Roughness", "none.png"),
        prod / baked.get("Metallic", "none.png"), shipped,
        timeout=rac_env.BLENDER_STEP_TIMEOUT, outputs=(shipped,))
    if code != 0:
        return failed("apply-material", code, lines)
    result["shipped"] = str(shipped)

    # --- gates, the same ones the source asset already passes ---------------
    regions = prod / "uv-regions.npz"
    code, lines = blender("export_uv_regions.py", retopo_fbx, regions,
                          timeout=rac_env.BLENDER_STEP_TIMEOUT, outputs=(regions,))
    if code != 0:
        return failed("export-uv-regions", code, lines)
    gate_tex = prod / "gate-tex.json"
    clear_outputs(gate_tex)
    # The texture gate exits non-zero when the texture FAILS the gate, and the
    # report then carries the reasons; only a missing report is a crash.
    gate_run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gate_texture.py"),
         str(regions), str(prod / baked["BaseColor"]),
         str(profile), str(gate_tex),
         "--material-name", "M_Retopo"],
        cwd=str(ROOT), capture_output=True, encoding="utf-8", errors="replace",
        timeout=rac_env.BLENDER_STEP_TIMEOUT)
    if not gate_tex.is_file() or gate_run.returncode not in (0, 1):
        return failed("gate-texture", gate_run.returncode,
                      (gate_run.stdout + "\n" + gate_run.stderr).splitlines())
    texture_gate = load_json(gate_tex)
    if gate_run.returncode != 0 and texture_gate.get("ok") is True:
        return failed("gate-texture", gate_run.returncode,
                      ["A failed process cannot certify a passing gate."])
    if asset_kind(asset) == "static_prop":
        # No skeleton to compare against a profile and no deformation to
        # exercise. Recording them as skipped rather than absent keeps the
        # summary honest -- a missing key and a passed gate look identical once
        # they are both falsy.
        #
        # The triangle budget is NOT skippable, and skipping it was an accident:
        # it is enforced inside gate_rig, so removing the rig gate removed the
        # budget with it. A generated chair passed every remaining check at
        # 971,442 triangles against a declared budget of 20,000, because nothing
        # left was looking. Check it here instead, with the same waiver rule the
        # rig gate uses.
        budget = None
        waiver = None
        if profile.exists():
            resolved = load_json(profile)
            budget = resolved.get("tri_budget")
            waiver = resolved.get("tri_budget_waiver")
        tris = (result.get("retopo") or {}).get("low_tris")
        over = budget is not None and tris is not None and tris > budget
        result["gate-rig"] = {
            "ok": (not over) or bool(waiver),
            "skipped": "static prop has no skeleton",
            "tri_budget": budget,
            "tris": tris,
            "tri_budget_waiver": waiver,
            "failures": ([] if (not over) or waiver else [
                "{0} triangles against a budget of {1}. Reduce it, or record a "
                "tri_budget_waiver naming a reason and an approver.".format(
                    tris, budget)]),
        }
        if over and not waiver:
            print("[BUILD] {0}: {1} triangles against a budget of {2}".format(
                asset, tris, budget))
        result["deform"] = {"ok": True, "skipped": "static prop does not deform"}
        for name in ("gate-rig", "deform"):
            (prod / (name + ".json")).write_text(json.dumps(result[name]), encoding="utf-8")
    else:
        gate_rig = prod / "gate-rig.json"
        code, lines = blender("gate_rig.py", shipped, profile, gate_rig,
                              timeout=rac_env.BLENDER_STEP_TIMEOUT, outputs=(gate_rig,))
        if code != 0:
            return failed("gate-rig", code, lines)
        deform_report = prod / "deform.json"
        code, lines = blender("deform_test.py", shipped, prod / "deform", deform_report,
                              timeout=rac_env.BLENDER_STEP_TIMEOUT, outputs=(deform_report,))
        if code != 0:
            return failed("deform", code, lines)

    for name in (("gate-tex",) if asset_kind(asset) == "static_prop"
                 else ("gate-tex", "gate-rig", "deform")):
        path = prod / (name + ".json")
        if path.exists():
            result[name] = load_json(path)

    if not args.skip_render:
        code, lines = blender("render_turnaround.py", shipped, prod / "turn", 900,
                              timeout=rac_env.BLENDER_STEP_TIMEOUT)
        if code != 0:
            return failed("render-turnaround", code, lines)
        # The close-up frames a sphere around a named bone. A prop has none,
        # and the turnaround already covers it at this size.
        if asset_kind(asset) != "static_prop":
            code, lines = blender("render_closeup.py", shipped, prod / "closeup", "head", 0.30,
                                  "beauty,matcap", "0,35", timeout=rac_env.BLENDER_STEP_TIMEOUT)
            if code != 0:
                return failed("render-closeup", code, lines)

    # The bake must have reached the UV islands. A texel the rays never hit
    # keeps the pass fill, and for BaseColor that fill is black -- which is
    # how ninja-man shipped a head that looked like its texture had been
    # destroyed when the geometry was fine. The texture gate already measures
    # island coverage, so compare the two.
    islands = result.get("gate-tex", {}).get("uv_islands", {}).get("coverage_pct")
    hit = result.get("retopo", {}).get("bake_coverage_pct", {}).get("BaseColor")
    result["bake_reached_islands"] = None
    if islands and hit is not None:
        result["bake_reached_islands"] = round(hit / islands, 3)
        if hit < 0.9 * islands:
            print("[BUILD] {0}: bake reached only {1}% of the sheet against "
                  "{2}% of it covered by UV islands".format(asset, hit, islands))

    result["ok"] = bool(
        result.get("retopo", {}).get("ok")
        and result.get("gate-rig", {}).get("ok")
        and result.get("gate-tex", {}).get("ok")
        and result.get("deform", {}).get("ok", True)
        and (result["bake_reached_islands"] is None
             or result["bake_reached_islands"] >= 0.9))
    result["retopo"] = bind_texture_payload(
        result["retopo"], prebuilt_low or retopo_fbx, shipped, gate_tex)
    report_path.write_text(json.dumps(result["retopo"], indent=2) + "\n", encoding="utf-8")
    if result["ok"] and ledgered:
        baked_paths = [prod / value for value in result["retopo"].get("baked", {}).values()]
        promote_stage(
            work, "unwrap_and_bake",
            [report_path, gate_tex, prebuilt_low, shipped, *baked_paths],
            "Baked the reviewed retopology; texture approval remains a separate human gate.",
            "build_production.py",
        )
    return result


def main() -> int:
    global BLENDER
    parser = argparse.ArgumentParser()
    parser.add_argument("assets", nargs="+")
    parser.add_argument("--budget", type=int, default=12000)
    parser.add_argument("--resolution", type=int, default=4096)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--production-name", default="prod-v2",
                        help="New retained prod-* attempt directory; existing attempts are refused")
    parser.add_argument("--strategy", default="auto", choices=("auto", "region", "passthrough"))
    parser.add_argument("--no-sweep", action="store_true",
                        help="use the given budget instead of trying double it")
    parser.add_argument("--blender", type=Path)
    args = parser.parse_args()
    BLENDER = args.blender or rac_env.find_blender()

    summary = []
    for asset in args.assets:
        try:
            built = build(asset, args)
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
            built = {"asset": asset, "ok": False, "failure": str(error)}
            print("[BUILD] {0}: {1}; retained evidence stays put.".format(asset, error))
        if built is None:
            summary.append({"asset": asset, "ok": False, "failure": "source missing"})
            continue
        summary.append(built)
        retopo = built.get("retopo", {})
        rig = built.get("gate-rig", {})
        tex = built.get("gate-tex", {})
        print("[BUILD] {0}: {1} -> {2} tris | rig {3} | tex {4} | {5}".format(
            asset, retopo.get("high_tris"), retopo.get("low_tris"),
            "ok" if rig.get("ok") else rig.get("failures"),
            "ok" if tex.get("ok") else tex.get("failures"),
            "PASS" if built["ok"] else "FAIL"))

    out = ROOT / "work" / "production-summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("[BUILD] summary -> {0}".format(out))
    return 0 if summary and all(b["ok"] for b in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
