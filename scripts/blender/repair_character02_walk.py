# SPDX-License-Identifier: MIT
"""Calibrated Character02 walk: moderate swing, rolling support and coupled pelvis IK.

Immutable source and packet; CPU authoring. Existing upper-body performance and
all other clips survive. Artistic acceptance is always separate from these checks.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from reference_asset_compiler.animation_calibration import align_segment_rotation


def smooth(u):
    u = np.clip(u, 0., 1.)
    return u*u*(3-2*u)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['source', 'packet', 'anim-tools', 'game-tools', 'out']:
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--lift-cm', type=float, default=5.)
    p.add_argument('--support-fraction', type=float, default=.60)
    p.add_argument('--cadence', type=float, default=1.8, help='Steps per second; stride and markers follow the resampled cycle.')
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    for key in ['source','packet','anim_tools','game_tools','out']:
        setattr(args, key, getattr(args, key).resolve())
    assert 2 <= args.lift_cm <= 8 and .53 <= args.support_fraction <= .65
    args.out.mkdir(parents=True, exist_ok=False)
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    original = json.loads(args.packet.read_text())
    assert sha(args.source) == original['provenance']['character_blend_sha256']
    sys.path[:0] = [str(args.anim_tools), str(args.game_tools)]
    import clip_retarget as cr
    import transition_clips as tc
    from CheckLocomotionClearance import matrix, deform
    from CheckLocomotionFooting import boot_data
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    rig = cr.TargetRig(next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE'))
    ix, inverse = rig.index, np.linalg.inv(rig.rest)
    legs, boots = tc.Legs(rig), boot_data(rig.obj)
    library_path = Path(original['provenance']['libraries']['ual1']['path'])
    library = cr.UalLibrary(library_path)
    reference = library.reference()
    mapping = json.loads(Path(original['provenance']['profile'][0]).read_text())['bone_map']
    retarget = cr.Retarget(rig, library, mapping)
    calibration = []
    for side in 'lr':
        for parent, child in [('thigh','calf'), ('calf','foot'), ('foot','ball')]:
            a, b = f'{parent}_{side}', f'{child}_{side}'
            direction = rig.rest[ix[b],:3,3] - rig.rest[ix[a],:3,3]
            source_direction = retarget.A @ (reference[b][:3,3]-reference[a][:3,3])
            corrected = align_segment_rotation(rig.rest[ix[a],:3,:3], direction, source_direction)
            retarget.tgt_ref[ix[a]] = corrected
            if parent == 'foot':
                retarget.tgt_ref[ix[b]] = corrected @ rig.rest[ix[a],:3,:3].T @ rig.rest[ix[b],:3,:3]
            calibration.append({'bone':a,'target_segment':direction.tolist(),
                'source_segment':source_direction.tolist(),'world_reference_rotation':corrected.tolist()})
    data = copy.deepcopy(original)
    name = 'MF_Unarmed_Walk_Fwd'
    clip = data['clips'][name]
    old_duration=(clip['frames']-1)/clip['fps']
    old_left=clip['contacts_s']['l']
    old_local=[np.array([matrix(clip['tracks'][n][f]) for n in rig.names]) for f in range(clip['frames'])]
    frames=round(2/args.cadence*clip['fps'])+1
    assert 1.5 <= args.cadence <= 2.1
    clip['frames']=frames
    clip['length']=(frames-1)/clip['fps']
    clip['tracks']={n:[] for n in original['bones']}
    for f in range(frames):
        at=(len(old_local)-1)*f/(frames-1)
        lo=min(int(at),len(old_local)-2)
        local=tc.blend_local(old_local[lo],old_local[lo+1],at-lo)
        for i,n in enumerate(rig.names):
            clip['tracks'][n].append([float(v) for v in cr.ue_from_matrix(local[i])])
    duration, speed = (clip['frames']-1)/clip['fps'], clip['speed_cm_s']/100
    support = duration * args.support_fraction
    contacts = {'l':old_left/old_duration*duration, 'r':(old_left/old_duration*duration+duration/2)%duration}
    def fk(c, f):
        return tc.fk(rig, np.array([matrix(c['tracks'][n][f]) for n in rig.names]))
    idle = fk(data['clips']['MM_Idle'], 0)
    pelvis = ix['pelvis']
    family = [pelvis]+[ix[b.name] for b in rig.obj.data.bones['pelvis'].children_recursive]
    leg_names = set()
    for s in 'lr':
        leg_names.add(f'thigh_{s}')
        leg_names.update(b.name for b in rig.obj.data.bones[f'thigh_{s}'].children_recursive)
    def points(w, side):
        return np.concatenate([deform(mesh,w@inverse)[ids[side]] for _,mesh,ids in boots if ids[side]])
    neutral = {}
    for s in 'lr':
        foot = idle[ix['foot_'+s]]
        verts = points(idle,s)
        sole = verts[verts[:,2] < verts[:,2].min()+.009]
        heel, toe = sole[np.argmax(sole[:,1])], sole[np.argmin(sole[:,1])]
        neutral[s] = {'rotation':foot[:3,:3], 'toe':np.linalg.inv(foot)@idle[ix['ball_'+s]],
            'heel_local':foot[:3,:3].T@(heel-foot[:3,3]),
            'toe_local':foot[:3,:3].T@(toe-foot[:3,3]),
            'x':float(foot[0,3]), 'z':float(foot[2,3]),
            'centre_y':float(idle[ix['thigh_'+s],1,3])}
    def path(s,t):
        at = (t-contacts[s])%duration
        q = at/support
        # The flat support segment travels backwards at the measured capsule speed.
        low, high = neutral[s]['centre_y']-speed*support/2, neutral[s]['centre_y']+speed*support/2
        if at <= support:
            y = low+speed*at
            pitch = -4*(1-smooth(q/.16)) if q<.16 else 18*smooth((q-.70)/.30)
            lift = .002
        else:
            u=(at-support)/(duration-support)
            # Cubic Hermite matches the support velocity at both swing boundaries.
            h00,h10,h01,h11=2*u**3-3*u*u+1,u**3-2*u*u+u,-2*u**3+3*u*u,u**3-u*u
            y=h00*high+h10*(duration-support)*speed+h01*low+h11*(duration-support)*speed
            pitch = 18-22*smooth(u/.60)
            lift = .002+args.lift_cm/100*math.sin(math.pi*u)**2
        r=np.array(Matrix.Rotation(math.radians(pitch),3,'X'))@neutral[s]['rotation']
        pivot=neutral[s]['heel_local'] if pitch<0 else neutral[s]['toe_local']
        rolling=neutral[s]['rotation']@pivot-r@pivot
        ankle=np.array([neutral[s]['x'], y, neutral[s]['z']])+rolling
        ankle[2]+=lift-.002
        return ankle,r,lift,at<=support,q
    worlds, measurements = [], []
    for f in range(clip['frames']):
        t=f/clip['fps']
        w=fk(clip,f)
        calibrated=retarget.world('Walk_Loop',t/duration*old_duration)
        for s in 'lr':
            thigh='thigh_'+s
            offset=w[ix[thigh],:3,3]-calibrated[ix[thigh],:3,3]
            for n in [thigh]+[b.name for b in rig.obj.data.bones[thigh].children_recursive]:
                w[ix[n]]=calibrated[ix[n]].copy()
                w[ix[n],:3,3]+=offset
        phase=(t-contacts['l'])/duration
        shift=np.array([.010*math.sin(2*math.pi*phase)-w[pelvis,0,3],0,0])
        w[family,:3,3]+=shift
        goals={s:path(s,t) for s in 'lr'}
        for s in 'lr':
            w[ix['ball_'+s]]=w[ix['foot_'+s]]@neutral[s]['toe']
        # Re-solve the pelvis after the skinned sole changes the ankle's height.
        # Otherwise toe-off can quietly overextend a leg by several millimetres.
        for _ in range(8):
            limits=[idle[pelvis,2,3]+.006]
            for s in 'lr':
                hip=w[ix['thigh_'+s],:3,3]
                ankle=goals[s][0]
                l1,l2=legs.legs[s][-2:]
                max_distance=math.sqrt(l1*l1+l2*l2+2*l1*l2*math.cos(math.radians(12)))
                planar=np.sum((hip[:2]-ankle[:2])**2)
                limits.append(ankle[2]+math.sqrt(max(max_distance**2-planar,.01))-(hip[2]-w[pelvis,2,3]))
            lowest=min(limits)
            height=lowest-.004*math.log(sum(math.exp(-(v-lowest)/.004) for v in limits))
            w[family,2,3]+=height-w[pelvis,2,3]
            for s in 'lr':
                ankle,r,wanted,_,_=goals[s]
                legs.place(w,s,ankle,r,knee_keep=.08)
                ankle[2]+=wanted-float(points(w,s)[:,2].min())
        row={'time':t,'pelvis_z_cm':height*100,'feet':{}}
        for s in 'lr':
            foot=ix['foot_'+s]
            ankle,r,wanted,planted,q=goals[s]
            legs.place(w,s,ankle,r,knee_keep=.08)
            error=float(np.linalg.norm(w[foot,:3,3]-ankle)*100)
            verts=points(w,s)
            a,b,c=[w[ix[n+'_'+s],:3,3] for n in ['thigh','calf','foot']]
            bend=math.degrees(math.acos(np.clip((b-a)@(c-b)/(np.linalg.norm(b-a)*np.linalg.norm(c-b)),-1,1)))
            row['feet'][s]={'support':planted,'support_fraction':q,'sole_cm':float(verts[:,2].min()*100),
                'knee_bend_deg':bend,'ankle_error_cm':error,'ankle_cm':(w[foot,:3,3]*100).tolist()}
            assert error<.10,(f,s,error)
            assert abs(row['feet'][s]['sole_cm']-wanted*100)<.08,(f,s,row['feet'][s])
        for source,dest in cr.IK_PINS:
            w[ix[dest]]=w[ix[source]].copy()
        worlds.append(w)
        measurements.append(row)
    # Exact periodic endpoint, including all helper targets.
    worlds[-1]=worlds[0].copy()
    for f,w in enumerate(worlds):
        local=rig.world_to_local(w)
        for n in leg_names|{'pelvis','ik_foot_l','ik_foot_r'}:
            clip['tracks'][n][f]=[float(v) for v in cr.ue_from_matrix(local[ix[n]])]
    clip['contacts_s']={s:round(v,6) for s,v in contacts.items()}
    clip['support_intervals']={'space':'cycle_seconds','duration_s':duration,
        'feet':{s:{'touchdown_s':contacts[s],'support_duration_s':support,
                   'flat_support_fraction':[.16,.70]} for s in 'lr'}}
    clip.setdefault('layers',{})['walk_repair']={'calibration':'mapped source/target segment directions',
        'swing_clearance_cm':args.lift_cm,'support_fraction':args.support_fraction,
        'pelvis':'coupled two-leg reach constraints with 12-degree extension margin',
        'heel_toe_pitch_deg':[-4,18],'cadence_steps_s':2/duration,'mesh_and_weights_changed':False}
    out=args.out/'clips.json'
    out.write_text(json.dumps(data,separators=(',',':')))
    receipt={'source_sha256':sha(args.packet),'packet_sha256':sha(out),'character_sha256':sha(args.source),
        'script_sha256':sha(Path(__file__)),'calibration_code_sha256':sha(Path(__file__).resolve().parents[2]/'src/reference_asset_compiler/animation_calibration.py'),
        'blender':bpy.app.version_string,'library_sha256':sha(library_path),
        'modified_clips':[name],'calibration':calibration,'parameters':{'lift_cm':args.lift_cm,'support_fraction':args.support_fraction,'cadence_steps_s':2/duration},
        'measurements':measurements,'human_approved':False,'installed':False,
        'scope':'Authored walk source; export, surface clearance, transitions and runtime remain separate checks.'}
    (args.out/'derivation.json').write_text(json.dumps(receipt,indent=2,default=float))
    print('WALK_CANDIDATE_READY -- the floor has been promoted from suggestion to constraint.')


if __name__ == '__main__':
    main()
