"""Placing derivatives in a studio's revision stacks, without a studio.

What matters is refused before anything is sent -- a file the studio would
reject, an id that is not one -- and that the two calls carry what the studio
needs: the file under the field and header it insists on, then the new asset
placed under the original with a note saying how it was made.
"""

import importlib.util
import json
import struct
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publish_studio_revisions", ROOT / "scripts" / "publish_studio_revisions.py")
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


def glb(path: Path, image_bytes: int = 64) -> Path:
    """A minimal GLB with one embedded image of the given size."""
    document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": image_bytes}],
                "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": image_bytes}],
                "images": [{"bufferView": 0, "mimeType": "image/png"}]}
    text = json.dumps(document).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary = b"\x00" * image_bytes
    body = struct.pack("<II", len(text), 0x4E4F534A) + text
    body += struct.pack("<II", len(binary), 0x004E4942) + binary
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    return path


class Checks(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.item = {"name": "cog-2m", "original_id": str(uuid.uuid4()),
                     "glb": str(glb(self.root / "runtime.glb"))}

    def test_a_publishable_item_is_described_by_its_size_and_hash(self):
        facts = publish.check(self.item)

        self.assertEqual(facts["texture_bytes"], 64)
        self.assertEqual(len(facts["sha256"]), 64)

    def test_a_missing_file_or_a_made_up_id_is_refused_before_sending(self):
        with self.assertRaises(publish.PublishError):
            publish.check({**self.item, "glb": str(self.root / "gone.glb")})
        with self.assertRaises(publish.PublishError):
            publish.check({**self.item, "original_id": "brazier"})

    def test_textures_over_the_studios_limit_are_refused_by_name(self):
        heavy = glb(self.root / "heavy.glb", image_bytes=4096)
        original = publish.MAXIMUM_TEXTURE_BYTES
        publish.MAXIMUM_TEXTURE_BYTES = 1024
        try:
            with self.assertRaises(publish.PublishError) as refusal:
                publish.check({**self.item, "glb": str(heavy)})
        finally:
            publish.MAXIMUM_TEXTURE_BYTES = original

        self.assertIn("textures", str(refusal.exception))


class Calls(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.original = str(uuid.uuid4())
        self.item = {"name": "cog-2m", "original_id": self.original,
                     "glb": str(glb(self.root / "runtime.glb")),
                     "prompt": "100,000 -> 15,000 triangles; paint re-baked",
                     "engine": "Reference Asset Compiler rebake-maps"}
        self.sent = []

    def studio(self, revision_status=200):
        def send(method, url, body=None, headers=None, timeout=600):
            self.sent.append((method, url, body, headers))
            if url.endswith("/api/assets/models"):
                return 200, {"id": "new-asset"}
            return revision_status, ({"revisionNumber": 2, "isCurrentRevision": True}
                                     if revision_status == 200 else {"error": "Conflict"})
        return send

    def test_the_file_goes_up_first_then_is_placed_under_the_original(self):
        placed = publish.publish(self.item, "http://127.0.0.1:5179/", send=self.studio())

        upload, revision = self.sent
        # The studio insists on this header and this field for a model upload.
        self.assertEqual(upload[3]["X-Storyboard-Studio"], "1")
        self.assertIn(b'name="file"', upload[2])
        self.assertTrue(revision[1].endswith("/api/assets/{0}/revisions".format(self.original)))
        request = json.loads(revision[2])
        self.assertEqual(request["assetId"], "new-asset")
        self.assertIn("re-baked", request["prompt"])
        self.assertEqual(placed["revision_number"], 2)

    def test_a_refused_placement_says_the_upload_happened(self):
        with self.assertRaises(publish.PublishError) as refusal:
            publish.publish(self.item, "http://127.0.0.1:5179", send=self.studio(409))

        # The file is in the library either way; the person needs to know which.
        self.assertIn("uploaded as new-asset", str(refusal.exception))

    def test_an_engine_name_longer_than_the_studio_keeps_is_trimmed_not_refused(self):
        publish.publish({**self.item, "engine": "x" * 300}, "http://s", send=self.studio())

        self.assertEqual(len(json.loads(self.sent[1][2])["engine"]), publish.ENGINE_LIMIT)


class Ledger(unittest.TestCase):
    def test_a_dry_run_sends_nothing_and_skips_what_was_placed_before(self):
        root = Path(tempfile.mkdtemp())
        items = [{"name": name, "original_id": str(uuid.uuid4()),
                  "glb": str(glb(root / "{0}.glb".format(name)))} for name in ("a", "b")]
        (root / "items.json").write_text(json.dumps(items), encoding="utf-8")
        (root / "ledger.json").write_text(json.dumps({"a": {"uploaded_asset_id": "x"}}),
                                          encoding="utf-8")

        code = publish.main(["--items", str(root / "items.json"),
                             "--ledger", str(root / "ledger.json"), "--dry-run"])

        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads((root / "ledger.json").read_text())), {"a"})


if __name__ == "__main__":
    unittest.main()
