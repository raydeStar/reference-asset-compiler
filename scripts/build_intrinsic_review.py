"""Show actual render inputs and independently retained albedo estimates side by side."""

import argparse
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work/sunset-ayric-v2/texture"
DEST = ROOT / "work/sunset-workshop/evidence"


def bound(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--highres-note", required=True)
    args = parser.parse_args()
    inputs_path = WORK / "intrinsic-inputs-v001/inputs.json"
    source = json.loads(inputs_path.read_text())
    reports = []
    for name in ("intrinsic-probe-v003", "intrinsic-highres-v001"):
        path = WORK / name / "execution.json"
        report = json.loads(path.read_text())
        if report["status"] != "candidate_needs_review":
            raise ValueError("Review requires a completed inference attempt")
        if report["inputs_receipt_sha256"] != bound(inputs_path)["sha256"]:
            raise ValueError("Inputs differ across the comparison")
        for row in report["outputs"]:
            if bound(Path(row["path"]))["sha256"] != row["sha256"]:
                raise ValueError("Changed generated output")
        reports.append((path, report))
    if reports[1][1]["guidance_receipt_sha256"] != bound(reports[0][0])["sha256"]:
        raise ValueError("High-resolution guidance does not bind the retained baseline")
    sections = []
    for frame in source["frames"]:
        input_path = Path(frame["path"])
        if bound(input_path)["sha256"] != frame["sha256"]:
            raise ValueError("Changed rendered input")
        paths = [input_path]
        for _, report in reports:
            paths.append(next(Path(row["path"]) for row in report["outputs"]
                              if Path(row["path"]).name == input_path.name))
        cards = []
        for label, path in zip(("Actual mesh · unlit input", "Base AI estimate · 256px inference",
                                "Guided AI estimate · overlapping patches"), paths):
            url = html.escape(path.as_uri(), quote=True)
            cards.append(f'<figure><a href="{url}"><img src="{url}" alt="{label}"></a>'
                         f'<figcaption>{label}</figcaption></figure>')
        sections.append(f'<h2>{html.escape(input_path.stem)}</h2><div class="grid">'
                        + "".join(cards) + "</div>")
    verdict = {
        "schema": "reference-asset-compiler.intrinsic-visual-review.v1",
        "input_receipt": bound(inputs_path), "attempts": [bound(path) for path, _ in reports],
        "base_verdict": "Reject direct replacement: softened eyes, beard and armor detail.",
        "highres_verdict": args.highres_note,
        "reviewer": "codex", "human_visual_review": False,
        "scope": "Two front-view image estimates only; not a baked/approved atlas or a 3D result.",
        "production_ready": False, "character_authority_changed": False,
        "retained_failures": [bound(WORK / "intrinsic-probe-v001/execution.json"),
                              bound(WORK / "intrinsic-probe-v001.log"),
                              bound(WORK / "intrinsic-probe-v002.log")],
    }
    (DEST / "intrinsic-review-v001.json").write_text(json.dumps(verdict, indent=2) + "\n")
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Ayric · albedo study</title>
<style>body{background:#111820;color:#eee9dc;font:17px/1.6 system-ui;margin:0;padding:3vw}
main{max-width:1600px;margin:auto}h1{font-size:2.6rem}a{color:#74deef}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
figure{margin:0;background:#202933}img{width:100%;display:block;background:white}
figcaption{padding:12px;font-size:14px}.note{border-left:3px solid #ecc181;padding-left:16px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}</style><main>
<small>SUNSET WORKSHOP · MATERIAL EXPERIMENT</small><h1>Less painted-in light. Identity still matters.</h1>
<p class="note">Only the first column is a render of the actual mesh. The others are AI-estimated
2D albedo images, not new 3D assets. No production atlas or accepted geometry was changed.</p>
<p>All comparisons use the same unchanged source. Inputs are true unlit sRGB at zero exposure.
White backgrounds here are for comparison; input alpha defines the object.</p>'''
    page += "".join(sections)
    page += "<h2>Review</h2><p>" + html.escape(verdict["base_verdict"]) + "</p><p>"
    page += html.escape(args.highres_note) + "</p>"
    page += '''<p>No texture gate promotion. Opposite views, UV-aware transfer and actual remapped
mesh evidence are still required.</p><p><a href="intrinsic-review-v001.json">Hashes, lineage and retained failures</a>
· <a href="ayric-collar-review-v001.html">Current held character package</a></p></main></html>'''
    output = DEST / "intrinsic-review-v001.html"
    output.write_text(page, encoding="utf-8")
    print(f"INTRINSIC_REVIEW_READY {output} — labels before laurels.")


if __name__ == "__main__":
    main()
