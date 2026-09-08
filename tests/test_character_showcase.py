import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "showcase_packager",
    Path(__file__).resolve().parents[1] / "scripts/package_character_showcase.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.report = {
            "ok": True,
            "source_assets_saved": False,
            "frames_per_cycle": 12,
            "cycle_seconds": 1.0,
            "frames": [],
        }
        for i in range(12):
            payload = f"fixture-{i}".encode()
            name = f"walk-{i:03d}.png"
            (self.path / name).write_bytes(payload)
            self.report["frames"].append(
                {
                    "name": "walk",
                    "file": name,
                    "actual_position": i / 12,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "attachments": [{"socket": "head", "error_cm": 0}],
                    "bones": {"foot_l": [i, 0, 0], "foot_r": [-i, 0, 0]},
                }
            )
        self.save()

    def save(self):
        (self.path / "showcase.json").write_text(json.dumps(self.report))

    def test_accepts_complete_hash_bound_capture(self):
        self.assertTrue(module.validate_capture(self.path)["ok"])

    def test_rejects_changed_image(self):
        (self.path / "walk-000.png").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            module.validate_capture(self.path)

    def test_rejects_wrong_animation_time(self):
        self.report["frames"][3]["actual_position"] = 0
        self.save()
        with self.assertRaises(ValueError):
            module.validate_capture(self.path)

    def test_rejects_failed_attachment(self):
        self.report["frames"][0]["attachments"][0]["error_cm"] = 1
        self.save()
        with self.assertRaises(ValueError):
            module.validate_capture(self.path)

    def test_rejects_saved_asset_or_failed_capture(self):
        for key, value in [("source_assets_saved", True), ("ok", False)]:
            self.report[key] = value
            self.save()
            with self.assertRaises(ValueError):
                module.validate_capture(self.path)
            self.report[key] = not value

    def test_rejects_missing_frame(self):
        self.report["frames"].pop()
        self.save()
        with self.assertRaises(ValueError):
            module.validate_capture(self.path)

    def test_rejects_missing_hash(self):
        self.report["frames"][0].pop("sha256")
        self.save()
        with self.assertRaises(ValueError):
            module.validate_capture(self.path)

    def test_rejects_frozen_feet_despite_changing_pixels(self):
        for frame in self.report["frames"]:
            frame["bones"]["foot_l"] = [0, 0, 0]
        self.save()
        with self.assertRaises(ValueError):
            module.validate_capture(self.path)

    def test_rejects_duplicate_still_records(self):
        frame = dict(self.report["frames"][0], name="portrait")
        self.report["frames"].extend([frame, frame])
        self.save()
        with self.assertRaises(ValueError):
            module.validate_capture(self.path)


if __name__ == "__main__":
    unittest.main()
