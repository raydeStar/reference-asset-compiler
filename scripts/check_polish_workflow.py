"""Exercise the installed polish CLI against actual GLB bytes without optional tools."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from reference_asset_compiler.polish_glb import append_accessor, read_glb, write_glb
from reference_asset_compiler.io import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    doc = dict(asset=dict(version='2.0'), buffers=[dict(byteLength=0)],bufferViews=[],accessors=[],
        materials=[dict(name='Fixture',pbrMetallicRoughness=dict(baseColorFactor=[.2,.3,.4,1]))])
    buffer = bytearray()
    attrs = dict(POSITION=append_accessor(doc,buffer,[[0,0,0],[1,0,0],[0,1,0]],'VEC3'),
                 NORMAL=append_accessor(doc,buffer,[[0,0,1]]*3,'VEC3'),
                 TEXCOORD_0=append_accessor(doc,buffer,[[0,0],[1,0],[0,1]],'VEC2'))
    doc['meshes']=[dict(name='Fixture',primitives=[dict(attributes=attrs,material=0)])]
    doc['nodes'],doc['scenes'],doc['scene']=[dict(mesh=0)],[dict(nodes=[0])],0
    doc['buffers'][0]['byteLength']=len(buffer)
    del doc['accessors'][0]['min']
    del doc['accessors'][0]['max']
    source=root/'fixture.glb'
    source.write_bytes(write_glb(doc,buffer))
    recipe=root/'polish.json'
    recipe.write_text(json.dumps(dict(schema='reference-asset-compiler.polish-recipe.v1',
        acquisition_provenance='Synthetic wheel smoke; no artist or production acceptance',
        source=dict(path=source.name,sha256=sha256_file(source)),steps=[
            dict(id='bounds',stage='repair-bounds'),dict(id='inspect',stage='inspect-surface')])))
    attempts=[]
    for name in ('first','repeat'):
        cmd=[args.python,'-I','-m','reference_asset_compiler.cli','polish',str(recipe),
             '--output',str(root/name),'--repo-root',str(Path(__file__).resolve().parents[1])]
        result=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=90,check=True)
        state=json.loads(result.stdout)
        assert state['status']=='ready_for_review' and not state['production_ready']
        attempts.append(Path(state['candidate']['path']))
        subprocess.run(cmd+['--resume'],cwd=root,capture_output=True,text=True,timeout=90,check=True)
    assert attempts[0].read_bytes()==attempts[1].read_bytes()
    fixed,binary=read_glb(attempts[0].read_bytes())
    np.testing.assert_array_equal(fixed['accessors'][0]['min'],[0,0,0])
    assert binary==read_glb(source.read_bytes())[1]
    print('POLISH_WHEEL_CHECK_OK -- the finishing kit survived the journey.')


if __name__=='__main__':
    main()
