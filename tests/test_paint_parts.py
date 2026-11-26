"""Painting a model by parts: finding the parts, and painting each from its own picture.

Everything that does not need a GPU, a detector or Blender is exercised here:
which detector boxes a part may keep, how masks resolve, how votes on pixels
become one label a face, how a labelling becomes pieces to paint, what each
piece's picture holds, that a piece is laid on exactly its own texels, and
what the two stages refuse before anything is queued.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import segment_part_views as spv  # noqa: E402
from label_parts import collect_votes, face_neighbours, face_normals, mesh_sha256, settle_labels  # noqa: E402
from paint_parts import (  # noqa: E402
    absorb_small_runs,
    base_picture,
    hard_weights,
    main as paint_parts_main,
    piece_picture,
    plan_pieces,
)
from paint_sections import GENERATOR_FRAME, face_sheet  # noqa: E402
from reference_asset_compiler.stages import (  # noqa: E402
    STAGES,
    StageError,
    prepare_label_parts,
    prepare_paint_parts,
)
from test_head_detail import glb_with_mesh, solid_png  # noqa: E402
from test_paint_sections import picture_of, strip  # noqa: E402
from test_texture_stage import paint_stack  # noqa: E402

PARTS = [{"name": "hull", "base": True}, {"name": "seat", "max_box": 0.25}, {"name": "fin", "max_box": 0.3}]


class BoxTests(unittest.TestCase):
    figure = [0, 0, 100, 100]

    def test_a_box_bigger_than_its_part_can_be_is_dropped_against_the_model_not_the_picture(self):
        # The whole boat answered "metal bracket"; it filled a fifth of the render, so
        # against the picture its box passed. Against the model's own box it does not.
        kept, dropped = spv.judge_boxes([{"index": 2, "score": 0.5, "box": [0, 0, 100, 90]},
                                         {"index": 2, "score": 0.4, "box": [10, 10, 40, 30]}],
                                        PARTS, self.figure)
        self.assertEqual([entry["box"] for entry in kept], [[10, 10, 40, 30]])
        self.assertIn("covers", dropped[0]["dropped"])

    def test_parts_compete_for_one_region_and_the_better_score_keeps_it(self):
        kept, dropped = spv.judge_boxes([{"index": 1, "score": 0.43, "box": [10, 10, 40, 30]},
                                         {"index": 2, "score": 0.51, "box": [11, 10, 40, 31]}],
                                        PARTS, self.figure)
        self.assertEqual([entry["index"] for entry in kept], [2])
        self.assertIn("lost the region to fin", dropped[0]["dropped"])

    def test_one_part_may_keep_two_boxes_and_two_parts_two_places(self):
        kept, _ = spv.judge_boxes([{"index": 2, "score": 0.5, "box": [0, 0, 20, 20]},
                                   {"index": 2, "score": 0.45, "box": [80, 80, 100, 100]},
                                   {"index": 1, "score": 0.6, "box": [40, 40, 60, 60]}],
                                  PARTS, self.figure)
        self.assertEqual(len(kept), 3)

    def test_the_strongest_mask_takes_a_pixel_and_the_base_the_rest(self):
        foreground = np.zeros((4, 4), bool)
        foreground[:, :3] = True
        weak, strong = np.zeros((4, 4), bool), np.zeros((4, 4), bool)
        weak[:2, :] = True
        strong[1:3, :] = True
        labels, strength = spv.resolve([(1, 0.3, weak), (2, 0.6, strong)], 0, foreground)
        self.assertEqual(labels[0, 0], 1)
        self.assertEqual(labels[1, 0], 2)
        self.assertEqual(labels[3, 0], 0)
        self.assertEqual(labels[0, 3], 255)
        self.assertEqual(strength[0, 3], 0)

    def test_a_picture_on_a_plain_backdrop_has_its_figure_found(self):
        picture = np.full((40, 40, 3), 200, np.uint8)
        picture[10:30, 5:35] = (120, 70, 30)
        foreground = spv.picture_foreground(Image.fromarray(picture))
        self.assertTrue(foreground[20, 20])
        self.assertFalse(foreground[2, 2])


class VoteTests(unittest.TestCase):
    def test_seam_copies_are_one_surface(self):
        # Two triangles sharing an edge whose vertices the export split along a seam.
        positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], np.float32)
        triangles = np.array([[0, 1, 2], [3, 5, 4]])
        a, b = face_neighbours(positions, triangles)
        self.assertEqual(sorted(zip(a.tolist(), b.tolist())), [(0, 1)])

    def test_an_unseen_face_takes_its_neighbours_label(self):
        positions, _, triangles = strip(columns=6)
        a, b = face_neighbours(positions, triangles)
        votes = np.zeros((len(triangles), 2))
        votes[:6, 1] = 1.0
        votes[8:, 0] = 1.0
        labels, unseen, _ = settle_labels(votes, a, b, face_normals(positions, triangles), 0)
        self.assertEqual(unseen.sum(), 2)
        self.assertEqual(labels[:6].tolist(), [1] * 6)
        self.assertEqual(labels[8:].tolist(), [0] * 4)

    def test_a_lone_stray_vote_is_outvoted_by_its_neighbours(self):
        positions, _, triangles = strip(columns=10)
        a, b = face_neighbours(positions, triangles)
        votes = np.zeros((len(triangles), 2))
        votes[:, 0] = 1.0
        votes[9] = [0.45, 0.55]
        labels, _, changed = settle_labels(votes, a, b, face_normals(positions, triangles), 0)
        self.assertEqual(labels[9], 0)
        self.assertEqual(changed, 1)

    def test_a_pixel_left_to_the_base_votes_weakly(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "views.json").write_text(json.dumps({"views": [{"view": 0}]}), encoding="utf-8")
        np.save(folder / "view-00-faces.npy", np.array([[0, 0], [1, -1]], np.int32))
        np.save(folder / "view-00-labels.npy", np.array([[0, 1], [0, 255]], np.uint8))
        np.save(folder / "view-00-score.npy", np.array([[0, 0.5], [0, 0]], np.float32))
        votes, views = collect_votes(folder, 2, 2, 0, 0.15)
        self.assertEqual(views, 1)
        self.assertAlmostEqual(votes[0, 0], 0.15)
        self.assertAlmostEqual(votes[0, 1], 0.5)
        self.assertAlmostEqual(votes[1, 0], 0.15)


class PieceTests(unittest.TestCase):
    def setUp(self):
        self.positions, _, self.triangles = strip(columns=48)
        self.a, self.b = face_neighbours(self.positions, self.triangles)
        self.labels = np.zeros(len(self.triangles), np.int64)
        self.labels[:10] = 2          # a fin at one end
        self.labels[-10:] = 2         # and one at the other, 2 m away
        self.labels[40:44] = 1        # a small seat in the middle

    def test_runs_of_a_part_far_apart_are_painted_apart(self):
        pieces, _ = plan_pieces(self.positions, self.triangles, self.labels, self.a, self.b, 0, set(), 0.05, 2)
        self.assertEqual([piece["part"] for piece in pieces], [0, 1, 2, 2])
        self.assertEqual(sum(len(piece["faces"]) for piece in pieces), len(self.triangles))

    def test_a_part_painted_together_is_one_piece(self):
        pieces, _ = plan_pieces(self.positions, self.triangles, self.labels, self.a, self.b, 0, {2}, 0.05, 2)
        self.assertEqual([piece["part"] for piece in pieces], [0, 1, 2])
        self.assertEqual(len(pieces[2]["faces"]), 20)

    def test_runs_closer_than_the_join_distance_are_one_piece(self):
        labels = self.labels.copy()
        labels[:] = 0
        labels[10:14] = 1
        labels[16:20] = 1   # 5 cm from the first run along a 2.4 m strip of 48 columns
        pieces, _ = plan_pieces(self.positions, self.triangles, labels, self.a, self.b, 0, set(), 0.06, 2)
        self.assertEqual([piece["part"] for piece in pieces], [0, 1])

    def test_a_piece_too_small_to_paint_goes_to_the_base(self):
        pieces, labels = plan_pieces(self.positions, self.triangles, self.labels, self.a, self.b, 0, {2}, 0.05, 6)
        self.assertEqual([piece["part"] for piece in pieces], [0, 2])
        self.assertTrue((labels[40:44] == 0).all())
        self.assertEqual(len(pieces[0]["faces"]), len(self.triangles) - 20)

    def test_a_stray_run_takes_its_neighbours_label(self):
        labels = np.zeros(len(self.triangles), np.int64)
        labels[30] = 2
        self.assertEqual(absorb_small_runs(labels, self.a, self.b, 3)[30], 0)


class PictureTests(unittest.TestCase):
    def setUp(self):
        self.rgba = np.zeros((60, 100, 4), np.uint8)
        self.rgba[..., :3] = (120, 80, 40)
        self.rgba[10:50, 5:95, 3] = 255

    def test_the_base_picture_fills_what_another_part_covered_and_keeps_the_figure(self):
        own = self.rgba[..., 3] > 0
        own[20:30, 40:60] = False            # the seat standing on the floor
        self.rgba[20:30, 40:60, :3] = (230, 230, 230)
        picture, region, filled = base_picture(self.rgba, own)
        self.assertEqual(filled, 200)
        self.assertTrue((picture[20:30, 40:60, 3] == 255).all())
        self.assertLess(abs(int(picture[25, 50, 0]) - 120), 10)   # wood, not the seat's white
        self.assertEqual(picture[0, 0, 3], 0)

    def test_a_hole_in_a_parts_mask_is_closed_with_the_pictures_own_pixels(self):
        own = np.zeros((60, 100), bool)
        own[20:30, 10:40] = True
        own[24:26, 20:24] = False            # the strut the detector gave to the hull
        picture, region, _ = piece_picture(self.rgba, own, (25, 25), together=False)
        self.assertTrue((picture[24:26, 20:24, 3] == 255).all())
        self.assertTrue((picture[24:26, 20:24, :3] == (120, 80, 40)).all())

    def test_a_piece_is_shown_its_own_region_or_all_of_them_together(self):
        own = np.zeros((60, 100), bool)
        own[15:35, 10:30] = True              # one fin
        own[15:35, 70:90] = True              # and the other
        picture, region, _ = piece_picture(self.rgba, own, (80, 25), together=False)
        self.assertTrue(region[20, 80])
        self.assertFalse(region[20, 20])
        self.assertEqual(picture[20, 20, 3], 0)
        picture, region, _ = piece_picture(self.rgba, own, (80, 25), together=True)
        self.assertTrue(region[20, 80] and region[20, 20])

    def test_a_part_the_picture_does_not_show_gives_no_picture(self):
        picture, region, _ = piece_picture(self.rgba, np.zeros((60, 100), bool), (50, 30), together=False)
        self.assertIsNone(picture)


class LayingTests(unittest.TestCase):
    def test_a_piece_weighs_one_on_its_own_texels_and_nothing_elsewhere(self):
        positions, uvs, triangles = strip(columns=8)
        sheet = face_sheet(uvs, triangles, 64, grow_texels=0)
        weights = hard_weights(sheet, np.arange(8), len(triangles), 64)
        owned = np.zeros((64, 64), bool)
        owned[sheet["rows"], sheet["columns"]] = sheet["faces"] < 8
        self.assertTrue((weights[owned] == 1).all())
        self.assertTrue((weights[~owned] == 0).all())
        self.assertEqual(set(np.unique(weights)), {0.0, 1.0})


class RunTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        positions, uvs, triangles = strip()
        self.source = self.root / "painted.glb"
        self.source.write_bytes(glb_with_mesh(positions, uvs, triangles, [solid_png(64, (120, 90, 60))]))
        from compress_textures import read_glb  # noqa: PLC0415
        from paint_head_detail import mesh_from_glb  # noqa: PLC0415
        self.positions, self.uvs, self.triangles = mesh_from_glb(*read_glb(self.source.read_bytes()))
        alpha = picture_of(positions, triangles, GENERATOR_FRAME)
        picture = np.zeros(alpha.shape + (4,), np.uint8)
        picture[..., :3] = 150
        picture[..., 3] = alpha
        self.reference = self.root / "reference.png"
        Image.fromarray(picture, "RGBA").save(self.reference)
        reference_labels = np.where(alpha > 127, 0, 255).astype(np.uint8)
        columns = np.nonzero((alpha > 127).any(axis=0))[0]
        left, right = columns.min(), columns.max()
        reference_labels[:, left:left + 40][alpha[:, left:left + 40] > 127] = 1
        reference_labels[:, right - 40:right + 1][alpha[:, right - 40:right + 1] > 127] = 1
        self.reference_labels = reference_labels
        self.faces = np.zeros(len(self.triangles), np.uint8)
        self.faces[:8] = 1
        self.faces[-8:] = 1

    def labelling(self, mesh=None):
        path = self.root / "labels.npz"
        vocab = {"parts": [{"name": "body", "base": True}, {"name": "end", "prompts": ["end"]}]}
        from paint_sections import sha256  # noqa: PLC0415
        with open(path, "wb") as stream:
            np.savez_compressed(stream, faces=self.faces, reference=self.reference_labels,
                                names=np.array(["body", "end"]), vocab=np.array(json.dumps(vocab)),
                                mesh_sha256=np.array(mesh or mesh_sha256(self.positions, self.uvs, self.triangles)),
                                reference_sha256=np.array(sha256(self.reference)))
        return path

    def run_plan(self, *extra):
        output, report = self.root / "out.glb", self.root / "out.json"
        code = paint_parts_main(["--", str(self.source), str(output), str(report), "--parts", str(self.labelling()),
                                 "--reference", str(self.reference), "--min-piece", "4", "--plan-only", *extra])
        return code, json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None

    def test_a_plan_names_each_piece_and_cuts_its_picture(self):
        code, receipt = self.run_plan()
        self.assertEqual(code, 0)
        self.assertEqual([piece["piece"] for piece in receipt["pieces"]], ["00-body", "01-end", "02-end"])
        self.assertEqual([piece["faces"] for piece in receipt["pieces"]], [80, 8, 8])
        self.assertFalse(receipt["painted"])
        for piece in receipt["pieces"]:
            crop = Image.open(Path(piece["folder"]) / "reference.png")
            self.assertEqual(crop.mode, "RGBA")
            self.assertGreater(piece["reference_pixels"], 0)
        self.assertEqual(receipt["settings"]["surface_from"], "first")

    def fake_painter(self, fail_last=False):
        """The painter, as paint_batch and paint_section drive it: each piece's maps and gate in its folder."""
        import paint_sections  # noqa: PLC0415
        calls = {"batch": 0, "single": 0}

        def write(paint_dir, fail=False):
            paint_dir.mkdir(parents=True, exist_ok=True)
            if fail:
                (paint_dir / "section.failure.json").write_text(json.dumps({"error": "CUDA out of memory"}),
                                                                encoding="utf-8")
                return
            rng = np.random.default_rng(len(paint_dir.parent.name) * 7 + int(paint_dir.parent.name[:2]))
            Image.fromarray(rng.integers(0, 255, (64, 64, 3)).astype(np.uint8), "RGB").save(paint_dir / "section.png")
            for name in ("section_metallic.png", "section_roughness.png"):
                Image.fromarray(rng.integers(0, 255, (64, 64)).astype(np.uint8), "L").save(paint_dir / name)
            (paint_dir / "section.validation.json").write_text(json.dumps(
                {"faces_equal": True, "geometry_delta": 0.0, "uv_delta": 0.0, "seconds": 2.0,
                 "seconds_painting": 1.5}), encoding="utf-8")

        def paint_batch(args, jobs, attempt, minutes_each=10.0, on_progress=None):
            calls["batch"] += 1
            for number, (_, _, paint_dir, _) in enumerate(jobs):
                write(paint_dir, fail_last and number == len(jobs) - 1)
            return 1 if fail_last else 0

        def paint_section(args, mesh_obj, crop_png, paint_dir, bake_size=0):
            calls["single"] += 1
            write(paint_dir)
            glb, gate = paint_sections.read_paint(paint_dir)
            return glb, gate, 0

        saved = paint_sections.paint_batch, paint_sections.paint_section
        self.addCleanup(lambda: (setattr(paint_sections, "paint_batch", saved[0]),
                                 setattr(paint_sections, "paint_section", saved[1])))
        paint_sections.paint_batch, paint_sections.paint_section = paint_batch, paint_section
        return calls

    def run_paint(self, name, *extra):
        legacy = self.root / "studio"
        (legacy / ".venv-hy3d21" / "Scripts").mkdir(parents=True, exist_ok=True)
        (legacy / ".venv-hy3d21" / "Scripts" / "python.exe").write_bytes(b"")
        launcher = self.root / "launch.ps1"
        launcher.write_text("", encoding="utf-8")
        output, report = self.root / (name + ".glb"), self.root / (name + ".json")
        code = paint_parts_main(["--", str(self.source), str(output), str(report), "--parts", str(self.labelling()),
                                 "--reference", str(self.reference), "--min-piece", "4", "--atlas", "2048",
                                 "--legacy-root", str(legacy), "--launcher", str(launcher), *extra])
        receipt = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
        return code, output, receipt

    def test_one_painter_run_paints_every_piece_as_separate_runs_did(self):
        calls = self.fake_painter()
        code, together, receipt = self.run_paint("one-run")
        self.assertEqual(code, 0)
        self.assertEqual(calls, {"batch": 1, "single": 0})
        self.assertEqual(receipt["settings"]["painter_runs"], "one for every piece")
        self.assertEqual(receipt["settings"]["inpaint_reach"], 32)
        self.assertEqual([piece["paint_seconds"] for piece in receipt["pieces"]], [1.5, 1.5, 1.5])
        code, apart, receipt = self.run_paint("separate", "--separate-runs")
        self.assertEqual(code, 0)
        self.assertEqual(calls, {"batch": 1, "single": 3})
        self.assertEqual(receipt["settings"]["painter_runs"], "one per piece")
        self.assertEqual(together.read_bytes(), apart.read_bytes())

    def test_a_piece_the_painter_did_not_finish_fails_the_pass_and_keeps_the_rest(self):
        self.fake_painter(fail_last=True)
        code, output, receipt = self.run_paint("broken")
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())
        self.assertIsNone(receipt)
        attempt = next(self.root.glob("broken-parts-attempt*"))
        self.assertTrue((attempt / "00-body" / "paint" / "section.validation.json").is_file())
        self.assertTrue((attempt / "02-end" / "paint" / "section.failure.json").is_file())

    def test_the_reach_is_bounded(self):
        code, _, receipt = self.run_paint("wide", "--inpaint-reach", "300")
        self.assertEqual(code, 1)
        self.assertIsNone(receipt)

    def test_parts_named_together_are_planned_as_one_piece(self):
        code, receipt = self.run_plan("--together", "end")
        self.assertEqual(code, 0)
        self.assertEqual([piece["piece"] for piece in receipt["pieces"]], ["00-body", "01-end"])

    def test_a_labelling_made_for_another_mesh_is_refused(self):
        output, report = self.root / "out.glb", self.root / "out.json"
        code = paint_parts_main(["--", str(self.source), str(output), str(report),
                                 "--parts", str(self.labelling(mesh="0" * 64)), "--reference", str(self.reference),
                                 "--plan-only"])
        self.assertEqual(code, 1)
        self.assertFalse(report.exists())

    def test_an_unknown_together_part_is_refused(self):
        code, _ = self.run_plan("--together", "mast")
        self.assertEqual(code, 1)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"png")
        self.legacy = paint_stack(self.root / "studio")
        python = self.root / "torch" / "python.exe"
        python.parent.mkdir()
        python.write_bytes(b"python")
        detector = self.root / "dino"
        detector.mkdir()
        (detector / "config.json").write_text("{}", encoding="utf-8")
        sam = self.root / "sam.pth"
        sam.write_bytes(b"sam")
        self.segmenter = {"torch_python": str(python), "detector": str(detector), "sam": str(sam)}

    def test_the_skiff_vocabulary_has_one_base_and_prompts_for_every_other_part(self):
        vocab = json.loads((ROOT / "profiles/segmentation/skiff-parts.json").read_text(encoding="utf-8"))
        parts = vocab["parts"]
        self.assertEqual(sum(1 for part in parts if part.get("base")), 1)
        for part in parts:
            if not part.get("base"):
                self.assertTrue(part["prompts"])
                self.assertLessEqual(part["max_box"], 0.5)
        self.assertTrue(next(part for part in parts if part["name"] == "fin")["together"])

    def test_a_vocabulary_is_found_by_name_and_handed_on_with_the_segmenter(self):
        prepared = prepare_label_parts(ROOT, {"vocab": "skiff-parts", "reference": self.reference,
                                              **self.segmenter}, "blender.exe")
        arguments = prepared["arguments"]
        self.assertEqual(Path(arguments[arguments.index("--vocab") + 1]).name, "skiff-parts.json")
        self.assertEqual(arguments[arguments.index("--blender") + 1], "blender.exe")
        self.assertEqual(arguments[arguments.index("--sam") + 1], self.segmenter["sam"])

    def test_a_vocabulary_with_two_bases_or_no_prompts_is_refused(self):
        for parts in ([{"name": "a", "base": True}, {"name": "b", "base": True}],
                      [{"name": "a", "base": True}, {"name": "b"}]):
            path = self.root / "vocab.json"
            path.write_text(json.dumps({"parts": parts}), encoding="utf-8")
            with self.assertRaises(StageError):
                prepare_label_parts(ROOT, {"vocab": str(path), "reference": self.reference, **self.segmenter},
                                    "blender.exe")

    def test_without_a_segmenter_it_says_what_is_missing(self):
        with self.assertRaises(StageError) as caught:
            prepare_label_parts(ROOT, {"vocab": "skiff-parts", "reference": self.reference,
                                       "torch_python": str(self.root / "none.exe"),
                                       "detector": str(self.root / "none"), "sam": str(self.root / "none.pth")},
                                "blender.exe")
        self.assertIn("torch-python", str(caught.exception))
        self.assertIn("grounding-dino", str(caught.exception))

    def test_the_part_painter_is_handed_the_labelling_the_picture_and_its_settings(self):
        labelling = self.root / "labels.npz"
        labelling.write_bytes(b"npz")
        earlier = self.root / "earlier"
        earlier.mkdir()
        prepared = prepare_paint_parts({"parts": labelling, "reference": self.reference, "atlas": 8192,
                                        "together": ["fin"], "surface": "first", "reuse_parts": earlier},
                                       self.legacy)
        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("--parts") + 1], str(labelling.resolve()))
        self.assertEqual(arguments[arguments.index("--together") + 1], "fin")
        self.assertEqual(arguments[arguments.index("--surface") + 1], "first")
        self.assertEqual(arguments[arguments.index("--reuse-parts") + 1], str(earlier.resolve()))

    def test_the_part_painter_refuses_without_a_labelling(self):
        with self.assertRaises(StageError):
            prepare_paint_parts({"reference": self.reference}, self.legacy)

    def test_the_stages_are_listed_with_their_cost(self):
        self.assertEqual(STAGES["label-parts"]["output_suffix"], ".npz")
        self.assertEqual(STAGES["paint-parts"]["estimate"]["unit"], "piece")
        from reference_asset_compiler import cli  # noqa: PLC0415
        args = cli.build_parser().parse_args([
            "run-stage", "paint-parts", "--source", "p.glb", "--output", "o.glb", "--report", "o.json",
            "--parts", "labels.npz", "--reference", "r.png", "--together", "fin", "--surface", "first"])
        self.assertEqual(args.together, ["fin"])
        self.assertEqual(args.surface, "first")


if __name__ == "__main__":
    unittest.main()
