"""Re-encode a model's textures, without touching anything else about it.

A finished asset is mostly texture. Across one real library: 22 models, 138.8
MB, and almost every byte of it uncompressed PNG. The sword in it carries a
1.7 MB base colour and a 1.2 MB packed roughness map at 2048 square, on a mesh
whose geometry is a fraction of that. The mesh was never the problem.

Two things decide how this is done.

**Colour maps and data maps are not the same thing.** A base colour is looked
at, so perceptual coding is exactly right for it. A roughness, normal or
occlusion map is *read as numbers* by a shader: its resolution can usually drop
well below the colour's without anyone seeing it, but quantisation shows up as
shading artefacts rather than as blur, so it is encoded without chroma
subsampling and its channels are left alone.

**The file is rewritten chunk by chunk rather than opened in a mesh library.**
Every accessor, skin, morph target and animation keeps its index and its
meaning, because none of them are touched: only image bytes move, and the
buffer views that point at them are rewritten around the new sizes. An asset
that came in rigged goes out rigged.

What it refuses: making a file bigger, and dropping an alpha channel something
was relying on. A base colour with real alpha stays in a format that has one,
and says so, rather than arriving opaque in a scene that expected a cutout.

Usage:
  python scripts/compress_textures.py <in.glb> <out.glb> <report.json> \
      [--colour-size 2048] [--data-size 1024] [--quality 90] [--format jpeg]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFile

# Pillow's JPEG writer works a block at a time and gives up with "Suspension
# not allowed here" when one optimised pass will not fit -- which happens on
# exactly the busiest textures, the ones most worth re-encoding. The buffer is
# a few megabytes and only exists while a single image is written.
ImageFile.MAXBLOCK = 32 * 1024 * 1024

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942

# A texture feeding one of these is data: a shader reads its channels as
# numbers. Everything else is looked at.
DATA_SLOTS = ("metallicRoughnessTexture", "normalTexture", "occlusionTexture")

MIME = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--colour-size", type=int, default=2048,
                        help="Longest side for maps that are looked at (0 keeps what came in)")
    parser.add_argument("--data-size", type=int, default=1024,
                        help="Longest side for maps a shader reads as numbers")
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--format", choices=("jpeg", "webp", "png"), default="jpeg",
                        help="jpeg is core glTF and needs no extension; webp is smaller "
                             "but travels as EXT_texture_webp")
    return parser.parse_args(argv)


def read_glb(data: bytes):
    if data[:4] != b"glTF":
        raise ValueError("This is not a GLB: it does not start with the glTF magic.")
    offset, document, binary = 12, None, b""
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8: offset + 8 + length]
        if kind == JSON_CHUNK:
            document = json.loads(chunk)
        elif kind == BIN_CHUNK:
            binary = chunk
        offset += 8 + length + (-length % 4)
    if document is None:
        raise ValueError("This GLB carries no JSON chunk.")
    return document, binary


def write_glb(document: dict, binary: bytes) -> bytes:
    text = json.dumps(document, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary = binary + b"\x00" * (-len(binary) % 4)
    body = struct.pack("<II", len(text), JSON_CHUNK) + text
    if binary:
        body += struct.pack("<II", len(binary), BIN_CHUNK) + binary
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def data_images(document: dict) -> set[int]:
    """Image indices feeding a slot a shader reads as numbers."""
    textures = document.get("textures", [])
    found: set[int] = set()

    def note(slot):
        if not slot or "index" not in slot:
            return
        texture = textures[slot["index"]]
        source = texture.get("source")
        if source is None:
            source = (texture.get("extensions", {})
                      .get("EXT_texture_webp", {}).get("source"))
        if source is not None:
            found.add(source)

    for material in document.get("materials", []):
        note(material.get("pbrMetallicRoughness", {}).get("metallicRoughnessTexture"))
        for slot in DATA_SLOTS:
            note(material.get(slot))
    return found


def normal_images(document: dict) -> set[int]:
    """Images used as normals, which are the least forgiving of all."""
    textures = document.get("textures", [])
    found: set[int] = set()
    for material in document.get("materials", []):
        slot = material.get("normalTexture")
        if slot and "index" in slot:
            source = textures[slot["index"]].get("source")
            if source is not None:
                found.add(source)
    return found


def carries_alpha(image: Image.Image) -> bool:
    """Whether anything is actually relying on this image's alpha channel."""
    if image.mode not in ("RGBA", "LA", "PA"):
        return False
    alpha = np.asarray(image.convert("RGBA"))[..., 3]
    return bool((alpha < 250).mean() > 0.001)


def psnr(before: Image.Image, after: Image.Image) -> float:
    """How much was lost, measured against the original at its own size.

    Resized back before comparing, so this is the whole loss a viewer would
    see -- the resolution drop included -- rather than only the codec's part.
    """
    original = np.asarray(before.convert("RGB"), dtype=np.float32)
    restored = np.asarray(after.convert("RGB").resize(before.size, Image.LANCZOS),
                          dtype=np.float32)
    error = float(np.mean((original - restored) ** 2))
    if error <= 1e-9:
        return float("inf")
    return float(20.0 * np.log10(255.0) - 10.0 * np.log10(error))


def encode(image: Image.Image, fmt: str, quality: int, longest: int, keep_alpha: bool):
    """One image, re-encoded. Returns the bytes, the format used, and its size."""
    working = image
    if longest and max(working.size) > longest:
        scale = longest / max(working.size)
        working = working.resize(
            (max(1, round(working.width * scale)), max(1, round(working.height * scale))),
            Image.LANCZOS)

    chosen = fmt
    if keep_alpha and fmt == "jpeg":
        # JPEG has no alpha. Something relying on a cutout would arrive opaque,
        # so the format gives way rather than the picture.
        chosen = "png"

    buffer = io.BytesIO()
    if chosen == "jpeg":
        # No chroma subsampling, for both kinds. On a data map the channels are
        # a direction or a set of numbers rather than a colour, and averaging
        # two of them across a 2x2 block is meaningless; on a colour map at
        # this quality it costs little and keeps hard edges hard.
        try:
            working.convert("RGB").save(buffer, format="JPEG", quality=quality,
                                        optimize=True, subsampling=0)
        except OSError:
            # An image too busy for one optimised pass. The unoptimised write
            # is a few percent larger and always succeeds.
            buffer = io.BytesIO()
            working.convert("RGB").save(buffer, format="JPEG", quality=quality,
                                        subsampling=0)
    elif chosen == "webp":
        working.save(buffer, format="WEBP", quality=quality, method=6)
    else:
        working.convert("RGBA" if keep_alpha else "RGB").save(
            buffer, format="PNG", optimize=True)
    return buffer.getvalue(), chosen, working.size


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    args = parse_arguments(argv)

    if not args.source.is_file():
        print("[TEXTURES] FAILED: source does not exist: {0}".format(args.source))
        return 1
    if args.output.exists():
        print("[TEXTURES] FAILED: refusing to overwrite {0}".format(args.output))
        return 1
    if not 1 <= args.quality <= 100:
        print("[TEXTURES] FAILED: quality runs from 1 to 100. Got {0}".format(args.quality))
        return 1

    raw = args.source.read_bytes()
    try:
        document, binary = read_glb(raw)
    except ValueError as problem:
        print("[TEXTURES] FAILED: {0}".format(problem))
        return 1

    images = document.get("images", [])
    if not images:
        print("[TEXTURES] FAILED: this model carries no textures, so there is nothing to re-encode")
        return 1
    views = document.get("bufferViews", [])
    data_slots = data_images(document)
    normals = normal_images(document)

    # Re-encoded bytes per image index, plus what it cost.
    replacements: dict[int, bytes] = {}
    records = []
    for index, entry in enumerate(images):
        view_index = entry.get("bufferView")
        if view_index is None:
            print("[TEXTURES] FAILED: image {0} is not stored in the file's own buffer, "
                  "so this cannot re-encode it".format(index))
            return 1
        view = views[view_index]
        start = view.get("byteOffset", 0)
        original_bytes = binary[start: start + view["byteLength"]]
        try:
            original = Image.open(io.BytesIO(original_bytes))
            original.load()
        except Exception as problem:  # noqa: BLE001 - any unreadable image is the same answer
            print("[TEXTURES] FAILED: image {0} could not be read: {1}".format(index, problem))
            return 1

        is_data = index in data_slots
        longest = args.data_size if is_data else args.colour_size
        keep_alpha = carries_alpha(original)
        encoded, used, size = encode(original, args.format, args.quality, longest, keep_alpha)
        replacements[index] = encoded
        entry["mimeType"] = MIME[used]

        records.append({
            "image": index,
            "name": entry.get("name"),
            "reads_as": "data" if is_data else "colour",
            "was": {"format": (original.format or "?").lower(),
                    "size": list(original.size), "bytes": len(original_bytes)},
            "now": {"format": used, "size": list(size), "bytes": len(encoded)},
            "kept_alpha": keep_alpha,
            "psnr_db": round(psnr(original, Image.open(io.BytesIO(encoded))), 2),
            "note": "normal map: encoded without chroma subsampling, because its "
                    "channels are a direction rather than a colour"
            if index in normals else None,
        })

    # The binary is rebuilt in buffer-view order so that every index a
    # accessor, skin or animation already holds still means what it meant.
    rebuilt = bytearray()
    for view_index, view in enumerate(views):
        owner = next((index for index, entry in enumerate(images)
                      if entry.get("bufferView") == view_index), None)
        payload = (replacements[owner] if owner is not None
                   else binary[view.get("byteOffset", 0):
                               view.get("byteOffset", 0) + view["byteLength"]])
        while len(rebuilt) % 4:
            rebuilt.append(0)
        view["byteOffset"] = len(rebuilt)
        view["byteLength"] = len(payload)
        rebuilt.extend(payload)
    while len(rebuilt) % 4:
        rebuilt.append(0)

    if document.get("buffers"):
        document["buffers"][0]["byteLength"] = len(rebuilt)
    if args.format == "webp" and any(record["now"]["format"] == "webp" for record in records):
        # Declared as used rather than required: a reader that refuses the mime
        # type has nothing else to read, and pretending otherwise would be
        # worse than saying so here.
        used_extensions = document.setdefault("extensionsUsed", [])
        if "EXT_texture_webp" not in used_extensions:
            used_extensions.append("EXT_texture_webp")
        for texture in document.get("textures", []):
            if "source" in texture:
                texture.setdefault("extensions", {})["EXT_texture_webp"] = {
                    "source": texture["source"]}

    written = write_glb(document, bytes(rebuilt))
    if len(written) >= len(raw):
        # Re-encoding that grows the file has done the opposite of its job, and
        # writing it anyway would leave somebody worse off for having run it.
        print("[TEXTURES] FAILED: re-encoding would grow this model from {0:,} to {1:,} bytes. "
              "Its textures are already smaller than this setting produces.".format(
                  len(raw), len(written)))
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(written)

    texture_before = sum(record["was"]["bytes"] for record in records)
    texture_after = sum(record["now"]["bytes"] for record in records)
    worst = min((record["psnr_db"] for record in records), default=float("inf"))
    report = {
        "schema": "reference-asset-compiler.compressed-textures.v1",
        "source": str(args.source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output": str(args.output),
        "output_sha256": hashlib.sha256(written).hexdigest(),
        "settings": {
            "format": args.format, "quality": args.quality,
            "colour_size": args.colour_size, "data_size": args.data_size,
        },
        "file": {
            "before_bytes": len(raw), "after_bytes": len(written),
            "saved_bytes": len(raw) - len(written),
            "saved_share": round(1 - len(written) / len(raw), 4),
        },
        "textures": {
            "before_bytes": texture_before, "after_bytes": texture_after,
            "images": records,
        },
        # The lowest of the per-image figures, because an average would let one
        # ruined map hide behind five untouched ones.
        "worst_psnr_db": None if worst == float("inf") else round(worst, 2),
        "geometry_unchanged": True,
        "uvs_unchanged": True,
        "rig_unchanged": True,
        "how": "Rewritten chunk by chunk. Only image bytes moved; every accessor, "
               "skin, morph target and animation keeps its index and its meaning.",
        "requires_fixed_view_review": True,
        "production_grade": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("[TEXTURES] {0:,} -> {1:,} bytes ({2:.0%} smaller); textures {3:,} -> {4:,}; "
          "worst image {5} dB".format(
              len(raw), len(written), report["file"]["saved_share"],
              texture_before, texture_after, report["worst_psnr_db"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
