"""Import an isolated rig derivative and retarget complete limb/palm chains.

Reuses the existing character's exact material, without promoting its pending
texture gate. New skeletal, animation, blueprint and level packages only.
"""
import json
import os
import sys
from pathlib import Path

import unreal

ROOT=Path(os.environ['RAC_ROOT'])
sys.path.insert(0,str(ROOT/'scripts/ue5'))
import import_asset  # noqa: E402  (RAC_ROOT path injected above)
import swap_workshop_player as swap  # noqa: E402  (RAC_ROOT path injected above)

def qmul(a,b):
    x,y,z,w=a
    X,Y,Z,W=b
    return (w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z)

def qi(q):
    n=sum(x*x for x in q)
    return (-q[0]/n,-q[1]/n,-q[2]/n,q[3]/n)

def qt(q):
    return (q.x,q.y,q.z,q.w)

def qrotate(q,v):
    a=qmul(qmul(q,(v.x,v.y,v.z,0)),qi(q))
    return unreal.Vector(*a[:3])

def retarget_pose(mesh,controller=None):
    def collect(c):
        poses={}
        for i in range(c.get_num_bones()):
            name=str(c.get_bone_name(i))
            parent=str(c.get_parent_bone(name))
            ref=c.get_socket_transform(name,unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE)
            offset=qt(controller.get_rotation_offset_for_retarget_pose_bone(name,unreal.RetargetSourceOrTarget.TARGET)) if controller else (0,0,0,1)
            local=qmul(qt(ref.rotation),offset)
            if parent in poses:
                p=poses[parent]
                pos=p['p']+qrotate(p['q'],ref.translation*p['scale'])
                rot=qmul(p['q'],local)
                scale=p['scale']*ref.scale3d.x
            else:
                pos=ref.translation
                rot=local
                scale=ref.scale3d.x
            poses[name]={'p':pos,'q':rot,'scale':scale,'local':qt(ref.rotation),'parent':parent}
        return poses
    return swap.with_probe(mesh,collect)

def frame(pose,side):
    forward=pose['middle_01_'+side]['p']-pose['hand_'+side]['p']
    across=pose['index_01_'+side]['p']-pose['pinky_01_'+side]['p']
    return qt(unreal.MathLibrary.make_rot_from_xy(forward,across).quaternion())

original_build=swap.build_retargeter

def build_retargeter(name,source_rig,target_rig,source_mesh,target_mesh):
    retargeter,notes=original_build(name,source_rig,target_rig,source_mesh,target_mesh)
    controller=unreal.IKRetargeterController.get_controller(retargeter)
    source=retarget_pose(source_mesh)
    for side in ['l','r']:
        target=retarget_pose(target_mesh,controller)
        hand='hand_'+side
        delta=qmul(frame(source,side),qi(frame(target,side)))
        desired=qmul(delta,target[hand]['q'])
        parent=target[target[hand]['parent']]['q']
        offset=qmul(qi(target[hand]['local']),qmul(qi(parent),desired))
        controller.set_rotation_offset_for_retarget_pose_bone(hand,unreal.Quat(*offset),unreal.RetargetSourceOrTarget.TARGET)
        notes.append('Anatomical palm frame aligned using wrist/middle/index/pinky landmarks: '+side)
    fingers=[f'{digit}_{joint}_{side}' for side in ['l','r'] for digit in ['thumb','index','middle','ring','pinky'] for joint in ['metacarpal','01','02'] if not (digit=='thumb' and joint=='metacarpal')]
    controller.auto_align_bones(fingers,unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN,unreal.RetargetSourceOrTarget.TARGET)
    notes.append('Finger and twist chains mapped; finger retarget-pose directions aligned after palms.')
    root_index=controller.add_retarget_op('/Script/IKRig.IKRetargetRootMotionOp')
    root_controller=controller.get_op_controller(root_index)
    root_controller.set_source_root_bone('root')
    root_controller.set_target_root_bone('root')
    root_controller.set_target_pelvis_bone('pelvis')
    notes.append('Root motion separated before export; stripped ancestor track gives in-place capsule-driven locomotion.')
    unreal.EditorAssetLibrary.save_loaded_asset(retargeter)
    return retargeter,notes

def main():
    folder='/Game/SunsetWorkshop/RigRepairs/'+os.environ.get('RAC_RIG_VERSION','anatomical_v002')
    reuse=os.environ.get('RAC_REUSE_RIG_MESH')
    if not reuse and unreal.EditorAssetLibrary.does_directory_exist(folder):
        raise RuntimeError('Rig import destination exists; refusing overwrite')
    fbx=ROOT/'work/sunset-ayric-v2/rig/anatomical-v002/ayric_rigged.fbx'
    manifest=json.loads((ROOT/'out/sunset-ayric-v2-production/sunset-ayric-v2-production.ue5import.json').read_text(encoding='utf-8-sig'))
    if not reuse:
        task=import_asset.build_skeletal_task(str(fbx),folder,manifest)
        task.replace_existing=False
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh_path=reuse or import_asset.find_skeletal_mesh(folder)
    mesh=unreal.load_asset(mesh_path)
    old=unreal.load_asset('/Game/Compiled/SunsetAyricV2Production/sunset-ayric-v2-production')
    material=old.get_editor_property('materials')[0].material_interface
    if not reuse:
        import_asset.assign_materials(mesh_path,{},material)
        import_asset.build_lods(mesh_path,manifest['lods'])
    if abs(mesh.get_bounds().box_extent.z*2-185)>1:
        raise RuntimeError('Imported rig height changed')
    swap.TARGET_MESH=mesh_path
    for side,title in [('l','Left'),('r','Right')]:
        for digit in ['thumb','index','middle','ring','pinky']:
            start=f'{digit}_01_{side}' if digit=='thumb' else f'{digit}_metacarpal_{side}'
            swap.CHAINS[title+digit.title()]=(start,(f'{digit}_03_{side}',))
        for limb in ['upperarm','lowerarm','thigh','calf']:
            for n in ['01','02']:
                bone=f'{limb}_twist_{n}_{side}'
                swap.CHAINS[bone]=(bone,(bone,))
    swap.build_retargeter=build_retargeter
    swap.main()

if __name__=='__main__':
    main()
