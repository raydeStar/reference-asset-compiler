"""Giving a generated mesh its real size, and collapsing it to a runtime budget.

A generator normalises: whatever it makes arrives about two metres tall. The
reduction gate measures surface deviation in millimetres. Put those together
without a size in between and the gate is meaningless -- the same lantern, the
same settings and the same reduction were rejected at 1.99 m and passed
comfortably at 0.42 m. So the size is asked for, in terms someone can answer,
and applied before anything measures anything.

None of this runs Blender. What is exercised here is the arithmetic and the
refusals, which is where the mistakes are.
"""
import tempfile
import unittest
from pathlib import Path

from reference_asset_compiler import human_scale
from reference_asset_compiler.human_scale import (
    HumanScaleError,
    LANDMARKS,
    named_sizes,
    resolve_height,
)
from reference_asset_compiler.stages import (
    StageError,
    prepare_reduction,
    prepare_staged_mesh,
)


class HumanScaleTests(unittest.TestCase):
    def test_a_size_is_where_it_comes_up_to_on_a_person(self):
        knee = resolve_height("knee")

        # The number matters, but so does the record of how it was reached: a
        # reviewer reading a receipt needs the landmark, not only the metres.
        self.assertAlmostEqual(knee["height_m"], 0.285 * 1.75, places=3)
        self.assertEqual(knee["size"], "knee")
        self.assertEqual(knee["description"], "about knee height")
        self.assertEqual(knee["reference_human_height_m"], 1.75)

    def test_a_little_under_a_landmark_needs_no_landmark_of_its_own(self):
        under = resolve_height("knee", 0.85)

        # "A few inches under the knee" is how people describe a thing, and it
        # should not require inventing a landmark every few inches.
        self.assertLess(under["height_m"], resolve_height("knee")["height_m"])
        self.assertAlmostEqual(under["height_m"], 0.424, places=2)
        self.assertEqual(under["adjust"], 0.85)

    def test_the_landmarks_rise_in_the_order_a_body_does(self):
        heights = [entry["metres"] for entry in named_sizes()]

        # A list that is not in order is a list nobody can pick from.
        self.assertEqual(heights, sorted(heights))
        self.assertEqual(named_sizes()[0]["size"], "ankle")
        self.assertEqual(named_sizes()[-1]["size"], "overhead")

    def test_every_landmark_has_words_for_it(self):
        # The words are what a person picks from; a landmark without them is a
        # landmark that cannot be offered.
        for name in LANDMARKS:
            self.assertIn(name, human_scale.DESCRIPTIONS, name)
            self.assertTrue(human_scale.DESCRIPTIONS[name].strip(), name)

    def test_a_size_nobody_has_heard_of_is_named_with_the_ones_that_exist(self):
        with self.assertRaises(HumanScaleError) as refusal:
            resolve_height("biggish")

        self.assertIn("biggish", str(refusal.exception))
        self.assertIn("knee", str(refusal.exception))

    def test_an_adjustment_that_means_a_different_landmark_is_refused(self):
        for adjust in (0.1, 9.0):
            with self.subTest(adjust=adjust):
                with self.assertRaises(HumanScaleError) as refusal:
                    resolve_height("knee", adjust)
                # Accepting it would record "knee" against a height nothing
                # like a knee, which is worse than refusing.
                self.assertIn("different size", str(refusal.exception))

    def test_a_reference_human_of_an_impossible_height_is_refused(self):
        with self.assertRaises(HumanScaleError):
            resolve_height("knee", reference_height_m=12.0)

    def test_landmarks_are_fractions_so_a_different_reference_still_works(self):
        tall = resolve_height("knee", reference_height_m=2.0)

        self.assertAlmostEqual(tall["height_m"], 0.285 * 2.0, places=3)
        self.assertEqual(tall["fraction_of_stature"], 0.285)


class StagedMeshPreparationTests(unittest.TestCase):
    def test_the_named_size_becomes_metres_for_blender(self):
        prepared = prepare_staged_mesh({"size": "knee", "size_adjust": 0.85})

        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("--size") + 1], "knee")
        self.assertAlmostEqual(float(arguments[arguments.index("--height-m") + 1]), 0.424, places=2)
        # The whole resolution travels in the payload, so the receipt can say
        # which landmark produced the number rather than only the number.
        self.assertEqual(prepared["payload"]["scale"]["size"], "knee")

    def test_staging_without_a_size_refuses_rather_than_guessing(self):
        with self.assertRaises(StageError) as refusal:
            prepare_staged_mesh({})

        # A guessed size silently invalidates every measurement downstream.
        self.assertIn("--size", str(refusal.exception))
        self.assertIn("knee", str(refusal.exception))

    def test_an_unknown_size_is_refused_before_blender_starts(self):
        with self.assertRaises(StageError) as refusal:
            prepare_staged_mesh({"size": "enormous"})

        # Refused here, in the caller's own terms, rather than inside a Blender
        # process whose stderr somebody then has to go and read.
        self.assertIn("enormous", str(refusal.exception))

    def test_no_adjustment_means_the_landmark_itself(self):
        prepared = prepare_staged_mesh({"size": "waist", "size_adjust": None})

        arguments = prepared["arguments"]
        self.assertAlmostEqual(
            float(arguments[arguments.index("--height-m") + 1]), 0.60 * 1.75, places=3)


class ReductionPreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = self.root / "staged.blend"
        self.source.write_bytes(b"blend")
        self.output = self.root / "runtime.glb"

    def test_the_reducer_is_pointed_at_the_source_not_the_destination(self):
        prepared = prepare_reduction(self.source, self.output, {})

        arguments = prepared["arguments"]
        # The destination does not exist yet, so naming it here fails before
        # the reducer has read anything -- which is exactly what happened.
        self.assertEqual(arguments[arguments.index("-InputMesh") + 1], str(self.source.resolve()))

    def test_each_attempt_claims_its_own_directory(self):
        first = prepare_reduction(self.source, self.output, {})
        Path(first["payload"]["attempt_directory"]).mkdir(parents=True)
        second = prepare_reduction(self.source, self.output, {})

        # The reducer refuses to overwrite an attempt, and a rejected reduction
        # is the record by which the next budget is chosen.
        self.assertNotEqual(first["payload"]["attempt_directory"],
                            second["payload"]["attempt_directory"])
        self.assertTrue(first["payload"]["attempt_directory"].endswith("attempt001"))
        self.assertTrue(second["payload"]["attempt_directory"].endswith("attempt002"))

    def test_what_the_launcher_writes_is_collected_from_its_attempt(self):
        prepared = prepare_reduction(self.source, self.output, {})

        attempt = Path(prepared["payload"]["attempt_directory"])
        self.assertEqual(prepared["produced"]["output"], attempt / "feature-qem-candidate.glb")
        self.assertEqual(prepared["produced"]["report"], attempt / "reduction-report.json")

    def test_settings_a_caller_chose_reach_the_launcher(self):
        prepared = prepare_reduction(self.source, self.output, {
            "triangle_budget": 8000, "maximum_p99_m": 0.004})

        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("-TriangleBudget") + 1], "8000")
        self.assertEqual(arguments[arguments.index("-MaximumP99M") + 1], "0.004")
        # Settings nobody chose are left out, so the launcher's own documented
        # defaults apply rather than a second set copied over here.
        self.assertNotIn("-WeightFactor", arguments)

    def test_the_blender_a_studio_named_is_the_one_used(self):
        prepared = prepare_reduction(self.source, self.output, {}, blender="C:/named/blender.exe")

        arguments = prepared["arguments"]
        # Otherwise the launcher finds its own, which may be a different
        # Blender from the one an asset was gated with.
        self.assertEqual(arguments[arguments.index("-Blender") + 1], "C:/named/blender.exe")

    def test_no_blender_named_leaves_the_launcher_to_its_own(self):
        prepared = prepare_reduction(self.source, self.output, {}, blender=None)

        self.assertNotIn("-Blender", prepared["arguments"])


if __name__ == "__main__":
    unittest.main()
