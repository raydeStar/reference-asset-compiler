"""What the visibility cull decides, without a renderer in the room.

The half that needs Blender needs a mesh. Everything that decides anything does
not, and that is deliberate: the viewpoints, the order rays are tried in and
the verdicts are the parts that can be wrong in a way no picture shows.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "blender"))

from reference_asset_compiler.stages import STAGES, prepare_cull_unseen  # noqa: E402
from visibility import (  # noqa: E402
    cull_verdict, directions_over_sphere, viewing_order, whole_part_verdict,
    whole_parts_removed)


def test_every_viewpoint_is_a_direction_and_not_a_position():
    """A direction that is not unit length makes the ray's reach mean something else."""
    for count in (8, 64, 257):
        for point in directions_over_sphere(count):
            assert math.isclose(sum(axis * axis for axis in point), 1.0, abs_tol=1e-12)


def test_the_viewpoints_do_not_clump_at_the_poles():
    """The reason for a spiral rather than a latitude and longitude grid.

    Split the sphere into eight octants by sign. A grid spends far more of its
    directions near the poles than around the equator, so a model's underside
    would be examined more carefully than its side for no reason at all.
    """
    counts: dict[tuple[bool, bool, bool], int] = {}
    for x, y, z in directions_over_sphere(256):
        key = (x >= 0, y >= 0, z >= 0)
        counts[key] = counts.get(key, 0) + 1
    assert len(counts) == 8
    assert min(counts.values()) >= 256 / 8 * 0.7


def test_both_sides_of_a_face_are_looked_from():
    """The bug that took a ninja's boots off.

    Firing only into the hemisphere a face points at assumes the normal is
    right. On generated meshes it often is not: measured on one rigged
    character, 5,950 faces -- a quarter of everything the outward-only test
    called hidden -- were in plain sight from their other side. Visibility is a
    question about where a face sits, not about which way an exporter thought
    it pointed.
    """
    directions = directions_over_sphere(64)
    ordered = viewing_order(directions, (0.0, 0.0, 1.0))
    assert len(ordered) == len(directions)
    assert any(side > 0 for _, side in ordered)
    assert any(side < 0 for _, side in ordered)


def test_each_ray_is_told_which_side_of_the_face_it_leaves_from():
    """Lift the origin the wrong way and the ray's first hit is the face itself,
    which reads as "hidden" for every face in the model."""
    for _, normal in (("up", (0.0, 0.0, 1.0)), ("skew", (0.6, 0.0, 0.8))):
        for ray, side in viewing_order(directions_over_sphere(64), normal):
            alignment = sum(a * b for a, b in zip(ray, normal))
            assert (alignment > 0) == (side > 0)


def test_the_best_aligned_ray_is_tried_first():
    """What makes looking from 64 directions affordable at all.

    An ordinary exterior face escapes on its first ray, so the full sweep is
    paid only by faces that really are buried. Reverse this and every visible
    face costs the worst case instead of one cast.
    """
    ordered = viewing_order(directions_over_sphere(128), (0.0, 0.0, 1.0))
    alignments = [abs(ray[2]) for ray, _ in ordered]
    assert alignments == sorted(alignments, reverse=True)


def test_a_ray_lying_exactly_in_the_face_is_not_cast():
    """It would only graze the face it started from and answer nothing."""
    ordered = viewing_order([(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)], (0.0, 0.0, 1.0))
    assert [ray for ray, _ in ordered] == [(0.0, 0.0, 1.0)]


def test_a_result_that_removes_most_of_a_model_is_refused():
    refusal = cull_verdict(total=1000, kept=100, most=0.6)
    assert refusal and "inside out" in refusal


def test_removing_nothing_is_refused_rather_than_shipped():
    """A revision identical to its source is clutter with a lineage note on it."""
    refusal = cull_verdict(total=1000, kept=1000, most=0.6)
    assert refusal and "nothing to remove" in refusal


def test_a_share_at_the_limit_is_allowed_and_one_past_it_is_not():
    assert cull_verdict(total=100, kept=40, most=0.6) is None
    assert cull_verdict(total=100, kept=39, most=0.6) is not None


def test_debris_that_vanishes_whole_is_counted_and_a_trimmed_part_is_not():
    """Only a group with nothing surviving beside it counts as a part lost whole."""
    sealed = {0: [1], 1: [0], 2: [3], 3: [2], 4: []}
    assert whole_parts_removed(sealed, {0, 1, 4}) == [2, 1]
    trimmed = {0: [1], 1: [0, 2], 2: [1]}
    assert whole_parts_removed(trimmed, {2}) == []


def test_a_part_too_big_to_be_debris_is_refused():
    """An eyeball sealed inside a head is the same arithmetic as a stray shell,
    and the only thing telling them apart is how much of the model it is."""
    assert whole_part_verdict([60], total=100, largest=0.1) is not None
    assert whole_part_verdict([2, 2, 1], total=1000, largest=0.1) is None
    assert whole_part_verdict([], total=1000, largest=0.1) is None


def test_the_stage_is_registered_with_the_report_it_produces():
    stage = STAGES["cull-unseen"]
    assert stage["runner"] == "blender"
    assert stage["produces"] == "reference-asset-compiler.culled-faces.v1"
    assert Path(stage["script"]).name == "cull_unseen_faces.py"


def test_the_option_names_a_caller_sends_are_the_names_the_script_answers_to():
    """The compression stage shipped asking for `format` against a parser that
    wanted `--texture-format`, and nothing caught it until a live run refused.
    The registry's option names and the flags built from them are two lists
    that have to agree, so here they are, compared."""
    assert set(STAGES["cull-unseen"]["options"]) == {
        "directions", "most", "largest_part", "ignore_transparency"}
    built = prepare_cull_unseen(
        {"directions": 96, "most": 0.4, "largest_part": 0.05, "ignore_transparency": True})
    assert built["arguments"] == [
        "--directions", "96", "--most", "0.4", "--largest-part", "0.05",
        "--ignore-transparency"]


def test_nothing_is_passed_for_an_option_nobody_set():
    """An unset option has to mean the script's own default, not the string "None"."""
    assert prepare_cull_unseen({})["arguments"] == []
    assert prepare_cull_unseen({"directions": None, "most": None})["arguments"] == []


def test_glass_is_not_waved_through_by_accident():
    """A model with glass is refused unless somebody says so in as many words,
    because a ray cannot see through anything and would empty a lantern."""
    assert "--ignore-transparency" not in prepare_cull_unseen({})["arguments"]
    assert "--ignore-transparency" not in prepare_cull_unseen(
        {"ignore_transparency": False})["arguments"]


def test_an_impossible_direction_count_is_refused_before_blender_starts():
    for directions in (2, 4096):
        with pytest.raises(ValueError):
            prepare_cull_unseen({"directions": directions})


def test_a_share_outside_its_range_is_refused_before_blender_starts():
    for name in ("most", "largest_part"):
        for share in (0.0, 1.5, -0.2):
            with pytest.raises(ValueError):
                prepare_cull_unseen({name: share})
