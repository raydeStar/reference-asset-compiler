"""Publish a passing production build as its own importable asset.

The accepted assets in `out/<asset>/` are authorities and are never touched.
This writes a sibling `out/<asset>-production/` -- a versioned derivative with
its own FBX, textures and UE5 import manifest -- so both can be imported and
compared side by side in the engine. `import_and_verify.py` discovers it
automatically, because discovery is `out/<name>/<name>.ue5import.json`.

The ORM is packed here rather than baked again: R is AO, G is authored
roughness and B is authored metallic. Older character builds without those
passes retain the narrow luminance-derived roughness and zero-metal fallback;
new prop builds must carry the real per-material channels.

Usage:
  python scripts/promote_production.py <asset> [<asset> ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler.approvals import validate_texture_approval  # noqa: E402
from reference_asset_compiler.runtime_evidence import record_static_publish_stages  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def camel(asset_id):
    return "".join(part.capitalize() for part in asset_id.replace("_", "-").split("-"))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _mask_channel(path, size):
    image = Image.open(path).convert("L")
    if image.size != size:
        image = image.resize(size, Image.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0


def pack_orm(ao_path, base_path, out_path, roughness_path=None, metallic_path=None):
    """Pack AO/roughness/metallic, with an explicit legacy fallback."""
    ao = np.asarray(Image.open(ao_path).convert("L"), dtype=np.float32) / 255.0
    size = (ao.shape[1], ao.shape[0])
    if roughness_path and Path(roughness_path).is_file():
        rough = _mask_channel(roughness_path, size)
        roughness_source = "authored per-material bake"
    else:
        albedo = Image.open(base_path).convert("RGB")
        if albedo.size != size:
            albedo = albedo.resize(size, Image.LANCZOS)
        rgb = np.asarray(albedo, dtype=np.float32) / 255.0
        luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        rough = np.clip(0.86 - 0.34 * np.sqrt(np.clip(luma, 0.0, 1.0)), 0.35, 0.92)
        roughness_source = "legacy fallback derived from albedo luminance"
    if metallic_path and Path(metallic_path).is_file():
        metallic = _mask_channel(metallic_path, size)
        metallic_source = "authored per-material bake"
    else:
        metallic = np.zeros_like(ao)
        metallic_source = "legacy fallback constant 0"
    orm = np.zeros(ao.shape + (3,), dtype=np.float32)
    orm[..., 0] = ao
    orm[..., 1] = rough
    orm[..., 2] = metallic
    Image.fromarray((np.clip(orm, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)).save(out_path)
    return {"ao_mean": round(float(ao.mean()), 4),
            "roughness_mean": round(float(rough.mean()), 4),
            "metallic_mean": round(float(metallic.mean()), 4),
            "roughness_source": roughness_source,
            "metallic_source": metallic_source}


def promote(asset):
    prod = ROOT / "work" / asset / "prod-v2"
    report_path = prod / "retopo.json"
    if not report_path.exists():
        print("[PROMOTE] {0}: no build at {1}".format(asset, prod))
        return None
    retopo = json.loads(report_path.read_text(encoding="utf-8"))
    texture = json.loads((prod / "gate-tex.json").read_text(encoding="utf-8"))
    # A static prop has no rig gate and no deformation suite to read, because
    # the build never ran them. Say so in the manifest rather than leaving the
    # keys absent: an absent gate and a passed one are both falsy, and the
    # difference between "this has no skeleton" and "nobody checked" is exactly
    # what the manifest exists to record.
    prop = retopo.get("asset_kind") == "static_prop"
    if prop:
        rig = {"profile": "static_prop", "ok": True, "failures": [],
               "warnings": [], "skipped": "a static prop has no skeleton"}
        deform = {"ok": True, "skipped": "a static prop does not deform"}
    else:
        rig = json.loads((prod / "gate-rig.json").read_text(encoding="utf-8"))
        deform = json.loads((prod / "deform.json").read_text(encoding="utf-8"))
    if not (retopo.get("ok") and rig.get("ok") and texture.get("ok")):
        print("[PROMOTE] {0}: refusing to publish a build that did not pass".format(asset))
        return None
    job = ROOT / "work" / asset
    texture_approval = None
    if (job / "state.json").is_file():
        try:
            texture_approval = validate_texture_approval(job, prod, retopo)
        except (OSError, KeyError, ValueError) as error:
            print("[PROMOTE] {0}: refusing unreviewed texture output: {1}".format(asset, error))
            return None

    new_id = asset + "-production"
    dest = ROOT / "out" / new_id
    (dest / "textures").mkdir(parents=True, exist_ok=True)
    source = json.loads((ROOT / "out" / asset / (asset + ".ue5import.json"))
                        .read_text(encoding="utf-8-sig"))

    fbx = dest / (new_id + ".fbx")
    shutil.copy2(prod / (asset + "_production.fbx"), fbx)
    fbm_src = prod / (asset + "_production.fbm")
    if fbm_src.is_dir():
        shutil.rmtree(dest / (new_id + ".fbm"), ignore_errors=True)
        shutil.copytree(fbm_src, dest / (new_id + ".fbm"))

    name = camel(asset)
    material = "M_{0}_Production".format(name)
    stem = "T_{0}Production".format(name)
    shutil.copy2(prod / retopo["baked"]["BaseColor"],
                 dest / "textures" / (stem + "_BaseColor.png"))
    # A character whose geometry could not be reduced has no normal map: there
    # was no denser surface to capture one from, and baking one anyway just
    # ships a flat blue sheet.
    has_normal = "Normal" in retopo["baked"]
    if has_normal:
        shutil.copy2(prod / retopo["baked"]["Normal"],
                     dest / "textures" / (stem + "_Normal.png"))
    orm_stats = pack_orm(prod / retopo["baked"]["AO"],
                         prod / retopo["baked"]["BaseColor"],
                         dest / "textures" / (stem + "_ORM.png"),
                         (prod / retopo["baked"]["Roughness"]
                          if "Roughness" in retopo["baked"] else None),
                         (prod / retopo["baked"]["Metallic"]
                          if "Metallic" in retopo["baked"] else None))

    manifest = {
        "asset_id": new_id,
        "derived_from": asset,
        "kind": source.get("kind") or source.get("asset_kind"),
        "asset_kind": retopo.get("asset_kind", "humanoid"),
        # What the engine should build. A prop imported as a skeletal mesh
        # gets a one-bone skeleton and an animation blueprint it will never
        # use, and it stops being placeable as ordinary level geometry.
        "ue5_mesh_type": "StaticMesh" if prop else "SkeletalMesh",
        "skeleton_profile": source.get("skeleton_profile"),
        "retarget_note": source.get("retarget_note"),
        "fbx": fbx.name,
        "fbx_sha256": sha256(fbx),
        "source_authority": str(ROOT / "out" / asset / (asset + ".fbx")),
        "source_authority_sha256": source.get("fbx_sha256"),
        "blender_version": retopo.get("blender_version"),
        "ue5_import": source.get("ue5_import"),
        "measurements": {
            # Carried from the authority so the engine's scale check has
            # something to compare against. The retopo must not resize the
            # character, and the check's 8% tolerance is what proves it: the
            # remesh shaves a few millimetres off the silhouette and nothing
            # more.
            "height_m_after": source.get("measurements", {}).get("height_m_after"),
            "height_cm_in_ue5": source.get("measurements", {}).get("height_cm_in_ue5"),
            "bone_count_expected_ue5": source.get("measurements", {}).get(
                "bone_count_expected_ue5"),
            "total_tris_before": retopo.get("high_tris"),
            "total_tris": retopo.get("low_tris"),
            "quads": retopo.get("low_quads"),
            "silhouette_iou": retopo.get("silhouette_iou"),
            "max_influences": (retopo.get("influences") or {}).get("after"),
            "unweighted_verts": (retopo.get("influences") or {}).get(
                "unweighted_verts"),
            "height_m": (source.get("height_m")
                         or source.get("measurements", {}).get("height_m_after")),
            "shells": len(retopo.get("shells", [])),
            "shells_refused": retopo.get("shells_refused"),
            "faces_preserved": retopo.get("faces_preserved"),
        },
        "lods": source.get("lods"),
        "materials": [material],
        "textures": {material: dict(
            {"BaseColor": {"file": "textures/{0}_BaseColor.png".format(stem),
                           "settings": {"compression": "TC_Default",
                                        "sRGB": True, "flip_green": False}},
             "ORM": {"file": "textures/{0}_ORM.png".format(stem),
                     "settings": {"compression": "TC_Masks",
                                  "sRGB": False, "flip_green": False}}},
            # Blender bakes an OpenGL-convention normal map, green pointing
            # up. Unreal reads DirectX convention, green pointing down. Left
            # unflipped the lighting is wrong on every sloping surface, which
            # reads as faceting and a washed-out character in the engine while
            # the same map looks correct in a Blender render.
            **({"Normal": {"file": "textures/{0}_Normal.png".format(stem),
                           "settings": {"compression": "TC_Normalmap",
                                        "sRGB": False, "flip_green": True}}}
               if has_normal else {}))},
        "gate": {"profile": rig.get("profile"), "ok": rig.get("ok"),
                 "failures": rig.get("failures"), "warnings": rig.get("warnings")},
        "deformation": deform,
        "texture_quality": {material: texture},
        "texture_approval": texture_approval,
        "pbr_pack": orm_stats,
        "retopology": retopo,
    }
    # Remove textures this build no longer ships. A character that used to get
    # a normal map and now does not would otherwise keep the old one sitting
    # beside the manifest that no longer mentions it -- which is the kind of
    # thing that gets picked up by hand later and put back.
    keep = {spec["file"].split("/")[-1]
            for slots in manifest["textures"].values() for spec in slots.values()}
    stale = [f for f in (dest / "textures").glob("*.png") if f.name not in keep]
    for path in stale:
        path.unlink()
    if stale:
        print("[PROMOTE] {0}: removed stale {1}".format(
            asset, ", ".join(sorted(f.name for f in stale))))

    out_manifest = dest / (new_id + ".ue5import.json")
    out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if texture_approval is not None:
        try:
            record_static_publish_stages(job, out_manifest)
        except (OSError, KeyError, ValueError) as error:
            print("[PROMOTE] {0}: payload written but ledger publication failed: {1}".format(
                asset, error))
            return None
    print("[PROMOTE] {0} -> {1}  {2} -> {3} tris".format(
        asset, dest.name, retopo.get("high_tris"), retopo.get("low_tris")))
    return str(out_manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets", nargs="+")
    args = parser.parse_args()
    published = [promote(a) for a in args.assets]
    ok = [p for p in published if p]
    print("[PROMOTE] published {0} of {1}".format(len(ok), len(published)))
    return 0 if len(ok) == len(published) else 1


if __name__ == "__main__":
    raise SystemExit(main())
