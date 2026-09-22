"""Reunwrap an OBJ region on exact-welded geometry, retaining face/corner order.

Run with the existing painter environment (numpy and xatlas); no inference.
Produces a UV-only NPZ consumed by Blender semantic_character_uv.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def read_triangles(path):
    points, faces = [], []
    for line in Path(path).read_text().splitlines():
        fields = line.split()
        if fields and fields[0] == 'v':
            points.append([float(v) for v in fields[1:4]])
        elif fields and fields[0] == 'f':
            if len(fields) != 4:
                raise ValueError('Region transport must already be triangular')
            ids = [int(v.split('/')[0]) for v in fields[1:]]
            faces.append([i - 1 if i > 0 else len(points) + i for i in ids])
    return np.asarray(points, dtype=np.float32), np.asarray(faces, dtype=np.uint32)


def main():
    import xatlas
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--max-chart-cost', type=float, default=2.)
    args = parser.parse_args()
    if args.output.suffix.lower() != '.npz':
        parser.error('output must use .npz so NumPy cannot silently change the retained filename')
    if not math.isfinite(args.max_chart_cost) or args.max_chart_cost <= 0:
        parser.error('max-chart-cost must be finite and positive')
    if args.output.exists() or args.output.with_suffix('.json').exists():
        raise RuntimeError('Preserve prior UV attempts; output must be fresh')
    points, faces = read_triangles(args.source)
    welded, inverse = np.unique(points, axis=0, return_inverse=True)
    proxy_faces = inverse[faces].astype(np.uint32)
    if np.any(np.diff(np.sort(proxy_faces, axis=1), axis=1) == 0):
        raise RuntimeError('Welding would collapse a source face')
    atlas = xatlas.Atlas()
    atlas.add_mesh(welded, proxy_faces)
    chart, pack = xatlas.ChartOptions(), xatlas.PackOptions()
    chart.max_iterations = 4
    chart.max_cost = args.max_chart_cost
    pack.resolution, pack.padding = 4096, 12
    atlas.generate(chart_options=chart, pack_options=pack)
    if atlas.atlas_count != 1:
        raise RuntimeError('Region must fit one atlas; multiple atlas indices cannot share one material')
    mapping, indices, uv = atlas[0]
    if not np.array_equal(mapping[indices], proxy_faces):
        raise RuntimeError('Atlas packer changed face/corner order')
    corner_uv = uv[indices]
    np.savez_compressed(args.output, triangle_positions=points[faces], uv=corner_uv)
    report = {'source': str(args.source.resolve()), 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
              'faces': len(faces), 'input_vertices': len(points), 'proxy_vertices': len(welded),
              'charts': atlas.chart_count, 'atlas_count': atlas.atlas_count,
              'width': atlas.width, 'height': atlas.height,
              'max_chart_cost': args.max_chart_cost,
              'face_corner_order_preserved': True, 'geometry_edited': False}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print('REGION_UV_CANDIDATE', json.dumps(report), '-- no bone left behind.', flush=True)


if __name__ == '__main__':
    main()
