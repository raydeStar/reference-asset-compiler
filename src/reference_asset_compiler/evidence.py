"""Shared ledger evidence helpers: portable paths, receipt lookup, integrity."""

from __future__ import annotations

import re
import string
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .io import read_json, sha256_file

_DRIVE_ABSOLUTE = re.compile(r"^[A-Za-z]:[/\\]")
IMPORT_SCHEMA = "reference-asset-compiler.ue5-import-evidence.v1"


def is_sha256(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(character in string.hexdigits for character in value))


def is_portable_absolute(value: str) -> bool:
    """True for POSIX-absolute, UNC, and drive-letter paths on every host."""
    return (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
            or bool(_DRIVE_ABSOLUTE.match(value)))


def evidence_display_path(job: Path, resolved: Path) -> str:
    """Job-relative when possible, always with forward slashes."""
    try:
        return resolved.relative_to(job).as_posix()
    except ValueError:
        return str(resolved).replace("\\", "/")


def resolve_evidence_path(job: Path, value: Any) -> Path:
    text = str(value or "").replace("\\", "/")
    if is_portable_absolute(text):
        return Path(text)
    return job / text


def record_evidence_paths(job: Path, record: dict[str, Any]) -> list[Path]:
    return [resolve_evidence_path(job, row.get("path"))
            for row in record.get("evidence", []) if isinstance(row, dict)]


def verified_evidence_hashes(job: Path, record: dict[str, Any]) -> set[str]:
    """Hashes of ledger rows whose file still exists and still matches."""
    hashes: set[str] = set()
    for row in record.get("evidence", []):
        if not isinstance(row, dict):
            continue
        resolved = resolve_evidence_path(job, row.get("path"))
        if resolved.is_file() and sha256_file(resolved) == row.get("sha256"):
            hashes.add(row["sha256"])
    return hashes


def verify_record_evidence(job: Path, stage: str, record: dict[str, Any]) -> list[str]:
    """Missing, re-hashed, or resized evidence rows, as audit failure strings."""
    failures: list[str] = []
    for row in record.get("evidence", []):
        resolved = resolve_evidence_path(job, row["path"])
        if not resolved.is_file():
            failures.append(f"Missing evidence for {stage}: {row['path']}")
        elif sha256_file(resolved) != row["sha256"]:
            failures.append(f"Evidence hash changed for {stage}: {row['path']}")
        elif resolved.stat().st_size != row["bytes"]:
            failures.append(f"Evidence size changed for {stage}: {row['path']}")
    return failures


def load_json_receipts(paths: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
    """Every readable JSON object among the paths; unreadable files are skipped."""
    receipts = []
    seen: set[Path] = set()
    for path in paths:
        if path.suffix.lower() != ".json" or not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            payload = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            receipts.append((path, payload))
    return receipts


def _superseded_hashes(matches: list[tuple[Path, dict[str, Any]]]) -> set[str]:
    """A native revision retires exactly the receipt its previous_import names."""
    retired = set()
    for _, payload in matches:
        revision = payload.get("native_revision")
        previous = revision.get("previous_import") if isinstance(revision, dict) else None
        if isinstance(previous, dict) and is_sha256(previous.get("sha256")):
            retired.add(previous["sha256"])
    return retired


def find_receipts(paths: list[Path], schema: str) -> list[tuple[Path, dict[str, Any]]]:
    """Active receipts of one schema; explicitly superseded receipts are excluded."""
    matches = [(path, payload) for path, payload in load_json_receipts(paths)
               if payload.get("schema") == schema]
    if len(matches) < 2:
        return matches
    retired = _superseded_hashes(matches)
    return [(path, payload) for path, payload in matches
            if not retired or sha256_file(path) not in retired]


def find_receipt(paths: list[Path], schema: str) -> tuple[Path, dict[str, Any]] | None:
    """The single active receipt of a schema; ambiguity is an error, not a guess."""
    matches = find_receipts(paths, schema)
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError("Evidence contains {0} active receipts of {1}: {2}".format(
            len(matches), schema, sorted(path.name for path, _ in matches)))
    return matches[0]


def record_receipt(
    job: Path, record: dict[str, Any], schema: str
) -> tuple[Path, dict[str, Any]] | None:
    return find_receipt(record_evidence_paths(job, record), schema)


def record_receipt_value(job: Path, record: dict[str, Any], schema: str, key: str) -> Any:
    found = record_receipt(job, record, schema)
    return found[1].get(key) if found else None


def stage_receipt(job: Path, state: dict[str, Any], stage: str, schema: str) -> dict[str, Any]:
    """The receipt a passed stage retained, or a ValueError naming what is missing."""
    record = state["stages"][stage]
    if record.get("status") != "passed":
        raise ValueError("{0} has not passed".format(stage))
    found = record_receipt(job, record, schema)
    if found is None:
        raise ValueError("{0} receipt is missing".format(stage))
    return found[1]
