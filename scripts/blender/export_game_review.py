"""Game review step 5: the finished blend as a centimetre FBX for Unreal, and its textures by material slot.

blender -b <game.blend> --python export_game_review.py -- <job.json>

Unreal works in centimetres. The 100x goes into the bones and vertices themselves (unit scale 0.01, objects scaled
100 and applied): a scale left on the armature node is reset by retargeted animation, and Remora shrank to 1 cm in
every clip. Axes and bone axes match rig_from_landmarks.py and manny_axes.py (forward -Y, up Z, primary bone Y).
Vertex colours go as LINEAR so the scatter mask arrives as written.

<textures>/textures.json: per material, base colour / roughness / metallic / normal / alpha files and constants, and
the base colour's mean linear luminance (a look can scale specular by base brightness against it).
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

job = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
fbx, tex = Path(job['paths']['fbx']), Path(job['paths']['textures'])
fbx.parent.mkdir(parents=True, exist_ok=True)
tex.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type in ('ARMATURE', 'MESH'):
        o.select_set(True)
bpy.context.scene.unit_settings.scale_length = 0.01
bpy.context.view_layer.objects.active = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
for o in bpy.context.selected_objects:
    if o.parent is None:
        o.scale = (100, 100, 100)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
bpy.ops.export_scene.fbx(
    filepath=str(fbx.resolve()), use_selection=True, path_mode='RELATIVE', embed_textures=False,
    apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', global_scale=1.0,
    apply_unit_scale=True, bake_anim=False, add_leaf_bones=False,
    object_types={'ARMATURE', 'MESH'}, use_armature_deform_only=False,
    primary_bone_axis='Y', secondary_bone_axis='X', mesh_smooth_type='FACE', colors_type='LINEAR')


def linked_image(socket):
    for link in socket.links:
        node = link.from_node
        while node.type != 'TEX_IMAGE' and node.inputs and any(i.links for i in node.inputs):
            node = next(i for i in node.inputs if i.links).links[0].from_node
        if node.type == 'TEX_IMAGE' and node.image:
            return node.image
    return None


def save(image, name):
    path = tex / f'{name}.png'
    copy = image.copy()
    copy.filepath_raw = str(path)
    copy.file_format = 'PNG'
    copy.save()
    bpy.data.images.remove(copy)
    return path.name


def mean_linear_luminance(image):
    px = np.empty(image.size[0] * image.size[1] * image.channels, np.float32)
    image.pixels.foreach_get(px)
    px = px.reshape(-1, image.channels)[:, :3]
    if not image.is_float and image.colorspace_settings.name == 'sRGB':      # byte images come back encoded
        px = np.where(px <= 0.04045, px / 12.92, ((px + 0.055) / 1.055) ** 2.4)
    return float((px @ np.array([0.2126, 0.7152, 0.0722], np.float32)).mean())


out = {}
for m in bpy.data.materials:
    if not m.node_tree:
        continue
    bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not bsdf:
        continue
    key = m.name.replace('.', '_')
    entry = {'roughness': bsdf.inputs['Roughness'].default_value, 'metallic': bsdf.inputs['Metallic'].default_value,
             'base_factor': list(bsdf.inputs['Base Color'].default_value)}
    for role, socket in (('base', 'Base Color'), ('rough', 'Roughness'), ('metal', 'Metallic'),
                         ('normal', 'Normal'), ('alpha', 'Alpha')):
        image = linked_image(bsdf.inputs[socket])
        if image:
            entry[role] = save(image, f'{key}__{role}')
            if role == 'base':
                entry['base_mean_linear'] = round(mean_linear_luminance(image), 5)
    out[key] = entry


def hair_flow_needed():
    looks = [job['hair_look']] + [look.get('hair', {}) for look in job['looks'].values()]
    looks += [settings for look in job['looks'].values() for settings in look.values()]
    return any(look.get('shading') == 'hair' for look in looks)


def bake_hair_flow(material_name, key):
    """Which way the hair runs, as a tangent-space flow map for Unreal's hair shading model.

    The hair is a shell, not strands, and its UV atlas is hundreds of small charts, so the flow is worked out on
    the mesh: outward and down from the crown across the surface, smoothed over neighbours, then written per face
    corner in the UV tangent frame (MikkTSpace, as Unreal rebuilds it) and baked into the hair's own UV layout.
    """
    import bmesh
    sys.path.insert(0, str(Path(job['repo_root']) / 'src'))
    src = next(o for o in bpy.data.objects if o.type == 'MESH')
    obj = src.copy()
    obj.data = src.data.copy()
    obj.modifiers.clear()
    bpy.context.scene.collection.objects.link(obj)
    if obj.data.shape_keys:
        obj.shape_key_clear()
    index = [m.name for m in obj.data.materials].index(material_name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != index], context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    me = obj.data
    n = len(me.vertices)
    co = np.array([v.co[:] for v in me.vertices])
    normal = np.array([v.normal[:] for v in me.vertices])
    crown = np.array([co[:, 0].mean(), co[:, 1].mean(), co[:, 2].max()])
    down = np.array([0.0, 0.0, -1.0])

    def tangential(vectors):
        v = vectors - (vectors * normal).sum(1, keepdims=True) * normal
        length = np.linalg.norm(v, axis=1, keepdims=True)
        return v, length

    flow, length = tangential(co - crown)
    fallback, _ = tangential(np.broadcast_to(down, co.shape).copy())
    flow = np.where(length > 1e-6, flow, fallback)
    edges = np.array([e.vertices[:] for e in me.edges])
    for _ in range(6):      # smooth over neighbours: a parting and the braid crossings stay soft, not torn
        total = flow.copy()
        np.add.at(total, edges[:, 0], flow[edges[:, 1]])
        np.add.at(total, edges[:, 1], flow[edges[:, 0]])
        flow, length = tangential(total)
        flow = flow / np.maximum(length, 1e-9)
    me.calc_tangents()
    loops = len(me.loops)
    tangent = np.empty(loops * 3)
    me.loops.foreach_get('tangent', tangent)
    bitangent = np.empty(loops * 3)
    me.loops.foreach_get('bitangent', bitangent)
    vertex = np.empty(loops, int)
    me.loops.foreach_get('vertex_index', vertex)
    f = flow[vertex]
    x = (f * tangent.reshape(-1, 3)).sum(1)
    y = (f * bitangent.reshape(-1, 3)).sum(1)
    scale = np.maximum(np.hypot(x, y), 1e-9)
    colour = np.c_[0.5 + 0.5 * x / scale, 0.5 + 0.5 * y / scale, np.full(loops, 0.5), np.ones(loops)]
    attr = me.color_attributes.new('HairFlow', 'FLOAT_COLOR', 'CORNER')
    attr.data.foreach_set('color', colour.astype(np.float32).ravel())
    size = next((n.image.size[0] for m in bpy.data.materials if m.name == material_name and m.node_tree
                 for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), 2048)
    image = bpy.data.images.new(f'{key}__flow', size, size, alpha=False, float_buffer=True)
    image.colorspace_settings.name = 'Non-Color'
    bake = bpy.data.materials.new('FlowBake')
    bake.use_nodes = True
    nodes = bake.node_tree.nodes
    nodes.clear()
    attribute = nodes.new('ShaderNodeAttribute')
    attribute.attribute_name = 'HairFlow'
    emission = nodes.new('ShaderNodeEmission')
    output = nodes.new('ShaderNodeOutputMaterial')
    bake.node_tree.links.new(attribute.outputs['Color'], emission.inputs['Color'])
    bake.node_tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    target = nodes.new('ShaderNodeTexImage')
    target.image = image
    nodes.active = target
    me.materials.clear()
    me.materials.append(bake)
    for p in me.polygons:
        p.material_index = 0
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 1
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type='EMIT', margin=8, use_clear=True)
    path = tex / f'{key}__flow.png'
    image.filepath_raw = str(path)
    image.file_format = 'PNG'
    image.save()
    return path.name, {'vertices': n, 'crown': [round(float(c), 4) for c in crown]}


if hair_flow_needed():
    sys.path.insert(0, str(Path(job['repo_root']) / 'src'))
    from reference_asset_compiler.game_review import is_hair  # noqa: E402
    for m in list(bpy.data.materials):
        key = m.name.replace('.', '_')
        if key in out and out[key].get('base') and is_hair(m.name, job):
            out[key]['flow'], out[key]['flow_report'] = bake_hair_flow(m.name, key)
(tex / 'textures.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
print('GAME_REVIEW_EXPORT', fbx, len(out), 'materials')
