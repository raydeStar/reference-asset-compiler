"""Discard unused material/image payloads without re-encoding active textures or geometry.

Usage: python scripts/prune_glb_payload.py source.glb new.glb receipt.json
Replaced bake images remain in the working source; the transport keeps only
reachable material textures. Accessor indices, animation and rig data stay intact.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from compress_textures import read_glb, write_glb


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def texture_slots(materials):
    for obj in walk(materials):
        for name, value in obj.items():
            if name.endswith("Texture") and isinstance(value, dict) and "index" in value:
                yield value


def prune(document, binary):
    """Return a compact document, binary and proof of byte-preserved reachable views."""
    allowed = {
        "KHR_materials_specular",
        "KHR_materials_clearcoat",
        "KHR_materials_ior",
        "KHR_materials_transmission",
        "KHR_materials_volume",
        "KHR_materials_sheen",
        "KHR_materials_emissive_strength",
        "KHR_materials_unlit",
        "KHR_texture_transform",
        "KHR_mesh_quantization",
    }
    unsupported = set(document.get("extensionsUsed", [])) - allowed
    if unsupported:
        raise ValueError(
            f"Unknown extension resource references need an explicit route: {sorted(unsupported)}"
        )
    if len(document.get("buffers", [])) != 1 or document["buffers"][0].get("uri"):
        raise ValueError("Expected one embedded buffer")
    doc = copy.deepcopy(document)
    used_materials = sorted(
        {
            pr["material"]
            for mesh in doc.get("meshes", [])
            for pr in mesh["primitives"]
            if "material" in pr
        }
    )
    materials = {old: new for new, old in enumerate(used_materials)}
    doc["materials"] = [doc["materials"][old] for old in used_materials]
    for mesh in doc.get("meshes", []):
        for pr in mesh["primitives"]:
            if "material" in pr:
                pr["material"] = materials[pr["material"]]
    used_textures = sorted({slot["index"] for slot in texture_slots(doc["materials"])})
    textures = {old: new for new, old in enumerate(used_textures)}
    doc["textures"] = [doc.get("textures", [])[old] for old in used_textures]
    for slot in texture_slots(doc["materials"]):
        slot["index"] = textures[slot["index"]]
    if any("source" not in tex or tex.get("extensions") for tex in doc["textures"]):
        raise ValueError("This packer requires core image sources")
    used_images = sorted({tex["source"] for tex in doc["textures"]})
    images = {old: new for new, old in enumerate(used_images)}
    doc["images"] = [doc.get("images", [])[old] for old in used_images]
    if any("bufferView" not in img or "uri" in img for img in doc["images"]):
        raise ValueError("Expected embedded images")
    for tex in doc["textures"]:
        tex["source"] = images[tex["source"]]
    used_views = sorted({obj["bufferView"] for obj in walk(doc) if "bufferView" in obj})
    views = {old: new for new, old in enumerate(used_views)}
    old_views = doc["bufferViews"]
    buffer = bytearray()
    copied = []
    for old in used_views:
        view = copy.deepcopy(old_views[old])
        if view.get("buffer", 0) != 0 or view.get("extensions"):
            raise ValueError("Expected ordinary embedded buffer views")
        start = view.get("byteOffset", 0)
        data = binary[start : start + view["byteLength"]]
        if len(data) != view["byteLength"]:
            raise ValueError("Truncated source buffer view")
        buffer.extend(b"\0" * (-len(buffer) % 4))
        view["byteOffset"] = len(buffer)
        buffer.extend(data)
        copied.append(view)
    for obj in walk(doc):
        if "bufferView" in obj:
            obj["bufferView"] = views[obj["bufferView"]]
    doc["bufferViews"] = copied
    doc["buffers"][0]["byteLength"] = len(buffer)
    for old, new in views.items():
        before, after = document["bufferViews"][old], copied[new]
        source = binary[
            before.get("byteOffset", 0) : before.get("byteOffset", 0) + before["byteLength"]
        ]
        result = buffer[after["byteOffset"] : after["byteOffset"] + after["byteLength"]]
        if source != result:
            raise AssertionError("Reachable payload changed during packing")
    for name in ("skins", "animations", "nodes", "scenes"):
        if doc.get(name) != document.get(name):
            raise AssertionError(f"{name} changed during packing")
    return (
        doc,
        bytes(buffer),
        {
            "materials_before_after": [len(document.get("materials", [])), len(doc["materials"])],
            "images_before_after": [len(document.get("images", [])), len(doc["images"])],
            "buffer_views_before_after": [len(document["bufferViews"]), len(copied)],
            "all_retained_buffer_views_byte_identical": True,
            "active_images_reencoded": False,
            "accessor_indices_and_rig_and_animation_retained": True,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if len({p.resolve() for p in (args.source, args.output, args.report)}) != 3:
        raise ValueError("Source, output and receipt must have distinct paths")
    if args.output.exists() or args.report.exists():
        raise ValueError("Keep earlier candidates; choose new output paths")
    raw = args.source.read_bytes()
    doc, binary = read_glb(raw)
    packed, buffer, proof = prune(doc, binary)
    result = write_glb(packed, buffer)
    proof.update(
        schema="rac.glb-payload-prune.v1",
        source_sha256=hashlib.sha256(raw).hexdigest(),
        output_sha256=hashlib.sha256(result).hexdigest(),
        bytes_before_after=[len(raw), len(result)],
        visual_approval="unchanged appearance expected; consumer verification still required",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(result)
    with args.report.open("x", encoding="utf8") as stream:
        json.dump(proof, stream, indent=2)
    print("GLB_PAYLOAD_PRUNED -- the travelling trunk has shed its abandoned wardrobes.")


if __name__ == "__main__":
    main()
