"""Naming a part of a model, and the kind of surface it is supposed to be.

A painter answers in one material, so a whole sword arrives as one opaque
surface and every part of it inherits whatever the paint's roughness and
metallic maps happened to say. On the real asset this was written for, that was
metallic 0.99 across 72% of the surface: the blade, the edges and the gem were
all being rendered as rough metal, and metal cannot transmit light, so nothing
would ever have made that gem read as a gem.

What is exercised here is the vocabulary and the refusals -- what a caller may
ask for, and what they are told when they ask for something that is not there.
Nothing here runs Blender.
"""
import tempfile
import unittest
from pathlib import Path

from reference_asset_compiler.material_recipes import (
    MaterialRecipeError,
    named_recipes,
    named_tones,
    parse_assignment,
    resolve_recipe,
)
from reference_asset_compiler.resources import checkout_root
from reference_asset_compiler.stages import STAGES, StageError, prepare_assign_surfaces

ROOT = checkout_root()


class VocabularyTests(unittest.TestCase):
    def test_a_crystal_is_not_metal(self):
        crystal = resolve_recipe("crystal", ROOT)

        # The whole reason this exists. A dielectric transmits; metal does not,
        # at all, so a crystal marked metallic can never be made to read as one
        # however its roughness is adjusted.
        #
        # The class is what is asserted, not the taste. How much a crystal
        # transmits is a dial somebody turns while looking at a render -- it
        # came down from 0.72 to 0.5 so a blade's dark core stayed rich -- and a
        # test that pinned the number would have to be edited every time
        # somebody adjusted it, which teaches it to be ignored.
        self.assertEqual(crystal["metallic"], 0.0)
        self.assertGreater(crystal["transmission"], 0.2)
        self.assertLess(crystal["roughness"], 0.2)

    def test_a_gem_bends_light_further_than_glass(self):
        # Which is what makes a cut stone catch light where a window only
        # passes it through.
        self.assertGreater(resolve_recipe("gemstone", ROOT)["ior"],
                           resolve_recipe("glass", ROOT)["ior"])

    def test_metals_do_not_transmit(self):
        for name in ("polished-metal", "brushed-metal", "cast-metal"):
            with self.subTest(surface=name):
                recipe = resolve_recipe(name, ROOT)
                self.assertEqual(recipe["metallic"], 1.0)
                self.assertEqual(recipe["transmission"], 0.0)

    def test_a_surface_nobody_offers_says_what_there_is(self):
        with self.assertRaises(MaterialRecipeError) as refusal:
            resolve_recipe("shiny", ROOT)

        # A refusal that does not say what the choices are sends somebody to
        # read the source.
        self.assertIn("crystal", str(refusal.exception))
        self.assertIn("shiny", str(refusal.exception))

    def test_every_surface_carries_the_numbers_a_caller_is_choosing_between(self):
        offered = named_recipes(ROOT)

        self.assertGreater(len(offered), 4)
        for entry in offered:
            with self.subTest(surface=entry["recipe"]):
                self.assertTrue(entry["description"])
                self.assertIsNotNone(entry["metallic"])
                self.assertIsNotNone(entry["roughness"])

    def test_the_tones_cover_value_end_to_end(self):
        # A part whose colour falls in no tone would simply never be selected,
        # and nothing would say why.
        self.assertEqual(sorted(named_tones(ROOT)), ["bright", "dark", "mid"])


class AssignmentTests(unittest.TestCase):
    def test_a_part_is_a_colour_and_where_it_sits_in_value(self):
        parsed = parse_assignment("blue:dark=crystal", ROOT)

        # A sword's body and the stone at its throat are both blue. Tone is the
        # only thing that tells them apart, and without it one recipe would
        # swallow the other.
        self.assertEqual(parsed["colour"], "blue")
        self.assertEqual(parsed["tone"], "dark")
        self.assertEqual(parsed["recipe"], "crystal")
        self.assertEqual(parsed["values"]["metallic"], 0.0)

    def test_a_colour_with_no_tone_means_the_whole_colour(self):
        self.assertIsNone(parse_assignment("grey=leather", ROOT)["tone"])

    def test_a_tone_nobody_offers_is_refused_by_name(self):
        with self.assertRaises(MaterialRecipeError) as refusal:
            parse_assignment("blue:glowing=crystal", ROOT)
        self.assertIn("glowing", str(refusal.exception))
        self.assertIn("dark", str(refusal.exception))

    def test_something_that_is_not_an_assignment_says_what_one_looks_like(self):
        for text in ("blue", "blue:dark", "=crystal", "blue:dark=", "a=b=c"):
            with self.subTest(text=text):
                with self.assertRaises(MaterialRecipeError) as refusal:
                    parse_assignment(text, ROOT)
                self.assertIn("=", str(refusal.exception))

    def test_a_part_may_name_where_on_the_model_it_is(self):
        parsed = parse_assignment("teal:bright@0.7-0.82=gemstone", ROOT)

        # Some parts colour cannot reach. The stone at a sword's throat and the
        # bright edge down its blade are painted the same, because to a painter
        # they are the same material, so no colour or tone will ever separate
        # them. Where they are will.
        self.assertEqual(parsed["band"], [0.7, 0.82])
        self.assertEqual(parsed["colour"], "teal")
        self.assertEqual(parsed["tone"], "bright")

    def test_a_part_with_no_band_is_the_whole_model(self):
        self.assertIsNone(parse_assignment("blue=crystal", ROOT)["band"])

    def test_a_band_that_is_not_a_band_says_what_one_looks_like(self):
        for text in ("blue@0.7=crystal", "blue@high-low=crystal", "blue@0.8-0.2=crystal",
                     "blue@-0.2-0.5=crystal", "blue@0.5-1.5=crystal"):
            with self.subTest(text=text):
                with self.assertRaises(MaterialRecipeError) as refusal:
                    parse_assignment(text, ROOT)
                self.assertIn("band", str(refusal.exception))

    def test_a_part_cannot_carry_two_tones(self):
        with self.assertRaises(MaterialRecipeError):
            parse_assignment("blue:dark:bright=crystal", ROOT)


class SurfaceStageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = self.root / "painted.glb"
        self.source.write_bytes(b"glb")
        self.output = self.root / "surfaced.glb"

    def test_every_part_reaches_the_script_as_it_was_resolved(self):
        prepared = prepare_assign_surfaces(ROOT, {
            "assign": ["teal:dark=crystal", "grey:bright=brushed-metal"]})

        arguments = prepared["arguments"]
        self.assertEqual(arguments.count("--assign"), 2)
        self.assertIn("teal:dark=crystal", arguments)
        self.assertIn("grey:bright=brushed-metal", arguments)

    def test_the_same_colour_at_two_heights_is_two_parts(self):
        prepared = prepare_assign_surfaces(ROOT, {
            "assign": ["teal:bright@0.0-0.6=crystal", "teal:bright@0.7-0.82=gemstone"]})

        arguments = prepared["arguments"]
        self.assertIn("teal:bright@0.0-0.6=crystal", arguments)
        self.assertIn("teal:bright@0.7-0.82=gemstone", arguments)

    def test_naming_the_same_part_twice_is_refused_rather_than_resolved(self):
        with self.assertRaises(StageError) as refusal:
            prepare_assign_surfaces(ROOT, {"assign": ["blue:dark=crystal", "blue:dark=matte"]})

        # Otherwise which surface won would depend on the order they happened
        # to be listed in, which is not something a caller should have to know.
        self.assertIn("twice", str(refusal.exception))

    def test_naming_nothing_does_nothing_and_says_so(self):
        for options in ({}, {"assign": []}, {"assign": None}):
            with self.subTest(options=options):
                with self.assertRaises(StageError) as refusal:
                    prepare_assign_surfaces(ROOT, options)
                self.assertIn("at least one part", str(refusal.exception))

    def test_a_surface_nobody_offers_is_refused_before_blender_starts(self):
        with self.assertRaises(StageError) as refusal:
            prepare_assign_surfaces(ROOT, {"assign": ["blue:dark=shiny"]})

        # In the caller's own terms, rather than as a line of stderr from a
        # Blender run somebody has to go and find.
        self.assertIn("shiny", str(refusal.exception))

    def test_a_caller_who_named_no_threshold_gets_the_scripts_own(self):
        prepared = prepare_assign_surfaces(ROOT, {"assign": ["blue:dark=crystal"]})
        self.assertNotIn("--minimum-share", prepared["arguments"])

    def test_the_stage_offers_what_it_applies(self):
        stage = STAGES["assign-surfaces"]

        self.assertIn("assign", stage["options"])
        self.assertEqual(stage["produces"], "reference-asset-compiler.material-recipes.v1")
        # No suffix of its own: what comes out is transport, same as it went in.
        self.assertEqual(stage.get("output_suffix", ".glb"), ".glb")


if __name__ == "__main__":
    unittest.main()
