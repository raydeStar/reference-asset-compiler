"""Deciding how many triangles an asset should cost from what it is and how big it is.

Every static object used to inherit the profile's 100,000-triangle ceiling as a
target, so a 1 m pipe was given the budget of a 6 m door. The table in
profiles/triangle-budgets.json replaces that with a role (prop, modular kit
piece, vegetation, hero, character) and a size class. These tests hold the
decisions an artist would otherwise have to spell out by hand.

None of this runs Blender.
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler import budgets, cli  # noqa: E402
from reference_asset_compiler.budgets import BudgetError, classify, decide, size_class  # noqa: E402


class ClassificationTests(unittest.TestCase):
    def test_an_ordinary_prop_is_a_prop_without_anyone_saying_so(self):
        decision = decide("Floor brazier", (0.9, 0.9, 1.2))

        self.assertEqual(decision["role"], "prop")
        self.assertEqual(decision["size_class"], "medium")
        # The number an artist expects for a chest or a brazier: about 5,000
        # vertices, which is about 10,000 triangles on a closed mesh.
        self.assertEqual(decision["triangle_budget"], 10_000)

    def test_a_set_piece_is_recognised_by_its_name(self):
        throne = decide("Hero throne", (3.5, 2.6, 4.6))
        statue = decide("guardian-kneeling-6m", (3.0, 3.0, 6.0))

        self.assertEqual(throne["role"], "hero")
        self.assertEqual(statue["role"], "hero")
        self.assertGreater(throne["triangle_budget"], decide("Crate", (3.5, 2.6, 4.6))["triangle_budget"])

    def test_kit_pieces_cost_by_length(self):
        short = decide("Sandstone rail 3 m", (3.0, 0.3, 1.0))
        long = decide("Sandstone rail 6 m", (6.0, 0.3, 1.0))

        self.assertEqual(short["role"], "modular")
        # A kit piece repeats along every wall it lines, so it is paid for by
        # the metre rather than as one object.
        self.assertGreater(long["triangle_budget"], short["triangle_budget"])
        self.assertLessEqual(long["triangle_budget"], 12_000)

    def test_a_name_that_says_kit_on_something_that_is_not_long_is_a_prop(self):
        winch = decide("chain-winch", (3.0, 1.7, 1.8))

        # 'chain' names kit pieces, but a winch is a machine: the real shape
        # overrules the word, and the receipt says so.
        self.assertEqual(winch["role"], "prop")
        self.assertIn("not long and thin", winch["role_reason"])

    def test_notes_can_raise_a_role_but_never_lower_one(self):
        head = decide("abyss-head", (3.6, 4.1, 4.5), notes="toppled giant statue head")
        brazier = decide("Floor brazier", (0.9, 0.9, 1.2), notes="stands on a sandstone plinth")

        self.assertEqual(head["role"], "hero")
        # Notes mention neighbours ('stands on a plinth') far more often than
        # names do, so they may not make something cheaper.
        self.assertEqual(brazier["role"], "prop")

    def test_a_given_role_wins(self):
        self.assertEqual(classify("Floor brazier", role="hero")[0], "hero")

    def test_an_unknown_role_is_refused_by_name(self):
        with self.assertRaises(BudgetError) as refusal:
            classify("Floor brazier", role="furniture")
        self.assertIn("prop", str(refusal.exception))

    def test_characters_take_the_rig_route(self):
        decision = decide("innkeeper", (0.6, 0.4, 1.8), role="character")

        self.assertIsNone(decision["triangle_budget"])
        self.assertEqual(decision["ladder"], [])
        self.assertIn("rig route", decision["summary"])


class SizeAndGateTests(unittest.TestCase):
    def test_size_classes_rise_with_the_longest_side(self):
        classes = [size_class(length) for length in (0.1, 0.5, 1.5, 3.0, 9.0)]

        self.assertEqual(classes, ["tiny", "small", "medium", "large", "huge"])

    def test_bigger_props_get_more_but_never_unbounded(self):
        budgets_by_size = [decide("Crate", (length, length, length))["triangle_budget"]
                           for length in (0.1, 0.5, 1.5, 3.0, 9.0)]

        self.assertEqual(budgets_by_size, sorted(budgets_by_size))
        self.assertLessEqual(budgets_by_size[-1], 20_000)

    def test_surface_gates_scale_with_the_object(self):
        coin = decide("Coin", (0.03, 0.03, 0.003))
        door = decide("Temple door", (3.0, 0.5, 10.0))

        # A colossus is not held to a coin's tolerance, and a coin is not let
        # off with a door's.
        self.assertLess(coin["maximum_p99_m"], door["maximum_p99_m"])
        self.assertGreaterEqual(coin["maximum_p99_m"], 0.0015)

    def test_the_ladder_rises_from_the_budget(self):
        ladder = decide("Floor brazier", (0.9, 0.9, 1.2))["ladder"]

        self.assertEqual(ladder[0], 10_000)
        self.assertEqual(ladder, sorted(ladder))
        self.assertEqual(len(ladder), len(set(ladder)))

    def test_a_source_already_close_to_budget_is_kept(self):
        near = decide("Floor brazier", (0.9, 0.9, 1.2), source_triangles=11_000)
        far = decide("Floor brazier", (0.9, 0.9, 1.2), source_triangles=120_000)

        self.assertTrue(near["keep_source"])
        self.assertFalse(far["keep_source"])
        self.assertTrue(all(rung < 0.75 * 120_000 for rung in far["ladder"]))

    def test_impossible_dimensions_are_refused(self):
        for dims in ((0, 0, 0), (1.0, float("nan"), 1.0), (1.0, 2.0)):
            with self.subTest(dims=dims):
                with self.assertRaises(BudgetError):
                    decide("Crate", dims)


class TableTests(unittest.TestCase):
    def test_the_checkout_table_is_the_one_read(self):
        policy, path = budgets.load_policy()

        self.assertEqual(path, ROOT / "profiles" / "triangle-budgets.json")
        self.assertEqual(policy["schema"], budgets.POLICY_SCHEMA)

    def test_every_budgeted_role_covers_every_size(self):
        policy, _ = budgets.load_policy()
        sizes = {entry["id"] for entry in policy["size_classes"]}
        for role in policy["roles"]:
            with self.subTest(role=role["id"]):
                if role.get("budgets"):
                    self.assertEqual(set(role["budgets"]), sizes)
                elif role["id"] != "character":
                    self.assertIn("per_metre", role)

    def test_the_decision_names_the_table_it_came_from(self):
        decision = decide("Crate", (1, 1, 1))

        self.assertEqual(decision["schema"], budgets.DECISION_SCHEMA)
        self.assertEqual(len(decision["policy"]["sha256"]), 64)


class BudgetCommandTests(unittest.TestCase):
    def test_rac_budget_prints_the_decision(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["budget", "--name", "Floor brazier", "--dims", "0.9", "0.9", "1.2"])

        self.assertEqual(code, 0)
        decision = json.loads(output.getvalue())
        self.assertEqual(decision["role"], "prop")
        self.assertEqual(decision["triangle_budget"], 10_000)

    def test_rac_budget_refusals_use_the_normal_error_channel(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = cli.main(["budget", "--name", "Crate", "--dims", "1", "1", "1",
                             "--role", "furniture"])

        self.assertEqual(code, 2)
        self.assertIn("RAC_ERROR", errors.getvalue())

    def test_the_reduce_stage_accepts_auto(self):
        args = cli.build_parser().parse_args([
            "run-stage", "reduce-mesh", "--triangle-budget", "auto", "--role", "prop"])

        self.assertEqual(args.triangle_budget, "auto")
        self.assertEqual(args.role, "prop")


if __name__ == "__main__":
    unittest.main()
