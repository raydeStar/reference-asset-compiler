# SPDX-License-Identifier: MIT
"""Owned game-input attack recovery tests using world time, poses and real collision."""
import hashlib
import json
import math
import os
from pathlib import Path
import time
import traceback

import unreal

assert '-game' in unreal.SystemLibrary.get_command_line().lower()
OUT=Path(os.environ['RAC_RECOVERY_OUTPUT'])
OUT.mkdir(parents=True,exist_ok=False)
BOOT_PATH=Path(os.environ['RAC_BOOT_PROBE'])
BOOT=json.loads(BOOT_PATH.read_text())
CASES=[('walk_attack_idle',1,False),('walk_attack_walk',1,True),
       ('combo_idle',3,False),('combo_walk',3,True),('cancel_to_walk',1,True)]
COMBAT_PANEL=os.environ.get('RAC_COMBAT_PANEL')=='1'
if COMBAT_PANEL:
    CASES=[(f'attack_{attack:02d}_{destination}',attack,destination=='walk')
           for attack in (1,2,3) for destination in ('idle','walk')]
if os.environ.get('RAC_RECOVERY_CASE'):
    CASES=[c for c in CASES if c[0]==os.environ['RAC_RECOVERY_CASE']]
    assert CASES
VIEWS={'recovery_front':180,'recovery_side':90,'recovery_back':0,'recovery_three_quarter':135}
if os.environ.get('RAC_RECOVERY_MULTIVIEW')=='1':
    CASES=[(name,3 if COMBAT_PANEL else 1,False) for name in VIEWS]
STATE={'pawn':None,'case':0,'started':time.monotonic(),'attack':False,'last_press':-1.,'seen':set()}
PROOF={'schema':'rac.character02-recovery-runtime.v1','frames':[],'movie_frames':[],
       'engine':unreal.SystemLibrary.get_engine_version(),'cases':CASES,'error':None,
       'boot_probe_sha256':hashlib.sha256(BOOT_PATH.read_bytes()).hexdigest(),
       'sole_measurement':'all sampled vertices against individual collision traces' if COMBAT_PANEL else 'lowest world-Z sampled vertex per boot',
       'scope':'Owned rendered -game process with actual DoComboAttack and DoMove entry points. Fixed simulation rate, not performance or cooked-build evidence.'}


def pack(t):
    p,q=t.translation,t.rotation
    return [p.x,p.y,p.z,q.x,q.y,q.z,q.w]


def soles(pawn,mesh,bones):
    result={}
    for side,vertices in BOOT['sides'].items():
        points=[]
        for vertex in vertices:
            p=unreal.Vector()
            for influence in vertex['influences']:
                p+=bones[influence['bone']].transform_location(unreal.Vector(*influence['point_cm']))*influence['weight']
            p=mesh.get_world_transform().transform_location(p)
            points.append((p.z,vertex['vertex'],p))
        checks=[]
        for _,index,p in points if COMBAT_PANEL else [min(points,key=lambda x:x[0])]:
            hit=unreal.SystemLibrary.line_trace_single(pawn,p+unreal.Vector(0,0,45),p-unreal.Vector(0,0,180),
                unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,True,[pawn],unreal.DrawDebugTrace.NONE,True)
            data=hit.to_dict() if hit else {}
            ground=data.get('impact_point') if data.get('blocking_hit') else None
            checks.append({'vertex':index,'point':[p.x,p.y,p.z],
                           'ground_z':ground.z if ground else None,'gap_cm':p.z-ground.z if ground else None})
        valid=[c for c in checks if c['gap_cm'] is not None]
        result[side]=dict(min(valid,key=lambda c:c['gap_cm']) if valid else checks[0],
                          traced_samples=len(checks),valid_ground_samples=len(valid),
                          negative_samples=sum(c['gap_cm']<0 for c in valid))
    return result


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(STATE['handle'])
    PROOF['error']=error
    (OUT/'proof.json').write_text(json.dumps(PROOF,separators=(',',':')))
    unreal.log_warning('RECOVERY_PROBE_DONE -- the toes have testified. '+str(error or OUT))
    if STATE['pawn']:
        unreal.SystemLibrary.quit_game(STATE['pawn'],STATE['pawn'].get_controller(),unreal.QuitPreference.QUIT,False)


def tick(_):
    try:
        if time.monotonic()-STATE['started']>480:
            raise TimeoutError('Owned recovery probe exceeded its wall-time budget')
        if STATE['pawn'] is None:
            for pawn in unreal.ObjectIterator(unreal.TheAetherWarsCharacter):
                if pawn.is_player_controlled():
                    mesh=pawn.get_component_by_class(unreal.SkeletalMeshComponent)
                    mesh.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
                    mesh.set_editor_property('enable_update_rate_optimizations',False)
                    now=unreal.GameplayStatics.get_time_seconds(pawn)
                    STATE.update(pawn=pawn,spawn=pawn.get_actor_transform(),case_start=now,last_time=now,
                                 bones=[str(mesh.get_bone_name(i)) for i in range(mesh.get_num_bones())])
                    yaw=pawn.get_actor_rotation().yaw+VIEWS.get(CASES[0][0],float(os.environ.get('RAC_RECOVERY_VIEW','110')))
                    pawn.get_controller().set_control_rotation(unreal.Rotator(pitch=-10,yaw=yaw,roll=0))
                    mesh.prestream_textures(120,True,0)
                    PROOF.update(mesh=mesh.get_skeletal_mesh_asset().get_path_name(),anim_class=mesh.get_anim_instance().get_class().get_path_name())
                    break
            return
        pawn=STATE['pawn']
        now=unreal.GameplayStatics.get_time_seconds(pawn)
        delta=now-STATE['last_time']
        if delta<1e-6:
            return
        STATE['last_time']=now
        t=now-STATE['case_start']
        name,swings,resume_walk=CASES[STATE['case']]
        mesh=pawn.get_component_by_class(unreal.SkeletalMeshComponent)
        anim=mesh.get_anim_instance()
        montage=pawn.get_editor_property('combo_attack_montage')
        section=str(anim.montage_get_current_section(montage))
        if section not in ('None',''):
            STATE['seen'].add(section)
        if t>=1.8 and not STATE['attack']:
            pawn.do_combo_attack()
            STATE.update(attack=True,last_press=t)
        elif STATE['attack'] and section in [f'Melee{i:02d}' for i in range(1,swings)] and t-STATE['last_press']>.10:
            pawn.do_combo_attack()
            STATE['last_press']=t
        # Move through the game's input handler, including its real recovery cancellation rules.
        moving=1.0<=t<1.8 or (resume_walk and t>={1:2.35,2:3.30,3:4.25}[swings])
        strength=89.180502/500 if moving else 0.
        if name=='cancel_to_walk' and 2.35<=t<2.65:
            strength=.24
        if moving:
            heading=math.radians(STATE['spawn'].rotation.rotator().yaw-pawn.get_controller().get_control_rotation().yaw)
            pawn.do_move(math.sin(heading)*strength,math.cos(heading)*strength)
        bones={n:mesh.get_socket_transform(n,unreal.RelativeTransformSpace.RTS_COMPONENT) for n in STATE['bones']}
        PROOF['frames'].append({'case':name,'time':t,'delta_s':delta,'input':strength,
            'speed_cm_s':pawn.get_velocity().length(),'falling':pawn.get_component_by_class(unreal.CharacterMovementComponent).is_falling(),
            'attacking':pawn.is_attacking(),'any_montage':anim.is_any_montage_playing(),
            'combo_active':anim.montage_is_active(montage),'combo_playing':anim.montage_is_playing(montage),
            'grounding_alpha':unreal.AetherAnimLibrary.get_recovery_grounding_alpha(anim) if hasattr(unreal.AetherAnimLibrary,'get_recovery_grounding_alpha') else None,
            'section':section,'montage_position':anim.montage_get_position(montage),
            'plant_curves':{s:anim.get_curve_value('SolePlant'+s.upper()) for s in 'lr'},
            'pawn':pack(pawn.get_actor_transform()),'mesh_world':pack(mesh.get_world_transform()),
            'bones':{n:pack(v) for n,v in bones.items()},'soles':soles(pawn,mesh,bones)})
        if os.environ.get('RAC_RECOVERY_CAPTURE')=='1' and .8<=t<6.4:
            last=STATE.get('last_capture',-1)
            if t-last>=1/30-1e-5:
                index=STATE.get('capture_index',0)
                path=OUT/f'{name}-{index:05d}.png'
                PROOF['movie_frames'].append({'case':name,'time':t,'path':str(path)})
                STATE.update(last_capture=t,capture_index=index+1)
                unreal.SystemLibrary.execute_console_command(pawn,f'HighResShot 768x576 filename="{path.as_posix()}"')
        if t>=7.2:
            assert len(STATE['seen'])==swings,(name,STATE['seen'])
            assert not anim.is_any_montage_playing(),(name,'unfinished montage')
            if resume_walk:
                assert 80<pawn.get_velocity().length()<100,(name,'walking did not resume')
            else:
                assert pawn.get_velocity().length()<1,(name,'idle did not resume')
            STATE['case']+=1
            if STATE['case']==len(CASES):
                finish()
            else:
                pawn.get_component_by_class(unreal.CharacterMovementComponent).stop_movement_immediately()
                pawn.set_actor_location(STATE['spawn'].translation,False,True)
                pawn.set_actor_rotation(STATE['spawn'].rotation.rotator(),False)
                yaw=STATE['spawn'].rotation.rotator().yaw+VIEWS.get(CASES[STATE['case']][0],float(os.environ.get('RAC_RECOVERY_VIEW','110')))
                pawn.get_controller().set_control_rotation(unreal.Rotator(pitch=-10,yaw=yaw,roll=0))
                STATE.update(case_start=now,attack=False,last_press=-1.,seen=set(),last_capture=-1,capture_index=0)
    except Exception:
        finish(traceback.format_exc())


STATE['handle']=unreal.register_slate_post_tick_callback(tick)
