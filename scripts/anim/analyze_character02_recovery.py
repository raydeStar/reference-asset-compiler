# SPDX-License-Identifier: MIT
"""Measure sampled game attack recovery; retain phase boundaries and comparison limits."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def analyze(proof):
    assert proof['error'] is None,proof['error']
    cases={}
    for name,swings,walking in proof['cases']:
        rows=[r for r in proof['frames'] if r['case']==name]
        attacking=[r for r in rows if r['combo_active']]
        assert attacking
        end=attacking[-1]['time']
        groups={'active_attack':attacking,
                'blend_out':[r for r in rows if r['any_montage'] and not r['combo_active']],
                'recovery':[r for r in rows if end<r['time']<=end+.6],
                'settled':[r for r in rows if r['time']>=6.4]}
        phases={}
        for phase,frames in groups.items():
            gaps=[r['soles'][s]['gap_cm'] for r in frames for s in 'lr' if r['soles'][s]['gap_cm'] is not None]
            phases[phase]={'samples':len(frames),'minimum_gap_cm':min(gaps) if gaps else None,
                'negative_gap_observations':sum(g<0 for g in gaps),
                'below_minus_05cm_observations':sum(g<-.5 for g in gaps)}
        pairs=[(a,b) for a,b in zip(rows,rows[1:]) if end-.1<=b['time']<=end+.6]
        # Component-space changes exclude intended pawn travel, but include authored pose motion.
        changes={bone:max(float(np.linalg.norm(np.array(b['bones'][bone][:3])-a['bones'][bone][:3])) for a,b in pairs)
                 for bone in ['pelvis','foot_l','foot_r']}
        cases[name]={'expected_swings':swings,'resume_walking':walking,'samples':len(rows),
            'sections':sorted({r['section'] for r in rows if r['section'] not in ('None','')}),
            'last_active_s':end,'montage_gone_s':next(r['time'] for r in rows if r['time']>end and not r['any_montage']),
            'end_speed_cm_s':rows[-1]['speed_cm_s'],'phases':phases,
            'maximum_recovery_component_step_cm':changes,
            'observed_delta_s_range':[min(r['delta_s'] for r in rows),max(r['delta_s'] for r in rows)]}
    return {'cases':cases,'scope':'149 sampled boot vertices, actual map collision and finite frame coverage. Recovery is the 0.6 seconds after the final active attack frame. Not continuous collision, performance or human acceptance proof.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('proof',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    result=analyze(json.loads(args.proof.read_text()))
    result['proof_sha256']=hashlib.sha256(args.proof.read_bytes()).hexdigest()
    with args.output.open('x') as file:
        json.dump(result,file,indent=2)
    print('RECOVERY_MEASURED -- even a graceful exit needs a floor.')


if __name__=='__main__':
    main()
