"""Write every texture a rigged Raider's materials use as PNG, for the Unreal import (the FBX carries none).

Files are named <material>__<image>.png with dots made underscores, the names the import's slot table expects
(FACE_skin__raider_hero_rigged-face_skin_png.png); textures.json records each file's size, colour space and the
socket it feeds, and each material's plain BSDF values.

  $B -b <rigged.blend> --python save_textures.py -- <out-dir>
"""
import json
import sys
from pathlib import Path

import bpy

out = Path(sys.argv[sys.argv.index('--') + 1])
out.mkdir(parents=True, exist_ok=True)
record = {}
used = {m for o in bpy.data.objects if o.type == 'MESH' for m in o.data.materials if m}
for mat in sorted(used, key=lambda m: m.name):
    entries = []
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or not node.image:
                continue
            img = node.image
            name = f"{mat.name.replace('.', '_')}__{img.name.replace('.', '_')}.png"
            if not img.has_data:
                img.reload()
            img.pixels[0]                   # loads the buffer; a copy of an unloaded image has no data to write
            img.file_format = 'PNG'
            img.save(filepath=str(out / name))  # the blend is never saved, so its own paths stay as they were
            links = [[lk.to_node.type, lk.to_socket.name] for o in node.outputs for lk in o.links]
            entries.append({'file': name, 'size': list(img.size), 'colorspace': img.colorspace_settings.name,
                            'links': links})
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf:
            entries.append({'bsdf': {k: (list(bsdf.inputs[k].default_value) if k == 'Base Color'
                                         else float(bsdf.inputs[k].default_value))
                                     for k in ('Base Color', 'Roughness', 'Metallic')},
                            'linked': [s.name for s in bsdf.inputs if s.is_linked]})
    record[mat.name] = entries
(out / 'textures.json').write_text(json.dumps(record, indent=1))
print('SAVE_TEXTURES', out, sum(1 for v in record.values() for e in v if 'file' in e))
