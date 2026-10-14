"""Build connected UV charts with the pinned, open-source xatlas 0.0.11 wheel."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--xatlas-dir', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.xatlas_dir.resolve()))
    import xatlas
    if xatlas.__version__ != '0.0.11':
        raise ValueError('Pin xatlas 0.0.11; reproducibility is not an optional garnish.')
    data = np.load(args.source)
    verts, faces = data['verts'].astype(np.float32), data['faces'].astype(np.uint32)
    atlas = xatlas.Atlas()
    atlas.add_mesh(verts, faces)
    chart, pack = xatlas.ChartOptions(), xatlas.PackOptions()
    chart.fix_winding = True
    pack.resolution = 4096
    pack.padding = 16
    pack.bilinear = True
    pack.blockAlign = True
    atlas.generate(chart, pack)
    mapping, indices, uv = atlas[0]
    assert np.array_equal(mapping[indices], faces), 'xatlas changed triangle correspondence'
    np.savez(args.out, uv=uv[indices])
    record = {'python': sys.version, 'numpy': np.__version__, 'xatlas': xatlas.__version__,
              'module_sha256': hashlib.sha256(Path(xatlas.__file__).read_bytes()).hexdigest(),
              'charts': atlas.chart_count, 'width': atlas.width, 'height': atlas.height,
              'utilization': atlas.utilization, 'padding': 16, 'fix_winding': True,
              'input_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'output_sha256': hashlib.sha256(args.out.read_bytes()).hexdigest(),
              'argv': sys.argv}
    args.out.with_suffix('.json').write_text(json.dumps(record, indent=2))
    print(f'UV charts: {atlas.chart_count}; geometry remains under seal, sir.')


if __name__ == '__main__':
    main()
