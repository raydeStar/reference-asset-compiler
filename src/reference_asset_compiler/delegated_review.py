"""Explicit user-delegated visual review, never disguised as a human inspection.

Default human gates remain unchanged. A delegated pass additionally binds its
authorization, exact source image, stage, reviewer and every reviewed file.
This records consent supplied by an operator; it is not an authentication system.
"""
from pathlib import Path
from typing import Any

from .contracts import DELEGATED_REVIEWERS
from .io import read_json, sha256_file, write_json

AUTH_SCHEMA = "reference-asset-compiler.review-delegation.v1"
REVIEW_SCHEMA = "reference-asset-compiler.delegated-review.v1"


def validate_authorization(path: Path, reviewer: str, source_hash: str | None,
                           stage: str) -> dict[str, Any]:
    auth = read_json(path)
    if not isinstance(auth, dict):
        raise ValueError("Review delegation must be an object")
    grantor = str(auth.get("authorized_by") or "").strip()
    stages = auth.get("stages")
    if (auth.get("schema") != AUTH_SCHEMA or not grantor
            or grantor.lower() in DELEGATED_REVIEWERS
            or auth.get("reviewer") != reviewer
            or reviewer.lower() not in DELEGATED_REVIEWERS
            or not source_hash or auth.get("source_sha256") != source_hash
            or not isinstance(stages, list)
            or any(not isinstance(item, str) for item in stages)
            or stage not in stages
            or auth.get("mechanical_gates_waived") is not False
            or not str(auth.get("user_instruction") or "").strip()):
        raise ValueError("Invalid or out-of-scope user review delegation")
    return auth


def validate_delegated_review(evidence: list[Path], reviewer: str,
                              source_hash: str | None, stage: str) -> None:
    receipts = []
    for path in evidence:
        if path.suffix.lower() == ".json":
            try:
                payload = read_json(path)
            except (ValueError, OSError):
                continue
            if isinstance(payload, dict) and payload.get("schema") == REVIEW_SCHEMA:
                receipts.append((path, payload))
    if len(receipts) != 1:
        raise ValueError("Agent review requires exactly one user-delegated review receipt")
    receipt_path, receipt = receipts[0]
    authorization = receipt.get("authorization") or {}
    if not isinstance(authorization, dict) or not isinstance(authorization.get("path"), str):
        raise ValueError("Delegated review authorization is malformed")
    auth_path = Path(authorization.get("path", ""))
    if (not auth_path.is_file() or sha256_file(auth_path) != authorization.get("sha256")
            or auth_path.resolve() not in {p.resolve() for p in evidence}):
        raise ValueError("Delegated review authorization is missing or changed")
    validate_authorization(auth_path, reviewer, source_hash, stage)
    if (receipt.get("reviewer") != reviewer or receipt.get("stage") != stage
            or receipt.get("source_sha256") != source_hash
            or receipt.get("human_visual_review") is not False
            or receipt.get("status") != "approved"
            or not str(receipt.get("findings") or "").strip()):
        raise ValueError("Delegated review lacks an explicit successful agent verdict")
    expected = {str(p.resolve()): sha256_file(p) for p in evidence
                if p.resolve() not in {receipt_path.resolve(), auth_path.resolve()}}
    rows = receipt.get("reviewed_files")
    if (not isinstance(rows, list)
            or any(not isinstance(row, dict) or not isinstance(row.get("path"), str)
                   or not isinstance(row.get("sha256"), str) for row in rows)):
        raise ValueError("Delegated review artifact list is malformed")
    actual = {row["path"]: row["sha256"] for row in rows}
    if len(actual) != len(rows):
        raise ValueError("Delegated review repeats an artifact")
    if not expected or actual != expected:
        raise ValueError("Delegated review does not bind every exact reviewed artifact")


def record_delegated_review(output: Path, authorization: Path, reviewer: str,
                            source_hash: str, stage: str, evidence: list[Path],
                            findings: str) -> list[Path]:
    """Call only after visually inspecting the supplied artifacts, not as a gate runner."""
    validate_authorization(authorization, reviewer, source_hash, stage)
    if output.exists():
        raise ValueError("Retained delegated review must not be overwritten")
    payload = {"schema": REVIEW_SCHEMA, "stage": stage, "reviewer": reviewer,
               "source_sha256": source_hash, "status": "approved",
               "human_visual_review": False, "findings": findings,
               "authorization": {"path": str(authorization.resolve()),
                                 "sha256": sha256_file(authorization)},
               "reviewed_files": [{"path": str(p.resolve()), "sha256": sha256_file(p)}
                                  for p in evidence]}
    if not findings.strip() or not evidence:
        raise ValueError("A review needs findings and actual inspected artifacts")
    write_json(output, payload)
    paths = [*evidence, authorization, output]
    validate_delegated_review(paths, reviewer, source_hash, stage)
    return paths
