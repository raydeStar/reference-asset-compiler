# SPDX-License-Identifier: MIT
"""Measure evaluated walk poses, sampled sole gaps and stationary support windows."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


def analyze(proof):
    if proof.get('error') or not proof.get('frames'):
        raise ValueError('Runtime capture must be complete and error-free')
    cases={}
    for name in dict.fromkeys(f['case'] for f in proof['frames']):
        rows=[f for f in proof['frames'] if f['case']==name]
        steady=[f for f in rows if f['input']>0 and abs(f['speed_cm_s']-89.180502)<1 and 1.45<f['time']<3.85]
        summary={'samples':len(rows),'falling_samples':sum(f['falling'] for f in rows),
                 'max_speed_cm_s':max(f['speed_cm_s'] for f in rows),'steady_walk_samples':len(steady)}
        summary['knee_bend_deg']={}
        for side in 'lr':
            values=[]
            for f in steady:
                a,b,c=[np.array(f['bones'][n+'_'+side][:3]) for n in ['thigh','calf','foot']]
                u,v=b-a,c-b
                values.append(float(np.degrees(np.arccos(np.clip(u@v/(np.linalg.norm(u)*np.linalg.norm(v)),-1,1)))))
            summary['knee_bend_deg'][side]={'min':min(values),'max':max(values)} if values else None
        summary['sole_gap_cm']={s:{'min':min(f['soles'][s]['gap_cm'] for f in rows if f['soles'][s]['gap_cm'] is not None),
            'max':max(f['soles'][s]['gap_cm'] for f in rows if f['soles'][s]['gap_cm'] is not None),
            'below_minus_05cm_samples':sum(f['soles'][s]['gap_cm'] is not None and f['soles'][s]['gap_cm']<-.5 for f in rows)} for s in 'lr'}
        # Infer only near-flat support windows. Changing heel/toe pivots are excluded;
        # thresholds and coverage are reported, so a short window cannot impersonate a whole gait.
        windows=[]
        for side in 'lr':
            current=[]
            def close():
                if len(current)>=4 and current[-1]['time']-current[0]['time']>=.10:
                    xyz=np.array([f['soles'][side]['point'][:2] for f in current])
                    window={'side':side,'start_s':current[0]['time'],'end_s':current[-1]['time'],
                        'samples':len(current),'max_displacement_cm':float(np.max(np.linalg.norm(xyz-xyz[0],axis=1)))}
                    if all('plant_curves' in f for f in current):
                        values=[f['plant_curves'][side] for f in current]
                        window['plant_curve_range']=[min(values),max(values)]
                        window['entire_window_declared_flat_support']=min(values)>=.9
                    windows.append(window)
                current.clear()
            for a,b in zip(rows,rows[1:]):
                dt=b['time']-a['time']
                qa,qb=[Rotation.from_quat(f['bones']['foot_'+side][3:]) for f in (a,b)]
                angular=float(np.degrees((qa.inv()*qb).magnitude())/dt)
                vertical=abs(b['bones']['foot_'+side][2]-a['bones']['foot_'+side][2])/dt
                gaps=[f['soles'][side]['gap_cm'] for f in (a,b)]
                good=(a['input']>0 and 85<a['speed_cm_s']<94 and 85<b['speed_cm_s']<94
                      and all(g is not None and -.5<=g<=2.5 for g in gaps) and angular<18 and vertical<8
                      and a['soles'][side]['vertex']==b['soles'][side]['vertex'])
                if good:
                    if not current:
                        current.append(a)
                    current.append(b)
                else:
                    close()
            close()
        summary['near_flat_support_windows']=windows
        changes=[rows[i]['time'] for i in range(1,len(rows)) if rows[i]['step']!=rows[i-1]['step']]
        transition=[]
        for moment in changes:
            pairs=[(a,b) for a,b in zip(rows,rows[1:]) if abs(b['time']-moment)<.25]
            movement=[float(np.linalg.norm(np.array(b['bones']['pelvis'][:3])-a['bones']['pelvis'][:3])) for a,b in pairs]
            transition.append({'input_change_s':moment,'max_pelvis_step_cm':max(movement,default=0),
                'observed_max_dt_s':max((b['time']-a['time'] for a,b in pairs),default=0)})
        summary['transition_windows']=transition
        cases[name]=summary
    return {'cases':cases,'support_window_definition':{'angular_speed_max_deg_s':18,'ankle_vertical_speed_max_cm_s':8,
        'sole_gap_range_cm':[-.5,2.5],'minimum_window_s':.10,'minimum_samples':4,'same_sampled_surface_vertex':True},
        'scope':'Sampled evaluated game poses and collision at this map location. Flat-support windows are inferred subsets, not continuous or all-terrain proof.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('proof',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    result=analyze(json.loads(args.proof.read_text()))
    result['proof_sha256']=hashlib.sha256(args.proof.read_bytes()).hexdigest()
    with args.output.open('x') as file:
        json.dump(result,file,indent=2)
    print('WALK_MEASURED -- the numbers describe the gait; they do not applaud it.')


if __name__=='__main__':
    main()
