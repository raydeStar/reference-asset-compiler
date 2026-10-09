"""Register orthographic pictures to a mesh and bake their paint into its UVs.

A character's turnaround (front, side, back) is the paint authority. Each
picture is an orthographic view along a world axis; registering it is a 2D
similarity between the view plane and the picture's pixels. The front is
registered from face landmarks (see conform_head_template.py); a side or back
view, which landmarks cannot anchor, is registered by matching the mesh's
silhouette to the picture's foreground.

Baking rasterizes each mesh in its UV space, finds every texel's surface point
and normal, and averages the pictures that see it, weighted by how squarely
they face it and only where the point is not hidden in that view.

Pure NumPy/SciPy/Pillow.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, optimize

# View name -> (plane x axis, plane y axis, direction the camera looks along).
# Plane coordinates grow right and down, as pixels do.
VIEW_AXES = {
    "front": (np.array([1.0, 0, 0]), np.array([0, 0, -1.0]), np.array([0, 1.0, 0])),
    "left": (np.array([0, 1.0, 0]), np.array([0, 0, -1.0]), np.array([-1.0, 0, 0])),
    "right": (np.array([0, -1.0, 0]), np.array([0, 0, -1.0]), np.array([1.0, 0, 0])),
    "back": (np.array([-1.0, 0, 0]), np.array([0, 0, -1.0]), np.array([0, -1.0, 0])),
}


@dataclass
class View:
    name: str
    image: np.ndarray          # (H, W, 3) float 0..1
    scale: float               # pixels per metre
    rotation: np.ndarray       # (2, 2)
    translation: np.ndarray    # (2,)
    mask: np.ndarray | None = None   # picture foreground; backdrop is never paint
    weight: float = 1.0              # trust relative to the other views
    sharpness: float = 4.0           # how squarely a surface must face this view
    warp: object = None              # local pixel correction, plane -> (dx, dy)
    gain: np.ndarray | None = None   # per-channel colour gain toward the other views

    def plane(self, pts):
        ax, ay, _ = VIEW_AXES[self.name]
        return np.stack([pts @ ax, pts @ ay], axis=1)

    def pixels(self, pts):
        plane = self.plane(pts)
        px = self.scale * plane @ self.rotation.T + self.translation
        if self.warp is not None:
            px = px + self.warp(plane)
        return px

    def depth(self, pts):
        return pts @ VIEW_AXES[self.name][2]

    def colour(self, px):
        c = sample(self.image, px)
        return c if self.gain is None else np.clip(c * self.gain, 0, 1)


class LocalWarp:
    """Pixel corrections at a few plane points, fading out with distance.

    A generated side view draws the features a few millimetres away from where
    the mesh (fitted to the front) has them. A Gaussian radial-basis warp moves
    the picture's eye, brow, nose, mouth and chin onto the mesh's own, and is
    zero away from them, so the silhouette registration still holds for hair.
    """

    def __init__(self, plane_points, corrections, radius=0.025):
        from scipy.interpolate import RBFInterpolator
        self.radius = radius
        self.rbf = RBFInterpolator(np.asarray(plane_points, float), np.asarray(corrections, float),
                                   kernel="gaussian", epsilon=1.0 / radius)

    def __call__(self, plane):
        return self.rbf(plane)


class MirroredWarp:
    def __init__(self, warp):
        self.warp = warp

    def __call__(self, plane):
        c = self.warp(np.c_[-plane[:, 0], plane[:, 1]])
        return np.c_[-c[:, 0], c[:, 1]]


def load_image(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0


def foreground_mask(image, threshold=0.08, fill=True, shrink=0):
    """Picture foreground against a flat backdrop sampled from its border.

    `fill` closes enclosed holes -- right for a silhouette, wrong for paint,
    where the backdrop showing between strands of hair must stay backdrop.
    """
    border = np.concatenate([image[:8].reshape(-1, 3), image[-8:].reshape(-1, 3),
                             image[:, :8].reshape(-1, 3), image[:, -8:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    mask = np.linalg.norm(image - bg, axis=2) > threshold
    mask = ndimage.binary_opening(mask, iterations=2)
    if fill:
        mask = ndimage.binary_fill_holes(mask)
    lab, n = ndimage.label(mask)
    if n > 1:
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        mask = lab == (1 + int(np.argmax(sizes)))
    if shrink:
        # Outline pixels blend subject and backdrop; paint never takes them.
        mask = ndimage.binary_erosion(mask, iterations=shrink)
    return mask


def rasterize_mask(points2d, tris, shape):
    img = Image.new("L", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(img)
    for t in tris:
        draw.polygon([tuple(points2d[i]) for i in t], fill=255)
    return np.asarray(img) > 0


def register_by_silhouette(name, image, verts, tris, init_scale, grid=0.0005):
    """Similarity (no rotation) placing the mesh silhouette on the picture's foreground."""
    ax, ay, _ = VIEW_AXES[name]
    plane = np.stack([verts @ ax, verts @ ay], 1)
    lo, hi = plane.min(0), plane.max(0)
    size = np.ceil((hi - lo) / grid).astype(int) + 4
    mesh_mask = rasterize_mask((plane - lo) / grid + 2, tris, (size[1], size[0]))
    fg = foreground_mask(image)
    ys, xs = np.nonzero(fg)
    my, mx = np.nonzero(mesh_mask)

    def picture_in_plane(params):
        s, tx, ty = params
        # plane cell (i, j) -> plane metres -> pixels
        m = np.array([[grid * s, 0.0, (lo[0] - 2 * grid) * s + tx],
                      [0.0, grid * s, (lo[1] - 2 * grid) * s + ty]])
        warped = Image.fromarray(fg.astype(np.uint8) * 255).transform(
            (mesh_mask.shape[1], mesh_mask.shape[0]), Image.AFFINE, m.ravel().tolist(),
            resample=Image.NEAREST)
        return np.asarray(warped) > 0

    def iou(params):
        pic = picture_in_plane(params)
        inter = (pic & mesh_mask).sum()
        union = (pic | mesh_mask).sum()
        return inter / max(union, 1)

    # Start: the given scale; centres and tops aligned.
    s0 = init_scale
    tx0 = xs.mean() - s0 * (lo[0] + (mx.mean() - 2) * grid)
    ty0 = ys.min() - s0 * (lo[1] + (my.min() - 2) * grid)
    best = (iou((s0, tx0, ty0)), (s0, tx0, ty0))
    for ds in np.linspace(0.85, 1.15, 7):
        p = (s0 * ds, xs.mean() - s0 * ds * (lo[0] + (mx.mean() - 2) * grid),
             ys.min() - s0 * ds * (lo[1] + (my.min() - 2) * grid))
        v = iou(p)
        if v > best[0]:
            best = (v, p)
    start = np.array(best[1])
    simplex = np.vstack([start, start + [start[0] * 0.03, 0, 0], start + [0, 15.0, 0],
                         start + [0, 0, 15.0]])
    res = optimize.minimize(lambda p: -iou(p), start, method="Nelder-Mead",
                            options={"xatol": 0.2, "fatol": 1e-5, "maxiter": 400,
                                     "initial_simplex": simplex})
    s, tx, ty = res.x
    return View(name=name, image=image, scale=float(s), rotation=np.eye(2),
                translation=np.array([tx, ty])), float(-res.fun)


def mirrored(view: View, name="right"):
    """The opposite side from a single side picture: flip it left-right."""
    w = view.image.shape[1]
    return View(name=name, image=view.image[:, ::-1].copy(), scale=view.scale,
                rotation=view.rotation.copy(),
                translation=np.array([w - 1 - view.translation[0], view.translation[1]]),
                mask=None if view.mask is None else view.mask[:, ::-1].copy(),
                weight=view.weight, sharpness=view.sharpness,
                warp=None if view.warp is None else MirroredWarp(view.warp), gain=view.gain)


def register_profile(view: View, skin_verts, skin_tris, z_top, z_bottom, grid=0.00025):
    """Refine a side view by the face's profile line: brow to chin.

    A whole-head silhouette is dominated by hair, which a generated side view
    and a generated mesh draw differently; the profile from the eyes down
    (nose, lips, chin) is the face's own outline and pins the painted
    features. Searches scale and vertical offset; the horizontal offset
    follows in closed form.
    """
    ax, ay, _ = VIEW_AXES[view.name]
    plane = np.stack([skin_verts @ ax, skin_verts @ ay], 1)
    lo = plane.min(0) - 2 * grid
    size = np.ceil((plane.max(0) - lo) / grid).astype(int) + 4
    mmask = rasterize_mask((plane - lo) / grid, skin_tris, (size[1], size[0]))
    rows = np.arange(int((-z_top - lo[1]) / grid), int((-z_bottom - lo[1]) / grid))
    rows = rows[(rows >= 0) & (rows < mmask.shape[0])]
    has = mmask[rows].any(1)
    rows = rows[has]
    # The face's front edge: smallest plane x for a left view, largest for a right one.
    front_left = view.name == "left"
    edge = np.array([(np.flatnonzero(mmask[r]).min() if front_left else np.flatnonzero(mmask[r]).max())
                     for r in rows])
    mesh_x = lo[0] + edge * grid
    mesh_y = lo[1] + rows * grid
    fg = view.mask if view.mask is not None else foreground_mask(view.image)
    h, w = fg.shape
    first = np.full(h, -1.0)
    for r in range(h):
        nz = np.flatnonzero(fg[r])
        if len(nz):
            first[r] = nz.min() if front_left else nz.max()

    def residual(params):
        s, ty = params
        py = np.round(s * mesh_y + ty).astype(int)
        ok = (py >= 0) & (py < h)
        ok[ok] &= first[py[ok]] >= 0
        if ok.sum() < 20:
            return 1e9, 0.0
        tx = np.median(first[py[ok]] - s * mesh_x[ok])
        err = first[py[ok]] - (s * mesh_x[ok] + tx)
        return float(np.mean(np.minimum(np.abs(err), 40.0))), float(tx)

    s0, ty0 = view.scale, view.translation[1]
    best = None
    for ds in np.linspace(0.9, 1.1, 21):
        for dy in np.linspace(-40, 40, 33):
            e, tx = residual((s0 * ds, ty0 + dy))
            if best is None or e < best[0]:
                best = (e, s0 * ds, ty0 + dy, tx)
    res = optimize.minimize(lambda q: residual(q)[0], np.array(best[1:3]), method="Nelder-Mead",
                            options={"xatol": 0.05, "fatol": 1e-4, "maxiter": 300})
    s, ty = res.x
    err, tx = residual((s, ty))
    return View(name=view.name, image=view.image, scale=float(s), rotation=np.eye(2),
                translation=np.array([tx, ty]), mask=view.mask, weight=view.weight,
                sharpness=view.sharpness), err


# ----------------------------------------------------------------------------- baking
def uv_rasterize(uv, tris_uv, size):
    """For each texel: the triangle covering it and its barycentric weights."""
    tri_id = -np.ones((size, size), np.int64)
    bary = np.zeros((size, size, 3))
    p = uv * [size, size]
    p[:, 1] = size - p[:, 1]
    for k, t in enumerate(tris_uv):
        a, b, c = p[t[0]], p[t[1]], p[t[2]]
        x0, y0 = np.floor(np.minimum(np.minimum(a, b), c)).astype(int)
        x1, y1 = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        v0, v1 = b - a, c - a
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12:
            continue
        dx, dy = gx - a[0], gy - a[1]
        w1 = (dx * v1[1] - v1[0] * dy) / den
        w2 = (v0[0] * dy - dx * v0[1]) / den
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not inside.any():
            continue
        yy, xx = np.nonzero(inside)
        yy, xx = yy + y0, xx + x0
        tri_id[yy, xx] = k
        bary[yy, xx] = np.stack([w0[inside], w1[inside], w2[inside]], 1)
    return tri_id, bary


def depth_buffer(view: View, verts, tris, shape):
    """Nearest depth per picture pixel (for hiding what a view cannot see)."""
    px = view.pixels(verts)
    dz = view.depth(verts)
    buf = np.full(shape, np.inf)
    for t in tris:
        a, b, c = px[t[0]], px[t[1]], px[t[2]]
        x0, y0 = np.floor(np.minimum(np.minimum(a, b), c)).astype(int)
        x1, y1 = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, shape[1] - 1), min(y1, shape[0] - 1)
        if x1 < x0 or y1 < y0:
            continue
        v0, v1 = b - a, c - a
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        dx, dy = gx - a[0], gy - a[1]
        w1 = (dx * v1[1] - v1[0] * dy) / den
        w2 = (v0[0] * dy - dx * v0[1]) / den
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-3) & (w1 >= -1e-3) & (w2 >= -1e-3)
        if not inside.any():
            continue
        z = w0 * dz[t[0]] + w1 * dz[t[1]] + w2 * dz[t[2]]
        sub = buf[y0:y1 + 1, x0:x1 + 1]
        np.minimum(sub, np.where(inside, z, np.inf), out=sub)
    return buf


def sample(image, px):
    """Bilinear sample of an (H, W, 3) image at (N, 2) pixel positions."""
    h, w = image.shape[:2]
    x = np.clip(px[:, 0] - 0.5, 0, w - 1.001)
    y = np.clip(px[:, 1] - 0.5, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (image[y0, x0] * (1 - fx) * (1 - fy) + image[y0, x0 + 1] * fx * (1 - fy)
            + image[y0 + 1, x0] * (1 - fx) * fy + image[y0 + 1, x0 + 1] * fx * fy)


def bake(views, verts, normals, tris, uv, tris_uv, size, occluders,
         depth_tolerance=0.004, buffers=None, min_facing=0.25, view_weights=None):
    """Weighted multi-view paint per texel.

    Returns (texture, coverage, painted, positions): `positions` is each
    texel's surface point, for filling what no view painted. A view only
    paints surface that faces it at least `min_facing` (cosine): a glancing
    projection smears whatever lies next to the outline. `buffers` caches
    each view's depth buffer between meshes sharing occluders. Optional
    `view_weights` maps view names to functions of world-space surface points;
    these limit inferred views to regions that their pictures actually describe.
    """
    tri_id, bary = uv_rasterize(uv, tris_uv, size)
    texel = tri_id >= 0
    ids = tris[tri_id[texel]]
    w3 = bary[texel]
    pos = np.einsum("nk,nkj->nj", w3, verts[ids])
    nrm = np.einsum("nk,nkj->nj", w3, normals[ids])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    acc = np.zeros((len(pos), 3))
    wsum = np.zeros(len(pos))
    occ_v, occ_t = occluders
    for view in views:
        cos = nrm @ -VIEW_AXES[view.name][2]
        facing = np.where(cos >= min_facing, view.weight * np.clip(cos, 0, 1) ** view.sharpness, 0.0)
        px = view.pixels(pos)
        h, w = view.image.shape[:2]
        inb = (px[:, 0] >= 0) & (px[:, 0] < w) & (px[:, 1] >= 0) & (px[:, 1] < h)
        if buffers is not None and view.name in buffers:
            buf = buffers[view.name]
        else:
            buf = depth_buffer(view, occ_v, occ_t, (h, w))
            if buffers is not None:
                buffers[view.name] = buf
        xi = np.clip(px[:, 0].astype(int), 0, w - 1)
        yi = np.clip(px[:, 1].astype(int), 0, h - 1)
        seen = inb & (view.depth(pos) <= buf[yi, xi] + depth_tolerance)
        if view.mask is not None:
            seen &= view.mask[yi, xi]
        wt = facing * seen
        if view_weights is not None and view.name in view_weights:
            wt *= np.clip(view_weights[view.name](pos), 0.0, 1.0)
        acc += view.colour(px) * wt[:, None]
        wsum += wt
    tex = np.zeros((size, size, 3))
    cov = np.zeros((size, size))
    filled = wsum > 1e-6
    vals = np.zeros((len(pos), 3))
    vals[filled] = acc[filled] / wsum[filled, None]
    tex[texel] = vals
    cov[texel] = wsum
    positions = np.zeros((size, size, 3))
    positions[texel] = pos
    return tex, cov, texel & (cov > 1e-6), positions


def match_colour(reference: View, other: View, verts, normals, occluders, min_both=0.35):
    """Per-channel gain bringing `other` to `reference` where both see the surface.

    Generated views of one character differ in exposure and warmth; without a
    match, the seam between their paints shows as a band of colour.
    """
    occ_v, occ_t = occluders
    keep = np.ones(len(verts), bool)
    cols = []
    for view in (reference, other):
        cos = normals @ -VIEW_AXES[view.name][2]
        px = view.pixels(verts)
        h, w = view.image.shape[:2]
        inb = (px[:, 0] >= 0) & (px[:, 0] < w) & (px[:, 1] >= 0) & (px[:, 1] < h)
        buf = depth_buffer(view, occ_v, occ_t, (h, w))
        xi = np.clip(px[:, 0].astype(int), 0, w - 1)
        yi = np.clip(px[:, 1].astype(int), 0, h - 1)
        ok = inb & (cos >= min_both) & (view.depth(verts) <= buf[yi, xi] + 0.004)
        if view.mask is not None:
            ok &= view.mask[yi, xi]
        keep &= ok
        cols.append(sample(view.image, px))
    if keep.sum() < 50:
        return np.ones(3), int(keep.sum())
    gain = cols[0][keep].mean(0) / np.maximum(cols[1][keep].mean(0), 1e-4)
    return np.clip(gain, 0.7, 1.4), int(keep.sum())


def fill_unseen_3d(tex, painted, texel, positions, k=6):
    """Paint texels no view saw from the nearest painted surface points in 3D.

    Nearest in the UV layout can be another island entirely (skin beside
    hair); nearest on the surface is the colour that belongs there.
    """
    from scipy.spatial import cKDTree
    todo = texel & ~painted
    if not todo.any() or not painted.any():
        return tex.copy()
    src = np.argwhere(painted)
    tree = cKDTree(positions[painted])
    d, j = tree.query(positions[todo], k=k, workers=-1)
    w = 1.0 / np.maximum(d, 1e-5)
    w /= w.sum(1, keepdims=True)
    out = tex.copy()
    cols = tex[src[:, 0], src[:, 1]]
    out[todo] = np.einsum("nk,nkc->nc", w, cols[j])
    return out


def mesh_edges(tris):
    """Each undirected edge of a triangle mesh once, as (a, b) with a < b."""
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    return np.unique(np.sort(e, axis=1), axis=0)


def smooth_normals(verts, tris, normals, radius):
    """Vertex normals averaged over the mesh's own edges out to about `radius` metres.

    A scanned sleeve's wrinkles have facets that tilt toward the front or the
    back picture; judged by those facets, the top of the sleeve faces a picture
    and takes the paint at its outline. Averaged over a few centimetres, the
    top faces up and is filled instead. Repeated one-ring means (a diffusion):
    (radius / median edge)^2 of them reach about `radius`.
    """
    from scipy import sparse
    if radius <= 0:
        return normals.copy()
    e = mesh_edges(tris)
    n = len(verts)
    adj = sparse.coo_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])),
                            shape=(n, n)).tocsr() + sparse.identity(n, format="csr")
    adj = sparse.diags(1.0 / np.asarray(adj.sum(1)).ravel()) @ adj
    steps = max(1, int(round((radius / np.median(np.linalg.norm(verts[e[:, 0]] - verts[e[:, 1]], axis=1))) ** 2)))
    out = normals.astype(float).copy()
    for _ in range(steps):
        out = adj @ out
        out /= np.linalg.norm(out, axis=1, keepdims=True) + 1e-12
    return out


def fill_unseen_surface(tex, keep, tri_id, bary, verts, tris):
    """Paint what no picture saw squarely as a smooth membrane over the mesh, from the paint that one did.

    `keep` (texels, 0..1) is how much of the bake to keep: 1 where a picture
    faced the surface squarely (those texels are the sources), 0 where nothing
    painted, between at the edge of a picture's view. The sources' colours go to
    their triangles' vertices; every other vertex gets the harmonic (Laplace)
    interpolation of them over the mesh's own edges, weighted by inverse edge
    length; texels take their triangle's vertex colours, blended with the bake
    by `keep`. Nearest painted points in 3D (fill_unseen_3d) copy a picture's
    outline across a coat's side as streaks and can reach across a gap (the arm
    to the coat); over the surface the fill is a smooth blend between the paint
    on either side, and only what the surface connects. A part with no source at
    all takes the sources' median colour. Returns (texture, record).
    """
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    valid = tri_id >= 0
    ids = tris[tri_id[valid]]
    w3 = bary[valid]
    cols = tex[valid].astype(float)
    k = np.clip(keep[valid], 0.0, 1.0)
    src = k >= 0.999
    n = len(verts)
    acc, wsum = np.zeros((n, 3)), np.zeros(n)
    for c in range(3):
        np.add.at(acc, ids[src, c], cols[src] * w3[src, c:c + 1])
        np.add.at(wsum, ids[src, c], w3[src, c])
    known = wsum > 1e-3
    out = tex.copy()
    if not known.any():
        return out, {"source_vertices": 0, "filled_vertices": 0}
    vc = np.zeros((n, 3))
    vc[known] = acc[known] / wsum[known, None]
    e = mesh_edges(tris)
    w = 1.0 / np.maximum(np.linalg.norm(verts[e[:, 0]] - verts[e[:, 1]], axis=1), 1e-5)
    W = sparse.coo_matrix((np.r_[w, w], (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    L = (sparse.diags(np.asarray(W.sum(1)).ravel()) - W).tocsr()
    u, kn = np.nonzero(~known)[0], np.nonzero(known)[0]
    if len(u):
        # A tiny pull toward the sources' median keeps parts with no source (and loose vertices) solvable.
        eps = 1e-6 * float(np.median(w))
        luu = (L[u][:, u] + sparse.identity(len(u)) * eps).tocsc()
        rhs = -(L[u][:, kn] @ vc[kn]) + eps * np.median(vc[kn], axis=0)[None]
        vc[u] = np.stack([spsolve(luu, rhs[:, c]) for c in range(3)], axis=1)
    fill = np.einsum("nk,nkc->nc", w3, vc[ids])
    out[valid] = cols * k[:, None] + fill * (1.0 - k[:, None])
    return out, {"source_vertices": int(known.sum()), "filled_vertices": int(len(u)),
                 "kept_texels": int(src.sum()), "feathered_texels": int(((k > 0) & ~src).sum()),
                 "filled_texels": int((k <= 0).sum())}


def fill_unpainted(tex, painted, blur=2.0):
    """Give every unpainted texel (seams, unseen undersides) its nearest paint.

    One Euclidean distance transform finds the nearest painted texel for the
    whole map; a light blur of only the filled texels hides the stepped edges.
    """
    if painted.all() or not painted.any():
        return tex.copy()
    _, (iy, ix) = ndimage.distance_transform_edt(~painted, return_indices=True)
    out = tex[iy, ix]
    if blur:
        soft = np.stack([ndimage.gaussian_filter(out[..., c], blur) for c in range(3)], -1)
        out[~painted] = soft[~painted]
    return out
