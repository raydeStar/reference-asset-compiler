"""Capture fixed native animation poses in an unsaved, dedicated-editor fixture.

Source assets are never saved. Evidence records component-space bones as well
as pictures: a moving capsule alone is not a certificate of healthy knees.
"""
import json
import math
import os
import time
from pathlib import Path

import unreal

ROOT = Path(os.environ['RAC_ROOT'])
OUT = ROOT / 'work/sunset-workshop/evidence' / os.environ['RAC_RIG_REVIEW']
OUT.mkdir(parents=True, exist_ok=False)
MESH = os.environ.get('RAC_TARGET_MESH', '/Game/Compiled/SunsetAyricV2Production/sunset-ayric-v2-production')
ANIMS = os.environ.get('RAC_ANIM_FOLDER', '/Game/SunsetWorkshop/AyricPlayer/v034/Anims')
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level.load_level('/Game/SunsetWorkshop/L_WorkshopNight_v034')
for actor in actors.get_all_level_actors():
    actor.set_is_temporarily_hidden_in_editor(True)
ASSEMBLY_BP = os.environ.get('RAC_REVIEW_BLUEPRINT')
actor_class = unreal.load_asset(ASSEMBLY_BP).generated_class() if ASSEMBLY_BP else unreal.SkeletalMeshActor
actor = actors.spawn_actor_from_class(actor_class, unreal.Vector(0, 0, 0))
component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
if ASSEMBLY_BP:
    component.set_world_transform(unreal.Transform(),False,True)
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
component.set_skeletal_mesh_asset(unreal.load_asset(MESH))
ORIGINAL_MATERIAL = component.get_material(0)
if os.environ.get('RAC_FACE_MATERIAL'):
    component.set_material(0,unreal.load_asset(os.environ['RAC_FACE_MATERIAL']))
component.set_forced_lod(1)
component.set_update_animation_in_editor(True)
for location, rotation, intensity in [((160,240,260),(-35,-120,0),5), ((-160,120,180),(-25,-50,0),3)]:
    lamp = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(*location), unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
    lamp.light_component.set_intensity(intensity)
if ASSEMBLY_BP:
    # A dark side is not side-view evidence. A restrained rear fill belongs
    # only to this unsaved inspection fixture, never to the workshop map.
    lamp = actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(0,-240,200),unreal.Rotator(pitch=-25,yaw=90))
    lamp.light_component.set_intensity(2)
level.editor_set_game_view(True)
world = editor.get_editor_world()
unreal.SystemLibrary.execute_console_command(world, 'r.EyeAdaptationQuality 0')
unreal.SystemLibrary.execute_console_command(world, 'r.DefaultFeature.AutoExposure 0')
poses = [('rest',None,0),('idle','MM_Idle_Ayric',0),('walk-a','MF_Unarmed_Walk_Fwd_Ayric',0.2),('walk-b','MF_Unarmed_Walk_Fwd_Ayric',0.65),('jump','MM_Jump_Ayric',0.35)]
shots = [(p,view) for p in poses for view in ['front','side']]
if ASSEMBLY_BP:
    shots = [(poses[0], view) for view in ['face-front','face-left','face-right','face-side','face-back']] + shots
if os.environ.get('RAC_ASSEMBLY_FACE_ONLY') == '1':
    shots = [(poses[0], view) for view in ['face-front','face-left','face-right','face-side','face-back']]
if os.environ.get('RAC_REVIEW_UNLIT') == '1':
    unreal.SystemLibrary.execute_console_command(world,'viewmode unlit')
FACE_REVIEW = os.environ.get('RAC_FACE_REVIEW') == '1'
if FACE_REVIEW:
    shots = [((variant,None,0),view) for variant in ['baseline','candidate'] for view in ['front','left','right','side','opposite']]
state = {'index':0,'phase':'set','since':time.monotonic(),'records':[]}
unreal.EditorPythonScripting.set_keep_python_script_alive(True)

def finish(error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    (OUT/'review.json').write_text(json.dumps({'mesh':MESH,'blueprint':ASSEMBLY_BP,'anims':ANIMS,'error':error,'samples':state['records'],'source_assets_saved':False,'face_only':os.environ.get('RAC_ASSEMBLY_FACE_ONLY')=='1','unlit':os.environ.get('RAC_REVIEW_UNLIT')=='1'},indent=2))
    unreal.log('RAC_LOCOMOTION_REVIEW '+str(error)+' -- the knees have taken the witness stand.')
    unreal.SystemLibrary.quit_editor()

def tick(delta):
    try:
        elapsed=time.monotonic()-state['since']
        if state['index']>=len(shots):
            finish()
            return
        (name,anim_name,seconds),view=shots[state['index']]
        if state['phase']=='set' and elapsed>3:
            if FACE_REVIEW:
                material = ORIGINAL_MATERIAL if name=='baseline' else unreal.load_asset(os.environ['RAC_FACE_MATERIAL'])
                component.set_material(0,material)
            if anim_name:
                anim=unreal.load_asset(ANIMS+'/'+anim_name)
                if anim is None:
                    raise RuntimeError('Missing animation '+anim_name)
                component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
                component.set_animation(anim)
                component.set_position(seconds,False)
                component.override_animation_data(anim,False,False,seconds,0.0)
                component.set_position(seconds,False)
                component.set_play_rate(0.0)
            elif ASSEMBLY_BP:
                component.set_animation(None)
                component.override_animation_data(None,False,False,0.0,0.0)
            camera=unreal.Vector(0,170,102) if view=='front' else unreal.Vector(170,0,102)
            target=unreal.Vector(0,0,94)
            if FACE_REVIEW or view.startswith('face-'):
                view_name = view.removeprefix('face-')
                angle=math.radians({'front':0,'left':40,'right':-40,'side':90,'opposite':-90,'back':180}[view_name])
                camera=unreal.Vector(48*math.sin(angle),48*math.cos(angle),174)
                target=unreal.Vector(0,0,169)
            editor.set_level_viewport_camera_info(camera,unreal.MathLibrary.find_look_at_rotation(camera,target))
            state.update(phase='capture',since=time.monotonic())
        elif state['phase']=='capture' and elapsed>3:
            bones={}
            for i in range(component.get_num_bones()):
                bone=component.get_bone_name(i)
                t=component.get_socket_transform(bone,unreal.RelativeTransformSpace.RTS_COMPONENT)
                bones[str(bone)]={'position':[t.translation.x,t.translation.y,t.translation.z],'rotation':[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],'scale':[t.scale3d.x,t.scale3d.y,t.scale3d.z]}
            file=name+'-'+view+'.png'
            attachments = []
            if ASSEMBLY_BP:
                for part in actor.get_components_by_class(unreal.StaticMeshComponent):
                    socket = str(part.get_attach_socket_name())
                    if socket not in ('','None'):
                        bone = component.get_socket_transform(socket,unreal.RelativeTransformSpace.RTS_WORLD)
                        expected = unreal.MathLibrary.transform_location(bone,part.get_relative_transform().translation)
                        actual = part.get_world_location()
                        attachments.append({'mesh':part.static_mesh.get_path_name(),'socket':socket,'location':str(actual),'error_cm':(expected-actual).length(),'world_transform':str(part.get_world_transform())})
            state['records'].append({'pose':name,'view':view,'seconds':seconds,'actual_position':component.get_position(),'animation':anim_name,'material':component.get_material(0).get_path_name(),'image':file,'bones':bones,'attachments':attachments})
            state.update(phase='wait',since=time.monotonic())
            unreal.AutomationLibrary.take_high_res_screenshot(1100,1000,str(OUT/file))
        elif state['phase']=='wait' and elapsed>2:
            file=state['records'][-1]['image']
            if not (OUT/file).is_file():
                raise RuntimeError('Screenshot missing '+file)
            state.update(index=state['index']+1,phase='set',since=time.monotonic())
    except Exception as error:
        finish(str(error))

handle=unreal.register_slate_post_tick_callback(tick)
