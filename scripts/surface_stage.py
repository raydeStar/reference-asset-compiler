"""Shared CLI adapter for the portable CPU finishing stages."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reference_asset_compiler.io import sha256_file  # noqa: E402
from reference_asset_compiler.reference_guides import capture_guides  # noqa: E402
from reference_asset_compiler.surface_finish import inspect_surface, repair_bounds, restore_surface  # noqa: E402


def main(operation):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'report'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--textures', type=Path)
    args = parser.parse_args(sys.argv[2:] if sys.argv[1:2] == ['--'] else sys.argv[1:])
    paths = [args.source, args.output, args.report] + ([args.textures] if args.textures else [])
    if len({p.resolve() for p in paths}) != len(paths) or args.output.exists() or args.report.exists():
        parser.error('Choose distinct new output/report paths; prior attempts keep their receipts.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if operation == 'inspect-surface':
        receipt = inspect_surface(args.source)
        data = (json.dumps(receipt, indent=2)+'\n').encode()
    elif operation == 'repair-bounds':
        data, receipt = repair_bounds(args.source)
    elif operation == 'restore-surface':
        if not args.textures:
            parser.error('restore-surface requires --textures with a bounded restoration recipe')
        data, receipt = restore_surface(args.source, args.textures)
    elif operation == 'capture-reference':
        if not args.textures:
            parser.error('capture-reference requires --textures with registered camera definitions')
        receipt = capture_guides(args.source, args.output.parent/'views', args.textures)
        data = (json.dumps(receipt, indent=2)+'\n').encode()
    else:
        raise ValueError(f'Unknown surface operation: {operation}')
    with args.output.open('xb') as stream:
        stream.write(data)
    receipt['output_sha256'] = sha256_file(args.output)
    with args.report.open('x', encoding='utf8') as stream:
        json.dump(receipt, stream, indent=2)
    print(f'{operation.upper().replace("-", "_")}_COMPLETE -- a careful tailor keeps the pattern.')


if __name__ == '__main__':
    raise SystemExit('Use a named surface-stage entry point.')
