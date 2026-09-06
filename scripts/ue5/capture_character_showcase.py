"""Capture genuine UE stills and a sampled walk loop in an unsaved studio fixture.

RAC_SHOWCASE_CONFIG and RAC_RIG_REVIEW select the recipe and fresh output.
Uses the proven locomotion fixture; no asset/map/material is saved or retouched.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import unreal

ROOT=Path(os.environ['RAC_ROOT'])
config_path=ROOT/os.environ.get('RAC_SHOWCASE_CONFIG','configs/showcase/ayric-v051-editorial.json')
config_bytes=config_path.read_bytes()
cfg=json.loads(config_bytes)
audit_path=ROOT/cfg['runtime_audit']
audit=json.loads(audit_path.read_text())
if audit.get('ok') is not True or audit.get('cooked_runtime') is not True or audit['skeletal_mesh'].split('.')[0]!=cfg['mesh']:
    raise RuntimeError('Showcase requires the exact runtime-verified character')
for key,value in [('RAC_TARGET_MESH',cfg['mesh']),('RAC_ANIM_FOLDER',cfg['animations']),('RAC_REVIEW_BLUEPRINT',cfg['blueprint'])]:
    os.environ[key]=value
for key in ('RAC_FACE_REVIEW','RAC_FACE_MATERIAL','RAC_REVIEW_UNLIT','RAC_ASSEMBLY_FACE_ONLY'):
    os.environ.pop(key,None)
fixture_file='showcase_workshop_fixture.py' if cfg.get('level') else 'review_character_locomotion.py'
spec=importlib.util.spec_from_file_location('showcase_fixture',ROOT/'scripts/ue5'/fixture_file)
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
if hasattr(fixture,'handle'):
    unreal.unregister_slate_post_tick_callback(fixture.handle)
component=fixture.component
animation=unreal.load_asset(cfg['animations']+'/'+cfg['animation'])
if not animation:
    raise RuntimeError('Missing verified walking animation')
length=animation.get_play_length()
if length<=0:
    raise RuntimeError('Walk animation has no duration')
shots=[dict(s,file=s['name']+'.png') for s in cfg['shots']]
for shot in shots:
    shot.setdefault('time',None)
for i in range(cfg['frames_per_cycle']):
    shots.append({'name':'walk','camera':cfg['walk_camera'],'target':cfg['walk_target'],
                  'width':cfg['walk_width'],'height':cfg['walk_height'],
                  'time':length*i/cfg['frames_per_cycle'],'file':f'walk-{i:03d}.png'})
state={'index':0,'phase':'set','since':time.monotonic(),'records':[],'busy':False}


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    report={'ok':error is None,'error':error,'source_assets_saved':False,
            'engine':unreal.SystemLibrary.get_engine_version(),'blueprint':cfg['blueprint'],'mesh':cfg['mesh'],
            'animation':animation.get_path_name(),'cycle_seconds':length,'frames_per_cycle':cfg['frames_per_cycle'],
            'config_sha256':hashlib.sha256(config_bytes).hexdigest(),
            'config':cfg,
            'runtime_audit_sha256':hashlib.sha256(audit_path.read_bytes()).hexdigest(),
            'frames':state['records'],'claim':'Actual UE editor renders; sampled animation, not a performance benchmark or gameplay recording'}
    (fixture.OUT/'showcase.json').write_text(json.dumps(report,indent=2))
    unreal.log('SHOWCASE_CAPTURE_FINISHED '+str(error)+' -- no imaginary cheekbones were admitted.')
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    # Screenshot rendering can pump Slate again; admit only one butler at a time.
    if state['busy']:
        return
    state['busy']=True
    try:
        elapsed=time.monotonic()-state['since']
        if state['index']>=len(shots):
            finish(); return
        shot=shots[state['index']]
        if state['phase']=='set' and elapsed>1:
            if shot['time'] is None:
                component.set_animation(None)
                component.override_animation_data(None,False,False,0,0)
            else:
                selected=unreal.load_asset(cfg['animations']+'/'+shot['animation']) if shot.get('animation') else animation
                if not selected:
                    raise RuntimeError('Missing still-pose animation')
                component.set_animation(selected)
                # Override evaluates immediately: set the live instance time first.
                component.set_position(shot['time'],False)
                component.override_animation_data(selected,False,False,shot['time'],0)
                component.set_position(shot['time'],False)
                component.set_play_rate(0)
            position=unreal.Vector(*shot['camera']); target=unreal.Vector(*shot['target'])
            fixture.editor.set_level_viewport_camera_info(position,unreal.MathLibrary.find_look_at_rotation(position,target))
            state.update(phase='capture',since=time.monotonic())
        elif state['phase']=='capture' and elapsed>(3 if shot['time'] is None else .4):
            attachments=[]
            for part in fixture.actor.get_components_by_class(unreal.StaticMeshComponent):
                socket=str(part.get_attach_socket_name())
                if socket not in ('','None'):
                    bone=component.get_socket_transform(socket,unreal.RelativeTransformSpace.RTS_WORLD)
                    expected=unreal.MathLibrary.transform_location(bone,part.get_relative_transform().translation)
                    attachments.append({'socket':socket,'error_cm':(expected-part.get_world_location()).length()})
            if any(a['error_cm']>.1 for a in attachments):
                raise RuntimeError('Attachment slipped in showcase frame')
            bones={}
            for i in range(component.get_num_bones()):
                name=component.get_bone_name(i)
                t=component.get_socket_transform(name,unreal.RelativeTransformSpace.RTS_COMPONENT)
                bones[str(name)]=[t.translation.x,t.translation.y,t.translation.z]
            state['records'].append(dict(shot,actual_position=component.get_position(),attachments=attachments,bones=bones))
            state.update(phase='wait',since=time.monotonic())
            unreal.AutomationLibrary.take_high_res_screenshot(shot['width'],shot['height'],str(fixture.OUT/shot['file']))
        elif state['phase']=='wait' and elapsed>.5:
            path=fixture.OUT/shot['file']
            if not path.exists():
                if elapsed>15: raise RuntimeError('Missing captured frame '+str(path))
                return
            state['records'][-1]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            state.update(index=state['index']+1,phase='set',since=time.monotonic())
    except Exception as exc:
        finish(str(exc))
    finally:
        state['busy']=False


handle=unreal.register_slate_post_tick_callback(tick)
