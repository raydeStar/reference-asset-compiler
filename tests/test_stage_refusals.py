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

from reference_asset_compiler.stages import last_words, refusal


def test_wrapped_powershell_refusal_keeps_the_reason_before_process_owners():
    stderr = (
        "C:\\repo\\scripts\\run_hy3d21_texture.ps1 : GPU has 20543 MiB free;\n"
        "21504 MiB is required. Inference was not launched. Owners: \n"
        + "1234, C:\\Windows\\application.exe, [N/A];\n" * 40
        + "At C:\\repo\\scripts\\run_hy3d21_texture.ps1:74 char:13\n"
        "+ $gpuState = & $guard\n"
        "+             ~~~~~~~~\n"
        "    + CategoryInfo : OperationStopped: (GPU has ...:String) [], RuntimeException\n"
        "    + FullyQualifiedErrorId : GPU has ...\n")
    message = last_words(stderr, "texture", 1)
    assert message.startswith("The texture stage exited with code 1: GPU has 20543 MiB free; 21504 MiB is required.")
    assert "Inference was not launched" in message
    assert "CategoryInfo" not in message
    assert message.endswith("...")
    assert len(message) <= 645


def test_last_powershell_error_block_wins_without_its_location_trailer():
    stderr = (
        "C:\\repo\\first.ps1 : Earlier error\nAt C:\\repo\\first.ps1:2 char:1\n"
        "C:\\repo\\second.ps1 : The reference hash changed\n"
        "At C:\\repo\\second.ps1:8 char:1\n+ throw 'mismatch'\n")
    assert last_words(stderr, "geometry", 1).endswith("The reference hash changed")


def test_unprefixed_file_error_ignores_wrapped_metadata_at_the_end():
    stderr = (
        "An image-to-3D worker is already running or loading (PID 42); inference was not launched. Let that worker\n"
        "finish.\nAt C:\\repo\\scripts\\assert_gpu_available.ps1:33 char:5\n"
        "+ throw 'busy'\n+ ~~~~~~~~~~~~\n"
        "    + CategoryInfo : OperationStopped: (An image-to-3D worker...:String) [], RuntimeException\n"
        "    + FullyQualifiedErrorId : An image-to-3D worker is already running; inference was no\n"
        "t launched. Let that worker finish.\n")
    assert last_words(stderr, 'texture', 1) == (
        'The texture stage exited with code 1: An image-to-3D worker is already running or loading (PID 42); '
        'inference was not launched. Let that worker finish.')


def test_non_powershell_errors_keep_the_last_meaningful_line():
    assert last_words("Traceback (most recent call last):\nValueError: missing mesh\n", "unwrap", 2).endswith("ValueError: missing mesh")
    assert last_words("", "unwrap", 2) == "The unwrap stage exited with code 2 without saying why."


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
