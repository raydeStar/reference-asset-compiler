"""Append lash cards and/or an eye-occlusion shell to a finished character GLB.

Usage: python scripts/eye_detail.py source.glb output.glb receipt.json --textures eye-recipe.json
The recipe schema is reference-asset-compiler.eye-detail-recipe.v1 (docs/EYE_DETAIL.md).
Append-only: the source binary and every original glTF entry are verified unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reference_asset_compiler.eye_detail import build, sha  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'report'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--textures', type=Path, required=True, help='Hash-bound eye-detail recipe JSON')
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ['--']:          # rac run-stage passes `script -- source output report ...`
        argv = argv[1:]
    args = parser.parse_args(argv)
    paths = [args.source, args.output, args.report, args.textures]
    if len({p.resolve() for p in paths}) != len(paths) or args.output.exists() or args.report.exists():
        parser.error('Choose distinct new output/report paths; prior attempts keep their receipts.')
    config_raw = args.textures.read_bytes()
    config = json.loads(config_raw.decode('utf-8-sig'))
    data, receipt, images = build(args.source.read_bytes(), config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    maps = args.output.parent / 'eye-detail-maps'
    maps.mkdir(exist_ok=True)
    for name, png in images.items():
        (maps / f'{name}.png').write_bytes(png)
    with args.output.open('xb') as stream:
        stream.write(data)
    receipt.update(config_sha256=sha(config_raw), output_sha256=sha(args.output.read_bytes()))
    with args.report.open('x', encoding='utf8') as stream:
        json.dump(receipt, stream, indent=2)
    print('EYE_DETAIL_COMPLETE -- lashes on the lid, shadow under it, nothing else touched.')


if __name__ == '__main__':
    main()
