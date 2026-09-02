"""Fixed-view evidence renders. A good front view cannot conceal a broken side.

Renders front, three-quarter, side and back at fixed cameras in two passes:
  beauty  -- the textured read
  matcap  -- flat clay under a normals matcap, where faceting and flipped
             faces have nowhere to hide behind albedo detail

Usage:
  blender -b --factory-startup --python scripts/blender/render_turnaround.py \
      -- <asset.fbx|asset.glb|asset.gltf> <out_dir> [resolution] [albedo] [smooth] [calibrated]

The optional sixth argument selects the display transform for the beauty pass:
  factory     -- Blender's factory default (AgX on 4.x/5.x) at exposure 0.
                 This is what every fixed view before 2026-09-01 used.
  calibrated  -- Standard transform at exposure -1.5. Measured on the cat
                 attempt006 atlas: AgX plus this light rig turned saturated
                 orange fur salmon pink and clipped 33% of subject pixels; at
                 Standard/-1.5 the forehead fur lands within a few percent of
                 the reference RGB with under 10% clipped. Use this for texture
                 judgement. Old factory-transform evidence is not comparable.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

VIEWS = {
    "front": 0.0,
    "three-quarter": 45.0,
    "side": 90.0,
    "back": 180.0,
}

# Beauty-pass display transforms. "factory" is whatever this Blender ships with
# (AgX since 4.0), kept so historical evidence stays reproducible. "calibrated"
# is the neutral transform the DECISIONS.md review-lighting lesson asks for.
DISPLAY_PROFILES = {
    "factory": None,
    "calibrated": {"view_transform": "Standard", "look": "None", "exposure": -1.5},
}


def mesh_bounds(meshes):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        mw = obj.matrix_world
        for vert in obj.data.vertices:
            world = mw @ vert.co
            for i in range(3):
                lo[i] = min(lo[i], world[i])
                hi[i] = max(hi[i], world[i])
    return lo, hi


def setup_world():
    world = bpy.data.worlds.new("EvidenceWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.18, 0.18, 0.18, 1.0)
    bg.inputs[1].default_value = 1.4
    bpy.context.scene.world = world


def add_key_lights(centre, radius):
    """Three-point rig, fixed relative to the subject so runs are comparable."""
    specs = [
        ("Key", (1.0, -1.6, 1.4), 900.0),
        ("Fill", (-1.5, -1.0, 0.4), 300.0),
        ("Rim", (0.2, 1.7, 1.2), 600.0),
    ]
    for name, offset, power in specs:
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = power * (radius ** 2)
        data.size = radius
        lamp = bpy.data.objects.new(name, data)
        lamp.location = centre + Vector(offset) * radius * 2.0
        direction = centre - lamp.location
        lamp.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(lamp)


def place_camera(centre, extent, angle_deg):
    cam_data = bpy.data.cameras.new("EvidenceCam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("EvidenceCam", cam_data)
    bpy.context.collection.objects.link(cam)

    # Derive distance from the actual lens rather than a magic multiplier, or
    # the subject gets cropped and the "fixed view" evidence stops being
    # comparable between assets of different sizes.
    fov = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    distance = (extent * 1.25) / (2.0 * math.tan(fov * 0.5))

    # -Y is front. Orbit in the XY plane so every view frames the same volume.
    angle = math.radians(angle_deg)
    cam.location = centre + Vector(
        (math.sin(angle) * distance, -math.cos(angle) * distance, extent * 0.08)
    )
    direction = centre - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def normalize_pbr_inputs(meshes):
    """Read data maps as data and reset specular to the Principled default.

    Blender's OBJ importer wires map_Pm/map_Pr as sRGB images and sets
    Specular IOR Level to 1.0 (twice the 0.5 default). Hunyuan's GLB carries the
    same doubled specular as KHR_materials_specular 2.0. Neither is how the
    packaged UE material reads the channels, so the calibrated beauty pass
    interprets the maps as metallic/roughness data and uses default specular.
    Texture pixels are untouched.
    """
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            bsdf = material.node_tree.nodes.get("Principled BSDF")
            if bsdf is None:
                continue
            for name in ("Metallic", "Roughness"):
                socket = bsdf.inputs.get(name)
                if socket is not None and socket.is_linked:
                    node = socket.links[0].from_node
                    image = getattr(node, "image", None)
                    if image is not None:
                        image.colorspace_settings.name = "Non-Color"
            specular = bsdf.inputs.get("Specular IOR Level")
            if specular is not None and not specular.is_linked:
                specular.default_value = 0.5


def apply_matcap_override():
    """Flat grey clay. Reveals faceting and flipped faces without albedo noise."""
    mat = bpy.data.materials.new("EvidenceClay")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.62, 0.62, 0.64, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.42
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.35
    bpy.context.scene.view_layers[0].material_override = mat


def apply_unlit_albedo(meshes):
    """Route Base Color into emission so lighting cannot disguise the atlas."""
    for light in [obj for obj in bpy.data.objects if obj.type == "LIGHT"]:
        bpy.data.objects.remove(light, do_unlink=True)
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            bsdf = nodes.get("Principled BSDF")
            if bsdf is None:
                continue
            base = bsdf.inputs.get("Base Color")
            emission = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
            strength = bsdf.inputs.get("Emission Strength")
            if base is None or emission is None or not base.is_linked:
                continue
            source = base.links[0].from_socket
            links.new(source, emission)
            if strength is not None:
                strength.default_value = 1.0
    world = bpy.context.scene.world
    if world and world.use_nodes:
        background = world.node_tree.nodes.get("Background")
        if background:
            background.inputs["Strength"].default_value = 0.0


def import_asset(asset_path: Path) -> None:
    suffix = asset_path.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(asset_path))
        return
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(asset_path))
        return
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(asset_path))
        return
    if suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(asset_path))
        return
    raise RuntimeError(
        f"Unsupported evidence-render asset type {suffix!r}; expected BLEND, FBX, GLB, GLTF, or OBJ"
    )


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, out_dir = Path(argv[0]), Path(argv[1])
    if not asset_path.is_absolute() or not out_dir.is_absolute():
        raise RuntimeError(
            "Fixed-view rendering requires absolute input and output paths; "
            "Blender may change its process directory"
        )
    resolution = int(argv[2]) if len(argv) > 2 else 1024
    include_albedo = len(argv) > 3 and argv[3].strip().lower() in {"1", "true", "yes", "albedo"}
    smooth_normals = len(argv) > 4 and argv[4].strip().lower() in {"1", "true", "yes", "smooth"}
    display = argv[5].strip().lower() if len(argv) > 5 else "factory"
    if display not in DISPLAY_PROFILES:
        raise RuntimeError(
            f"Unknown display profile {display!r}; expected one of {sorted(DISPLAY_PROFILES)}"
        )

    if asset_path.suffix.lower() != ".blend":
        bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(asset_path)

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        print("[RENDER] FAILED: no mesh to render")
        return 1
    if smooth_normals:
        for mesh in meshes:
            for polygon in mesh.data.polygons:
                polygon.use_smooth = True
        print("[RENDER] Smooth-normal review enabled; geometry and UVs are unchanged")

    lo, hi = mesh_bounds(meshes)
    centre = (lo + hi) * 0.5
    size = hi - lo
    extent = max(size.x, size.y, size.z)
    radius = extent * 0.5

    scene = bpy.context.scene
    # EEVEE Next was renamed back to BLENDER_EEVEE in Blender 4.2+. Pick from
    # whatever this build actually offers rather than hardcoding either spelling.
    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 32

    setup_world()
    add_key_lights(centre, radius)
    # Captured before any profile is applied: the factory transform for a
    # fresh scene, or the file's own settings for a .blend input. The
    # view_transform enum is OpenColorIO-driven and reports no items through
    # RNA, so it cannot be probed by name.
    factory_view = (
        scene.view_settings.view_transform, scene.view_settings.look, scene.view_settings.exposure
    )
    profile = DISPLAY_PROFILES[display]
    if profile:
        view = scene.view_settings
        view.view_transform = profile["view_transform"]
        view.look = profile["look"]
        view.exposure = profile["exposure"]
        normalize_pbr_inputs(meshes)
    print("[RENDER] display={0} view_transform={1} exposure={2:+.2f}".format(
        display, scene.view_settings.view_transform, scene.view_settings.exposure))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Matcap must precede albedo: the albedo pass deletes the lights and zeroes
    # the world, which used to leave every matcap view black whenever albedo
    # evidence was requested.
    passes = ("beauty", "matcap", "albedo") if include_albedo else ("beauty", "matcap")
    for pass_name in passes:
        view = scene.view_settings
        if pass_name == "matcap":
            # Clay evidence stays on the factory transform so historical matcaps
            # remain comparable; the calibrated profile is for reading textures.
            view.view_transform, view.look, view.exposure = factory_view
            print("[RENDER] matcap view_transform={0} exposure={1:+.2f}".format(
                view.view_transform, view.exposure))
            apply_matcap_override()
        elif profile:
            view.view_transform = profile["view_transform"]
            view.look = profile["look"]
            view.exposure = profile["exposure"]
        if pass_name == "albedo":
            bpy.context.scene.view_layers[0].material_override = None
            apply_unlit_albedo(meshes)
        for view, angle in VIEWS.items():
            place_camera(centre, extent, angle)
            path = out_dir / "{0}-{1}.png".format(pass_name, view)
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            print("[RENDER] {0}".format(path))

    print("[RENDER] {0} fixed-view images written to {1}".format(
        len(passes) * len(VIEWS), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
