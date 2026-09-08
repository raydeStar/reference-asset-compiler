"""Isolated face-material preview on the verified rig; no authority promotion."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

ROOT = Path(os.environ['RAC_ROOT'])
sys.path.insert(0,str(ROOT/'scripts/ue5'))
import swap_workshop_player as swap  # noqa: E402  (RAC_ROOT path injected above)


def main():
    version = os.environ.get('RAC_VERSION','v037')
    folder = '/Game/SunsetWorkshop/AyricPlayer/'+version
    level_path = '/Game/SunsetWorkshop/L_WorkshopNight_'+version
    lib = unreal.EditorAssetLibrary
    if lib.does_directory_exist(folder) or lib.does_asset_exist(level_path):
        raise RuntimeError('Preview destination exists')
    candidate = ROOT/'work/sunset-ayric-v2/texture/face-repair-20260906/mapped-v003'
    texture_file = candidate/'BaseColor.png'
    mapping = json.loads((candidate/'mapping.json').read_text())
    if hashlib.sha256(texture_file.read_bytes()).hexdigest() != mapping['output_sha256']:
        raise RuntimeError('Texture differs from reviewed mapping')
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    task = unreal.AssetImportTask()
    task.filename = str(texture_file)
    task.destination_path = folder+'/Materials'
    task.destination_name = 'T_AyricFace_BaseColor'
    task.automated = True
    task.replace_existing = False
    task.save = True
    tools.import_asset_tasks([task])
    texture = lib.load_asset(task.imported_object_paths[0])
    texture.set_editor_property('srgb',True)
    lib.save_loaded_asset(texture)
    mesh = lib.load_asset('/Game/SunsetWorkshop/RigRepairs/anatomical_v002/ayric_rigged')
    original = mesh.get_editor_property('materials')[0].material_interface
    material = lib.duplicate_asset(original.get_path_name(),folder+'/Materials/MI_AyricFace_Preview')
    editing = unreal.MaterialEditingLibrary
    original_orm = editing.get_material_instance_texture_parameter_value(original,'ORM')
    editing.set_material_instance_texture_parameter_value(material,'BaseColor',texture)
    editing.update_material_instance(material)
    if editing.get_material_instance_texture_parameter_value(material,'BaseColor') != texture:
        raise RuntimeError('BaseColor override did not bind')
    if editing.get_material_instance_texture_parameter_value(material,'ORM') != original_orm:
        raise RuntimeError('Scalar texture changed')
    lib.save_loaded_asset(material)
    source_folder = '/Game/SunsetWorkshop/AyricPlayer/v036'
    bp_path = folder+'/BP_WorkshopAyric_'+version
    bp = lib.duplicate_asset(source_folder+'/BP_WorkshopAyric_v036',bp_path)
    component = next(p for p in swap.blueprint_parts(bp) if isinstance(p,unreal.SkeletalMeshComponent))
    original_anim = component.get_editor_property('anim_class')
    component.set_material(0,material)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    lib.save_loaded_asset(bp)
    if component.get_editor_property('skeletal_mesh_asset') != mesh:
        raise RuntimeError('Preview changed the verified rig')
    gm_path = folder+'/BP_WorkshopGameMode_Ayric_'+version
    gm = lib.duplicate_asset(source_folder+'/BP_WorkshopGameMode_Ayric_v036',gm_path)
    unreal.get_default_object(gm.generated_class()).set_editor_property('default_pawn_class',bp.generated_class())
    unreal.BlueprintEditorLibrary.compile_blueprint(gm)
    lib.save_loaded_asset(gm)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level.new_level_from_template(level_path,'/Game/SunsetWorkshop/L_WorkshopNight_v036'):
        raise RuntimeError('Preview level failed')
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode',gm.generated_class())
    level.save_current_level()
    report = {'ok':True,'level':level_path,'blueprint':bp_path,'mesh':mesh.get_path_name(),'animation':original_anim.get_path_name(),'material':material.get_path_name(),'texture':texture.get_path_name(),'texture_sha256':mapping['output_sha256'],'original_material':original.get_path_name(),'original_orm':original_orm.get_path_name(),'geometry_rig_uv_and_orm_changed':False,'human_approved':False,'status':'isolated_demo_preview_pending_visual_review'}
    (ROOT/f'work/sunset-workshop/evidence/face-preview-{version}.json').write_text(json.dumps(report,indent=2))
    unreal.log('FACE_PREVIEW_READY -- new paint, same well-behaved knees.')


if __name__ == '__main__':
    main()
