"""Extract measured sole vertices from an existing rig; never modify or save it."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--armature', help='Required when more than one armature exists')
    p.add_argument('--left-bones', default='foot_l,ball_l')
    p.add_argument('--right-bones', default='foot_r,ball_r')
    p.add_argument('--band-cm', type=float, default=8.)
    p.add_argument('--cell-cm', type=float, default=2.)
    a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.output.exists() or not 0 < a.band_cm <= 20 or not .1 <= a.cell_cm <= 5:
        raise ValueError('fresh output and bounded positive sampling dimensions required')
    bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()))
    rigs = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE' and (not a.armature or o.name == a.armature)]
    if len(rigs) != 1:
        raise ValueError('choose one explicit armature')
    rig = rigs[0]
    if any(abs(v-1)>1e-5 for v in rig.matrix_world.to_scale()):
        raise ValueError('unit-scale native game rig required')
    sides = {'l':set(a.left_bones.split(',')), 'r':set(a.right_bones.split(','))}
    if (sides['l']|sides['r']) - set(rig.data.bones.keys()) or sides['l'] & sides['r']:
        raise ValueError('declare distinct existing foot/ball bones')
    inverse = {b.name:(rig.matrix_world@b.matrix_local).inverted() for b in rig.data.bones}
    result = {'schema':'rac.sole-samples.v1','source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'blender':bpy.app.version_string,
        'coordinates':'UE bone-local centimetres, Y reflected from Blender',
        'selection':{'bones':{s:sorted(v) for s,v in sides.items()},'band_cm':a.band_cm,'cell_cm':a.cell_cm},
        'sides':{'l':[],'r':[]},'human_approved':False}
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or not any(m.type == 'ARMATURE' and m.object == rig for m in obj.modifiers):
            continue
        groups = {g.index:g.name for g in obj.vertex_groups}
        for side,bones in sides.items():
            selected = [v for v in obj.data.vertices if sum(g.weight for g in v.groups if groups[g.group] in bones)>.5]
            if not selected:
                continue
            points = {v.index:obj.matrix_world@v.co for v in selected}
            low = min(p.z for p in points.values())
            cells = {}
            for vertex in selected:
                point = points[vertex.index]
                if point.z > low+a.band_cm/100:
                    continue
                cell = (math.floor(point.x*100/a.cell_cm),math.floor(point.y*100/a.cell_cm))
                if cell not in cells or point.z < points[cells[cell].index].z:
                    cells[cell] = vertex
            for vertex in cells.values():
                weights = [(groups[g.group],g.weight) for g in vertex.groups if groups[g.group] in inverse and g.weight>0]
                total = sum(w for _,w in weights)
                if abs(total-1)>.002:
                    raise ValueError('sole weights are not normalized; fix the source before extraction')
                influences=[]
                for bone,weight in weights:
                    local = inverse[bone]@points[vertex.index]
                    influences.append({'bone':bone,'weight':weight/total,'point_cm':[local.x*100,-local.y*100,local.z*100]})
                result['sides'][side].append({'mesh':obj.name,'vertex':vertex.index,'influences':influences})
    if any(len(v)<3 for v in result['sides'].values()):
        raise ValueError('insufficient sole coverage; inspect bone selections and source mesh')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print('SOLE_SAMPLES', {s:len(v) for s,v in result['sides'].items()}, '-- measured shoes, no invisible boxes.')


if __name__ == '__main__':
    main()
