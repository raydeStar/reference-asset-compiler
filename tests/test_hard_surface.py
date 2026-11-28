"""The hard-surface painter: what it promises about the maps it writes, checked on a part small enough to reason about.

The part is synthetic: a half-metre plate lying flat, an upright panel with a rivet on it, and a short tube. Its
maps are written here by arithmetic, the way bake_surface_maps would have written them, so these tests need
neither Blender nor a GPU.
"""
import hashlib
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler import hard_surface as hs
from reference_asset_compiler.polish_glb import read_glb, write_glb

PROFILE = json.loads((ROOT / "profiles" / "materials" / "hard-surface-ironworks.json").read_text(encoding="utf-8"))
SIZE = 128


def part_maps(size=SIZE, plate_texel=.004):
    """Three islands on one atlas: a flat plate (class 0), an upright panel with a rivet (1), a tube (2)."""
    valid = np.zeros((size, size), bool)
    pos = np.zeros((size, size, 3), np.float32)
    nrm = np.zeros((size, size, 3), np.float32)
    cls = np.zeros((size, size), np.uint8)
    ao = np.ones((size, size, 3), np.float32)
    bev = np.zeros((size, size, 4), np.float32)
    bev[..., 2:] = 1
    half = size // 2 - 4
    rows, cols = np.mgrid[0:half, 0:half].astype(np.float32)
    # the plate, facing up
    plate = (slice(2, 2 + half), slice(2, 2 + half))
    valid[plate] = True
    pos[plate] = np.stack([cols * plate_texel, rows * plate_texel, np.zeros_like(rows)], -1)
    nrm[plate] = (0, 0, 1)
    # the panel, upright and facing -Y, with a rivet head in the middle of it
    panel = (slice(2, 2 + half), slice(size // 2 + 2, size // 2 + 2 + half))
    valid[panel] = True
    pos[panel] = np.stack([cols * .002, np.zeros_like(rows), (half - rows) * .002], -1)
    nrm[panel] = (0, -1, 0)
    cls[panel] = 1
    centre = half // 2
    rivet = (rows - centre) ** 2 + (cols - centre) ** 2 < 16
    ao[panel][..., 1][np.abs(np.hypot(rows - centre, cols - centre) - 5) < 1.5] = .3          # the crevice round its foot
    crown = np.zeros_like(rows)
    crown[rivet] = 1 - np.hypot(rows - centre, cols - centre)[rivet] / 4
    # the tube, lying along X
    tube = (slice(size // 2 + 2, size // 2 + 2 + half), slice(2, 2 + half))
    valid[tube] = True
    angle = rows / half * 2 * np.pi
    pos[tube] = np.stack([cols * .003, .02 * np.sin(angle), .5 + .02 * np.cos(angle)], -1)
    nrm[tube] = np.stack([np.zeros_like(rows), np.sin(angle), np.cos(angle)], -1)
    cls[tube] = 2
    edge = np.zeros((size, size), np.float32)                        # the plate's and the panel's rims are edges
    for region in (plate, panel):
        mask = np.zeros((half, half), np.float32)
        mask[:3] = mask[-3:] = 1
        mask[:, :3] = mask[:, -3:] = 1
        edge[region] = mask
    bev[..., 3] = 1 - .2 * edge
    dome = np.zeros((size, size), np.float32)
    dome[panel] = crown
    fasteners = np.array([[centre * .002, 0, (half - centre) * .002, 0, -1, 0, .008]], np.float32)
    return {"valid": valid, "pos": pos, "nrm": nrm, "ao": ao, "bev": bev, "cls": cls, "dome": dome,
            "bounds": np.stack([pos[valid].min(0), pos[valid].max(0)]), "class_names": ["deck", "panel", "rail"], "fasteners": fasteners}


RECIPE = {"classes": {"deck": "tread_plate", "panel": "old_teal_paint", "rail": "palm_rail"}, "seed": 7}


class HardSurfacePainter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = tempfile.TemporaryDirectory()
        cls.noise = hs.Noise(cls.cache.name, size=64)
        cls.palette, cls.classes = hs.load_profile(PROFILE)
        cls.maps = part_maps()
        cls.result = hs.paint(cls.maps, RECIPE, cls.palette, cls.classes, cls.noise)

    @classmethod
    def tearDownClass(cls):
        cls.cache.cleanup()

    def region(self, name, image):
        index = self.maps["class_names"].index(name)
        return image[self.maps["valid"] & (self.maps["cls"] == index)]

    def test_three_maps_come_back_whole_and_bounded(self):
        for key in ("base_color", "normal", "orm"):
            image = self.result[key]
            self.assertEqual(image.shape, (SIZE, SIZE, 3))
            self.assertEqual(image.dtype, np.uint8)
        # every island's edge is carried outward, so no texel is left black for a mip to find
        self.assertGreater(int(self.result["base_color"][~self.maps["valid"]].sum(axis=1).min()), 0)
        normals = self.result["normal"].astype(np.float32) / 127.5 - 1
        self.assertGreater(float(normals[..., 2].min()), 0.0)
        self.assertLess(float(np.abs(np.linalg.norm(normals, axis=2) - 1).max()), .03)

    def test_the_same_recipe_paints_the_same_part(self):
        again = hs.paint(self.maps, RECIPE, self.palette, self.classes, self.noise)
        for key in ("base_color", "normal", "orm"):
            self.assertTrue(np.array_equal(again[key], self.result[key]), key)

    def test_another_seed_wears_differently(self):
        other = hs.paint(self.maps, {**RECIPE, "seed": 8}, self.palette, self.classes, self.noise)
        self.assertFalse(np.array_equal(other["base_color"], self.result["base_color"]))

    def test_paint_is_not_metal_and_iron_is(self):
        self.assertLess(float(np.median(self.region("panel", self.result["orm"])[:, 2])), 40)          # paint: dielectric
        self.assertGreater(float(np.median(self.region("rail", self.result["orm"])[:, 2])), 180)       # browned iron: metal
        self.assertGreater(float(np.median(self.region("deck", self.result["orm"])[:, 2])), 180)

    def test_the_painted_panel_is_teal_where_the_paint_holds(self):
        red, green, blue = np.median(self.region("panel", self.result["base_color"]), axis=0)
        self.assertGreater(green, red)
        self.assertGreater(green, blue - 12)

    def test_a_tread_plate_carries_its_pattern_in_the_normal_map(self):
        # one plate, a quarter of a metre square at a millimetre a texel: big enough to have a field inside its plain margin
        size = 250
        rows, cols = np.mgrid[0:size, 0:size].astype(np.float32)
        maps = {"valid": np.ones((size, size), bool), "pos": np.stack([cols * .001, rows * .001, np.zeros_like(rows)], -1),
                "nrm": np.tile(np.array([0, 0, 1], np.float32), (size, size, 1)), "ao": np.ones((size, size, 3), np.float32),
                "bev": np.tile(np.array([0, 0, 1, 1], np.float32), (size, size, 1)), "cls": np.zeros((size, size), np.uint8),
                "class_names": ["deck"]}

        def tilt(pattern):
            result = hs.paint(maps, {"classes": {"deck": "tread_plate"}, "seed": 7, "tread": {"pattern": pattern, "wheel_lines_y_m": []}},
                              self.palette, self.classes, self.noise)
            z = result["normal"][100:150, 100:150].astype(np.float32)[..., 2] / 127.5 - 1      # the middle, inside the margin
            return float(np.degrees(np.arccos(np.clip(z, -1, 1))).mean())
        self.assertGreater(tilt("lozenge"), tilt("none") + 2.0)

    def test_rust_stands_proud_of_the_metal(self):
        field = hs.Field(self.noise, self.palette, P=np.random.default_rng(1).random((4000, 3)).astype(np.float32) * .2,
                         texel=np.full(4000, .0007, np.float32))
        layers = hs.Layers(field.n)
        hs.rust(field, layers, np.ones(field.n, np.float32), 3)
        self.assertGreater(float(layers.H.mean()), 1.5e-4)           # a crust: it stands above the metal it ate
        self.assertGreater(float(np.percentile(layers.H, 5)), 0.0)   # even its pits rarely reach back down to it
        self.assertGreater(float(layers.H.std()), 3e-5)              # scabbed and pitted, not a slab
        self.assertEqual(float(layers.M.max()), 0.0)
        self.assertGreater(float(np.median(layers.R)), .75)          # rough, never glossy

    def test_a_coarse_face_is_given_noise_it_can_hold(self):
        points = np.random.default_rng(2).random((6000, 3)).astype(np.float32)
        fine = hs.Field(self.noise, self.palette, P=points, texel=np.full(6000, .0001, np.float32)).fbm(.016, 5)
        coarse = hs.Field(self.noise, self.palette, P=points, texel=np.full(6000, .004, np.float32)).fbm(.016, 5)
        self.assertLess(float(coarse.std()), float(fine.std()) * .95)    # band-limited to the texel, so it cannot alias into grain
        gone = hs.Field(self.noise, self.palette, P=points, texel=np.full(6000, .004, np.float32)).band(.003, 5)
        self.assertEqual(float(np.abs(gone).max()), 0.0)             # a 3 mm feature is not asked of a 4 mm texel

    def test_an_unannotated_mesh_still_says_what_is_round_and_which_way_it_runs(self):
        maps = {k: v for k, v in self.maps.items() if k != "dome"}
        labels, count, _, _ = hs._islands(maps["valid"], maps["pos"])
        normal = maps["nrm"][maps["valid"]]
        curved, grain, dome = hs.derive_attributes(labels, count, maps["valid"], maps["pos"], normal)
        rail = maps["cls"][maps["valid"]] == 2
        self.assertTrue(curved[rail].all())
        self.assertFalse(curved[~rail].any())
        self.assertGreater(float(np.abs(grain[rail][:, 0]).mean()), .98)     # the tube runs along X, and so does its grain
        self.assertEqual(float(dome.max()), 0.0)                     # a long tube is not a rivet head
        result = hs.paint(maps, RECIPE, self.palette, self.classes, self.noise)
        self.assertEqual(result["stats"]["annotated"], [])

    def test_rust_runs_down_from_a_fastener_not_up(self):
        maps = self.maps
        index = np.flatnonzero((maps["valid"] & (maps["cls"] == 1)).ravel())
        field = hs.Field(self.noise, self.palette, P=maps["pos"].reshape(-1, 3)[index], N=maps["nrm"].reshape(-1, 3)[index])
        head = maps["fasteners"][0]
        for seed in range(40):                                       # some fasteners stay clean; find one that runs
            run = hs.drips(field, maps["fasteners"], seed)
            if run.max() > 0:
                break
        self.assertGreater(float(run.max()), 0.0)
        below = field.P[:, 2] < head[2] - .004
        above = field.P[:, 2] > head[2] + .004
        self.assertGreater(float(run[below].max()), 0.0)
        self.assertEqual(float(run[above].max()), 0.0)

    def test_what_it_will_not_guess(self):
        with self.assertRaisesRegex(hs.HardSurfaceError, "no class for 'rail'"):
            hs.paint(self.maps, {"classes": {"deck": "tread_plate", "panel": "old_teal_paint"}}, self.palette, self.classes, self.noise)
        with self.assertRaisesRegex(hs.HardSurfaceError, "does not define"):
            hs.paint(self.maps, {"classes": {**RECIPE["classes"], "rail": "chrome"}}, self.palette, self.classes, self.noise)
        with self.assertRaisesRegex(hs.HardSurfaceError, "lack 'bev'"):
            hs.paint({k: v for k, v in self.maps.items() if k != "bev"}, RECIPE, self.palette, self.classes, self.noise)
        broken = json.loads(json.dumps(PROFILE))
        broken["classes"]["old_teal_paint"]["coat"] = "mauve"
        with self.assertRaisesRegex(hs.HardSurfaceError, "palette colour"):
            hs.load_profile(broken)
        del broken["palette"]["rust_mid"]
        with self.assertRaisesRegex(hs.HardSurfaceError, "lacks rust_mid"):
            hs.load_profile(broken)

    def test_the_stage_is_registered_and_its_script_is_there(self):
        from reference_asset_compiler import stages
        for name in ("bake-surface-maps", "hard-surface-finish"):
            self.assertTrue((ROOT / stages.STAGES[name]["script"]).is_file(), name)
        self.assertEqual(stages.STAGES["bake-surface-maps"]["runner"], "blender")
        self.assertEqual(stages.STAGES["hard-surface-finish"]["produces"], hs.RECEIPT_SCHEMA)


def quad_glb():
    """One square with UV0 across the whole atlas, as a GLB."""
    positions = np.array([[0, 0, 0], [.5, 0, 0], [.5, .5, 0], [0, .5, 0]], "<f4")
    uvs = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], "<f4")
    indices = np.array([0, 1, 2, 0, 2, 3], "<u2")
    blob = positions.tobytes() + uvs.tobytes() + indices.tobytes()
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2}]}],
           "buffers": [{"byteLength": len(blob)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48}, {"buffer": 0, "byteOffset": 48, "byteLength": 32},
                           {"buffer": 0, "byteOffset": 80, "byteLength": 12}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3", "min": [0, 0, 0], "max": [.5, .5, 0]},
                         {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC2"},
                         {"bufferView": 2, "componentType": 5123, "count": 6, "type": "SCALAR"}]}
    return write_glb(doc, blob)


class HardSurfaceFinishStage(unittest.TestCase):
    def run_stage(self, folder, recipe, name="finished"):
        (folder / "recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "hard_surface_finish.py"), str(folder / "part.glb"),
                               str(folder / f"{name}.glb"), str(folder / f"{name}.json"), "--textures", str(folder / "recipe.json")],
                              capture_output=True, text=True, env={**__import__("os").environ, "RAC_NOISE_CACHE": str(folder / "noise")})

    def test_a_part_leaves_with_one_material_and_its_geometry_untouched(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = quad_glb()
            (folder / "part.glb").write_bytes(source)
            size = 64
            rows, cols = np.mgrid[0:size, 0:size].astype(np.float32)
            maps = {"valid": np.ones((size, size), bool), "pos": np.stack([cols / size * .5, (size - rows) / size * .5, np.zeros_like(rows)], -1),
                    "nrm": np.tile(np.array([0, 0, 1], np.float32), (size, size, 1)), "ao": np.ones((size, size, 3), np.float32),
                    "bev": np.tile(np.array([0, 0, 1, 1], np.float32), (size, size, 1)), "cls": np.zeros((size, size), np.uint8),
                    "class_names": np.array(["plate"])}
            held = io.BytesIO()
            np.savez_compressed(held, **maps)
            (folder / "maps.npz").write_bytes(held.getvalue())

            def sha(data):
                return hashlib.sha256(data).hexdigest()
            recipe = {"schema": hs.RECIPE_SCHEMA, "source_sha256": sha(source), "maps": "maps.npz", "maps_sha256": sha(held.getvalue()),
                      "classes": {"plate": "plain_plate"}, "masters": True}
            done = self.run_stage(folder, recipe)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("HARD_SURFACE_FINISH_COMPLETE", done.stdout)
            receipt = json.loads((folder / "finished.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], hs.RECEIPT_SCHEMA)
            self.assertEqual(receipt["output_sha256"], sha((folder / "finished.glb").read_bytes()))
            self.assertEqual(receipt["classes"]["plate"]["kind"], "plain_plate")
            doc, binary = read_glb((folder / "finished.glb").read_bytes())
            original, original_binary = read_glb(source)
            self.assertEqual(binary[:len(original_binary)], original_binary)             # the mesh's own bytes, untouched
            self.assertEqual(doc["accessors"], original["accessors"])
            self.assertEqual(len(doc["materials"]), 1)
            material = doc["materials"][0]
            self.assertEqual(material["occlusionTexture"]["index"], material["pbrMetallicRoughness"]["metallicRoughnessTexture"]["index"])
            self.assertEqual(doc["meshes"][0]["primitives"][0]["material"], 0)
            for image in doc["images"]:
                view = doc["bufferViews"][image["bufferView"]]
                self.assertEqual(binary[view["byteOffset"]:view["byteOffset"] + 8], b"\x89PNG\r\n\x1a\n")
            for suffix in ("BaseColor", "Normal", "ORM"):
                self.assertTrue((folder / f"finished_{suffix}.png").is_file())
            # an earlier attempt keeps its receipt: the same output is refused
            again = self.run_stage(folder, recipe)
            self.assertNotEqual(again.returncode, 0)
            # and a recipe bound to another mesh is refused before anything is painted
            refused = self.run_stage(folder, {**recipe, "source_sha256": "0" * 64}, name="other")
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("binds a different source", refused.stderr)
            self.assertFalse((folder / "other.glb").exists())

    def test_struct_is_what_a_glb_header_says(self):
        raw = quad_glb()
        self.assertEqual(struct.unpack_from("<4sII", raw), (b"glTF", 2, len(raw)))


if __name__ == "__main__":
    unittest.main()
