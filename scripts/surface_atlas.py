"""Read ordinary embedded glTF triangles and locate texel centres in their rest mesh."""

import io

import numpy as np
from PIL import Image


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def accessor(doc, binary, index):
    a = doc["accessors"][index]
    if "sparse" in a or "bufferView" not in a:
        raise ValueError("Sparse base geometry is not supported by the material baker")
    bv = doc["bufferViews"][a["bufferView"]]
    if bv.get("buffer", 0) != 0 or bv.get("extensions"):
        raise ValueError("Use an embedded, uncompressed geometry stream")
    kind = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}.get(a["componentType"])
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}.get(a["type"])
    if not kind or not n or a.get("normalized"):
        raise ValueError("Expected float vertex data or unsigned triangle indices")
    stride = np.dtype(kind).itemsize
    return np.ndarray(
        (a["count"], n),
        dtype=kind,
        buffer=binary,
        offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0),
        strides=(bv.get("byteStride", n * stride), stride),
    )


def read_image(doc, binary, slot):
    texture = doc["textures"][slot["index"]]
    if slot.get("texCoord", 0) != 0 or slot.get("extensions") or texture.get("extensions"):
        raise ValueError("This baker requires untransformed TEXCOORD_0 and a core texture")
    img = doc["images"][texture["source"]]
    v = doc["bufferViews"][img["bufferView"]]
    start = v.get("byteOffset", 0)
    return Image.open(io.BytesIO(binary[start : start + v["byteLength"]]))


def triangles(doc, binary, material):
    geom = []
    for mesh in doc.get("meshes", []):
        for pr in mesh["primitives"]:
            if pr.get("material") != material:
                continue
            if pr.get("mode", 4) != 4 or pr.get("extensions", {}).get("KHR_draco_mesh_compression"):
                raise ValueError("Expected uncompressed triangles")
            at = pr["attributes"]
            p = accessor(doc, binary, at["POSITION"])
            if "TEXCOORD_0" not in at or "NORMAL" not in at:
                raise ValueError("A mapped surface needs UV0 and normals")
            uv = accessor(doc, binary, at["TEXCOORD_0"])
            if np.any(uv < -1e-4) or np.any(uv > 1.0001):
                raise ValueError("Tiled UVs need a dedicated unique material atlas first")
            n = accessor(doc, binary, at["NORMAL"])
            idx = (
                accessor(doc, binary, pr["indices"]).ravel()
                if "indices" in pr
                else np.arange(len(p))
            ).reshape(-1, 3)
            t = accessor(doc, binary, at["TANGENT"])[idx] if "TANGENT" in at else None
            geom.append((p[idx], uv[idx], n[idx], t))
    if not geom:
        raise ValueError("The assigned material has no triangles")
    if any(item[3] is not None for item in geom) and any(item[3] is None for item in geom):
        raise ValueError("Use consistent tangent streams within the assigned material")
    return tuple(np.concatenate(items) if items[0] is not None else None for items in zip(*geom))


def raster(uv, width, height):
    """Batched bounding boxes: neither per-pixel Python nor a faces × atlas allocation."""
    q = uv.astype("d") * [width, height] - 0.5
    low = np.maximum(np.ceil(q.min(1)).astype(int), 0)
    high = np.minimum(np.floor(q.max(1)).astype(int), [width - 1, height - 1])
    span = np.maximum(0, high - low + 1)
    sizes = span.prod(1)
    total = np.r_[0, np.cumsum(sizes)]
    faces = np.full((height, width), -1, np.int32)
    bary = np.zeros((height, width, 2), np.float32)
    for start in range(0, total[-1], 250_000):
        linear = np.arange(start, min(start + 250_000, total[-1]))
        ids = np.searchsorted(total[1:], linear, side="right")
        local = linear - total[ids]
        x = low[ids, 0] + local % span[ids, 0]
        y = low[ids, 1] + local // span[ids, 0]
        a, b, c = q[ids].transpose(1, 0, 2)
        v, w = b - a, c - a
        det = v[:, 0] * w[:, 1] - v[:, 1] * w[:, 0]
        valid = abs(det) > 1e-10
        det = np.where(valid, det, 1.0)
        u = ((x - a[:, 0]) * w[:, 1] - (y - a[:, 1]) * w[:, 0]) / det
        t = (v[:, 0] * (y - a[:, 1]) - v[:, 1] * (x - a[:, 0])) / det
        yes = valid & (u >= -1e-7) & (t >= -1e-7) & (u + t <= 1 + 1e-7)
        yy, xx = y[yes], x[yes]
        faces[yy, xx] = ids[yes]
        bary[yy, xx] = np.stack((u[yes], t[yes]), axis=1)
    return faces, bary


def frames(geometry, size):
    p, uv, normals, tangents = geometry
    face, bary = raster(uv, size, size)
    yy, xx = np.where(face >= 0)
    if not len(yy):
        raise ValueError("No UV triangle covers a texel at this bake resolution")
    f = face[yy, xx]
    b = bary[yy, xx]
    weights = np.c_[1 - b.sum(1), b]
    pos = np.einsum("ij,ijk->ik", weights, p[f])
    n = unit(np.einsum("ij,ijk->ik", weights, normals[f]))
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    u, v = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
    det = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
    det[abs(det) < 1e-12] = 1.0
    du = (e1 * v[:, 1, None] - e2 * u[:, 1, None]) / det[:, None]
    dv = (e2 * u[:, 0, None] - e1 * v[:, 0, None]) / det[:, None]
    footprint = np.maximum(np.linalg.norm(du, axis=1), np.linalg.norm(dv, axis=1))[f] / size
    if tangents is not None:
        interp = np.einsum("ij,ijk->ik", weights, tangents[f])
        t, sign = interp[:, :3], np.sign(interp[:, 3])
    else:
        t = du[f]
        sign = np.sign(np.sum(np.cross(n, t) * dv[f], axis=1))
    t = unit(t - n * np.sum(t * n, axis=1, keepdims=True))
    return yy, xx, pos, t, np.cross(n, t) * sign[:, None], footprint
