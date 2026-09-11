"""Portable evidence paths, unambiguous receipt lookup, and BOM-tolerant JSON."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.evidence import (
    IMPORT_SCHEMA,
    evidence_display_path,
    find_receipt,
    find_receipts,
    record_evidence_paths,
    resolve_evidence_path,
)
from reference_asset_compiler.io import read_json, sha256_file, write_retained_json


class EvidencePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.job = Path(self.temporary.name) / "work" / "asset"
        self.job.mkdir(parents=True)

    def test_drive_and_posix_absolute_rows_are_not_joined_to_the_job(self) -> None:
        for value in ("D:/x/y.png", "D:\\x\\y.png", "/srv/evidence/y.png", "//server/share/y.png"):
            with self.subTest(value=value):
                resolved = resolve_evidence_path(self.job, value)
                self.assertFalse(str(resolved).startswith(str(self.job)), resolved)
                self.assertEqual("y.png", resolved.name)

    def test_relative_rows_resolve_inside_the_job_with_either_separator(self) -> None:
        for value in ("prod-v2/retopo.json", "prod-v2\\retopo.json"):
            with self.subTest(value=value):
                self.assertEqual(self.job / "prod-v2" / "retopo.json",
                                 resolve_evidence_path(self.job, value))

    def test_display_paths_are_job_relative_with_forward_slashes(self) -> None:
        inside = self.job / "prod-v2" / "retopo.json"
        outside = Path(self.temporary.name) / "out" / "asset.fbx"
        self.assertEqual("prod-v2/retopo.json", evidence_display_path(self.job, inside))
        self.assertNotIn("\\", evidence_display_path(self.job, outside))
        self.assertEqual(outside, resolve_evidence_path(
            self.job, evidence_display_path(self.job, outside)))

    def test_state_rows_written_with_mixed_separators_resolve_on_this_host(self) -> None:
        target = self.job / "validation" / "frame.png"
        target.parent.mkdir()
        target.write_bytes(b"frame")
        record = {"evidence": [
            {"path": "validation/frame.png"},
            {"path": "validation\\frame.png"},
            {"path": str(target).replace("\\", "/")},
        ]}
        resolved = record_evidence_paths(self.job, record)
        self.assertTrue(all(path.is_file() for path in resolved), resolved)
        self.assertEqual(1, len({path.resolve() for path in resolved}))


class ReceiptLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def receipt(self, name: str, **fields) -> Path:
        path = self.root / name
        path.write_text(json.dumps({"schema": IMPORT_SCHEMA, **fields}), encoding="utf-8")
        return path

    def test_two_active_receipts_of_one_schema_are_an_error(self) -> None:
        first = self.receipt("ue5-import.json", asset_id="a")
        second = self.receipt("ue5-import-v2.json", asset_id="a")
        with self.assertRaisesRegex(ValueError, "2 active receipts"):
            find_receipt([first, second], IMPORT_SCHEMA)

    def test_the_same_receipt_listed_twice_is_not_ambiguous(self):
        receipt = self.receipt("ue5-import.json", asset_id="a")
        self.assertEqual(receipt, find_receipt([receipt, receipt], IMPORT_SCHEMA)[0])

    def test_native_revision_supersedes_exactly_the_receipt_it_names(self) -> None:
        first = self.receipt("ue5-import.json", asset_id="a")
        second = self.receipt(
            "ue5-import-native-v2.json", asset_id="a",
            native_revision={"id": "native-v2",
                             "previous_import": {"path": str(first),
                                                 "sha256": sha256_file(first)}})
        unrelated = self.root / "gallery.json"
        unrelated.write_text(json.dumps({"schema": "other"}), encoding="utf-8")
        found = find_receipt([first, unrelated, second], IMPORT_SCHEMA)
        self.assertEqual(second, found[0])
        self.assertEqual([second], [path for path, _ in find_receipts([first, second], IMPORT_SCHEMA)])

    def test_case_insensitive_json_suffix_and_unreadable_files_are_tolerated(self) -> None:
        upper = self.root / "RECEIPT.JSON"
        upper.write_text(json.dumps({"schema": IMPORT_SCHEMA}), encoding="utf-8")
        broken = self.root / "broken.json"
        broken.write_text("{", encoding="utf-8")
        found = find_receipt([broken, upper], IMPORT_SCHEMA)
        self.assertEqual(upper, found[0])
        self.assertIsNone(find_receipt([broken], IMPORT_SCHEMA))


class JsonIoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_bom_prefixed_receipts_from_powershell_parse(self) -> None:
        path = self.root / "gate-tex.json"
        path.write_text(json.dumps({"ok": True}), encoding="utf-8-sig")
        self.assertEqual({"ok": True}, read_json(path))

    def test_retained_write_is_idempotent_but_refuses_a_different_payload(self) -> None:
        path = self.root / "receipt.json"
        write_retained_json(path, {"ok": True})
        write_retained_json(path, {"ok": True})
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            write_retained_json(path, {"ok": False})
        self.assertEqual({"ok": True}, read_json(path))
        self.assertEqual([], list(self.root.glob(".rac-*")))

    def test_idempotent_retained_write_preserves_existing_bom_bytes(self):
        path = self.root / "retained.json"
        path.write_text(json.dumps({"ok": True}, indent=2) + "\n", encoding="utf-8-sig")
        before = path.read_bytes()
        write_retained_json(path, {"ok": True})
        self.assertEqual(before, path.read_bytes())

    def test_concurrent_retained_writer_cannot_replace_the_first_receipt(self):
        from unittest.mock import patch
        import os
        link = os.link
        path = self.root / "retained.json"

        def concurrent_winner(source, destination):
            destination.write_text('{"winner": "other recorder"}', encoding="utf-8")
            link(source, destination)

        with patch("reference_asset_compiler.io.os.link", side_effect=concurrent_winner):
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                write_retained_json(path, {"winner": "this recorder"})
        self.assertEqual({"winner": "other recorder"}, read_json(path))
        self.assertEqual([], list(self.root.glob(".rac-*")))

    def test_publication_waits_for_a_transient_windows_directory_lock(self):
        from unittest.mock import patch
        from reference_asset_compiler.io import publish_directory
        source, destination = self.root / "staged", self.root / "published"
        source.mkdir()
        (source / "payload").write_bytes(b"complete")
        rename = Path.rename
        denied = PermissionError("temporary directory lock")
        denied.winerror = 5
        calls = []

        def locked_once(path, target):
            calls.append(path)
            if len(calls) == 1:
                raise denied
            return rename(path, target)

        with patch.object(Path, "rename", locked_once), patch("reference_asset_compiler.io.time.sleep"):
            publish_directory(source, destination)
        self.assertEqual(2, len(calls))
        self.assertEqual(b"complete", (destination / "payload").read_bytes())

    def test_publication_refuses_an_authority_that_appears_during_a_lock(self):
        from unittest.mock import patch
        from reference_asset_compiler.io import publish_directory
        source, destination = self.root / "staged", self.root / "published"
        source.mkdir()
        denied = PermissionError("temporary directory lock")
        denied.winerror = 5

        def another_publisher(path, target):
            target.mkdir()
            (target / "payload").write_bytes(b"other publisher")
            raise denied

        with patch.object(Path, "rename", another_publisher), patch("reference_asset_compiler.io.time.sleep"):
            with self.assertRaises(FileExistsError):
                publish_directory(source, destination)
        self.assertEqual(b"other publisher", (destination / "payload").read_bytes())
        self.assertTrue(source.is_dir())


if __name__ == "__main__":
    unittest.main()
