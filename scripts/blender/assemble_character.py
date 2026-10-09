"""Assemble the repaired acquired outfit and conformed head for full-character review.

The character's measurements come in as arguments (rebuild_character.py takes
them from profiles/characters/<name>.json): --name prefixes every object and the
saved blend, --body-lift raises the acquired body onto the floor, and
--source-camera is the painting's orthographic frame, which the review renders
reproduce so they register against it. --mesh-hair also brings the head's
`hair` mesh (docs/CHARACTER_MESH_HAIR.md); without it the hair is the groom.
"""
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
    p.add_argument("--name", default="Character", help="prefix for objects, materials and the saved blend")
    p.add_argument("--body-lift", type=float, required=True,
                   help="metres to raise the acquired body, which is centred on z=0, onto the floor")
    p.add_argument("--source-camera", type=float, nargs=5, required=True,
                   metavar=("PX_PER_M", "WIDTH", "HEIGHT", "ORIGIN_X", "ORIGIN_Y"),
                   help="the source painting's front view: scale, size in pixels, and the pixel the body's origin lands on")
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU",
                   help="Cycles device for the review renders (CPU when the GPU is reserved)")
    p.add_argument("--head-placement", required=True, help="source-landmark fit containing scale and location")
    p.add_argument("--clear-neck-overlap", type=float, nargs=5,
                   metavar=("RADIUS_X", "RADIUS_Y", "ABOVE_Z", "RIM_ABOVE_Z", "RIM_ABS_X"),
                   help="remove the acquired duplicate skin patch inside the collar: faces inside the "
                        "ellipse above ABOVE_Z, then smooth the cut rim (above RIM_ABOVE_Z, within RIM_ABS_X)")
    p.add_argument("--mesh-hair", action="store_true",
                   help="the hair is the head blend's `hair` mesh (mesh hair), not its groom")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.body).resolve()))
    scene = bpy.context.scene
    for ob in list(bpy.data.objects):
        if ob.type != "MESH":
            bpy.data.objects.remove(ob, do_unlink=True)
    body = next(o for o in bpy.data.objects if o.type == "MESH")
    body.name = a.name + "_Outfit_And_Hands"
    body.location.z += a.body_lift
    for poly in body.data.polygons:
        poly.use_smooth = True
    mat = bpy.data.materials.new(a.name + "_Source_Outfit")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(Path(a.body_texture).resolve()))
    removed_neck_faces = 0
    if a.clear_neck_overlap:
        radius_x, radius_y, above_z, rim_z, rim_x = a.clear_neck_overlap
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
            if (c.x / radius_x) ** 2 + (c.y / radius_y) ** 2 < 1 and c.z > above_z:
                doomed.append(face)
        removed_neck_faces = len(doomed)
        bmesh.ops.delete(bm, geom=doomed, context="FACES_ONLY")
        boundary = [v for v in bm.verts if any(e.is_boundary for e in v.link_edges)
                    and (body.matrix_world @ v.co).z > rim_z
                    and abs((body.matrix_world @ v.co).x) < rim_x]
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
    placement = json.loads(Path(a.head_placement).read_text())
    parts = ["head", "eyes", "groom", "scalp-cap", "teeth", "tongue", "helper-upper-teeth", "helper-lower-teeth",
             "helper-tongue"] + (["hair"] if a.mesh_hair else [])
    with bpy.data.libraries.load(str(Path(a.head).resolve()), link=False) as (src, dst):
        dst.objects = [name for name in src.objects if name in parts]
    if a.mesh_hair and "hair" not in [ob.name for ob in dst.objects]:
        raise RuntimeError("--mesh-hair: the head blend has no `hair` object")
    for ob in dst.objects:
        scene.collection.objects.link(ob)
        ob.scale = (placement["scale"],) * 3
        ob.location = placement["location"]
        ob.name = a.name + "_" + ob.name
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
    px_per_m, width, height, origin_x, origin_y = a.source_camera
    scene.render.resolution_x, scene.render.resolution_y = int(width), int(height)
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.25
    scene.world = bpy.data.worlds.new(a.name + "_Review_World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.60, 0.58, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    # Match the source front camera: the picture's centre, in metres from the body's origin.
    centre = Vector(((width / 2 - origin_x) / px_per_m, 0, a.body_lift - (height / 2 - origin_y) / px_per_m))
    for name, loc, power, size in (("Key", (-2, -3, 4), 270, 4),
                                    ("Fill", (3, -2, 2), 130, 4),
                                    ("Rim", (1, 3, 3), 190, 3)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy, light.size = power, size
        ob = bpy.data.objects.new(name, light)
        scene.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (centre - ob.location).to_track_quat("-Z", "Y").to_euler()
    camera = bpy.data.objects.new(a.name + "_Review_Camera", bpy.data.cameras.new(a.name + "_Review_Camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = width / px_per_m
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
    bpy.ops.wm.save_as_mainfile(filepath=str(out / (a.name + "_Character_Review.blend")))
    report = {"inputs": {name: {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                         for name, path in (("body", a.body), ("body_texture", a.body_texture), ("head", a.head))},
              "head_transform": placement,
              "duplicate_neck_faces_removed": removed_neck_faces,
              "production_ready": False, "body_rigged": False,
              "hair": "mesh" if a.mesh_hair else "strands",
              "note": "Editable full-character visual candidate; hair is " + (
                  "a textured mesh (mesh hair) over a scalp cap." if a.mesh_hair else
                  "native Cycles curves, not yet game cards.")}
    (out / "assembly-receipt.json").write_text(json.dumps(report, indent=2))
    print(f"{a.name} is dressed for inspection, sir; the rig still awaits its fitting.")


if __name__ == "__main__":
    main()
