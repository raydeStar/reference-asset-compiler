"""Conform a rigged human template onto an acquired character shape.

An image-to-3D acquisition gets a character's silhouette, proportions and
facial form right and its anatomy wrong for animation: the eyes are a groove,
the mouth has no inside, the fingers are slabs, and the surface is a dense
triangle soup with no edge loops. A template (the MakeHuman hm08 base mesh,
CC0) has exactly what the acquisition lacks: quads with joint loops,
eyeballs, lids that close, teeth and tongue, expression shapes and a skeleton
placed from its own vertices. Conforming moves the template onto the acquired
shape -- this is retopology onto a known, rigged topology, the same idea as
Wrap or MetaHuman's Mesh to MetaHuman -- so the identity stays the
acquisition's and the anatomy is the template's.

The fit is optimal-step non-rigid ICP (Amberg, Romdhani and Vetter, CVPR 2007):
each template vertex carries an affine transform, a stiffness term keeps
neighbouring transforms alike, and the stiffness is relaxed in steps so the
template first follows the gross shape and only then the detail. Template
regions the acquisition cannot vouch for -- scalp under hair, eyelids over a
fused groove, the inside of the mouth -- carry no data term and simply ride
along with their neighbours.

Pure NumPy/SciPy; Blender only reads and writes the meshes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree


# ----------------------------------------------------------------------------- template
@dataclass
class Template:
    verts: np.ndarray                     # (n, 3) metres, Z up, facing -Y
    loops: np.ndarray                     # flat polygon vertex indices
    starts: np.ndarray                    # polygon loop starts
    totals: np.ndarray                    # polygon sizes
    groups: dict = field(default_factory=dict)       # name -> vertex indices
    expressions: dict = field(default_factory=dict)  # name -> (n, 3) deltas
    weights: np.ndarray | None = None     # (n, bones) skin weights
    bone_names: list = field(default_factory=list)
    exposure: np.ndarray | None = None    # (n,) open-sky fraction; 0 = cavity

    @property
    def tris(self) -> np.ndarray:
        return fan_triangles(self.loops, self.starts, self.totals)

    @property
    def edges(self) -> np.ndarray:
        return unique_edges(self.loops, self.starts, self.totals)

    def polygon_vertices(self, polygons) -> np.ndarray:
        polygons = np.asarray(sorted(polygons), dtype=np.int64)
        polygons = polygons[polygons < len(self.starts)]
        out = [self.loops[s:s + t] for s, t in zip(self.starts[polygons], self.totals[polygons])]
        return np.unique(np.concatenate(out)) if out else np.zeros(0, np.int64)

    def bone_weight(self, name: str) -> np.ndarray:
        return self.weights[:, self.bone_names.index(name)]


def load_template(path) -> Template:
    z = np.load(path)
    groups = {k[4:]: z[k] for k in z.files if k.startswith("vg__")}
    expr = {k[4:]: z[k].astype(np.float64) for k in z.files if k.startswith("ex__")}
    return Template(verts=z["verts"].astype(np.float64), loops=z["loops"],
                    starts=z["loop_starts"], totals=z["loop_totals"], groups=groups,
                    expressions=expr, weights=z["weights"] if "weights" in z.files else None,
                    bone_names=[str(b) for b in z["bone_names"]] if "bone_names" in z.files else [],
                    exposure=z["exposure"] if "exposure" in z.files else None)


def fan_triangles(loops, starts, totals) -> np.ndarray:
    tris = []
    for k in range(1, int(totals.max()) - 1):
        sel = totals > k + 1
        s = starts[sel]
        tris.append(np.stack([loops[s], loops[s + k], loops[s + k + 1]], axis=1))
    return np.concatenate(tris)


def unique_edges(loops, starts, totals) -> np.ndarray:
    nxt = np.arange(len(loops)) + 1
    ends = starts + totals
    poly_of = np.repeat(np.arange(len(starts)), totals)
    wrap = nxt == ends[poly_of]
    nxt[wrap] = starts[poly_of[wrap]]
    e = np.sort(np.stack([loops, loops[nxt]], axis=1), axis=1)
    return np.unique(e, axis=0)


def vertex_normals(verts, tris) -> np.ndarray:
    fn = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]])
    n = np.zeros_like(verts)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def boundary_vertices(tris, n) -> np.ndarray:
    """Vertices on an open edge: a correspondence there is the acquisition's cut, not its surface."""
    e = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    key = e[:, 0] * n + e[:, 1]
    uniq, count = np.unique(key, return_counts=True)
    open_edges = uniq[count == 1]
    mask = np.zeros(n, bool)
    mask[open_edges // n] = True
    mask[open_edges % n] = True
    return mask


# ----------------------------------------------------------------------------- target
@dataclass
class Target:
    points: np.ndarray
    normals: np.ndarray
    tree: cKDTree
    on_boundary: np.ndarray

    @classmethod
    def from_mesh(cls, verts, tris) -> "Target":
        return cls(points=verts, normals=vertex_normals(verts, tris), tree=cKDTree(verts),
                   on_boundary=boundary_vertices(tris, len(verts)))

    def correspond(self, pts, normals, max_dist, min_cos):
        """Closest target point per source point, with the validity of each match."""
        d, j = self.tree.query(pts, k=1, workers=-1)
        ok = (d <= max_dist) & ~self.on_boundary[j]
        if normals is not None:
            ok &= np.einsum("ij,ij->i", normals, self.normals[j]) >= min_cos
        return self.points[j], ok, d


# ----------------------------------------------------------------------------- rigid
def umeyama(src, dst, weights=None, scale=True):
    """Least-squares similarity (s, R, t) with dst ~= s * src @ R.T + t."""
    w = np.ones(len(src)) if weights is None else np.asarray(weights, float)
    w = w / w.sum()
    ms, md = w @ src, w @ dst
    a, b = src - ms, dst - md
    cov = (b * w[:, None]).T @ a
    u, sig, vt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(u @ vt))
    corr = np.diag([1.0, 1.0, d])
    r = u @ corr @ vt
    var = (w * (a * a).sum(1)).sum()
    s = (sig * np.diag(corr)).sum() / var if scale else 1.0
    t = md - s * ms @ r.T
    return s, r, t


def apply_similarity(pts, s, r, t):
    return s * pts @ r.T + t


def similarity_icp(src, normals, target: Target, s=1.0, r=None, t=None, iterations=60,
                   trim=0.7, min_cos=0.3, scale=True):
    """Trimmed ICP: the closest `trim` fraction of valid matches drives each step."""
    r = np.eye(3) if r is None else r
    t = np.zeros(3) if t is None else t
    err = np.inf
    for _ in range(iterations):
        p = apply_similarity(src, s, r, t)
        n = normals @ r.T if normals is not None else None
        q, ok, d = target.correspond(p, n, np.inf, min_cos)
        idx = np.flatnonzero(ok)
        if len(idx) < 10:
            break
        keep = idx[np.argsort(d[idx])[: max(10, int(trim * len(idx)))]]
        ds, dr, dt = umeyama(p[keep], q[keep], scale=scale)
        s, r, t = ds * s, dr @ r, ds * t @ dr.T + dt
        new_err = float(np.sqrt(np.mean(d[keep] ** 2)))
        if abs(err - new_err) < 1e-7:
            err = new_err
            break
        err = new_err
    return s, r, t, err


# ----------------------------------------------------------------------------- non-rigid
@dataclass
class NricpResult:
    verts: np.ndarray                 # deformed positions of every template vertex
    affine: np.ndarray                # (n, 4, 3) per-vertex transform, row-vector convention
    log: list


@dataclass
class SurfaceLandmarks:
    """Points on the template surface (three vertices and barycentric weights)
    with the positions they must reach. `free_axis` names a coordinate the
    target does not constrain -- depth, for landmarks read from a single
    orthographic picture -- which then follows the fit instead."""
    ids: np.ndarray          # (L, 3) vertex indices
    bary: np.ndarray         # (L, 3) weights
    points: np.ndarray       # (L, 3) targets
    weight: np.ndarray       # (L,) per-landmark weight
    free_axis: int | None = None

    def evaluate(self, verts):
        return np.einsum("lk,lkj->lj", self.bary, verts[self.ids])


def nricp(verts, edges, active, data_weight, target: Target, tris, stiffness,
          landmarks: SurfaceLandmarks | None = None, gamma=1.0, inner=4,
          max_dist=(0.03, 0.006), min_cos=0.5, tol=1e-5,
          inward_only=None, outward_tolerance=0.002):
    """Optimal-step non-rigid ICP over the `active` vertices; the rest stay put.

    data_weight -- per-vertex weight of the closest-point term (0 = rides along)
    stiffness   -- decreasing sequence of stiffness weights (alpha)
    landmarks   -- surface points held to their targets at every step
    max_dist    -- correspondence radius at the first and last stiffness step
    inward_only -- vertices that may be pulled in onto the acquisition but not
                   out onto something standing off it (skin under hair: the
                   forehead fits, the strands above it do not)
    """
    n = len(verts)
    act = np.flatnonzero(active)
    k = len(act)
    pos = -np.ones(n, np.int64)
    pos[act] = np.arange(k)
    e = edges[active[edges[:, 0]] & active[edges[:, 1]]]
    m = len(e)
    inc = sparse.coo_matrix((np.r_[np.ones(m), -np.ones(m)],
                             (np.r_[np.arange(m), np.arange(m)], np.r_[pos[e[:, 0]], pos[e[:, 1]]])),
                            shape=(m, k)).tocsr()
    g = sparse.diags([1.0, 1.0, 1.0, gamma])
    stiff = sparse.kron(inc, g).tocsr()
    vh = np.c_[verts[act], np.ones(k)]
    rows = np.repeat(np.arange(k), 4)
    cols = (4 * np.arange(k)[:, None] + np.arange(4)).ravel()
    dmat = sparse.csr_matrix((vh.ravel(), (rows, cols)), shape=(k, 4 * k))
    x = np.tile(np.r_[np.eye(3), np.zeros((1, 3))], (k, 1))
    dl = lm_pts = lm_w = None
    if landmarks is not None:
        ok_lm = active[landmarks.ids].all(1)
        ids, bary = landmarks.ids[ok_lm], landmarks.bary[ok_lm]
        lm_pts = landmarks.points[ok_lm].astype(float).copy()
        lm_w = landmarks.weight[ok_lm].astype(float)
        nl = len(ids)
        lrows = np.repeat(np.arange(nl), 12)
        lcols = (4 * pos[ids][:, :, None] + np.arange(4)).reshape(nl, 12).ravel()
        lvals = (bary[:, :, None] * vh[pos[ids]]).reshape(nl, 12).ravel()
        dl = sparse.csr_matrix((lvals, (lrows, lcols)), shape=(nl, 4 * k))
        dl = sparse.diags(lm_w) @ dl
    dw = np.asarray(data_weight, float)[act]
    tri_act = tris[active[tris].all(1)]
    log = []
    radii = np.geomspace(max_dist[0], max_dist[1], len(stiffness))
    out = verts.copy()
    for alpha, radius in zip(stiffness, radii):
        for it in range(inner):
            cur = (dmat @ x)
            out[act] = cur
            nrm = vertex_normals(out, tri_act)[act]
            q, ok, d = target.correspond(cur, nrm, radius, min_cos)
            if inward_only is not None:
                outward = np.einsum("ij,ij->i", q - cur, nrm)
                ok &= ~(inward_only[act] & (outward > outward_tolerance))
            w = dw * ok
            wd = sparse.diags(w) @ dmat
            blocks = [alpha * stiff, wd]
            rhs = [np.zeros((4 * m, 3)), w[:, None] * q]
            if dl is not None and dl.shape[0]:
                if landmarks.free_axis is not None:
                    current = (dl @ x) / lm_w[:, None]
                    lm_pts[:, landmarks.free_axis] = current[:, landmarks.free_axis]
                blocks.append(dl)
                rhs.append(lm_w[:, None] * lm_pts)
            a = sparse.vstack(blocks).tocsc()
            b = np.vstack(rhs)
            ata = (a.T @ a).tocsc()
            atb = a.T @ b
            x_new = splu(ata).solve(atb)
            change = float(np.abs(x_new - x).max())
            x = x_new
            res = float(np.sqrt(np.mean(d[ok] ** 2))) if ok.any() else float("nan")
            log.append({"alpha": float(alpha), "iteration": it, "radius": float(radius),
                        "matched": int(ok.sum()), "weighted": int((w > 0).sum()),
                        "rms_m": res, "change": change})
            if change < tol:
                break
    out[act] = dmat @ x
    affine = np.tile(np.r_[np.eye(3), np.zeros((1, 3))], (n, 1, 1))
    affine[act] = x.reshape(k, 4, 3)
    return NricpResult(verts=out, affine=affine, log=log)


# ----------------------------------------------------------------------------- pictures
def camera_project(verts, cam):
    """Pixels and depth of world points in an orthographic camera record
    (render_mesh_view.py writes one beside each render)."""
    c = np.asarray(cam["centre"], float)
    d = verts - c
    scale = cam["resolution"] / cam["ortho_scale"]
    px = cam["resolution"] / 2 + (d @ np.asarray(cam["right"], float)) * scale
    py = cam["resolution"] / 2 - (d @ np.asarray(cam["up"], float)) * scale
    return np.stack([px, py], axis=1), d @ np.asarray(cam["forward"], float)


def bind_pixels(verts, tris, cam, pixels):
    """The front-most surface point under each pixel: (ids, barycentric, found)."""
    p2, depth = camera_project(verts, cam)
    a, b, c = p2[tris[:, 0]], p2[tris[:, 1]], p2[tris[:, 2]]
    v0, v1 = b - a, c - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    good = np.abs(den) > 1e-12
    ids = np.zeros((len(pixels), 3), np.int64)
    bary = np.zeros((len(pixels), 3))
    found = np.zeros(len(pixels), bool)
    for i, q in enumerate(np.asarray(pixels, float)):
        v2 = q - a
        d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            v = (d11 * d20 - d01 * d21) / den
            w = (d00 * d21 - d01 * d20) / den
        u = 1 - v - w
        inside = good & (u >= -1e-6) & (v >= -1e-6) & (w >= -1e-6)
        if not inside.any():
            continue
        cand = np.flatnonzero(inside)
        bw = np.stack([u[cand], v[cand], w[cand]], 1)
        z = (bw * depth[tris[cand]]).sum(1)
        k = int(np.argmin(z))
        ids[i], bary[i], found[i] = tris[cand[k]], bw[k], True
    return ids, bary, found


def similarity_2d(src, dst, weights=None):
    """Least-squares 2D similarity: dst ~= s * src @ R.T + t."""
    w = np.ones(len(src)) if weights is None else np.asarray(weights, float)
    w = w / w.sum()
    ms, md = w @ src, w @ dst
    a, b = src - ms, dst - md
    u, sig, vt = np.linalg.svd((b * w[:, None]).T @ a)
    corr = np.diag([1.0, np.sign(np.linalg.det(u @ vt))])
    r = u @ corr @ vt
    s = (sig * np.diag(corr)).sum() / (w * (a * a).sum(1)).sum()
    return s, r, md - s * ms @ r.T


# ----------------------------------------------------------------------------- carry-along parts
def rigid_follow(part_verts, rest_skin, fitted_skin):
    """Move a rigid part (an eyeball, a row of teeth) with the skin around it.

    A similarity transform keeps an eyeball round where a per-vertex affine
    would shear it into an egg.
    """
    s, r, t = umeyama(rest_skin, fitted_skin, scale=True)
    return apply_similarity(part_verts, s, r, t)


def carry_interior(rest, fitted, interior, source, k=12):
    """Move hidden surfaces with the fitted surface around them, through the volume.

    The mouth's inside is joined to the face only at the lips, so stiffness
    alone moves it with the lips; when the fit pulls a cheek in, the inside of
    the mouth stays put and pokes through the cheek as soon as an expression
    moves it. Interpolating displacement from the nearest exposed vertices in
    space keeps each hidden wall the same distance behind the skin it was
    behind in the template.
    """
    out = fitted.copy()
    src = np.flatnonzero(source & ~interior)
    dst = np.flatnonzero(interior)
    if not len(dst):
        return out
    tree = cKDTree(rest[src])
    d, j = tree.query(rest[dst], k=k, workers=-1)
    w = 1.0 / np.maximum(d, 1e-5) ** 2
    w /= w.sum(1, keepdims=True)
    disp = fitted[src] - rest[src]
    out[dst] = rest[dst] + np.einsum("nk,nkj->nj", w, disp[j])
    return out


def unfold(rest, fitted, tris, movable, edges, rounds=40):
    """Relax the displacement of folded triangles until none are turned over.

    A closest-point fit can drag a sharp template corner (an eye or mouth
    commissure) across its neighbours. Each round replaces the displacement of
    every vertex on a turned-over triangle with its neighbours' average.
    """
    out = fitted.copy()
    n = len(rest)

    def turned(v):
        a = np.cross(rest[tris[:, 1]] - rest[tris[:, 0]], rest[tris[:, 2]] - rest[tris[:, 0]])
        b = np.cross(v[tris[:, 1]] - v[tris[:, 0]], v[tris[:, 2]] - v[tris[:, 0]])
        return np.einsum("ij,ij->i", a, b) <= 0

    count = 0
    for count in range(rounds):
        bad = turned(out)
        if not bad.any():
            break
        verts = np.zeros(n, bool)
        verts[tris[bad].ravel()] = True
        verts = ring_neighbours(np.flatnonzero(verts), edges, n, rings=1) & movable
        disp = out - rest
        acc = np.zeros_like(disp)
        cnt = np.zeros(n)
        np.add.at(acc, edges[:, 0], disp[edges[:, 1]])
        np.add.at(acc, edges[:, 1], disp[edges[:, 0]])
        np.add.at(cnt, edges[:, 0], 1)
        np.add.at(cnt, edges[:, 1], 1)
        avg = acc / np.maximum(cnt, 1)[:, None]
        out[verts] = rest[verts] + avg[verts]
    return out, int(turned(out).sum()), count


def rotation_scale(affine):
    """Each vertex's fitted linear map reduced to rotation times uniform scale.

    The full affine carries the local stretch the fit needed to reach the
    acquisition; pushing an expression through that stretch shears it (a
    pursed mouth tears at its corners). Rotation and size are what an
    expression should inherit.
    """
    lin = affine[:, :3, :]
    u, sig, vt = np.linalg.svd(lin)
    d = np.sign(np.linalg.det(u @ vt))
    u[:, :, 2] *= d[:, None]
    rot = u @ vt
    scale = np.cbrt(np.abs(np.prod(sig, axis=1)))
    return rot * scale[:, None, None]


def smooth_per_vertex(values, edges, n, rounds=3):
    """Average a per-vertex quantity with its neighbours a few times."""
    out = values.copy()
    flat = out.reshape(n, -1)
    for _ in range(rounds):
        acc = flat.copy()
        cnt = np.ones(n)
        np.add.at(acc, edges[:, 0], flat[edges[:, 1]])
        np.add.at(acc, edges[:, 1], flat[edges[:, 0]])
        np.add.at(cnt, edges[:, 0], 1)
        np.add.at(cnt, edges[:, 1], 1)
        flat = acc / cnt[:, None]
    return flat.reshape(values.shape)


def transfer_deltas(deltas, linear):
    """Carry template shape deltas through each vertex's (n, 3, 3) linear map."""
    return np.einsum("ni,nij->nj", deltas, linear)


def ring_neighbours(seed, edges, n, rings=1):
    """`seed` grown by `rings` edge steps."""
    mask = np.zeros(n, bool)
    mask[seed] = True
    for _ in range(rings):
        hit = mask[edges[:, 0]] | mask[edges[:, 1]]
        mask[edges[hit].ravel()] = True
    return mask
