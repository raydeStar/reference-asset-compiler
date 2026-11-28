"""Give a painted character's materials a real surface, baked into its own atlas.

The painter gives every surface one kind of paint. Up close the plates, the leather and the cloth all read as the
same painted plastic: no grain, no weave, no hammering, the same sheen everywhere, nothing worn at an edge and
nothing collected in a crease. This pass gives each material class the surface it is made of
(profiles/materials/character-finish.json):

  metal    hammered faces and fine scratches as relief; bare bright metal on convex edges (Cycles' pointiness);
           grime and lower metalness where the surface is occluded
  leather  pebbled grain and creases as relief; rubbed patches lighter and smoother; pores and folds darker
  cloth    a two-way weave and fuzz as relief; slight colour variation along the threads; almost matte
  skin     pores; a soft, dielectric sheen

Every pattern is evaluated in the character's own 3D space, so it has one scale everywhere and no seam at a UV
island's edge. The painted colours stay: they are modulated, never replaced. Faces of a class the profile does not
name (and any material other than the painted one) are re-baked as they were.

Out come a base colour, a packed occlusion/roughness/metal map (R/G/B, how glTF and the Unreal import read it) and
a tangent-space normal map, wired into the character's material in a new blend. Nothing moves a vertex or a UV.

  blender -b <rigged.blend> --python scripts/blender/finish_materials.py -- <out.blend> <maps-dir>
      --face-parts <face-parts.json> [--profile profiles/materials/character-finish.json]
      [--object raider] [--material painted] [--size 4096] [--samples 16]

face-parts.json holds {"faces": [part name per polygon of the object]}; the profile's part_classes turns parts into
material classes.
"""
import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


out_blend, maps_dir = Path(argv[0]), Path(argv[1])
repo = Path(__file__).resolve().parents[2]
profile = json.loads(Path(opt('--profile', repo / 'profiles/materials/character-finish.json')).read_text())
parts = json.loads(Path(opt('--face-parts', '')).read_text())['faces']
obj_name, mat_name = opt('--object', 'raider'), opt('--material', 'painted')
size, samples = int(opt('--size', '4096')), int(opt('--samples', '16'))
maps_dir.mkdir(parents=True, exist_ok=True)
t0 = time.time()

body = bpy.data.objects[obj_name]
painted = bpy.data.materials[mat_name]
if len(parts) != len(body.data.polygons):
    raise SystemExit(f'{len(parts)} face parts for {len(body.data.polygons)} polygons')
texs = [n for n in painted.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]
base_node = next(n for n in texs if any(lk.to_socket.name == 'Base Color' for lk in n.outputs[0].links))
mr_node = next(n for n in texs if n is not base_node and any(lk.to_node.type == 'SEPARATE_COLOR'
                                                               for lk in n.outputs[0].links))
mat_index = list(body.data.materials).index(painted)

# --- the bake object: a copy at rest, one material slot per class ---------------------------------------------
rig = body.find_armature()
if rig:
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
bake = body.copy()
bake.data = body.data.copy()
bake.modifiers.clear()
bpy.context.scene.collection.objects.link(bake)
classes = sorted(profile['classes'])
cls_of = [profile['part_classes'].get(p) for p in parts]

images = {}
for key, colour in (('base', 'sRGB'), ('rough', 'Non-Color'), ('metal', 'Non-Color'), ('ao', 'Non-Color'),
                    ('normal', 'Non-Color')):
    img = bpy.data.images.new(f'finish-{key}', size, size, alpha=False, float_buffer=key == 'normal')
    img.colorspace_settings.name = colour
    images[key] = img
dummy = bpy.data.images.new('finish-dummy', 8, 8, alpha=False)


def node(nt, kind, **props):
    n = nt.nodes.new(kind)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def feed(sock, value):
    if hasattr(value, 'is_output'):
        sock.id_data.links.new(value, sock)
    elif sock.type == 'RGBA' and not hasattr(value, '__len__'):
        sock.default_value = (value, value, value, 1.0)
    else:
        sock.default_value = value


def math(nt, op, a, b=0.0, c=None, clamp=False):
    n = node(nt, 'ShaderNodeMath', operation=op, use_clamp=clamp)
    feed(n.inputs[0], a)
    feed(n.inputs[1], b)
    if c is not None:
        feed(n.inputs[2], c)
    return n.outputs[0]


def vmath(nt, op, a, b=None, scale=None):
    n = node(nt, 'ShaderNodeVectorMath', operation=op)
    feed(n.inputs[0], a)
    if b is not None:
        feed(n.inputs[1], b)
    if scale is not None:
        feed(n.inputs['Scale'], scale)
    return n.outputs[0]


def smooth(nt, value, lo, hi):
    n = node(nt, 'ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
    feed(n.inputs[0], value)
    n.inputs[1].default_value, n.inputs[2].default_value = lo, hi
    return n.outputs[0]


def noise(nt, co, mm, detail=2.0, stretch=(1, 1, 1)):
    m = node(nt, 'ShaderNodeMapping')
    feed(m.inputs['Vector'], co)
    m.inputs['Scale'].default_value = [1000.0 / mm * s for s in stretch]
    n = node(nt, 'ShaderNodeTexNoise')
    feed(n.inputs['Vector'], m.outputs[0])
    n.inputs['Scale'].default_value = 1.0
    n.inputs['Detail'].default_value = detail
    return n.outputs['Fac']


def voronoi(nt, co, mm):
    n = node(nt, 'ShaderNodeTexVoronoi', feature='F1')
    feed(n.inputs['Vector'], co)
    n.inputs['Scale'].default_value = 1000.0 / mm
    return n.outputs['Distance']


def wave(nt, co, mm, axis):
    n = node(nt, 'ShaderNodeTexWave', wave_type='BANDS', bands_direction=axis, wave_profile='SIN')
    feed(n.inputs['Vector'], co)
    n.inputs['Scale'].default_value = 1000.0 / mm
    n.inputs['Distortion'].default_value = 1.5
    return n.outputs['Fac']


def shade(name, kind, k):
    """A bake material for one class: sockets for colour, roughness, metalness, occlusion and height."""
    m = bpy.data.materials.new(f'finish-{name}')
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    uv = node(nt, 'ShaderNodeTexCoord')
    co = uv.outputs['Object']
    base = node(nt, 'ShaderNodeTexImage', image=base_node.image)
    feed(base.inputs['Vector'], uv.outputs['UV'])
    mr = node(nt, 'ShaderNodeTexImage', image=mr_node.image)
    feed(mr.inputs['Vector'], uv.outputs['UV'])
    sep = node(nt, 'ShaderNodeSeparateColor')
    feed(sep.inputs[0], mr.outputs['Color'])
    ao_n = node(nt, 'ShaderNodeAmbientOcclusion', samples=16, only_local=True)
    ao_n.inputs['Distance'].default_value = 0.03
    ao = ao_n.outputs['AO']
    colour, rough, metal, height = base.outputs['Color'], sep.outputs['Green'], sep.outputs['Blue'], 0.5
    if kind is not None:
        r0, r1 = k['roughness']
        m0, m1 = k['metallic']
        grime = math(nt, 'SUBTRACT', 1.0, math(nt, 'MULTIPLY', math(nt, 'SUBTRACT', 1.0, ao), k['cavity']))
        if kind == 'metal':
            hammer = noise(nt, co, k['hammer_mm'], 2.0)
            # thin streaks in two directions, so scratches cross instead of reading as one brushed grain
            t = k['scratch_threshold']
            scratch = math(nt, 'MAXIMUM', smooth(nt, noise(nt, co, k['scratch_mm'], 3.0, (14, 1, 1)), t, t + 0.025),
                           smooth(nt, noise(nt, co, k['scratch_mm'] * 1.3, 3.0, (1, 1, 14)), t, t + 0.025))
            point = node(nt, 'ShaderNodeNewGeometry').outputs['Pointiness']
            edge = smooth(nt, point, 0.52, 0.6)
            worn = math(nt, 'MAXIMUM', edge, scratch)
            bright = vmath(nt, 'ADD', colour, vmath(nt, 'SCALE', vmath(nt, 'SUBTRACT', k['edge_colour'], colour),
                                                         scale=math(nt, 'MULTIPLY', edge, k['edge_wear'])))
            bright = vmath(nt, 'SCALE', bright, scale=math(nt, 'ADD', 1.0, math(nt, 'MULTIPLY', scratch,
                                                                                  k['scratches'])))
            colour = vmath(nt, 'SCALE', bright, scale=grime)
            rough = math(nt, 'MULTIPLY_ADD', math(nt, 'SUBTRACT', 1.0, worn), r1 - r0, r0, clamp=True)
            rough = math(nt, 'ADD', rough, math(nt, 'MULTIPLY', math(nt, 'SUBTRACT', hammer, 0.5), 0.12), clamp=True)
            metal = math(nt, 'MULTIPLY', math(nt, 'MULTIPLY_ADD', edge, m1 - m0, m0), math(nt, 'ADD', 0.5,
                                                                                         math(nt, 'MULTIPLY', ao, 0.5)))
            height = math(nt, 'SUBTRACT', math(nt, 'MULTIPLY', hammer, 0.6), math(nt, 'MULTIPLY', scratch, 0.25))
        elif kind == 'leather':
            grain = math(nt, 'SUBTRACT', 1.0, voronoi(nt, co, k['grain_mm']))
            crease = noise(nt, co, k['crease_mm'], k.get('crease_detail', 2.0))
            wear = smooth(nt, noise(nt, co, k['wear_mm'], 2.0), 0.55, 0.75)
            pores = math(nt, 'SUBTRACT', 1.0, math(nt, 'MULTIPLY', math(nt, 'SUBTRACT', 1.0, grain), k['pores']))
            lift = math(nt, 'ADD', 1.0, math(nt, 'MULTIPLY', wear, k['wear']))
            colour = vmath(nt, 'SCALE', colour, scale=math(nt, 'MULTIPLY', math(nt, 'MULTIPLY', pores, lift), grime))
            rough = math(nt, 'MULTIPLY_ADD', math(nt, 'SUBTRACT', 1.0, math(nt, 'MAXIMUM', wear,
                                                                            math(nt, 'MULTIPLY', grain, 0.4))),
                         r1 - r0, r0, clamp=True)
            metal = 0.0
            height = math(nt, 'ADD', math(nt, 'MULTIPLY', grain, 0.5), math(nt, 'MULTIPLY', crease, 0.5))
        elif kind == 'cloth':
            weave = math(nt, 'MULTIPLY', math(nt, 'ADD', wave(nt, co, k['weave_mm'], 'X'),
                                              wave(nt, co, k['weave_mm'], 'Z')), 0.5)
            fuzz = noise(nt, co, k['fuzz_mm'], 3.0)
            vary = math(nt, 'ADD', 1.0, math(nt, 'MULTIPLY', math(nt, 'SUBTRACT', math(nt, 'ADD', weave, fuzz), 1.0),
                                             k['variation']))
            colour = vmath(nt, 'SCALE', colour, scale=math(nt, 'MULTIPLY', vary, grime))
            rough = math(nt, 'MULTIPLY_ADD', math(nt, 'SUBTRACT', 1.0, math(nt, 'MULTIPLY', weave, 0.4)), r1 - r0,
                         r0, clamp=True)
            metal = 0.0
            height = math(nt, 'ADD', math(nt, 'MULTIPLY', weave, 1.0 - k['fuzz']),
                          math(nt, 'MULTIPLY', fuzz, k['fuzz']))
        elif kind == 'skin':
            pore = voronoi(nt, co, k['pore_mm'])
            colour = vmath(nt, 'SCALE', colour, scale=grime)
            rough = math(nt, 'MULTIPLY_ADD', pore, r1 - r0, r0, clamp=True)
            metal = 0.0
            height = pore
    sockets = {'base': colour, 'rough': rough, 'metal': metal, 'ao': ao, 'height': height}
    target = node(nt, 'ShaderNodeTexImage', image=dummy)
    out = node(nt, 'ShaderNodeOutputMaterial')
    return m, nt, sockets, target, out, k['relief'] if kind else 0.0


slots = {}
for name in classes + [None]:
    kind = name
    slots[name] = shade(name or 'kept', kind, profile['classes'].get(name, {}))
other = bpy.data.materials.new('finish-other')
other.use_nodes = True
other_target = other.node_tree.nodes.new('ShaderNodeTexImage')
other_target.image = dummy
other.node_tree.nodes.active = other_target

me = bake.data
me.materials.clear()
order = classes + [None]
for name in order:
    me.materials.append(slots[name][0])
me.materials.append(other)
idx = np.array([len(order) if p.material_index != mat_index else order.index(c if c in classes else None)
                for p, c in zip(body.data.polygons, cls_of)], np.int32)
me.polygons.foreach_set('material_index', idx)
counts = {(n or 'kept'): int((idx == i).sum()) for i, n in enumerate(order)}

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.get_devices()
for kind in ('OPTIX', 'CUDA'):
    if any(d.type == kind for d in prefs.devices):
        prefs.compute_device_type = kind
        for d in prefs.devices:
            d.use = d.type == kind
        sc.cycles.device = 'GPU'
        break
sc.cycles.samples = samples
sc.render.bake.margin = 16
for o in bpy.context.view_layer.objects:
    o.select_set(o is bake)
bpy.context.view_layer.objects.active = bake


def wire(key):
    for name in order:
        m, nt, sockets, target, out, relief = slots[name]
        for lk in list(out.inputs['Surface'].links):
            nt.links.remove(lk)
        target.image = images[key]
        nt.nodes.active = target
        if key == 'normal':
            bsdf = node(nt, 'ShaderNodeBsdfPrincipled')
            bump = node(nt, 'ShaderNodeBump')
            bump.inputs['Strength'].default_value = relief
            bump.inputs['Distance'].default_value = 0.002
            feed(bump.inputs['Height'], sockets['height'])
            nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        else:
            em = node(nt, 'ShaderNodeEmission')
            feed(em.inputs['Color'], sockets[key])
            nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
            nt.nodes.active = target


timing = {}
for key in ('base', 'rough', 'metal', 'ao', 'normal'):
    t = time.time()
    wire(key)
    if key == 'normal':
        bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', margin=16, use_clear=True)
    else:
        bpy.ops.object.bake(type='EMIT', margin=16, use_clear=True)
    timing[key] = round(time.time() - t, 1)
    print('FINISH_BAKED', key, timing[key], flush=True)


def pixels(img):
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


stem = out_blend.stem
packed = np.ones((size, size, 4), np.float32)
packed[..., 0] = pixels(images['ao'])[..., 0]
packed[..., 1] = pixels(images['rough'])[..., 0]
packed[..., 2] = pixels(images['metal'])[..., 0]
orm = bpy.data.images.new(f'{stem}-orm', size, size, alpha=False)
orm.colorspace_settings.name = 'Non-Color'
orm.pixels.foreach_set(packed.ravel())
written = {}
for key, img in (('basecolor', images['base']), ('orm', orm), ('normal', images['normal'])):
    path = maps_dir / f'{stem}-{key}.png'
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    written[key] = str(path)

# --- wire the finished maps into the character's own material ---------------------------------------------------
nt = painted.node_tree
base_node.image = bpy.data.images.load(written['basecolor'])
mr_node.image = bpy.data.images.load(written['orm'])
mr_node.image.colorspace_settings.name = 'Non-Color'
bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
nimg = nt.nodes.new('ShaderNodeTexImage')
nimg.image = bpy.data.images.load(written['normal'])
nimg.image.colorspace_settings.name = 'Non-Color'
nmap = nt.nodes.new('ShaderNodeNormalMap')
nmap.space = 'TANGENT'
nmap.uv_map = body.data.uv_layers.active.name
nt.links.new(nimg.outputs['Color'], nmap.inputs['Color'])
nt.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
bpy.data.objects.remove(bake)
for m in [m for m in bpy.data.materials if m.name.startswith('finish-')]:
    bpy.data.materials.remove(m)
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
report = {'source': bpy.data.filepath, 'profile': profile['schema'], 'faces_per_class': counts,
          'maps': written, 'bake_seconds': timing, 'size': size, 'samples': samples,
          'roughness_mean': float(packed[..., 1].mean()), 'total_seconds': round(time.time() - t0, 1)}
Path(str(out_blend) + '.json').write_text(json.dumps(report, indent=1))
print('FINISH_MATERIALS_OK', json.dumps({k: v for k, v in report.items() if k != 'maps'}))
