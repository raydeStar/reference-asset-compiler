"""Reference-space checks for a Pixal open frame, before UVs or paint."""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from project_reference import camera_frame, fit_camera, load_glb, project, turn
from frame_seating import measure_seats, seat_transform


def validate_mounts(data, run_m):
    if not isinstance(data, dict):
        raise ValueError("Mounting annotations must be an object.")
    for key in ("lowerFoot", "upperFoot", "postTop"):
        point = data[key]
        if (not isinstance(point, list) or len(point) != 2 or
                any(type(v) not in (float, int) or not 0 <= v <= 1 for v in point)):
            raise ValueError(f"{key} requires normalized reference x and y coordinates.")
    if len({tuple(data[k]) for k in ("lowerFoot", "upperFoot", "postTop")}) != 3:
        raise ValueError("Mark three distinct landmarks.")
    if type(data["riseM"]) not in (float, int) or not 0 <= data["riseM"] <= 50:
        raise ValueError("Mounting rise must be between zero and 50 metres.")
    return {**data, "runM": run_m}


def pixel_vertices(vertices, camera):
    u, v = project(camera["params"], vertices)
    return np.column_stack((u, v)) * camera["scale"] + camera["offset"]


def rasterize(points, faces, shape):
    """Union of triangles sampled at pixel centres, independent of triangulation density."""
    height, width = shape
    image = np.zeros(shape, dtype=bool)
    # Expand only the scanlines touched by each triangle. Process chunks so
    # a large, thin projected triangle cannot reserve a whole dense atlas.
    for start in range(0, len(faces), 2048):
        tri = points[faces[start:start + 2048]]
        x, y = tri[:, :, 0], tri[:, :, 1]
        first = np.clip(np.ceil(y.min(axis=1) - .5).astype(int), 0, height)
        end = np.clip(np.ceil(y.max(axis=1) - .5).astype(int), 0, height)
        counts = end - first
        index = np.repeat(np.arange(len(tri)), counts)
        if not len(index):
            continue
        rows = np.arange(len(index)) + np.repeat(first - (np.cumsum(counts) - counts), counts)
        scan = rows + .5
        left, right = np.full(len(rows), np.inf), np.full(len(rows), -np.inf)
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ay, by = y[index, a], y[index, b]
            hit = (ay > scan) != (by > scan)
            i = index[hit]
            crossing = x[i, a] + (scan[hit] - ay[hit]) * (x[i, b] - x[i, a]) / (by[hit] - ay[hit])
            left[hit] = np.minimum(left[hit], crossing)
            right[hit] = np.maximum(right[hit], crossing)
        lo = np.clip(np.ceil(left - .5), 0, width).astype(int)
        hi = np.clip(np.ceil(right - .5), 0, width).astype(int)
        valid = hi > lo
        if not valid.any():
            continue
        rows, lo, hi = rows[valid], lo[valid], hi[valid]
        lengths = hi - lo
        if lengths.sum() > 2_000_000:
            delta = np.zeros((height, width + 1), dtype=np.int32)
            np.add.at(delta, (rows, lo), 1)
            np.add.at(delta, (rows, hi), -1)
            image |= np.cumsum(delta[:, :-1], axis=1) > 0
            continue
        cols = np.arange(lengths.sum()) + np.repeat(lo - (np.cumsum(lengths) - lengths), lengths)
        image[np.repeat(rows, lengths), cols] = True
    return image


def overlap(a, b):
    return float(np.count_nonzero(a & b) / max(1, np.count_nonzero(a | b)))


def fit_frame_camera(vertices, faces, reference, fov):
    """The coarse camera is a starting point. Judge and refine thin edges at source resolution."""
    coarse = fit_camera(vertices, faces, reference, fov)
    yy, xx = np.nonzero(reference)
    low = np.array((xx.min(), yy.min()))
    high = np.array((xx.max()+1, yy.max()+1))

    def candidate(params, shift):
        uv = np.column_stack(project(params, vertices))
        scale = float((high-low).max() / np.ptp(uv, axis=0).max())
        offset = .5*(low + high - scale*(uv.max(axis=0) + uv.min(axis=0))) + shift
        score = overlap(reference, rasterize(uv*scale+offset, faces, reference.shape))
        return {"params": list(params), "scale": scale, "offset": offset.tolist(), "iou": score}

    shift = np.zeros(2)
    best = max([candidate(coarse["params"], shift), candidate([0., 0., 0., fov], shift)], key=lambda c: c["iou"])
    for step in (1., .5, .25):
        for _ in range(3):
            previous = best["iou"]
            for axis in range(6):
                origin, origin_shift = best["params"], shift.copy()
                for sign in (-1, 1):
                    params, delta = list(origin), origin_shift.copy()
                    if axis < 4:
                        params[axis] += sign * step
                        if not 2 <= params[3] <= 60:
                            continue
                    else:
                        delta[axis-4] += sign * step
                    trial = candidate(params, delta)
                    if trial["iou"] > best["iou"] + 1e-6:
                        best, shift = trial, delta
            if best["iou"] == previous or best["iou"] == 1.:
                break
    best["coarse_iou"] = coarse["iou"]
    return best


def opening_errors(reference, drawn):
    """Each enclosed reference space must still have its own enclosed background region."""
    expected, _ = ndimage.label(np.pad(~reference, 1, constant_values=True))
    actual, _ = ndimage.label(np.pad(~drawn, 1, constant_values=True))
    seen = set()
    errors = []
    for label, bounds in enumerate(ndimage.find_objects(expected), 1):
        if label == expected[0, 0] or bounds is None:
            continue
        region = expected[bounds] == label
        if np.count_nonzero(region) < 16:
            continue
        distance = ndimage.distance_transform_edt(np.pad(region, 1))[1:-1, 1:-1]
        centre = np.unravel_index(distance.argmax(), region.shape)
        actual_label = actual[bounds][centre]
        if actual_label == 0 or actual_label == actual[0, 0] or actual_label in seen:
            errors.append("A reference opening is filled, open to the exterior, or merged with its neighbour.")
        seen.add(actual_label)
    return errors


def overlay(reference, drawn, destination):
    rgb = np.zeros((*reference.shape, 3), dtype=np.uint8)
    rgb[reference & drawn] = (215, 215, 215)
    rgb[reference & ~drawn] = (240, 75, 54)
    rgb[drawn & ~reference] = (55, 164, 255)
    Image.fromarray(rgb).save(destination)


def span_errors(reference, pixels, vertices, faces, feet):
    """Test each separate interior bar for a continuous welded path across the clear span."""
    low, high = feet
    dx = high[0] - low[0]
    if abs(dx) < 1:
        return ["The reference must show both mounting feet apart horizontally."]
    # Cut beyond the shafts and check the clear lengths. In this strip each
    # distinct reference member is a separate connected foreground region.
    xx = np.arange(reference.shape[1]) + .5
    fraction = (xx - low[0]) / dx
    inside = (fraction >= .08) & (fraction <= .92)
    labels, _ = ndimage.label(reference & inside[None, :], structure=np.ones((3, 3)))
    mid = pixels[faces].mean(axis=1)
    ix, iy = np.floor(mid).astype(int).T
    valid = (ix >= 0) & (iy >= 0) & (ix < labels.shape[1]) & (iy < labels.shape[0])
    assigned = np.zeros(len(faces), dtype=int)
    assigned[valid] = labels[iy[valid], ix[valid]]
    # Pixal can export duplicate vertices at UV seams. Weld coincident positions
    # only, so unrelated bars crossing the same image pixel cannot close a break.
    extent = np.ptp(vertices, axis=0).max()
    _, welded = np.unique(np.round(vertices / max(1e-12, extent * 1e-6)).astype(np.int64),
                          axis=0, return_inverse=True)
    along = (pixels[:, 0] - low[0]) / dx
    errors = []
    tested = 0
    for label, bounds in enumerate(ndimage.find_objects(labels), 1):
        if bounds is None or bounds[1].stop - bounds[1].start < .80 * abs(dx):
            continue
        tested += 1
        triangles = faces[assigned == label]
        if len(triangles):
            used, local = np.unique(welded[triangles], return_inverse=True)
            edges = local.reshape(-1, 3)
            graph = coo_matrix((np.ones(edges.size, dtype=bool),
                                (edges.ravel(), np.roll(edges, 1, axis=1).ravel())),
                               shape=(len(used), len(used)))
            _, groups = connected_components(graph, directed=False)
            starts = groups[edges[along[triangles] <= .10]]
            ends = groups[edges[along[triangles] >= .90]]
            if np.intersect1d(starts, ends).size:
                continue
        errors.append(f"Member {tested} has no continuous mesh path across its clear span.")
    if not tested:
        errors.append("No distinct spanning members could be resolved between the marked feet.")
    return errors


def resolve_anchor(vertices, faces, pixels, xy, camera):
    """Frontmost ray/triangle hit, with perspective-correct barycentric coordinates."""
    tri = pixels[faces]
    p = np.array(xy)
    near = np.all((tri.min(axis=1) <= p) & (tri.max(axis=1) >= p), axis=1)
    ids = faces[near]
    a, b, c = tri[near].transpose(1, 0, 2)
    def cross(u, v):
        return u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
    det = cross(b-a, c-a)
    valid = np.abs(det) > 1e-12
    ids, a, b, c, det = ids[valid], a[valid], b[valid], c[valid], det[valid]
    u, v = cross(p-a, c-a)/det, cross(b-a, p-a)/det
    weights = np.column_stack((1-u-v, u, v))
    hit = np.all(weights >= -1e-7, axis=1)
    if not hit.any():
        raise ValueError("A mounting landmark misses the acquired mesh.")
    ids, weights = ids[hit], weights[hit]
    pitch, yaw, roll, fov = camera["params"]
    depth = (camera_frame(vertices) @ turn(pitch, yaw, roll).T)[:, 1] + .5 / math.tan(math.radians(fov)/2)
    weights = weights / depth[ids]
    nearest = weights.sum(axis=1).argmax()
    return np.average(vertices[ids[nearest]], axis=0, weights=weights[nearest])


def mounting_transform(hits, run):
    foot, upper, cap = hits
    up = cap - foot
    if np.linalg.norm(up) < 1e-8:
        raise ValueError("Lower foot and post top coincide.")
    up = up / np.linalg.norm(up)
    along = upper - foot
    along -= up * (along @ up)
    span = np.linalg.norm(along)
    if span < 1e-8:
        raise ValueError("Mounting feet coincide along the run.")
    along /= span
    matrix = np.eye(4)
    matrix[:3, :3] = np.stack((along, np.cross(up, along), up)) * (run / span)
    matrix[:3, 3] = -matrix[:3, :3] @ foot
    return matrix


def reduction_weights(reference):
    """Protect narrow reference members and contours, leaving broad surfaces cheaper to collapse."""
    distance = ndimage.distance_transform_edt(reference)
    half_width = max(2., .01 * max(reference.shape))
    return np.clip(1 - distance / (2 * half_width), 0, 1).astype(np.float32)


def frame_check(attempt: Path, game: Path, mounts: dict | None, camera=None):
    with Image.open(attempt / "cutout.png") as image:
        ref = np.asarray(image.convert("RGBA"))[:, :, 3] > 127
    if not ref.any():
        raise ValueError("The reference has no foreground.")
    gv, gf = load_glb(game)
    dv, df = load_glb(attempt / "pixal.glb")
    logged = re.search(r"camera_angle_x=([0-9.]+)", (attempt / "pixal.log").read_text(errors="replace"))
    if camera is None:
        camera = fit_frame_camera(gv, gf, ref, math.degrees(float(logged[1])) if logged else 15.)
    errors, metrics, anchors = [], {}, {}
    for name, verts, faces in (("dense", dv, df), ("game", gv, gf)):
        pixels = pixel_vertices(verts, camera)
        mask = rasterize(pixels, faces, ref.shape)
        iou = overlap(ref, mask)
        file = attempt / (name + "-overlay.png")
        overlay(ref, mask, file)
        metrics[name] = {"iou": iou, "overlay": str(file)}
        if iou < .97:
            errors.append(f"{name} outline {iou:.1%} below 97%")
        errors.extend(f"{name}: {reason}" for reason in opening_errors(ref, mask))
        if mounts is None:
            continue
        coords = np.array([mounts[k] for k in ("lowerFoot", "upperFoot", "postTop")]) * np.array(ref.shape[::-1])
        errors.extend(f"{name}: {reason}" for reason in span_errors(ref, pixels, verts, faces, coords[:2]))
        try:
            anchors[name] = np.array([resolve_anchor(verts, faces, pixels, xy, camera) for xy in coords])
        except ValueError as exc:
            errors.append(f"{name}: {exc}")
    result = {"camera": camera, "surfaces": metrics, "reasons": errors, "ok": False}
    if mounts and "dense" in anchors:
        transform = mounting_transform(anchors["dense"], mounts["runM"])
        transform = seat_transform(dv, transform, mounts["runM"])
        for name, vertices in (("dense", dv), ("game", gv)):
            placed = vertices @ transform[:3, :3].T + transform[:3, 3]
            measurements, problems = measure_seats(placed, mounts["runM"], mounts["riseM"])
            metrics[name].update(measurements)
            errors.extend(f"{name}: {problem}" for problem in problems)
        # level_pair imports GLB in Blender coordinates.
        blender_to_gltf = np.eye(4)[[0, 2, 1, 3]]
        blender_to_gltf[2] *= -1
        result["transform"] = (transform @ blender_to_gltf).tolist()
    result["ok"] = not errors
    return result
