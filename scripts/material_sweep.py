"""Bake material response after paint, keeping the accepted GLB geometry and base colour."""

import argparse
import copy
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from compress_textures import read_glb, write_glb
from surface_atlas import frames, read_image, triangles, unit


PROFILE = Path(__file__).resolve().parents[1] / "profiles/materials/surface-response.json"
TARGETS = {"framewright-scene": PROFILE.with_name("framewright-scene.json")}
SCHEMA = "reference-asset-compiler.material-sweep.v1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def field(pos, pattern, pitch):
    """Height gradient in rest space. Woven crossings, pebbles and elongated grain differ."""
    p = pos * (2 * np.pi / pitch)
    a = np.array([0.82, 0.48, 0.31], "f")
    b = np.array([-0.51, 0.85, 0.12], "f")
    c = np.array([-0.19, -0.23, 0.95], "f")
    x, y, z = (p @ axis for axis in (a, b, c))
    if pattern == "weave":
        # Alternate over/under rather than laying parallel ridges across the shirt.
        h = (0.54 * np.cos(x) * (1 + 0.55 * np.sin(y / 2)))[:, None] * a
        h += (0.54 * np.cos(y) * (1 - 0.55 * np.sin(x / 2)))[:, None] * b
        h += (0.1485 * (np.sin(x) * np.cos(y / 2)))[:, None] * b
        h -= (0.1485 * (np.sin(y) * np.cos(x / 2)))[:, None] * a
        return h + (0.19 * np.cos(z))[:, None] * c
    waves = {
        "metal": ((0.85, 0.11, 0.43), (0.24, 0.65, 0.14)),
        "fibres": ((0.1, 1.15, 0.18), (0.23, 0.77, 0.12)),
        "pores": ((0.95, 0.75, 0.9), (0.64, 1.18, 0.72)),
        "pebble": ((0.64, 0.93, 1.1), (1.15, 0.72, 0.86)),
    }
    grad = np.zeros_like(pos)
    for j, rates in enumerate(waves[pattern]):
        k = np.array(rates, "f")
        phase = p * k + (1.2 + j * 2.57)
        s, co = np.sin(phase), np.cos(phase)
        grad += k * co * (np.roll(s, 1, axis=1) + np.roll(s, 2, axis=1)) * (0.52 if not j else 0.32)
    return grad


def add_texture(doc, blob, name, array, sampler):
    im = Image.fromarray(array)
    out = io.BytesIO()
    im.save(out, "PNG", compress_level=4)
    encoded = out.getvalue()
    blob.extend(b"\0" * (-len(blob) % 4))
    view = len(doc["bufferViews"])
    doc["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(encoded)})
    blob.extend(encoded)
    imgs = doc.setdefault("images", [])
    tex = doc.setdefault("textures", [])
    imgs.append({"bufferView": view, "mimeType": "image/png", "name": name})
    tex.append({"source": len(imgs) - 1, **({"sampler": sampler} if sampler is not None else {})})
    return {"index": len(tex) - 1}, sha(encoded)


def validate_class(profile):
    lo, hi = profile["roughness"]
    values = [
        lo,
        hi,
        profile["metallic"],
        profile["specular"],
        profile["retain_normal"],
        profile["slope"],
    ]
    if not all(0 <= float(x) <= 1 for x in values) or lo > hi:
        raise ValueError("Surface response values must be ordered and in [0,1]")
    if not 0 < profile["pitch_mm"] <= 100 or profile["pattern"] not in (
        "smooth",
        "weave",
        "metal",
        "fibres",
        "pebble",
        "pores",
    ):
        raise ValueError("Unsupported detail pattern or physical pitch")


def apply_slot(doc, binary, blob, index, cfg, classes, directory):
    mat = doc["materials"][index]
    if cfg == {"keep": True}:
        return {"mode": "kept"}
    ext = mat.setdefault("extensions", {})
    if {"KHR_materials_unlit", "KHR_materials_pbrSpecularGlossiness"} & ext.keys():
        raise ValueError("Cannot add a metallic-roughness finish to an unlit/spec-gloss material")
    if ext.get("KHR_materials_ior", {}).get("ior", 1.5) != 1.5:
        raise ValueError("Response profiles are calibrated for IOR 1.5; keep this optical material")
    pbr = mat.setdefault("pbrMetallicRoughness", {})
    common = {"size", "meters_per_mesh_unit"}
    if "class" in cfg:
        valid = set(cfg) <= common | {"class"}
    else:
        valid = (
            {"mask", "labels", "mask_sha256"}
            <= set(cfg)
            <= common | {"mask", "labels", "mask_sha256"}
        )
    if not valid:
        raise ValueError(
            "Assign one class, an indexed mask with labels and SHA-256, or explicit keep"
        )
    labelmap = (
        {1: cfg["class"]} if "class" in cfg else {int(k): v for k, v in cfg["labels"].items()}
    )
    if not labelmap or not set(labelmap.values()) <= classes.keys():
        raise ValueError("A surface assignment names an unknown class")
    for name in set(labelmap.values()):
        validate_class(classes[name])
    uniform = classes[cfg["class"]] if "class" in cfg else None
    # Smooth single-class finishes need no atlas. An existing normal map remains active.
    if (
        uniform
        and uniform["pattern"] == "smooth"
        and uniform["roughness"][0] == uniform["roughness"][1]
    ):
        pbr.pop("metallicRoughnessTexture", None)
        pbr.update(metallicFactor=uniform["metallic"], roughnessFactor=uniform["roughness"][0])
        ext["KHR_materials_specular"] = {"specularFactor": uniform["specular"]}
        return {"mode": "uniform", "class": cfg["class"], "response": uniform}
    size = cfg.get("size", 1024)
    if type(size) is not int or not 32 <= size <= 4096:
        raise ValueError("Use a map size from 32 to 4096")
    mm = float(cfg.get("meters_per_mesh_unit", 1.0)) * 1000
    if not np.isfinite(mm) or mm <= 0:
        raise ValueError("Bind-space scale must be finite and positive")
    labels = np.ones((size, size), np.uint8)
    if "mask" in cfg:
        mask = (directory / cfg["mask"]).read_bytes()
        if cfg.get("mask_sha256") != sha(mask):
            raise ValueError(f"Class mask hash mismatch: {mat['name']}")
        im = Image.open(io.BytesIO(mask))
        if im.format != "PNG" or im.mode not in ("L", "P") or im.size != (size, size):
            raise ValueError("Indexed masks must be L/P PNGs at the requested square resolution")
        labels = np.asarray(im)
    for slot in [
        pbr.get("baseColorTexture"),
        pbr.get("metallicRoughnessTexture"),
        mat.get("normalTexture"),
    ]:
        if slot and (slot.get("texCoord", 0) != 0 or slot.get("extensions")):
            raise ValueError("Expected untransformed UV0 for the finish")
    y, x, pos, t, b, footprint = frames(triangles(doc, binary, index), size)
    ids = labels[y, x]
    if not set(np.unique(ids)) <= labelmap.keys():
        raise ValueError(f"An occupied texel on {mat['name']} has no declared material class")
    pos *= mm
    footprint *= mm

    def samples(slot):
        image = read_image(doc, binary, slot).convert("RGB")
        return (
            np.asarray(image.resize((size, size), Image.Resampling.BILINEAR))[y, x].astype("f")
            / 255
        )

    oldmr = pbr.get("metallicRoughnessTexture")
    oldn = mat.get("normalTexture")
    prior = (
        samples(oldmr)[:, 1] * pbr.get("roughnessFactor", 1)
        if oldmr
        else np.full(len(x), pbr.get("roughnessFactor", 1), "f")
    )
    normal = unit(samples(oldn) * 2 - 1) if oldn else np.tile(np.array([0, 0, 1], "f"), (len(x), 1))
    src_scale = oldn.get("scale", 1) if oldn else 1
    normal[:, :2] *= src_scale
    normal = unit(normal)
    packed = np.full((len(x), 4), 255, np.uint8)
    rows = {}
    for label, name in sorted(labelmap.items()):
        use = ids == label
        if not use.any():
            continue
        prop = classes[name]
        lo, hi = prop["roughness"]
        pp = pos[use]
        variation = np.sin(pp @ np.array([0.034, 0.021, 0.008], "f")) * np.sin(
            pp @ np.array([0.026, -0.012, 0.031], "f")
        )
        # Historic variations may contribute; an accidental old factor cannot dictate the new class.
        rough = lo + (hi - lo) * np.clip(0.5 + 0.36 * (prior[use] - 0.5) + 0.23 * variation, 0, 1)
        packed[use, 1] = np.rint(rough * 255)
        packed[use, 2] = round(prop["metallic"] * 255)
        packed[use, 3] = round(prop["specular"] * 255)
        slope = normal[use, :2] / np.maximum(0.1, normal[use, 2, None]) * prop["retain_normal"]
        if prop["pattern"] != "smooth":
            pitch = prop["pitch_mm"]
            # Fade sub-texel detail instead of aliasing pores into pepper.
            aa = np.clip((pitch / np.maximum(footprint[use], 0.0001) - 1.6) / 1.6, 0, 1)
            grad = field(pp, prop["pattern"], pitch)
            slope -= (prop["slope"] * aa)[:, None] * np.column_stack(
                ((grad * t[use]).sum(1), (grad * b[use]).sum(1))
            )
        corrected = unit(np.c_[slope, np.ones(len(slope), "f")])
        normal[use] = corrected
        rows[str(label)] = {
            "class": name,
            "occupied_texels": int(use.sum()),
            "roughness_median": round(float(np.median(rough)), 4),
            "metallic": prop["metallic"],
            "dielectric_specular": prop["specular"],
            "normal_tilt_rms_degrees": round(
                float(
                    np.sqrt(np.mean(np.rad2deg(np.arccos(np.clip(corrected[:, 2], -1, 1))) ** 2))
                ),
                3,
            ),
        }
    occupied = np.zeros((size, size), bool)
    occupied[y, x] = True
    nearest = distance_transform_edt(~occupied, return_distances=False, return_indices=True)

    def padding(values):
        full = np.zeros((size, size, values.shape[1]), np.uint8)
        full[y, x] = values
        return full[nearest[0], nearest[1]]

    base = pbr.get("baseColorTexture", {})

    def sampler(slot):
        return doc["textures"][slot["index"]].get("sampler") if slot else None

    mr, mrhash = add_texture(
        doc, blob, mat["name"] + " • response", padding(packed), sampler(oldmr or base)
    )
    nm, nhash = add_texture(
        doc,
        blob,
        mat["name"] + " • normal",
        padding(np.uint8(np.rint((normal * 0.5 + 0.5) * 255))),
        sampler(oldn or base),
    )
    pbr.update(metallicRoughnessTexture=mr, roughnessFactor=1, metallicFactor=1)
    # R is neutral: keep any independent occlusionTexture and its existing UV/strength.
    ext["KHR_materials_specular"] = {"specularTexture": dict(mr)}
    mat["normalTexture"] = nm
    return {
        "mode": "atlas",
        "size": size,
        "mask_sha256": cfg.get("mask_sha256"),
        "classes": rows,
        "response_png_sha256": mrhash,
        "normal_png_sha256": nhash,
    }


def apply_target(cfg, profile, classes):
    name = cfg.get("response_target")
    if name is None and "target_sha256" not in cfg:
        return {}
    if name not in TARGETS:
        raise ValueError("Unknown material response target")
    path = TARGETS[name]
    digest = sha(path.read_bytes())
    if cfg.get("target_sha256") != digest:
        raise ValueError("The response target must match its assigned SHA-256")
    target = read(path)
    if target.get("schema") != "rac.surface-target.v1" or target.get("base_sha256") != sha(
        profile.read_bytes()
    ):
        raise ValueError("The response target was authored against a different base profile")
    for surface, fields in target["overrides"].items():
        if surface not in classes or not fields.keys() <= classes[surface].keys():
            raise ValueError(f"Unknown target surface or property on {surface}")
        classes[surface].update(fields)
        validate_class(classes[surface])
    return {"response_target": name, "target_sha256": digest}


def sweep(source, output, report, manifest):
    paths = [p.resolve() for p in (source, output, report, manifest)]
    if len(set(paths)) != 4 or output.exists() or report.exists():
        raise ValueError(
            "Supply distinct paths and a new output and receipt; earlier finishes are evidence"
        )
    cfg = read(manifest)
    raw = source.read_bytes()
    if cfg.get("schema") != "rac.surface-assignments.v1" or cfg.get("source_sha256") != sha(raw):
        raise ValueError("Assignments must name this exact source GLB by SHA-256")
    profile = manifest.parent / cfg["profile"] if "profile" in cfg else PROFILE
    pr = read(profile)
    if pr.get("schema") != "rac.surface-response.v1":
        raise ValueError("Unknown surface response profile")
    if cfg.get("profile_sha256") and cfg["profile_sha256"] != sha(profile.read_bytes()):
        raise ValueError("The declared response profile changed")
    target_receipt = apply_target(cfg, profile, pr["classes"])
    if (
        len(raw) < 20
        or raw[:4] != b"glTF"
        or int.from_bytes(raw[4:8], "little") != 2
        or int.from_bytes(raw[8:12], "little") != len(raw)
    ):
        raise ValueError("Expected a complete GLB 2.0")
    doc, binary = read_glb(raw)
    if (
        len(doc.get("buffers", [])) != 1
        or "uri" in doc["buffers"][0]
        or any("uri" in im for im in doc.get("images", []))
    ):
        raise ValueError("Supply a self-contained embedded GLB")
    original = copy.deepcopy(doc)
    names = [m.get("name") for m in doc["materials"]]
    if (
        any(not n for n in names)
        or len(names) != len(set(names))
        or set(names) != set(cfg["materials"])
    ):
        raise ValueError("Assign each unique material name a class, mask, or explicit keep")
    blob = bytearray(binary)
    rows = {
        n: apply_slot(doc, binary, blob, i, cfg["materials"][n], pr["classes"], manifest.parent)
        for i, n in enumerate(names)
    }
    used = doc.setdefault("extensionsUsed", [])
    if all(r["mode"] == "kept" for r in rows.values()):
        raise ValueError("Every material is marked keep; assign at least one surface before baking")
    if "KHR_materials_specular" not in used:
        used.append("KHR_materials_specular")
    doc["buffers"][0]["byteLength"] = len(blob)
    result = write_glb(doc, bytes(blob))
    reopened, stored = read_glb(result)
    for k in original:
        if (
            k not in {"materials", "buffers", "images", "textures", "bufferViews", "extensionsUsed"}
            and original[k] != reopened[k]
        ):
            raise ValueError(f"Protected model field changed: {k}")
    for k in ("images", "textures", "bufferViews"):
        if original.get(k, []) != reopened.get(k, [])[: len(original.get(k, []))]:
            raise ValueError(f"Original {k} changed")
    if not stored.startswith(binary):
        raise ValueError("Original geometry, animation or image buffers changed")
    out = {
        "schema": SCHEMA,
        "ok": True,
        "source_sha256": sha(raw),
        "output_sha256": sha(result),
        "manifest_sha256": sha(manifest.read_bytes()),
        "profile_sha256": sha(profile.read_bytes()),
        "original_binary_prefix_verified_bytes": len(binary),
        "materials": rows,
        "visual_approval": "pending",
        **target_receipt,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as file:
        file.write(result)
    with report.open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2)
    return out


def starter(source, output, target=None):
    """Inventory actual slots. Guesses from broad names such as 'painted' are unsafe."""
    raw = source.read_bytes()
    doc, _ = read_glb(raw)
    names = [m.get("name") for m in doc.get("materials", [])]
    if not names or not all(names) or len(names) != len(set(names)):
        raise ValueError("Give each material slot a unique name before creating an assignment")
    cfg = {
        "schema": "rac.surface-assignments.v1",
        "source_sha256": sha(raw),
        "profile_sha256": sha(PROFILE.read_bytes()),
        "materials": {n: {"keep": True} for n in names},
    }
    if target:
        cfg.update(response_target=target, target_sha256=sha(TARGETS[target].read_bytes()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf8") as stream:
        json.dump(cfg, stream, indent=2)


def main(argv):
    if argv[:1] == ["--init"]:
        parser = argparse.ArgumentParser(
            description="Make an editable assignment from an exported GLB."
        )
        parser.add_argument("source", type=Path)
        parser.add_argument("output", type=Path)
        parser.add_argument(
            "--target", choices=TARGETS, help="Opt in to a renderer-specific finish"
        )
        args = parser.parse_args(argv[1:])
        try:
            starter(args.source, args.output, args.target)
        except (ValueError, OSError) as exc:
            parser.exit(1, f"RAC_ERROR {exc}\n")
        print("MATERIAL_ASSIGNMENTS_READY — every swatch awaits its tailor.")
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "report"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--textures", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        sweep(args.source, args.output, args.report, args.textures)
    except (ValueError, KeyError, IndexError, OSError, TypeError) as exc:
        print(f"RAC_ERROR {exc}", file=sys.stderr)
        return 1
    print("MATERIAL_SWEEP_OK — cloth has relinquished its career as chrome.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[2:] if sys.argv[1:2] == ["--"] else sys.argv[1:]))
