"""Read a skeleton out of an exported GLB, which is where it has to be read.

The browser studio contract fingerprints a skeleton from the values the payload
actually stores, not from the values an authoring scene held before export. Two
numbers differing in the seventh significant digit can land on opposite sides of
a quantization boundary as 64-bit doubles and on the same side as the 32-bit
floats a glTF file stores, so a fingerprint taken from Blender's memory is not
guaranteed to match one taken from the file afterwards. This reads the file.

Only the JSON chunk is parsed. A skeleton's rest transforms live on the nodes,
so no accessor data is touched and the cost does not scale with the geometry.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A


class GlbSkeletonError(ValueError):
    """The file cannot be read as a GLB carrying a skeleton."""


def read_document(path: Path) -> dict[str, Any]:
    """The glTF JSON chunk of a binary GLB, and nothing else."""
    data = Path(path).read_bytes()
    if len(data) < 20:
        raise GlbSkeletonError("This file is too short to be a GLB container.")
    magic, version, declared = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise GlbSkeletonError("This file is not a GLB container.")
    if version != 2:
        raise GlbSkeletonError("Only GLB version 2 is supported; this declares {0}.".format(version))
    if declared != len(data):
        raise GlbSkeletonError("This GLB is truncated or padded: the header length does not match.")

    offset = 12
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + length > len(data):
            raise GlbSkeletonError("This GLB is truncated: a chunk claims more bytes than the file holds.")
        if kind == JSON_CHUNK:
            try:
                return json.loads(data[offset:offset + length].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as problem:
                raise GlbSkeletonError("This GLB's JSON chunk could not be read.") from problem
        offset += length
    raise GlbSkeletonError("This GLB has no JSON chunk.")


def skeleton_joints(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The first skin's joints, as the fingerprint wants them.

    A parent is only reported when it is itself a joint of the same skin: the
    node above the root of a skeleton is scene structure, not part of the
    skeleton's identity.
    """
    skins = document.get("skins") or []
    if not skins:
        return []
    nodes = document.get("nodes") or []

    joints = skins[0].get("joints") or []
    if any(not isinstance(index, int) or index < 0 or index >= len(nodes) for index in joints):
        raise GlbSkeletonError("This skin names joints that are not nodes in this file.")
    if len(set(joints)) != len(joints):
        raise GlbSkeletonError("This skin names the same joint more than once.")

    parent_of: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children") or []:
            if isinstance(child, int) and 0 <= child < len(nodes):
                parent_of[child] = index

    within = set(joints)
    read = []
    for index in joints:
        node = nodes[index]
        parent = parent_of.get(index)
        read.append({
            "name": node.get("name") or "Bone {0}".format(index),
            "parent": nodes[parent].get("name") or "Bone {0}".format(parent)
            if parent is not None and parent in within else None,
            "translation": tuple(node.get("translation", (0.0, 0.0, 0.0))),
            "rotation": tuple(node.get("rotation", (0.0, 0.0, 0.0, 1.0))),
            "scale": tuple(node.get("scale", (1.0, 1.0, 1.0))),
        })
    return read


def read_skeleton(path: Path) -> list[dict[str, Any]]:
    """The joints of the first skin in a GLB file, or an empty list for a prop."""
    return skeleton_joints(read_document(path))
