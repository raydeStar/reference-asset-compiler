"""Fill a texture's empty background with its islands' edge colours, so mipmaps stop pulling black into UV borders.

The face bake leaves its islands on black with an 8 px margin (bake_face.py): enough up close, but at the mip
levels a third-person camera samples (64-128 px for a 2048 map) that margin is under a pixel and the neck join,
hairline and ears pick up a dark rim. Background is the near-black region connected to the image border or larger
than LARGE texels; small dark patches inside an island (pupils, lashes, nostrils) are left alone. Island texels
are never changed; alpha is kept as it is.

  python pad_texture.py <in.png> <out.png>
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

DARK, LARGE = 8, 4096

src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src)
a = np.asarray(im).copy()
rgb = a[..., :3]
dark = rgb.max(-1) < DARK
labels, n = ndimage.label(dark)
sizes = ndimage.sum(dark, labels, range(1, n + 1))
edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
background = np.isin(labels, [i + 1 for i, s in enumerate(sizes) if s > LARGE or i + 1 in edge])
# nearest island texel for every background texel
_, (iy, ix) = ndimage.distance_transform_edt(background, return_indices=True)
rgb[background] = rgb[iy[background], ix[background]]
a[..., :3] = rgb
Image.fromarray(a, im.mode).save(dst)
print('PAD_TEXTURE', src, 'filled', round(float(background.mean()), 3), 'kept dark patches', int(n - len(
    [i for i, s in enumerate(sizes) if s > LARGE or i + 1 in edge])))
