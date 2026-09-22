"""Clip selection must preserve the model payload and refuse ambiguous requests."""

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler.animation_export import select_animations


def model_with_two_clips():
    document = {"asset": {"version": "2.0"},
                "animations": [{"name": "Idle", "channels": [{"sampler": 0}]},
                               {"name": "Wave", "channels": [{"sampler": 1}]}],
                "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}
    encoded = json.dumps(document).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    binary = struct.pack("<II", 4, 0x004E4942) + b"BONE"
    return (struct.pack("<III", 0x46546C67, 2, 20 + len(encoded) + len(binary))
            + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + binary)


def split_model(value):
    assert struct.unpack_from("<I", value, 8)[0] == len(value)
    length = struct.unpack_from("<I", value, 12)[0]
    return json.loads(value[20:20 + length]), value[20 + length:]


def test_clip_selection_preserves_the_binary_chunk_and_model_description():
    source = model_with_two_clips()
    original, original_binary = split_model(source)
    for names in ([], ["Wave"], ["Idle", "Wave"]):
        output, binary = split_model(select_animations(source, names))
        assert binary == original_binary
        assert output["meshes"] == original["meshes"]
        assert [item["name"] for item in output.get("animations", [])] == names
    assert source == model_with_two_clips()


def test_clip_selection_rejects_missing_or_duplicate_names():
    source = model_with_two_clips()
    for names in (["Ghost"], ["Idle", "Idle"]):
        with pytest.raises(ValueError):
            select_animations(source, names)
    with pytest.raises(ValueError):
        select_animations(b"not a model", [])
    malformed = model_with_two_clips().replace(b'"animations"', b'"animationX"')
    # Replacing a key without rebuilding the header is invalid GLB; the
    # command refuses it instead of leaving an export that looks successful.
    with pytest.raises(ValueError):
        select_animations(malformed, ["Idle"])
