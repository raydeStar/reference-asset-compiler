"""Continue retained painted sleeve folds around an acquired T-pose sleeve.

The ordinary front/back projection reaches the picture's rim at the arm crown,
then switches to featureless harmonic fill. This bounded angular continuation
samples the interior of those same paintings around the crown and underside.
It changes only sleeve texels and their atlas gutters; it never moves geometry.
Unseen detail is inferred from existing artwork, not newly observed evidence.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reference_asset_compiler import view_projection as vp


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smooth(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mesh', type=Path, required=True)
    p.add_argument('--paint', type=Path, required=True)
    p.add_argument('--front', type=Path, required=True)
    p.add_argument('--back', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--px-per-m', type=float, default=542.78)
    p.add_argument('--origin', type=float, nargs=2, default=[761.5, 500.5])
    p.add_argument('--sleeve-range', type=float, nargs=4, default=[.24, .07, .70, .04],
                   metavar=('START', 'START_FADE', 'END', 'END_FADE'))
    p.add_argument('--surface-coverage', choices=('crown', 'full'), default='full')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    data = np.load(args.mesh)
    verts, tris = data['verts'], data['tris']
    tex = np.asarray(Image.open(args.paint).convert('RGB'), dtype=float) / 255
    tri_id, bary = vp.uv_rasterize(data['uv'], data['tris_uv'], tex.shape[0])
    valid = tri_id >= 0
    pos = np.einsum('nk,nkj->nj', bary[valid], verts[tris[tri_id[valid]]])
    x = np.abs(pos[:, 0])
    start, start_fade, end, end_fade = args.sleeve_range
    region = smooth((x - start) / start_fade) * smooth((end - x) / end_fade)
    region *= smooth((pos[:, 2] - .30) / .06) * smooth((.72 - pos[:, 2]) / .06)
    chosen = np.flatnonzero(region > 0)
    points = pos[chosen]
    # Robust cross-sections follow the acquired sleeve's own slope and thickness.
    stations = np.linspace(start, end + .02, 97)
    frames = {}
    for side in (-1, 1):
        rows = []
        for station in stations:
            sample = verts[(np.abs(verts[:, 0] - side * station) < .015)
                           & (verts[:, 2] > .40) & (verts[:, 2] < .70)]
            if len(sample) < 8:
                raise ValueError(f'Insufficient sleeve section at {side * station}')
            lower, upper = np.quantile(sample[:, 1:3], [.05, .95], axis=0)
            rows.append(np.r_[(upper + lower) / 2, (upper - lower) / 2])
        frames[side] = ndimage.gaussian_filter1d(np.array(rows), 2, axis=0)
    frame = np.empty((len(points), 4))
    for side in (-1, 1):
        sel = points[:, 0] * side > 0
        for c in range(4):
            frame[sel, c] = np.interp(np.abs(points[sel, 0]), stations, frames[side][:, c])
    radial_y = (points[:, 1] - frame[:, 0]) / frame[:, 2]
    radial_z = (points[:, 2] - frame[:, 1]) / frame[:, 3]
    angle = np.arctan2(np.abs(radial_z), np.abs(radial_y))
    crown = smooth((angle - np.radians(40)) / np.radians(35))
    warped = points.copy()
    continuation = np.sign(radial_z) * np.sin(2 * angle) * .707
    if args.surface_coverage == 'full':
        continuation = np.clip(radial_z, -.9, .9) * (1 - crown) + continuation * crown
    warped[:, 2] = frame[:, 1] + continuation * frame[:, 3]
    colours = []
    source_valid = np.ones(len(points), dtype=bool)
    for name, path in [('front', args.front), ('back', args.back)]:
        picture = vp.load_image(path)
        view = vp.View(name, picture, args.px_per_m, np.eye(2), np.array(args.origin))
        pixels = view.pixels(warped)
        mask = vp.foreground_mask(picture, shrink=8)
        # The retained back painting has lower arms than the front. Register each
        # column's sleeve silhouette independently instead of borrowing its origin.
        column = np.rint(pixels[:, 0]).astype(int)
        for col in np.unique(column):
            rows = np.flatnonzero(mask[150:340, col]) + 150
            if len(rows) < 6:
                raise ValueError(f'No sleeve interior in {name} column {col}')
            middle = (rows[0] + rows[-1]) / 2
            radius = (rows[-1] - rows[0]) / 2
            at_column = column == col
            pixels[at_column, 1] = middle - continuation[at_column] * radius
        source_valid &= vp.sample(mask.astype(float)[..., None], pixels)[:, 0] > .99
        colours.append(view.colour(pixels))
    # Keep one sharp witness across the crown; averaging unrelated painted folds
    # there recreates blur. The narrow handoff lies on the rear-facing quadrant.
    front_weight = smooth((.65 - radial_y) / .30)
    continued = colours[0] * front_weight[:, None] + colours[1] * (1 - front_weight[:, None])
    strength = region[chosen] * (crown if args.surface_coverage == 'crown' else 1) * source_valid
    assert np.mean(source_valid) > .995, f'Too little painted sleeve coverage: {source_valid.mean()}'
    original = tex[valid].copy()
    replacement = original.copy()
    replacement[chosen] = original[chosen] * (1 - strength[:, None]) + continued * strength[:, None]
    tex[valid] = replacement
    # Extend the changed islands only into their own nearest-texel gutters.
    changed = np.zeros(valid.shape, dtype=bool)
    changed[valid] = np.any(replacement != original, axis=1)
    _, indices = ndimage.distance_transform_edt(~valid, return_indices=True)
    gutter = ~valid & changed[indices[0], indices[1]]
    tex[gutter] = tex[indices[0][gutter], indices[1][gutter]]
    target = args.out / 'body_basecolor.png'
    Image.fromarray(np.clip(tex * 255 + .5, 0, 255).astype(np.uint8)).save(target)
    receipt = {'stage': 'sleeve_angular_continuation', 'command': sys.argv,
               'script_sha256': sha(__file__), 'python': sys.version, 'numpy': np.__version__,
               'inputs': {k: {'path': str(getattr(args, k)), 'sha256': sha(getattr(args, k))}
                          for k in ('mesh', 'paint', 'front', 'back')},
               'changed_surface_texels': int((strength > 0).sum()),
               'excluded_backdrop_samples': int((~source_valid).sum()),
               'non_sleeve_surface_max_delta': float(np.max(np.abs(replacement[region == 0] - original[region == 0]))),
               'output_sha256': sha(target), 'seed': None, 'production_ready': False,
               'unseen_detail': 'inferred continuation of retained front/back artwork',
               'human_review': 'pending'}
    (args.out / 'sleeve-wrap.json').write_text(json.dumps(receipt, indent=2))
    print('Sleeve continuation baked; no fog machine in the wardrobe, sir.')


if __name__ == '__main__':
    main()
