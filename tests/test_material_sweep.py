"""Exercise real exported texels, unchanged mesh bytes, and a reproducible second bake."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compress_textures import read_glb, write_glb
from material_sweep import starter, sweep
from surface_atlas import read_image


def swatch(directory):
    # A 12 mm square has enough texels at 64 px for the woven relief to survive.
    arrays = [
        np.array(a, "<f4")
        for a in (
            [[0, 0, 0], [0.012, 0, 0], [0.012, 0.012, 0], [0, 0.012, 0]],
            [[0, 0, 1]] * 4,
            [[0, 1], [1, 1], [1, 0], [0, 0]],
        )
    ]
    arrays.append(np.array([0, 1, 2, 0, 2, 3], "<u2"))
    blob = bytearray()
    views = []
    accessors = []
    for i, a in enumerate(arrays):
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": a.nbytes})
        accessors.append(
            {
                "bufferView": i,
                "type": ["VEC3", "VEC3", "VEC2", "SCALAR"][i],
                "componentType": 5123 if i == 3 else 5126,
                "count": len(a),
            }
        )
        blob.extend(a.tobytes())
    doc = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(blob)}],
        "accessors": accessors,
        "bufferViews": views,
        "materials": [
            {
                "name": "Hand-painted",
                "pbrMetallicRoughness": {"baseColorFactor": [0.2, 0.3, 0.4, 1]},
            },
            {"name": "Glass", "extensions": {"KHR_materials_ior": {"ior": 1.46}}},
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "material": 0,
                    }
                ]
            }
        ],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    src = directory / "swatch.glb"
    src.write_bytes(write_glb(doc, bytes(blob)))
    mask = directory / "labels.png"
    labels = np.ones((64, 64), np.uint8)
    labels[:, 32:] = 2
    Image.fromarray(labels).save(mask)
    cfg = directory / "assign.json"
    starter(src, cfg)
    data = json.loads(cfg.read_text())
    data["materials"]["Hand-painted"] = {
        "mask": mask.name,
        "size": 64,
        "mask_sha256": hashlib.sha256(mask.read_bytes()).hexdigest(),
        "labels": {"1": "canvas", "2": "worn_steel"},
    }
    cfg.write_text(json.dumps(data))
    return src, cfg


def test_encoded_channels_and_replay(tmp_path):
    src, cfg = swatch(tmp_path)
    targets = [tmp_path / f"run{i}.glb" for i in range(2)]
    for i, target in enumerate(targets):
        sweep(src, target, tmp_path / f"run{i}.json", cfg)
    assert targets[0].read_bytes() == targets[1].read_bytes()
    d, b = read_glb(targets[0].read_bytes())
    original, old = read_glb(src.read_bytes())
    assert (
        b.startswith(old) and d["meshes"] == original["meshes"] and d["nodes"] == original["nodes"]
    )
    assert d["materials"][1] == original["materials"][1]
    mat = d["materials"][0]
    pbr = mat["pbrMetallicRoughness"]
    mr = pbr["metallicRoughnessTexture"]
    assert mat["extensions"]["KHR_materials_specular"]["specularTexture"] == mr
    assert (
        pbr["baseColorFactor"]
        == original["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]
    )
    pixels = np.asarray(read_image(d, b, mr))
    left, right = pixels[:, :32], pixels[:, 32:]
    assert set(left[:, :, 2].flat) == {0} and set(right[:, :, 2].flat) == {round(0.94 * 255)}
    assert left[:, :, 1].min() > right[:, :, 1].max()
    assert set(left[:, :, 3].flat) == {round(0.48 * 255)} and set(right[:, :, 3].flat) == {255}
    n = np.asarray(read_image(d, b, mat["normalTexture"])).astype(float) / 127.5 - 1
    assert np.all(np.abs(np.linalg.norm(n, axis=-1) - 1) < 0.007) and np.std(n[:, :32, 0]) > 0.015


@pytest.mark.parametrize("fault", ["stale_source", "stale_mask", "missing_label", "all_kept"])
def test_rejects_bad_assignments_without_delivering_a_model(tmp_path, fault):
    src, cfg = swatch(tmp_path)
    data = json.loads(cfg.read_text())
    slot = data["materials"]["Hand-painted"]
    if fault == "stale_source":
        data["source_sha256"] = "a" * 64
    elif fault == "stale_mask":
        slot["mask_sha256"] = "b" * 64
    elif fault == "missing_label":
        del slot["labels"]["2"]
    else:
        data["materials"]["Hand-painted"] = {"keep": True}
    cfg.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        sweep(src, tmp_path / "output.glb", tmp_path / "receipt.json", cfg)
    assert not (tmp_path / "output.glb").exists() and not (tmp_path / "receipt.json").exists()


def test_scene_target_changes_steel_only_and_pins_the_target(tmp_path):
    src, cfg = swatch(tmp_path)
    original = tmp_path / "studio.glb"
    sweep(src, original, tmp_path / "studio.json", cfg)
    target_cfg = tmp_path / "scene-assign.json"
    starter(src, target_cfg, "framewright-scene")
    assignment = json.loads(target_cfg.read_text())
    assignment["materials"] = json.loads(cfg.read_text())["materials"]
    target_cfg.write_text(json.dumps(assignment))
    finish = tmp_path / "scene.glb"
    receipt = sweep(src, finish, tmp_path / "scene.json", target_cfg)
    assert receipt["target_sha256"] == assignment["target_sha256"]

    def maps(path):
        doc, binary = read_glb(path.read_bytes())
        mat = doc["materials"][0]
        response = mat["pbrMetallicRoughness"]["metallicRoughnessTexture"]
        return np.asarray(read_image(doc, binary, response)), np.asarray(
            read_image(doc, binary, mat["normalTexture"])
        )

    studio, normal = maps(original)
    scene, scene_normal = maps(finish)
    assert np.array_equal(scene_normal, normal)
    assert np.array_equal(scene[:, :32], studio[:, :32])  # Woven canvas.
    assert np.all(scene[:, 32:, 1] > studio[:, 32:, 1])
    assert np.all(scene[:, 32:, 2] == round(0.67 * 255))
    assert np.array_equal(scene[:, 32:, 3], studio[:, 32:, 3])
    assignment["target_sha256"] = "0" * 64
    target_cfg.write_text(json.dumps(assignment))
    with pytest.raises(ValueError, match="target must match"):
        sweep(src, tmp_path / "stale.glb", tmp_path / "stale.json", target_cfg)
