# SPDX-License-Identifier: MIT
"""Measure per-strike contact and compare the unaffected combat performance."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from analyze_character02_recovery import analyze


def measure(proof):
    result=analyze(proof)
    result['sole_measurement']=proof['sole_measurement']
    for name,case in result['cases'].items():
        rows=[f for f in proof['frames'] if f['case']==name]
        observations=[f['soles'][s] for f in rows for s in 'lr']
        gaps=[s['gap_cm'] for s in observations if s['gap_cm'] is not None]
        case['whole_case']={'minimum_gap_cm':min(gaps),'negative_foot_observations':sum(g<0 for g in gaps),
            'traced_vertices':sum(s['traced_samples'] for s in observations),
            'valid_ground_hits':sum(s['valid_ground_samples'] for s in observations),
            'minimum_trace_coverage':min(s['valid_ground_samples']/s['traced_samples'] for s in observations)}
        case['strikes']={}
        for section in case['sections']:
            frames=[f for f in rows if f['combo_active'] and f['section']==section]
            gaps=[f['soles'][s]['gap_cm'] for f in frames for s in 'lr' if f['soles'][s]['gap_cm'] is not None]
            case['strikes'][section]={'frames':len(frames),'minimum_gap_cm':min(gaps),
                'negative_foot_observations':sum(g<0 for g in gaps),
                'minimum_trace_coverage':min(f['soles'][s]['valid_ground_samples']/f['soles'][s]['traced_samples'] for f in frames for s in 'lr')}
    return result


def compare(before,after):
    assert before['error'] is after['error'] is None
    old={(f['case'],round(f['time'],6)):f for f in before['frames']}
    assert len(old)==len(after['frames'])
    maxima=dict(unaffected_position_cm=0.,unaffected_rotation_deg=0.,pawn_position_cm=0.,
                active_foot_xy_cm=0.,active_foot_rotation_deg=0.,active_foot_lift_cm=0.,active_foot_lowering_cm=0.,
                montage_time_s=0.)
    changes=[]
    count=0
    per_case={}
    previous=None
    for f in after['frames']:
        b=old[(f['case'],round(f['time'],6))]
        for key in ['section','combo_active','combo_playing','any_montage','attacking','falling','input']:
            if f[key]!=b[key]:
                changes.append({'case':f['case'],'time':f['time'],'field':key})
        maxima['pawn_position_cm']=max(maxima['pawn_position_cm'],float(np.linalg.norm(np.array(f['pawn'][:3])-b['pawn'][:3])))
        maxima['montage_time_s']=max(maxima['montage_time_s'],abs(f['montage_position']-b['montage_position']))
        # Only the two leg chains, their descendants and IK foot targets may move.
        for bone,pose in f['bones'].items():
            if bone.startswith(('thigh_','calf_','foot_','ball_')) or bone in ('ik_foot_l','ik_foot_r'):
                continue
            other=b['bones'][bone]
            position=float(np.linalg.norm(np.array(pose[:3])-other[:3]))
            angle=float(np.degrees((Rotation.from_quat(other[3:]).inv()*Rotation.from_quat(pose[3:])).magnitude()))
            maxima['unaffected_position_cm']=max(maxima['unaffected_position_cm'],position)
            maxima['unaffected_rotation_deg']=max(maxima['unaffected_rotation_deg'],angle)
        if f['combo_active'] and previous and previous['case']==f['case'] and previous['combo_active']:
            count+=1
            per_case[f['case']]=per_case.get(f['case'],0)+1
            for side in 'lr':
                a,z=f['bones']['foot_'+side],b['bones']['foot_'+side]
                maxima['active_foot_xy_cm']=max(maxima['active_foot_xy_cm'],float(np.linalg.norm(np.array(a[:2])-z[:2])))
                maxima['active_foot_rotation_deg']=max(maxima['active_foot_rotation_deg'],float(np.degrees((Rotation.from_quat(z[3:]).inv()*Rotation.from_quat(a[3:])).magnitude())))
                maxima['active_foot_lift_cm']=max(maxima['active_foot_lift_cm'],a[2]-z[2])
                maxima['active_foot_lowering_cm']=min(maxima['active_foot_lowering_cm'],a[2]-z[2])
        previous=f
    passed=(not changes and maxima['pawn_position_cm']<.001 and maxima['montage_time_s']<1e-6
            and maxima['unaffected_position_cm']<.001 and maxima['unaffected_rotation_deg']<.001
            and maxima['active_foot_xy_cm']<.001 and maxima['active_foot_rotation_deg']<.001
            and maxima['active_foot_lowering_cm']>-.001)
    return {'maxima':maxima,'state_mismatches':changes,'active_frames_compared':count,
            'per_case_frames':per_case,'performance_preserved_except_vertical_leg_contact':passed,
            'scope':'Paired fixed-step game poses. Upper body, pelvis, coat, hand targets, path and timing are preserved; active feet may rise but must retain horizontal trajectory and orientation. Input-onset frames are excluded from active-foot comparison.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('proof',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--before',type=Path)
    args=p.parse_args()
    proof=json.loads(args.proof.read_text())
    result=measure(proof)
    result['proof']={'path':str(args.proof.resolve()),'sha256':hashlib.sha256(args.proof.read_bytes()).hexdigest()}
    if args.before:
        result['comparison']=compare(json.loads(args.before.read_text()),proof)
        result['before']={'path':str(args.before.resolve()),'sha256':hashlib.sha256(args.before.read_bytes()).hexdigest()}
    with args.output.open('x') as f:
        json.dump(result,f,indent=2)
    print('COMBAT_CONTACT_MEASURED -- a sword may sweep; a toe should not excavate.')


if __name__=='__main__':
    main()
