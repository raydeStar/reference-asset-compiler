from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.glb_skeleton import (  # noqa: E402
    GlbSkeletonError,
    read_document,
    read_skeleton,
    skeleton_joints,
)
from reference_asset_compiler.skeleton_fingerprint import skeleton_fingerprint  # noqa: E402


def glb(document: dict) -> bytes:
    """A GLB carrying only a JSON chunk, which is all a skeleton read needs."""
    chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    if len(chunk) % 4:
        chunk += b" " * (4 - len(chunk) % 4)
    header = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(chunk))
    return header + struct.pack("<II", len(chunk), 0x4E4F534A) + chunk


RIGGED = {
    "asset": {"version": "2.0"},
    "nodes": [
        {"name": "Figure", "mesh": 0, "skin": 0},
        # The armature stands above the skeleton and is not a joint itself.
        {"name": "Armature", "children": [2]},
        {"name": "Hips", "children": [3], "translation": [0.0, 0.95, 0.0]},
        {"name": "Spine", "translation": [0.0, 0.1234565, 0.0],
         "rotation": [0.0, 0.0, 0.3826834, 0.9238795]},
    ],
    "skins": [{"joints": [2, 3]}],
    "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
}


class GlbSkeletonTests(unittest.TestCase):
    def read(self, document: dict):
        with tempfile.TemporaryDirectory(prefix="rac-skeleton-") as raw:
            path = Path(raw) / "payload.glb"
            path.write_bytes(glb(document))
            return read_skeleton(path)

    def test_joints_are_read_with_their_parents_and_rest_transforms(self):
        joints = self.read(RIGGED)

        self.assertEqual([joint["name"] for joint in joints], ["Hips", "Spine"])
        # The armature above the skeleton is scene structure, not identity.
        self.assertIsNone(joints[0]["parent"])
        self.assertEqual(joints[1]["parent"], "Hips")
        self.assertEqual(joints[0]["translation"], (0.0, 0.95, 0.0))
        self.assertEqual(joints[1]["rotation"], (0.0, 0.0, 0.3826834, 0.9238795))
        # A joint that states no scale rests at unit scale.
        self.assertEqual(joints[1]["scale"], (1.0, 1.0, 1.0))

    def test_the_read_skeleton_fingerprints_to_the_shared_worked_example(self):
        # The same two joints as the contract's worked example, so the file
        # route and the in-memory route agree on one string.
        self.assertEqual(
            skeleton_fingerprint(self.read(RIGGED)),
            "18c20df3170c39e2b00a889d44b9f38c2b6309aae636ce1e091e82736058d589",
        )

    def test_a_prop_has_no_skeleton_and_that_is_not_a_failure(self):
        document = dict(RIGGED)
        document.pop("skins")
        self.assertEqual(self.read(document), [])

    def test_a_file_that_is_not_a_readable_glb_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="rac-skeleton-") as raw:
            root = Path(raw)
            short = root / "short.glb"
            short.write_bytes(b"glTF")
            wrong = root / "wrong.glb"
            wrong.write_bytes(b"NOPE" + glb(RIGGED)[4:])
            truncated = root / "truncated.glb"
            truncated.write_bytes(glb(RIGGED)[:-8])

            for path in (short, wrong, truncated):
                with self.assertRaises(GlbSkeletonError):
                    read_document(path)

    def test_a_skin_that_does_not_resolve_is_refused_rather_than_guessed_at(self):
        dangling = json.loads(json.dumps(RIGGED))
        dangling["skins"][0]["joints"] = [99]
        repeated = json.loads(json.dumps(RIGGED))
        repeated["skins"][0]["joints"] = [2, 2]

        for document in (dangling, repeated):
            with self.assertRaises(GlbSkeletonError):
                skeleton_joints(document)

    def test_an_unnamed_joint_still_has_a_stable_identity(self):
        unnamed = json.loads(json.dumps(RIGGED))
        unnamed["nodes"][3].pop("name")

        joints = self.read(unnamed)
        self.assertEqual(joints[1]["name"], "Bone 3")


if __name__ == "__main__":
    unittest.main()
