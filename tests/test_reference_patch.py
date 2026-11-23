"""Exercise registered mapping, occlusion, scope and immutable transport data."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compress_textures import read_glb
from project_reference_patch import fill_unseen, prepare_view, project_patch, sample
from surface_atlas import read_image
from test_material_sweep import swatch


def test_large_projection_preserves_samples_across_opencv_row_limit():
    pixels = np.arange(64 * 64 * 3, dtype="f").reshape(64, 64, 3)
    coordinates = np.tile([[0.25, 0.25], [0.75, 0.75]], (20000, 1))[:32768]
    expected = sample(pixels, coordinates[:2])
    actual = sample(pixels, coordinates)
    np.testing.assert_array_equal(actual, np.tile(expected, (16384, 1)))


def test_surface_gap_fill_is_bounded_and_never_invents_an_unobserved_donor():
    position = np.array([[0, 0, 0], [0, 0.001, 0], [0, 0.1, 0]])
    color = np.array([[180., 100, 60], [224, 224, 224], [0, 0, 0]])
    weight = np.array([1., 0, 0])
    actual, confidence = fill_unseen(position, color, weight, 0.003)
    np.testing.assert_array_equal(actual[1], color[0])
    np.testing.assert_array_equal(confidence, [1, 1, 0])
    np.testing.assert_array_equal(actual[2], color[2])
    _, empty = fill_unseen(position, color, weight * 0, 1)
    assert not empty.any()
    np.testing.assert_array_equal(weight, [1, 0, 0])


def repair_fixture(tmp_path):
    source, _ = swatch(tmp_path)
    image = tmp_path / "reference.png"
    Image.new("RGB", (64, 64), (200, 80, 40)).save(image)
    guide = tmp_path / "guide.npz"
    np.savez_compressed(guide, hit=np.zeros((64, 64), "i"), depth=np.zeros((64, 64), "f"))
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    recipe = dict(
        schema="reference-asset-compiler.reference-patch-recipe.v1",
        source_sha256=sha(source),
        acquisition_provenance="Synthetic registered planar acquisition for mechanical test only",
        patches=[
            dict(
                material="Hand-painted",
                size=64,
                feather_m=0,
                bounds=[[-0.001, -0.001, -0.001], [0.006, 0.013, 0.001]],
                response=dict(roughness=0.8, metallic=0, specular=0.4),
                views=[
                    dict(
                        image=image.name,
                        image_sha256=sha(image),
                        guide=guide.name,
                        guide_sha256=sha(guide),
                        center=[0.006, 0.006, 0],
                        axis=[0, 0, 1],
                        width=0.012,
                        relief_m=0,
                    )
                ],
            )
        ],
    )
    config = tmp_path / "patch.json"
    config.write_text(json.dumps(recipe))
    return source, config


def test_opt_in_foreground_guard_fills_neutral_spill_without_changing_camera_mask(tmp_path):
    _, config = repair_fixture(tmp_path)
    view = json.loads(config.read_text())["patches"][0]["views"][0]
    path = tmp_path / view["image"]
    pixels = np.full((64, 64, 3), 224, dtype=np.uint8)
    pixels[8:56, 8:56] = [180, 110, 65]
    Image.fromarray(pixels).save(path)
    view["image_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    original = prepare_view(tmp_path, view)
    guarded = prepare_view(tmp_path, {**view, "foreground_chroma_min": 12})
    np.testing.assert_array_equal(guarded["mask"], original["mask"])
    np.testing.assert_array_equal(guarded["depth"], original["depth"])
    assert original["image"][0, 0].tolist() == [224, 224, 224]
    assert np.all(guarded["image"] == [180, 110, 65])
    with pytest.raises(ValueError, match="No chromatic foreground"):
        prepare_view(tmp_path, {**view, "foreground_chroma_min": 200})
    with pytest.raises(ValueError, match="must be in"):
        prepare_view(tmp_path, {**view, "foreground_chroma_min": -1})


def test_scoped_texels_and_replay_keep_transport(tmp_path):
    source, config = repair_fixture(tmp_path)
    outputs = [tmp_path / f"candidate{i}.glb" for i in range(2)]
    for i, output in enumerate(outputs):
        project_patch(source, output, tmp_path / f"receipt{i}.json", config)
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    before, old = read_glb(source.read_bytes())
    after, new = read_glb(outputs[0].read_bytes())
    assert new.startswith(old)
    for key in ["meshes", "nodes", "accessors", "scenes"]:
        assert before[key] == after[key]
    assert before["materials"][1] == after["materials"][1]
    pbr = after["materials"][0]["pbrMetallicRoughness"]
    color = np.asarray(read_image(after, new, pbr["baseColorTexture"]))
    assert np.max(abs(color[8:56, 8:28, :3].astype(int) - [200, 80, 40])) == 0
    expected = np.rint((1.055 * np.array([0.2, 0.3, 0.4]) ** (1 / 2.4) - 0.055) * 255)
    assert np.max(abs(color[8:56, 36:56, :3].astype(int) - expected)) <= 1
    response = np.asarray(read_image(after, new, pbr["metallicRoughnessTexture"]))
    assert set(response[8:56, 8:28, 2].flat) == {0}
    assert set(response[8:56, 36:56, 2].flat) == {255}


@pytest.mark.parametrize("fault", ["source", "reference", "guide", "occluded", "material"])
def test_invalid_or_invisible_input_cannot_deliver(tmp_path, fault):
    source, config = repair_fixture(tmp_path)
    data = json.loads(config.read_text())
    patch = data["patches"][0]
    if fault == "source":
        data["source_sha256"] = "0" * 64
    elif fault == "reference":
        patch["views"][0]["image_sha256"] = "0" * 64
    elif fault == "guide":
        patch["views"][0]["guide_sha256"] = "0" * 64
    elif fault == "material":
        patch["material"] = "missing material"
    else:
        guide = tmp_path / "guide.npz"
        np.savez_compressed(guide, hit=np.zeros((64, 64), "i"), depth=np.ones((64, 64), "f"))
        patch["views"][0]["guide_sha256"] = hashlib.sha256(guide.read_bytes()).hexdigest()
    config.write_text(json.dumps(data))
    output = tmp_path / "output.glb"
    with pytest.raises(ValueError):
        project_patch(source, output, tmp_path / "receipt.json", config)
    assert not output.exists() and not (tmp_path / "receipt.json").exists()
