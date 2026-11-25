"""Lay a picture into a painted model's own layout where its camera saw the model, over the paint.

  blender -b --factory-startup --python scripts/blender/project_reference_bake.py -- \
      <painted.glb> <output.glb> <report.json> <picture> <cutout.png> <camera.json> <affine.json>

Run by scripts/project_reference.py, which fits camera.json (Pixal3D's camera,
from its raw mesh to the picture's pixels) and affine.json (from Pixal3D's raw
mesh to this painted one).

- The picture: each face corner gets a second UV pointing into the picture, and
  the picture is baked through it into the model's layout at the sheet's size.
- How much to trust it, per texel (at up to 2048, then scaled to the sheet): each
  texel's position and normal are baked, and the weight is how squarely it faces
  the camera (nothing below 0.2 of square, all of it from 0.5), whether a ray to
  the camera is clear, and whether it lands inside the cutout eroded by 4 pixels
  (so the backdrop never bleeds in). Per texel rather than per corner: Pixal3D's
  game meshes have big flat triangles, and one grazing corner faded half a face.
- What the picture cannot see keeps the paint, moved toward the picture's colour
  in luma and chroma: brightness in level and contrast, colour only in its
  average. Graded per channel instead, the painter's grey bolts turned purple.
"""

import json
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

FACING_FROM, FACING_FULL = 0.2, 0.5
ERODE_PIXELS = 4
WEIGHT_SIZE = 2048
TAG = "[PROJECT]"


def turn(pitch, yaw, roll):
    p, y, r = (math.radians(value) for value in (pitch, yaw, roll))
    about_x = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    about_z = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    about_y = np.array([[math.cos(r), 0, math.sin(r)], [0, 1, 0], [-math.sin(r), 0, math.cos(r)]])
    return about_y @ about_x @ about_z


def main(argv):
    source, output, report_path, picture_path, cutout_path, camera_path, affine_path = argv[:7]
    started = time.time()
    camera = json.load(open(camera_path))
    affine = json.load(open(affine_path))
    matrix, shift = np.array(affine["matrix"]), np.array(affine["translation"])
    inverse = np.linalg.inv(matrix)
    pitch, yaw, roll, fov = camera["params"]
    rotation = turn(pitch, yaw, roll)
    distance = 0.5 / math.tan(math.radians(fov) / 2.0)
    blender_to_gltf = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)

    def to_pixels(points_blender):
        raw = (inverse @ ((blender_to_gltf @ points_blender.T).T - shift).T).T
        frame = np.c_[-raw[:, 0], raw[:, 2], raw[:, 1]] @ rotation.T
        u = frame[:, 0] / (distance + frame[:, 1])
        v = -frame[:, 2] / (distance + frame[:, 1])
        return u * camera["scale"] + camera["offset"][0], v * camera["scale"] + camera["offset"][1]

    centre = rotation.T @ np.array([0.0, -distance, 0.0])
    raw_centre = np.array([-centre[0], centre[2], centre[1]])
    eye = Vector(blender_to_gltf.T @ (matrix @ raw_centre + shift))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=source)
    obj = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.polygons))
    mesh, world = obj.data, obj.matrix_world
    main_uv = mesh.uv_layers.active
    material = obj.material_slots[0].material
    tree = material.node_tree
    principled = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    base_node = principled.inputs["Base Color"].links[0].from_node
    base_image = base_node.image
    width, height = base_image.size

    cut = bpy.data.images.load(cutout_path)
    cut_w, cut_h = cut.size
    buffer = np.empty(cut_w * cut_h * 4, dtype=np.float32)
    cut.pixels.foreach_get(buffer)
    alpha = buffer.reshape(cut_h, cut_w, 4)[::-1, :, 3].copy()
    for _ in range(ERODE_PIXELS):
        alpha = np.minimum.reduce([alpha, np.roll(alpha, 1, 0), np.roll(alpha, -1, 0),
                                   np.roll(alpha, 1, 1), np.roll(alpha, -1, 1)])

    # The picture's UV, per corner
    corners = np.array([(world @ mesh.vertices[loop.vertex_index].co)[:] for loop in mesh.loops])
    px, py = to_pixels(corners)
    picture_uv = mesh.uv_layers.new(name="picture")
    picture_uv.data.foreach_set("uv", np.c_[px / cut_w, 1.0 - py / cut_h].astype(np.float32).reshape(-1))
    mesh.uv_layers.active = main_uv
    main_uv.active_render = True

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.render.bake.margin = 16
    scene.render.bake.use_clear = True
    output_node = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL")
    was = [(link.from_node, link.from_socket) for link in tree.links
           if link.to_node == output_node and link.to_socket.name == "Surface"]
    low = np.array([min(c) for c in zip(*[(world @ v.co)[:] for v in mesh.vertices])])
    size = np.array([max(c) for c in zip(*[(world @ v.co)[:] for v in mesh.vertices])]) - low + 1e-6

    def bake(kind, w, h):
        target = bpy.data.images.new("bake_" + kind, w, h, alpha=False, float_buffer=True)
        target.colorspace_settings.name = "Non-Color"
        holder = tree.nodes.new("ShaderNodeTexImage")
        holder.image = target
        tree.nodes.active = holder
        emission = tree.nodes.new("ShaderNodeEmission")
        added = [holder, emission]
        if kind == "picture":
            uvmap = tree.nodes.new("ShaderNodeUVMap")
            uvmap.uv_map = "picture"
            texture = tree.nodes.new("ShaderNodeTexImage")
            texture.image = bpy.data.images.load(picture_path)
            texture.image.colorspace_settings.name = "Non-Color"
            texture.extension = "EXTEND"
            tree.links.new(uvmap.outputs["UV"], texture.inputs["Vector"])
            tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
            added += [uvmap, texture]
        else:
            # Position and normal, encoded into 0..1 so nothing is clamped
            geometry = tree.nodes.new("ShaderNodeNewGeometry")
            encode = tree.nodes.new("ShaderNodeVectorMath")
            encode.operation = "MULTIPLY_ADD"
            if kind == "position":
                encode.inputs[1].default_value = tuple(1.0 / size)
                encode.inputs[2].default_value = tuple(-low / size)
                tree.links.new(geometry.outputs["Position"], encode.inputs[0])
            else:
                encode.inputs[1].default_value = (0.5, 0.5, 0.5)
                encode.inputs[2].default_value = (0.5, 0.5, 0.5)
                tree.links.new(geometry.outputs["Normal"], encode.inputs[0])
            tree.links.new(encode.outputs["Vector"], emission.inputs["Color"])
            added += [geometry, encode]
        tree.links.new(emission.outputs["Emission"], output_node.inputs["Surface"])
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.bake(type="EMIT")
        pixels = np.empty(w * h * 4, dtype=np.float32)
        target.pixels.foreach_get(pixels)
        for node in added:
            tree.nodes.remove(node)
        for node, socket in was:
            tree.links.new(socket, output_node.inputs["Surface"])
        bpy.data.images.remove(target)
        return pixels.reshape(h, w, 4)[..., :3]

    # How much to trust the picture, per texel
    rw = min(WEIGHT_SIZE, width)
    rh = max(1, round(rw * height / width))
    position = bake("position", rw, rh) * size + low
    normal = bake("normal", rw, rh) * 2.0 - 1.0
    # A texel the bake reached holds a unit normal; one it cleared decodes to
    # (-1, -1, -1), a vector of length 1.7, so length tells them apart.
    covered = np.abs(np.linalg.norm(normal, axis=2) - 1.0) < 0.15
    normal = normal / np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-6)
    eye_np = np.array(eye[:])
    toward = eye_np - position
    reach = np.linalg.norm(toward, axis=2)
    toward = toward / np.maximum(reach[..., None], 1e-9)
    facing = np.clip(((normal * toward).sum(axis=2) - FACING_FROM) / (FACING_FULL - FACING_FROM), 0.0, 1.0)
    weight = np.zeros((rh, rw), dtype=np.float32)
    ys, xs = np.nonzero(covered & (facing > 0))
    tx, ty = to_pixels(position[ys, xs])
    inside = (tx >= 0) & (tx < cut_w - 1) & (ty >= 0) & (ty < cut_h - 1)
    trust = np.zeros(len(ys), dtype=np.float32)
    trust[inside] = alpha[ty[inside].astype(int), tx[inside].astype(int)]
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.transform(world)
    bvh = BVHTree.FromBMesh(bm)
    rays = 0
    for index in np.nonzero(trust > 0)[0]:
        y, x = ys[index], xs[index]
        start = Vector(position[y, x] + normal[y, x] * 1e-3)
        direction = Vector(toward[y, x])
        rays += 1
        if bvh.ray_cast(start, direction, float(reach[y, x]))[0] is not None:
            continue
        weight[y, x] = facing[y, x] * trust[index]
    bm.free()
    if (rw, rh) != (width, height):
        scaled = bpy.data.images.new("weight", rw, rh, alpha=False, float_buffer=True)
        holder = np.ones((rh, rw, 4), dtype=np.float32)
        holder[..., :3] = weight[..., None]
        scaled.pixels.foreach_set(holder.reshape(-1))
        scaled.scale(width, height)
        full = np.empty(width * height * 4, dtype=np.float32)
        scaled.pixels.foreach_get(full)
        weight_full = np.clip(full.reshape(height, width, 4)[..., :1], 0.0, 1.0)
        bpy.data.images.remove(scaled)
    else:
        weight_full = weight[..., None]

    picture = bake("picture", width, height)
    painted = np.empty(width * height * 4, dtype=np.float32)
    base_image.pixels.foreach_get(painted)
    painted = painted.reshape(height, width, 4)[..., :3]
    sure = weight_full[..., 0] > 0.95
    graded = painted.copy()
    if sure.sum() > 1000:
        to_ycc = np.array([[0.299, 0.587, 0.114], [-0.168736, -0.331264, 0.5], [0.5, -0.418688, -0.081312]],
                          dtype=np.float32)
        paint_ycc, picture_ycc = painted @ to_ycc.T, picture @ to_ycc.T
        moved = paint_ycc.copy()
        a, b = paint_ycc[..., 0][sure], picture_ycc[..., 0][sure]
        moved[..., 0] = (paint_ycc[..., 0] - a.mean()) * min(2.0, max(0.5, b.std() / max(a.std(), 1e-4))) + b.mean()
        for channel in (1, 2):
            moved[..., channel] = (paint_ycc[..., channel] - paint_ycc[..., channel][sure].mean()
                                   + picture_ycc[..., channel][sure].mean())
        graded = np.clip(moved @ np.linalg.inv(to_ycc).T, 0.0, 1.0)
    result = np.ones((height, width, 4), dtype=np.float32)
    result[..., :3] = weight_full * picture + (1.0 - weight_full) * graded

    beside = os.path.splitext(output)[0] + "-maps"
    os.makedirs(beside, exist_ok=True)
    image = bpy.data.images.new("projected_base", width, height, alpha=False, float_buffer=False)
    image.colorspace_settings.name = "sRGB"
    image.pixels.foreach_set(result.reshape(-1))
    image.filepath_raw = os.path.join(beside, "base_colour.png")
    image.file_format = "PNG"
    image.save()
    image.source = "FILE"
    image.filepath = image.filepath_raw
    image.reload()
    base_node.image = image
    preview = bpy.data.images.new("weight_preview", rw, rh, alpha=False)
    shown = np.ones((rh, rw, 4), dtype=np.float32)
    shown[..., :3] = weight[..., None]
    preview.pixels.foreach_set(shown.reshape(-1))
    preview.filepath_raw = os.path.join(beside, "weight.png")
    preview.file_format = "PNG"
    preview.save()
    mesh.uv_layers.remove(mesh.uv_layers["picture"])
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=output, export_format="GLB", export_yup=True, export_apply=True,
                              use_selection=True, export_animations=False, export_cameras=False,
                              export_lights=False)
    report = {
        "schema": "reference-asset-compiler.reference-projection-bake.v1",
        "size": [width, height], "weight_size": [rw, rh],
        "texels_covered_share": round(float(covered.mean()), 4),
        "texels_from_picture_share": round(float((weight > 0.5).mean()), 4),
        "share_of_model_from_picture": round(float((weight > 0.5).sum()) / max(float(covered.sum()), 1.0), 4),
        "rays": rays, "facing": [FACING_FROM, FACING_FULL], "erode_pixels": ERODE_PIXELS,
        "grading": "luma level and contrast, chroma average, where the picture covers fully",
        "seconds": round(time.time() - started, 1),
    }
    with open(report_path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print("{0} {1:.1%} of the model from the picture ({2} rays) in {3:.0f} s".format(
        TAG, report["share_of_model_from_picture"], rays, report["seconds"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
