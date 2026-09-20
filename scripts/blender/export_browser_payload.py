"""Export the staged asset as a self-contained GLB a browser studio can load.

The FBX export beside this one is for Unreal and applies UE's axis convention.
A browser wants the opposite: glTF's own +Y up, metres, one file with its
textures inside it. Blender's glTF exporter converts the Z-up staged scene on
the way out, so the payload arrives in browser convention without anything
downstream converting it -- which is exactly what the browser studio contract
requires, because an import that converts is an import that can convert wrongly.

Nothing is judged here and the source is not modified. The stage exports, counts
what it exported, and stops; the skeleton fingerprint is taken from the written
file afterwards by the compiler, never from this scene's memory.

Usage:
  blender -b --factory-startup --python scripts/blender/export_browser_payload.py \
      -- <source.fbx|blend|glb> <payload.glb> <report.json>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

import bpy


def import_any(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path))
    elif suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise SystemExit("unsupported source format: " + suffix)


def principled(material):
    """The material's Principled BSDF, made if the import left none."""
    material.use_nodes = True
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    node = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    output = next((n for n in material.node_tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if output is None:
        output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(node.outputs["BSDF"], output.inputs["Surface"])
    return node


def rebuild_surface(material) -> None:
    """Take a material back to a bare surface before binding a manifest to it.

    A working file's material is a preview. The neck-transfer one blends the
    paint against a vertex colour through a computed mask and feeds that image
    into metallic-roughness and normal as well; left there, the blue channel of
    blue armour becomes metalness, and metal with nothing to reflect renders
    black. Unlinking those inputs is not enough. The orphaned network stays in
    the tree, and the glTF exporter still finds an image in it and writes a
    normal texture nobody asked for -- in the case that prompted this, a second
    copy of a ten megabyte base colour map, at strength zero, so it cost the
    payload a third of its size and changed nothing on screen.

    So the nodes go, not just the links. The manifest is the authority for this
    material; anything the preview had to say about it is already superseded.
    """
    tree = material.node_tree
    output = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
    for node in list(tree.nodes):
        if node is not output:
            tree.nodes.remove(node)
    principled(material)


def bind_base_colour(material, path: Path) -> None:
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(path), check_existing=True)
    node.image.colorspace_settings.name = "sRGB"
    material.node_tree.links.new(node.outputs["Color"], principled(material).inputs["Base Color"])


def bind_orm(material, path: Path) -> None:
    """Occlusion, roughness and metallic packed into one image's R, G and B.

    glTF stores exactly this arrangement, so wiring green to roughness and blue
    to metallic is what lets the exporter recognise the pack and write a single
    metallicRoughness texture instead of inventing two.
    """
    tree = material.node_tree
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(path), check_existing=True)
    node.image.colorspace_settings.name = "Non-Color"
    split = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(node.outputs["Color"], split.inputs["Color"])
    surface = principled(material)
    tree.links.new(split.outputs["Green"], surface.inputs["Roughness"])
    tree.links.new(split.outputs["Blue"], surface.inputs["Metallic"])


def relink_missing(source: Path, report: dict) -> None:
    """Textures that sit beside an FBX under their own names, not renamed."""
    folders = [source.parent, source.parent / "textures"]
    relinked, missing = [], []
    for image in bpy.data.images:
        if not image.filepath or image.packed_file:
            continue
        if Path(bpy.path.abspath(image.filepath)).is_file():
            continue
        name = PurePosixPath(image.filepath.replace("\\", "/")).name
        for folder in folders:
            candidate = folder / name
            if candidate.is_file():
                image.filepath = str(candidate)
                image.reload()
                relinked.append(name)
                break
        else:
            missing.append(name)
    report["textures_relinked"] = sorted(relinked)
    report["textures_missing"] = sorted(missing)


def lone_material(entries: dict, report: dict):
    """The one material a single-material file must mean.

    Some packages name their material after the package rather than after the
    mesh, so the manifest's key does not match what the FBX carries. Where the
    file has exactly one material and the manifest describes exactly one, there
    is nothing to confuse it with and refusing would only lose the textures. Any
    file with more than one material stays strict, because there a wrong guess
    paints the wrong surface. The substitution is recorded rather than assumed.
    """
    materials = list(bpy.data.materials)
    if len(materials) != 1 or len(entries) != 1:
        return None
    report["material_matched_by_position"] = materials[0].name
    return materials[0]


def bind_manifest_textures(source: Path, report: dict, named: Path | None = None) -> None:
    """Bind the textures a production export keeps beside it.

    A production package renames its textures and packs occlusion, roughness
    and metallic into one image, so the names in the FBX no longer match the
    files on disk and matching by name silently finds nothing. The import
    manifest written beside the FBX is the only record of which file belongs to
    which material and slot, so that is what is read. Without it, fall back to
    relinking by name, which is what a staged asset needs.

    A caller may name a manifest instead. An assembled working file carries a
    preview material rather than the production binding, and the manifest that
    describes its paint belongs to the package it was exported as, not to the
    blend. Naming it is how an assembly gets the surface its source already
    passed review with, without editing the authority to say so.
    """
    manifest_path = Path(named) if named else source.with_suffix(".ue5import.json")
    if not manifest_path.is_file():
        if named:
            report["texture_manifest_error"] = "no such manifest: {0}".format(manifest_path)
        relink_missing(source, report)
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as problem:
        report["texture_manifest_error"] = str(problem)
        relink_missing(source, report)
        return

    bound, missing, rebuilt = [], [], set()
    entries = manifest.get("textures") or {}
    for material_name, slots in entries.items():
        material = bpy.data.materials.get(material_name)
        if material is None:
            material = lone_material(entries, report)
        if material is None:
            missing.append("{0} (no such material in the file)".format(material_name))
            continue
        for slot, entry in (slots or {}).items():
            relative = (entry or {}).get("file")
            if not relative:
                continue
            path = (manifest_path.parent / relative).resolve()
            if not path.is_file():
                missing.append("{0}.{1} -> {2}".format(material_name, slot, relative))
                continue
            if material.name not in rebuilt:
                rebuild_surface(material)
                rebuilt.add(material.name)
            if slot.lower() == "basecolor":
                bind_base_colour(material, path)
            elif slot.lower() == "orm":
                bind_orm(material, path)
            else:
                continue
            bound.append("{0}.{1}".format(material_name, slot))

    report["texture_manifest"] = str(manifest_path) if named else manifest_path.name
    report["textures_bound"] = sorted(bound)
    report["textures_missing"] = sorted(missing)


def drop_dead_images(report: dict) -> None:
    """Forget images the importer recorded that were never on this disk.

    An FBX names the textures its author had; a production package renames them
    on the way out. The importer therefore leaves datablocks pointing at files
    that do not exist. The manifest has already bound the real ones over the
    top, so these are dead weight: kept, they make packing report failures for
    files nobody wants and can leave a broken external reference in the payload.
    """
    dropped = []
    for image in list(bpy.data.images):
        if image.packed_file or not image.filepath:
            continue
        if Path(bpy.path.abspath(image.filepath)).is_file():
            continue
        dropped.append(PurePosixPath(image.filepath.replace("\\", "/")).name)
        bpy.data.images.remove(image)
    if dropped:
        report["textures_dropped"] = sorted(dropped)


def scene_counts() -> dict:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    vertices = 0
    triangles = 0
    materials = set()
    for obj in meshes:
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        vertices += len(mesh.vertices)
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        evaluated.to_mesh_clear()
        for slot in obj.material_slots:
            if slot.material:
                materials.add(slot.material.name)
    return {
        "mesh_objects": len(meshes),
        "armatures": len(armatures),
        "bones": sum(len(obj.data.bones) for obj in armatures),
        "vertices": vertices,
        "triangles": triangles,
        "materials": sorted(materials),
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    named_manifest = None
    if "--textures" in argv:
        at = argv.index("--textures")
        named_manifest = Path(argv[at + 1])
        argv = argv[:at] + argv[at + 2:]
    if len(argv) < 3:
        print("[PAYLOAD] FAILED: expected <source> <payload.glb> <report.json> [--textures <manifest>]")
        return 2

    source = Path(argv[0])
    payload = Path(argv[1])
    report_path = Path(argv[2])
    if not source.is_file():
        print("[PAYLOAD] FAILED: source does not exist: {0}".format(source))
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    import_any(source)

    before = scene_counts()
    if before["mesh_objects"] == 0:
        print("[PAYLOAD] FAILED: the source carries no mesh to export")
        return 1

    # An FBX keeps its textures beside it rather than inside it, so without this
    # the payload exports with correct geometry and no colour at all -- which
    # looks like a broken asset rather than a missing file.
    textures = {}
    bind_manifest_textures(source, textures, named_manifest)
    drop_dead_images(textures)
    if bpy.data.images:
        # Packing is what puts the pixels inside the GLB; a payload that points
        # at a file on this workstation is no use to a browser anywhere else.
        try:
            bpy.ops.file.pack_all()
        except RuntimeError as problem:
            textures["pack_error"] = str(problem)

    payload.parent.mkdir(parents=True, exist_ok=True)
    # A self-contained GLB: one file, textures inside it, no external URIs, and
    # the exporter's own Z-up to Y-up conversion rather than a hand-rolled one.
    bpy.ops.export_scene.gltf(
        filepath=str(payload),
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_texture_dir="",
        export_skins=before["armatures"] > 0,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
    )
    if not payload.is_file():
        print("[PAYLOAD] FAILED: the exporter wrote no file")
        return 1

    report = {
        "schema": "reference-asset-compiler.browser-payload.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "payload": str(payload),
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "payload_bytes": payload.stat().st_size,
        "convention": {"up": "+Y", "units": "metres", "self_contained": True},
        "exported": before,
        "textures": textures,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[PAYLOAD] wrote {0} ({1} bytes, {2} triangles)".format(
        payload.name, report["payload_bytes"], before["triangles"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
