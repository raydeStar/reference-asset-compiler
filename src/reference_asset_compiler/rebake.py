"""Chaining a re-bake after a reduction: what binds the two, and what to try next.

``reduce-mesh`` collapses a painted mesh and measures how far its surface moved;
``rebake-maps`` puts the paint back and judges it by eye. The reduction's
receipt is what joins them. It names the dense source and the reduced output by
hash, so a re-bake given that receipt can refuse a dense mesh or a candidate
that is not the pair the reduction measured -- a bake between the wrong two
files transfers somebody else's paint without any error at all.

The receipt also carries the budget ladder. Reduction climbed it until the
surface gates were satisfied; when the re-baked candidate then fails the
appearance gate, the next rung is where to go, with the same gates, the same
role and the same mode, so the two stages climb one ladder rather than two.

Nothing here touches Blender, so all of it can be tested anywhere.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "reference-asset-compiler.rebake-maps.v1"
REDUCTION_SCHEMA = "reference-asset-compiler.production-retopology-candidate.v1"
MESH_SUFFIXES = (".blend", ".glb", ".gltf")


class RebakeError(ValueError):
    """A re-bake that would pair the wrong files or cannot be attempted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_reduction(path: Path) -> dict[str, Any]:
    """A reduction receipt, or a refusal saying why it is not one."""
    path = Path(path)
    if not path.is_file():
        raise RebakeError("The reduction receipt does not exist: {0}".format(path))
    try:
        receipt = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as problem:
        raise RebakeError("The reduction receipt is not JSON: {0}".format(problem)) from problem
    if receipt.get("schema") != REDUCTION_SCHEMA:
        raise RebakeError("{0} is not a reduction receipt (schema {1!r}).".format(
            path.name, receipt.get("schema")))
    return receipt


def check_binding(receipt: dict[str, Any], dense: Path, reduced: Path) -> dict[str, Any]:
    """Prove the dense and reduced files are the pair this reduction measured."""
    if receipt.get("status") != "mechanical_pass":
        raise RebakeError(
            "That reduction was {0}, so there is no accepted candidate to re-bake.".format(
                receipt.get("status") or "never finished"))
    source = receipt.get("source") or {}
    output = receipt.get("output") or {}
    dense_sha = sha256_file(dense)
    if dense_sha != source.get("sha256"):
        raise RebakeError(
            "The dense mesh is not the one this reduction was made from: {0} hashes to {1}, "
            "the receipt names {2}.".format(Path(dense).name, dense_sha[:12],
                                            str(source.get("sha256"))[:12]))
    reduced_sha = sha256_file(reduced)
    if reduced_sha == output.get("sha256"):
        reduced_is = "native"
    elif reduced_sha == output.get("review_glb_sha256"):
        reduced_is = "review_glb"
    else:
        raise RebakeError(
            "The reduced mesh is not this reduction's output: {0} matches neither its .blend "
            "nor its GLB.".format(Path(reduced).name))
    settings = receipt.get("settings") or {}
    return {
        "dense_sha256": dense_sha,
        "reduced_sha256": reduced_sha,
        "reduced_is": reduced_is,
        "triangle_budget": settings.get("triangle_budget"),
        "triangles": output.get("triangles"),
        "mode": receipt.get("mode"),
    }


def remaining_rungs(receipt: dict[str, Any]) -> list[int]:
    """The rungs above the one the reduction settled on, still below the source."""
    decision = receipt.get("budget_decision") or {}
    ladder = decision.get("ladder") or []
    settings = receipt.get("settings") or {}
    if not ladder or settings.get("triangle_budget") is None:
        # An explicit number was one attempt by request, and a kept source was
        # never reduced: neither offers anywhere to climb to.
        return []
    current = int(settings["triangle_budget"])
    source = int(((receipt.get("source") or {}).get("topology") or {}).get("triangles") or 0)
    return [int(rung) for rung in ladder if int(rung) > current and (not source or int(rung) < source)]


def reduction_options(receipt: dict[str, Any], rung: int) -> dict[str, Any]:
    """reduce-mesh options for the next rung: the same gates, role and mode as before."""
    settings = receipt.get("settings") or {}
    decision = receipt.get("budget_decision") or {}
    options = {
        "triangle_budget": int(rung),
        "maximum_p99_m": settings.get("maximum_p99_m"),
        "maximum_max_m": settings.get("maximum_max_m"),
        "weight_factor": settings.get("weight_factor"),
        "asset_name": decision.get("name"),
        "role": decision.get("role"),
        "runtime_derivative": True if receipt.get("mode") == "runtime-derivative" else None,
    }
    return {key: value for key, value in options.items() if value is not None}


def triangle_savings(dense_triangles: int, runtime_triangles: int) -> dict[str, Any]:
    dense_triangles, runtime_triangles = int(dense_triangles), int(runtime_triangles)
    saved = dense_triangles - runtime_triangles
    return {
        "dense_triangles": dense_triangles,
        "runtime_triangles": runtime_triangles,
        "triangles_saved": saved,
        "share_saved": round(saved / dense_triangles, 4) if dense_triangles else 0.0,
    }


def reusable_views(manifest_path: Path, reference: Path, resolution: int, samples: int) -> bool:
    """Whether views rendered earlier are of this exact reference, taken the same way."""
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return False
    device = manifest.get("device") or {}
    return (manifest.get("source_sha256") == sha256_file(reference)
            and int(manifest.get("resolution") or 0) == int(resolution)
            and int(device.get("samples") or 0) == int(samples)
            and not manifest.get("framing_borrowed")
            and all((manifest_path.parent / item["file"]).is_file()
                    for item in manifest.get("views", [])))
