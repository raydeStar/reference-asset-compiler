"""Import a versioned character review without replacing the playable character.

Call main(fbx_path, groom_path, fresh_content_folder, receipt_path, name=<asset
prefix>) from the editor's Python bridge. ``name`` is the character profile's
asset_prefix: it finds the build's materials (<name>_Source_Outfit, <name>_teeth,
...) and names the assets (SK_<name>_Review, G_<name>_Review, BP_<name>_Review).
``eye_texture`` is the imported texture the eyes' material samples. This is an
import check, never a production promotion.
"""
import hashlib
import json
from pathlib import Path

import unreal


def import_groom(groom, destination, name):
    hair = unreal.AssetImportTask()
    hair.filename = str(Path(groom).resolve())
    hair.destination_path = destination
    hair.destination_name = f"G_{name}_Review"
    hair.automated = True
    hair.replace_existing = False
    hair.save = True
    # GroomFactory creates empty card assets. HairStrandsFactory reads Alembic.
    hair.factory = unreal.HairStrandsFactory()
    hair_options = unreal.GroomImportOptions()
    conversion = unreal.GroomConversionSettings()
    # Blender Alembic is Y-up: (x,z,-y). Match the FBX's X-wide, Z-up frame.
    conversion.scale = unreal.Vector(100, 100, -100)
    conversion.rotation = unreal.Vector(-90, 0, 0)
    hair_options.conversion_settings = conversion
    hair.options = hair_options
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([hair])
    grooms = [obj for obj in hair.get_objects() if isinstance(obj, unreal.GroomAsset)]
    if len(grooms) != 1:
        raise RuntimeError("No GroomAsset was imported")
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        f"MI_{name}_Hair", destination, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    unreal.MaterialEditingLibrary.set_material_instance_parent(mat, unreal.load_asset('/HairStrands/Materials/HairDefaultMaterial'))
    unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mat, 'Color', unreal.LinearColor(.09, .033, .013, 1))
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mat, 'Roughness', .48)
    slot = unreal.HairGroupsMaterial()
    slot.set_editor_property('material', mat)
    slot.set_editor_property('slot_name', 'Hair')
    grooms[0].hair_groups_materials = [slot]
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(grooms[0])
    return grooms[0]


def configure_body_materials(mesh, destination, prefix, eye_texture):
    """Explicit base-colour shaders avoid FBX Phong/emission conversion surprises."""
    editor = unreal.MaterialEditingLibrary
    textures = {prefix + '_Source_Outfit': ('body_basecolor', .78), 'skin': ('head_basecolor', .65),
                'eyes': (eye_texture, .22), prefix + '_teeth': ('teeth', .38),
                prefix + '_tongue': ('tongue01_diffuse', .55)}
    slots = list(mesh.materials)
    for slot in slots:
        name = str(slot.material_slot_name)
        material_name = 'M_Review_' + name.replace('-', '_')
        mat = unreal.load_asset(destination + '/' + material_name)
        if mat:
            editor.delete_all_material_expressions(mat)
        else:
            mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(material_name,
                destination, unreal.Material, unreal.MaterialFactoryNew())
        editor.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
        roughness = .8
        if name in textures:
            texture_name, roughness = textures[name]
            node = editor.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, 0)
            node.texture = (editor.get_material_instance_texture_parameter_value(slot.material_interface, 'DiffuseColorMap')
                            if isinstance(slot.material_interface, unreal.MaterialInstanceConstant) else None)
            if not node.texture:
                node.texture = unreal.load_asset(destination + '/' + texture_name)
            if not node.texture and name == 'eyes':
                node.texture = unreal.load_asset(destination + '/head-front')
            if not node.texture:
                raise RuntimeError('Missing imported base colour: ' + texture_name)
            editor.connect_material_property(node, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
        else:
            node = editor.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
            colour = (.006, .0015, .001) if name == prefix + '_Mouth_Interior' else (.055, .020, .008)
            node.constant = unreal.LinearColor(*colour, 1)
            editor.connect_material_property(node, '', unreal.MaterialProperty.MP_BASE_COLOR)
        rough = editor.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 160)
        rough.r = roughness
        editor.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
        editor.recompile_material(mat)
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
        slot.material_interface = mat
    mesh.materials = slots
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)


def assemble_blueprint(mesh, groom, destination, name):
    binding = unreal.GroomLibrary.create_new_groom_binding_asset_with_path(
        destination + f'/GB_{name}_Review', groom, mesh, 100, None, 0)
    if not binding:
        raise RuntimeError('Groom binding creation failed')
    unreal.EditorAssetLibrary.save_loaded_asset(binding)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', unreal.Actor)
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(f'BP_{name}_Review', destination, unreal.Blueprint, factory)
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    root = subsystem.k2_gather_subobject_data_for_blueprint(bp)[0]

    def component(parent, cls):
        params = unreal.AddNewSubobjectParams()
        params.set_editor_property('parent_handle', parent)
        params.set_editor_property('new_class', cls)
        params.set_editor_property('blueprint_context', bp)
        handle, reason = subsystem.add_new_subobject(params)
        if str(reason):
            raise RuntimeError(str(reason))
        return handle, library.get_object_for_blueprint(library.get_data(handle), bp)

    body_handle, body = component(root, unreal.SkeletalMeshComponent)
    body.set_skeletal_mesh_asset(mesh)
    body.set_editor_property('skin_cache_usage', [unreal.SkinCacheUsage.ENABLED])
    body.set_update_animation_in_editor(True)
    _, hair = component(body_handle, unreal.GroomComponent)
    hair.set_groom_asset(groom)
    hair.set_binding_asset(binding)
    settings = hair.get_editor_property('simulation_settings')
    settings.set_editor_property('override_settings', True)
    hair.set_editor_property('simulation_settings', settings)
    hair.set_enable_simulation(False)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    unreal.EditorAssetLibrary.save_loaded_asset(bp)
    return bp, binding


def main(fbx, groom, destination, receipt, name="Character", eye_texture="head-front"):
    if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        raise RuntimeError("Stop PIE before importing the review")
    if unreal.EditorAssetLibrary.does_directory_exist(destination):
        raise RuntimeError("Choose a fresh review folder; retained candidates are evidence")
    options = unreal.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    options.import_as_skeletal = True
    options.import_mesh = True
    options.import_materials = True
    options.import_textures = True
    options.import_animations = False
    options.create_physics_asset = False
    options.skeletal_mesh_import_data.set_editor_property("import_morph_targets", True)
    options.skeletal_mesh_import_data.import_uniform_scale = 1.0
    options.skeletal_mesh_import_data.convert_scene = True
    options.skeletal_mesh_import_data.force_front_x_axis = False
    options.skeletal_mesh_import_data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    unreal.EditorAssetLibrary.make_directory(destination)
    task = unreal.AssetImportTask()
    task.filename = str(Path(fbx).resolve())
    task.destination_path = destination
    task.destination_name = f"SK_{name}_Review"
    task.automated = True
    task.replace_existing = False
    task.save = True
    task.options = options
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    tools.import_asset_tasks([task])
    meshes = [obj for obj in task.get_objects() if isinstance(obj, unreal.SkeletalMesh)]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one assembled skeletal mesh, got {len(meshes)}")
    mesh = meshes[0]
    configure_body_materials(mesh, destination, name, eye_texture)
    groom_asset = import_groom(groom, destination, name)
    blueprint, binding = assemble_blueprint(mesh, groom_asset, destination, name)
    result = {
        "inputs": {name: {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                   for name, path in (("fbx", fbx), ("groom", groom))},
        "skeletal_mesh": mesh.get_path_name(), "groom": groom_asset.get_path_name(),
        "review_blueprint": blueprint.get_path_name(), "groom_binding": binding.get_path_name(),
        "binding_groups": [{key: group.get_editor_property(key)
                            for key in ('ren_root_count', 'sim_root_count', 'ren_lod_count')}
                           for group in binding.get_editor_property('group_infos')],
        "morph_targets": [target.get_name() for target in mesh.get_editor_property("morph_targets")],
        "material_slots": [str(mat.material_slot_name) for mat in mesh.materials],
        "groom_groups": [{"curves": group.get_editor_property("num_curves"),
                           "points": group.get_editor_property("num_curve_vertices"),
                           "guides": group.get_editor_property("num_guides")}
                          for group in groom_asset.get_editor_property("hair_groups_info")],
        "imported": True, "render_verified": False, "runtime_verified": False, "production_ready": False,
        "hair_colour_note": "Native per-strand colours remain in Blender. Alembic strips that custom colour attribute; UE uses an explicit brown review material.",
    }
    Path(receipt).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
