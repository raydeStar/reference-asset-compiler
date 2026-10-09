"""freeze_character_inputs.py: a bundle and a recipe the rebuild runner accepts."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import freeze_character_inputs as freeze  # noqa: E402


def sources(tmp_path, skip=()):
    folder = tmp_path / "front-end"
    folder.mkdir()
    pairs = []
    for name in freeze.REQUIRED + ("rig-landmarks.json", "head-left.png"):
        if name in skip:
            continue
        path = folder / ("src-" + name)
        path.write_bytes(name.encode() * 3)
        pairs.append(f"{name}={path}")
    oral = folder / "oral"
    (oral / "teeth").mkdir(parents=True)
    (oral / "teeth/teeth.obj").write_text("v 0 0 0\n")
    (oral / "tongue.obj").write_text("v 1 0 0\n")
    pairs.append(f"makehuman={oral}")
    template = tmp_path / "template-recipe.json"
    template.write_text(json.dumps({"schema": "s", "character": "profiles/characters/ennix.json",
                                    "inputs": {"old.npz": {}}, "groom": {"seed": 7},
                                    "groom_note": "the other character's", "samples": 32}))
    return pairs, template


def freeze_args(tmp_path, pairs, template, *extra):
    return [*pairs, "--bundle", str(tmp_path / "bundle"), "--recipe-from", str(template),
            "--recipe-out", str(tmp_path / "recipe.json"), "--character", "profiles/characters/ennix.json", *extra]


def test_every_input_is_copied_and_hashed_as_the_runner_checks(tmp_path):
    pairs, template = sources(tmp_path)
    assert freeze.main(freeze_args(tmp_path, pairs, template)) == 0
    recipe = json.loads((tmp_path / "recipe.json").read_text())
    assert recipe["character"] == "profiles/characters/ennix.json"
    assert recipe["groom"] == {"seed": 7} and recipe["samples"] == 32
    assert "groom_note" not in recipe
    assert "makehuman/teeth/teeth.obj" in recipe["inputs"] and "makehuman/tongue.obj" in recipe["inputs"]
    assert "old.npz" not in recipe["inputs"]
    # rebuild_character.py's own check: every listed file exists with its hash.
    for name, info in recipe["inputs"].items():
        data = (tmp_path / "bundle" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info["sha256"]
        assert len(data) == info["bytes"]


def test_a_missing_input_is_refused_before_anything_is_copied(tmp_path):
    pairs, template = sources(tmp_path, skip=("placement.json",))
    with pytest.raises(SystemExit):
        freeze.main(freeze_args(tmp_path, pairs, template))
    assert not (tmp_path / "bundle").exists()


def test_rig_landmarks_may_be_left_to_the_build(tmp_path):
    pairs, template = sources(tmp_path, skip=("rig-landmarks.json",))
    with pytest.raises(SystemExit):
        freeze.main(freeze_args(tmp_path, pairs, template))
    assert freeze.main(freeze_args(tmp_path, pairs, template, "--rig-landmarks-optional")) == 0
    assert "rig-landmarks.json" not in json.loads((tmp_path / "recipe.json").read_text())["inputs"]


def test_an_existing_bundle_or_recipe_is_never_overwritten(tmp_path):
    pairs, template = sources(tmp_path)
    (tmp_path / "bundle").mkdir()
    (tmp_path / "bundle/old.txt").write_text("evidence")
    with pytest.raises(SystemExit):
        freeze.main(freeze_args(tmp_path, pairs, template))
    (tmp_path / "bundle/old.txt").unlink()
    (tmp_path / "recipe.json").write_text("{}")
    with pytest.raises(SystemExit):
        freeze.main(freeze_args(tmp_path, pairs, template))
