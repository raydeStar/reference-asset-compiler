"""A new character's approved face must not inherit another character's retouch."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from rebuild_character import frozen_head_mode


def bound_head(tmp_path):
    image = tmp_path / 'head-front.png'
    image.write_bytes(b'source-bound facial image')
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    (tmp_path / 'head.json').write_text(json.dumps({'picture': {'image_sha256': digest}}))
    (tmp_path / 'front-landmarks.json').write_text(json.dumps({'image_sha256': digest}))
    return {'head_finish': {'mode': 'frozen'}}


def test_legacy_recipe_keeps_its_existing_path(tmp_path):
    assert frozen_head_mode({}, tmp_path) is False


def test_frozen_head_requires_the_actual_identity_reference(tmp_path):
    recipe = bound_head(tmp_path)
    assert frozen_head_mode(recipe, tmp_path) is True
    (tmp_path / 'head-front.png').write_bytes(b'different face')
    with pytest.raises(ValueError, match='exact facial guidance'):
        frozen_head_mode(recipe, tmp_path)


def test_frozen_head_rejects_stale_landmarks_and_extra_retouch(tmp_path):
    recipe = bound_head(tmp_path)
    (tmp_path / 'front-landmarks.json').write_text(json.dumps({'image_sha256': 'stale'}))
    with pytest.raises(ValueError, match='exact facial guidance'):
        frozen_head_mode(recipe, tmp_path)
    recipe = bound_head(tmp_path)
    recipe['face_paint'] = {'stubble_strength': .2}
    with pytest.raises(ValueError, match='face_paint'):
        frozen_head_mode(recipe, tmp_path)


def test_unknown_head_mode_fails_closed(tmp_path):
    with pytest.raises(ValueError, match='legacy or frozen'):
        frozen_head_mode({'head_finish': {'mode': 'typo'}}, tmp_path)
