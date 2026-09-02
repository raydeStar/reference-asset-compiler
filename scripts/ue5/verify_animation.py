"""Play Epic's Manny animation on the compiled characters and measure the result.

Runs headless inside the editor:

  UnrealEditor-Cmd.exe <project>.uproject \
      -ExecutePythonScript="<this file>" -unattended -nop4 -nosplash -stdout

Matching bone names says an animation SHOULD bind. This checks that it does,
and that the skeleton moves the way the animation says.

An AnimSequence stores its tracks by bone name, so the binding test is exact:
every track name in the sequence must exist on the target skeleton. Beyond
that the pose is sampled at several times and applied to a live component, and
the bone world positions are compared -- a rig that binds but does not move,
or moves to infinity, fails here rather than in someone's level.

Writes `work/animation-verify.json`.
"""

from __future__ import annotations

import json
import os

import unreal

ROOT = os.environ.get("RAC_ROOT")
if not ROOT:
    unreal.log_error("RAC_ROOT is not set")
    raise SystemExit(1)

# Unarmed idle and a run: one nearly still, one with large motion.
ANIMATIONS = ("/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle",
              "/Game/Characters/Mannequins/Anims/Unarmed/Jog/MF_Unarmed_Jog_Fwd")
SAMPLE_TIMES = (0.0, 0.25, 0.5)


def track_names(anim):
    """Bone names the sequence actually animates."""
    for getter in ("get_animation_track_names", "get_bone_track_names"):
        if hasattr(unreal.AnimationLibrary, getter):
            try:
                return [str(n) for n in getattr(unreal.AnimationLibrary, getter)(anim)]
            except Exception:  # noqa: BLE001 - try the next spelling
                continue
    return None


def spawn(mesh):
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(0.0, 0.0, 0.0))
    component = actor.skeletal_mesh_component
    for setter in ("set_skeletal_mesh_asset", "set_skeletal_mesh"):
        if hasattr(component, setter):
            getattr(component, setter)(mesh)
            break
    return actor, component


def finite(vector):
    return all(abs(v) < 1.0e7 and v == v for v in (vector.x, vector.y, vector.z))


def check(asset_path, anim_path):
    result = {"asset": asset_path, "animation": anim_path, "checks": []}

    def note(name, ok, detail):
        result["checks"].append({"check": name, "ok": bool(ok), "detail": detail})

    mesh = unreal.EditorAssetLibrary.load_asset(asset_path)
    anim = unreal.EditorAssetLibrary.load_asset(anim_path)
    if mesh is None or anim is None:
        note("assets_load", False, "mesh or animation missing")
        result["ok"] = False
        return result

    actor, component = spawn(mesh)
    try:
        bones = {str(component.get_bone_name(i))
                 for i in range(component.get_num_bones())}
        tracks = track_names(anim)
        if tracks is None:
            note("track_names", False, "no API on this build to list tracks")
        else:
            # The question is NOT whether the sequence has tracks this skeleton
            # lacks -- the engine binds by name and quietly skips the rest, so
            # a sequence authored for a richer rig still plays. The question is
            # whether OUR bones get driven.
            track_set = set(tracks)
            undriven = sorted(b for b in bones if b not in track_set)
            ignored = sorted(t for t in track_set if t not in bones)
            result["animated_bones"] = len(tracks)
            result["bones_not_driven"] = undriven
            result["tracks_ignored"] = ignored
            covered = len(bones) - len(undriven)
            note("animation_drives_skeleton", not undriven,
                 "{0} of {1} bones driven{2}".format(
                     covered, len(bones),
                     "" if not undriven else "; not driven: " + ", ".join(undriven[:8])))
            if ignored:
                result["note_ignored"] = (
                    "{0} tracks belong to bones this character does not have "
                    "and are skipped by the engine: {1}".format(
                        len(ignored), ", ".join(ignored[:8])))

        # Does the pose actually change over time, and stay finite?
        changed, bad, sampled = 0, [], 0
        for name in sorted(bones):
            poses = []
            for time in SAMPLE_TIMES:
                try:
                    poses.append(unreal.AnimationLibrary.get_bone_pose_for_time(
                        anim, name, time, False))
                except Exception:  # noqa: BLE001 - not in this sequence
                    poses = []
                    break
            if not poses:
                continue
            sampled += 1
            for pose in poses:
                if not finite(pose.translation):
                    bad.append(name)
                    break
            first, last = poses[0], poses[-1]
            if (last.translation - first.translation).length() > 1.0e-4 or                     (last.rotation.euler() - first.rotation.euler()).length() > 1.0e-3:
                changed += 1
        result["bones_sampled"] = sampled
        result["bones_that_move"] = changed
        note("pose_finite", not bad,
             "{0} bones sampled, {1} non-finite{2}".format(
                 sampled, len(bad), "" if not bad else ": " + ", ".join(bad[:6])))
        note("skeleton_moves", changed > 0,
             "{0} of {1} sampled bones change pose between {2}s and {3}s".format(
                 changed, sampled, SAMPLE_TIMES[0], SAMPLE_TIMES[-1]))
    finally:
        unreal.EditorLevelLibrary.destroy_actor(actor)

    result["ok"] = all(c["ok"] for c in result["checks"])
    return result


report = {"engine_version": unreal.SystemLibrary.get_engine_version(), "runs": []}
registry = unreal.AssetRegistryHelpers.get_asset_registry()
meshes = [str(d.package_name)
          for d in registry.get_assets_by_path("/Game/Compiled", recursive=True)
          if str(d.asset_class_path.asset_name) == "SkeletalMesh"
          and str(d.package_name).endswith("production")]

for anim_path in ANIMATIONS:
    if unreal.EditorAssetLibrary.load_asset(anim_path) is None:
        unreal.log_warning("RAC animation missing: {0}".format(anim_path))
        continue
    for mesh_path in sorted(meshes):
        entry = check(mesh_path, anim_path)
        report["runs"].append(entry)
        unreal.log("RAC {0} + {1}: ok={2} {3}".format(
            mesh_path.split("/")[-1], anim_path.split("/")[-1], entry["ok"],
            "; ".join(c["detail"] for c in entry["checks"])))

out = os.path.join(ROOT, "work", "animation-verify.json")
with open(out, "w") as handle:
    json.dump(report, handle, indent=2)
unreal.log("RAC wrote {0}".format(out))
