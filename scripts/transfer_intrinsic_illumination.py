"""Transport only broad AI-estimated luminance gains through unchanged mesh/UV correspondence.

The estimator never supplies replacement facial features, hues or edge artwork.
Head/neck triangles and unseen texels retain their original bytes. No gate-score
optimization is performed; settings are fixed before candidate measurement.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from map_face_donor import pad_face_gutters
from projection_visibility import depth_visible, project_surface
from raster_geometry import triangle_pixels


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linear(rgb):
    value = np.asarray(rgb, dtype=np.float64) / 255
    return np.where(value <= .04045, value / 12.92, ((value + .055) / 1.055) ** 2.4)


def encode(rgb):
    rgb = np.maximum(rgb, 0)
    return np.rint(np.clip(np.where(rgb <= .0031308, rgb * 12.92,
                                   1.055 * rgb ** (1 / 2.4) - .055), 0, 1) * 255).astype(np.uint8)


def validate_donor_signal(source_rgba, donor_rgb):
    foreground = (source_rgba[..., 3] >= 254) & (np.mean(source_rgba[..., :3], axis=2) > 35)
    if not np.any(foreground):
        raise ValueError("Source has insufficient visible color for illumination estimation")
    collapsed = np.mean(np.max(donor_rgb[foreground], axis=1) < 5)
    if collapsed > .5:
        raise ValueError("Estimator collapsed colored foreground to a black silhouette")
    return float(collapsed)


def illumination_field(source_rgba, donor_rgb, sigma=16):
    if source_rgba.shape[:2] != donor_rgb.shape[:2] or source_rgba.shape[2] != 4:
        raise ValueError("Estimator images must match the actual RGBA camera input")
    mask = source_rgba[..., 3] >= 254
    luminance = np.array([.2126, .7152, .0722])
    src = linear(source_rgba[..., :3]) @ luminance
    dst = linear(donor_rgb) @ luminance
    # The floor prevents near-black paint from acquiring enormous gains.
    raw = np.log(dst + .01) - np.log(src + .01)
    support = ndimage.gaussian_filter(mask.astype(float), sigma)
    smoothed = ndimage.gaussian_filter(raw * mask, sigma) / np.maximum(support, 1e-8)
    smoothed = np.clip(smoothed, np.log(.5), np.log(2))
    boundary = np.clip(ndimage.distance_transform_edt(mask) / 8, 0, 1)
    return smoothed, boundary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path)
    parser.add_argument("inference", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Choose a new retained transport candidate")
    inputs = json.loads(args.inputs.read_text())
    inference = json.loads(args.inference.read_text())
    if inference["status"] != "candidate_needs_review" or inference["inputs_receipt_sha256"] != sha(args.inputs):
        raise ValueError("Estimator output is not bound to the supplied camera input receipt")
    if len(inputs["textures"]) != 1:
        raise ValueError("Require one unambiguous source albedo")
    source, source_hash = next(iter(inputs["textures"].items()))
    if sha(source) != source_hash or sha(inputs["source"]) != inputs["source_sha256"]:
        raise ValueError("Changed mesh or albedo authority")
    base = np.asarray(Image.open(source).convert("RGB"))
    size = base.shape[0]
    if base.shape[:2] != (size, size):
        raise ValueError("Require a square atlas")
    expected_views = {"body-" + name for name in ("front", "side", "back", "opposite", "top", "bottom")}
    oblique_views = {"body-" + name for name in ("front", "right-oblique", "back", "left-oblique", "top", "bottom")}
    names = {Path(frame["path"]).stem for frame in inputs["frames"]}
    if names != expected_views and names != oblique_views:
        raise ValueError("Require the six declared orbit views")
    sum_gain = np.zeros((size, size), np.float32)
    sum_weight = np.zeros_like(sum_gain)
    occupied = np.zeros((size, size), bool)
    protected = np.zeros_like(occupied)
    rows = []
    reference_uv = reference_height = None
    for frame in inputs["frames"]:
        name = Path(frame["path"]).name
        donor = next(row for row in inference["outputs"] if Path(row["path"]).name == name)
        for path, expected_hash in [(frame["path"], frame["sha256"]),
                                    (donor["path"], donor["sha256"]),
                                    (frame["correspondence"], frame["correspondence_sha256"])]:
            if sha(path) != expected_hash:
                raise ValueError("Changed transfer input " + str(path))
        with np.load(frame["correspondence"]) as archive:
            data = {key: archive[key] for key in archive.files}
        if reference_uv is None:
            reference_uv, reference_height = data["uv"], data["height"]
        elif not (np.array_equal(reference_uv, data["uv"]) and np.array_equal(reference_height, data["height"])):
            raise ValueError("Multiview geometry/UV correspondence drift")
        source_image = np.asarray(Image.open(frame["path"]).convert("RGBA"))
        donor_image = np.asarray(Image.open(donor["path"]).convert("RGB"))
        collapsed_fraction = validate_donor_signal(source_image, donor_image)
        field, boundary = illumination_field(source_image, donor_image)
        changed_samples = 0
        for i, uv in enumerate(data["uv"]):
            pixels = triangle_pixels(uv, size)
            if pixels is None:
                continue
            yy, xx, weights = pixels
            occupied[yy, xx] = True
            if np.max(data["height"][i]) >= .82:
                protected[yy, xx] = True
                continue
            screen, depth = project_surface(weights, data["screen"][i], data["depth"][i])
            visible = depth_visible(screen, depth, data["depth_buffer"], float(data["depth_tolerance"]))
            facing = np.clip((weights @ data["cosine"][i] - .2) / .6, 0, 1) ** 4
            seam_fade = ndimage.map_coordinates(boundary, [screen[:, 1], screen[:, 0]], order=1, mode="constant")
            height = weights @ data["height"][i]
            head_fade = np.clip((.82 - height) / .14, 0, 1)
            confidence = facing * visible * seam_fade
            gain = ndimage.map_coordinates(field, [screen[:, 1], screen[:, 0]], order=1, mode="constant")
            sum_gain[yy, xx] += gain * confidence * head_fade
            sum_weight[yy, xx] += confidence
            changed_samples += int(np.count_nonzero(confidence))
        rows.append({"name": name, "mapped_samples": changed_samples,
                     "collapsed_colored_fraction": collapsed_fraction,
                     "field_log_gain_range": [float(field.min()), float(field.max())]})
        print("ILLUMINATION_VIEW_BOUND", name, changed_samples, flush=True)
    support = (sum_weight > .001) & ~protected
    gain = np.ones_like(sum_gain)
    confidence_fade = np.clip(sum_weight / .15, 0, 1)
    gain[support] = np.exp(sum_gain[support] / sum_weight[support] * confidence_fade[support])
    result = base.copy()
    unbounded = linear(base[support]) * gain[support, None]
    result[support] = encode(unbounded)
    if not np.array_equal(result[protected], base[protected]):
        raise ValueError("Head protection failed")
    result, gutters = pad_face_gutters(result, occupied, support, 8)
    if not np.array_equal(result[~(support | gutters)], base[~(support | gutters)]):
        raise ValueError("Changed texels outside mapped support")
    if support.sum() < 1000:
        raise ValueError("Insufficient mapped body coverage")
    output.mkdir(parents=True)
    Image.fromarray(result).save(output / "BaseColor.png")
    Image.fromarray(support.astype(np.uint8) * 255).save(output / "support.png")
    Image.fromarray(protected.astype(np.uint8) * 255).save(output / "protected-head.png")
    Image.fromarray(gutters.astype(np.uint8) * 255).save(output / "gutters.png")
    np.save(output / "luminance-gain.npy", gain)
    report = {
        "schema": "reference-asset-compiler.intrinsic-illumination-transfer.v1",
        "input_receipt": str(args.inputs.resolve()), "inference_receipt": str(args.inference.resolve()),
        "input_receipt_sha256": sha(args.inputs), "inference_receipt_sha256": sha(args.inference),
        "source_mesh_sha256": inputs["source_sha256"], "source_albedo_sha256": source_hash,
        "output_sha256": sha(output / "BaseColor.png"), "script_sha256": sha(__file__),
        "views": rows, "support_texels": int(support.sum()), "protected_head_texels": int(protected.sum()),
        "gutter_texels": int(gutters.sum()), "head_bit_identical": True,
        "outside_support_and_gutters_bit_identical": True, "geometry_or_uv_edited": False,
        "changed_texels": int(np.any(result != base, axis=2).sum()),
        "clipped_mapped_channel_fraction": float(np.mean(unbounded > 1)),
        "gain_range": [float(gain.min()), float(gain.max())],
        "settings": {"sigma_screen_pixels": 16, "luminance_floor": .01, "gain_limits": [.5, 2],
                     "head_protect_height": .82, "head_transition_start": .68},
        "method": "Masked low-frequency log-luminance ratio; perspective/depth-aware UV transport; scalar linear-RGB gain",
        "production_ready": False, "status": "candidate_requires_actual_mesh_review",
    }
    (output / "transfer.json").write_text(json.dumps(report, indent=2) + "\n")
    print("ILLUMINATION_TRANSFER_READY -- borrowed illumination, original identity.", flush=True)


if __name__ == "__main__":
    main()
