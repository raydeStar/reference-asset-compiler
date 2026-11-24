"""Finish a hard-surface part from maps baked off its own geometry.

    python scripts/hard_surface_finish.py source.glb finished.glb receipt.json --textures recipe.json
    rac run-stage hard-surface-finish --source source.glb --textures recipe.json --output finished.glb --report receipt.json

The source is a static mesh whose geometry is already approved and whose UV0 is unique. The recipe
binds that mesh and a map set written by the bake-surface-maps stage, and says what each baked class
is made of. Geometry, UVs and accessors are carried over untouched; the part leaves with one material
holding a base colour, a tangent-space normal and a packed occlusion / roughness / metal map.

The recipe (schema rac.hard-surface-recipe.v1):

    source_sha256, maps (path beside the recipe), maps_sha256
    classes     {baked class name: class in the profile}; every baked class must be assigned
    profile     optional path beside the recipe; default profiles/materials/hard-surface-ironworks.json
    seed        optional integer; two parts with different seeds never wear alike
    tread       optional, for tread_plate classes: {"pattern", "wheel_lines_y_m", "stamp": {"text", "origin_m"}}
    fasteners   optional [[x, y, z, nx, ny, nz, radius], ...] in the maps' space; default is what the bake found
    encode      "png" (default, lossless) or "review" (JPEG colour and mask, lossless normal, for a size ceiling)
    masters     true to also write the three maps as PNG files beside the output
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler import hard_surface as hs  # noqa: E402
from reference_asset_compiler.polish_glb import read_glb, write_glb  # noqa: E402

DEFAULT_PROFILE = ROOT / "profiles" / "materials" / "hard-surface-ironworks.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(array, kind, mode):
    """One map as bytes. Review mode keeps the normal lossless: block edges there show in every reflection,
    and colour is JPEG at full chroma resolution because subsampled chroma turns rust on dark iron into squares."""
    out = io.BytesIO()
    if mode == "review" and kind != "normal":
        Image.fromarray(array).save(out, "JPEG", quality=93, subsampling=0, optimize=True)
        return out.getvalue(), "image/jpeg"
    Image.fromarray(array).save(out, "PNG", compress_level=6)
    return out.getvalue(), "image/png"


def embed(source, images, name):
    """The source GLB with one material made of `images`; every primitive is given it and nothing else moves."""
    doc, binary = read_glb(source)
    blob = bytearray(binary)
    for key in ("materials", "textures", "images", "samplers"):
        doc.pop(key, None)
    doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
    doc["images"], doc["textures"] = [], []
    index = {}
    for kind, (payload, mime) in images.items():
        blob.extend(b"\0" * (-len(blob) % 4))
        doc.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(payload)})
        blob.extend(payload)
        doc["images"].append({"bufferView": len(doc["bufferViews"]) - 1, "mimeType": mime, "name": f"{name}_{kind}"})
        doc["textures"].append({"sampler": 0, "source": len(doc["images"]) - 1, "name": f"{name}_{kind}"})
        index[kind] = len(doc["textures"]) - 1
    doc["materials"] = [{
        "name": name, "doubleSided": False,
        "pbrMetallicRoughness": {"baseColorTexture": {"index": index["base_color"]}, "metallicRoughnessTexture": {"index": index["orm"]},
                                 "metallicFactor": 1.0, "roughnessFactor": 1.0},
        "normalTexture": {"index": index["normal"], "scale": 1.0},
        "occlusionTexture": {"index": index["orm"], "strength": 1.0},
    }]
    primitives = 0
    for mesh in doc.get("meshes", []):
        for primitive in mesh["primitives"]:
            if "TEXCOORD_0" not in primitive.get("attributes", {}):
                raise hs.HardSurfaceError("every primitive needs UV0; a part with none cannot carry these maps")
            primitive["material"] = 0
            primitives += 1
    if not primitives:
        raise hs.HardSurfaceError("the source holds no mesh")
    blob.extend(b"\0" * (-len(blob) % 4))
    doc["buffers"][0]["byteLength"] = len(blob)
    return write_glb(doc, blob), primitives


def finish(source, output, report, recipe_path):
    began = time.time()
    recipe = json.loads(recipe_path.read_text(encoding="utf-8-sig"))
    if recipe.get("schema") != hs.RECIPE_SCHEMA:
        raise hs.HardSurfaceError(f"recipe schema must be {hs.RECIPE_SCHEMA}")
    raw = source.read_bytes()
    if recipe.get("source_sha256") != sha(raw):
        raise hs.HardSurfaceError("the recipe binds a different source: source_sha256 does not match")
    maps_path = (recipe_path.parent / recipe.get("maps", "")).resolve()
    if not recipe.get("maps") or not maps_path.is_file():
        raise hs.HardSurfaceError("the recipe must name the baked map set beside it (maps)")
    maps_raw = maps_path.read_bytes()
    if recipe.get("maps_sha256") != sha(maps_raw):
        raise hs.HardSurfaceError("the recipe binds a different map set: maps_sha256 does not match")
    mode = recipe.get("encode", "png")
    if mode not in ("png", "review"):
        raise hs.HardSurfaceError('encode is "png" or "review"')
    profile_path = (recipe_path.parent / recipe["profile"]).resolve() if recipe.get("profile") else DEFAULT_PROFILE
    profile_raw = profile_path.read_bytes()
    palette, classes = hs.load_profile(json.loads(profile_raw.decode("utf-8-sig")))
    with np.load(io.BytesIO(maps_raw), allow_pickle=False) as held:
        maps = {key: held[key] for key in held.files}
    if "class_names" in maps:
        maps["class_names"] = [str(n) for n in maps["class_names"]]
    result = hs.paint(maps, recipe, palette, classes, hs.Noise())
    name = "M_" + output.stem
    images = {kind: encode(result[kind], kind, mode) for kind in ("base_color", "normal", "orm")}
    data, primitives = embed(raw, images, name)
    with output.open("xb") as stream:
        stream.write(data)
    receipt = {"schema": hs.RECEIPT_SCHEMA, "source_sha256": sha(raw), "maps_sha256": sha(maps_raw), "recipe_sha256": sha(recipe_path.read_bytes()),
               "profile": profile_path.name, "profile_sha256": sha(profile_raw), "output_sha256": sha(data), "seed": int(recipe.get("seed", 1083)),
               "encode": mode, "primitives": primitives, "material": name,
               "images": {kind: {"mime": mime, "bytes": len(payload), "sha256": sha(payload)} for kind, (payload, mime) in images.items()},
               **result["stats"], "seconds": round(time.time() - began, 1),
               "preserved": "geometry, UVs and accessors are the source's own buffers; only materials and images were replaced"}
    if recipe.get("masters"):
        receipt["masters"] = {}
        for kind, suffix in (("base_color", "BaseColor"), ("normal", "Normal"), ("orm", "ORM")):
            path = output.with_name(f"{output.stem}_{suffix}.png")
            payload, _ = encode(result[kind], kind, "png")
            with path.open("xb") as stream:
                stream.write(payload)
            receipt["masters"][suffix] = {"file": path.name, "sha256": sha(payload)}
    with report.open("x", encoding="utf8") as stream:
        json.dump(receipt, stream, indent=2)
    return receipt


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("source", "output", "report"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--textures", type=Path, required=True, help="the hard-surface recipe")
    args = parser.parse_args(argv)
    paths = [args.source, args.output, args.report, args.textures]
    if len({p.resolve() for p in paths}) != len(paths) or args.output.exists() or args.report.exists():
        parser.error("Choose distinct new output/report paths; prior attempts keep their receipts.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        receipt = finish(args.source, args.output, args.report, args.textures)
    except hs.HardSurfaceError as error:
        raise SystemExit(f"hard-surface-finish refused: {error}")
    print(f"HARD_SURFACE_FINISH_COMPLETE -- {receipt['resolution'][0]} px, {len(receipt['classes'])} classes; the rust has an address now.")


if __name__ == "__main__":
    main(sys.argv[2:] if sys.argv[1:2] == ["--"] else sys.argv[1:])
