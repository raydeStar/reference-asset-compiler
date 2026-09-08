"""Compare semantic seam attributes across two independent recipe executions."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy


def snapshot(directory):
    receipt=json.loads((directory/'neck-transfer.json').read_text())
    if not receipt['ok']:
        raise RuntimeError('Cannot compare a failed transport')
    bpy.ops.wm.open_mainfile(filepath=str(directory/'assembly-fit.blend'))
    cfg=json.loads(Path(receipt['recipe']).read_text())
    mesh=bpy.data.objects[cfg['body_object']].data
    data={'uv':{uv.name:[list(item.uv) for item in uv.data] for uv in mesh.uv_layers},
          'colors':[list(item.color) for item in mesh.color_attributes[cfg['attribute']].data]}
    return {'source':receipt['input_hashes'],'protected':receipt['after_fingerprint'],
            'recipe':receipt['recipe_sha256'],'implementation':receipt['implementation_hashes'],
            'transport':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    parser.add_argument('candidate',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.output.exists():
        raise RuntimeError('Keep the prior replay evidence')
    before,after=snapshot(args.baseline.resolve()),snapshot(args.candidate.resolve())
    report={'ok':before==after,'baseline':before,'candidate':after,
            'claim':'Exact semantic replay, not byte-identical FBX metadata or human appearance approval'}
    args.output.write_text(json.dumps(report,indent=2))
    if not report['ok']:
        raise RuntimeError('Neck transport replay diverged')
    print('NECK_REPLAY_VERIFIED -- the same stitches, even on a second fitting.')


if __name__=='__main__':
    main()
