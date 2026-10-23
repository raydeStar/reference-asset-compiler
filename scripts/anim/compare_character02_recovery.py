# SPDX-License-Identifier: MIT
"""Compare paired fixed-step recovery probes, including preservation of active strikes."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


def compare(before,after):
    assert before['error'] is after['error'] is None
    index={(r['case'],round(r['time'],6)):r for r in before['frames']}
    maximum_position=maximum_angle=maximum_pawn=0.
    checked=0
    state_mismatches=[]
    previous=None
    for row in after['frames']:
        old=index[(row['case'],round(row['time'],6))]
        for key in ['combo_active','combo_playing','any_montage','section','attacking']:
            if old[key]!=row[key]:
                state_mismatches.append({'case':row['case'],'time':row['time'],'field':key})
        maximum_pawn=max(maximum_pawn,float(np.linalg.norm(np.array(row['pawn'][:3])-old['pawn'][:3])))
        # Input is submitted after pose evaluation; skip the first frame that activates a montage.
        if row['combo_active'] and previous and previous['case']==row['case'] and previous['combo_active']:
            for name,pose in row['bones'].items():
                other=old['bones'][name]
                maximum_position=max(maximum_position,float(np.linalg.norm(np.array(pose[:3])-other[:3])))
                delta=Rotation.from_quat(other[3:]).inv()*Rotation.from_quat(pose[3:])
                maximum_angle=max(maximum_angle,float(np.degrees(delta.magnitude())))
            checked+=1
        previous=row
    return {'active_pose_frames_compared':checked,'active_pose_max_position_difference_cm':maximum_position,
        'active_pose_max_rotation_difference_deg':maximum_angle,'maximum_pawn_path_difference_cm':maximum_pawn,
        'montage_state_mismatches':state_mismatches,
        'active_strikes_preserved':maximum_position<.01 and maximum_angle<.01 and not state_mismatches,
        'scope':'Paired game runs at identical simulation rate. Active-strike comparison excludes input-onset frames; no timing, movement-path or combat-state change is intended.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('before',type=Path)
    p.add_argument('after',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    result=compare(json.loads(args.before.read_text()),json.loads(args.after.read_text()))
    result['inputs']={label:{'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                      for label,path in [('before',args.before),('after',args.after)]}
    with args.output.open('x') as file:
        json.dump(result,file,indent=2)
    print('RECOVERY_COMPARED -- the strike keeps its appointment; the toes keep their dignity.')


if __name__=='__main__':
    main()
