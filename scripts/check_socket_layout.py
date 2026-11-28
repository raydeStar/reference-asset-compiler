"""Measure sockets on a reference elevation, or on both of its acquired meshes."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from pixal_frame import pixel_vertices, resolve_anchor
from project_reference import load_glb, sha256


def measure(spec):
    picture = Path(spec["picture"])
    if sha256(picture) != spec["picture_sha256"]:
        raise ValueError("Socket marks belong to a different reference.")
    with Image.open(picture) as source:
        image = source.convert("RGB")
    top, bottom = spec["top_y"], spec["bottom_y"]
    width, height = image.size
    target, tolerance = spec["height_m"], spec["tolerance_m"]
    if not (0 <= top < bottom <= 1 and 0 < tolerance < target):
        raise ValueError("Expected top and underside marks, a physical height, and a positive fit tolerance.")
    sockets = spec["sockets"]
    if not sockets:
        raise ValueError("Mark the centre of each socket.")
    geometries = {}
    if spec.get("geometry"):
        receipt = json.loads(Path(spec["geometry"]).read_text(encoding="utf-8"))
        if (receipt["picture_sha256"] != spec["picture_sha256"] or not receipt["frame_check"]["ok"]
                or not receipt["game_mesh_check"]["ok"] or receipt["size_is"] != "height"
                or abs(receipt["size_m"] - target) > 1e-6):
            raise ValueError("Use passing geometry acquired from this exact picture at the measured height.")
        camera = receipt["frame_check"]["camera"]
        transform = np.asarray(receipt["level"]["transform"])
        for role, name in (("dense", "pixal.glb"), ("game", f'pixal-v{receipt["vertex_target"]}.glb')):
            mesh = Path(receipt["attempt"]) / name
            if sha256(mesh) != receipt["pixal"][role + "_sha256"]:
                raise ValueError(f"The {role} mesh differs from its receipt.")
            vertices, faces = load_glb(mesh)
            geometries[role] = (vertices, faces, pixel_vertices(vertices, camera))

    draw = ImageDraw.Draw(image)
    rows, reasons = [], []
    for socket in sockets:
        x, y = socket["centre"]
        want = socket["height_m"]
        if not (0 <= x <= 1 and top <= y <= bottom and 0 <= want <= target):
            raise ValueError("Socket centre or declared height lies outside the marked post.")
        actual = {"reference": (bottom - y)/(bottom - top) * target}
        point = (x * width, y * height)
        for role, (vertices, faces, pixels) in geometries.items():
            a = resolve_anchor(vertices, faces, pixels, point, camera)
            actual[role] = float((transform @ [a[0], -a[2], a[1], 1])[2])
        for role, seen in actual.items():
            if abs(seen - want) > tolerance:
                reasons.append(f'{socket["name"]} ({role}): {seen:.3f} m, expected {want:.3f} m.')
        desired_y = height * (bottom - want/target*(bottom - top))
        draw.line((x*width-42, desired_y, x*width+42, desired_y), fill="#1fcf74", width=4)
        draw.ellipse((x*width-7, y*height-7, x*width+7, y*height+7), outline="#ff573e", width=4)
        rows.append({"socket": socket["name"], "target_m": want, "measured_m": actual})
    return image, {"schema": "reference-asset-compiler.socket-layout.v1", "ok": not reasons,
                   "picture_sha256": spec["picture_sha256"], "tolerance_m": tolerance, "sockets": rows,
                   "geometry": spec.get("geometry"), "reasons": reasons}


def main(spec_file, output, report):
    spec_file, output, report = map(Path, (spec_file, output, report))
    if output.exists() or report.exists():
        raise ValueError("Choose new paths for the socket overlay and receipt.")
    spec = json.loads(spec_file.read_text(encoding="utf-8-sig"))
    image, result = measure(spec)
    image.save(output)
    result.update(overlay=str(output), source_sha256=sha256(spec_file))
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["ok"]:
        print("[SOCKETS] FAILED: " + " ".join(result["reasons"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[sys.argv.index("--")+1:]))
