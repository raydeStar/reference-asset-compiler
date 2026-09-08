"""Retain failed orbit estimates as inspectable, hash-bound negative evidence."""

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
    reasons = {
        "v001": "Reject: both exact side views collapse colored armor into black silhouettes.",
        "v002": "Reject: oblique camera adjustment restores one side but the other loses almost all armor color.",
        "v003": "Reject: overlapping vertical crops restore side color but create broad horizontal bands and black leg/foot patches.",
    }
    rows, sections = [], []
    for version, reason in reasons.items():
        attempt = WORK / ("intrinsic-orbit-estimate-" + version)
        receipt = attempt / "execution.json"
        report = json.loads(receipt.read_text())
        if report["status"] != "candidate_needs_review":
            raise ValueError("Expected completed retained inference")
        frames = []
        cards = []
        for frame in report["outputs"]:
            path = Path(frame["path"])
            if bound(path)["sha256"] != frame["sha256"]:
                raise ValueError("Changed orbit evidence")
            frames.append(bound(path))
            url = html.escape(path.as_uri(), quote=True)
            cards.append(f'<figure><a href="{url}"><img src="{url}" alt="{path.stem}" loading="lazy"></a>'
                         f'<figcaption>{path.stem}</figcaption></figure>')
        rows.append({"attempt": bound(receipt), "frames": frames, "status": "rejected",
                     "reason": reason, "reviewer": "codex", "human_visual_review": False})
        sections.append(f'<h2>{version}</h2><p>{reason}</p><div class="grid">' + "".join(cards) + "</div>")
    result = {"schema": "reference-asset-compiler.intrinsic-orbit-review.v1", "attempts": rows,
              "authority_changed": False, "actual_atlas_transport_run": False, "production_ready": False,
              "decision": "Stop this route after three bounded orbit trials. No invalid donor enters the atlas."}
    (DEST / "intrinsic-orbit-rejections-v001.json").write_text(json.dumps(result, indent=2) + "\n")
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ayric · orbit rejection evidence</title><style>body{background:#121923;color:#eee7d9;font:17px/1.6 system-ui;padding:3vw}
main{max-width:1500px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
figure{margin:0;background:#26303b}img{display:block;width:100%;background:white}figcaption{padding:10px}a{color:#72d5ea}</style>
<main><h1>The orbit did not hold up</h1><p>These are AI-estimated 2D images, not altered meshes.
Three bounded trials were rejected. Ayric's original atlas and head artwork are unchanged.</p>
<p>The first front-view success did not generalize to complete body coverage. No texture gate was promoted.</p>'''
    page += "".join(sections)
    page += '''<p><a href="intrinsic-orbit-rejections-v001.json">All hashes and review decisions</a> ·
<a href="ayric-collar-review-v001.html">Unchanged held character</a></p></main></html>'''
    output = DEST / "intrinsic-orbit-rejections-v001.html"
    output.write_text(page, encoding="utf-8")
    print(f"ORBIT_REJECTIONS_BOUND {output} — the evidence gets the last word.")


if __name__ == "__main__":
    main()
