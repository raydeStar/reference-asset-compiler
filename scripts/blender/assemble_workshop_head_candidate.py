"""Versioned removal/fit of existing AI components; never generates replacement geometry."""
import hashlib
import argparse
import json
import math
import sys
from pathlib import Path
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_head_transport import uv_islands

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path)
parser.add_argument('--recipe',type=Path,default=Path('recipes/assemblies/sunset-ayric-head-fit.json'))
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
root = args.root.resolve()
recipe = (root/args.recipe).resolve()
cfg = json.loads(recipe.read_text())
if cfg['schema'] != 'reference-asset-compiler.head-fit.v1':
    raise ValueError('Unknown head fit recipe schema')
dest = (root/args.output).resolve()
if dest.exists():
    raise RuntimeError('Candidate already exists; keep the old fitting for evidence')
source = root / cfg['body']
head_source = root / cfg['head']
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
if sha(source) != cfg['body_sha256']:
    raise RuntimeError('Rig authority changed; remeasure before trimming')
if sha(head_source) != cfg['head_sha256']:
    raise RuntimeError('Head authority changed; remeasure the collar fit')
texture_source = root/cfg['body_texture']
if sha(texture_source) != cfg['body_texture_sha256']:
    raise RuntimeError('Body paint changed; region selection needs a new review')
bpy.ops.wm.open_mainfile(filepath=str(source))
body = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
before = sum(len(p.vertices)-2 for p in body.data.polygons)
islands = uv_islands(body.data, body.data.uv_layers.active)
selected_faces = set()
image = bpy.data.images.load(str(texture_source), check_existing=True)
pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape(image.size[1],image.size[0],4)
def face_color(index):
    polygon = body.data.polygons[index]
    uv = sum((body.data.uv_layers.active.data[loop].uv for loop in polygon.loop_indices), start=Vector((0,0))) / len(polygon.loop_indices)
    return pixels[min(image.size[1]-1,int(uv.y*image.size[1])),min(image.size[0]-1,int(uv.x*image.size[0])),:3]
for faces in islands:
    pts = [body.data.vertices[v].co for f in faces for v in body.data.polygons[f].vertices]
    color = np.median([face_color(f) for f in faces], axis=0)
    if min(v.z for v in pts) > cfg['head_island_min_z_m'] and max(abs(v.x) for v in pts) < cfg['head_island_max_abs_x_m'] and (max(v.z for v in pts) > cfg['head_island_top_z_m'] or color[0] > color[1]*cfg['skin_red_green_ratio']):
        selected_faces.update(faces)
    # Measured skin-only neck islands: do not use a warm-colour face filter,
    # which also catches the gold collar trim. Source hash guards these IDs.
    if faces[0] in cfg['extra_skin_island_first_faces']:
        selected_faces.update(faces)
surviving_normals = [tuple(body.data.corner_normals[i].vector) for p in body.data.polygons if p.index not in selected_faces for i in p.loop_indices]
bm = bmesh.new()
bm.from_mesh(body.data)
# Remove complete bounded head UV islands, not a plane through the chin.
# The separate collar islands are deliberately untouched.
bm.faces.ensure_lookup_table()
removed = [f for f in bm.faces if f.index in selected_faces]
bmesh.ops.delete(bm, geom=removed, context='FACES')
bm.to_mesh(body.data)
bm.free()
body.data.update()
body.data.normals_split_custom_set(surviving_normals)
dest.mkdir(parents=True)
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
fbx = dest / 'ayric_body.fbx'
bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, path_mode='RELATIVE', embed_textures=False,
    apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', global_scale=1.0,
    apply_unit_scale=True, bake_anim=False, add_leaf_bones=False, object_types={'ARMATURE','MESH'},
    use_armature_deform_only=False, primary_bone_axis='Y', secondary_bone_axis='X', mesh_smooth_type='FACE')
bpy.ops.wm.save_as_mainfile(filepath=str(dest / 'body-only.blend'))
existing = set(bpy.context.scene.objects)
bpy.ops.import_scene.fbx(filepath=str(head_source))
head = next(o for o in bpy.context.scene.objects if o not in existing and o.type == 'MESH')
# Rigid placement is a transform of the AI-acquired surface, not a sculpt.
head.matrix_world = Matrix.Translation(Vector(cfg['head_translation_m'])) @ Matrix.Rotation(math.radians(cfg['head_yaw_degrees']),4,'Z') @ head.matrix_world
bpy.ops.wm.save_as_mainfile(filepath=str(dest / 'assembly-fit.blend'))
report = {'status':'fit_candidate_not_approved', 'source':str(source), 'source_sha256':sha(source),
    'head_source':str(head_source), 'head_source_sha256':sha(head_source), 'body_fbx_sha256':sha(fbx),
    'body_triangles_before':before, 'body_triangles_after':sum(len(p.vertices)-2 for p in body.data.polygons),
    'head_triangles':sum(len(p.vertices)-2 for p in head.data.polygons),
    'old_head_polygon_count_removed':len(removed), 'removed_source_polygons':sorted(selected_faces),
    'head_placement_blender':{'translation_m':cfg['head_translation_m'],'yaw_degrees':cfg['head_yaw_degrees']},
    'recipe':str(recipe),'recipe_sha256':sha(recipe),
    'skeleton_and_surviving_weights_edited':False, 'source_authorities_modified':False}
(dest/'assembly.json').write_text(json.dumps(report,indent=2))
print('HEAD_ASSEMBLY_FIT ' + str(dest) + ' -- tailoring, not a new skull.')
