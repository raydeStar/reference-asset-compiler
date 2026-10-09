"""mesh_hair_scalp_cap.py: a dark cap on the scalp under mesh hair, with its edge inside the hair.

A toy head (a sphere facing -y) carries locks over its crown and back, with
gaps between them wider than a lock; the template's scalp group is its upper
half. The cap must lie under the locks and their gaps, nowhere without hair,
behind the face, lifted off the skin, compact, and coloured from the hair's own
paint (its median, black bake misses skipped).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mesh_hair_scalp_cap as cap  # noqa: E402

CENTRE = np.array([0.0, 0.0, 1.7])
RADIUS = 0.1
DARK, CARAMEL = (40, 25, 15), (230, 156, 93)


def sphere(lat_step=4, lon_step=6):
    """Quads on a sphere: verts, loops, starts, totals (latitude -84..84 degrees, longitude all round)."""
    lats = np.radians(np.arange(-84, 85, lat_step))
    lons = np.radians(np.arange(0, 360, lon_step))
    verts = np.array([CENTRE + RADIUS * np.array([np.cos(t) * np.cos(p), np.cos(t) * np.sin(p), np.sin(t)])
                      for t in lats for p in lons])
    n = len(lons)
    quads = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
             for i in range(len(lats) - 1) for j in range(n)]
    loops = np.array(quads).ravel()
    return verts, loops, np.arange(0, len(loops), 4), np.full(len(quads), 4)


def locks(width_deg=18, every_deg=30, lift=0.012):
    """Strips of hair over the crown and back (y > -0.03): one per `every_deg` of longitude, `width_deg` wide."""
    verts, tris, uv = [], [], []
    for start in range(0, 360, every_deg):
        ring = []
        for t in np.radians(np.arange(10, 89, 3)):
            row = []
            for p in np.radians(np.linspace(start, start + width_deg, 4)):
                point = CENTRE + (RADIUS + lift) * np.array([np.cos(t) * np.cos(p), np.cos(t) * np.sin(p), np.sin(t)])
                row.append(len(verts))
                verts.append(point)
            ring.append(row)
        for a, b in zip(ring, ring[1:]):
            for k in range(3):
                tris += [(a[k], a[k + 1], b[k + 1]), (a[k], b[k + 1], b[k])]
    verts = np.array(verts)
    tris = np.array(tris)
    tris = tris[verts[tris].mean(1)[:, 1] > -0.03]      # no hair over the forehead
    used = np.unique(tris)
    remap = np.zeros(len(verts), int)
    remap[used] = np.arange(len(used))
    verts, tris = verts[used], remap[tris]
    # Per triangle: 55% in black texels (bake misses), 25% in the dark paint, 20% in the caramel tips.
    u = np.where(np.arange(len(tris)) % 20 < 11, 0.45, np.where(np.arange(len(tris)) % 20 < 16, 0.15, 0.85))
    uv = np.repeat(np.stack([u, np.full(len(tris), 0.5)], 1), 3, axis=0)
    return verts, tris, uv


def write_inputs(tmp_path, scalp=True):
    verts, loops, starts, totals = sphere()
    eye = np.array([len(verts) + k for k in range(4)])      # a helper quad (an eye) that must not be capped
    verts = np.vstack([verts, CENTRE + [[0.03, -0.11, 0.0], [0.04, -0.11, 0.0], [0.04, -0.11, 0.01],
                                         [0.03, -0.11, 0.01]]])
    loops = np.r_[loops, eye]
    starts, totals = np.r_[starts, len(loops) - 4], np.r_[totals, 4]
    head = tmp_path / "head.npz"
    np.savez(head, verts=verts, loops=loops, loop_starts=starts, loop_totals=totals,
             keep_polys=np.arange(len(starts)), **{"vg__helper-l-eye": eye})
    template = tmp_path / "template.npz"
    upper = np.flatnonzero(verts[:, 2] > CENTRE[2] + 0.02)
    np.savez(template, verts=verts, **({"vg__scalp": upper} if scalp else {}))
    hv, ht, uv = locks()
    hair = tmp_path / "hair-mesh.npz"
    np.savez(hair, verts=hv, tris=ht, loop_uv=uv)
    paint = np.zeros((16, 16, 3), np.uint8)              # columns 5-10 stay black
    paint[:, :5], paint[:, 11:] = DARK, CARAMEL
    texture = tmp_path / "hair-basecolor.png"
    Image.fromarray(paint).save(texture)
    return template, head, hair, texture, verts


def build(tmp_path, **options):
    template, head, hair, texture, verts = write_inputs(tmp_path)
    result = cap.scalp_cap(np.load(template), np.load(head), np.load(hair), texture, **options)
    return (*result, verts)


def directions(points):
    d = points - CENTRE
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def test_the_cap_lies_on_the_scalp_under_the_hair_and_its_gaps(tmp_path):
    cap_verts, cap_tris, _, report, verts = build(tmp_path, front_inset=0.0)
    centres = directions(cap_verts[cap_tris].mean(1))
    assert len(cap_tris) > 50
    assert (centres[:, 2] > 0.2 - 0.05).all()                       # on the scalp (upper half)...
    assert (centres[:, 1] > -0.35).all()                            # ...and only where hair lies over it
    # Under the gaps too: the cap runs right round the back, not just under the locks.
    lon = np.degrees(np.arctan2(centres[:, 1], centres[:, 0])) % 360
    back = lon[(lon > 30) & (lon < 150)]
    assert np.histogram(back, bins=np.arange(30, 151, 10))[0].min() > 0
    assert report["covered_vertices"]["closed"] >= report["covered_vertices"]["probe"]


def gap_cap(tmp_path, close):
    """Cap triangles in the gap between the locks at 30 and 60 degrees, below 55 degrees of latitude (higher up the
    locks converge and the gap closes by itself)."""
    cap_verts, cap_tris, _, report, _ = build(tmp_path, front_inset=0.0, close=close)
    centres = directions(cap_verts[cap_tris].mean(1))
    lon = np.degrees(np.arctan2(centres[:, 1], centres[:, 0])) % 360
    lat = np.degrees(np.arcsin(centres[:, 2]))
    return int(((lon > 50) & (lon < 58) & (lat < 55)).sum()), report


def test_closing_puts_the_cap_under_the_gaps_between_locks(tmp_path):
    bare, report = gap_cap(tmp_path, 0)
    assert bare == 0 and report["covered_vertices"]["closed"] == report["covered_vertices"]["probe"]
    capped, report = gap_cap(tmp_path, 2)
    assert capped > 10 and report["covered_vertices"]["closed"] > report["covered_vertices"]["probe"]


def test_the_cap_is_lifted_off_the_skin_and_compact(tmp_path):
    cap_verts, cap_tris, _, _, _ = build(tmp_path, lift=0.004)
    radius = np.linalg.norm(cap_verts - CENTRE, axis=1)
    assert np.allclose(radius, RADIUS + 0.004, atol=0.0006)        # a sphere's normals are radial
    assert np.array_equal(np.unique(cap_tris), np.arange(len(cap_verts)))
    assert cap_tris.dtype == np.int32 and cap_verts.dtype == np.float32


def test_the_cap_ends_behind_the_face(tmp_path):
    plain, plain_tris, _, plain_report, verts = build(tmp_path, front_inset=0.0)
    inset, inset_tris, _, report, _ = build(tmp_path, front_inset=0.03)
    assert len(inset_tris) < len(plain_tris)
    assert report["front_dropped"] == len(plain_tris) - len(inset_tris) and plain_report["front_dropped"] == 0
    # Nothing kept within the inset of the face (forward-facing skin outside the scalp).
    template = np.load(tmp_path / "template.npz")
    scalp = np.zeros(len(verts), bool)
    scalp[template["vg__scalp"]] = True
    face = verts[~scalp & (directions(verts)[:, 1] < cap.FACE_FORWARD)]
    centres = (inset[inset_tris].mean(1) - CENTRE) * RADIUS / (RADIUS + 0.0025) + CENTRE
    gaps = np.linalg.norm(centres[:, None] - face[None], axis=2).min(1)
    assert gaps.min() > 0.03 - 0.002


def test_a_rim_inset_pulls_every_free_edge_in(tmp_path):
    _, plain_tris, _, _, _ = build(tmp_path)
    _, tris, _, report, _ = build(tmp_path, rim_inset=0.012)
    assert 0 < len(tris) < len(plain_tris) and report["rim_dropped"] == len(plain_tris) - len(tris)


def test_the_colour_is_the_hairs_paint_without_bake_misses(tmp_path):
    *_, colour, _, _ = build(tmp_path)
    dark = (np.array(DARK) / 255.0 + 0.055) / 1.055
    assert np.allclose(colour, dark ** 2.4, atol=1e-4)


def test_a_template_without_a_scalp_group_is_refused(tmp_path):
    template, head, hair, texture, _ = write_inputs(tmp_path, scalp=False)
    with pytest.raises(ValueError, match="scalp"):
        cap.scalp_cap(np.load(template), np.load(head), np.load(hair), texture)


def test_the_stage_writes_the_keys_render_painted_head_reads(tmp_path):
    template, head, hair, texture, _ = write_inputs(tmp_path)
    out = tmp_path / "cap.npz"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/mesh_hair_scalp_cap.py"), str(template), str(head),
                             str(hair), str(texture), str(out), "--front-inset", "0.02"],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout.strip().splitlines()[-1])
    z = np.load(out)
    assert set(z.files) == {"cap_verts", "cap_tris", "cap_colour"}
    assert len(z["cap_tris"]) == report["cap_triangles"] > 0
    assert report["options"]["front_inset_m"] == 0.02
