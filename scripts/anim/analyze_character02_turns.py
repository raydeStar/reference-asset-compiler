# SPDX-License-Identifier: MIT
"""Measure turn contact, exit states and paired performance from evaluated game poses."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from analyze_character02_walk import analyze


def measure(proof):
    result=analyze(proof)
    plans=dict(proof['plan'])
    for name,case in result['cases'].items():
        rows=[f for f in proof['frames'] if f['case']==name]
        assert rows[-1]['time']>=sum(s[0] for s in plans[name])-1e-4, name
        end_speed=rows[-1]['speed_cm_s']
        expected_walk=name.endswith('_walk')
        case['end_speed_cm_s']=end_speed
        case['exit_state_passed']=80<end_speed<100 if expected_walk else end_speed<1
        observations=[f['soles'][s] for f in rows for s in 'lr']
        valid=[o['gap_cm'] for o in observations if o['gap_cm'] is not None]
        case['whole_case']={'minimum_gap_cm':min(valid),'negative_foot_observations':sum(g<0 for g in valid),
            'minimum_trace_coverage':min(o['valid_ground_samples']/o['traced_samples'] for o in observations),
            'valid_ground_hits':sum(o['valid_ground_samples'] for o in observations),
            'traced_vertices':sum(o['traced_samples'] for o in observations)}
        exit_start=sum(s[0] for s in plans[name][:-1])
        case['exit_start_s']=exit_start
        case['exit_minimum_gap_cm']=min(f['soles'][s]['gap_cm'] for f in rows for s in 'lr'
                                      if f['time']>=exit_start and f['soles'][s]['gap_cm'] is not None)
        # Component-space foot jumps complement the unchanged pelvis/path checks.
        case['exit_maximum_foot_step_cm']={s:max(float(np.linalg.norm(np.array(b['bones']['foot_'+s][:3])-a['bones']['foot_'+s][:3]))
            for a,b in zip(rows,rows[1:]) if exit_start-.2<=b['time']<=exit_start+.6) for s in 'lr'}
    result['scope']='All retained sole vertices independently traced on tested terrain; finite samples and ray misses do not establish continuous contact.'
    return result


def compare(before,after):
    assert before['error'] is after['error'] is None
    old={(f['case'],round(f['time'],6)):f for f in before['frames']}
    assert len(old)==len(after['frames'])
    maximum={'unaffected_position_cm':0.,'unaffected_rotation_deg':0.,'pawn_position_cm':0.,'foot_rotation_deg':0.}
    mismatches=[]
    for f in after['frames']:
        b=old[(f['case'],round(f['time'],6))]
        for key in ('step','input','heading','falling','combo_active','cycle_start','transition_time'):
            if abs(float(f[key])-float(b[key]))>1e-5:
                mismatches.append({'case':f['case'],'time':f['time'],'field':key})
        maximum['pawn_position_cm']=max(maximum['pawn_position_cm'],float(np.linalg.norm(np.array(f['pawn'][:3])-b['pawn'][:3])))
        for bone,pose in f['bones'].items():
            other=b['bones'][bone]
            angle=float(np.degrees((Rotation.from_quat(other[3:]).inv()*Rotation.from_quat(pose[3:])).magnitude()))
            if bone in ('foot_l','foot_r'):
                maximum['foot_rotation_deg']=max(maximum['foot_rotation_deg'],angle)
            if bone.startswith(('thigh_','calf_','foot_','ball_')) or bone in ('ik_foot_l','ik_foot_r'):
                continue
            maximum['unaffected_position_cm']=max(maximum['unaffected_position_cm'],float(np.linalg.norm(np.array(pose[:3])-other[:3])))
            maximum['unaffected_rotation_deg']=max(maximum['unaffected_rotation_deg'],angle)
    return {'frames_compared':len(old),'maxima':maximum,'state_mismatches':mismatches,
            'unaffected_performance_preserved':not mismatches and all(v<.001 for v in maximum.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proof',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--before',type=Path)
    args=parser.parse_args()
    proof=json.loads(args.proof.read_text())
    result=measure(proof)
    result['proof']={'path':str(args.proof.resolve()),'sha256':hashlib.sha256(args.proof.read_bytes()).hexdigest()}
    if args.before:
        result['comparison']=compare(json.loads(args.before.read_text()),proof)
        result['before']={'path':str(args.before.resolve()),'sha256':hashlib.sha256(args.before.read_bytes()).hexdigest()}
    with args.output.open('x') as handle:
        json.dump(result,handle,indent=2)
    print('TURNS_MEASURED -- the boots have been asked to explain themselves.')


if __name__=='__main__':
    main()
