"""Re-baking a reduced painted prop, and judging it by how it looks.

Reducing a mesh after it was painted slides the paint with the UVs, and a
surface-deviation gate cannot see that: the floor brazier stayed within
millimetres and lost its iron bands anyway. The re-bake puts the paint back
from the dense original; the appearance gate compares fixed views, because that
is the only measure that can see paint.

None of this runs Blender. What is exercised is the contract around it: which
files a re-bake may pair, what it refuses before anything is baked, how the
ladder is climbed, how short the rays are, when a reduction's UVs stop being
trusted, which channels need a map, and how two sets of pictures are judged.
"""

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "blender"))

from rebake_rules import (  # noqa: E402
    UV_TOLERANCE,
    painted_shares,
    plan_channels,
    ray_settings,
    uv_verdict,
)
from reference_asset_compiler import appearance  # noqa: E402
from reference_asset_compiler.appearance import (  # noqa: E402
    AppearanceError,
    check_comparable,
    compare_pair,
    compare_views,
    judge,
    ssim_map,
)
from reference_asset_compiler.rebake import (  # noqa: E402
    RebakeError,
    check_binding,
    read_reduction,
    reduction_options,
    remaining_rungs,
    reusable_views,
    triangle_savings,
)
from reference_asset_compiler.stages import (  # noqa: E402
    STAGES,
    StageError,
    describe_stages,
    prepare_rebake_maps,
    run_stage,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reduction_receipt(dense, reduced_blend, reduced_glb=None, status="mechanical_pass",
                      budget=15000, ladder=(10000, 15000, 22500, 33800, 50700),
                      decided=True, mode="runtime-derivative"):
    """The receipt reduce-mesh writes, with the fields a re-bake reads."""
    return {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": status,
        "mode": mode,
        "budget_decision": ({"name": "Floor brazier", "role": "prop", "ladder": list(ladder),
                             "triangle_budget": ladder[0]} if decided else None),
        "source": {"path": str(dense), "sha256": sha(dense),
                   "topology": {"triangles": 119994}},
        "settings": {"triangle_budget": budget, "maximum_p99_m": 0.0044, "maximum_max_m": 0.0175,
                     "weight_factor": 20.0},
        "output": {"path": str(reduced_blend), "sha256": sha(reduced_blend),
                   "review_glb": str(reduced_glb) if reduced_glb else None,
                   "review_glb_sha256": sha(reduced_glb) if reduced_glb else None,
                   "triangles": budget},
    }


class Files(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.dense = self.root / "floor-brazier.blend"
        self.dense.write_bytes(b"dense painted original")
        self.reduced = self.root / "feature-qem-candidate.blend"
        self.reduced.write_bytes(b"reduced native")
        self.review = self.root / "feature-qem-candidate.glb"
        self.review.write_bytes(b"reduced review glb")
        self.output = self.root / "out" / "floor-brazier-runtime.glb"
        self.blender = str(self.root / "blender.exe")

    def write_receipt(self, **changes):
        path = self.root / "reduction-report.json"
        path.write_text(json.dumps(reduction_receipt(self.dense, self.reduced, self.review,
                                                     **changes)), encoding="utf-8")
        return path


class PreparationRefusals(Files):
    def test_a_rebake_without_its_dense_original_is_refused_by_name(self):
        with self.assertRaises(StageError) as refusal:
            prepare_rebake_maps(self.reduced, self.output, {}, self.blender)

        # There is nothing to bake from, and the caller is told which flag says so.
        self.assertIn("--dense", str(refusal.exception))

    def test_a_dense_original_that_is_not_there_is_refused(self):
        with self.assertRaises(StageError) as refusal:
            prepare_rebake_maps(self.reduced, self.output,
                                {"dense": self.root / "missing.blend"}, self.blender)

        self.assertIn("does not exist", str(refusal.exception))

    def test_only_meshes_blender_can_open_for_a_bake_are_accepted(self):
        fbx = self.root / "dense.fbx"
        fbx.write_bytes(b"fbx")
        with self.assertRaises(StageError):
            prepare_rebake_maps(self.reduced, self.output, {"dense": fbx}, self.blender)
        with self.assertRaises(StageError):
            prepare_rebake_maps(self.root / "reduced.obj", self.output, {"dense": self.dense},
                                self.blender)

    def test_a_mesh_cannot_be_rebaked_from_itself(self):
        with self.assertRaises(StageError) as refusal:
            prepare_rebake_maps(self.dense, self.output, {"dense": self.dense}, self.blender)

        self.assertIn("same file", str(refusal.exception))

    def test_a_layout_or_thread_count_that_means_nothing_is_refused_up_front(self):
        for options in ({"uv_layout": "smart"}, {"threads": 0}, {"threads": 500}):
            with self.subTest(options=options):
                with self.assertRaises(StageError):
                    prepare_rebake_maps(self.reduced, self.output,
                                        {"dense": self.dense, **options}, self.blender)

    def test_the_stage_cannot_start_without_blender(self):
        with mock.patch.dict(os.environ, {"RAC_BLENDER": ""}):
            with self.assertRaises(StageError) as refusal:
                run_stage("rebake-maps", self.reduced, self.output, self.root / "r.json",
                          repo_root=ROOT, blender=None, options={"dense": self.dense})

        self.assertIn("Blender", str(refusal.exception))


class PreparationArguments(Files):
    def test_the_attempt_is_claimed_beside_the_output_and_left_for_the_run_to_create(self):
        prepared = prepare_rebake_maps(self.reduced, self.output, {"dense": self.dense},
                                       self.blender)

        arguments = prepared["arguments"]
        attempt = Path(arguments[arguments.index("--attempt-directory") + 1])
        # Attempts are kept, never replaced: the record of what was tried is
        # how the next attempt is chosen.
        self.assertEqual(attempt.parent, self.output.parent.resolve())
        self.assertIn("rebake-attempt001", attempt.name)
        self.assertFalse(attempt.exists())
        self.assertEqual(prepared["payload"]["attempt_directory"], str(attempt))

    def test_the_blender_the_studio_named_is_the_one_that_bakes(self):
        prepared = prepare_rebake_maps(self.reduced, self.output, {"dense": self.dense},
                                       self.blender)

        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("--blender") + 1], self.blender)
        self.assertEqual(arguments[arguments.index("--dense") + 1], str(self.dense.resolve()))

    def test_what_a_caller_chose_reaches_the_stage(self):
        prepared = prepare_rebake_maps(self.reduced, self.output, {
            "dense": self.dense, "uv_layout": "fresh", "threads": 6, "normal_resolution": 1024,
            "samples": 8, "resolution": 768, "no_climb": True}, self.blender)

        arguments = prepared["arguments"]
        for flag, value in (("--uv-layout", "fresh"), ("--threads", "6"),
                            ("--normal-resolution", "1024"), ("--samples", "8"),
                            ("--resolution", "768")):
            self.assertEqual(arguments[arguments.index(flag) + 1], value, flag)
        self.assertIn("--no-climb", arguments)


class ReductionBinding(Files):
    def test_the_pair_a_reduction_measured_is_accepted_by_either_of_its_files(self):
        receipt = read_reduction(self.write_receipt())

        native = check_binding(receipt, self.dense, self.reduced)
        review = check_binding(receipt, self.dense, self.review)

        # reduce-mesh hands a caller its GLB and keeps its .blend in the
        # attempt; either is the same candidate.
        self.assertEqual(native["reduced_is"], "native")
        self.assertEqual(review["reduced_is"], "review_glb")
        self.assertEqual(native["triangle_budget"], 15000)

    def test_a_different_dense_mesh_is_refused_before_anything_is_baked(self):
        report = self.write_receipt()
        impostor = self.root / "another-brazier.blend"
        impostor.write_bytes(b"somebody else's paint")

        with self.assertRaises(StageError) as refusal:
            prepare_rebake_maps(self.reduced, self.output,
                                {"dense": impostor, "reduction_report": report}, self.blender)

        # A bake between the wrong two files transfers paint without any error
        # at all, so the hash is the only thing that can catch it.
        self.assertIn("not the one this reduction was made from", str(refusal.exception))

    def test_a_candidate_this_reduction_did_not_write_is_refused(self):
        report = self.write_receipt()
        stranger = self.root / "stranger.glb"
        stranger.write_bytes(b"a different reduction")

        with self.assertRaises(StageError) as refusal:
            prepare_rebake_maps(stranger, self.output,
                                {"dense": self.dense, "reduction_report": report}, self.blender)

        self.assertIn("not this reduction's output", str(refusal.exception))

    def test_a_rejected_reduction_has_nothing_to_rebake(self):
        report = self.write_receipt(status="rejected")

        with self.assertRaises(StageError) as refusal:
            prepare_rebake_maps(self.reduced, self.output,
                                {"dense": self.dense, "reduction_report": report}, self.blender)

        self.assertIn("rejected", str(refusal.exception))

    def test_a_file_that_is_not_a_reduction_receipt_is_named_as_such(self):
        path = self.root / "views.json"
        path.write_text(json.dumps({"schema": "reference-asset-compiler.review-views.v1"}),
                        encoding="utf-8")

        with self.assertRaises(RebakeError) as refusal:
            read_reduction(path)

        self.assertIn("not a reduction receipt", str(refusal.exception))

    def test_a_bound_receipt_travels_into_the_stage_payload(self):
        report = self.write_receipt()

        prepared = prepare_rebake_maps(self.review, self.output,
                                       {"dense": self.dense, "reduction_report": report},
                                       self.blender)

        self.assertEqual(prepared["payload"]["reduction_binding"]["reduced_is"], "review_glb")
        self.assertIn("--reduction-report", prepared["arguments"])


class Ladder(Files):
    def test_the_climb_continues_from_the_rung_the_surface_gates_accepted(self):
        receipt = reduction_receipt(self.dense, self.reduced, budget=15000)

        # The reduction already refused 10,000 for its surface; appearance
        # failing at 15,000 sends the next attempt up, never back down.
        self.assertEqual(remaining_rungs(receipt), [22500, 33800, 50700])

    def test_a_rung_that_would_keep_most_of_the_source_is_not_offered(self):
        receipt = reduction_receipt(self.dense, self.reduced, budget=50700,
                                    ladder=(50700, 76000, 114000, 171000))

        # 171,000 is more than the source has; reducing to it means nothing.
        self.assertEqual(remaining_rungs(receipt), [76000, 114000])

    def test_an_explicit_number_was_one_attempt_and_offers_no_ladder(self):
        receipt = reduction_receipt(self.dense, self.reduced, decided=False)

        self.assertEqual(remaining_rungs(receipt), [])

    def test_the_next_rung_is_reduced_with_the_same_gates_role_and_mode(self):
        receipt = reduction_receipt(self.dense, self.reduced)

        options = reduction_options(receipt, 22500)

        self.assertEqual(options["triangle_budget"], 22500)
        self.assertEqual(options["maximum_p99_m"], 0.0044)
        self.assertEqual(options["maximum_max_m"], 0.0175)
        self.assertEqual(options["role"], "prop")
        self.assertEqual(options["asset_name"], "Floor brazier")
        self.assertTrue(options["runtime_derivative"])

    def test_an_authority_reduction_is_not_turned_into_a_runtime_derivative(self):
        receipt = reduction_receipt(self.dense, self.reduced, mode="production-authority")

        self.assertNotIn("runtime_derivative", reduction_options(receipt, 22500))

    def test_the_saving_is_reported_against_the_dense_original(self):
        saved = triangle_savings(119994, 16800)

        self.assertEqual(saved["triangles_saved"], 103194)
        self.assertAlmostEqual(saved["share_saved"], 0.86, places=2)


class Rays(unittest.TestCase):
    def test_rays_cross_the_measured_gap_and_no_further(self):
        rays = ray_settings(gap_p99_m=0.003, diagonal_m=1.75)

        # Twice the 99th-percentile gap: long enough to find the dense surface
        # from either side, short enough not to land on the next part over.
        self.assertAlmostEqual(rays["cage_extrusion_m"], 0.006)
        self.assertAlmostEqual(rays["max_ray_distance_m"], 0.012)
        self.assertFalse(rays["use_cage"])

    def test_a_reduction_that_barely_moved_still_gets_a_usable_ray(self):
        self.assertAlmostEqual(ray_settings(0.0001, 1.0)["cage_extrusion_m"], 0.0015)

    def test_a_large_gap_never_makes_rays_longer_than_a_hundredth_of_the_object(self):
        # The worst points miss and are filled from their neighbours; that is
        # a smaller error than every ray in the model reaching too far.
        self.assertAlmostEqual(ray_settings(0.2, 2.0)["cage_extrusion_m"], 0.02)

    def test_nonsense_measurements_are_refused(self):
        with self.assertRaises(ValueError):
            ray_settings(-0.001, 1.0)
        with self.assertRaises(ValueError):
            ray_settings(0.001, 0.0)


class Coverage(unittest.TestCase):
    def setUp(self):
        self.islands = np.zeros((20, 20), dtype=bool)
        self.islands[2:18, 2:18] = True            # 256 painted texels
        self.reached = self.islands.copy()
        self.reached[5:9, 5:9] = False             # 16 the rays missed
        self.written = self.reached.copy()
        self.written[5:9, 5] = True                # 4 the margin then covered

    def test_misses_the_margin_covered_are_written_not_reached(self):
        shares = painted_shares(self.islands, self.reached, self.written)

        self.assertEqual(shares["painted_surface_reached_share"], round(240 / 256, 4))
        self.assertEqual(shares["painted_surface_written_share"], round(244 / 256, 4))

    def test_the_gutter_does_not_count_either_way(self):
        reached = self.reached | ~self.islands
        shares = painted_shares(self.islands, reached, np.ones((20, 20), dtype=bool))

        self.assertEqual(shares["painted_surface_reached_share"], round(240 / 256, 4))
        self.assertEqual(shares["painted_surface_written_share"], 1.0)

    def test_no_painted_texel_means_no_share_rather_than_zero(self):
        empty = np.zeros((4, 4), dtype=bool)

        self.assertEqual(painted_shares(empty, empty, empty),
                         {"painted_surface_reached_share": None,
                          "painted_surface_written_share": None})

    def test_masks_of_different_sizes_are_refused(self):
        with self.assertRaises(ValueError):
            painted_shares(self.islands, self.reached, np.ones((10, 10), dtype=bool))


class UvTrust(unittest.TestCase):
    clean = {"overlap_share": 0.0, "flipped_share": 0.0, "distorted_share": 0.0,
             "outside_share": 0.0}

    def test_a_reduction_that_kept_its_atlas_usable_is_baked_onto_as_it_is(self):
        healthy, reasons = uv_verdict({**self.clean, "distorted_share": 0.013}, self.clean)

        # The 16.8k brazier: 1.3% more stretched area is within tolerance.
        self.assertTrue(healthy)
        self.assertEqual(reasons, [])

    def test_damage_the_reduction_introduced_sends_the_bake_to_a_fresh_unwrap(self):
        healthy, reasons = uv_verdict({**self.clean, "distorted_share": 0.0347}, self.clean)

        # The 5k brazier: collapse stretched 3.5% of its surface.
        self.assertFalse(healthy)
        self.assertIn("distorted", reasons[0])

    def test_an_atlas_that_was_always_crowded_is_not_blamed_on_the_reduction(self):
        source = {**self.clean, "overlap_share": 0.04}

        healthy, _ = uv_verdict({**self.clean, "overlap_share": 0.042}, source)

        self.assertTrue(healthy)

    def test_every_tolerance_is_a_small_share(self):
        for key, allowed in UV_TOLERANCE.items():
            self.assertTrue(0.0 < allowed <= 0.05, key)


def material(**channels):
    entry = {"base_color": {"linked": True}, "alpha": {"constant": 1.0},
             "roughness": {"constant": 0.5}, "metallic": {"constant": 0.0},
             "transmission": {"constant": 0.0}, "emission": {"constant": (0.0, 0.0, 0.0)},
             "occlusion": {"constant": 1.0}}
    entry.update(channels)
    return entry


class ChannelPlan(unittest.TestCase):
    def test_the_paint_is_always_baked_and_neutral_constants_stay_numbers(self):
        plan = plan_channels([material()])

        self.assertTrue(plan["base_color"]["baked"])
        self.assertEqual(plan["roughness"], {"baked": False, "constant": 0.5})
        self.assertFalse(plan["occlusion"]["baked"])

    def test_a_channel_a_texture_drives_gets_its_own_map(self):
        plan = plan_channels([material(roughness={"linked": True}, metallic={"linked": True})])

        self.assertTrue(plan["roughness"]["baked"])
        self.assertTrue(plan["metallic"]["baked"])

    def test_one_number_cannot_stand_for_two_materials_that_disagree(self):
        plan = plan_channels([material(roughness={"constant": 0.9}),
                              material(roughness={"constant": 0.3})])

        self.assertTrue(plan["roughness"]["baked"])
        self.assertIn("differ", plan["roughness"]["why"])

    def test_a_cutout_keeps_its_cutoff(self):
        plan = plan_channels([material(alpha={"linked": True, "cutoff": 0.5})])

        # The tattered banners are cut out at 0.5; baked and blended instead,
        # their torn edges would turn translucent.
        self.assertTrue(plan["alpha"]["baked"])
        self.assertEqual(plan["alpha"]["cutoff"], 0.5)

    def test_there_must_be_something_to_plan(self):
        with self.assertRaises(ValueError):
            plan_channels([])


def write_rgba(path, rgb, alpha):
    pixels = np.dstack([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]])
    Image.fromarray((pixels * 255).round().astype(np.uint8), "RGBA").save(path)


def painted_bands(size=128, blur=0):
    """A small asset with crisp bands of paint, like iron straps on a bowl."""
    rgb = np.full((size, size, 3), 0.35)
    rgb[:, :, 0] += 0.25 * (np.arange(size)[None, :] // 6 % 2)
    if blur:
        from scipy import ndimage
        rgb = ndimage.uniform_filter(rgb, size=(1, blur, 1))
    return rgb


class AppearanceComparison(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_identical_pictures_are_identical(self):
        image = np.random.default_rng(1).random((64, 64))

        self.assertAlmostEqual(float(ssim_map(image, image).mean()), 1.0, places=6)

    def test_a_smear_scores_below_the_gate_and_a_faithful_copy_above_it(self):
        size = 128
        alpha = np.zeros((size, size))
        alpha[32:96, 32:96] = 1.0
        write_rgba(self.root / "original.png", painted_bands(size), alpha)
        write_rgba(self.root / "smeared.png", painted_bands(size, blur=9), alpha)
        write_rgba(self.root / "faithful.png", painted_bands(size) + 0.005, alpha)

        smeared = compare_pair(self.root / "original.png", self.root / "smeared.png")
        faithful = compare_pair(self.root / "original.png", self.root / "faithful.png")

        self.assertLess(smeared["ssim"], appearance.THRESHOLDS["albedo"]["minimum_ssim"])
        self.assertGreater(faithful["ssim"], appearance.THRESHOLDS["albedo"]["minimum_ssim"])
        self.assertEqual(faithful["silhouette_iou"], 1.0)

    def test_the_background_does_not_vote(self):
        size = 256
        alpha = np.zeros((size, size))
        alpha[108:148, 108:148] = 1.0
        write_rgba(self.root / "original.png", painted_bands(size), alpha)
        write_rgba(self.root / "smeared.png", painted_bands(size, blur=9), alpha)

        scores = compare_pair(self.root / "original.png", self.root / "smeared.png")

        # Over the whole frame the grey background would make a ruined prop
        # look 99% alike; over the asset alone it does not.
        whole = ssim_map(appearance.luma(appearance.load_view(self.root / "original.png")[0]),
                         appearance.luma(appearance.load_view(self.root / "smeared.png")[0]))
        self.assertGreater(float(whole.mean()), 0.97)
        self.assertLess(scores["ssim"], 0.9)

    def test_a_missing_part_shows_in_the_silhouette(self):
        size = 64
        whole = np.zeros((size, size))
        whole[8:56, 8:56] = 1.0
        broken = whole.copy()
        broken[8:20, 8:56] = 0.0
        flat = np.full((size, size, 3), 0.4)
        write_rgba(self.root / "whole.png", flat, whole)
        write_rgba(self.root / "broken.png", flat, broken)

        scores = compare_pair(self.root / "whole.png", self.root / "broken.png")

        self.assertLess(scores["silhouette_iou"], appearance.THRESHOLDS["minimum_silhouette_iou"])

    def test_pictures_of_different_sizes_are_not_compared(self):
        write_rgba(self.root / "a.png", np.zeros((8, 8, 3)), np.ones((8, 8)))
        write_rgba(self.root / "b.png", np.zeros((16, 16, 3)), np.ones((16, 16)))

        with self.assertRaises(AppearanceError):
            compare_pair(self.root / "a.png", self.root / "b.png")


class AppearanceVerdict(unittest.TestCase):
    def views(self, beauty=0.97, albedo=0.98, iou=0.99, back=None):
        entries = []
        for pass_name, score in (("beauty", beauty), ("albedo", albedo)):
            for view in ("front", "three-quarter", "side", "back"):
                value = back if (view == "back" and back is not None) else score
                entries.append({"pass": pass_name, "view": view, "ssim": value,
                                "silhouette_iou": iou})
        return entries

    def test_a_faithful_candidate_passes(self):
        passed, failures = judge(self.views())

        self.assertTrue(passed)
        self.assertEqual(failures, [])

    def test_a_good_front_cannot_excuse_a_broken_back(self):
        passed, failures = judge(self.views(back=0.80))

        # The average is high; one side is not. Fixed views exist for this.
        self.assertFalse(passed)
        self.assertTrue(all("back" in failure for failure in failures))

    def test_a_silhouette_that_changed_fails_however_well_it_is_painted(self):
        passed, failures = judge(self.views(iou=0.90))

        self.assertFalse(passed)
        self.assertIn("silhouette", failures[0])

    def test_the_thresholds_are_recorded_with_the_verdict(self):
        root = Path(tempfile.mkdtemp())
        manifests = []
        for name in ("reference", "candidate"):
            directory = root / name
            directory.mkdir()
            views = []
            for pass_name in ("beauty", "albedo"):
                for view in ("front", "three-quarter", "side", "back"):
                    file = "{0}-{1}.png".format(pass_name, view)
                    alpha = np.zeros((48, 48))
                    alpha[8:40, 8:40] = 1.0
                    write_rgba(directory / file, painted_bands(48), alpha)
                    views.append({"pass": pass_name, "view": view, "file": file})
            manifest = {"schema": appearance.VIEWS_SCHEMA, "resolution": 48,
                        "framing": {"centre": [0, 0, 0.6], "extent": 1.2},
                        "display": {"view_transform": "Standard"}, "passes": ["beauty", "albedo"],
                        "device": {"engine": "CYCLES", "samples": 32, "seed": 0},
                        "views": views, "source_sha256": name}
            (directory / "views.json").write_text(json.dumps(manifest), encoding="utf-8")
            manifests.append(directory / "views.json")

        verdict = compare_views(*manifests)

        self.assertTrue(verdict["passed"])
        self.assertEqual(verdict["thresholds"], appearance.THRESHOLDS)
        self.assertEqual(len(verdict["views"]), 8)
        self.assertEqual(verdict["summary"]["albedo"]["minimum_ssim"], 1.0)


class Comparability(unittest.TestCase):
    base = {"resolution": 512, "framing": {"centre": [0, 0, 0.6], "extent": 1.2},
            "display": {"view_transform": "Standard"}, "passes": ["beauty", "albedo"],
            "device": {"samples": 32, "seed": 0, "engine": "CYCLES"},
            "views": [{"pass": "beauty", "view": "front"}, {"pass": "albedo", "view": "front"}]}

    def test_a_candidate_framed_by_its_own_bounds_is_refused(self):
        candidate = {**self.base, "framing": {"centre": [0, 0, 0.61], "extent": 1.19}}

        with self.assertRaises(AppearanceError) as refusal:
            check_comparable(self.base, candidate)

        # Otherwise the comparison measures the millimetres the silhouette
        # moved, not the paint.
        self.assertIn("cameras", str(refusal.exception))

    def test_views_rendered_differently_are_refused(self):
        for change in ({"resolution": 768}, {"device": {"samples": 64, "seed": 0,
                                                         "engine": "CYCLES"}},
                       {"views": self.base["views"][:1]}):
            with self.subTest(change=change):
                with self.assertRaises(AppearanceError):
                    check_comparable(self.base, {**self.base, **change})


class ReferenceViewReuse(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.reference = self.root / "floor-brazier.glb"
        self.reference.write_bytes(b"glTF delivered")
        (self.root / "beauty-front.png").write_bytes(b"png")
        self.manifest = self.root / "views.json"

    def write(self, **changes):
        manifest = {"source_sha256": sha(self.reference), "resolution": 512,
                    "device": {"samples": 32}, "framing_borrowed": False,
                    "views": [{"file": "beauty-front.png"}]}
        manifest.update(changes)
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")

    def test_views_of_exactly_this_reference_taken_the_same_way_are_reused(self):
        self.write()

        self.assertTrue(reusable_views(self.manifest, self.reference, 512, 32))

    def test_views_of_anything_else_are_rendered_again(self):
        for change in ({"source_sha256": "0" * 64}, {"resolution": 768},
                       {"device": {"samples": 64}}, {"framing_borrowed": True}):
            with self.subTest(change=change):
                self.write(**change)
                self.assertFalse(reusable_views(self.manifest, self.reference, 512, 32))


class Registry(unittest.TestCase):
    def test_the_stage_is_offered_with_what_it_writes_and_needs(self):
        described = describe_stages(ROOT, blender=None, legacy_root=None)
        stage = next(item for item in described["stages"] if item["stage"] == "rebake-maps")

        self.assertEqual(stage["output_suffix"], ".glb")
        self.assertIn("dense", stage["options"])
        if not os.environ.get("RAC_BLENDER"):
            self.assertIn("blender", stage["missing"])
        self.assertEqual(STAGES["rebake-maps"]["produces"], "reference-asset-compiler.rebake-maps.v1")


class StageScript(Files):
    """The script the stage runs, refusing before it spends any CPU."""

    def load(self):
        spec = importlib.util.spec_from_file_location("rebake_maps_script",
                                                      ROOT / "scripts" / "rebake_maps.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_without_blender_it_refuses_and_writes_nothing(self):
        script = self.load()

        code = script.main(["--", str(self.reduced), str(self.output), str(self.root / "r.json"),
                            "--dense", str(self.dense), "--blender", str(self.root / "none.exe")])

        self.assertEqual(code, 1)
        self.assertFalse(self.output.parent.exists())

    def test_a_mismatched_pair_leaves_a_receipt_saying_why(self):
        script = self.load()
        Path(self.blender).write_bytes(b"never executed")
        report = self.write_receipt()
        impostor = self.root / "impostor.blend"
        impostor.write_bytes(b"another original")
        receipt_path = self.root / "rebake.json"

        code = script.main(["--", str(self.reduced), str(self.output), str(receipt_path),
                            "--dense", str(impostor), "--blender", self.blender,
                            "--reduction-report", str(report)])

        self.assertEqual(code, 1)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["schema"], "reference-asset-compiler.rebake-maps.v1")
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("not the one this reduction was made from", receipt["failures"][0])
        self.assertIsNone(receipt["accepted"])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
