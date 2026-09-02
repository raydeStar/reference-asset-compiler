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
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rac_env  # noqa: E402
from reference_asset_compiler.approvals import validate_modeling_approval  # noqa: E402
from reference_asset_compiler.io import read_json  # noqa: E402
from reference_asset_compiler.workspace import promote_stage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

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
BLENDER = rac_env.find_blender()

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


def blender(script, *script_args, quiet=True):
    command = [str(BLENDER), "-b", "--factory-startup", "--python",
               str(ROOT / "scripts" / "blender" / script), "--"]
    command += [str(a) for a in script_args]
    done = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
    text = done.stdout + "\n" + done.stderr
    lines = [ln for ln in text.splitlines()
             if ln.startswith("[") or "Error" in ln or "Traceback" in ln
             or ln.strip().startswith("File \"")]
    if not quiet or done.returncode != 0:
        print("\n".join(lines[-25:]))
    return done.returncode, lines


def material_slots(fbx):
    """Material names on the mesh, via a throwaway Blender read."""
    probe = ROOT / "scripts" / "blender" / "_list_materials.py"
    probe.write_text(PROBE, encoding="utf-8")
    try:
        _, lines = blender("_list_materials.py", fbx)
        return [ln.split(" ", 1)[1] for ln in lines if ln.startswith("[SLOT] ")]
    finally:
        probe.unlink(missing_ok=True)


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
    src = ROOT / "out" / asset / (asset + ".fbx")
    work = ROOT / "work" / asset
    prod = work / "prod-v2"
    profile = work / "resolved-profile.json"
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
    prod.mkdir(parents=True, exist_ok=True)
    result = {"asset": asset, "source": str(src), "out_dir": str(prod)}
    manifest_path = ROOT / "out" / asset / (asset + ".ue5import.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    reduction = manifest.get("production_reduction") or {}
    prebuilt_low = Path(reduction["candidate"]) if reduction.get("candidate") else None
    prebuilt_args = []
    if reduction:
        modeling_candidate = prebuilt_low or src
        fixed_views = Path(reduction.get("fixed_views") or "")
        try:
            approval = validate_modeling_approval(work, modeling_candidate, fixed_views)
        except (OSError, KeyError, ValueError) as error:
            print("[BUILD] {0}: fixed views lack valid human modeling approval: {1}".format(
                asset, error))
            return {**result, "ok": False, "stage": "modeling-approval"}
        result["modeling_approval"] = approval
    if prebuilt_low:
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
        limits = json.loads(profile.read_text(encoding="utf-8")).get(
            "texture_limits", {})
        min_density = float(limits.get("min_texel_density_per_cm2", 0.0) or 0.0)

    mapping, unmatched = build_texmap(asset, src, prod / "texmap.json")
    result["texmap"] = mapping
    result["materials_without_texture"] = unmatched
    if unmatched:
        print("[BUILD] {0}: flat-coloured materials, baked from their own "
              "base colour: {1}".format(asset, ", ".join(unmatched)))

    # Blender exits 0 even when the script it was handed raised, so a crashed
    # stage looks like a successful one and the next step happily reads the
    # report left behind by the PREVIOUS run. That is how a build that died on
    # an UnboundLocalError reported PASS with stale numbers. Delete the report
    # first and require it back.
    report_path = prod / "retopo.json"
    if report_path.exists():
        report_path.unlink()

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
        code, lines = blender(
            "retopo_bake.py", src, prod, prod / "retopo.json",
            "--budget", candidate, "--resolution", args.resolution,
            "--samples", args.samples, "--texmap", prod / "texmap.json",
            "--strategy", STRATEGY.get(asset, args.strategy),
            "--settle-props", SETTLE_PROPS.get(asset, ""),
            "--preserve-props", PRESERVE_PROPS.get(asset, ""),
            "--close-holes", "yes" if CLOSE_HOLES.get(asset) else "",
            "--kind", asset_kind(asset),
            "--min-density", min_density,
            *prebuilt_args)
        for line in lines:
            if line.startswith("[RETOPO]"):
                print("   " + line)
        if code != 0 or not report_path.exists():
            break
        trial = json.loads(report_path.read_text(encoding="utf-8"))
        drift = (trial.get("deviation") or {}).get("p99_m")
        attempts.append({"budget": candidate, "tris": trial.get("low_tris"),
                         "deviation_p99_m": drift,
                         "reduced": trial.get("reduced")})
        if best is None or (drift is not None
                            and (best[1] is None or drift < best[1])):
            best = (candidate, drift)
            for name in ("retopo.json",):
                (prod / (name + ".best")).write_bytes(report_path.read_bytes())
        if not trial.get("reduced"):
            break
    result["budget_attempts"] = attempts

    # Rebuild at the winner if the last run was not it.
    if best is not None and attempts and attempts[-1]["budget"] != best[0]:
        print("[BUILD] {0}: {1} measured closest ({2}m); rebuilding".format(
            asset, best[0], best[1]))
        code, lines = blender(
            "retopo_bake.py", src, prod, prod / "retopo.json",
            "--budget", best[0], "--resolution", args.resolution,
            "--samples", args.samples, "--texmap", prod / "texmap.json",
            "--strategy", STRATEGY.get(asset, args.strategy),
            "--settle-props", SETTLE_PROPS.get(asset, ""),
            "--preserve-props", PRESERVE_PROPS.get(asset, ""),
            "--close-holes", "yes" if CLOSE_HOLES.get(asset) else "",
            "--kind", asset_kind(asset),
            "--min-density", min_density,
            *prebuilt_args)
        for line in lines:
            if line.startswith("[RETOPO]"):
                print("   " + line)
    for stale in prod.glob("*.best"):
        stale.unlink()
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
    result["retopo"] = json.loads(report_path.read_text(encoding="utf-8"))

    retopo_fbx = prod / (asset + "_retopo.fbx")
    shipped = prod / (asset + "_production.fbx")
    baked = result["retopo"]["baked"]
    blender("apply_production_material.py", retopo_fbx,
            prod / baked["BaseColor"], prod / baked.get("Normal", "none.png"),
            prod / baked.get("AO", "none.png"),
            prod / baked.get("Roughness", "none.png"),
            prod / baked.get("Metallic", "none.png"), shipped)
    result["shipped"] = str(shipped)

    # --- gates, the same ones the source asset already passes ---------------
    blender("export_uv_regions.py", retopo_fbx, prod / "uv-regions.npz")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gate_texture.py"),
         str(prod / "uv-regions.npz"), str(prod / baked["BaseColor"]),
         str(profile), str(prod / "gate-tex.json"),
         "--material-name", "M_Retopo"],
        cwd=str(ROOT), capture_output=True, text=True)
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
            resolved = json.loads(profile.read_text(encoding="utf-8"))
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
    else:
        blender("gate_rig.py", shipped, profile, prod / "gate-rig.json")
        blender("deform_test.py", shipped, prod / "deform", prod / "deform.json")

    for name in ("gate-tex", "gate-rig", "deform"):
        path = prod / (name + ".json")
        if path.exists():
            result[name] = json.loads(path.read_text(encoding="utf-8"))

    if not args.skip_render:
        blender("render_turnaround.py", shipped, prod / "turn", 900)
        # The close-up frames a sphere around a named bone. A prop has none,
        # and the turnaround already covers it at this size.
        if asset_kind(asset) != "static_prop":
            blender("render_closeup.py", shipped, prod / "closeup", "head", 0.30,
                    "beauty,matcap", "0,35")

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
    if result["ok"] and (work / "state.json").is_file():
        state = read_json(work / "state.json")
        baked_paths = [prod / value for value in result["retopo"].get("baked", {}).values()]
        stage_evidence = {
            "semantic_cleanup": [report_path],
            "production_retopology": [report_path, retopo_fbx],
            "unwrap_and_bake": [report_path, prod / "gate-tex.json", shipped, *baked_paths],
        }
        for stage, evidence in stage_evidence.items():
            status = state["stages"][stage]["status"]
            if status == "pending":
                state = promote_stage(
                    work,
                    stage,
                    evidence,
                    "Automated mechanical gate passed; human visual gates remain separate.",
                    "build_production.py",
                )
            elif status != "passed":
                result["ok"] = False
                result["stage"] = stage
                result["failure"] = "workspace stage is {0}".format(status)
                break
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets", nargs="+")
    parser.add_argument("--budget", type=int, default=12000)
    parser.add_argument("--resolution", type=int, default=4096)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--strategy", default="auto", choices=("auto", "region", "passthrough"))
    parser.add_argument("--no-sweep", action="store_true",
                        help="use the given budget instead of trying double it")
    args = parser.parse_args()

    summary = []
    for asset in args.assets:
        built = build(asset, args)
        if built is None:
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
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("[BUILD] summary -> {0}".format(out))
    return 0 if summary and all(b["ok"] for b in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
