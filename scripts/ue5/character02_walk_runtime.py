# SPDX-License-Identifier: MIT
"""Owned game-input walk, stops, speed changes and turns; real poses and collision.

RAC_WALK_OUTPUT and RAC_BOOT_PROBE are required. Optional RAC_WALK_CAPTURE=1
records the first case. Fixed-step capture runs are not real-time FPS benchmarks.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import time
import traceback

import unreal

assert '-game' in unreal.SystemLibrary.get_command_line().lower()
OUT=Path(os.environ['RAC_WALK_OUTPUT'])
OUT.mkdir(parents=True,exist_ok=False)
BOOT_PATH=Path(os.environ['RAC_BOOT_PROBE'])
BOOT=json.loads(BOOT_PATH.read_text())
REVIEW = json.loads(Path(os.environ['RAC_WALK_REVIEW_PROFILE']).read_text()) if os.environ.get('RAC_WALK_REVIEW_PROFILE') else {}
PLAN=[('walk_stop_a',[(1.,0.,0),(3.,89.180502/500,0),(1.4,0,0)]),
      ('walk_stop_b',[(1.,0.,0),(3.666667,89.180502/500,0),(1.4,0,0)]),
      ('speed_changes',[(1.,0.,0),(1.8,89.180502/500,0),(1.4,1.,0),(1.8,89.180502/500,0),(1.,0,0)]),
      ('walk_turns',[(1.,0.,0),(1.5,.24,0),(1.5,.24,90),(1.5,.24,-90),(1.,0,0)])]
if os.environ.get('RAC_WALK_REGRESSIONS')=='1':
    PLAN += [('walk_jump',[(1.,0.,0),(3.,89.180502/500,0),(1.,0,0)]),
             ('walk_attack',[(1.,0.,0),(.8,89.180502/500,0),(2.2,0,0)])]
TURN_PANEL=os.environ.get('RAC_TURN_PANEL')=='1'
if TURN_PANEL:
    # Keep the original failing path as well as isolated left/right/reversal exits.
    PLAN=[('turn_sequence_idle',[(1.,0.,0),(1.5,.24,0),(1.5,.24,90),(1.5,.24,-90),(2.,0,-90)])]
    for label,angle in [('left',90),('right',-90),('reverse',180)]:
        for exit_name in ('idle','walk'):
            tail=[(2.,0,angle)] if exit_name=='idle' else [(2.,89.180502/500,angle)]
            PLAN.append((f'turn_{label}_{exit_name}',[(1.,0.,0),(1.5,.24,0),(1.5,.24,angle),*tail]))
    if os.environ.get('RAC_TURN_CASE') and not REVIEW:
        PLAN=[p for p in PLAN if p[0] in os.environ['RAC_TURN_CASE'].split(',')]
    assert PLAN
if REVIEW:
    speed = float(REVIEW['walk_speed_cm_s'])
    assert 30 <= speed <= 300
    PLAN = [('idle_walk_stop_left', [(3.,0,0),(3.,speed/500,0),(2.,0,0)]),
            ('idle_walk_stop_right', [(1.,0,0),(3.5,speed/500,0),(2.,0,0)])]
    for label, angle in [('left',90),('right',-90),('reverse',180)]:
        for exit_name in ('idle','walk'):
            PLAN.append((f'{label}_to_{exit_name}', [(1.,0,0),(1.5,speed/500,0),
                (1.5,speed/500,angle),(2.,0 if exit_name=='idle' else speed/500,angle),(1.,0,angle)]))
    if os.environ.get('RAC_TURN_CASE'):
        PLAN=[p for p in PLAN if p[0] in os.environ['RAC_TURN_CASE'].split(',')]
        assert PLAN
    TURN_PANEL=True
STATE={'pawn':None,'case':0,'elapsed':0.,'sample':0.,'started':time.monotonic(),'step':-1}
PROOF={'schema':'rac.character02-walk-runtime.v1','engine':unreal.SystemLibrary.get_engine_version(),
       'command_line':unreal.SystemLibrary.get_command_line(),'plan':PLAN,'frames':[],'movie_frames':[],
       'error':None,'boot_probe_sha256':hashlib.sha256(BOOT_PATH.read_bytes()).hexdigest(),
       'scope':'Owned -game process, actual movement input and collision. Reset to spawn only between cases. No cooked-build or human-acceptance claim.'}
PROOF['review_profile'] = REVIEW
PROOF['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


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
        for _,index,p in points if os.environ.get('RAC_WALK_FULL_SOLE')=='1' else [min(points,key=lambda x:x[0])]:
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
    unreal.log_warning('WALK_RUNTIME_DONE -- the floor has been cross-examined. '+str(error or OUT))
    if STATE['pawn']:
        unreal.SystemLibrary.quit_game(STATE['pawn'],STATE['pawn'].get_controller(),unreal.QuitPreference.QUIT,False)


def tick(delta):
    try:
        if time.monotonic()-STATE['started']>(600 if REVIEW else 260):
            raise TimeoutError('Owned runtime test exceeded time budget')
        if STATE['pawn'] is None:
            for pawn in unreal.ObjectIterator(unreal.TheAetherWarsCharacter):
                if pawn.is_player_controlled():
                    STATE['pawn']=pawn
                    mesh=pawn.get_component_by_class(unreal.SkeletalMeshComponent)
                    if REVIEW:
                        # A temporary costume change; the saved player remains inviolate.
                        mesh.set_skeletal_mesh_asset(unreal.load_asset(REVIEW['mesh']))
                        for slot in range(mesh.get_num_materials()):
                            mesh.set_material(slot,None)
                        mesh.set_anim_instance_class(unreal.load_class(None, REVIEW['anim_class']))
                        hair=pawn.get_component_by_class(unreal.GroomComponent)
                        if hair and REVIEW.get('groom'):
                            hair.set_groom_asset(unreal.load_asset(REVIEW['groom']))
                            hair.set_binding_asset(None)
                            hair.set_editor_property('attachment_name','head')
                            hair.set_relative_transform(unreal.Transform())
                            if REVIEW.get('hair_material'):
                                hair.set_material(0,unreal.load_asset(REVIEW['hair_material']))
                        PROOF['temporary_mesh_override']=True
                    mesh.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
                    mesh.set_editor_property('enable_update_rate_optimizations',False)
                    STATE.update(pawn=pawn,spawn=pawn.get_actor_transform(),bones=[str(mesh.get_bone_name(i)) for i in range(mesh.get_num_bones())])
                    STATE['case_start']=STATE['last_world_time']=unreal.GameplayStatics.get_time_seconds(pawn)
                    PROOF.update(mesh=mesh.get_skeletal_mesh_asset().get_path_name(),anim_class=mesh.get_anim_instance().get_class().get_path_name())
                    pawn.get_controller().set_control_rotation(unreal.Rotator(pitch=-10,yaw=pawn.get_actor_rotation().yaw+float(os.environ.get('RAC_WALK_VIEW','110')),roll=0))
                    mesh.prestream_textures(120,True,0)
                    break
            return
        pawn=STATE['pawn']
        now=unreal.GameplayStatics.get_time_seconds(pawn)
        delta=now-STATE['last_world_time']
        if delta<=1e-6:
            return
        STATE['last_world_time']=now
        STATE['elapsed']=now-STATE['case_start']
        name,steps=PLAN[STATE['case']]
        t=STATE['elapsed']
        end=0.
        for step,(length,strength,angle) in enumerate(steps):
            end+=length
            if t<end:
                break
        yaw=STATE['spawn'].rotation.rotator().yaw+angle
        if name in ('walk_jump','walk_attack') and t>=1.8 and not STATE.get('action_fired'):
            STATE['action_fired']=True
            if name=='walk_jump':
                pawn.jump()
            else:
                pawn.do_combo_attack()
        if name=='walk_jump' and t>=1.95:
            pawn.stop_jumping()
        if strength:
            direction=unreal.Vector(math.cos(math.radians(yaw)),math.sin(math.radians(yaw)),0)
            if TURN_PANEL:
                relative=math.radians(yaw-pawn.get_controller().get_control_rotation().yaw)
                pawn.do_move(math.sin(relative)*strength,math.cos(relative)*strength)
            else:
                pawn.add_movement_input(direction,strength,True)
        STATE['sample']+=float(delta)
        mesh=pawn.get_component_by_class(unreal.SkeletalMeshComponent)
        anim=mesh.get_anim_instance()
        if STATE['sample']>=1/60-1e-5:
            STATE['sample']=0.
            bones={n:mesh.get_socket_transform(n,unreal.RelativeTransformSpace.RTS_COMPONENT) for n in STATE['bones']}
            PROOF['frames'].append({'case':name,'step':step,'time':t,'delta_s':float(delta),
                'speed_cm_s':pawn.get_velocity().length(),'input':strength,'heading':yaw,
                'falling':pawn.get_component_by_class(unreal.CharacterMovementComponent).is_falling(),
                'pawn':pack(pawn.get_actor_transform()),'mesh_world':pack(mesh.get_world_transform()),
                'transition_time':unreal.AetherAnimLibrary.get_locomotion_transition_time(anim),
                'cycle_start':unreal.AetherAnimLibrary.get_locomotion_cycle_start(anim),
                'plant_curves':{s:anim.get_curve_value('SolePlant'+s.upper()) for s in 'lr'},
                'combo_active':anim.montage_is_playing(pawn.get_editor_property('combo_attack_montage')),
                'bones':{n:pack(v) for n,v in bones.items()},'soles':soles(pawn,mesh,bones)})
        capture_cases=os.environ.get('RAC_WALK_CAPTURE_CASES','').split(',')
        capture_case=not capture_cases[0] or name in capture_cases
        if os.environ.get('RAC_WALK_CAPTURE')=='1' and capture_case and (TURN_PANEL or STATE['case']==0) and t>=.5 and t<=sum(s[0] for s in steps)-.2:
            captures=PROOF['movie_frames']
            if not captures or captures[-1]['case']!=name or t-captures[-1]['time_s']>=1/30-1e-5:
                index=STATE.get('capture_index',0)
                path=OUT/(f'{name}-{index:05d}.png' if TURN_PANEL else f'movie-{len(captures):05d}.png')
                captures.append({'time_s':t,'path':str(path),'case':name})
                STATE['capture_index']=index+1
                unreal.SystemLibrary.execute_console_command(pawn,f'HighResShot 768x576 filename="{path.as_posix()}"')
        if STATE['elapsed']>=sum(s[0] for s in steps):
            if REVIEW:
                rows=[f for f in PROOF['frames'] if f['case']==name]
                gaps=[v['gap_cm'] for f in rows for v in f['soles'].values() if v['gap_cm'] is not None]
                (OUT/(name+'-summary.json')).write_text(json.dumps({'case':name,'frames':len(rows),
                    'minimum_sole_gap_cm':min(gaps),'samples_below_minus_0_2_cm':sum(v<-.2 for v in gaps),
                    'maximum_speed_cm_s':max(f['speed_cm_s'] for f in rows)},indent=2))
            STATE['case']+=1
            STATE['elapsed']=0.
            STATE['case_start']=now
            STATE['action_fired']=False
            STATE['capture_index']=0
            if STATE['case']==len(PLAN):
                finish()
            else:
                movement=pawn.get_component_by_class(unreal.CharacterMovementComponent)
                movement.stop_movement_immediately()
                pawn.set_actor_location(STATE['spawn'].translation,False,True)
                pawn.set_actor_rotation(STATE['spawn'].rotation.rotator(),False)
                if REVIEW:
                    # Independent cases must not inherit a world-space plant
                    # from the previous case's teleported-away location.
                    previous_instance=mesh.get_anim_instance()
                    instance_class=previous_instance.get_class()
                    mesh.set_anim_instance_class(None)
                    mesh.set_anim_instance_class(instance_class)
                    assert mesh.get_anim_instance()!=previous_instance
                    PROOF['between_case_animation_reset']=True
                    PROOF.setdefault('case_instance_resets',[]).append({
                        'previous':previous_instance.get_path_name(),
                        'next':mesh.get_anim_instance().get_path_name()})
    except Exception:
        finish(traceback.format_exc())


STATE['handle']=unreal.register_slate_post_tick_callback(tick)
