"""Attach the existing AI head to a source-preserving body derivative.

The verified v036 skeleton and animations remain authoritative. New assets
only; rigid head attachment is not a facial deformation rig.
"""
import hashlib
import json
import os
import sys
from pathlib import Path
import unreal

ROOT = Path(os.environ['RAC_ROOT'])
sys.path.insert(0,str(ROOT/'scripts/ue5'))
import import_asset  # noqa: E402  (RAC_ROOT path injected above)
import swap_workshop_player as swap  # noqa: E402  (RAC_ROOT path injected above)

def main():
    version = os.environ.get('RAC_VERSION','v038')
    folder = '/Game/SunsetWorkshop/AyricPlayer/'+version
    mesh_folder = os.environ.get('RAC_ASSEMBLY_MESH_FOLDER','/Game/SunsetWorkshop/RigRepairs/head_assembly_v006')
    level_path = '/Game/SunsetWorkshop/L_WorkshopNight_'+version
    lib = unreal.EditorAssetLibrary
    reuse = os.environ.get('RAC_REUSE_ASSEMBLY_MESH') == '1'
    if lib.does_directory_exist(folder) or (lib.does_directory_exist(mesh_folder) and not reuse):
        raise RuntimeError('Assembly destination exists; retain previous candidates')
    job = ROOT/os.environ.get('RAC_ASSEMBLY_JOB','work/sunset-ayric-v2/rig/head-assembly-v006')
    neck = (job/'neck-transfer.json').is_file()
    proof = json.loads((job/('neck-transfer.json' if neck else 'subset-verification.json')).read_text())
    fbx = job/'ayric_body.fbx'
    if not proof['ok'] or hashlib.sha256(fbx.read_bytes()).hexdigest()!=proof['body_fbx_sha256']:
        raise RuntimeError('Body subset proof failed or payload changed')
    if neck and proof.get('added_uv_channels') != ['RAC_HeadNormalXY','RAC_HeadNormalZ']:
        raise RuntimeError('This native seam shader requires the colour-plus-normal transport payload')
    old_mesh = lib.load_asset('/Game/SunsetWorkshop/RigRepairs/anatomical_v002/ayric_rigged')
    skeleton = old_mesh.get_editor_property('skeleton')
    manifest = json.loads((ROOT/'out/sunset-ayric-v2-production/sunset-ayric-v2-production.ue5import.json').read_text(encoding='utf-8-sig'))
    task = import_asset.build_skeletal_task(str(fbx),mesh_folder,manifest)
    task.replace_existing = False
    task.options.set_editor_property('skeleton',skeleton)
    task.options.create_physics_asset = False
    if neck:
        task.options.skeletal_mesh_import_data.set_editor_property('vertex_color_import_option',unreal.VertexColorImportOption.REPLACE)
    if not reuse:
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh_path = import_asset.find_skeletal_mesh(mesh_folder)
    mesh = lib.load_asset(mesh_path)
    if mesh.get_editor_property('skeleton') != skeleton:
        raise RuntimeError('Imported body did not reuse the verified skeleton')
    if not reuse:
        material = old_mesh.get_editor_property('materials')[0].material_interface
        if neck:
            from neck_transition_material import build_material
            recipe = Path(proof['recipe'])
            if hashlib.sha256(recipe.read_bytes()).hexdigest()!=proof['recipe_sha256']:
                raise RuntimeError('Seam recipe changed after transport')
            material = build_material(material,mesh_folder,json.loads(recipe.read_text()))
        import_asset.assign_materials(mesh_path,{},material)
        mesh.set_editor_property('physics_asset',old_mesh.get_editor_property('physics_asset'))
        import_asset.build_lods(mesh_path,manifest['lods'])
        lib.save_loaded_asset(mesh)
    buffers = json.loads(unreal.RacEditorBridgeLibrary.inspect_skeletal_seam_buffers(mesh)) if neck else None
    if neck and (not buffers.get('ok') or buffers['vertices']>15000 or buffers['colors']!=buffers['vertices'] or buffers['nonzero_alpha']==0):
        raise RuntimeError('Native seam buffer coverage or vertex budget failed: '+str(buffers))
    source = '/Game/SunsetWorkshop/AyricPlayer/v036'
    bp_path = folder+'/BP_WorkshopAyric_'+version
    bp = lib.duplicate_asset(source+'/BP_WorkshopAyric_v036',bp_path)
    parts = swap.blueprint_parts(bp)
    body = next(p for p in parts if isinstance(p,unreal.SkeletalMeshComponent))
    body.set_skeletal_mesh_asset(mesh)
    body.set_editor_property('override_materials',[])
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    fn = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sub.k2_gather_subobject_data_for_blueprint(bp)
    parent = next(h for h in handles if isinstance(fn.get_object_for_blueprint(fn.get_data(h),bp),unreal.SkeletalMeshComponent))
    handle, reason = sub.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=parent,new_class=unreal.StaticMeshComponent,blueprint_context=bp))
    head = fn.get_object_for_blueprint(fn.get_data(handle),bp)
    if not isinstance(head,unreal.StaticMeshComponent):
        raise RuntimeError('Head component creation failed: '+str(reason))
    sub.rename_subobject(handle,'WorkshopAyricHead')
    head_mesh = lib.load_asset('/Game/Compiled/SunsetAyricRigidHeadV1Production/sunset-ayric-rigid-head-v1-production')
    head.set_static_mesh(head_mesh)
    head.set_collision_profile_name('NoCollision')
    head.set_mobility(unreal.ComponentMobility.MOVABLE)
    if not unreal.RacEditorBridgeLibrary.set_blueprint_component_socket(bp,'WorkshopAyricHead','head'):
        raise RuntimeError('Persistent head socket assignment failed')
    head = next(p for p in swap.blueprint_parts(bp) if isinstance(p,unreal.StaticMeshComponent) and p.get_editor_property('static_mesh') == head_mesh)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    temp = actors.spawn_actor_from_class(bp.generated_class(),unreal.Vector(),unreal.Rotator())
    try:
        sk = temp.get_component_by_class(unreal.SkeletalMeshComponent)
        # A spawned character immediately evaluates idle. Fit against the bind
        # pose instead, or that idle offset becomes a permanent neck error.
        sk.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        sk.set_animation(None)
        sk.override_animation_data(None,False,False,0.0,0.0)
        bone = sk.get_socket_transform('head',unreal.RelativeTransformSpace.RTS_WORLD)
        # Matched native views establish the static and skeletal local facing.
        # Compose the measured 152 cm placement with the actual body frame.
        body_world = sk.get_world_transform()
        desired = unreal.Transform(location=unreal.MathLibrary.transform_location(body_world,unreal.Vector(0,0,152)),
            rotation=body_world.rotation.rotator(),scale=unreal.Vector(1,1,1))
        relative = unreal.MathLibrary.make_relative_transform(desired,bone)
        head.set_editor_property('relative_location',relative.translation)
        head.set_editor_property('relative_rotation',relative.rotation.rotator())
        head.set_editor_property('relative_scale3d',relative.scale3d)
    finally:
        actors.destroy_actor(temp)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    lib.save_loaded_asset(bp)
    gm_path = folder+'/BP_WorkshopGameMode_Ayric_'+version
    gm = lib.duplicate_asset(source+'/BP_WorkshopGameMode_Ayric_v036',gm_path)
    unreal.get_default_object(gm.generated_class()).set_editor_property('default_pawn_class',bp.generated_class())
    unreal.BlueprintEditorLibrary.compile_blueprint(gm)
    lib.save_loaded_asset(gm)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level.new_level_from_template(level_path,'/Game/SunsetWorkshop/L_WorkshopNight_v036'):
        raise RuntimeError('Assembly map creation failed')
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode',gm.generated_class())
    level.save_current_level()
    report = {'ok':True,'status':'assembly_candidate_pending_motion_and_cook','level':level_path,'blueprint':bp_path,
        'mesh':mesh_path,'head_mesh':head_mesh.get_path_name(),'head_socket':'head','head_relative':str(relative),
        'animation':body.get_editor_property('anim_class').get_path_name(),'skeleton':skeleton.get_path_name(),
        'body_subset':proof,'human_approved':False,'facial_rig':False,
        'native_seam_buffers':buffers,
        'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'material_builder_sha256':hashlib.sha256((ROOT/'scripts/ue5/neck_transition_material.py').read_bytes()).hexdigest() if neck else None}
    (ROOT/f'work/sunset-workshop/evidence/head-assembly-{version}.json').write_text(json.dumps(report,indent=2))
    unreal.log('HEAD_ASSEMBLY_READY -- the portrait finally has a skull to agree with.')

if __name__=='__main__':
    main()
