"""Import a compiled asset package into UE5 from its ue5import.json manifest.

Run inside the Unreal Editor's Python environment:

    py "<repo>/scripts/ue5/import_asset.py" "<repo>/out/ninja-man/ninja-man.ue5import.json"

or from the editor's Python console:

    import import_asset; import_asset.main(["<manifest path>"])

The manifest carries the settings that are easy to get wrong by hand -- sRGB
off for Normal and ORM, TC_Normalmap, TC_Masks, Import Uniform Scale 1.0 -- so
that they are applied identically on every machine and every re-import.

Textures are grouped by material in the manifest, because a character can have
more than one: field-scout-female carries a body atlas and a separate face
projection. Each group becomes its own UE material, bound to the mesh section
whose slot name matches.
"""

from __future__ import annotations

import json
import os
import sys

import unreal

COMPRESSION = {
    "TC_Default": unreal.TextureCompressionSettings.TC_DEFAULT,
    "TC_Normalmap": unreal.TextureCompressionSettings.TC_NORMALMAP,
    "TC_Masks": unreal.TextureCompressionSettings.TC_MASKS,
}


def build_texture_task(abs_path, destination):
    task = unreal.AssetImportTask()
    task.filename = abs_path
    task.destination_path = destination
    task.automated = True
    task.replace_existing = True
    task.save = True
    return task


def build_skeletal_task(abs_path, destination, manifest):
    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_as_skeletal = True
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False
    options.create_physics_asset = True

    mesh_data = options.skeletal_mesh_import_data
    settings = manifest["ue5_import"]
    mesh_data.import_uniform_scale = float(settings.get("import_uniform_scale", 1.0))
    mesh_data.convert_scene = bool(settings.get("convert_scene", True))
    mesh_data.force_front_x_axis = bool(settings.get("force_front_x_axis", False))
    # UE 5.8's FbxSkeletalMeshImportData exposes neither use_t0_as_ref_pose nor
    # preserve_smoothing_groups; setting them raises AttributeError.
    mesh_data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    mesh_data.compute_weighted_normals = True
    mesh_data.import_mesh_lods = False

    task = unreal.AssetImportTask()
    task.filename = abs_path
    task.destination_path = destination
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    return task


def build_static_task(abs_path, destination, manifest):
    """A prop imports as a StaticMesh, and that is not a detail.

    Imported as skeletal it acquires a single-bone skeleton, a physics asset
    built for a body that does not exist, and a skeletal mesh component --
    which costs a skinning pass every frame for geometry that never moves, and
    stops it being placeable as ordinary level geometry.
    """
    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_as_skeletal = False
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False

    mesh_data = options.static_mesh_import_data
    settings = manifest.get("ue5_import") or {}
    mesh_data.import_uniform_scale = float(settings.get("import_uniform_scale", 1.0))
    mesh_data.convert_scene = bool(settings.get("convert_scene", True))
    mesh_data.force_front_x_axis = bool(settings.get("force_front_x_axis", False))
    mesh_data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    mesh_data.compute_weighted_normals = True
    # Without this the prop has no collision at all and a player walks through
    # it, which reads as the asset not being there rather than as a missing
    # setting.
    mesh_data.auto_generate_collision = bool(settings.get("generate_collision", True))
    mesh_data.combine_meshes = True

    task = unreal.AssetImportTask()
    task.filename = abs_path
    task.destination_path = destination
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    return task


def find_static_mesh(root):
    for path in unreal.EditorAssetLibrary.list_assets(root, recursive=False):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, unreal.StaticMesh):
            return path.split(".")[0]
    return None


def assign_static_materials(mesh_path, by_manifest_name, fallback):
    """Bind each created material to the slot whose name matches.

    Same rule as the skeletal path, and for the same reason: the FBX carries
    the Blender material names as slot names and the manifest is keyed by
    those names, so the match is exact rather than positional. The authority
    chair has six slots; assigning the first material to all of them would
    paint the whole thing in black frame vinyl and still report success.

    Read back afterwards, because set_material is silent when the index is out
    of range and a prop with an unassigned slot renders as the default
    checkerboard while every log line says the import worked.
    """
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        return False
    slots = mesh.get_editor_property("static_materials")
    if not slots:
        unreal.log_error("{0} imported with no material slots".format(mesh_path))
        return False
    assigned = []
    for index, entry in enumerate(slots):
        slot_name = str(entry.get_editor_property("material_slot_name"))
        chosen = by_manifest_name.get(slot_name, fallback)
        if chosen is not None:
            mesh.set_material(index, chosen)
        assigned.append((slot_name, chosen.get_name() if chosen else None))
    unreal.EditorAssetLibrary.save_asset(mesh_path)
    applied = unreal.EditorAssetLibrary.load_asset(mesh_path).get_editor_property(
        "static_materials")
    ok = all(e.get_editor_property("material_interface") is not None
             for e in applied)
    for slot_name, material_name in assigned:
        unreal.log("  slot {0} -> {1}".format(slot_name, material_name))
    unreal.log("RAC static materials on {0}: {1} slot(s), all assigned={2}".format(
        mesh_path, len(applied), ok))
    return ok


def build_static_lods(mesh_path, lods):
    """Screen-size driven reduction, same shape as the skeletal path."""
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None or not lods:
        return
    try:
        subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    except Exception:  # noqa: BLE001 - older builds
        return
    options = unreal.EditorScriptingMeshReductionOptions()
    settings = []
    for entry in lods:
        item = unreal.EditorScriptingMeshReductionSettings()
        item.percent_triangles = float(entry.get("percent_triangles", 1.0))
        item.screen_size = float(entry.get("screen_size", 1.0))
        settings.append(item)
    options.reduction_settings = settings
    options.auto_compute_lod_screen_size = False
    try:
        subsystem.set_lods(mesh, options)
        unreal.EditorAssetLibrary.save_asset(mesh_path)
        unreal.log("RAC built {0} LODs on {1}".format(len(settings), mesh_path))
    except Exception as error:  # noqa: BLE001
        unreal.log_warning("static LOD build skipped: {0}".format(error))


def apply_texture_settings(root, texture_name, settings):
    """sRGB and compression are per-texture and silently wrong by default."""
    asset_path = "{0}/Textures/{1}".format(root, texture_name)
    texture = unreal.EditorAssetLibrary.load_asset(asset_path)
    if texture is None:
        unreal.log_warning("could not load imported texture {0}".format(asset_path))
        return None
    texture.set_editor_property("srgb", bool(settings.get("sRGB", False)))
    compression = COMPRESSION.get(settings.get("compression"))
    if compression is not None:
        texture.set_editor_property("compression_settings", compression)
    if settings.get("flip_green"):
        texture.set_editor_property("flip_green_channel", True)
    unreal.EditorAssetLibrary.save_asset(asset_path)
    return texture


MASTER_PATH = "/Game/Compiled/Materials"
MASTER_NAME = "M_RAC_CharacterMaster"
TEXTURE_PARAMETERS = ("BaseColor", "ORM", "Normal")


def ensure_master_material(masks_default=None):
    """One parameterised master material for the whole cohort.

    Every character used to get its own standalone Material. That works and it
    does not scale: changing how roughness is read, or adding a detail normal,
    means editing each one, and each is a separate shader to compile. A master
    plus instances is the shape production wants -- one graph, one shader, and
    per-character overrides that are just texture references.

    ORM is packed R=AO, G=Roughness, B=Metallic. Feeding the whole texture into
    one input, or forgetting to split it, is the usual reason a character
    imports looking chalky or unexpectedly metallic.

    Every default here has to be a sane standalone value, because a character
    that ships without one of these maps -- ninja-man has no normal map -- gets
    the default instead of nothing.
    """
    path = "{0}/{1}".format(MASTER_PATH, MASTER_NAME)
    existing = unreal.EditorAssetLibrary.load_asset(path)
    if existing is not None:
        # Repair a master built before the usage flags were set, rather than
        # trusting that an asset which exists is an asset that is correct.
        # This one shipped a cooked build with every character grey.
        missing = [flag for flag in ("used_with_skeletal_mesh",
                                     "used_with_morph_targets",
                                     "used_with_static_lighting")
                   if not existing.get_editor_property(flag)]
        if missing:
            for flag in missing:
                existing.set_editor_property(flag, True)
            unreal.MaterialEditingLibrary.recompile_material(existing)
            unreal.EditorAssetLibrary.save_asset(path)
            unreal.log("RAC repaired {0}: set {1}".format(path, missing))
        return existing

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    master = tools.create_asset(
        MASTER_NAME, MASTER_PATH, unreal.Material, unreal.MaterialFactoryNew())
    if master is None:
        unreal.log_error("could not create {0}".format(path))
        return None

    lib = unreal.MaterialEditingLibrary

    base = lib.create_material_expression(
        master, unreal.MaterialExpressionTextureSampleParameter2D, -700, -200)
    base.set_editor_property("parameter_name", "BaseColor")
    base.set_editor_property("texture", unreal.EditorAssetLibrary.load_asset(
        "/Engine/EngineMaterials/DefaultDiffuse"))
    lib.connect_material_property(base, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)

    # Normal needs no guard: the default IS the correct fallback, because a
    # flat normal map and no normal map are the same surface.
    normal = lib.create_material_expression(
        master, unreal.MaterialExpressionTextureSampleParameter2D, -700, 500)
    normal.set_editor_property("parameter_name", "Normal")
    normal.set_editor_property("texture", unreal.EditorAssetLibrary.load_asset(
        "/Engine/EngineMaterials/DefaultNormal"))
    normal.set_editor_property(
        "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    lib.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)

    # ORM does need one. There is no stock texture that reads as "no occlusion,
    # cloth roughness, not metal", so a material without an ORM map would take
    # whatever the placeholder happens to contain -- a mid-grey default reads
    # as half metal. Blend against explicit constants instead, and let each
    # instance say whether it actually has the map.
    # The default texture on a Masks sampler has to BE a masks texture.
    #
    # This is what broke the first master material, and it broke it in the
    # worst way: an sRGB default on a SAMPLERTYPE_MASKS parameter is a
    # compile error, the whole material silently falls back to the engine
    # default, and every character renders pure white. Nothing said so --
    # the cook reported "0 errors, 2 warnings" and the warnings were this.
    #
    # No engine texture is imported as TC_Masks, so the default comes from
    # the cohort's own ORM maps. It is never seen: every instance overrides
    # it, and HasORM blends it out for any that do not.
    orm = lib.create_material_expression(
        master, unreal.MaterialExpressionTextureSampleParameter2D, -700, 120)
    orm.set_editor_property("parameter_name", "ORM")
    orm.set_editor_property("texture", masks_default or
                            unreal.EditorAssetLibrary.load_asset(
                                "/Engine/EngineMaterials/DefaultDiffuse"))
    orm.set_editor_property(
        "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)

    has_orm = lib.create_material_expression(
        master, unreal.MaterialExpressionScalarParameter, -700, 340)
    has_orm.set_editor_property("parameter_name", "HasORM")
    has_orm.set_editor_property("default_value", 0.0)

    channels = (
        ("R", 1.0, unreal.MaterialProperty.MP_AMBIENT_OCCLUSION, 60),
        ("G", 0.7, unreal.MaterialProperty.MP_ROUGHNESS, 160),
        ("B", 0.0, unreal.MaterialProperty.MP_METALLIC, 260),
    )
    for channel, fallback, prop, y in channels:
        constant = lib.create_material_expression(
            master, unreal.MaterialExpressionConstant, -400, y)
        constant.set_editor_property("r", fallback)
        blend = lib.create_material_expression(
            master, unreal.MaterialExpressionLinearInterpolate, -200, y)
        lib.connect_material_expressions(constant, "", blend, "A")
        lib.connect_material_expressions(orm, channel, blend, "B")
        lib.connect_material_expressions(has_orm, "", blend, "Alpha")
        lib.connect_material_property(blend, "", prop)

    # Declare every mesh type this material will be drawn on, BEFORE the
    # compile.
    #
    # A material compiles one shader permutation per vertex factory it says it
    # is used with, and by default that list does not include skeletal meshes.
    # In the editor this is invisible: `automatically_set_usage_in_editor` is
    # on, so the first time a skeletal mesh tries to draw with it the flag gets
    # set and the shader is compiled on the spot. A cooked build has no shader
    # compiler. The permutation was never cooked, the material falls back to
    # the engine default, and every character renders flat grey with correct
    # geometry and correct normals -- which is exactly what shipped, while the
    # packaged run reported "map loads, 0 errors, 0 warnings", because it is
    # not an error. The office chair looked right in the same build only
    # because it is a StaticMesh, whose usage is on by default.
    #
    # Morph targets are included because field-scout-male carries four
    # corrective elbow blendshapes; a permutation costs a little cook time and
    # not having it costs the character.
    for flag in ("used_with_skeletal_mesh", "used_with_morph_targets",
                 "used_with_static_lighting"):
        try:
            master.set_editor_property(flag, True)
        except Exception as error:  # noqa: BLE001 - reported below
            unreal.log_warning("could not set {0}: {1}".format(flag, error))

    lib.recompile_material(master)
    unreal.EditorAssetLibrary.save_asset(path)

    # Read the flags back. Setting a property that did not take is silent, and
    # the symptom does not appear until something is cooked and run.
    unset = [flag for flag in ("used_with_skeletal_mesh", "used_with_morph_targets")
             if not master.get_editor_property(flag)]
    if unset:
        unreal.log_error(
            "{0} still reports {1} False; a cooked build will draw every "
            "skeletal mesh with the default material".format(path, unset))
        return None

    # Prove the parameters exist before anything relies on them. Naming a
    # parameter and having the material actually expose one are different
    # things, and the gap between them is four white characters.
    try:
        exposed = [str(n) for n in lib.get_texture_parameter_names(master)]
    except Exception:  # noqa: BLE001 - older builds lack the accessor
        exposed = None
    if exposed is not None:
        missing = [n for n in TEXTURE_PARAMETERS if n not in exposed]
        if missing:
            unreal.log_error(
                "master material exposes {0}; missing {1}".format(exposed, missing))
            return None
    # Prove it compiled. A material that fails to compile is not an error
    # anywhere the import can see -- it just quietly becomes the default
    # material at runtime, which is a white character.
    try:
        stats = lib.get_statistics(master)
        instructions = int(stats.num_pixel_shader_instructions)
    except Exception:  # noqa: BLE001 - no accessor on this build
        instructions = None
    if instructions is not None and instructions <= 0:
        unreal.log_error(
            "master material {0} compiled to {1} pixel shader instructions; "
            "it will fall back to the engine default at runtime".format(
                path, instructions))
        return None
    unreal.log("built master material {0} exposing {1}, {2} instructions".format(
        path, exposed, instructions))
    return master


def build_material(root, material_name, textures_by_slot):
    """Create a material instance of the shared master for one manifest material.

    The instance is read back after it is written. Setting a texture parameter
    that the master does not expose is silent -- it is simply ignored -- and
    the result is a character that names the right material and renders pure
    white, which is exactly what shipped the first time this was tried.
    """
    master = ensure_master_material(textures_by_slot.get("ORM"))
    if master is None:
        return None

    package_path = "{0}/{1}".format(root, material_name)
    if unreal.EditorAssetLibrary.does_asset_exist(package_path):
        unreal.EditorAssetLibrary.delete_asset(package_path)

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    instance = tools.create_asset(
        material_name, root, unreal.MaterialInstanceConstant,
        unreal.MaterialInstanceConstantFactoryNew())
    if instance is None:
        unreal.log_error("could not create material instance {0}".format(package_path))
        return None

    lib = unreal.MaterialEditingLibrary
    lib.set_material_instance_parent(instance, master)
    wanted = {}
    for slot in TEXTURE_PARAMETERS:
        if slot in textures_by_slot:
            lib.set_material_instance_texture_parameter_value(
                instance, slot, textures_by_slot[slot])
            wanted[slot] = textures_by_slot[slot]
    lib.set_material_instance_scalar_parameter_value(
        instance, "HasORM", 1.0 if "ORM" in textures_by_slot else 0.0)
    lib.update_material_instance(instance)

    wrong = []
    for slot, texture in wanted.items():
        try:
            got = lib.get_material_instance_texture_parameter_value(instance, slot)
        except Exception as error:  # noqa: BLE001
            wrong.append("{0}: {1}".format(slot, error))
            continue
        if got is None or got.get_name() != texture.get_name():
            wrong.append("{0}: wanted {1}, got {2}".format(
                slot, texture.get_name(), got.get_name() if got else None))
    if wrong:
        unreal.log_error("material instance {0} did not take its textures: {1}".format(
            package_path, "; ".join(wrong)))
        return None

    unreal.EditorAssetLibrary.save_asset(package_path)
    unreal.log("built material instance {0} carrying {1}".format(
        package_path, sorted(wanted)))
    return instance


def find_skeletal_mesh(root):
    for path in unreal.EditorAssetLibrary.list_assets(root, recursive=False):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, unreal.SkeletalMesh):
            return path
    return None


def assign_materials(mesh_path, by_manifest_name, fallback):
    """Bind each created material to the section whose slot name matches.

    The FBX carries the Blender material names as slot names, and the manifest
    is keyed by those same names, so the match is exact rather than positional.
    A section with no match takes the fallback, because a mesh imported with an
    unassigned slot renders as a featureless white blob -- which reads as a
    broken export when only the material was missing.
    """
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        return []

    # Iterating the materials array yields COPIES of the SkeletalMaterial
    # struct, so mutating them in place and writing the same list back is a
    # no-op -- the mesh keeps WorldGridMaterial and the character still renders
    # white. Build fresh structs and assign the new array.
    existing = mesh.get_editor_property("materials")
    rebuilt = []
    assigned = []
    for entry in existing:
        slot_name = str(entry.get_editor_property("material_slot_name"))
        chosen = by_manifest_name.get(slot_name, fallback)
        replacement = unreal.SkeletalMaterial()
        replacement.set_editor_property("material_slot_name", slot_name)
        replacement.set_editor_property(
            "material_interface",
            chosen if chosen is not None
            else entry.get_editor_property("material_interface"))
        rebuilt.append(replacement)
        assigned.append((slot_name, chosen.get_name() if chosen else None))
    mesh.set_editor_property("materials", rebuilt)
    unreal.EditorAssetLibrary.save_asset(mesh_path)
    for slot_name, material_name in assigned:
        unreal.log("  slot {0} -> {1}".format(slot_name, material_name))
    return assigned


def build_lods(mesh_path, lods):
    """Generate LODs with UE's own reducer.

    Deliberately not Blender's Decimate: that produces long skinny triangles,
    which are the direct cause of the faceted shading this pipeline exists to
    eliminate. UE's reduction is edge-collapse with skinning and boundary
    constraints, so silhouette and weights survive.
    """
    generated = [entry for entry in lods if entry.get("source") == "ue5_reduction"]
    if not generated:
        return
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh is None:
        return

    total = max(int(entry["lod"]) for entry in generated) + 1
    # EditorScriptingUtilities is deprecated in 5.8 in favour of
    # SkeletalMeshEditorSubsystem; prefer the subsystem, fall back for older.
    subsystem = None
    if hasattr(unreal, "SkeletalMeshEditorSubsystem"):
        subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    try:
        if subsystem is not None:
            subsystem.regenerate_lod(mesh, total)
        else:
            unreal.EditorSkeletalMeshLibrary.regenerate_lod(mesh, total)
    except Exception as error:  # noqa: BLE001 - editor API varies by version
        unreal.log_warning("LOD generation unavailable: {0}".format(error))
        return
    unreal.EditorAssetLibrary.save_asset(mesh_path)
    unreal.log("requested {0} LOD levels on {1}".format(total, mesh_path))


def main(argv):
    if not argv:
        unreal.log_error("usage: import_asset.py <manifest.json>")
        return 1

    manifest_path = os.path.abspath(argv[0])
    with open(manifest_path, "r", encoding="utf-8-sig") as handle:
        manifest = json.load(handle)

    package_dir = os.path.dirname(manifest_path)
    asset_id = manifest["asset_id"]
    folder = "".join(part.capitalize() for part in asset_id.replace("_", "-").split("-"))
    root = "/Game/Compiled/{0}".format(folder)

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    tasks = []

    fbx_path = os.path.join(package_dir, manifest["fbx"])
    if not os.path.exists(fbx_path):
        unreal.log_error("FBX missing: {0}".format(fbx_path))
        return 1
    static = manifest.get("ue5_mesh_type") == "StaticMesh"
    tasks.append(build_static_task(fbx_path, root, manifest) if static
                 else build_skeletal_task(fbx_path, root, manifest))

    # Textures are grouped by material: {material: {slot: {file, settings}}}.
    wanted = {}
    for material_name, slots in manifest.get("textures", {}).items():
        for slot, entry in slots.items():
            tex_path = os.path.join(package_dir, entry["file"].replace("/", os.sep))
            if not os.path.exists(tex_path):
                unreal.log_warning("texture missing, skipped: {0}".format(tex_path))
                continue
            tasks.append(build_texture_task(tex_path, root + "/Textures"))
            name = os.path.splitext(os.path.basename(tex_path))[0]
            wanted.setdefault(material_name, {})[slot] = (name, entry["settings"])

    tools.import_asset_tasks(tasks)

    materials_by_name = {}
    for material_name, slots in wanted.items():
        textures_by_slot = {}
        for slot, (name, settings) in slots.items():
            texture = apply_texture_settings(root, name, settings)
            if texture is not None:
                textures_by_slot[slot] = texture
        material = build_material(root, material_name, textures_by_slot)
        if material is not None:
            materials_by_name[material_name] = material

    if static:
        mesh_path = find_static_mesh(root)
        if mesh_path:
            build_static_lods(mesh_path, manifest.get("lods", []))
            fallback = (list(materials_by_name.values())[0]
                        if materials_by_name else None)
            assign_static_materials(mesh_path, materials_by_name, fallback)
        measurements = manifest["measurements"]
        unreal.log("RAC_UE5_IMPORT_OK {0} -> {1} (static prop, {2} tris, "
                   "{3} m tall)".format(asset_id, root,
                                        measurements.get("total_tris"),
                                        measurements.get("height_m")))
        return 0

    mesh_path = find_skeletal_mesh(root)
    if mesh_path:
        fallback = None
        for name, material in materials_by_name.items():
            if name.endswith("_Body"):
                fallback = material
                break
        if fallback is None and materials_by_name:
            fallback = list(materials_by_name.values())[0]
        build_lods(mesh_path, manifest.get("lods", []))
        # After LOD generation, not before: regenerating LODs rewrites the
        # section list and can drop a freshly assigned material.
        assign_materials(mesh_path, materials_by_name, fallback)

    measurements = manifest["measurements"]
    unreal.log(
        "RAC_UE5_IMPORT_OK {0} -> {1} (expect {2} bones, {3} cm tall)".format(
            asset_id, root,
            measurements.get("bone_count_expected_ue5"),
            measurements.get("height_cm_in_ue5")))
    unreal.log("retarget: {0}".format(manifest.get("retarget_note", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
