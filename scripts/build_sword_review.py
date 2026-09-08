"""Bind the reviewed sword fixture and retained lighting trials into a local panel."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "work/sunset-workshop/evidence"


def bound(path: Path) -> dict:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    report_path = EVIDENCE / "sword-runtime-v003/review.json"
    report = json.loads(report_path.read_text())
    receipt = ROOT / "work/sunset-sword-v1/validation/ue5-runtime-review.json"
    review = json.loads(receipt.read_text())
    if review["gallery_report_sha256"] != bound(report_path)["sha256"]:
        raise ValueError("Review binding differs; the butler refuses a borrowed verdict.")
    retained = []
    for version, reason in [("v001", "Underlit: unsuitable as sole material review"),
                            ("v002", "Overbright inspection fill obscures blade edges")]:
        trial_path = EVIDENCE / f"sword-runtime-{version}/review.json"
        trial = json.loads(trial_path.read_text())
        retained.append({"version": version, "status": "rejected_lighting_fixture",
                         "reason": reason, "report": bound(trial_path),
                         "frames": [bound(Path(frame["path"])) for frame in trial["frames"]]})
    cards = []
    for frame in report["frames"]:
        path = Path(frame["path"])
        if bound(path)["sha256"] != frame["sha256"]:
            raise ValueError(f"Changed frame: {path}")
        src = html.escape(path.relative_to(EVIDENCE).as_posix(), quote=True)
        name = html.escape(frame["name"])
        cards.append(f'<figure><a href="{src}"><img src="{src}" alt="Sword {name}" loading="lazy"></a>'
                     f'<figcaption>{name} · LOD {frame["forced_lod_model"] - 1}</figcaption></figure>')
    payload = {"schema": "reference-asset-compiler.sword-review-panel.v1",
               "accepted": bound(report_path), "receipt": bound(receipt),
               "retained_rejections": retained, "human_visual_review": False,
               "production_ready": False, "scope": review["review_scope"]}
    (EVIDENCE / "sword-review-v003.json").write_text(json.dumps(payload, indent=2) + "\n")
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sword · UE inspection</title><style>
body{margin:0;background:#111820;color:#e8e6dc;font:17px/1.6 system-ui;padding:3vw}
main{max-width:1500px;margin:auto}h1{font-size:2.5rem;margin-bottom:0}
a{color:#70d9ef}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:20px}
figure{margin:0;background:#202933;border-radius:10px;overflow:hidden}img{width:100%;display:block}
figcaption{padding:12px}small{color:#b9c8cd}.scope{border-left:3px solid #70d9ef;padding-left:16px}
</style><main><small>SUNSET WORKSHOP · ACTUAL UE5.8.2 FRAMES</small>
<h1>The separate sword</h1><p class="scope">Static appearance accepted by delegated agent review.
Not attached to the character; no collision, animation or cooked-runtime certification.
The room shown is an unfinished inspection fixture, not the final scene.</p>
<p>135 cm · 18,000 / 9,000 / 4,500 triangles · six verified views.
Click an image for its original 1920 × 1080 capture.</p><div class="grid">'''
    page += "".join(cards)
    page += '''</div><h2>Evidence, not stage magic</h2>
<p>The v003 copy uses low-intensity neutral inspection fill; the playable v004 map is unchanged.
The reflective grip reads lighter here than in Blender. No mesh or texture replacement was made.</p>
<p><a href="sword-runtime-v003/review.json">Capture report</a> ·
<a href="sword-review-v003.json">Hashes and retained rejection records</a> ·
<a href="sword-runtime-v001/front.png">Underlit v001</a> ·
<a href="sword-runtime-v002/front.png">Overbright v002</a></p></main></html>'''
    output = EVIDENCE / "sword-review-v003.html"
    output.write_text(page, encoding="utf-8")
    print(f"SWORD_REVIEW_BOUND {output} — all six witnesses accounted for.")


if __name__ == "__main__":
    main()
