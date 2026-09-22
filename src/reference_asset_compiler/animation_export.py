"""Select glTF animation clips without rebaking a model or touching its skin."""

from __future__ import annotations

import json
import struct


_MAGIC = 0x46546C67
_JSON = 0x4E4F534A


def select_animations(source: bytes, selected: list[str]) -> bytes:
    """Return a GLB with exactly the named animations, keeping other chunks byte-for-byte."""
    if len(source) < 20:
        raise ValueError("The model is too short to be a GLB")
    magic, version, length = struct.unpack_from("<III", source)
    json_length, kind = struct.unpack_from("<II", source, 12)
    if magic != _MAGIC or version != 2 or length != len(source) or kind != _JSON:
        raise ValueError("Expected a complete GLB 2.0 with a JSON chunk first")
    end = 20 + json_length
    if json_length % 4 or end > len(source):
        raise ValueError("The GLB JSON chunk is truncated or misaligned")
    model = json.loads(source[20:end])
    if not isinstance(model, dict):
        raise ValueError("The GLB JSON chunk must describe an object")
    animations = model.get("animations", [])
    if not isinstance(animations, list):
        raise ValueError("The GLB animations field is invalid")
    if any(not isinstance(item, dict) for item in animations):
        raise ValueError("Every GLB animation must be an object")
    names = [item.get("name") for item in animations]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Every animation must have a unique name before it can be selected")
    if len(selected) != len(set(selected)) or any(name not in names for name in selected):
        raise ValueError("The requested animation names must be unique and present in the GLB")

    kept = [item for item in animations if item["name"] in selected]
    if len(kept) != len(selected):
        raise ValueError("The requested animation set could not be matched")
    if kept:
        model["animations"] = kept
    else:
        model.pop("animations", None)
    encoded = json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    remainder = source[end:]
    total = 20 + len(encoded) + len(remainder)
    return (struct.pack("<III", _MAGIC, version, total)
            + struct.pack("<II", len(encoded), _JSON) + encoded + remainder)
