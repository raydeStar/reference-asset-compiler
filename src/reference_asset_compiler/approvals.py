"""Hash-bound human approval checks for visible asset gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import AUTOMATION_REVIEWERS
from .delegated_review import validate_delegated_review
from .evidence import record_evidence_paths, verified_evidence_hashes
from .io import read_json, sha256_file, write_retained_json
from .workspace import audit_workspace

MODELING_VIEW_NAMES = (
    "matcap-front.png",
    "matcap-three-quarter.png",
    "matcap-side.png",
    "matcap-back.png",
)

TEXTURE_VIEW_NAMES = (
    "beauty-front.png",
    "beauty-three-quarter.png",
    "beauty-side.png",
    "beauty-back.png",
)


def record_modeling_derivative(
    job: Path,
    source_ai_candidate: Path,
    modeling_candidate: Path,
    operations: list[str],
    derivation_artifacts: list[Path] | None = None,
) -> tuple[Path, list[Path]]:
    """Bind a reviewed modeling mesh to the exact AI candidate and allowed transforms."""
    job = job.resolve()
    source_ai_candidate = source_ai_candidate.resolve()
    modeling_candidate = modeling_candidate.resolve()
    artifacts = [path.resolve() for path in (derivation_artifacts or [])]
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    generated = read_json(job / "state.json")["stages"]["generate_candidates"]
    if generated.get("status") != "passed":
        raise ValueError("generate_candidates has not passed")
    generated_hashes = _evidence_hashes(job, generated)
    source_hash = sha256_file(source_ai_candidate)
    if source_hash not in generated_hashes:
        raise ValueError("modeling derivation does not begin at the ledger AI candidate")
    for path in [modeling_candidate, *artifacts]:
        if not path.is_file():
            raise ValueError("modeling derivation artifact is missing: {0}".format(path))
    payload = {
        "schema": "reference-asset-compiler.modeling-derivative-lineage.v1",
        "source_ai_candidate_sha256": source_hash,
        "modeling_candidate_sha256": sha256_file(modeling_candidate),
        "operations": operations,
        "derivation_artifacts": [
            {"role": path.stem, "path": str(path), "sha256": sha256_file(path)}
            for path in artifacts
        ],
        "ok": True,
    }
    output = job / "modeling" / "modeling-lineage.json"
    try:
        write_retained_json(output, payload)
    except ValueError as error:
        raise ValueError("refusing to overwrite different modeling lineage evidence") from error
    return output, artifacts


_evidence_hashes = verified_evidence_hashes


def _require_identified_reviewer(job: Path, record: dict[str, Any], stage: str) -> str:
    """Same rule as promote_stage: automation identities need hash-bound delegation."""
    approved_by = str(record.get("approved_by") or "").strip()
    if not approved_by:
        raise ValueError("{0} requires an identified human reviewer".format(stage))
    if approved_by.lower() in AUTOMATION_REVIEWERS:
        source_hash = read_json(job / "intake.json").get("source", {}).get("sha256")
        try:
            validate_delegated_review(
                record_evidence_paths(job, record), approved_by, source_hash, stage)
        except ValueError as error:
            raise ValueError("{0} requires an identified human reviewer or explicit "
                             "hash-bound user delegation: {1}".format(stage, error)) from error
    return approved_by


def validate_generated_candidate(job: Path, candidate: Path, report: Path) -> dict[str, Any]:
    """Require the generate-candidates ledger row to name this exact run."""
    job = job.resolve()
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    record = read_json(job / "state.json")["stages"]["generate_candidates"]
    if record.get("status") != "passed":
        raise ValueError("generate_candidates has not passed")
    hashes = _evidence_hashes(job, record)
    required = {sha256_file(candidate.resolve()), sha256_file(report.resolve())}
    if not required.issubset(hashes):
        raise ValueError("generate_candidates evidence does not bind this mesh and AI report")
    return record


def validate_modeling_approval(
    job: Path, candidate: Path, fixed_view_directory: Path
) -> dict[str, Any]:
    """Require a human identity plus candidate and four neutral fixed views."""
    job = job.resolve()
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    record = read_json(job / "state.json")["stages"]["modeling_approval"]
    if record.get("status") != "passed":
        raise ValueError("modeling_approval has not passed")
    _require_identified_reviewer(job, record, "modeling_approval")

    candidate = candidate.resolve()
    view_directory = fixed_view_directory.resolve()
    required_paths = [candidate, *(view_directory / name for name in MODELING_VIEW_NAMES)]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise ValueError("required modeling evidence is missing: {0}".format(missing))
    hashes = _evidence_hashes(job, record)
    absent = [path.name for path in required_paths if sha256_file(path) not in hashes]
    if absent:
        raise ValueError("modeling_approval does not include: {0}".format(", ".join(absent)))
    return record


def texture_evidence_paths(production_directory: Path, retopo: dict[str, Any]) -> list[Path]:
    """Return the exact payload and lit views a texture reviewer must approve."""
    production_directory = production_directory.resolve()
    baked = retopo.get("baked") or {}
    payloads = list(production_directory.glob("*_production.fbx"))
    if len(payloads) != 1:
        raise ValueError("expected one production FBX, found {0}".format(len(payloads)))
    paths = [
        payloads[0],
        production_directory / "retopo.json",
        production_directory / "gate-tex.json",
        *(production_directory / value for value in baked.values()),
        *(production_directory / "turn" / name for name in TEXTURE_VIEW_NAMES),
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def validate_texture_approval(
    job: Path, production_directory: Path, retopo: dict[str, Any]
) -> dict[str, Any]:
    """Require a human review of exact baked maps, payload, and lit fixed views."""
    job = job.resolve()
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    record = read_json(job / "state.json")["stages"]["texture_approval"]
    if record.get("status") != "passed":
        raise ValueError("texture_approval has not passed")
    _require_identified_reviewer(job, record, "texture_approval")
    required_paths = texture_evidence_paths(production_directory, retopo)
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise ValueError("required texture evidence is missing: {0}".format(missing))
    hashes = _evidence_hashes(job, record)
    absent = [path.name for path in required_paths if sha256_file(path) not in hashes]
    if absent:
        raise ValueError("texture_approval does not include: {0}".format(", ".join(absent)))
    return record
