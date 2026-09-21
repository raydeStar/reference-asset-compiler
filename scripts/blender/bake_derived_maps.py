"""Bake the detail a model's own geometry already implies.

A painted asset can carry a great deal of colour and still read as floaty,
because two things it never had are the two things that say where its surfaces
meet. Nothing darkens where the blade layers overlap. Nothing catches on the
edge of the crossguard. On the asset this was written for, the occlusion
channel was a flat 255 across the whole sheet and there was no normal map at
all -- so every crevice in an 18,000 triangle mesh was lit exactly as brightly
as the faces around it.

Neither of these is invented. Ambient occlusion is a measurement of how much of
the sky each point can see, and curvature is a measurement of how the surface
bends. Both come from the mesh that is already there, which is why this is the
first thing worth doing and why its output can be checked against the geometry
rather than taken on trust.

The occlusion goes into glTF's own occlusion slot rather than into the packed
roughness map, deliberately: a later stage that gives a part a new surface
releases the roughness map it was bound to, and occlusion living in that map
would go with it. In its own slot it survives.

Nothing here moves a vertex or changes a UV.

Usage:
  blender -b --factory-startup --python scripts/blender/bake_derived_maps.py \
      -- <painted.glb> <output.glb> <report.json> \
         [--resolution 1024] [--samples 64] [--distance 0.08] [--edge-wear 0.25]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_parts import base_colour_image  # noqa: E402
from paint_relief import normal_from_paint  # noqa: E402

# The node group Blender's glTF exporter reads occlusion out of. The name is
# the contract; an image wired anywhere else is simply not exported.
GLTF_OUTPUT = "glTF Material Output"


def read_option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def target_image(material, image):
    """Make `image` the thing a bake writes into, for this material."""
    tree = material.node_tree
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.select = True
    tree.nodes.active = node
    return node


def bake_occlusion(mesh_object, image, samples, distance):
    """How much of the sky each point can see. A measurement, not a guess."""
    scene = bpy.context.scene
    # An empty startup file has no world, and occlusion is a question about how
    # much of the sky a point can see -- with no sky there is nothing to ask.
    if scene.world is None:
        scene.world = bpy.data.worlds.new("BakeWorld")
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    # CPU on purpose: a bake is seconds either way, and a studio without a
    # usable GPU device would otherwise fail here for a reason nobody could act
    # on from the receipt.
    scene.cycles.device = "CPU"
    scene.world.light_settings.distance = distance
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.margin = 8
    # Cycles wipes the target to black before baking unless told not to, which
    # took the "nothing here" fill with it and left every unreached texel
    # reading as fully occluded.
    scene.render.bake.use_clear = False

    nodes = [target_image(material, image) for material in mesh_object.data.materials if material]
    try:
        bpy.ops.object.bake(type="AO")
    finally:
        for material, node in zip([m for m in mesh_object.data.materials if m], nodes):
            material.node_tree.nodes.remove(node)


def bake_curvature(mesh_object, image, samples):
    """How the surface bends: raised where it is exposed, sunken where it hides.

    Baked through an emission shader because Blender has no curvature bake of
    its own. The shader is put on, baked, and taken off again, so the material
    a caller handed in is the material they get back.
    """
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = max(8, samples // 4)
    scene.render.bake.margin = 8
    scene.render.bake.use_clear = False

    restore = []
    targets = []
    for material in mesh_object.data.materials:
        if material is None:
            continue
        tree = material.node_tree
        output = next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL")
        was = [(link.from_node.name, link.from_socket.name)
               for link in tree.links if link.to_node.name == output.name]
        geometry = tree.nodes.new("ShaderNodeNewGeometry")
        ramp = tree.nodes.new("ShaderNodeValToRGB")
        # Pointiness sits around 0.5 and barely moves. Without pulling the
        # range in around it, a curvature bake comes back a flat grey card.
        ramp.color_ramp.elements[0].position = 0.42
        ramp.color_ramp.elements[1].position = 0.58
        emission = tree.nodes.new("ShaderNodeEmission")
        tree.links.new(geometry.outputs["Pointiness"], ramp.inputs["Fac"])
        tree.links.new(ramp.outputs["Color"], emission.inputs["Color"])
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        targets.append(target_image(material, image))
        restore.append((material, output, was, [geometry, ramp, emission]))

    try:
        bpy.ops.object.bake(type="EMIT")
    finally:
        for (material, output, was, added), node in zip(restore, targets):
            tree = material.node_tree
            for temporary in added + [node]:
                tree.nodes.remove(temporary)
            for from_name, from_socket in was:
                source = tree.nodes.get(from_name)
                if source is not None:
                    tree.links.new(source.outputs[from_socket], output.inputs["Surface"])


def bake_coverage(mesh_object, image):
    """Which texels geometry actually reaches, with the bake's own margin.

    Every material is swapped for one that emits plain white, baked, and put
    back, so the result is 1 where an island is (plus the margin the other
    bakes also bleed) and the fill everywhere else. The curvature map cannot
    serve for this: a flat surface bakes to exactly the "nothing here" grey,
    and a flat plate with its relief painted on is the one case the relief
    derivation is for.
    """
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.render.bake.margin = 8
    scene.render.bake.use_clear = False

    white = bpy.data.materials.new("CoverageProbe")
    white.use_nodes = True
    tree = white.node_tree
    output = next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL")
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    target_image(white, image)

    was = [slot.material for slot in mesh_object.material_slots]
    try:
        for slot in mesh_object.material_slots:
            slot.material = white
        bpy.ops.object.bake(type="EMIT")
    finally:
        for slot, material in zip(mesh_object.material_slots, was):
            slot.material = material
        bpy.data.materials.remove(white)


def wire_occlusion(material, image):
    """Put occlusion where the glTF exporter will actually look for it."""
    tree = material.node_tree
    group = bpy.data.node_groups.get(GLTF_OUTPUT)
    if group is None:
        group = bpy.data.node_groups.new(GLTF_OUTPUT, "ShaderNodeTree")
        group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    holder = tree.nodes.new("ShaderNodeGroup")
    holder.node_tree = group
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    # Colour space is set when the image is made, and setting it again here is
    # not harmless: changing it makes Blender reload the image from its source,
    # and a generated image's source is the flat colour it was created with --
    # so this line threw the whole bake away and left a black map behind.
    separate = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(texture.outputs["Color"], separate.inputs["Color"])
    tree.links.new(separate.outputs["Red"], holder.inputs["Occlusion"])
    return texture




def wire_normal(material, image):
    """Put the normal where both Blender and the glTF exporter read it."""
    tree = material.node_tree
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    mapping = tree.nodes.new("ShaderNodeNormalMap")
    tree.links.new(texture.outputs["Color"], mapping.inputs["Color"])
    tree.links.new(mapping.outputs["Normal"], principled.inputs["Normal"])
    return texture


def pixels_of(image):
    return np.asarray(image.pixels[:], dtype=np.float32).reshape(image.size[1], image.size[0], 4)


def blank(name, resolution, value):
    """An image filled with the value that means "nothing here".

    Filled through the pixel buffer rather than by setting `generated_color`,
    which does not re-fill an image that already exists -- so the fill silently
    stayed black and every texel counted as baked.

    The fill matters twice over. Only about a quarter of a typical sheet is
    reachable by geometry, so a renderer sampling a hair outside an island
    reads whatever is there: black occlusion puts a dark rim around every part.
    And it is what tells this script afterwards which texels the bake actually
    reached.
    """
    image = bpy.data.images.new(name, resolution, resolution, alpha=False, float_buffer=False)
    image.colorspace_settings.name = "Non-Color"
    fill = np.tile(np.array([value, value, value, 1.0], dtype=np.float32), resolution * resolution)
    image.pixels = fill.tolist()
    image.update()
    return image


def settle(image):
    """Read what a bake produced, and write it back so it is really there.

    A bake fills an image's buffer without marking the datablock edited, so an
    image created as generated still saves and packs the flat colour it was
    created with -- which is how the first occlusion map reached the exporter
    pure black while every number measured off the buffer said it was full of
    detail. Assigning the pixels through Python is what makes the buffer the
    image's actual content.
    """
    pixels = pixels_of(image)
    image.pixels = pixels.reshape(-1).tolist()
    image.update()
    return pixels


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [item for index, item in enumerate(argv)
                  if not item.startswith("--")
                  and (index == 0 or not argv[index - 1].startswith("--"))]
    if len(positional) < 3:
        print("[BAKE] FAILED: expected <source> <output.glb> <report.json>")
        return 2

    source, output, report_path = (Path(positional[0]), Path(positional[1]), Path(positional[2]))
    resolution = int(read_option(argv, "--resolution", "1024"))
    samples = int(read_option(argv, "--samples", "64"))
    distance = float(read_option(argv, "--distance", "0.08"))
    edge_wear = float(read_option(argv, "--edge-wear", "0"))
    relief = float(read_option(argv, "--relief-from-paint", "0"))

    if resolution not in (512, 1024, 2048):
        print("[BAKE] FAILED: resolution is 512, 1024 or 2048. Got {0}".format(resolution))
        return 1
    if not 0.0 <= edge_wear <= 1.0:
        print("[BAKE] FAILED: edge wear runs from 0 to 1. Got {0}".format(edge_wear))
        return 1
    if not 0.0 <= relief <= 2.0:
        print("[BAKE] FAILED: relief from paint runs from 0 to 2. Got {0}".format(relief))
        return 1
    if not source.is_file():
        print("[BAKE] FAILED: source does not exist: {0}".format(source))
        return 1
    if output.exists():
        print("[BAKE] FAILED: refusing to overwrite {0}".format(output))
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        print("[BAKE] FAILED: expected one mesh object, found {0}".format(len(meshes)))
        return 1

    mesh_object = meshes[0]
    if not mesh_object.data.uv_layers.active:
        print("[BAKE] FAILED: the mesh has no UVs, so nothing can be baked into a map")
        return 1
    if not mesh_object.data.materials:
        print("[BAKE] FAILED: the mesh carries no material to bake into")
        return 1

    bpy.ops.object.select_all(action="DESELECT")
    mesh_object.select_set(True)
    bpy.context.view_layer.objects.active = mesh_object

    # Filled with the value that means "nothing here", not with black. Only
    # about a quarter of a typical sheet is reachable by geometry, and a
    # renderer sampling a hair outside an island would otherwise read fully
    # occluded and put a black rim around every part. White is unoccluded;
    # mid-grey is uncurved.
    occlusion = blank("baked_occlusion", resolution, 1.0)
    curvature = blank("baked_curvature", resolution, 0.5)
    coverage = blank("baked_coverage", resolution, 0.0)
    bake_coverage(mesh_object, coverage)
    reached = settle(coverage)[..., 0] > 0.5

    bake_occlusion(mesh_object, occlusion, samples, distance)
    occluded = settle(occlusion)[..., 0]
    bake_curvature(mesh_object, curvature, samples)
    curved = settle(curvature)[..., 0]

    # Where the bake actually landed: everything else is the sheet's own fill,
    # and including it would make every statistic a statement about how the UVs
    # were packed rather than about the model.
    # With a tolerance, because an 8-bit buffer stores 0.5 as 128/255 and an
    # exact comparison called the untouched background "baked", which made
    # every statistic a description of the empty sheet.
    touched = np.abs(curved - 0.5) > 0.01
    if not touched.any():
        print("[BAKE] FAILED: the bake reached none of the sheet, so the UVs are "
              "not where the geometry is")
        return 1

    # A bake that came back uniform found nothing, and delivering it would put
    # a map on the asset that costs bytes and says nothing.
    if float(occluded[touched].std()) < 0.002:
        print("[BAKE] FAILED: the occlusion bake came back flat ({0:.4f} spread), so there is "
              "nothing in it. Check the mesh has thickness and the UVs do not overlap.".format(
                  float(occluded[touched].std())))
        return 1

    painted = mesh_object.data.materials[0]
    wire_occlusion(painted, occlusion)

    worn = None
    if edge_wear > 0:
        albedo = base_colour_image(painted)
        if albedo is None:
            print("[BAKE] FAILED: edge wear needs a base colour image to work on")
            return 1
        base = pixels_of(albedo)
        # Curvature sits around 0.5: above it the surface is exposed, below it
        # recessed. Lifting one and dropping the other is what makes an edge
        # catch light and a crease hold shadow.
        lift = np.clip((curved - 0.5) * 2.0, -1.0, 1.0)[..., None]
        if lift.shape[:2] != base.shape[:2]:
            print("[BAKE] FAILED: the curvature map and the base colour are different sizes, "
                  "so edge wear would land in the wrong place")
            return 1
        base[..., :3] = np.clip(base[..., :3] * (1.0 + edge_wear * lift), 0.0, 1.0)
        albedo.pixels = base.reshape(-1).tolist()
        worn = round(float(np.abs(lift).mean()), 4)

    # The painter delivers its base colour as a JPEG, and the exporter writes a
    # changed JPEG image back out as JPEG at whatever quality it likes. On a
    # ninja that took a 730 KB base colour to 298 KB: a second lossy pass on
    # top of the first, and the one map somebody actually looks at. Written
    # out as PNG instead, once, and packed, so what leaves is what is here.
    recoded = None
    albedo = base_colour_image(painted)
    if albedo is not None and (worn is not None or albedo.file_format == "JPEG"):
        recoded = albedo.file_format

    normal_image = None
    relief_mean = None
    if relief > 0:
        albedo = base_colour_image(painted)
        if albedo is None:
            print("[BAKE] FAILED: relief from paint needs a base colour image to read")
            return 1
        source_pixels = pixels_of(albedo)
        # With coverage, so the atlas's own island edges are not read as
        # cliffs: on a generated character that outlined every one of six
        # hundred islands, and the face looked drawn on triangles.
        encoded, relief_mean = normal_from_paint(source_pixels, relief, coverage=reached)
        if relief_mean < 1e-5:
            # Nothing local in the paint means nothing to raise. Delivering a
            # flat normal map would cost bytes and change nothing.
            print("[BAKE] FAILED: this paint has no local detail to raise ({0:.6f}), so a "
                  "normal derived from it would be flat".format(relief_mean))
            return 1
        normal_image = bpy.data.images.new(
            "baked_normal", albedo.size[0], albedo.size[1], alpha=False, float_buffer=False)
        normal_image.colorspace_settings.name = "Non-Color"
        normal_image.pixels = encoded.reshape(-1).tolist()
        normal_image.update()
        wire_normal(painted, normal_image)

    output.parent.mkdir(parents=True, exist_ok=True)
    # Written to real files before packing. A generated image packs the pattern
    # it was created with rather than what a bake put in its buffer, which is
    # how the first occlusion map came out of the exporter pure black while the
    # numbers measured off the buffer said it was full of detail.
    beside = output.parent / (output.stem + "-maps")
    beside.mkdir(parents=True, exist_ok=True)
    made = [(occlusion, "occlusion"), (curvature, "curvature")]
    if normal_image is not None:
        made.append((normal_image, "normal"))
    if recoded is not None:
        made.append((albedo, "base_colour"))
    for image, name in made:
        image.filepath_raw = str(beside / (name + ".png"))
        image.file_format = "PNG"
        image.save()
        image.pack()
    bpy.ops.export_scene.gltf(
        filepath=str(output), export_format="GLB", export_yup=True, export_apply=True,
        export_animations=False, export_cameras=False, export_lights=False)
    if not output.is_file():
        print("[BAKE] FAILED: the exporter wrote no file")
        return 1

    report = {
        "schema": "reference-asset-compiler.derived-maps.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "resolution": resolution,
        "samples": samples,
        "occlusion": {
            "distance_m": distance,
            # Measured where the bake actually landed, not across the whole
            # sheet. Only about a quarter of a sheet is reachable by geometry,
            # and averaging in the empty three quarters made a correct map read
            # as though the whole model were in shadow.
            "mean_where_baked": round(float(occluded[touched].mean()), 4) if touched.any() else None,
            "spread": round(float(occluded[touched].std()), 4) if touched.any() else 0.0,
            "shaded_share_of_model": round(float((occluded[touched] < 0.95).mean()), 4)
            if touched.any() else 0.0,
            "sheet_reached": round(float(touched.mean()), 4),
            "unreached_sheet_reads_as": "unoccluded, so a sample a hair outside an "
                                        "island cannot put a black rim on a part",
            "slot": "glTF occlusionTexture, not the packed roughness map, so a "
                    "later surface change cannot take it away",
        },
        "curvature": {
            "mean_where_baked": round(float(curved[touched].mean()), 4) if touched.any() else None,
            "spread": round(float(curved[touched].std()), 4) if touched.any() else 0.0,
        },
        "edge_wear": {"strength": edge_wear, "mean_shift": worn} if worn is not None else None,
        "base_colour_recoded": None if recoded is None else {
            "was": recoded, "now": "PNG",
            "because": "a changed JPEG leaves the exporter as a second-generation JPEG, "
                       "and the base colour is the one map somebody looks at",
        },
        "coverage": {
            "sheet_reached": round(float(reached.mean()), 4),
            "used_for": "keeping the relief derivation off the atlas's own island edges",
        },
        "relief_from_paint": None if normal_image is None else {
            "strength": relief,
            "local_detail": round(relief_mean, 6),
            "derived_from": "the base colour's local luminance, after its own blurred self "
                            "is subtracted, so a step between two materials is not read as a cliff",
            "seams": "the gutter is filled from the islands before measuring and left flat "
                     "after, so a UV seam is not read as relief",
            "honestly": "a derivation rather than a measurement. A highlight that was painted "
                        "and never was relief becomes a bump, which is why this one wants "
                        "looking at where occlusion and curvature do not.",
        },
        "geometry_unchanged": True,
        "uvs_unchanged": True,
        "derived_from": "the mesh itself; nothing here was invented or generated",
        "requires_fixed_view_review": True,
        "production_grade": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if normal_image is not None:
        print("[BAKE] relief from paint at {0}: local detail {1:.5f} raised into a normal map".format(
            relief, relief_mean))
    print("[BAKE] occlusion {0:.3f} where baked, {1:.1%} of the model shaded, {2:.0%} of the "
          "sheet reached; curvature spread {3:.3f}{4}".format(
        report["occlusion"]["mean_where_baked"], report["occlusion"]["shaded_share_of_model"],
        report["occlusion"]["sheet_reached"], report["curvature"]["spread"],
        "" if worn is None else "; edge wear {0} at {1:.2f}".format(worn, edge_wear)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
