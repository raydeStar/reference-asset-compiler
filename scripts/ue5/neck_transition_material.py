"""Add a bounded vertex-colour neck transition to a COPY of an existing PBR material."""
import unreal


def build_material(original, folder, config):
    lib, edit = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    master = lib.duplicate_asset(original.get_base_material().get_path_name(),folder+'/M_NeckTransition')
    instance = lib.duplicate_asset(original.get_path_name(),folder+'/MI_NeckTransition')
    if not master or not instance:
        raise RuntimeError('Could not duplicate the original material authorities')
    edit.set_material_instance_parent(instance,master)
    props = [unreal.MaterialProperty.MP_BASE_COLOR,unreal.MaterialProperty.MP_ROUGHNESS,unreal.MaterialProperty.MP_METALLIC]
    sources = [(edit.get_material_property_input_node(master,p),edit.get_material_property_input_node_output_name(master,p)) for p in props]
    if any(node is None for node,_ in sources):
        raise RuntimeError('The source PBR material must connect base colour, roughness and metallic')
    vertex = edit.create_material_expression(master,unreal.MaterialExpressionVertexColor)
    position = edit.create_material_expression(master,unreal.MaterialExpressionPreSkinnedPosition)
    interpolator = edit.create_material_expression(master,unreal.MaterialExpressionVertexInterpolator)
    mask = edit.create_material_expression(master,unreal.MaterialExpressionCustom)
    inputs=[]
    for name in ('Base','Weight','Position'):
        item=unreal.CustomInput()
        item.set_editor_property('input_name',name)
        inputs.append(item)
    mask.set_editor_property('inputs',inputs)
    mask.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    low, high = [v*100 for v in config['pixel_fade_bottom_m']]
    mask.set_editor_property('code',f'return Weight * smoothstep(1.25,1.6,Base.r/max(Base.g,0.000001)) * smoothstep(0.08,0.18,Base.b/max(Base.r,0.000001)) * smoothstep({low},{high},Position.z);')
    def connect(source, output, target, pin):
        if not edit.connect_material_expressions(source,output,target,pin):
            raise RuntimeError('Material connection failed: '+pin)
    connect(*sources[0],mask,'Base')
    connect(vertex,'A',mask,'Weight')
    # Pre-skinned position is vertex-only; interpolate the rest-space position
    # rather than making the neck mask drift with world-space animation.
    connect(position,'',interpolator,'')
    connect(interpolator,'',mask,'Position')
    for index, prop in enumerate(props):
        lerp = edit.create_material_expression(master,unreal.MaterialExpressionLinearInterpolate)
        connect(*sources[index],lerp,'A')
        if index == 0:
            connect(vertex,'',lerp,'B')
        else:
            lerp.set_editor_property('const_b',config['target_roughness' if index==1 else 'target_metallic'])
        connect(mask,'',lerp,'Alpha')
        if not edit.connect_material_property(lerp,'',prop):
            raise RuntimeError('Material property connection failed')
    normal_prop = unreal.MaterialProperty.MP_NORMAL
    normal_source = edit.get_material_property_input_node(master,normal_prop)
    normal_output = edit.get_material_property_input_node_output_name(master,normal_prop)
    if normal_source:
        normal_uvs=[]
        for channel in (1,2):
            uv=edit.create_material_expression(master,unreal.MaterialExpressionTextureCoordinate)
            uv.set_editor_property('coordinate_index',channel)
            normal_uvs.append(uv)
        flat=edit.create_material_expression(master,unreal.MaterialExpressionCustom)
        normal_inputs=[]
        for name in ('XY','Z'):
            item=unreal.CustomInput()
            item.set_editor_property('input_name',name)
            normal_inputs.append(item)
        flat.set_editor_property('inputs',normal_inputs)
        flat.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        # FBX import reverses V; UE's UV tangent Y is opposite Blender's.
        flat.set_editor_property('code','return normalize(float3(XY.x, XY.y-1.0, Z.x));')
        connect(normal_uvs[0],'',flat,'XY')
        connect(normal_uvs[1],'',flat,'Z')
        normal_mix=edit.create_material_expression(master,unreal.MaterialExpressionLinearInterpolate)
        connect(normal_source,normal_output,normal_mix,'A')
        connect(flat,'',normal_mix,'B')
        connect(mask,'',normal_mix,'Alpha')
        edit.connect_material_property(normal_mix,'',normal_prop)
    edit.recompile_material(master)
    edit.update_material_instance(instance)
    lib.save_loaded_asset(master)
    lib.save_loaded_asset(instance)
    unreal.log('NECK_MATERIAL_READY -- the face stays itself; the collar keeps its gold.')
    return instance
