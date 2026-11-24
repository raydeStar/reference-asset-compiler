"""auto_part_map.py's rules: which boxes are kept, which mask wins, what counts as bare skin."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import auto_part_map as apm  # noqa: E402

VOCAB = json.loads((ROOT / "profiles/segmentation/humanoid-gear.json").read_text(encoding="utf-8"))


def figure(h=200, w=100):
    """A foreground mask whose bounding box is the whole picture."""
    fg = np.zeros((h, w), bool)
    fg[0, 0] = fg[-1, -1] = True
    return fg


def test_vocabulary_phrases_share_no_word_and_every_part_has_a_prompt():
    seen = {}
    for name, spec in VOCAB["parts"].items():
        assert spec["prompts"], name
        for word in spec["phrase"].split():
            assert word not in seen, f"{name} and {seen.get(word)} share '{word}'"
            seen[word] = name
    assert set(VOCAB["base"]) <= set(VOCAB["parts"])
    assert set(VOCAB["body"]) <= set(VOCAB["parts"])


def test_joint_labels_map_back_to_parts():
    phrases = {n: VOCAB["parts"][n]["phrase"] for n in VOCAB["parts"]}
    assert apm.parts_of("knee pad", phrases) == ["kneepad"]
    assert sorted(apm.parts_of("knee pad holster", phrases)) == ["kneepad", "thigh_pouch"]
    assert apm.parts_of("harness strap", phrases) == ["strap"]
    # a fragment of a two-word phrase falls back to the part whose word comes first
    assert apm.parts_of("strap", phrases) == ["strap"]
    assert apm.parts_of("nothing here", phrases) == []


def test_select_drops_oversized_out_of_zone_weak_and_duplicate_single_boxes():
    vocab = {"parts": {"belt": {"max_box": 0.1, "zone": [0.3, 0.6], "single": True},
                       "plate": {"max_box": 0.2}},
             "rel_score": 0.6}
    found = [
        ("belt", np.array([10, 80, 90, 95]), 0.5, "a"),     # kept: the best belt
        ("belt", np.array([10, 100, 90, 115]), 0.3, "b"),   # in zone, but belt is single
        ("belt", np.array([10, 5, 90, 20]), 0.6, "c"),      # centre above the zone
        ("plate", np.array([0, 0, 100, 200]), 0.9, "d"),    # the whole figure
        ("plate", np.array([10, 40, 40, 70]), 0.5, "e"),    # a shoulder plate
        ("plate", np.array([60, 40, 90, 70]), 0.25, "f"),   # the other shoulder, weak but alone
        ("plate", np.array([12, 42, 38, 68]), 0.2, "g"),    # a weak duplicate of e
    ]
    kept, dropped = apm.select(found, vocab, figure())
    assert kept == [0, 4, 5]
    assert "single" in dropped[1] and "zone" in dropped[2] and "max_box" in dropped[3]
    assert "overlapping" in dropped[6]


def test_thin_keeps_straps_and_cuts_the_block_they_frame():
    mask = np.zeros((100, 100), bool)
    mask[10:90, 10:16] = True       # a strap 6 px wide
    mask[40:80, 30:80] = True       # a block 40 px across
    out = apm.thin(mask, 10)
    assert out[10:90, 10:16].all()
    assert not out[50:70, 40:70].any()


def test_nested_plate_beats_the_harness_mask_round_it_but_not_a_glove_two_layers_up():
    vocab = {"parts": {"strap": {"layer": 8}, "plate": {"layer": 7}, "glove": {"layer": 5},
                       "sleeve_roll": {"layer": 3}, "jacket": {"layer": 1}},
             "base": ["jacket"]}
    harness = np.zeros((50, 50), bool)
    harness[5:45, 5:45] = True
    plate = np.zeros((50, 50), bool)
    plate[15:35, 15:35] = True
    glove = harness.copy()
    cuff = plate.copy()
    found = [("strap", None, 0.4, ""), ("plate", None, 0.3, ""), ("glove", None, 0.4, ""),
             ("sleeve_roll", None, 0.3, "")]
    masks = {0: harness, 1: plate, 2: glove, 3: cuff}
    key = apm.layer_keys(found, masks, [0, 1], vocab)
    assert key[1] > key[0]
    key = apm.layer_keys(found, masks, [2, 3], vocab)
    assert key[3] < key[2]


def test_bare_skin_takes_face_coloured_cloth_that_touches_the_face_only():
    face_rgb, cloth_rgb = (205, 150, 120), (40, 90, 110)
    rgb = np.zeros((120, 60, 3), np.uint8)
    rgb[:] = cloth_rgb
    part = np.full((120, 60), "jacket", dtype="U12")
    part[0:30, 10:50] = "face"
    rgb[0:30, 10:50] = face_rgb
    rgb[30:50, 20:40] = face_rgb      # the neck under the face
    rgb[80:110, 0:20] = face_rgb      # a face-coloured patch nowhere near the face
    moved = apm.bare_skin(part, apm.to_lab(rgb), VOCAB)
    assert moved > 0
    assert (part[32:48, 22:38] == "face").all()
    assert (part[82:108, 2:18] == "jacket").all()


def test_lab_of_white_and_black():
    lab = apm.to_lab(np.array([[[255, 255, 255], [0, 0, 0]]], np.uint8))
    assert abs(lab[0, 0, 0] - 100) < 0.5 and abs(lab[0, 1, 0]) < 0.5
    assert abs(lab[0, 0, 1]) < 1 and abs(lab[0, 0, 2]) < 1
