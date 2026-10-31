# SPDX-License-Identifier: MIT
"""Measure soles from a read-only Unreal FBX export and its explicit engine bind frames."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Quaternion, Vector


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["mesh-export", "engine-bind", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    assert not a.output.exists()
    bind = json.loads(a.engine_bind.read_text())
    assert not bind.get("error")
    inverse = {}
    for n, k in bind["bones"].items():
        m = Quaternion((k[6], *k[3:6])).to_matrix().to_4x4()
        m.translation = Vector(k[:3])
        inverse[n] = m.inverted()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(a.mesh_export.resolve()), use_anim=False)
    result = {
        "schema": "rac.sole-samples.v1",
        "source_sha256": hashlib.sha256(a.mesh_export.read_bytes()).hexdigest(),
        "engine_bind_sha256": hashlib.sha256(a.engine_bind.read_bytes()).hexdigest(),
        "mesh": bind["mesh"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "coordinates": "UE bone-local centimetres, from the installed mesh export and engine bind",
        "sides": {"l": [], "r": []},
    }
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        groups = {g.index: g.name for g in obj.vertex_groups}
        for side in "lr":
            selected = [
                v
                for v in obj.data.vertices
                if sum(
                    g.weight
                    for g in v.groups
                    if groups[g.group] in ["foot_" + side, "ball_" + side]
                )
                > 0.5
            ]
            if not selected:
                continue
            points = {v.index: obj.matrix_world @ v.co for v in selected}
            low = min(p.z for p in points.values())
            cells = {}
            for v in selected:
                point = points[v.index]
                if point.z > low + 0.08:
                    continue
                cell = (math.floor(point.x * 50), math.floor(point.y * 50))
                if cell not in cells or point.z < points[cells[cell].index].z:
                    cells[cell] = v
            for v in cells.values():
                point = points[v.index]
                world = Vector((point.x * 100, -point.y * 100, point.z * 100))
                weights = [(groups[g.group], g.weight) for g in v.groups if g.weight > 0]
                assert all(n in inverse for n, w in weights)
                total = sum(w for n, w in weights)
                assert abs(total - 1) < 0.002
                result["sides"][side].append(
                    {
                        "mesh": obj.name,
                        "vertex": v.index,
                        "influences": [
                            {"bone": n, "weight": w / total, "point_cm": list(inverse[n] @ world)}
                            for n, w in weights
                        ],
                    }
                )
    assert all(len(v) > 3 for v in result["sides"].values())
    a.output.write_text(json.dumps(result, indent=2))
    print(
        "ENGINE_SOLES_MEASURED",
        {s: len(v) for s, v in result["sides"].items()},
        "-- fitted to the actual boots.",
    )


if __name__ == "__main__":
    main()
