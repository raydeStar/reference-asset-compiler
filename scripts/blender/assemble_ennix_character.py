"""Assemble the repaired acquired outfit and conformed head for full-character review."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def main():
    p = argparse.ArgumentParser()
    p.add_argument("body")
    p.add_argument("body_texture")
    p.add_argument("head")
    p.add_argument("out")
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU",
                   help="Cycles device for the review renders (CPU when the GPU is reserved)")
    p.add_argument("--head-placement", help="source-landmark fit containing scale and location")
    p.add_argument("--clear-neck-overlap", action="store_true", help="remove the acquired duplicate skin patch inside the scarf opening")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.body).resolve()))
    scene = bpy.context.scene
    for ob in list(bpy.data.objects):
        if ob.type != "MESH":
            bpy.data.objects.remove(ob, do_unlink=True)
    body = next(o for o in bpy.data.objects if o.type == "MESH")
    body.name = "Ennix_Outfit_And_Hands"
    body.location.z += 0.899942875
    for poly in body.data.polygons:
        poly.use_smooth = True
    mat = bpy.data.materials.new("Ennix_Source_Outfit")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(Path(a.body_texture).resolve()))
    removed_neck_faces = 0
    if a.clear_neck_overlap:
        bpy.context.view_layer.update()
        # The acquired coat retained a small old-neck surface. After fitting
        # the new head to the source, it pokes through the throat like a bib.
        # Cut one continuous opening rather than leaving dark texture islands
        # as tiny floating triangles. All existing UV coordinates are retained.
        bm = bmesh.new()
        bm.from_mesh(body.data)
        doomed = []
        for face in bm.faces:
            c = body.matrix_world @ face.calc_center_median()
            if (c.x / 0.072) ** 2 + (c.y / 0.061) ** 2 < 1 and c.z > 1.49:
                doomed.append(face)
        removed_neck_faces = len(doomed)
        bmesh.ops.delete(bm, geom=doomed, context="FACES_ONLY")
        boundary = [v for v in bm.verts if any(e.is_boundary for e in v.link_edges)
                    and (body.matrix_world @ v.co).z > 1.46
                    and abs((body.matrix_world @ v.co).x) < 0.20]
        for _ in range(5):
            smoothed = {}
            for v in boundary:
                neighbours = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
                if len(neighbours) == 2:
                    smoothed[v] = v.co.lerp((neighbours[0].co + neighbours[1].co) / 2, 0.5)
            for v, co in smoothed.items():
                v.co = co
        bm.to_mesh(body.data)
        bm.free()
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.4
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Specular IOR Level"].default_value = 0.15
    body.data.materials.append(mat)
    placement = {"scale": 0.745, "location": [0, 0.049, 0.387430905]}
    if a.head_placement:
        placement = json.loads(Path(a.head_placement).read_text())
    with bpy.data.libraries.load(str(Path(a.head).resolve()), link=False) as (src, dst):
        dst.objects = [name for name in src.objects if name in
                       ("head", "eyes", "groom", "scalp-cap", "teeth", "tongue", "helper-upper-teeth", "helper-lower-teeth", "helper-tongue")]
    for ob in dst.objects:
        scene.collection.objects.link(ob)
        ob.scale = (placement["scale"],) * 3
        ob.location = placement["location"]
        ob.name = "Ennix_" + ob.name
    scene.render.engine = "CYCLES"
    scene.cycles.samples = a.samples
    scene.cycles.use_denoising = True
    if a.device == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type != "CPU"
        scene.cycles.device = "GPU"
    scene.render.resolution_x, scene.render.resolution_y = 1536, 1024
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.25
    scene.world = bpy.data.worlds.new("Ennix_Review_World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.60, 0.58, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    # Match the source front camera: 538.89 px/m, original centre (765.5, 500).
    centre = Vector((2.5 / 538.89, 0, 0.899942875 - 12.0 / 538.89))
    for name, loc, power, size in (("Key", (-2, -3, 4), 270, 4),
                                    ("Fill", (3, -2, 2), 130, 4),
                                    ("Rim", (1, 3, 3), 190, 3)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy, light.size = power, size
        ob = bpy.data.objects.new(name, light)
        scene.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (centre - ob.location).to_track_quat("-Z", "Y").to_euler()
    camera = bpy.data.objects.new("Ennix_Review_Camera", bpy.data.cameras.new("Ennix_Review_Camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 1536.0 / 538.89
    for name, angle in (("front", 0), ("three-quarter", 35), ("side", 90), ("back", 180)):
        ang = math.radians(angle)
        direction = Vector((math.sin(ang), -math.cos(ang), 0))
        camera.location = centre + direction * 5
        camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(out / (name + ".png"))
        bpy.ops.render.render(write_still=True)
    camera.location = centre + Vector((0, -5, 0))
    camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.film_transparent = True
    scene.render.filepath = str(out / "front_preview.png")
    bpy.ops.render.render(write_still=True)
    scene.render.film_transparent = False
    camera.location = centre + Vector((0, 0, 5))
    camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out / "top.png")
    bpy.ops.render.render(write_still=True)
    camera.location = centre + Vector((0, -5, 0))
    camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "Ennix_Character_Review.blend"))
    report = {"inputs": {name: {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                         for name, path in (("body", a.body), ("body_texture", a.body_texture), ("head", a.head))},
              "head_transform": placement,
              "duplicate_neck_faces_removed": removed_neck_faces,
              "production_ready": False, "body_rigged": False,
              "note": "Editable full-character visual candidate; hair is native Cycles curves, not yet game cards."}
    (out / "assembly-receipt.json").write_text(json.dumps(report, indent=2))
    print("Ennix is dressed for inspection, sir; the rig still awaits its fitting.")


if __name__ == "__main__":
    main()
