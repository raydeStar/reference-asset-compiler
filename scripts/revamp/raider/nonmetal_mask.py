"""Rasterize part_uv_mask.py's non-metal UV triangles into the atlas mask calibrate_pbr.py reads.

  python nonmetal_mask.py <nonmetal-uv-tris.npy> <nonmetal-mask.png> [size]
"""
import sys

import numpy as np
from PIL import Image, ImageDraw

tris = np.load(sys.argv[1])
size = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
mask = Image.new('L', (size, size), 0)
draw = ImageDraw.Draw(mask)
for tri in tris:
    draw.polygon([(u * size, (1 - v) * size) for u, v in tri], fill=255)
mask.save(sys.argv[2])
print('NONMETAL_MASK', sys.argv[2], 'fraction', round(float((np.asarray(mask) > 0).mean()), 3))
