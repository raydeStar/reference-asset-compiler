"""Find a painted model's parts, face by face, and the same parts in its reference picture.

Painting a whole model at once lets the painter carry one part's colour onto
another: on the skiff the fin's red landed on the strut that holds it, and a
fin lost its cream band. `paint_parts.py` paints each part alone instead, and
needs to know which face belongs to which part, and which pixels of the
reference show it. This finds both:

1. 24 renders of the painted model, with the face under every pixel
   (`blender/render_part_views.py`).
2. Each render and the reference labelled by part with Grounding DINO and
   Segment Anything (`segment_part_views.py`, run by a Python with torch).
3. The renders' labels voted onto the faces. A pixel of a found part votes
   with its detection's strength; a pixel left to the base part votes weakly
   (it only means nothing else was found there). Faces no render saw take
   their neighbours' votes, ring by ring, and every face is then pulled toward
   its neighbours across smooth surface but hardly across a crease, so a
   label's edge follows the model's own edges.
4. Fixed views of the model in its part colours, for a person to check
   (`blender/render_part_review.py`). The labelling is a candidate: a fin
   labelled as hull would be painted from the hull's picture.

Writes <output> (.npz): faces (part index per triangle, glTF order),
reference (part index per reference pixel, 255 off the model), names, the
vocabulary, and the hashes binding it to the model's mesh and the reference.
Beside it, <output stem>-views/ (the renders, labels and overlays) and
<output stem>-review/ (the fixed views).

Usage:
  python scripts/label_parts.py -- <painted.glb> <labels.npz> <report.json> \\
      --vocab profiles/segmentation/skiff-parts.json --reference <image> \\
      [--blender <exe>] [--torch-python <exe>] [--detector <dir>] [--sam <pth>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / "src"))
from compress_textures import read_glb  # noqa: E402
from paint_head_detail import mesh_from_glb, sha256  # noqa: E402
from reference_asset_compiler.processes import run_bounded  # noqa: E402
from reference_asset_compiler.segmentation import resolve_segmentation  # noqa: E402

TAG = "[PARTS]"
SCHEMA = "reference-asset-compiler.part-labels.v1"


def failed(reason: str) -> int:
    print("{0} FAILED: {1}".format(TAG, reason))
    return 1


def mesh_sha256(positions, uvs, triangles) -> str:
    """The identity a labelling is bound to: the mesh's positions, UVs and triangles, as read."""
    digest = hashlib.sha256()
    for array in (np.ascontiguousarray(positions, dtype=np.float32), np.ascontiguousarray(uvs, dtype=np.float32),
                  np.ascontiguousarray(triangles, dtype=np.int64)):
        digest.update(array.tobytes())
    return digest.hexdigest()


def face_neighbours(positions, triangles):
    """Pairs of faces sharing an edge, after welding the copies an export splits along UV seams."""
    span = float(np.ptp(positions, axis=0).max()) or 1.0
    key = np.round(positions / (span * 1e-6)).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    corners = weld.ravel()[triangles]
    edges = np.sort(np.stack([corners[:, [0, 1]], corners[:, [1, 2]], corners[:, [2, 0]]], axis=1).reshape(-1, 2),
                    axis=1)
    owner = np.repeat(np.arange(len(triangles)), 3)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owner = edges[order], owner[order]
    same = np.all(edges[1:] == edges[:-1], axis=1)
    return owner[:-1][same], owner[1:][same]


def face_normals(positions, triangles):
    p = positions[triangles].astype(np.float64)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def settle_labels(votes, a, b, normals, base, smooth=0.6, crease=35.0, iterations=12):
    """Votes (faces x parts) to one label a face: unseen faces filled, then smoothed along the surface.

    Returns (labels, unseen mask, faces the smoothing changed).
    """
    count, parts = votes.shape
    angle = np.degrees(np.arccos(np.clip(np.sum(normals[a] * normals[b], axis=1), -1, 1)))
    weight = np.where(angle < crease, 1.0, 0.1)
    graph = coo_matrix((np.r_[weight, weight], (np.r_[a, b], np.r_[b, a])), shape=(count, count)).tocsr()
    total = votes.sum(axis=1, keepdims=True)
    unseen = total[:, 0] == 0
    filled = np.where(total > 0, votes / np.maximum(total, 1e-12), 0.0)
    known = ~unseen
    for _ in range(10000):
        if known.all():
            break
        spread = graph @ (filled * known[:, None])
        reach = graph @ known.astype(float)
        grow = (~known) & (reach > 0)
        if not grow.any():
            break
        filled[grow] = spread[grow] / reach[grow][:, None]
        known |= grow
    filled[~known] = np.eye(parts)[base]
    degree = np.asarray(graph.sum(axis=1)).ravel()
    belief = filled.copy()
    for _ in range(iterations):
        belief = (1 - smooth) * filled + smooth * (graph @ belief) / np.maximum(degree, 1e-12)[:, None]
    labels = belief.argmax(axis=1).astype(np.uint8)
    return labels, unseen, int((labels != filled.argmax(axis=1)).sum())


def collect_votes(views_dir: Path, faces: int, parts: int, base: int, default_weight: float):
    votes = np.zeros((faces, parts))
    meta = json.loads((views_dir / "views.json").read_text(encoding="utf-8"))
    for record in meta["views"]:
        number = record["view"]
        ids = np.load(views_dir / "view-{0:02d}-faces.npy".format(number)).ravel()
        labels = np.load(views_dir / "view-{0:02d}-labels.npy".format(number)).ravel()
        strength = np.load(views_dir / "view-{0:02d}-score.npy".format(number)).ravel()
        ok = (ids >= 0) & (labels != 255)
        if ids[ok].max(initial=-1) >= faces:
            raise ValueError("view {0} names face {1}, the model has {2}".format(number, ids[ok].max(), faces))
        label = labels[ok].astype(np.int64)
        weight = np.where(label == base, default_weight, np.maximum(strength[ok], 0.05))
        np.add.at(votes, (ids[ok], label), weight)
    return votes, len(meta["views"])


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--vocab", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--blender", default=os.environ.get("RAC_BLENDER"))
    parser.add_argument("--torch-python")
    parser.add_argument("--detector")
    parser.add_argument("--sam")
    parser.add_argument("--view-size", type=int, default=1024)
    parser.add_argument("--id-size", type=int, default=768)
    parser.add_argument("--default-weight", type=float, default=0.15,
                        help="the vote of a pixel left to the base part: weak, it only means nothing else was found")
    parser.add_argument("--smooth", type=float, default=0.6)
    parser.add_argument("--crease", type=float, default=35.0)
    args = parser.parse_args(argv)
    started = time.monotonic()

    for path, what in ((args.source, "model"), (args.vocab, "vocabulary"), (args.reference, "reference")):
        if not path.is_file():
            return failed("the {0} does not exist: {1}".format(what, path))
    if args.output.exists():
        return failed("refusing to overwrite {0}".format(args.output))
    if not args.blender or not Path(args.blender).is_file():
        return failed("Blender is needed to render the views: pass --blender or set RAC_BLENDER")
    try:
        segmenter = resolve_segmentation(args.torch_python, args.detector, args.sam)
    except ValueError as problem:
        return failed(str(problem))
    vocab = json.loads(args.vocab.read_text(encoding="utf-8"))
    parts = vocab["parts"]
    names = [part["name"] for part in parts]
    bases = [i for i, part in enumerate(parts) if part.get("base")]
    if len(bases) != 1 or len(parts) < 2 or len(parts) > 32:
        return failed("a vocabulary has one base part and at least one other (at most 32 parts)")
    base = bases[0]

    document, binary = read_glb(args.source.read_bytes())
    positions, uvs, triangles = mesh_from_glb(document, binary)
    work = args.output.parent / (args.output.stem + "-views")
    review = args.output.parent / (args.output.stem + "-review")
    for folder in (work, review):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
    scripts = Path(__file__).resolve().parent

    def run(command, what, timeout):
        done = run_bounded(command, capture_output=True, text=True, errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL)
        if done.returncode != 0:
            raise RuntimeError("{0} failed (exit {1}): {2}".format(
                what, done.returncode, " | ".join((done.stdout + done.stderr).strip().splitlines()[-4:])))
        return done

    try:
        run([args.blender, "-b", "--factory-startup", "--python", str(scripts / "blender" / "render_part_views.py"),
             "--", str(args.source), str(work), "--size", str(args.view_size), "--id-size", str(args.id_size)],
            "rendering the views", 3600)
        segment = [segmenter["python"], "-I", str(scripts / "segment_part_views.py"), str(work), str(args.vocab),
                   "--detector", segmenter["detector"], "--sam", segmenter["sam"]]
        run(segment, "labelling the views", 3600)
        run(segment + ["--pictures", str(args.reference)], "labelling the reference", 1800)
    except (RuntimeError, subprocess.TimeoutExpired) as problem:
        return failed(str(problem))
    meta = json.loads((work / "views.json").read_text(encoding="utf-8"))
    if meta["faces"] != len(triangles):
        return failed("Blender read {0} faces, the file holds {1}; the labels would not line up".format(
            meta["faces"], len(triangles)))

    votes, view_count = collect_votes(work, len(triangles), len(parts), base, args.default_weight)
    a, b = face_neighbours(positions, triangles)
    labels, unseen, changed = settle_labels(votes, a, b, face_normals(positions, triangles), base,
                                            args.smooth, args.crease)
    reference = np.load(work / (args.reference.stem + "-labels.npy"))
    np.save(review / "faces.npy", labels)
    (review / "colours.json").write_text(json.dumps([part.get("colour", [200, 200, 200]) for part in parts]),
                                         encoding="utf-8")
    try:
        run([args.blender, "-b", "--factory-startup", "--python", str(scripts / "blender" / "render_part_review.py"),
             "--", str(args.source), str(review / "faces.npy"), str(review / "colours.json"), str(review)],
            "rendering the review", 1800)
    except (RuntimeError, subprocess.TimeoutExpired) as problem:
        return failed(str(problem))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "wb") as stream:
        np.savez_compressed(stream, faces=labels, reference=reference, names=np.array(names),
                            vocab=np.array(json.dumps(vocab)),
                            mesh_sha256=np.array(mesh_sha256(positions, uvs, triangles)),
                            reference_sha256=np.array(sha256(args.reference)))
    area = np.linalg.norm(np.cross(positions[triangles[:, 1]] - positions[triangles[:, 0]],
                                   positions[triangles[:, 2]] - positions[triangles[:, 0]]), axis=1) / 2
    report = {
        "schema": SCHEMA,
        "source": str(args.source), "source_sha256": sha256(args.source),
        "mesh_sha256": mesh_sha256(positions, uvs, triangles),
        "reference": str(args.reference), "reference_sha256": sha256(args.reference),
        "vocab": str(args.vocab), "vocab_sha256": sha256(args.vocab),
        "output": str(args.output), "output_sha256": sha256(args.output),
        "segmenter": {"python": segmenter["python"], "detector": segmenter["detector"], "sam": segmenter["sam"]},
        "views": view_count, "view_size": args.view_size, "id_size": args.id_size,
        "faces": int(len(triangles)), "faces_seen": int((~unseen).sum()),
        "faces_changed_by_smoothing": changed,
        "settings": {"default_weight": args.default_weight, "smooth": args.smooth, "crease_degrees": args.crease},
        "parts": {name: {"faces": int((labels == i).sum()),
                         "area_share": round(float(area[labels == i].sum() / max(area.sum(), 1e-12)), 4),
                         "reference_pixels": int((reference == i).sum())} for i, name in enumerate(names)},
        "views_dir": str(work),
        "review_views": sorted(str(path) for path in review.glob("parts-*.png")),
        "requires_human_review": True,
        "seconds": round(time.monotonic() - started, 1),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("{0} labelled {1} faces: {2}".format(TAG, len(triangles), {n: report["parts"][n]["faces"] for n in names}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
