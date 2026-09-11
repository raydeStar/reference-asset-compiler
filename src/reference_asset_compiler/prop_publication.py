"""Resolve retained normalization evidence for new and historical prop compiles."""
from pathlib import Path

from .io import read_json, sha256_file


def normalization_report(job: Path, manifest_path: Path) -> Path:
    manifest = read_json(manifest_path)
    binding = manifest.get("compile_receipt")
    if binding is None:
        # Historical authorities retain their original evidence location. No migration.
        report = job / "normalize-prop-report.json"
        if not report.is_file():
            raise ValueError("Historical prop normalization evidence is missing")
        return report
    root = manifest_path.resolve().parent

    def bound_file(name):
        if not isinstance(name, str) or not name:
            raise ValueError("Publication receipt requires a relative filename")
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Publication file is missing or outside the payload: {name}")
        return path

    if not isinstance(binding, dict):
        raise ValueError("Invalid prop publication binding")
    receipt_path = bound_file(binding.get("file"))
    if sha256_file(receipt_path) != binding.get("sha256"):
        raise ValueError("Prop publication receipt hash changed")
    receipt = read_json(receipt_path)
    if receipt.get("schema") != "reference-asset-compiler.prop-publication.v1":
        raise ValueError("Unsupported prop publication receipt")
    files = receipt.get("files")
    if not isinstance(files, dict) or not {manifest.get("fbx"), "normalize-prop-report.json"} <= files.keys():
        raise ValueError("Prop publication must bind its FBX and normalization report")
    for name, digest in files.items():
        if sha256_file(bound_file(name)) != digest:
            raise ValueError(f"Published prop file hash changed: {name}")
    report = bound_file("normalize-prop-report.json")
    if sha256_file(report) != receipt.get("normalization_sha256"):
        raise ValueError("Normalization receipt hash mismatch")
    return report
