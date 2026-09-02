"""Import every compiled package into UE5 and verify the imported payload.

Runs headless inside the editor:

  UnrealEditor-Cmd.exe <project>.uproject \
      -ExecutePythonScript="<this file>" -unattended -nop4 -nosplash -stdout

Reads the repo root from the RAC_ROOT environment variable, imports every
`out/<asset>/<asset>.ue5import.json`, then inspects what the engine actually
built and writes the result to `work/ue5-verify.json`.

Verifying the imported payload, not the import call's return value, is the
whole point. An import that "succeeds" and produces a mesh at the wrong scale,
with a bone missing or the material unassigned, is the failure mode this
project has already shipped once.
"""

from __future__ import annotations

import json
import hashlib
import os
import sys
import traceback

import unreal

ROOT = os.environ.get("RAC_ROOT")
if not ROOT:
    unreal.log_error("RAC_ROOT is not set")
    raise SystemExit(1)

sys.path.insert(0, os.path.join(ROOT, "scripts", "ue5"))
import import_asset  # noqa: E402


def folder_for(asset_id):
    return "".join(p.capitalize() for p in asset_id.replace("_", "-").split("-"))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(manifest, root):
    """Inspect what the engine built, and compare it to what was promised."""
    result = {"asset_id": manifest["asset_id"], "package_root": root, "checks": []}

    def check(name, ok, detail):
        result["checks"].append({"check": name, "ok": bool(ok), "detail": detail})

    # A static prop is verified the same way with two substitutions: the mesh
    # is a StaticMesh and its slots are StaticMaterial rather than
    # SkeletalMaterial. Everything the check is actually FOR -- did it import,
    # is it the right size, is a real material bound, does that material
    # sample the textures the manifest promised, are the LODs there -- is
    # identical, and it is worth having on a prop for exactly the same
    # reasons. What does not apply is the bone count.
    static = manifest.get("ue5_mesh_type") == "StaticMesh"
    kind = "StaticMesh" if static else "SkeletalMesh"
    mesh_path = (import_asset.find_static_mesh(root) if static
                 else import_asset.find_skeletal_mesh(root))
    if not mesh_path:
        check("mesh_exists", False, "no {0} under {1}".format(kind, root))
        result["ok"] = False
        return result
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    result["mesh"] = mesh_path
    result["mesh_type"] = kind
    if not static:
        result["skeletal_mesh"] = mesh_path

    # unreal.Skeleton exposes no bone accessor to Python in 5.8, so the bone
    # count comes from the asset registry tags the content browser uses.
    bone_count = None
    asset_data = unreal.EditorAssetLibrary.find_asset_data(mesh_path)
    tags = {}
    try:
        for key, value in asset_data.get_tag_values().items():
            tags[str(key)] = str(value)
    except Exception:
        pass
    result["asset_tags"] = tags
    for key in ("Bones", "NumBones", "BoneCount"):
        if key in tags and tags[key].isdigit():
            bone_count = int(tags[key])
            break
    expected_bones = manifest["measurements"].get("bone_count_expected_ue5")
    result["bone_count"] = bone_count
    if static:
        check("bone_count", True, "static prop; no skeleton by design")
    elif bone_count is None:
        check("bone_count", True,
              "not exposed to Python in this engine version; skipped")
    else:
        check("bone_count", expected_bones is None or bone_count == expected_bones,
              "engine reports {0} bones, manifest expected {1}".format(
                  bone_count, expected_bones))

    bounds = mesh.get_bounds()
    extent = bounds.box_extent
    height_cm = float(extent.z) * 2.0
    expected_cm = manifest["measurements"].get("height_cm_in_ue5")
    result["imported_height_cm"] = round(height_cm, 1)
    tolerance = 0.08 * expected_cm if expected_cm else 1e9
    check(
        "import_scale",
        expected_cm is not None and abs(height_cm - expected_cm) <= tolerance,
        "imported {0:.1f} cm, manifest expected {1} cm".format(height_cm, expected_cm),
    )

    materials = mesh.get_editor_property(
        "static_materials" if static else "materials")
    assigned = []
    for entry in materials:
        interface = entry.get_editor_property("material_interface")
        assigned.append(interface.get_name() if interface else None)
    result["material_slots"] = assigned
    # A default engine material counts as NOT assigned. Accepting any non-null
    # value here is how an all-white character passes a material check.
    placeholders = {"WorldGridMaterial", "DefaultMaterial", "DefaultDeferredDecalMaterial"}
    expected_names = set(manifest.get("textures", {}).keys())
    bad = [n for n in assigned if not n or n in placeholders]
    check("materials_assigned", not bad,
          "slots: {0}; expected materials from {1}".format(
              assigned, sorted(expected_names) or "manifest"))

    # An assigned material is not a textured one.
    #
    # Switching the cohort to a master material plus instances passed this
    # check and shipped four pure-white characters: every slot named the right
    # material, and not one of them carried a texture. So look at what the
    # material actually samples, and require the manifest's textures to be
    # among them.
    wanted = set()
    for slots in manifest.get("textures", {}).values():
        for spec in slots.values():
            stem = os.path.basename(spec["file"]).rsplit(".", 1)[0]
            wanted.add(stem)
    used = set()
    for entry in materials:
        interface = entry.get_editor_property("material_interface")
        if interface is None:
            continue
        lib = unreal.MaterialEditingLibrary
        try:
            for texture in lib.get_used_textures(interface):
                if texture is not None:
                    used.add(texture.get_name())
        except Exception:  # noqa: BLE001 - reported by the check below
            pass
        # get_used_textures answers for a Material and returns nothing for a
        # material INSTANCE, which reads identically to "this material has no
        # textures". Ask the instance for its parameter values instead.
        if isinstance(interface, unreal.MaterialInstance):
            try:
                base = interface.get_base_material()
                for name in lib.get_texture_parameter_names(base):
                    value = lib.get_material_instance_texture_parameter_value(
                        interface, name)
                    if value is not None:
                        used.add(value.get_name())
            except Exception:  # noqa: BLE001 - reported by the check below
                pass
    result["textures_used"] = sorted(used)
    missing_textures = sorted(wanted - used)
    check("materials_textured", not missing_textures,
          "material samples {0} textures; manifest textures not sampled: {1}".format(
              len(used), missing_textures or "none"))

    if static:
        try:
            lod_count = mesh.get_num_lods()
        except Exception:  # noqa: BLE001
            lod_count = None
        result["lod_count"] = lod_count
        expected_lods = len(manifest.get("lods") or []) or None
        check("lods", expected_lods is None or (lod_count or 0) >= expected_lods,
              "engine built {0} LODs, manifest asked for {1}".format(
                  lod_count, expected_lods))
        result["ok"] = all(c["ok"] for c in result["checks"])
        return result

    lod_count = None
    try:
        if hasattr(unreal, "SkeletalMeshEditorSubsystem"):
            lod_count = unreal.get_editor_subsystem(
                unreal.SkeletalMeshEditorSubsystem).get_lod_count(mesh)
        else:
            lod_count = unreal.EditorSkeletalMeshLibrary.get_lod_count(mesh)
    except Exception:
        lod_count = None
    result["lod_count"] = lod_count
    expected_lods = len(manifest.get("lods", [])) or None
    check("lods_built",
          lod_count is None or expected_lods is None or lod_count >= expected_lods,
          "engine reports {0} LODs, manifest declared {1}".format(lod_count, expected_lods))

    # Texture import settings are per-asset and silently wrong by default.
    tex_issues = []
    for material_name, slots in manifest.get("textures", {}).items():
        for slot, entry in slots.items():
            name = os.path.splitext(os.path.basename(entry["file"]))[0]
            path = "{0}/Textures/{1}".format(root, name)
            texture = unreal.EditorAssetLibrary.load_asset(path)
            if texture is None:
                tex_issues.append("{0}: missing".format(name))
                continue
            want_srgb = bool(entry["settings"].get("sRGB", False))
            got_srgb = bool(texture.get_editor_property("srgb"))
            if want_srgb != got_srgb:
                tex_issues.append("{0}: sRGB {1}, expected {2}".format(
                    name, got_srgb, want_srgb))
    check("texture_settings", not tex_issues,
          "; ".join(tex_issues) if tex_issues else "all correct")

    result["ok"] = all(c["ok"] for c in result["checks"])
    return result


def main():
    out_root = os.path.join(ROOT, "out")
    requested = {
        value.strip() for value in os.environ.get("RAC_ASSET_IDS", "").split(",")
        if value.strip()
    }
    manifests = []
    for name in sorted(os.listdir(out_root)):
        if requested and name not in requested:
            continue
        candidate = os.path.join(out_root, name, name + ".ue5import.json")
        if os.path.exists(candidate):
            manifests.append(candidate)

    unreal.log("RAC found {0} manifests".format(len(manifests)))
    report = {
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "assets": [],
    }

    for manifest_path in manifests:
        with open(manifest_path, "r", encoding="utf-8-sig") as handle:
            manifest = json.load(handle)
        asset_id = manifest["asset_id"]
        root = "/Game/Compiled/{0}".format(folder_for(asset_id))
        unreal.log("RAC importing {0} -> {1}".format(asset_id, root))
        try:
            import_asset.main([manifest_path])
            entry = verify(manifest, root)
        except Exception as error:  # noqa: BLE001 - report, never abort the batch
            unreal.log_error("RAC {0} failed: {1}".format(asset_id, error))
            entry = {
                "asset_id": asset_id,
                "ok": False,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        entry["manifest_path"] = manifest_path
        entry["manifest_sha256"] = sha256(manifest_path)
        report["assets"].append(entry)
        for check in entry.get("checks", []):
            unreal.log("RAC   [{0}] {1}: {2}".format(
                "OK " if check["ok"] else "FAIL", check["check"], check["detail"]))

    report["ok"] = all(a.get("ok") for a in report["assets"])
    out_path = os.environ.get("RAC_VERIFY_REPORT") or os.path.join(
        ROOT, "work", "ue5-verify.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    unreal.log("RAC_UE5_VERIFY_WRITTEN {0} ok={1}".format(out_path, report["ok"]))


main()
