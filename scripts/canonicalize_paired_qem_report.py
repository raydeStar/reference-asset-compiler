"""Convert a passing paired-QEM diagnostic into the canonical retopology report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler.io import read_json, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pairing_report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    pairing_path = args.pairing_report.resolve()
    output_path = args.output.resolve()
    if output_path.exists():
        raise RuntimeError("Refusing to overwrite canonical retopology evidence")
    pairing = read_json(pairing_path)
    source = pairing.get("ai_authority") or {}
    qem_source = pairing.get("qem_source") or {}
    output = pairing.get("output") or {}
    operation = pairing.get("operation") or {}
    source_path = Path(str(source.get("path", ""))).resolve()
    qem_path = Path(str(qem_source.get("path", ""))).resolve()
    candidate_path = Path(str(output.get("path", ""))).resolve()
    review_glb = Path(str(output.get("review_glb", ""))).resolve()
    if pairing.get("schema") != "reference-asset-compiler.paired-feature-qem-candidate.v1":
        raise ValueError("Input is not a paired Feature-QEM report")
    if pairing.get("status") != "mechanical_pass" or pairing.get("failures") not in ([], None):
        raise ValueError("Paired Feature-QEM diagnostic did not pass")
    if operation.get("vertex_coordinates_unchanged") is not True:
        raise ValueError("Paired Feature-QEM diagnostic moved vertices")
    for path in (source_path, qem_path, candidate_path, review_glb):
        if not path.is_file():
            raise FileNotFoundError("Retopology evidence is missing: {0}".format(path))
    expected = {
        source_path: source.get("sha256"),
        qem_path: qem_source.get("sha256"),
        candidate_path: output.get("sha256"),
        review_glb: output.get("review_glb_sha256"),
    }
    for path, digest in expected.items():
        if sha256_file(path) != digest:
            raise ValueError("Retopology evidence hash drifted: {0}".format(path))
    canonical = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass",
        "method": "feature_qem_triangle_pairing_with_bounded_augmenting_paths",
        "purpose": "Downstream topology conversion of AI-derived geometry; no image reconstruction.",
        "source": {"path": str(source_path), "sha256": source["sha256"]},
        "qem_derivative": {
            "path": str(qem_path),
            "sha256": qem_source["sha256"],
            "topology": qem_source.get("topology"),
        },
        "pairing_report": {"path": str(pairing_path), "sha256": sha256_file(pairing_path)},
        "operation": operation,
        "settings": pairing.get("settings"),
        "output": output,
        "symmetric_surface_deviation": pairing.get("symmetric_surface_deviation"),
        "failures": [],
        "requires_fixed_view_review": True,
        "requires_deformation_flow_review": True,
        "production_grade": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
    print("RAC_CANONICAL_RETOPOLOGY_REPORT_OK {0}".format(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
