"""Unsaved staging in the actual workshop; never hide the room or save assets."""
import json
import os
from pathlib import Path
import unreal

ROOT=Path(os.environ['RAC_ROOT'])
cfg=json.loads((ROOT/os.environ['RAC_SHOWCASE_CONFIG']).read_text())
OUT=ROOT/'work/sunset-workshop/evidence'/os.environ['RAC_RIG_REVIEW']
OUT.mkdir(parents=True,exist_ok=False)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not level.load_level(cfg['level']):
    raise RuntimeError('Workshop unavailable; the butler refuses a cardboard substitute.')
actor=actors.spawn_actor_from_class(unreal.load_asset(cfg['blueprint']).generated_class(),unreal.Vector(0,0,100))
component=actor.get_component_by_class(unreal.SkeletalMeshComponent)
component.set_world_transform(unreal.Transform(location=unreal.Vector(*cfg['character_location']),rotation=unreal.Rotator(yaw=cfg['character_yaw'])),False,True)
component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
component.set_skeletal_mesh_asset(unreal.load_asset(cfg['mesh']))
component.set_forced_lod(1)
component.set_update_animation_in_editor(True)
if cfg.get('portrait_fill'):
    fill=cfg['portrait_fill']
    position=unreal.Vector(*fill['location'])
    target=unreal.Vector(*fill['target'])
    lamp=actors.spawn_actor_from_class(unreal.RectLight,position,unreal.MathLibrary.find_look_at_rotation(position,target))
    light=lamp.get_component_by_class(unreal.RectLightComponent)
    light.set_editor_property('intensity_units',unreal.LightUnits.LUMENS)
    light.set_intensity(fill['lumens'])
    light.set_attenuation_radius(350)
    light.set_source_width(120)
    light.set_source_height(120)
    light.set_light_color(unreal.LinearColor(1,.85,.7,1))
level.editor_set_game_view(True)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
