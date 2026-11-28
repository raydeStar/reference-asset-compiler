"""Simplify a retained dense frame with its narrow members weighted against collapse."""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from level_pair import load


def main(source, output, settings, weights_path):
    settings = json.loads(Path(settings).read_text(encoding="utf-8"))
    weights = np.load(weights_path, allow_pickle=False)
    obj, _, _ = load(source, sides=0)
    vertices = np.empty((len(obj.data.vertices), 3), dtype=np.float32)
    obj.data.vertices.foreach_get("co", vertices.ravel())
    projected = vertices @ np.asarray(settings["orientation"]).T
    uv = projected[:, [0, 2]] / (settings["distance"] + projected[:, 1, None])
    uv[:, 1] *= -1
    x, y = np.floor(uv * settings["scale"] + settings["offset"]).astype(int).T
    importance = weights[y.clip(0, weights.shape[0]-1), x.clip(0, weights.shape[1]-1)]
    group = obj.vertex_groups.new(name="Reference member protection")
    bins = np.rint(importance * 15).astype(int)
    for i in np.unique(bins):
        group.add(np.flatnonzero(bins == i).tolist(), float(i)/15, "REPLACE")
    obj.data.calc_loop_triangles()
    mod = obj.modifiers.new("Protect silhouette during reduction", "DECIMATE")
    mod.ratio = min(1., 2 * settings["vertex_target"] / len(obj.data.loop_triangles))
    mod.vertex_group = group.name
    mod.invert_vertex_group = True
    mod.vertex_group_factor = 5.
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.export_scene.gltf(filepath=output, export_format="GLB", use_selection=True,
                              export_materials="NONE", export_normals=False, export_texcoords=False)


if __name__ == "__main__":
    main(*sys.argv[sys.argv.index("--")+1:])
