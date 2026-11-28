"""Packing must preserve live specular images and sparse morph payloads byte for byte."""

import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prune_glb_payload import prune


def fixture():
    chunks = [
        b"old paint",
        b"position bytes",
        b"indices",
        b"morph deltas",
        b"active RGBA alpha",
        b"abandoned normal",
    ]
    binary = b"".join(chunks)
    offset = 0
    views = []
    for chunk in chunks:
        views.append(dict(buffer=0, byteOffset=offset, byteLength=len(chunk)))
        offset += len(chunk)
    doc = dict(
        asset={"version": "2.0"},
        buffers=[{"byteLength": len(binary)}],
        bufferViews=views,
        accessors=[
            dict(
                bufferView=1,
                componentType=5126,
                type="VEC3",
                count=1,
                sparse={
                    "count": 1,
                    "indices": {"bufferView": 2, "componentType": 5121},
                    "values": {"bufferView": 3},
                },
            )
        ],
        images=[{"bufferView": i, "mimeType": "image/png"} for i in [0, 4, 5]],
        textures=[{"source": i} for i in range(3)],
        materials=[
            {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
            {"extensions": {"KHR_materials_specular": {"specularTexture": {"index": 1}}}},
        ],
        meshes=[{"primitives": [{"attributes": {"POSITION": 0}, "material": 1}]}],
        nodes=[{"mesh": 0}],
        skins=[{"joints": [0]}],
        animations=[],
        scenes=[{"nodes": [0]}],
        extensionsUsed=["KHR_materials_specular"],
    )
    return doc, binary


def test_live_alpha_and_sparse_morph_bytes_are_retained():
    doc, binary = fixture()
    before = copy.deepcopy(doc)
    packed, result, proof = prune(doc, binary)
    assert doc == before and proof["images_before_after"] == [3, 1]
    assert (
        packed["materials"][0]["extensions"]["KHR_materials_specular"]["specularTexture"]["index"]
        == 0
    )
    assert packed["accessors"][0]["sparse"]["indices"]["bufferView"] == 1
    assert packed["accessors"][0]["sparse"]["values"]["bufferView"] == 2
    for source_index, target_index in [(1, 0), (2, 1), (3, 2), (4, 3)]:
        old = doc["bufferViews"][source_index]
        new = packed["bufferViews"][target_index]
        assert (
            binary[old["byteOffset"] : old["byteOffset"] + old["byteLength"]]
            == result[new["byteOffset"] : new["byteOffset"] + new["byteLength"]]
        )
    for key in ["nodes", "skins", "animations", "scenes"]:
        assert packed[key] == doc[key]


@pytest.mark.parametrize("fault", ["extension", "external", "truncated"])
def test_unproven_resource_layout_is_rejected(fault):
    doc, binary = fixture()
    if fault == "extension":
        doc["extensionsUsed"].append("VENDOR_arbitrary_texture_reference")
    elif fault == "external":
        doc["buffers"][0]["uri"] = "external.bin"
    else:
        binary = binary[:10]
    with pytest.raises(ValueError):
        prune(doc, binary)
