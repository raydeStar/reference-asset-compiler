"""Convert a passing feature-fairing diagnostic into canonical retopology evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler.io import read_json, sha256_file


def checked_path(record: dict, key: str = "path") -> Path:
    path = Path(str(record.get(key, ""))).resolve()
    if not path.is_file():
        raise FileNotFoundError("Feature-fairing evidence is missing: {0}".format(path))
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fairing_report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report_path = args.fairing_report.resolve()
    output_path = args.output.resolve()
    if output_path.exists():
        raise RuntimeError("Refusing to overwrite canonical retopology evidence")
    report = read_json(report_path)
    if report.get("schema") != "reference-asset-compiler.feature-fairing-candidate.v1":
        raise ValueError("Input is not a feature-fairing report")
    if report.get("status") != "mechanical_pass" or report.get("failures") not in ([], None):
        raise ValueError("Feature-fairing diagnostic did not pass")

    authority = report.get("authority") or {}
    source = report.get("source") or {}
    candidate = report.get("output") or {}
    authority_path = checked_path(authority)
    source_path = checked_path(source)
    candidate_path = checked_path(candidate)
    review_path = checked_path(candidate, "review_glb")
    expected = {
        authority_path: authority.get("sha256"),
        source_path: source.get("sha256"),
        candidate_path: candidate.get("sha256"),
        review_path: candidate.get("review_glb_sha256"),
    }
    for path, digest in expected.items():
        if sha256_file(path) != digest:
            raise ValueError("Feature-fairing evidence hash drifted: {0}".format(path))

    canonical = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass",
        "method": "paired_feature_qem_with_feature_weighted_taubin_fairing",
        "purpose": "Downstream cleanup of AI-derived topology; no image reconstruction.",
        "source": {"path": str(authority_path), "sha256": authority["sha256"]},
        "topology_base": {"path": str(source_path), "sha256": source["sha256"]},
        "fairing_report": {"path": str(report_path), "sha256": sha256_file(report_path)},
        "settings": report.get("settings"),
        "protection": report.get("protection"),
        "roughness": report.get("roughness"),
        "displacement": report.get("displacement"),
        "output": candidate,
        "symmetric_surface_deviation": report.get("symmetric_surface_deviation"),
        "failures": [],
        "requires_fixed_view_review": True,
        "requires_deformation_flow_review": True,
        "known_review_risks": [
            "slight residual broad-surface waviness",
            "joint regions retain non-semantic paired-QEM flow and require deformation validation",
        ],
        "production_grade": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
    print("RAC_CANONICAL_FEATURE_FAIRING_REPORT_OK {0}".format(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
