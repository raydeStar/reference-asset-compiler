"""Give a conformed head one continuous neck that ends at a clean collar.

The conform stage fits the template's head and neck onto the acquisition. An
image-to-3D acquisition rarely has a usable neck (it is cut, torn or merged
into a collar), and fitting the template onto it leaves shards and a jagged
edge. This stage keeps what the fit got right and replaces what it could not:

* The skull and face (head-bone weight >= TRUST) keep their fitted shape.
* Everything below - jaw underside, neck, top of the chest - takes the
  template's own neck, carried along by a smooth (harmonic) continuation of the
  face's fitted displacement. One mesh, the template's topology: no seam
  between face and neck, and every expression unit moves both together.
* The neck ends on a smooth collar curve (low at the throat, rising to the
  sides and the nape, like a bust): polygons that straddle it are kept and
  their lower vertices are laid onto the curve, so the edge is clean.

Deterministic, CPU only, NumPy/SciPy. Writes a new conform NPZ (same arrays as
conform_head_template.py, so the paint and render stages take it unchanged)
and a receipt.

Usage:
  python scripts/close_head_neck.py <template.npz> <conform.npz> <conform.json> \
      <out.npz> <out.json> [--trust 0.6] [--collar 1.515 0.32 0.30]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix, diags, identity
from scipy.sparse.linalg import spsolve

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler import template_conform as tc  # noqa: E402

HELPERS = ("helper-l-eye", "helper-r-eye", "helper-upper-teeth", "helper-lower-teeth",
           "helper-tongue")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collar_height(rest, z0, side, back, front_y):
    """The collar curve's height under each point: lowest at the throat, rising in
    a U to the sides (side = rise in metres at 6 cm out) and linearly towards the
    nape (+y)."""
    return z0 + side * (rest[:, 0] / 0.06) ** 2 + back * np.maximum(rest[:, 1] - front_y, 0.0)


def harmonic_fill(values, known, region, edges):
    """Values on `region & ~known` that minimise the summed squared difference
    across every edge inside `region`, with `known` held fixed: a smooth,
    seam-free continuation. Unknowns not connected to any known vertex take the
    known mean (a weak pull keeps the system well-posed)."""
    n = len(values)
    e = edges[region[edges[:, 0]] & region[edges[:, 1]]]
    i, j = e[:, 0], e[:, 1]
    w = np.ones(len(e))
    adj = coo_matrix((np.r_[w, w], (np.r_[i, j], np.r_[j, i])), shape=(n, n)).tocsr()
    lap = (diags(np.asarray(adj.sum(1)).ravel()) - adj).tocsr()
    unk = np.flatnonzero(region & ~known)
    kn = np.flatnonzero(region & known)
    if len(unk) == 0:
        return values.copy()
    a = lap[unk][:, unk] + 1e-6 * identity(len(unk), format="csr")
    rhs = -(lap[unk][:, kn] @ values[kn]) + 1e-6 * values[kn].mean(0)
    out = values.copy()
    out[unk] = np.column_stack([spsolve(a.tocsc(), rhs[:, c]) for c in range(values.shape[1])])
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ("template", "conform", "receipt", "out", "out_receipt"):
        p.add_argument(name)
    p.add_argument("--trust", type=float, default=0.6,
                   help="head-bone weight from which the fitted shape is kept")
    p.add_argument("--collar", type=float, nargs=3, default=(1.475, 0.03, 0.40),
                   metavar=("THROAT_Z", "SIDE_RISE", "BACK_RISE"),
                   help="collar curve in template metres: throat height, rise 6 cm to the "
                        "side, rise per metre towards the nape")
    a = p.parse_args(argv)

    t = tc.load_template(a.template)
    z = np.load(a.conform)
    receipt = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    rest = t.verts.astype(np.float64)
    fitted = z["verts"].astype(np.float64)
    n = len(rest)

    body = np.zeros(n, bool)
    body[t.groups["body"]] = True
    head_w = t.bone_weight("head")
    trusted = body & (head_w >= a.trust)

    # The collar: everything of the body above the curve, plus the polygons
    # that cross it (their lower corners are laid onto it below).
    throat_y = float(rest[trusted, 1].min()) + 0.06   # behind the chin: the throat's depth
    cut = collar_height(rest, a.collar[0], a.collar[1], a.collar[2], throat_y)
    above = body & (rest[:, 2] >= cut)
    helper = np.zeros(n, bool)
    for g in HELPERS:
        if g in t.groups:
            helper[t.groups[g]] = True
    keep_polys, kept = [], np.zeros(n, bool)
    for i, (st, tot) in enumerate(zip(t.starts, t.totals)):
        lv = t.loops[st:st + tot]
        if helper[lv].all() or (body[lv].all() and above[lv].any()):
            keep_polys.append(i)
            kept[lv] = True
    keep_polys = np.array(keep_polys)
    skin = kept & body

    # Rest shape of the kept skin, with the collar row laid onto the curve.
    shaped = rest.copy()
    below = skin & ~above
    shaped[below, 2] = cut[below]

    # Displacement: fitted on the skull and face, harmonic below.
    disp = fitted - rest
    disp = harmonic_fill(disp, trusted, skin, t.edges)
    out_v = fitted.copy()
    out_v[skin] = shaped[skin] + disp[skin]

    arrays = {k: z[k] for k in z.files}
    arrays["verts"] = out_v
    arrays["keep_polys"] = keep_polys
    np.savez_compressed(a.out, **arrays)

    replaced = skin & ~trusted
    change = np.linalg.norm(out_v - fitted, axis=1)
    receipt = dict(receipt)
    receipt["neck"] = {
        "stage": "close_head_neck",
        "input": {"path": str(a.conform), "sha256": _sha(a.conform)},
        "output": {"path": str(a.out), "sha256": _sha(a.out)},
        "trust_head_weight": a.trust,
        "collar": {"throat_z": a.collar[0], "side_rise": a.collar[1], "back_rise": a.collar[2],
                   "throat_y": throat_y},
        "trusted_vertices": int(trusted.sum()),
        "replaced_vertices": int(replaced.sum()),
        "collar_vertices": int(below.sum()),
        "kept_polygons": int(len(keep_polys)),
        "change_from_fit_mm": {"median": float(np.median(change[replaced]) * 1000),
                               "max": float(change[replaced].max() * 1000)},
    }
    Path(a.out_receipt).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt["neck"], indent=1))


if __name__ == "__main__":
    main()
