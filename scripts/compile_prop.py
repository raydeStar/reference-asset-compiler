"""Intake a static prop: stage its textures, normalize it, publish the authority.

The humanoid intake is `scripts/compile_asset.ps1`, and it is a skeleton
pipeline from end to end -- it resolves a bone profile, gates the rig, and runs
a deformation suite. A prop has none of those, and bolting a "kind" switch onto
every stage of it would make the humanoid path harder to read in exchange for
sharing about twenty lines of texture staging.

So this is the prop half, and it is deliberately short:

  1. Copy each material's textures next to where the FBX will be written, under
     the names that ship. Before the export, not after, so the FBX can carry a
     relative reference to the exact files beside it.
  2. Normalize scale, origin and material names, and join the parts.
  3. Leave the result in out/<asset>/ as the authority the compiler builds from.

What it does NOT do is any rigging stage, which is the whole point:
`tests/test_planner.py::test_static_prop_never_enters_rigging` is the contract.

Usage:
  python scripts/compile_prop.py recipes/office-chair.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rac_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Resolved rather than hard-coded: see scripts/rac_env.py. A path that is
# right on one machine is what makes a repo unrunnable on every other.
BLENDER = rac_env.find_blender()


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", re.sub(r"^M_", "", name))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    args = parser.parse_args()

    recipe = rac_env.expand_tree(json.loads(args.recipe.read_text(encoding="utf-8-sig")))
    if recipe.get("kind") != "static_prop":
        print("[PROP] {0} is kind '{1}'; this driver only compiles static "
              "props".format(args.recipe, recipe.get("kind")))
        return 1

    asset = recipe["asset_id"]
    work = ROOT / "work" / asset
    out = ROOT / "out" / asset
    textures = out / "textures"
    textures.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    # Staged under the shipped name, keyed by material, so normalize_prop can
    # build each material against the file that will sit beside the FBX.
    # Stage under the material's FINAL name, not the one it had in the source
    # file. The FBX carries the renamed materials, and the build stage matches
    # textures to materials by name -- stage them as T_Material0_BaseColor.png
    # and the build reports the material as untextured and bakes its flat
    # colour instead, which is a grey asset and no error anywhere.
    renames = recipe.get("normalize", {}).get("material_renames", {})
    texture_map, shipped = {}, {}
    for source_material, slots in recipe.get("material_textures", {}).items():
        material = renames.get(source_material, source_material)
        texture_map[material] = {}
        for slot, source in slots.items():
            source_path = Path(source)
            if not source_path.exists():
                print("[PROP] FAILED: {0} texture for {1} missing at {2}".format(
                    slot, material, source_path))
                return 1
            name = "T_{0}_{1}.png".format(slug(material), slot)
            destination = textures / name
            shutil.copyfile(source_path, destination)
            texture_map[material][slot] = str(destination)
            shipped[name] = str(source_path)
    map_path = work / "texture-map.json"
    map_path.write_text(json.dumps(texture_map, indent=2), encoding="utf-8")
    print("[PROP] staged {0} textures for {1} materials".format(
        len(shipped), len(texture_map)))

    out_fbx = out / (asset + ".fbx")
    report = work / "normalize-prop-report.json"
    command = [str(args.blender), "-b", "--factory-startup", "--python",
               str(ROOT / "scripts" / "blender" / "normalize_prop.py"), "--",
               str(args.recipe.resolve()), str(out_fbx), str(report),
               str(map_path)]
    done = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
    for line in done.stdout.splitlines():
        if line.startswith("[NORMALIZE]"):
            print("   " + line)
    # Blender exits 0 even when the script it was handed raised, so the report
    # coming back is the only proof the stage ran.
    if done.returncode != 0 or not report.exists():
        print("[PROP] FAILED: normalize did not produce {0}".format(report))
        for line in done.stderr.splitlines()[-20:]:
            print("   " + line)
        return 1

    measured = json.loads(report.read_text(encoding="utf-8"))
    manifest = {
        "asset_id": asset,
        "asset_kind": "static_prop",
        "articulation": "static",
        # Keyed the way every other manifest in out/ is keyed, because the UE5
        # importer reads them all the same way and a prop that spells the mesh
        # key differently is simply skipped -- with one log line, in the middle
        # of a successful-looking import of everything else.
        "fbx": out_fbx.name,
        "ue5_mesh_type": "StaticMesh",
        "materials": sorted(texture_map),
        "textures": {
            material: {
                slot: {
                    "file": "textures/{0}".format(Path(path).name),
                    "settings": {"compression": "TC_Default", "sRGB": True,
                                 "flip_green": False},
                }
                for slot, path in slots.items()
            }
            for material, slots in texture_map.items()
        },
        "measurements": {
            "height_m": measured["after"]["height_m"],
            "height_cm_in_ue5": round(measured["after"]["height_m"] * 100.0, 1),
            "total_tris": measured["after"]["tris"],
        },
        "height_m": measured["after"]["height_m"],
        "triangles": measured["after"]["tris"],
        "ue5_import": {
            "import_as_skeletal": False,
            # The FBX is written in metres and Unreal works in centimetres, and
            # convert_scene handles that from the file's own unit header -- the
            # characters import at uniform scale 1 the same way. A prop that
            # arrives a hundred times too small or too large is almost always
            # this pair being set to compensate for each other.
            "import_uniform_scale": 1,
            "convert_scene": True,
            "force_front_x_axis": False,
            "normal_import_method": "ImportNormals",
            "generate_collision": True,
            "collision_note": "Auto convex from the mesh. A five-spoke base is "
                              "not convex, so the hull bridges between the "
                              "spokes; for something you walk into rather than "
                              "roll under, that is the right trade."
        },
        "lods": [
            {"lod": 0, "percent_triangles": 1, "screen_size": 1, "source": "imported"},
            {"lod": 1, "percent_triangles": 0.5, "screen_size": 0.4,
             "source": "ue5_reduction"},
            {"lod": 2, "percent_triangles": 0.25, "screen_size": 0.15,
             "source": "ue5_reduction"},
        ],
        "source_authority": measured["source_authority"],
        "reference_authority": recipe["source"].get("reference_authority"),
    }
    (out / (asset + ".ue5import.json")).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print("[PROP] {0}: {1} tris, {2:.3f} m -> {3}".format(
        asset, manifest["triangles"], manifest["height_m"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
