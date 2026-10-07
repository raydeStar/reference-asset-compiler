"""Dump Manny's reference pose and sample animation poses from a local UE project.

Run headless with the editor closed:
  UnrealEditor-Cmd.exe <project>.uproject -run=pythonscript -script="dump_manny_reference.py <out_dir>"

Writes manny_refpose.json (89 bones: parent, component-space position in cm,
rotation quaternion xyzw) and manny_anim_poses.json (component-space and local
rotations for a few clips). This is Epic's content: keep the dumps in work/,
never commit them. fit_ue5_manny_rig.py and pose_ue5_anim_test.py read them.
"""
import json
import os
import sys

import unreal

MESH = '/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple'
CLIPS = {'MM_Idle': [0.5], 'MF_Unarmed_Jog_Fwd': [0.1, 0.35], 'MM_Jump': [0.3], 'MM_Attack_01': [0.25, 0.5],
         'MM_Fall_Loop': [0.2], 'MM_Dash': [0.2]}

out_dir = [a for a in sys.argv[1:] if not a.startswith('-')][0]
os.makedirs(out_dir, exist_ok=True)
mesh = unreal.load_asset(MESH)
actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
    unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), transient=True)
comp = actor.skeletal_mesh_component
comp.set_skeletal_mesh_asset(mesh)
bones = []
for i in range(comp.get_num_bones()):
    n = comp.get_bone_name(i)
    t = comp.get_socket_transform(n, unreal.RelativeTransformSpace.RTS_COMPONENT)
    parent = str(comp.get_parent_bone(n))
    bones.append({'name': str(n), 'parent': None if parent == 'None' else parent,
                  'pos': [t.translation.x, t.translation.y, t.translation.z],
                  'quat': [t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w]})
actor.destroy_actor()
with open(os.path.join(out_dir, 'manny_refpose.json'), 'w') as f:
    json.dump({'schema': 'rac.ue-refpose.v1', 'source': MESH, 'skeleton': mesh.get_editor_property('skeleton').get_path_name(),
               'space': 'UE component space, cm, quat xyzw', 'bones': bones}, f, indent=1)

registry = unreal.AssetRegistryHelpers.get_asset_registry()
found = {}
for data in registry.get_assets_by_path('/Game/Characters/Mannequins/Anims', recursive=True):
    if str(data.asset_class_path.asset_name) == 'AnimSequence' and str(data.asset_name) in CLIPS:
        found.setdefault(str(data.asset_name), str(data.package_name))
options = unreal.AnimPoseEvaluationOptions()
options.optional_skeletal_mesh = mesh
names = [b['name'] for b in bones]
poses = []
for name, path in sorted(found.items()):
    anim = unreal.load_asset(path)
    for fraction in CLIPS[name]:
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(anim, fraction * anim.get_play_length(), options)
        sample = {}
        for n in names:
            t = unreal.AnimPoseExtensions.get_bone_pose(pose, n, unreal.AnimPoseSpaces.WORLD)
            local = unreal.AnimPoseExtensions.get_bone_pose(pose, n, unreal.AnimPoseSpaces.LOCAL)
            sample[n] = {'pos': [t.translation.x, t.translation.y, t.translation.z],
                         'quat': [t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w],
                         'lquat': [local.rotation.x, local.rotation.y, local.rotation.z, local.rotation.w]}
        poses.append({'anim': name, 'path': path, 'time': fraction * anim.get_play_length(), 'bones': sample})
with open(os.path.join(out_dir, 'manny_anim_poses.json'), 'w') as f:
    json.dump({'found': found, 'poses': poses}, f)
unreal.log('Manny reference written to ' + out_dir)
