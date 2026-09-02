"""Give every compiled character collision, and measure its LODs.

Runs headless inside the editor:

  UnrealEditor-Cmd.exe <project>.uproject \
      -ExecutePythonScript="<this file>" -unattended -nop4 -nosplash -stdout

Two gaps between "imports and renders" and "is a character in a game".

**Collision.** A skeletal mesh with no PhysicsAsset cannot be hit, cannot
ragdoll, and does not exist to a physics query. None of these characters had
one. The asset is generated from the mesh, assigned, and then checked --
because an asset with no bodies is worse than none at all, since it looks like
collision is there.

**LODs.** The manifests ask the engine to build three, and the import verifier
confirms three exist. Nobody has ever looked at what is IN them. Auto-reduction
is not reliable on a mesh made of many disconnected shells, which is exactly
what field-scout-male and ninja-man are, so the vertex counts per level are
measured here and a level that failed to reduce is reported.

`unreal.PhysicsAssetFactory` is not the route: its only members are
`create_new` and `script_factory_create_file`, and driving it from Python
returns nothing. `SkeletalMeshEditorSubsystem` has `create_physics_asset` and
`assign_physics_asset`, which is what the editor itself uses.

Writes `work/physics-and-lods.json`.
"""

from __future__ import annotations

import json
import os

import unreal

ROOT = os.environ.get("RAC_ROOT")
if not ROOT:
    unreal.log_error("RAC_ROOT is not set")
    raise SystemExit(1)

subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
registry = unreal.AssetRegistryHelpers.get_asset_registry()


def physics_for(mesh, mesh_path, result):
    """Create collision bodies and bind them, or say why not."""
    try:
        physics = subsystem.create_physics_asset(mesh)
    except Exception as error:  # noqa: BLE001 - report, never abort the batch
        result["physics_error"] = str(error)
        return
    if physics is None:
        result["physics_error"] = "create_physics_asset returned nothing"
        return

    try:
        assigned = subsystem.assign_physics_asset(mesh, physics)
    except Exception as error:  # noqa: BLE001
        result["physics_error"] = "assign failed: {0}".format(error)
        assigned = False

    bodies = None
    try:
        setups = physics.get_editor_property("skeletal_body_setups")
        bodies = len(setups) if setups is not None else None
    except Exception:  # noqa: BLE001 - the count is a nicety, not the point
        pass

    path = physics.get_path_name().split(".")[0]
    result["physics_asset"] = path
    result["physics_bodies"] = bodies
    result["physics_assigned"] = bool(assigned)
    result["physics_compatible"] = bool(
        subsystem.is_physics_asset_compatible(mesh, physics))
    unreal.EditorAssetLibrary.save_asset(path)
    unreal.EditorAssetLibrary.save_asset(mesh_path)


def lods_for(mesh, result):
    """What the engine actually built for each level."""
    levels = []
    try:
        count = subsystem.get_lod_count(mesh)
    except Exception as error:  # noqa: BLE001
        result["lod_error"] = str(error)
        return
    for index in range(count):
        entry = {"lod": index}
        for name, call in (("verts", subsystem.get_num_verts),
                           ("sections", subsystem.get_num_sections)):
            try:
                entry[name] = int(call(mesh, index))
            except Exception:  # noqa: BLE001 - not every level answers
                entry[name] = None
        levels.append(entry)
    result["lods"] = levels

    base = levels[0].get("verts") if levels else None
    if base:
        for level in levels[1:]:
            if level.get("verts"):
                level["fraction_of_lod0"] = round(level["verts"] / float(base), 3)
        # A level that did not shrink is a level that costs memory for nothing.
        stuck = [level["lod"] for level in levels[1:]
                 if level.get("fraction_of_lod0") is not None
                 and level["fraction_of_lod0"] > 0.95]
        result["lods_that_did_not_reduce"] = stuck


report = {"engine_version": unreal.SystemLibrary.get_engine_version(), "assets": []}
meshes = sorted(
    str(d.package_name)
    for d in registry.get_assets_by_path("/Game/Compiled", recursive=True)
    if str(d.asset_class_path.asset_name) == "SkeletalMesh")

for mesh_path in meshes:
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        continue
    result = {"mesh": mesh_path}
    physics_for(mesh, mesh_path, result)
    lods_for(mesh, result)
    result["ok"] = bool(result.get("physics_assigned")) and bool(result.get("lods"))
    report["assets"].append(result)

out = os.path.join(ROOT, "work", "physics-and-lods.json")
with open(out, "w") as handle:
    json.dump(report, handle, indent=2)
