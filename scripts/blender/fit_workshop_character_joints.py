"""Source-bound Ayric rig repair; never edits the accepted mesh or textures.

The generic centreline fit included coat panels and guessed a closed hand on
an open glove. Explicit anatomical anchors replace those guesses. Depth is
measured from the actual surface around each anchor. These are rig pivots,
not newly sculpted geometry, and remain candidates pending deformation review.
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

def main():
    source, old, dest = map(Path, sys.argv[sys.argv.index('--')+1:])
    if dest.exists():
        raise RuntimeError('Refusing to overwrite a joint candidate')
    data=json.loads(old.read_text())
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != data['payload_fbx_sha256']:
        raise RuntimeError('Landmarks do not belong to this mesh')
    bpy.ops.import_scene.fbx(filepath=str(source))
    points=np.array([tuple(o.matrix_world@v.co) for o in bpy.context.scene.objects if o.type=='MESH' for v in o.data.vertices])
    joints=data['joints']
    measured=[]

    def surface_depth(x,z,radius=.025):
        d=(points[:,0]-x)**2+(points[:,2]-z)**2
        selected=points[d<radius**2]
        if len(selected)<4:
            selected=points[np.argsort(d)[:12]]
        return float((np.quantile(selected[:,1],.1)+np.quantile(selected[:,1],.9))*.5)

    # Metre-space anchors fitted against the actual 1.85 m mesh front and side.
    anchors={'lowerarm':(.307,1.245),'hand':(.418,1.035),
             'thigh':(.115,1.00),'calf':(.170,.545)}
    digits={
        'thumb':[(.494,.987),(.534,.995),(.562,1.002),(.584,1.009)],
        'index':[(.508,.905),(.559,.876),(.599,.857),(.628,.842)],
        'middle':[(.482,.884),(.515,.830),(.545,.787),(.566,.760)],
        'ring':[(.455,.880),(.467,.816),(.483,.761),(.492,.727)],
        'pinky':[(.429,.897),(.417,.835),(.407,.781),(.399,.743)]}
    for side,sign in [('l',1),('r',-1)]:
        for name,(x,z) in anchors.items():
            # Hips use the torso depth, not a loose coat flap in front of it.
            y=float(joints['pelvis'][1]) if name=='thigh' else surface_depth(sign*x,z)
            joints[name+'_'+side]=[sign*x,y,z]
            measured.append(name+'_'+side)
        wrist=np.array(joints['hand_'+side])
        for digit,chain in digits.items():
            for index,(x,z) in enumerate(chain):
                suffix=f'{index+1:02d}' if index<3 else 'tip'
                joints[f'{digit}_{suffix}_{side}']=[sign*x,surface_depth(sign*x,z,.018),z]
            if digit!='thumb':
                joints[f'{digit}_metacarpal_{side}']=(wrist*.55+np.array(joints[f'{digit}_01_{side}'])*.45).tolist()
        joints['hand_end_'+side]=joints['middle_01_'+side]
        for base,a,b in [('upperarm','upperarm','lowerarm'),('lowerarm','lowerarm','hand'),('thigh','thigh','calf'),('calf','calf','foot')]:
            start=np.array(joints[a+'_'+side])
            end=np.array(joints[b+'_'+side])
            for n,fraction in [(1,1/3),(2,2/3)]:
                joints[f'{base}_twist_{n:02d}_{side}']=(start+(end-start)*fraction).tolist()
        for kind,bone in [('hand','hand'),('foot','foot')]:
            joints[f'ik_{kind}_{side}']=joints[bone+'_'+side]
            joints[f'ik_{kind}_{side}_end']=(np.array(joints[bone+'_'+side])+[0,0,.0925]).tolist()
    joints['ik_hand_gun']=joints['hand_r']
    joints['ik_hand_gun_end']=(np.array(joints['hand_r'])+[0,0,.0925]).tolist()
    data.update(method='Explicit source-bound anatomical XZ anchors; local surface depth; reconstructed finger and twist pivots; unchanged mesh',
                corrected_from=str(old.resolve()),corrected_from_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
                reviewed_by=None,review_status='candidate_pending_deformation_and_native_review',
                notes=['Hip pivots moved out of coat panels; wrists moved to cuffs; splayed glove digits fitted individually.',
                       'Agent-selected rig landmarks, not human-approved production evidence.'])
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,indent=2)+'\n')
    print('RAC_JOINT_CANDIDATE '+str(dest)+' -- hips belong in trousers, not the coat rack.')

if __name__=='__main__':
    main()
