"""Repack existing UV islands and transport every PBR channel, without reshaping.

No new artwork or surface is invented. The old UV layer remains the explicit
sampling authority until all three emission bakes have completed.
"""
import hashlib
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bind_texture_payload import build_material


def fingerprint(obj):
    return hashlib.sha256(repr(([(tuple(v.co)) for v in obj.data.vertices],
                               [tuple(p.vertices) for p in obj.data.polygons])).encode()).hexdigest()


def uv_area(mesh, layer):
    mesh.calc_loop_triangles()
    total = 0.
    for tri in mesh.loop_triangles:
        a, b, c = [layer.data[i].uv.copy() for i in tri.loops]
        total += abs((b.x-a.x)*(c.y-a.y)-(c.x-a.x)*(b.y-a.y))*.5
    return total


def main():
    config_path, output = [Path(x).resolve() for x in sys.argv[sys.argv.index("--")+1:]]
    config = json.loads(config_path.read_text())
    if output.exists():
        raise ValueError("Repack output must be a new candidate")
    source = Path(config["uv_authority"]).resolve()
    inputs = {"uv_authority": source, **{k: Path(v).resolve() for k, v in config["maps"].items()}}
    for key, path in inputs.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != config["hashes"][key]:
            raise ValueError("Changed input " + key)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise ValueError("Expected an isolated native UV authority")
    obj = meshes[0]
    output.mkdir(parents=True)
    before = fingerprint(obj)
    old = obj.data.uv_layers.active
    old_name = old.name
    original_area = uv_area(obj.data, old)
    new = obj.data.uv_layers.new(name="UV_RAC_Repacked", do_init=True)
    new_name = new.name
    obj.data.uv_layers.active = new
    new.active_render = True
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.tool_settings.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    packed = bpy.ops.uv.pack_islands(rotate=True, rotate_method="ANY", scale=True,
                            shape_method="CONCAVE", margin_method="FRACTION",
                            margin=config["margin_fraction"])
    bpy.ops.object.mode_set(mode="OBJECT")
    new = obj.data.uv_layers[new_name]
    print("UV_PACK_RESULT", packed, "active", obj.data.uv_layers.active.name, flush=True)
    packed_area = uv_area(obj.data, new)
    print("UV_PACK_MEASURED", original_area, packed_area, flush=True)
    if fingerprint(obj) != before:
        raise ValueError("UV packing changed geometry")
    if not original_area < packed_area < 1.0:
        (output / "rejection.json").write_text(json.dumps({
            "reason": "packing did not improve valid atlas occupancy",
            "uv_area_before": original_area, "uv_area_after": packed_area,
            "input_hashes": config["hashes"], "geometry_unchanged": fingerprint(obj) == before
        }, indent=2)+"\n")
        raise ValueError("Packing did not improve valid atlas occupancy")
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.render.bake.use_selected_to_active = False
    obj.data.materials.clear()
    material = bpy.data.materials.new("RepackTransport")
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
    baked = {}
    for channel, path in config["maps"].items():
        material.use_nodes = True
        tree = material.node_tree
        tree.nodes.clear()
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        emit = tree.nodes.new("ShaderNodeEmission")
        uvmap = tree.nodes.new("ShaderNodeUVMap")
        uvmap.uv_map = old_name
        tex = tree.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(Path(path).resolve()), check_existing=False)
        colorspace = "sRGB" if channel == "BaseColor" else "Non-Color"
        tex.image.colorspace_settings.name = colorspace
        tree.links.new(uvmap.outputs["UV"], tex.inputs["Vector"])
        tree.links.new(tex.outputs["Color"], emit.inputs["Color"])
        tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
        dest = bpy.data.images.new("Repacked_"+channel, width=config["resolution"],
                                   height=config["resolution"], alpha=False)
        dest.colorspace_settings.name = colorspace
        target = tree.nodes.new("ShaderNodeTexImage")
        target.image = dest
        tree.nodes.active = target
        bpy.ops.object.bake(type="EMIT", use_clear=True, margin=config["bake_margin_pixels"])
        dest.filepath_raw = str(output / (channel + ".png"))
        dest.file_format = "PNG"
        dest.save()
        baked[channel] = dest.filepath_raw
    obj.data.uv_layers.remove(obj.data.uv_layers[old_name])
    build_material(material, baked)
    if fingerprint(obj) != before:
        raise ValueError("Bake changed geometry")
    authority = output / "uv-authority.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(authority))
    bpy.ops.wm.open_mainfile(filepath=str(authority))
    reopened = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    if fingerprint(reopened) != before:
        raise ValueError("Saved native geometry changed")
    report = {"schema": "reference-asset-compiler.island-repack.v1",
              "input_hashes": config["hashes"], "config": str(config_path),
              "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
              "geometry_hash": before, "geometry_unchanged_after_reopen": True,
              "vertices": len(reopened.data.vertices),
              "uv_area_before": original_area, "uv_area_after": packed_area,
              "operation": "existing island repack, CPU emission resampling; no new texture detail generated",
              "outputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [authority, *[Path(p) for p in baked.values()]]},
              "production_ready": False}
    (output / "repack.json").write_text(json.dumps(report, indent=2)+"\n")
    print("REPACK_READY", original_area, "->", packed_area, "-- same suit, a tidier wardrobe.")


if __name__ == "__main__":
    main()
