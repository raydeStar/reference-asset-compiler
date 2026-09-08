"""Make a source-versus-four-views HTML review; never grant an approval."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ("front", "three-quarter", "side", "back")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=("modeling", "retopology", "texture"), default="modeling")
    parser.add_argument("--package", action="append", default=[], metavar="ASSET=PROD-NAME")
    parser.add_argument("--reject", action="append", default=[], metavar="ASSET=REASON",
                        help="Retain an agent rejection in the review; never an approval.")
    args = parser.parse_args()
    packages = {}
    for entry in args.package:
        asset, separator, name = entry.partition("=")
        if not separator or asset not in args.assets or not re.fullmatch(r"prod-[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Package must name a reviewed asset and a local prod-* directory")
        packages[asset] = name
    rejections = {}
    for entry in args.reject:
        asset, separator, reason = entry.partition("=")
        if not separator or asset not in args.assets or not reason.strip():
            raise ValueError("Rejection must name a reviewed asset and a reason")
        rejections[asset] = reason.strip()
    output = args.output.resolve()
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("Existing evidence remains untouched; choose a new output name.")
    sections, records = [], []
    for asset in args.assets:
        if not asset.startswith("sunset-") or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in asset):
            raise ValueError("Expected a sunset asset id")
        job = ROOT / "work" / asset
        prod = job / packages.get(asset, "prod-v2")
        paths = [job / "references/primary.png"] + [
            job / "modeling/fixed-views" / ("matcap-" + view + ".png") for view in VIEWS]
        labels = ["Reference", *VIEWS]
        if args.stage == "retopology":
            labels = ["Reference", *("Approved " + view for view in VIEWS)]
            paths += [job / "references/primary.png"] + [
                job / "retopology/operator-attempt001/fixed-views" / ("matcap-" + view + ".png") for view in VIEWS]
            labels += ["Reference", *("Reduced " + view for view in VIEWS)]
        if args.stage == "texture":
            paths, labels = [], []
            for pass_name in ("beauty", "albedo"):
                paths += [job / "references/primary.png"] + [
                    prod / "turn" / (pass_name + "-" + view + ".png") for view in VIEWS]
                labels += ["Reference", *(pass_name + " " + view for view in VIEWS)]
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise ValueError("Missing fixed views: " + ", ".join(missing))
        for extra in ("top", "underside", "elevated"):
            if args.stage == "texture":
                for pass_name in ("beauty", "albedo"):
                    path = prod / "surface-views" / (pass_name + "-" + extra + ".png")
                    if path.is_file():
                        paths.append(path)
                        labels.append(pass_name + " " + extra)
                continue
            stage_dir = "modeling" if args.stage == "modeling" else "retopology/operator-attempt001"
            path = job / stage_dir / "surface-views" / ("matcap-" + extra + ".png")
            if path.is_file():
                original_extra = job / "modeling/surface-views" / ("matcap-" + extra + ".png")
                if args.stage == "retopology" and original_extra.is_file():
                    paths.append(original_extra)
                    labels.append("Approved " + extra)
                paths.append(path)
                labels.append(("Reduced " if args.stage == "retopology" else "") + extra)
        figures = []
        if args.stage == "texture" and (prod / "face-review-v001").is_dir():
            for pass_name in ("beauty", "albedo"):
                for view in ("front", "three-quarter", "side"):
                    path = prod / "face-review-v001" / (pass_name + "-face-" + view + ".png")
                    if not path.is_file():
                        raise ValueError("Incomplete face evidence: " + str(path))
                    paths.append(path)
                    labels.append(pass_name + " face " + view)
            opposite = [(pass_name, view, prod / "face-review-v001" /
                         (pass_name + "-face-opposite-" + view + ".png"))
                        for pass_name in ("beauty", "albedo")
                        for view in ("three-quarter", "side")]
            if any(path.is_file() for _mode, _view, path in opposite):
                for mode, view, path in opposite:
                    if not path.is_file():
                        raise ValueError("Incomplete opposite-face evidence: " + str(path))
                    paths.append(path)
                    labels.append(mode + " opposite face " + view)
        for label, path in zip(labels, paths):
            figures.append('<figure><a href="{0}"><img src="{0}" alt="{1}"></a><figcaption>{1}</figcaption></figure>'.format(
                html.escape(Path(os.path.relpath(path, output.parent)).as_posix(), quote=True), html.escape(label)))
        generation = json.loads((job / "candidates/hy3d-single-seed42-attempt001/generation.json").read_text())
        status = "rejected by agent: " + rejections[asset] if asset in rejections else "awaits recorded " + args.stage + " review"
        mesh = job / "candidates/hy3d-single-seed42-attempt001/candidate.glb"
        reduction = None
        texture_payload = None
        payload_files = []
        if args.stage == "retopology":
            report = job / "retopology/operator-attempt001/reduction-report.json"
            reduction = json.loads(report.read_text())
            mesh = job / "retopology/operator-attempt001/voxel-qem-candidate.glb"
            status += " · {:,} reduced triangles · {}".format(reduction["output"]["triangles"], reduction["status"])
        if args.stage == "texture":
            report = prod / "retopo.json"
            texture_payload = json.loads(report.read_text())
            mesh = prod / texture_payload["output_fbx"]
            payload_files = [report, prod / "gate-tex.json", prod / "texture-payload-binding.json"]
            payload_files += [prod / name for name in texture_payload["baked"].values()]
            status += " · {}px atlas · texture gate {}".format(texture_payload["resolution"],
                "passed" if texture_payload["ok"] else "FAILED — held, not eligible for promotion")
        sections.append("<section><h2>{0}</h2><p>{1:,} source triangles · {2:.1f}s AI generation · {4}</p><div class='views'>{3}</div></section>".format(
            html.escape(asset), generation["faces"], generation["seconds"], "".join(figures), html.escape(status)))
        records.append({"asset_id": asset, "status": status,
                        "review_stage": args.stage,
                        "texture_package": prod.name if args.stage == "texture" else None,
                        "payload_files": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in payload_files],
                        "reduction_report": {"path": str(report), "sha256": hashlib.sha256(report.read_bytes()).hexdigest()} if reduction else None,
                        "candidate": {"path": str(mesh), "sha256": hashlib.sha256(mesh.read_bytes()).hexdigest()},
                        "files": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]})
    page = """<!doctype html><meta charset='utf-8'><title>Workshop modeling review</title>
<style>body{background:#171b1c;color:#ecdfc7;font:16px system-ui;margin:32px}h1{color:#e8bc75}p{color:#bec3bd}.views{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}figure{margin:0}img{width:100%;background:#333;border-radius:6px}figcaption{padding:7px}section{margin:32px 0;border-top:1px solid #464b43}a{color:#8bd7d4}@media(max-width:900px){.views{grid-template-columns:repeat(2,1fr)}}</style>
<h1>Sunset workshop — geometry review</h1><p>Actual AI-derived mesh renders, not painted mockups. Click a view for full resolution. Check silhouettes, openings, legs, handles, and side depth. No approvals have been granted. Texturing and production reduction come after review.</p>""" + "".join(sections)
    if args.stage == "retopology":
        page = page.replace("Workshop modeling review", "Workshop topology review").replace(
            "Sunset workshop — geometry review", "Sunset workshop — reduction comparison").replace(
            "No approvals have been granted. Texturing and production reduction come after review.",
            "Original shapes were approved by Ayric. Compare each approved row with its reduced row. This page grants no topology approval; texturing follows that separate gate.")
    if args.stage == "texture":
        page = page.replace("Workshop modeling review", "Workshop texture review").replace(
            "Sunset workshop — geometry review", "Sunset workshop — texture review").replace(
            "No approvals have been granted. Texturing and production reduction come after review.",
            "Modeling and topology passed their recorded review gates. Compare lit PBR and unlit albedo rows. This page grants no texture approval. Failed gates remain held; these are not UE screenshots or cooked-runtime proof.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    output.with_suffix(".json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print("WORKSHOP_REVIEW_READY", output, "-- every side gets its day in court.")


if __name__ == "__main__":
    main()
