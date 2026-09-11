"""Small deterministic filesystem helpers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    # utf-8-sig: PowerShell 5.1 prefixes a BOM that json.loads otherwise rejects.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace a complete file: interrupted writes must not eat yesterday's ledger.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".rac-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def encode_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2) + "\n"


def write_retained_json(path: Path, value: dict[str, Any]) -> Path:
    """Atomically write a receipt that may be re-derived but never silently changed."""
    encoded = encode_json(value)
    def existing() -> None:
        if path.read_text(encoding="utf-8-sig") != encoded:
            raise ValueError("refusing to overwrite different retained evidence: {0}".format(path))

    if path.exists():
        existing()
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".rac-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is complete and exclusive: a concurrent writer
        # may win the name, but cannot have its receipt replaced by ours.
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing()
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_directory(source: Path, destination: Path) -> Path:
    """Publish a complete directory, tolerating only transient Windows file locks."""
    for attempt in range(6):
        if destination.exists():
            raise FileExistsError("Refusing to overwrite published directory: {0}".format(destination))
        try:
            return source.rename(destination)
        except PermissionError as error:
            if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 5:
                raise
            # Antivirus/indexing can briefly hold a fresh output directory open.
            # Retry only the rename, never the compiler or an inference process.
            time.sleep(0.1 * (attempt + 1))
    raise AssertionError("unreachable")


def slugify(value: str) -> str:
    cleaned = "-".join(value.strip().lower().replace("_", "-").split())
    cleaned = "".join(character for character in cleaned if character.isalnum() or character == "-")
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    if not cleaned:
        raise ValueError("Asset id must contain at least one letter or number")
    return cleaned
