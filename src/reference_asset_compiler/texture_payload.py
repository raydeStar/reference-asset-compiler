"""Bind texture packaging reports to the actual mesh, maps and gate result."""

from pathlib import Path
from typing import Any

from .io import sha256_file


def bind_texture_payload(
    payload: dict[str, Any], source: Path, output: Path, gate: Path,
) -> dict[str, Any]:
    """Record bytes produced by this attempt; a filename is not a family tree."""
    return {
        **payload,
        "source_uv_authority": str(source.resolve()),
        "source_uv_authority_sha256": sha256_file(source),
        "output_fbx": output.name,
        "output_fbx_sha256": sha256_file(output),
        "baked_sha256": {
            channel: sha256_file(output.parent / filename)
            for channel, filename in payload["baked"].items()
        },
        "gate_texture_sha256": sha256_file(gate),
    }
