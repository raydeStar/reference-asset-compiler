"""Transport existing head albedo to a bounded body seam via nearest surface UVs.

Creates a mesh colour attribute, not a new portrait or painted atlas. Original
geometry, UVs, weights, head texture and body texture remain unchanged.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from reference_asset_compiler.neck_transition import geometry_seam_weight, srgb_to_linear, validate_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('recipe',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    cfg = json.loads(args.recipe.resolve().read_text())
    validate_config(cfg)
    dest = args.output.resolve()
    if dest.exists():
        raise RuntimeError('Keep existing seam evidence; choose a fresh output')
    paths = {k:(ROOT/cfg[k]).resolve() for k in ('source_blend','body_texture','head_texture')}
    hashes = {k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()}
    for key in paths:
        if cfg.get(key+'_sha256') and hashes[key]!=cfg[key+'_sha256']:
            raise RuntimeError('Changed authority: '+key)
    bpy.ops.wm.open_mainfile(filepath=str(paths['source_blend']))
    body, head = [bpy.data.objects[cfg[k+'_object']] for k in ('body','head')]
    def fingerprint():
        rig = next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
        payload = {'bones':[(b.name,b.parent.name if b.parent else None,[list(r) for r in b.matrix_local]) for b in rig.data.bones]}
        for obj in (body,head):
            mesh=obj.data
            payload[obj.name]={'vertices':[(list(v.co),[(g.group,g.weight) for g in v.groups]) for v in mesh.vertices],
                'faces':[list(p.vertices) for p in mesh.polygons], 'uv':[list(loop.uv) for loop in mesh.uv_layers.active.data],
                'normals':[list(n.vector) for n in mesh.corner_normals], 'matrix':[list(r) for r in obj.matrix_world]}
        return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    before = fingerprint()
    if len(body.data.uv_layers)!=1:
        raise RuntimeError('Normal transport requires one source UV channel; do not overwrite existing auxiliary UVs')
    source_uv_name=body.data.uv_layers.active.name
    # The approved body contains ngons. Derive per-corner UV frames from its
    # evaluated loop triangles without triangulating the protected mesh.
    body.data.calc_loop_triangles()
    frames={i:[Vector((0,0,0)),Vector((0,0,0))] for i in range(len(body.data.loops))}
    for triangle in body.data.loop_triangles:
        a,b,c=[body.data.vertices[i].co for i in triangle.vertices]
        u,v,w=[body.data.uv_layers.active.data[i].uv for i in triangle.loops]
        e1,e2=b-a,c-a
        d1,d2=v-u,w-u
        determinant=d1.x*d2.y-d1.y*d2.x
        if abs(determinant)<1e-12:
            continue
        t=(e1*d2.y-e2*d1.y)/determinant
        bt=(e2*d1.x-e1*d2.x)/determinant
        for index in triangle.loops:
            frames[index][0]+=t
            frames[index][1]+=bt
    normal_xy=body.data.uv_layers.new(name='RAC_HeadNormalXY')
    normal_z=body.data.uv_layers.new(name='RAC_HeadNormalZ')
    body.data.uv_layers.active_index=0
    def texture(path):
        im = bpy.data.images.load(str(path),check_existing=True)
        return np.asarray(im.pixels[:],dtype=np.float32).reshape(im.size[1],im.size[0],4)
    _body_pixels, head_pixels = texture(paths['body_texture']),texture(paths['head_texture'])
    def sample(pixels, uv):
        y = min(pixels.shape[0]-1,max(0,int(uv.y*pixels.shape[0])))
        x = min(pixels.shape[1]-1,max(0,int(uv.x*pixels.shape[1])))
        return pixels[y,x,:3]
    head.data.calc_loop_triangles()
    points = [head.matrix_world@v.co for v in head.data.vertices]
    triangles = list(head.data.loop_triangles)
    tree = BVHTree.FromPolygons(points,[tuple(t.vertices) for t in triangles],all_triangles=True)
    attribute = body.data.color_attributes.new(name=cfg['attribute'],type='FLOAT_COLOR',domain='CORNER')
    body.data.color_attributes.active_color = attribute
    body.data.color_attributes.render_color_index = len(body.data.color_attributes)-1
    weights=[]
    for loop in body.data.loops:
        point = body.matrix_world@body.data.vertices[loop.vertex_index].co
        hit, normal, index, distance = tree.find_nearest(point)
        if index is None:
            attribute.data[loop.index].color=(0,0,0,0)
            continue
        triangle = triangles[index]
        uv_corners = [Vector((*head.data.uv_layers.active.data[i].uv,0)) for i in triangle.loops]
        uv = barycentric_transform(hit,*[points[i] for i in triangle.vertices],*uv_corners)
        target = tuple(srgb_to_linear(float(c)) for c in sample(head_pixels,uv))
        head_normals=[(head.matrix_world.to_3x3().inverted().transposed()@head.data.corner_normals[i].vector).normalized() for i in triangle.loops]
        mapped_normal=barycentric_transform(hit,*[points[i] for i in triangle.vertices],*head_normals).normalized()
        local_normal=(body.matrix_world.to_3x3().transposed()@mapped_normal).normalized()
        normal=body.data.corner_normals[loop.index].vector
        tangent=(frames[loop.index][0]-normal*normal.dot(frames[loop.index][0])).normalized()
        if tangent.length<.5:
            tangent=normal.orthogonal().normalized()
        sign=1 if normal.cross(tangent).dot(frames[loop.index][1])>=0 else -1
        bitangent=normal.cross(tangent)*sign
        tangent_normal=Vector((local_normal.dot(tangent),local_normal.dot(bitangent),local_normal.dot(normal))).normalized()
        # A blue triangle corner can enclose a skin-coloured texel. Classify
        # skin per pixel in the shader, not sparsely at the mesh's corners.
        weight = geometry_seam_weight(point,distance,cfg)
        # Unused per-corner normals would split vertices across the whole coat
        # during FBX import. Constant auxiliary UVs outside the mask avoid that.
        normal_xy.data[loop.index].uv=tangent_normal.xy if weight>0 else (0,0)
        normal_z.data[loop.index].uv=(tangent_normal.z,0) if weight>0 else (1,0)
        attribute.data[loop.index].color=(*target,weight)
        weights.append(weight)
    # This preview shader mirrors the runtime lerp. The canonical textures are
    # inputs only; all seam information lives in the mesh's colour attribute.
    original = body.data.materials[0]
    material = original.copy()
    material.name='M_NeckTransfer_Preview'
    body.data.materials[0]=material
    nodes, links = material.node_tree.nodes,material.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    base = bsdf.inputs['Base Color'].links[0].from_socket
    color = nodes.new('ShaderNodeVertexColor')
    color.layer_name=cfg['attribute']
    separate = nodes.new('ShaderNodeSeparateColor')
    links.new(base,separate.inputs['Color'])
    masks=[]
    for numerator,denominator,low,high in [('Red','Green',1.25,1.6),('Blue','Red',.08,.18)]:
        divide=nodes.new('ShaderNodeMath')
        divide.operation='DIVIDE'
        links.new(separate.outputs[numerator],divide.inputs[0])
        links.new(separate.outputs[denominator],divide.inputs[1])
        feather=nodes.new('ShaderNodeMapRange')
        feather.interpolation_type='SMOOTHSTEP'
        feather.inputs['From Min'].default_value=low
        feather.inputs['From Max'].default_value=high
        links.new(divide.outputs[0],feather.inputs['Value'])
        masks.append(feather.outputs[0])
    alpha=color.outputs['Alpha']
    geometry=nodes.new('ShaderNodeNewGeometry')
    xyz=nodes.new('ShaderNodeSeparateXYZ')
    links.new(geometry.outputs['Position'],xyz.inputs[0])
    height=nodes.new('ShaderNodeMapRange')
    height.interpolation_type='SMOOTHSTEP'
    height.inputs['From Min'].default_value=cfg['pixel_fade_bottom_m'][0]
    height.inputs['From Max'].default_value=cfg['pixel_fade_bottom_m'][1]
    links.new(xyz.outputs['Z'],height.inputs['Value'])
    masks.append(height.outputs[0])
    for mask in masks:
        multiply=nodes.new('ShaderNodeMath')
        multiply.operation='MULTIPLY'
        links.new(alpha,multiply.inputs[0])
        links.new(mask,multiply.inputs[1])
        alpha=multiply.outputs[0]
    mix = nodes.new('ShaderNodeMixRGB')
    mix.blend_type='MIX'
    links.new(base,mix.inputs[1])
    links.new(color.outputs['Color'],mix.inputs[2])
    links.new(alpha,mix.inputs[0])
    links.new(mix.outputs[0],bsdf.inputs['Base Color'])
    for name,target in [('Roughness',cfg['target_roughness']),('Metallic',cfg['target_metallic'])]:
        socket=bsdf.inputs[name]
        if socket.is_linked:
            scalar=nodes.new('ShaderNodeMixRGB')
            scalar.blend_type='MIX'
            links.new(socket.links[0].from_socket,scalar.inputs[1])
            scalar.inputs[2].default_value=(target,target,target,1)
            links.new(alpha,scalar.inputs[0])
            links.new(scalar.outputs[0],socket)
    normal_input=bsdf.inputs['Normal']
    if normal_input.is_linked:
        transported=[]
        for uv_name in ('RAC_HeadNormalXY','RAC_HeadNormalZ'):
            uv_node=nodes.new('ShaderNodeUVMap')
            uv_node.uv_map=uv_name
            split=nodes.new('ShaderNodeSeparateXYZ')
            links.new(uv_node.outputs[0],split.inputs[0])
            transported.append(split)
        combine=nodes.new('ShaderNodeCombineXYZ')
        for source_socket,pin in [(transported[0].outputs['X'],'X'),(transported[0].outputs['Y'],'Y'),(transported[1].outputs['X'],'Z')]:
            encode=nodes.new('ShaderNodeMath')
            encode.operation='MULTIPLY_ADD'
            links.new(source_socket,encode.inputs[0])
            encode.inputs[1].default_value=.5
            encode.inputs[2].default_value=.5
            links.new(encode.outputs[0],combine.inputs[pin])
        target_normal=nodes.new('ShaderNodeNormalMap')
        target_normal.uv_map=source_uv_name
        links.new(combine.outputs[0],target_normal.inputs['Color'])
        normal_mix=nodes.new('ShaderNodeMixRGB')
        normal_mix.blend_type='MIX'
        links.new(normal_input.links[0].from_socket,normal_mix.inputs[1])
        links.new(target_normal.outputs[0],normal_mix.inputs[2])
        links.new(alpha,normal_mix.inputs[0])
        links.new(normal_mix.outputs[0],normal_input)
    dest.mkdir(parents=True)
    after = fingerprint()
    if before != after:
        raise RuntimeError('Seam transport altered geometry, UV, normal, rig or weights')
    bpy.ops.wm.save_as_mainfile(filepath=str(dest/'assembly-fit.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active=rig
    fbx=dest/'ayric_body.fbx'
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,path_mode='RELATIVE',embed_textures=False,
        apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',global_scale=1.,apply_unit_scale=True,
        bake_anim=False,add_leaf_bones=False,object_types={'ARMATURE','MESH'},use_armature_deform_only=False,
        primary_bone_axis='Y',secondary_bone_axis='X',mesh_smooth_type='FACE',colors_type='LINEAR')
    report={'schema':cfg['schema'],'status':'candidate_pending_native_review','recipe':str(args.recipe.resolve()),
        'recipe_sha256':hashlib.sha256(args.recipe.read_bytes()).hexdigest(),'input_hashes':hashes,
        'fbx_sha256':hashlib.sha256(fbx.read_bytes()).hexdigest(),'attribute':cfg['attribute'],
        'affected_corners':int(sum(w>0 for w in weights)),'maximum_weight':float(max(weights)),'geometry_uv_weights_changed':False,
        'texture_images_changed':False,'face_authority_changed':False,'color_encoding':'linear RGBA, FBX LINEAR, UE Replace vertex colors'}
    report.update({'ok':before==after,'before_fingerprint':before,'after_fingerprint':after,
        'body_fbx_sha256':report['fbx_sha256'],'body_blend':str(dest/'assembly-fit.blend'),
        'implementation_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__).resolve(),ROOT/'src/reference_asset_compiler/neck_transition.py')},
        'neck_normal_policy':'Transfer matched head surface normal via auxiliary UV1/UV2, blend only in the skin mask',
        'added_uv_channels':['RAC_HeadNormalXY','RAC_HeadNormalZ'],'source_uv0_unchanged':True})
    (dest/'neck-transfer.json').write_text(json.dumps(report,indent=2))
    print('NECK_TRANSFER_READY '+str(dest)+' -- a seam allowance, not another face.')


if __name__=='__main__':
    main()
