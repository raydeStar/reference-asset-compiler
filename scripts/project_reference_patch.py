"""Project hash-bound registered image repairs onto an acquired GLB's existing UVs.

The recipe defines mesh-space cameras, material names, bounds and optional surface
response. It is a mapping step, not image generation or an acceptance decision.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

from compress_textures import read_glb, write_glb
from surface_atlas import frames, raster, read_image, triangles, unit


def smooth(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def sample(pixels, coordinates):
    return np.concatenate(
        [
            cv2.remap(
                pixels,
                (c[:, 0] * pixels.shape[1] - 0.5).astype("f")[:, None],
                (c[:, 1] * pixels.shape[0] - 0.5).astype("f")[:, None],
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )[:, 0]
            for c in np.array_split(coordinates, max(1, (len(coordinates) + 19999) // 20000))
        ]
    )


def checked_file(root, item, key):
    path = (root / item[key]).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != item[key + "_sha256"]:
        raise ValueError(f"Stale {key} reference: {path.name}")
    return path


def fill_unseen(position, donor, blend, radius):
    """Carry nearby observed colour into tiny projection gaps on the same surface."""
    if not np.isfinite(radius) or radius < 0:
        raise ValueError("fill_unseen_m must be nonnegative and finite")
    if radius == 0:
        return donor, blend
    trusted = np.flatnonzero(blend >= 0.95)
    missing = np.flatnonzero(blend < 0.95)
    if not len(trusted) or not len(missing):
        return donor, blend
    distance, nearest = cKDTree(position[trusted]).query(position[missing])
    close = distance <= radius
    donor, blend = donor.copy(), blend.copy()
    donor[missing[close]] = donor[trusted[nearest[close]]]
    blend[missing[close]] = 1
    return donor, blend


def prepare_view(root, definition):
    image_path = checked_file(root, definition, "image")
    guide_path = checked_file(root, definition, "guide")
    pixels = np.asarray(Image.open(image_path).convert("RGB")).astype("f")
    guide = np.load(guide_path, allow_pickle=False)
    valid = guide["hit"] >= 0
    if not valid.any() or guide["depth"].shape != valid.shape:
        raise ValueError("A registered guide needs valid hit/depth arrays")
    near = tuple(
        ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    )
    depth = guide["depth"][near].astype("f")
    if not np.isfinite(depth).all():
        raise ValueError("The registered guide has invalid visible depths")
    mask = (
        cv2.resize(
            valid.astype("B"), (pixels.shape[1], pixels.shape[0]), interpolation=cv2.INTER_NEAREST
        )
        > 0
    )
    # Opt-in chromatic foreground protection for skin-only guides. A slight AI
    # silhouette drift must not turn the nose into a porcelain teapot.
    chroma_min = float(definition.get("foreground_chroma_min", 0))
    dark_max = float(definition.get("foreground_dark_max", 0))
    if not np.isfinite(chroma_min) or not 0 <= chroma_min <= 255:
        raise ValueError("foreground_chroma_min must be in [0, 255]")
    if not np.isfinite(dark_max) or not 0 <= dark_max <= 255:
        raise ValueError("foreground_dark_max must be in [0, 255]")
    if chroma_min:
        mask &= (np.ptp(pixels, axis=2) >= chroma_min) | (pixels.max(axis=2) < dark_max)
        if not mask.any():
            raise ValueError("No chromatic foreground remains in the registered guide")
    nearest = tuple(
        ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    )
    pixels = pixels[nearest]
    axis = np.asarray(definition["axis"], "f")
    up = np.asarray(definition.get("up", [0, 1, 0]), "f")
    if np.linalg.norm(axis) < 1e-8 or np.linalg.norm(np.cross(up, axis)) < 1e-8:
        raise ValueError("The camera needs distinct forward and up axes")
    axis = unit(axis)
    side = unit(np.cross(up, axis))
    up = np.cross(axis, side)
    width = float(definition["width"])
    if width <= 0:
        raise ValueError("Camera width must be positive")
    relief = float(definition.get("relief_m", 0.00004))
    gray = pixels @ np.array([0.26, 0.54, 0.20], "f") / 255
    height = (gray - cv2.GaussianBlur(gray, (0, 0), 3)) * relief
    dy, dx = np.gradient(height, width / len(pixels), width / pixels.shape[1])
    return dict(
        image=pixels,
        depth=depth,
        mask=valid.astype("f"),
        axis=axis,
        side=side,
        up=up,
        center=np.asarray(definition["center"], "f"),
        width=width,
        dx=dx,
        dy=dy,
        tolerance=float(definition.get("visibility_tolerance_m", 0.006)),
    )


def scope_weight(position, definition):
    bounds = definition.get("bounds")
    if bounds is None:
        return np.ones(len(position), "f")
    low, high = np.asarray(bounds, "f")
    if np.any(low >= high):
        raise ValueError("Patch bounds must have positive volume")
    feather = float(definition.get("feather_m", 0.01))
    distance = np.minimum(position - low, high - position).min(1)
    return smooth(distance / feather) if feather > 0 else (distance >= 0).astype("f")


def project_patch(source, output, report, recipe_path):
    source, output, report, recipe_path = map(Path, (source, output, report, recipe_path))
    if len({p.resolve() for p in (source, output, report, recipe_path)}) != 4:
        raise ValueError("Source, recipe, output and report need distinct paths")
    if output.exists() or report.exists():
        raise ValueError("Keep prior candidates; select new output and report paths")
    config = json.loads(recipe_path.read_text(encoding="utf8"))
    if config.get("schema") != "reference-asset-compiler.reference-patch-recipe.v1":
        raise ValueError("Expected a reference-patch-recipe.v1")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != config["source_sha256"]:
        raise ValueError("The patch recipe is bound to a different source GLB")
    if not config.get("acquisition_provenance") or not config.get("patches"):
        raise ValueError("Acquisition provenance and scoped patches are required")
    doc, binary = read_glb(raw)
    original = copy.deepcopy(doc)
    buffer = bytearray(binary)
    names = [m.get("name") for m in doc["materials"]]
    jobs = {}
    for patch in config["patches"]:
        name = patch["material"]
        if names.count(name) != 1:
            raise ValueError(f"Expected one material named {name}")
        size = int(patch["size"])
        if size < 16 or size > 8192:
            raise ValueError("Atlas size must be between 16 and 8192")
        if not patch.get("views"):
            raise ValueError("A patch must have a registered view")
        prepared = [prepare_view(recipe_path.parent, view) for view in patch["views"]]
        jobs.setdefault(names.index(name), []).append((patch, prepared))

    def embed(pixels, label):
        import io

        stream = io.BytesIO()
        Image.fromarray(pixels).save(stream, format="PNG")
        data = stream.getvalue()
        buffer.extend(b"\0" * (-len(buffer) % 4))
        view = len(doc["bufferViews"])
        doc["bufferViews"].append(dict(buffer=0, byteOffset=len(buffer), byteLength=len(data)))
        buffer.extend(data)
        image = len(doc.setdefault("images", []))
        doc["images"].append(dict(name=label, bufferView=view, mimeType="image/png"))
        texture = len(doc.setdefault("textures", []))
        doc["textures"].append(dict(source=image))
        return {"index": texture}

    statistics = []
    for material_index, patches in jobs.items():
        sizes = {int(patch["size"]) for patch, _ in patches}
        if len(sizes) != 1:
            raise ValueError("All patches on one material need the same atlas size")
        size = sizes.pop()
        material = doc["materials"][material_index]
        pbr = material.setdefault("pbrMetallicRoughness", {})
        geometry = triangles(doc, binary, material_index)
        yy, xx, pos, tangent, bitangent, _ = frames(geometry, size)
        face, bary = raster(geometry[1], size, size)
        weights = np.c_[1 - bary[yy, xx].sum(1), bary[yy, xx]]
        outward = unit(np.einsum("ij,ijk->ik", weights, geometry[2][face[yy, xx]]))
        coordinates = np.c_[(xx + 0.5) / size, (yy + 0.5) / size]
        factor = np.asarray(pbr.get("baseColorFactor", [1, 1, 1, 1]), "f")
        if "baseColorTexture" in pbr:
            if not np.allclose(factor, 1):
                raise ValueError(
                    "Normalize textured base-color factors before reference projection"
                )
            color = sample(
                np.asarray(read_image(doc, binary, pbr["baseColorTexture"]).convert("RGBA")),
                coordinates,
            ).astype("f")
        else:
            rgb = np.where(
                factor[:3] <= 0.0031308, factor[:3] * 12.92, 1.055 * factor[:3] ** (1 / 2.4) - 0.055
            )
            color = np.tile(np.r_[rgb, factor[3]] * 255, (len(pos), 1))
        response = (
            sample(
                np.asarray(
                    read_image(doc, binary, pbr["metallicRoughnessTexture"]).convert("RGBA")
                ),
                coordinates,
            ).astype("f")
            if "metallicRoughnessTexture" in pbr
            else np.tile(
                [255, pbr.get("roughnessFactor", 1) * 255, pbr.get("metallicFactor", 1) * 255, 255],
                (len(pos), 1),
            ).astype("f")
        )
        if "metallicRoughnessTexture" in pbr:
            response[:, 1] *= pbr.get("roughnessFactor", 1)
            response[:, 2] *= pbr.get("metallicFactor", 1)
        specular = material.get("extensions", {}).get("KHR_materials_specular", {})
        response[:, 3] = (
            sample(
                np.asarray(read_image(doc, binary, specular["specularTexture"]).convert("RGBA")),
                coordinates,
            )[:, 3]
            if "specularTexture" in specular
            else 255
        )
        response[:, 3] *= specular.get("specularFactor", 1)
        normals = (
            unit(
                sample(
                    np.asarray(read_image(doc, binary, material["normalTexture"]).convert("RGB")),
                    coordinates,
                ).astype("f")
                / 127.5
                - 1
            )
            if "normalTexture" in material
            else np.tile([0.0, 0.0, 1.0], (len(pos), 1))
        )
        normals[:, :2] *= material.get("normalTexture", {}).get("scale", 1)
        normals = unit(normals)
        touched = np.zeros(len(pos), bool)
        for patch, views in patches:
            point, normal = pos.copy(), outward.copy()
            sign = patch.get("mirror_x")
            if sign is not None:
                if sign not in (-1, 1):
                    raise ValueError("mirror_x must be -1 or +1")
                normal[:, 0] *= np.where(point[:, 0] * sign < 0, -1, 1)
                point[:, 0] = abs(point[:, 0]) * sign
            acc = np.zeros((len(pos), 3), "f")
            slope = np.zeros_like(acc)
            total = np.zeros(len(pos), "f")
            confidence = np.zeros(len(pos), "f")
            for view in views:
                relative = point - view["center"]
                uv = np.c_[
                    0.5 + relative @ view["side"] / view["width"],
                    0.5 - relative @ view["up"] / view["width"],
                ]
                alignment = normal @ view["axis"]
                facing = np.clip(
                    abs(alignment) if patch.get("two_sided", False) else alignment, 0, 1
                )
                visible = smooth(
                    (
                        view["tolerance"]
                        - np.maximum(0, sample(view["depth"], uv) - relative @ view["axis"])
                    )
                    / max(view["tolerance"] * 0.67, 1e-6)
                )
                margin = np.min(np.c_[uv, 1 - uv], axis=1)
                valid = visible * smooth(margin / 0.02) * smooth(sample(view["mask"], uv))
                weight = valid * facing**6
                acc += sample(view["image"], uv) * weight[:, None]
                gradient = (
                    sample(view["dx"], uv)[:, None] * view["side"]
                    - sample(view["dy"], uv)[:, None] * view["up"]
                )
                if sign is not None:
                    gradient[:, 0] *= np.where(pos[:, 0] * sign < 0, -1, 1)
                slope += gradient * weight[:, None]
                total += weight
                confidence = np.maximum(confidence, valid * smooth((facing - 0.05) / 0.40))
            blend = confidence * scope_weight(pos, patch) * (total > 1e-8)
            donor = acc / np.maximum(total[:, None], 1e-9)
            gradient = slope / np.maximum(total[:, None], 1e-9)
            fill_radius = float(patch.get("fill_unseen_m", 0))
            if fill_radius and patch.get("bounds") is not None:
                raise ValueError("fill_unseen_m needs a whole-material patch without bounds")
            donor, blend = fill_unseen(pos, donor, blend, fill_radius)
            color[:, :3] += (donor - color[:, :3]) * blend[:, None]
            retain = float(patch.get("retain_normal", 0.25))
            relief = np.c_[
                -np.sum(gradient * tangent, axis=1), -np.sum(gradient * bitangent, axis=1)
            ]
            target = unit(
                np.c_[normals[:, :2] * retain + np.clip(relief, -0.15, 0.15), np.ones(len(pos))]
            )
            normals = unit(normals + (target - normals) * blend[:, None])
            for key, channel in [("roughness", 1), ("metallic", 2), ("specular", 3)]:
                if key in patch.get("response", {}):
                    value = float(patch["response"][key])
                    if not 0 <= value <= 1:
                        raise ValueError("Response factors must be in [0, 1]")
                    response[:, channel] += (value * 255 - response[:, channel]) * blend
            touched |= blend > 0.5
        if not touched.any():
            raise ValueError(f"No visible texels were repaired for {material['name']}")
        near = tuple(
            ndimage.distance_transform_edt(face < 0, return_distances=False, return_indices=True)
        )
        slots = {}
        for label, values in [
            ("color", color),
            ("response", response),
            ("normal", normals * 127.5 + 127.5),
        ]:
            image = np.zeros((size, size, values.shape[1]), "B")
            image[yy, xx] = np.rint(values).clip(0, 255).astype("B")
            slots[label] = embed(image[near], f"{material['name']} reference repair {label}")
        pbr["baseColorTexture"] = slots["color"]
        pbr["baseColorFactor"] = [1, 1, 1, 1]
        pbr["metallicRoughnessTexture"] = slots["response"]
        pbr["roughnessFactor"] = 1
        pbr["metallicFactor"] = 1
        material["normalTexture"] = slots["normal"]
        material.setdefault("extensions", {}).setdefault("KHR_materials_specular", {})[
            "specularTexture"
        ] = slots["response"].copy()
        material["extensions"]["KHR_materials_specular"]["specularFactor"] = 1
        if "KHR_materials_specular" not in doc.setdefault("extensionsUsed", []):
            doc["extensionsUsed"].append("KHR_materials_specular")
        statistics.append(
            dict(
                material=material["name"],
                size=size,
                occupied_texels=len(pos),
                changed_texels=int(touched.sum()),
            )
        )
    for key in ("meshes", "nodes", "skins", "animations", "accessors", "scenes"):
        if doc.get(key) != original.get(key):
            raise AssertionError(f"Reference projection changed {key}")
    doc["buffers"][0]["byteLength"] = len(buffer)
    result = write_glb(doc, bytes(buffer))
    receipt = dict(
        schema="reference-asset-compiler.reference-patch.v1",
        source_sha256=hashlib.sha256(raw).hexdigest(),
        output_sha256=hashlib.sha256(result).hexdigest(),
        recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
        original_binary_prefix_retained=bytes(buffer[: len(binary)]) == binary,
        geometry_rig_morphs_and_animation_unchanged=True,
        statistics=statistics,
        visual_acceptance="pending",
        production_ready=False,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(result)
    with report.open("x", encoding="utf8") as stream:
        json.dump(receipt, stream, indent=2)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "report"):
        parser.add_argument(name, type=Path)
    parser.add_argument(
        "--textures", type=Path, required=True, help="Hash-bound registered patch recipe"
    )
    args = parser.parse_args(sys.argv[2:] if sys.argv[1:2] == ["--"] else sys.argv[1:])
    try:
        project_patch(args.source, args.output, args.report, args.textures)
    except (ValueError, KeyError, IndexError, OSError, TypeError) as exc:
        parser.exit(1, f"RAC_ERROR {exc}\n")
    print("REFERENCE_PATCH_COMPLETE -- a careful tailor keeps the bones where they belong.")


if __name__ == "__main__":
    main()
