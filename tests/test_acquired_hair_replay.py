"""Acquisition lineage and displacement continuity guard the hair replay boundary."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hair_replay", ROOT / "scripts/replay_acquired_hair.py")
hair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hair)


def recipe_at(tmp_path):
    files = {}
    for name in hair.REQUIRED:
        path = tmp_path / name
        path.write_text(name)
        files[name] = path
    files["acquisition_receipt"].write_text(json.dumps({
        "schema": "reference-asset-compiler.geometry-candidate.v1", "ok": True,
        "candidate_sha256": hair.sha(files["scan"]),
        "image_sha256": hair.sha(files["conditioning_image"]),
    }))
    files["extraction_receipt"].write_text(json.dumps({"source_sha256": hair.sha(files["scan"])}))
    recipe = {"schema": "reference-asset-compiler.acquired-hair-recipe.v1",
              "inputs": {k: {"path": p.name, "sha256": hair.sha(p)} for k, p in files.items()},
              "extraction_review": "Delegated reviewer accepted the isolated extraction",
              "component_scope": "hair only"}
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(recipe))
    return path, recipe, files


def test_frozen_input_tampering_stops_before_execution(tmp_path):
    path, _, files = recipe_at(tmp_path)
    hair.load_recipe(path)
    files["head"].write_text("changed head")
    with pytest.raises(ValueError, match="Stale head"):
        hair.load_recipe(path)


def test_a_receipt_for_another_conditioning_image_is_rejected(tmp_path):
    path, recipe, files = recipe_at(tmp_path)
    receipt = json.loads(files["acquisition_receipt"].read_text())
    receipt["image_sha256"] = "0" * 64
    files["acquisition_receipt"].write_text(json.dumps(receipt))
    recipe["inputs"]["acquisition_receipt"]["sha256"] = hair.sha(files["acquisition_receipt"])
    path.write_text(json.dumps(recipe))
    with pytest.raises(ValueError, match="bind the AI geometry"):
        hair.load_recipe(path)


@pytest.mark.parametrize("settings", [{"erosion_m": .02}, {"voxel_m": float("nan")},
                                     {"triangles": 1000.5}, {"silent_retry": 1}])
def test_invalid_or_unknown_cleanup_settings_stop_before_execution(tmp_path, settings):
    path, recipe, _ = recipe_at(tmp_path)
    recipe["settings"] = settings
    path.write_text(json.dumps(recipe))
    with pytest.raises(ValueError):
        hair.load_recipe(path)


def test_smoothing_does_not_move_disconnected_locks_or_isolated_vertices():
    verts = np.zeros((7, 3))
    tris = np.array([[0, 1, 2], [3, 4, 5]])
    delta = np.zeros_like(verts)
    delta[:3, 2] = .01
    delta[6] = [1, 2, 3]
    result = hair.smooth_displacements(verts, tris, delta, 24)
    assert np.allclose(result[:3, 2], .01)
    assert np.array_equal(result[3:6], delta[3:6])
    assert np.array_equal(result[6], delta[6])


def test_smoothing_reduces_a_local_clearance_spike_without_changing_input():
    verts = np.zeros((3, 3))
    tris = np.array([[0, 1, 2]])
    delta = np.array([[0., 0., .03], [0., 0., 0.], [0., 0., 0.]])
    result = hair.smooth_displacements(verts, tris, delta, 24)
    assert np.ptp(result[:, 2]) < 1e-8
    assert result[:, 2].sum() == pytest.approx(.03)
    assert delta[0, 2] == .03 and delta[1, 2] == 0
