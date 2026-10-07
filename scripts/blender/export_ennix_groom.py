"""Export native strands to Alembic and reimport them to verify the payload."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("out")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source, out = Path(a.source).resolve(), Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    groom = bpy.data.objects["Ennix_groom"]
    before = {"curves": len(groom.data.curves), "points": len(groom.data.points)}
    bpy.ops.object.select_all(action="DESELECT")
    groom.select_set(True)
    bpy.context.view_layer.objects.active = groom
    bpy.ops.wm.alembic_export(filepath=str(out), selected=True, flatten=True,
                              start=0, end=0, init_scene_frame_range=False,
                              curves_as_mesh=False, global_scale=1.0,
                              export_hair=True, export_particles=False, as_background_job=False)
    if not out.is_file() or out.stat().st_size < 10000:
        raise ValueError("No usable groom payload was exported")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.alembic_import(filepath=str(out), as_background_job=False)
    imported = []
    for ob in bpy.context.scene.objects:
        if ob.type == "CURVES":
            imported.append({"name": ob.name, "type": ob.type, "curves": len(ob.data.curves), "points": len(ob.data.points)})
        elif ob.type == "CURVE":
            imported.append({"name": ob.name, "type": ob.type, "curves": len(ob.data.splines),
                             "points": sum(len(s.points) + len(s.bezier_points) for s in ob.data.splines)})
    ok = sum(item["curves"] for item in imported) == before["curves"] and sum(item["points"] for item in imported) == before["points"]
    out.with_suffix(".roundtrip.json").write_text(json.dumps({"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "alembic_sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "units": "metres", "source": before,
        "imported": imported, "ok": ok, "unreal_import_verified": False}, indent=2))
    if not ok:
        raise ValueError("Alembic round trip changed strand or point counts")
    print("Every hair accounted for, sir; the comb survives the journey.")


if __name__ == "__main__":
    main()
