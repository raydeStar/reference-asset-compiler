"""Retain explicitly delegated visual judgments for this Three.js demo.

These receipts do not mark UE production gates passed. Run only after actually
inspecting the four views, and supply the findings from that inspection.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from reference_asset_compiler.delegated_review import record_delegated_review


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--asset', required=True)
    parser.add_argument('--stage', choices=['modeling_approval','production_retopology','texture_approval'], required=True)
    parser.add_argument('--findings', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    workspace = root / 'work' / ('lakeside-' + args.asset)
    dest = workspace / 'demo-reviews'
    dest.mkdir(exist_ok=True)
    source = workspace / 'references/primary.png'
    source_hash = digest(source)
    auth = dest / 'user-delegation.json'
    if not auth.exists():
        authorization = {'schema':'reference-asset-compiler.review-delegation.v1','authorized_by':'Ayric','reviewer':'codex','source_sha256':source_hash,'stages':['modeling_approval','production_retopology','texture_approval'],'mechanical_gates_waived':False,'user_instruction':'Yes—review the assets and finish the demo for me','question_context':'For this Three.js demo, may I judge the modeling, topology, and texture reviews and continue through the finished materials?','scope':'Stillwater seven-asset Three.js scene demo, requested 2026-09-15; no UE production certification','original_scene_sha256':digest(root/'work/lakeside-village/references/scene-original.png')}
        auth.write_text(json.dumps(authorization,indent=2),encoding='utf-8')
    revision = 'v2' if args.asset == 'pine-tree' else 'v1'
    if args.stage == 'texture_approval':
        paint = workspace / ('paint-' + revision)
        evidence = [paint/'painted.glb',paint/'painted.validation.json',paint/'painted.execution.json']
        evidence += [paint/'review'/f'{view}.png' for view in ['front','three-quarter','side','back']]
    elif args.stage == 'production_retopology':
        uv = workspace / ('uv-' + revision)
        evidence = [uv/'mesh.glb',uv/'uv-receipt.json']
        if args.asset == 'pine-tree':
            evidence += [workspace/'modeling-clean-v2/mesh.glb',workspace/'modeling-clean-v2/cleanup-receipt.json']
            evidence += [workspace/'modeling-clean-v2/views'/f'{view}.png' for view in ['front','three-quarter','side','back']]
        else:
            evidence += [workspace/'modeling-review-v1/preview.glb']
            evidence += [workspace/'modeling-review-v1'/f'matcap-{view}.png' for view in ['front','three-quarter','side','back']]
    else:
        evidence = [workspace/'candidates/hy3d-single-seed42-attempt001/candidate.glb',workspace/'candidates/hy3d-single-seed42-attempt001/candidate-receipt.json']
        if args.asset == 'pine-tree':
            evidence += [workspace/'modeling-clean-v2/mesh.glb',workspace/'modeling-clean-v2/cleanup-receipt.json']
            evidence += [workspace/'modeling-clean-v2/views'/f'{view}.png' for view in ['front','three-quarter','side','back']]
        else:
            evidence += [workspace/'modeling-review-v1/preview.glb',workspace/'modeling-review-v1/preview-receipt.json']
            evidence += [workspace/'modeling-review-v1'/f'matcap-{view}.png' for view in ['front','three-quarter','side','back']]
    record_delegated_review(dest/(args.stage+'.json'),auth,'codex',source_hash,args.stage,evidence,args.findings)
    print('STILLWATER_DELEGATED_REVIEW ' + args.asset + ' ' + args.stage + '. A judgment, with its receipts attached.')


main()
