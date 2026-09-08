"""Small, portable scene contracts. A successful machine check is not applause."""
from __future__ import annotations

import html
import json
import math
import os
import re
import shutil
from pathlib import Path

from .io import sha256_file

RECIPE_SCHEMA = "reference-asset-compiler.scene-atmosphere.v1"
REVIEW_SCHEMA = "reference-asset-compiler.scene-review-bundle.v1"


def read_utf8(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def finite(value, name, low=None, high=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("{0} must be a finite number".format(name))
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError("{0} is outside its supported range".format(name))
    return float(value)


def local_fog_falloff(radius_cm, e_fold_height_cm):
    """UE 5.8 multiplies UI falloff by .01 in normalized sphere coordinates.

    exp(-height / H) => shader falloff = radius / H, UI = 100 * radius / H.
    Nonuniform scaling is deliberately unsupported by this spherical adapter.
    """
    radius = finite(radius_cm, "radius_cm", 1)
    height = finite(e_fold_height_cm, "e_fold_height_cm", 0.001)
    return finite(100 * radius / height, "UE 5.8 falloff", 1, 5000)


def vector(value, name, low=None, high=None):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("{0} needs three numbers".format(name))
    return [finite(x, name, low, high) for x in value]


def plan_atmosphere(recipe):
    required = {"schema", "engine_adapter", "source_map", "source_map_sha256",
                "target_map", "fog"}
    if not isinstance(recipe, dict) or set(recipe) != required:
        raise ValueError("Recipe fields must be exactly: " + ", ".join(sorted(required)))
    if recipe["schema"] != RECIPE_SCHEMA or recipe["engine_adapter"] != "ue5.8":
        raise ValueError("Only the explicit ue5.8 atmosphere contract is supported")
    for key in ("source_map", "target_map"):
        if not isinstance(recipe[key], str) or not re.fullmatch(
                r"/Game/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*", recipe[key]):
            raise ValueError("Invalid Unreal map path: " + key)
    if recipe["source_map"] == recipe["target_map"]:
        raise ValueError("Target must be a new map, never the source")
    if not isinstance(recipe["source_map_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", recipe["source_map_sha256"]):
        raise ValueError("Source map needs its lowercase SHA-256")
    if not isinstance(recipe["fog"], list) or not recipe["fog"]:
        raise ValueError("At least one explicitly named fog volume is required")
    operations, names = [], set()
    keys = {"actor", "radius_cm", "ground_z_cm", "height_above_ground_cm",
            "e_fold_height_cm", "density", "albedo_linear", "emissive_linear"}
    for fog in recipe["fog"]:
        if not isinstance(fog, dict) or set(fog) != keys:
            raise ValueError("Unknown or missing fog fields")
        name = fog["actor"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Fog actor labels must be nonempty and unique")
        names.add(name)
        radius = finite(fog["radius_cm"], "radius_cm", 1)
        operations.append({
            "actor": name,
            "z_cm": finite(fog["ground_z_cm"], "ground_z_cm") + finite(
                fog["height_above_ground_cm"], "height_above_ground_cm", 0),
            "uniform_scale": radius / 500,
            "properties": {
                "radial_fog_extinction": 0.0,
                "height_fog_extinction": finite(fog["density"], "density", 0, 2),
                "height_fog_falloff": local_fog_falloff(radius, fog["e_fold_height_cm"]),
                "height_fog_offset": 0.0,
                "fog_albedo": vector(fog["albedo_linear"], "albedo_linear", 0, 1),
                "fog_emissive": vector(fog["emissive_linear"], "emissive_linear", 0),
            },
        })
    return {"schema": RECIPE_SCHEMA, "source_map": recipe["source_map"],
            "target_map": recipe["target_map"], "operations": operations,
            "human_review": "pending", "changes_applied": False,
            "note": "UE 5.8 only; visual review still has veto power."}


def require_unchanged(before, after):
    """Compare numeric snapshots, never pointer-bearing Unreal Transform strings."""
    if before != after:
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        raise ValueError("Protected scene changed: " + ", ".join(changed))


def contained_file(root, value):
    root = Path(root).resolve()
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Missing file or path outside evidence root: " + str(value))
    return path


def check_binding(root, row):
    if not isinstance(row, dict) or not isinstance(row.get("path"), str):
        raise ValueError("Invalid file binding")
    path = contained_file(root, row["path"])
    if not isinstance(row.get("sha256"), str) or sha256_file(path) != row["sha256"]:
        raise ValueError("Hash mismatch: " + row["path"])
    if "bytes" in row and (type(row["bytes"]) is not int or row["bytes"] != path.stat().st_size):
        raise ValueError("Size mismatch: " + row["path"])
    return path


def bundle_scene_review(receipt_path, root, output):
    """Revalidate an existing lighting receipt and copy a portable review folder.

    This does not run UE, infer visual approval, or independently attest the
    original capture provenance. Existing agent judgments stay attributed.
    Every bound input is rehashed, including the complete package inventory.
    """
    # Unreal's embedded Python needs only the stdlib planner, not Pillow.
    from PIL import Image

    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Existing review will not be overwritten")
    receipt_path = contained_file(root, str(receipt_path))
    receipt_hash = sha256_file(receipt_path)
    receipt = read_utf8(receipt_path)
    if receipt.get("schema") != "reference-asset-compiler.scene-lighting-review.v1":
        raise ValueError("Unsupported source receipt schema")
    checks = receipt.get("cooked_programmatic_checks")
    if not isinstance(checks, dict) or not checks or any(x is not True for x in checks.values()):
        raise ValueError("Cooked checks must be nonempty and all explicitly true")
    groups = {}
    all_paths = set()
    for group in ("frames", "package", "evidence"):
        rows = receipt.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Missing bound " + group)
        groups[group] = []
        for row in rows:
            path = check_binding(root, row)
            if path in all_paths:
                raise ValueError("Duplicate bound file: " + str(path))
            all_paths.add(path)
            groups[group].append((path, row["sha256"]))
    frames = groups["frames"]
    if len(frames) < 3 or len({digest for _, digest in frames}) != len(frames):
        raise ValueError("Need at least three distinct captured frames")
    for path, _ in frames:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format != "PNG" or min(image.size) < 64:
                raise ValueError("Frame must be a readable PNG, at least 64px")
    # Require the audit itself to be bound, not merely a hand-copied PASS field.
    audits = [(p, read_utf8(p)) for p, _ in groups["evidence"] if p.name == "audit.json"]
    if len(audits) != 1:
        raise ValueError("One hash-bound audit.json is required")
    _, audit = audits[0]
    if (audit.get("ok") is not True or audit.get("cooked_runtime") is not True
            or audit.get("checks") != checks or audit.get("error") not in (None, "")
            or audit.get("map") != str(receipt.get("map", "")).rsplit("/", 1)[-1]):
        raise ValueError("Bound runtime audit contradicts the scene receipt")
    recorded_frames = audit.get("frames")
    if not isinstance(recorded_frames, list) or [
            contained_file(root, p) for p in recorded_frames] != [p for p, _ in frames]:
        raise ValueError("Audit frame paths/order do not match bound captures")
    # Require an exact inventory; otherwise an unbound replacement DLL could sneak in.
    package_files = [p for p, _ in groups["package"]]
    package_root = Path(os.path.commonpath([str(p.parent) for p in package_files]))
    if package_root / "RacValidate.exe" not in package_files:
        raise ValueError("Lighting receipt adapter needs a RacValidate.exe bootstrap at package root")
    if output.is_relative_to(package_root):
        raise ValueError("Review output must be outside the verified package")
    actual = {p.resolve() for p in package_root.rglob("*") if p.is_file()
              and "Saved" not in p.relative_to(package_root).parts}
    if actual != set(package_files):
        raise ValueError("Package inventory changed (excluding runtime Saved files)")
    total = sum(p.stat().st_size for p in package_files)
    if receipt.get("package_bytes") != total:
        raise ValueError("Package byte total differs")
    if not isinstance(receipt.get("map"), str) or not receipt["map"].startswith("/Game/"):
        raise ValueError("Missing /Game map identity")
    # Local /Game content is explicit; never trust an arbitrary path from a receipt.
    maps = []
    for path, _ in groups["evidence"]:
        if path.suffix != ".json":
            continue
        data = read_utf8(path)
        if not isinstance(data, dict):
            continue
        for row in data.get("maps", []):
            if row.get("sha256") == receipt.get("map_sha256"):
                candidate = check_binding(root, row)
                if candidate.name == receipt["map"].rsplit("/", 1)[-1] + ".umap":
                    maps.append(candidate)
    if len(set(maps)) != 1:
        raise ValueError("Need one hash-bound local map matching the declared identity")
    if sha256_file(receipt_path) != receipt_hash:
        raise ValueError("Receipt changed during verification")
    # Reserve after validation. On an I/O failure leave an incomplete folder, no PASS.
    if any(p.is_relative_to(output) for p in all_paths | {receipt_path}):
        raise ValueError("Review output cannot contain its own source inputs")
    output.mkdir(parents=True, exist_ok=False)
    (output / "frames").mkdir()
    rendered, frame_rows = [], []
    for index, (path, digest) in enumerate(frames, 1):
        name = "frames/{0:02d}.png".format(index)
        dest = output / name
        shutil.copyfile(path, dest)
        if sha256_file(dest) != digest:
            raise ValueError("Frame changed while copying")
        label = path.stem
        rendered.append('<figure><img src="{0}" alt="{1}"><figcaption>{1}</figcaption></figure>'.format(
            name, html.escape(label)))
        frame_rows.append({"path": name, "sha256": digest, "caption": label})
    record = {"schema": REVIEW_SCHEMA, "human_review": "pending",
              "mechanical_verification": "passed", "production_ready": False,
              "source_receipt_sha256": receipt_hash, "map": receipt["map"],
              "map_sha256": receipt["map_sha256"], "package_bytes": total,
              "package_files": len(package_files), "checks": checks, "frames": frame_rows,
              "capture_provenance": "revalidated existing receipt; no new engine run",
              "source_visual_reviewer": receipt.get("reviewer"),
              "physical_keyboard_tested": False}
    record["verified_inputs"] = {
        group: [{"path": str(path.relative_to(root)).replace("\\", "/"),
                 "sha256": digest, "bytes": path.stat().st_size}
                for path, digest in rows]
        for group, rows in groups.items()}
    record["verified_map"] = {"path": str(maps[0].relative_to(root)).replace("\\", "/"),
                              "sha256": receipt["map_sha256"]}
    title = html.escape(str(receipt.get("variant", "Scene review")))
    page = ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>{0} — pending review</title><style>body{{background:#111822;color:#eee;'
            'font:17px/1.6 system-ui;margin:0 auto;padding:24px;max-width:1200px}}'
            'img{{width:100%;height:auto}}figure{{margin:24px 0}}'
            '.status{{padding:16px;border:1px solid #d7ab64}}a{{color:#f1c980}}</style>'
            '<h1>{0}</h1><p class="status">Awaiting human approval. Mechanical checks passed.'
            ' This is not visual approval or production certification.</p>'
            '<p>Revalidated existing cooked evidence; no new engine run. '
            'No physical-keyboard test is claimed.</p>{1}'
            '<p><a href="review.json">Hash-bound review record</a></p></html>').format(
                title, "".join(rendered))
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / "review.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record
