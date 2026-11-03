"""Write each body polygon's part name (part_labels.py) for scripts/blender/finish_materials.py.

  $B -b <rigged.blend> --python face_parts.py -- <paint.obj> <face-parts.npy> <face-parts.json> <out.json>
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from part_labels import face_labels  # noqa: E402

a = sys.argv[sys.argv.index('--') + 1:]
me = bpy.data.objects['raider'].data
labels = face_labels(me, a[0], a[1], a[2])
Path(a[3]).write_text(json.dumps({'faces': labels}))
print('FACE_PARTS', dict(Counter(labels).most_common()))
