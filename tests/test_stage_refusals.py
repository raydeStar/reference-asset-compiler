"""A stage's reason for refusing has to reach whoever asked.

Every stage here refuses the same way: it prints "[TAG] FAILED: " and then a
reason written for a person. Before this, all of that landed in a stdout tail
that only somebody reading a raw receipt would ever see, and the caller was
handed "the stage exited with code 1" -- true, useless, and exactly what those
messages were written to prevent.

It matters most for the stages whose refusals are the feature. The cull refuses
a model with glass in it because a ray cannot see through anything and culling
would empty a lantern through its own panes. A studio that can only say "exit
code 1" cannot offer the artist the choice that refusal exists to give them.
"""

from __future__ import annotations

from reference_asset_compiler.stages import refusal


def test_the_reason_is_lifted_out_of_what_the_stage_printed():
    printed = (
        "Blender 5.2.1 LTS\n"
        "[CULL] FAILED: this model has materials somebody can see past (Material.001_Glass), "
        "and a ray cannot tell glass from brass.\n"
        "Blender quit\n")
    assert refusal(printed) == (
        "this model has materials somebody can see past (Material.001_Glass), "
        "and a ray cannot tell glass from brass.")


def test_the_last_refusal_wins():
    """A stage that got further before giving up said something more specific."""
    assert refusal("[A] FAILED: could not start\n[B] FAILED: the mesh is inside out") \
        == "the mesh is inside out"


def test_output_with_no_refusal_in_it_yields_nothing_to_report():
    """So the caller falls back to naming the stage and its exit code, rather
    than reporting an empty string as though it were an explanation."""
    assert refusal("Blender quit\nsome unrelated chatter") is None
    assert refusal("") is None
    assert refusal("[CULL] FAILED:   ") is None


def test_a_refusal_is_found_wherever_the_tag_sits_on_the_line():
    """Blender prefixes its own noise to a line often enough that anchoring
    this to the start of one would find nothing on a real run."""
    assert refusal("Info: [BAKE] FAILED: the buffer was never marked dirty") \
        == "the buffer was never marked dirty"
