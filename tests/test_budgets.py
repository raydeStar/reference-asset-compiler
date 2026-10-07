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

    def test_notes_promote_only_through_unambiguous_words(self):
        # A door frame's notes say its leaves are separate: door leaves, not foliage.
        frame = decide("temple-frame", (1.4, 9.98, 12.05), notes="Measured clear opening 6 x 10 m. Independent leaves.")
        vines = decide("wall-cover", (0.9, 0.16, 4.0), notes="hanging ivy for the crypt wall")

        self.assertEqual(frame["role"], "prop")
        self.assertEqual(vines["role"], "vegetation")

    def test_notes_only_make_big_things_heroes(self):
        # Notes mention neighbours: a brazier beside the throne, or a lamp lighting a statue, is still a prop...
        brazier = decide("standing-brazier", (0.8, 0.8, 2.5), notes="flanks the throne on the dais")
        lamp = decide("floor-lamp", (0.5, 0.5, 1.2), notes="lights the king's statue")
        # ...while a 4.5 m toppled head is the set piece its notes say it is.
        head = decide("abyss-head", (3.6, 4.1, 4.5), notes="toppled giant statue head")

        self.assertEqual(brazier["role"], "prop")
        self.assertEqual(lamp["role"], "prop")
        self.assertEqual(head["role"], "hero")

    def test_a_given_role_wins(self):
        self.assertEqual(classify("Floor brazier", role="hero")[0], "hero")

    def test_an_unknown_role_is_refused_by_name(self):
        with self.assertRaises(BudgetError) as refusal:
            classify("Floor brazier", role="furniture")
        self.assertIn("prop", str(refusal.exception))

    def test_a_character_without_a_tier_keeps_its_skeleton_profile_ceiling(self):
        decision = decide("wolf creature", (0.6, 0.4, 1.8))

        # Nothing gets more triangles until someone says what it is.
        self.assertEqual(decision["role"], "character")
        self.assertIsNone(decision["tier"])
        self.assertIsNone(decision["triangle_budget"])
        self.assertEqual(decision["ladder"], [])
        self.assertIn("tier", decision["summary"])


class CharacterTierTests(unittest.TestCase):
    """A character costs what its screen time earns, not what its size says.

    Mark, 2026-10-07: characters may run high when it makes sense; random
    objects may not. The hero is up close all game, a regular enemy shares the
    screen with five others.
    """

    def test_each_tier_has_the_agreed_range(self):
        ranges = {tier: (decide("someone", (0.6, 0.4, 1.8), tier=tier)["triangle_floor"],
                         decide("someone", (0.6, 0.4, 1.8), tier=tier)["triangle_ceiling"])
                  for tier in ("hero", "boss", "elite", "regular", "npc")}

        self.assertEqual(ranges, {"hero": (60_000, 80_000), "boss": (50_000, 80_000),
                                  "elite": (30_000, 40_000), "regular": (15_000, 25_000),
                                  "npc": (10_000, 20_000)})

    def test_the_hero_is_budgeted_near_seventy_thousand(self):
        hero = decide("Ennix", (2.1, 0.4, 1.73), tier="hero")

        self.assertEqual(hero["role"], "character")
        self.assertEqual(hero["triangle_budget"], 70_000)
        self.assertIn("groom strands excluded", hero["summary"])

    def test_a_tier_ignores_size(self):
        small = decide("goblin grunt", (0.4, 0.3, 0.9), role="character")
        large = decide("ogre grunt", (1.4, 1.0, 3.0), role="character")

        self.assertEqual(small["tier"], "regular")
        self.assertEqual(small["triangle_budget"], large["triangle_budget"])

    def test_a_name_can_give_the_tier(self):
        self.assertEqual(decide("innkeeper", (0.6, 0.4, 1.8), role="character")["tier"], "npc")
        self.assertEqual(decide("ice boss", (2, 2, 4), role="character")["tier"], "boss")
        self.assertIn("'innkeeper'",
                      decide("innkeeper", (0.6, 0.4, 1.8), role="character")["tier_reason"])

    def test_a_given_tier_wins_over_the_name(self):
        decision = decide("innkeeper", (0.6, 0.4, 1.8), role="character", tier="elite")

        self.assertEqual(decision["tier"], "elite")
        self.assertEqual(decision["tier_reason"], "its tier was given as elite")

    def test_a_tier_on_something_that_is_not_a_character_is_refused(self):
        with self.assertRaises(BudgetError) as refusal:
            decide("Floor brazier", (0.9, 0.9, 1.2), role="prop", tier="hero")
        self.assertIn("character", str(refusal.exception))

    def test_an_unknown_tier_is_refused_by_name(self):
        with self.assertRaises(BudgetError) as refusal:
            decide("Ennix", (2.1, 0.4, 1.73), tier="wizard")
        self.assertIn("hero", str(refusal.exception))

    def test_the_ladder_climbs_to_the_tiers_ceiling_and_no_further(self):
        self.assertEqual(decide("Ennix", (2.1, 0.4, 1.73), tier="hero")["ladder"], [70_000, 80_000])

    def test_a_source_over_the_ceiling_is_never_kept(self):
        over = decide("Ennix", (2.1, 0.4, 1.73), tier="hero", source_triangles=90_000)
        under = decide("Ennix", (2.1, 0.4, 1.73), tier="hero", source_triangles=79_000)

        # 90,000 is close to 70,000 by the ladder's rule, but it fails the gate.
        self.assertFalse(over["keep_source"])
        self.assertEqual(over["ladder"], [80_000])
        self.assertTrue(under["keep_source"])


class RigGateBudgetTests(unittest.TestCase):
    """The strict rig gate's ceiling: the tier when one is declared, else the profile's flat number."""

    PROFILE = {"profile_id": "ue5_manny", "tri_budget": 20_000, "tri_budget_waiver": None}

    def test_without_a_tier_the_flat_ceiling_stays(self):
        rule = budgets.rig_gate_budget(self.PROFILE)

        self.assertEqual(rule["tri_budget"], 20_000)
        self.assertEqual(rule["source"], "skeleton_profile")
        self.assertIsNone(rule["character_tier"])

    def test_a_tier_replaces_the_flat_ceiling_with_its_top(self):
        rule = budgets.rig_gate_budget(self.PROFILE, "hero")

        self.assertEqual(rule["tri_budget"], 80_000)
        self.assertEqual(rule["source"], "character_tier")
        self.assertEqual(rule["character_tier"]["range"], [60_000, 80_000])
        self.assertEqual(rule["replaces_profile_tri_budget"], 20_000)
        self.assertIn("Groom strands", rule["character_tier"]["counts"])
        self.assertEqual(len(rule["policy"]["sha256"]), 64)

    def test_a_tier_can_be_folded_into_the_profile_like_a_waiver(self):
        folded = dict(self.PROFILE, character_tier="regular")

        self.assertEqual(budgets.rig_gate_budget(folded)["tri_budget"], 25_000)
        # A tier named on the command line wins over the folded one.
        self.assertEqual(budgets.rig_gate_budget(folded, "npc")["tri_budget"], 20_000)

    def test_an_unknown_tier_fails_before_the_gate_measures_anything(self):
        with self.assertRaises(BudgetError):
            budgets.rig_gate_budget(self.PROFILE, "wizard")

    def test_a_tier_can_be_stricter_than_the_flat_ceiling(self):
        self.assertEqual(budgets.rig_gate_budget(self.PROFILE, "npc")["tri_budget"], 20_000)
        self.assertLess(budgets.rig_gate_budget({"tri_budget": 50_000}, "elite")["tri_budget"], 50_000)


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

    def test_character_tiers_left_every_other_budget_alone(self):
        # Props stay low; only characters were given room.
        policy, _ = budgets.load_policy()
        roles = {role["id"]: role for role in policy["roles"]}

        self.assertEqual(roles["prop"]["budgets"], {"tiny": 2000, "small": 5000, "medium": 10000,
                                                    "large": 15000, "huge": 20000})
        self.assertEqual(roles["hero"]["budgets"], {"tiny": 8000, "small": 15000, "medium": 25000,
                                                    "large": 40000, "huge": 60000})
        self.assertEqual(roles["vegetation"]["budgets"], {"tiny": 3000, "small": 8000, "medium": 14000,
                                                          "large": 20000, "huge": 30000})
        self.assertEqual(roles["modular"]["per_metre"], {"base": 2000, "per_metre": 1500, "cap": 12000})

    def test_every_tier_is_complete_and_its_target_inside_its_range(self):
        policy, _ = budgets.load_policy()
        character = next(role for role in policy["roles"] if role["id"] == "character")
        ids = [tier["id"] for tier in character["tiers"]]

        self.assertEqual(len(ids), len(set(ids)))
        for tier in character["tiers"]:
            with self.subTest(tier=tier["id"]):
                floor, ceiling = tier["range"]
                self.assertLessEqual(floor, tier["triangles"])
                self.assertLessEqual(tier["triangles"], ceiling)
                self.assertTrue(tier["description"])
                self.assertTrue(tier["keywords"])

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

    def test_rac_budget_takes_a_characters_tier(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["budget", "--name", "Ennix", "--dims", "2.1", "0.4", "1.73",
                             "--tier", "hero"])

        self.assertEqual(code, 0)
        decision = json.loads(output.getvalue())
        self.assertEqual((decision["role"], decision["tier"]), ("character", "hero"))
        self.assertEqual(decision["triangle_ceiling"], 80_000)

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
