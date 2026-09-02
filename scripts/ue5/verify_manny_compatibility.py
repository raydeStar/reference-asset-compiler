"""Compare every compiled skeleton against the REAL Manny skeleton.

Runs headless inside the editor:

  UnrealEditor-Cmd.exe <project>.uproject \
      -ExecutePythonScript="<this file>" -unattended -nop4 -nosplash -stdout

The manifests claim "direct compatibility with the UE5 Manny animation
ecosystem". That has only ever been checked against a hand-written profile in
this repo, which is worth exactly as much as whoever typed it. Epic's
animations are bound to `SK_Mannequin`, so that is the thing to match.

`unreal.Skeleton` exposes no bone accessor to Python in 5.8 -- the import
verifier already works around that by reading asset-registry tags -- and
headless FBX export of a skeletal mesh fails, so neither of the obvious routes
works. A spawned SkeletalMeshComponent does expose bones, so the meshes are
spawned into the transient editor world and read there.

Writes `work/manny-compatibility.json`.
"""

from __future__ import annotations

import json
import os

import unreal

ROOT = os.environ.get("RAC_ROOT")
if not ROOT:
    unreal.log_error("RAC_ROOT is not set")
    raise SystemExit(1)

# SK_Mannequin is the SKELETON asset; the mesh is SKM_Manny_Simple. Loading
# the wrong one fails deep inside a property conversion, which reads as a
# Python type error rather than "that is not a mesh".
MANNY_CANDIDATES = ("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
                    "/Game/Characters/Mannequins/Meshes/SKM_Manny",
                    "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple")


def bones_of(asset_path):
    """Bone names in skeleton order, via a temporary actor."""
    mesh = unreal.EditorAssetLibrary.load_asset(asset_path)
    if mesh is None:
        return None, "asset not found"
    actor = None
    try:
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.SkeletalMeshActor, unreal.Vector(0.0, 0.0, 0.0))
        component = actor.skeletal_mesh_component
        for setter in ("set_skeletal_mesh_asset", "set_skeletal_mesh"):
            if hasattr(component, setter):
                getattr(component, setter)(mesh)
                break
        else:
            return None, "no way to assign the mesh to a component"
        count = component.get_num_bones()
        return [str(component.get_bone_name(i)) for i in range(count)], None
    except Exception as error:  # noqa: BLE001 - report, never abort the batch
        return None, str(error)
    finally:
        if actor is not None:
            unreal.EditorLevelLibrary.destroy_actor(actor)


report = {"engine_version": unreal.SystemLibrary.get_engine_version(),
          "assets": []}

manny_bones, error, MANNY = None, "none of the candidates loaded", None
for candidate in MANNY_CANDIDATES:
    bones, why = bones_of(candidate)
    if bones:
        manny_bones, error, MANNY = bones, None, candidate
        break
report["manny"] = MANNY
report["manny_bone_count"] = len(manny_bones) if manny_bones else None
report["manny_error"] = error
unreal.log("RAC Manny bones: {0} ({1})".format(
    len(manny_bones) if manny_bones else None, error))

registry = unreal.AssetRegistryHelpers.get_asset_registry()
for data in registry.get_assets_by_path("/Game/Compiled", recursive=True):
    if str(data.asset_class_path.asset_name) != "SkeletalMesh":
        continue
    path = str(data.package_name)
    bones, error = bones_of(path)
    entry = {"asset": path, "bone_count": len(bones) if bones else None,
             "error": error}
    if manny_bones and bones:
        manny_set, ours = set(manny_bones), set(bones)
        entry["missing_from_manny"] = sorted(manny_set - ours)
        entry["extra_beyond_manny"] = sorted(ours - manny_set)
        entry["covers_manny"] = not entry["missing_from_manny"]
        entry["order_matches"] = [b for b in bones if b in manny_set] == [
            b for b in manny_bones if b in ours]
    report["assets"].append(entry)
    unreal.log("RAC {0}: {1} bones, covers Manny = {2}, missing {3}".format(
        path, entry["bone_count"], entry.get("covers_manny"),
        len(entry.get("missing_from_manny") or [])))

out = os.path.join(ROOT, "work", "manny-compatibility.json")
with open(out, "w") as handle:
    json.dump(report, handle, indent=2)
unreal.log("RAC wrote {0}".format(out))
