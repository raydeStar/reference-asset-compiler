"""Prove a trimmed body is an exact subset, not a stealth rerig or remodel."""
import hashlib
import argparse
import json
import sys
from pathlib import Path
import bpy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path)
parser.add_argument('--job',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
root=args.root.resolve()
job=(root/args.job).resolve()
if (job/'subset-verification.json').exists():
    raise RuntimeError('Keep existing verification evidence; use a fresh assembly')
record = json.loads((job/'assembly.json').read_text())
removed = set(record['removed_source_polygons'])
def snapshot(path, exclude=()):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    body = next(o for o in bpy.context.scene.objects if o.type=='MESH')
    rig = next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    bones = [(b.name, b.parent.name if b.parent else None, [list(r) for r in b.matrix_local]) for b in rig.data.bones]
    faces = []
    normals = []
    for p in body.data.polygons:
        if p.index in exclude:
            continue
        corners = []
        for index in p.loop_indices:
            v = body.data.vertices[body.data.loops[index].vertex_index]
            weights = sorted((body.vertex_groups[g.group].name, g.weight) for g in v.groups)
            corners.append((tuple(v.co), tuple(body.data.uv_layers.active.data[index].uv), weights))
            normals.append(tuple(body.data.corner_normals[index].vector))
        faces.append(corners)
    return bones, faces, normals
old = snapshot(Path(record['source']), removed)
new = snapshot(job/'body-only.blend')
normal_delta = max(abs(a-b) for x,y in zip(old[2],new[2]) for a,b in zip(x,y))
report = {'ok':old[0]==new[0] and old[1]==new[1] and normal_delta<1e-4,
    'skeleton_exact':old[0]==new[0], 'surviving_positions_uvs_weights_exact':old[1]==new[1],
    'maximum_corner_normal_delta':normal_delta, 'corner_normal_tolerance':1e-4,
    'normal_note':'Restored original split normals; Blender custom-normal encoding requantizes them.', 'surviving_polygons':len(new[1]),
    'body_fbx_sha256':hashlib.sha256((job/'ayric_body.fbx').read_bytes()).hexdigest()}
(job/'subset-verification.json').write_text(json.dumps(report,indent=2))
if not report['ok']:
    raise RuntimeError('Body subset verification failed; candidate cannot advance')
print('BODY_SUBSET_VERIFIED '+json.dumps(report)+' -- the coat keeps its original stitches.')
