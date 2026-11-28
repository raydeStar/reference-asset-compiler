"""Paint a hard-surface part's PBR maps from maps baked off its own geometry.

An ironwork kit piece, a machine housing or a prop is finished here the way the real thing was: bare
metal, then primer, then paint, then the years. Nothing is drawn in UV space. For every texel the
bake (scripts/blender/bake_surface_maps.py) recorded where the surface is in metres, which way it
faces, how buried or exposed it is at three scales, how near an edge, and what it is made of; each
layer is a function of those, in physical units, so wear follows the geometry and a pattern has one
size everywhere and no seam at a UV island's edge.

Four rules this module keeps, each learned by getting it wrong first:

* Noise is given to a texel at a size the texel can hold. A face painted at low density goes soft,
  not grainy.
* Rust is a crust, not a stain: it has height, and the normal map carries it.
* A mark is a few centimetres long and lies at its own angle. Polish follows where hands, feet and
  wheels go and varies along the way; nothing runs the full length of a member.
* Physically plain values: a surface is metal or it is not, and what is in between is a layer over it.

The result is three maps: base colour (sRGB), a tangent-space normal (OpenGL, +Y) and a packed
occlusion / roughness / metal map (R, G, B: how glTF and the Unreal import read it).
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import scipy.ndimage as ndi
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import cKDTree

try:  # an accelerator, never a requirement: the lookups are the same trilinear read
    import torch
    import torch.nn.functional as torch_functional

    torch.set_grad_enabled(False)
except Exception:  # pragma: no cover - depends on the workstation
    torch = None

RECIPE_SCHEMA = "rac.hard-surface-recipe.v1"
PROFILE_SCHEMA = "rac.hard-surface-profile.v1"
MAPS_SCHEMA = "rac.surface-maps.v1"
RECEIPT_SCHEMA = "rac.hard-surface-finish.v1"
KINDS = ("tread_plate", "plain_plate", "palm_rail", "worn_iron", "bronze", "coated")
PALETTE_KEYS = (
    "iron_bright",
    "patina_cool",
    "patina_warm",
    "primer",
    "rust_dark",
    "rust_mid",
    "rust_bright",
    "bronze",
    "bronze_tarnish",
    "verdigris",
    "grime",
    "dust",
    "scale",
    "burnished",
    "russet",
)


class HardSurfaceError(ValueError):
    """A recipe, profile or map set this painter will not guess its way around."""


def srgb(*c):
    c = np.array(c, np.float32) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def sm(a, b, x):
    """Smoothstep from a to b; a > b gives the falling version."""
    t = np.clip((x - a) / (b - a), 0, 1)
    return (t * t * (3 - 2 * t)).astype(np.float32)


def mix(a, b, t):
    """Blend colours (n,3) or (3,) by a per-texel mask."""
    return a + (b - a) * t[:, None]


def load_profile(profile):
    """Check a profile and return (palette namespace of linear colours, classes)."""
    if profile.get("schema") != PROFILE_SCHEMA:
        raise HardSurfaceError(f"profile schema must be {PROFILE_SCHEMA}")
    colours = profile.get("palette", {})
    missing = [key for key in PALETTE_KEYS if key not in colours]
    if missing:
        raise HardSurfaceError(f"profile palette lacks {', '.join(missing)}")
    for key, value in colours.items():
        if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) and 0 <= v <= 255 for v in value)):
            raise HardSurfaceError(f"palette colour {key!r} must be three sRGB values from 0 to 255")
    palette = SimpleNamespace(**{key: srgb(*value) for key, value in colours.items()})
    classes = profile.get("classes", {})
    for name, entry in classes.items():
        if entry.get("kind") not in KINDS:
            raise HardSurfaceError(f"class {name!r} has kind {entry.get('kind')!r}; kinds are {', '.join(KINDS)}")
        if entry["kind"] == "coated":
            for key in ("coat", "faded"):
                if entry.get(key) not in colours:
                    raise HardSurfaceError(f"class {name!r} needs {key!r} to name a palette colour")
            if not 0.6 <= float(entry.get("level", 1.1)) <= 1.6:
                raise HardSurfaceError(f"class {name!r}: level is how much damage paint takes before it lets go, 0.6 to 1.6")
    return palette, classes


class Noise:
    """Tileable 3-D noise volumes, sampled at real positions so nothing follows a UV seam.

    The volumes are deterministic and cached on disk; `size` is 256 for production and small in tests.
    """

    def __init__(self, cache=None, size=256):
        cache = Path(cache or os.environ.get("RAC_NOISE_CACHE") or Path(tempfile.gettempdir()) / "rac-hard-surface-noise") / str(size)
        cache.mkdir(parents=True, exist_ok=True)
        self.size = size
        cell = max(24, round(size * 168 / 256))
        made = {}
        for name, build in (
            ("fbm", lambda: self._spectral(size, lambda k: np.where(k >= 1.5, np.maximum(k, 1e-3) ** -2.0, 0), 11)),
            ("band", lambda: self._spectral(size, lambda k: np.exp(-(((k - 24 * size / 256) / (8.5 * size / 256)) ** 2)), 12)),
            ("cell", lambda: self._cell(cell)),
        ):
            if not all((cache / f"{part}.npy").exists() for part in (("cell", "cellid") if name == "cell" else (name,))):
                volumes = build()
                # Written whole or not at all: several parts are painted at once and share this cache.
                for part, volume in (("cell", volumes[0]), ("cellid", volumes[1])) if name == "cell" else ((name, volumes),):
                    draft = cache / f"{part}.{os.getpid()}.npy"
                    np.save(draft, volume)
                    os.replace(draft, cache / f"{part}.npy")
        for name in ("fbm", "band", "cell", "cellid"):
            levels = [np.load(cache / f"{name}.npy").astype(np.float32)]
            # Coarser copies of the broad-band noise, so a face painted at low density is given
            # noise it can actually hold instead of aliasing it into grain.
            while name == "fbm" and levels[-1].shape[0] > 16:
                v = levels[-1]
                h = v.shape[0] // 2
                levels.append(v.reshape(h, 2, h, 2, h, 2).mean(axis=(1, 3, 5)))
            made[name] = [self._prepare(level) for level in levels]
        self.volumes = made

    @staticmethod
    def _prepare(volume):
        if torch is None:
            return volume
        v = torch.from_numpy(volume)
        v = torch.cat([v, v[:1]], 0)
        v = torch.cat([v, v[:, :1]], 1)
        v = torch.cat([v, v[:, :, :1]], 2)
        return v[None, None]

    @staticmethod
    def _spectral(size, shape, seed):
        rng = np.random.default_rng(seed)
        white = np.fft.rfftn(rng.standard_normal((size,) * 3).astype(np.float32))
        axes = np.meshgrid(np.fft.fftfreq(size) * size, np.fft.fftfreq(size) * size, np.fft.rfftfreq(size) * size, indexing="ij")
        k = np.sqrt(sum(a**2 for a in axes))
        field = np.fft.irfftn(white * shape(k), s=(size,) * 3, axes=(0, 1, 2)).astype(np.float32)
        return field / field.std()

    @staticmethod
    def _cell(size):
        rng = np.random.default_rng(13)
        grid = 14
        points = (np.stack(np.meshgrid(*[np.arange(grid)] * 3, indexing="ij"), -1).reshape(-1, 3) + rng.random((grid**3, 3))) / grid
        tree = cKDTree(points % 1.0, boxsize=1.0)
        centers = (np.stack(np.meshgrid(*[np.arange(size)] * 3, indexing="ij"), -1).reshape(-1, 3) + 0.5) / size
        distance, index = tree.query(centers, k=2, workers=-1)
        edge = ((distance[:, 1] - distance[:, 0]) * grid).astype(np.float32)  # 0 on a cell wall
        ident = rng.random(len(points)).astype(np.float32)[index[:, 0]]
        return edge.reshape((size,) * 3), ident.reshape((size,) * 3)

    def sample(self, name, q, nearest=False, level=None):
        volumes = self.volumes[name]
        if level is None or len(volumes) == 1:
            return self._lookup(volumes[0], q, nearest)
        out = np.empty(len(q), np.float32)
        level = np.clip(level, 0, len(volumes) - 1)
        for k in np.unique(level):
            pick = level == k
            out[pick] = self._lookup(volumes[int(k)], q[pick], nearest)
        return out

    @staticmethod
    def _lookup(volume, q, nearest):
        q = np.ascontiguousarray(q, dtype=np.float32)
        if torch is None:
            n = volume.shape[0]
            coords = ((q - np.floor(q)) * n).T
            return ndi.map_coordinates(volume, coords, order=0 if nearest else 1, mode="grid-wrap", prefilter=False).astype(np.float32)
        g = torch.from_numpy(q)
        g = (g - torch.floor(g)) * 2 - 1
        out = torch_functional.grid_sample(
            volume, g.view(1, -1, 1, 1, 3), mode="nearest" if nearest else "bilinear", padding_mode="border", align_corners=True
        )
        return out.view(-1).numpy()


class Field:
    """Everything known about a set of texels, with noise sampled where they really are."""

    def __init__(self, noise, pal, **arrays):
        self.noise = noise
        self.pal = pal
        self.__dict__.update(arrays)
        self.n = len(self.P)

    def take(self, mask):
        return Field(self.noise, self.pal, **{k: v[mask] for k, v in self.__dict__.items() if isinstance(v, np.ndarray) and len(v) == self.n})

    def _coords(self, period, seed, stretch, axis):
        rng = np.random.default_rng(seed)
        p = self.P
        if not np.isscalar(period):
            period = np.asarray(period, np.float32)[:, None]
        if stretch:
            a = self.axis if axis is None else np.broadcast_to(np.asarray(axis, np.float32), p.shape)
            p = p - a * ((p * a).sum(1, keepdims=True) * (1 - 1 / stretch))
            return p / period + rng.random(3).astype(np.float32)
        rotation = np.linalg.qr(rng.standard_normal((3, 3)))[0].astype(np.float32)
        return (p @ rotation) / period + rng.random(3).astype(np.float32)

    def fbm(self, period, seed, stretch=None, axis=None):
        """Broad-band noise, unit variance. `period` is the repeat length; features run from about a third of it down."""
        level = np.rint(np.log2(np.maximum(self.texel * self.noise.size / period, 1e-6))).astype(np.int32)
        return self.noise.sample("fbm", self._coords(period, seed, stretch, axis), level=level)

    def band(self, size, seed, stretch=None, axis=None):
        """Single-scale noise, unit variance, with features `size` metres across (a scalar or one size per texel).
        Fades to nothing where a texel is too coarse to hold a feature that small."""
        size = size if np.isscalar(size) else np.asarray(size, np.float32)
        return self.noise.sample("band", self._coords(size * 24, seed, stretch, axis)) * sm(1.6, 3.2, size / self.texel)

    def cell(self, size, seed):
        """Cells `size` across: distance from the cell wall (0 at the wall), and a random value per cell."""
        q = self._coords(size * 14, seed, None, None)
        return self.noise.sample("cell", q), self.noise.sample("cellid", q, nearest=True)


class Layers:
    def __init__(self, n):
        self.C = np.zeros((n, 3), np.float32)
        self.R = np.full(n, 0.5, np.float32)
        self.M = np.zeros(n, np.float32)
        self.H = np.zeros(n, np.float32)

    def lay(self, mask, color=None, rough=None, metal=None, height=None, lift=None):
        m = np.clip(mask, 0, 1).astype(np.float32)
        if color is not None:
            self.C += (color - self.C) * m[:, None]
        if rough is not None:
            self.R += (rough - self.R) * m
        if metal is not None:
            self.M += (metal - self.M) * m
        if height is not None:
            self.H += (height - self.H) * m
        if lift is not None:
            self.H += lift * m


# ---------------------------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------------------------


def bare_iron(f, L, seed):
    """Wrought iron worn bright: the metal under everything else."""
    grain = f.band(0.0016, seed, stretch=26)
    smear = f.fbm(0.07, seed + 1)
    L.C[:] = f.pal.iron_bright * (1 + 0.025 * grain[:, None] + 0.04 * smear[:, None])
    L.R[:] = 0.30 + 0.05 * grain + 0.05 * smear
    L.M[:] = 1.0
    L.H[:] = grain * 7e-6


def patina(f, L, seed, warmth=0.0, amount=1.0):
    """The dark skin iron grows when it is handled and oiled rather than painted."""
    big = f.fbm(0.55, seed)
    mid = f.fbm(0.09, seed + 1)
    pit = f.band(0.0032, seed + 2)
    tone = mix(f.pal.patina_cool, f.pal.patina_warm, sm(-2.4, 2.4, 0.8 * big + 0.5 * mid + 2.4 * warmth))
    tone = tone * (1 + 0.10 * mid[:, None])
    L.lay(
        np.full(f.n, amount, np.float32) if np.isscalar(amount) else amount,
        color=tone,
        rough=0.52 + 0.06 * mid + 0.04 * pit,
        metal=0.86,
        lift=2.5e-5 + pit * 1.4e-5,
    )


def rust(f, L, amount, seed):
    """Rust: three ages of it. It is a crust, not a stain: it stands proud of the metal it ate,
    lifts into scabs a few millimetres across and pits between them, and every one of those is
    height the normal map carries. Scabs are never smaller than three texels, so the relief
    survives on faces painted at low density."""
    a = f.fbm(0.07, seed)
    b = f.fbm(0.012, seed + 1)
    pit = f.band(0.0030, seed + 2)
    scab = f.band(np.maximum(0.0055, 3.0 * f.texel), seed + 3)
    tone = mix(f.pal.rust_dark, f.pal.rust_mid, sm(-0.9, 0.5, a + 0.5 * b))
    tone = mix(tone, f.pal.rust_bright, sm(0.9, 2.0, b + 0.5 * pit) * 0.7)
    tone = tone * (1 + 0.16 * scab[:, None])  # crowns catch a little more light, pits less
    crust = sm(0.25, 0.8, amount)
    L.lay(amount, color=tone, rough=0.84 + 0.05 * pit + 0.04 * scab, metal=0.0, lift=crust * (1.5e-4 + 1.7e-4 * sm(-0.7, 1.2, scab) + pit * 7e-5))


def painted(f, L, seed, coat, faded, level, peel=1.0):
    """Paint over red-oxide primer over iron, chipped where it is struck and where rust lifted it.

    Returns (paint, primer_only, bare) masks. `level` is how much damage it takes to get through;
    lower is more worn.
    """
    big = f.fbm(0.5, seed)
    mid = f.fbm(0.10, seed + 1)
    fine = f.fbm(0.016, seed + 2)
    wall, ident = f.cell(0.007, seed + 3)
    # What takes paint off: edges, rivet crowns, knocks that cluster, and the flake-shaped way it lets go.
    damage = (
        1.9 * f.edge
        + 1.5 * f.dtop * sm(-1.0, 0.9, f.fbm(0.06, seed + 9))
        + 0.50 * big
        + 0.46 * mid
        + 0.30 * fine
        + 0.34 * (ident - 0.5)
        + 0.5 * f.cav * (mid > 0)
    )
    paint = sm(level + 0.07, level - 0.07, damage)
    primer = sm(level + 0.30, level + 0.12, damage)
    bare = 1 - primer
    # Colour: sun and rain chalk the upward faces; shelter keeps the pigment.
    exposure = sm(-0.2, 0.9, f.up) * f.ao
    tone = mix(coat, faded, np.clip(0.25 + 0.55 * exposure + 0.22 * big, 0, 1))
    tone = tone * (1 + 0.07 * mid[:, None] + 0.03 * fine[:, None])
    peel_noise = f.band(0.0024, seed + 4)
    brush = f.band(0.0050, seed + 5, stretch=7)
    # Paint lifts into blisters just before it lets go.
    blister = sm(level - 0.42, level - 0.12, damage) * sm(0.5, 1.5, f.band(0.006, seed + 6)) * peel
    L.lay(primer, color=f.pal.primer * (1 + 0.08 * fine[:, None]), rough=0.72, metal=0.0, lift=6e-5)
    L.lay(
        paint,
        color=tone,
        rough=0.50 + 0.05 * mid + 0.10 * exposure - 0.10 * sm(0.25, 0.8, f.edge),
        metal=0.0,
        lift=1.6e-4 + peel_noise * 9e-6 + brush * 1.4e-5 + blister * 2.2e-4,
    )
    L.lay(paint * blister * 0.5, color=tone * 1.12, rough=0.58)
    return paint, primer * (1 - paint), bare


def weather_bare(f, L, bare, seed, fresh):
    """What bare iron does once the paint is gone: stays bright where it is still being rubbed, rusts elsewhere."""
    rusting = bare * (1 - fresh)
    rust(f, L, rusting, seed)
    return rusting


def rust_wash(f, L, source, seed, strength=0.5):
    """Rust carried by rain: a thin stain below and around where the rust lives, running with gravity on upright faces."""
    streak = f.fbm(0.035, seed, stretch=16, axis=(0, 0, 1))
    upright = 1 - np.abs(f.N[:, 2])
    veil = sm(0.9, 1.9, streak * 0.9 + f.fbm(0.3, seed + 1) * 0.7 + f.cav * 1.8) * (0.25 + 0.75 * upright)
    L.lay(veil * strength * (1 - source), color=f.pal.rust_mid * 1.05, rough=0.72, metal=0.0)
    return veil


def drips(f, fasteners, seed):
    """Where rain has carried rust down an upright face from a rivet or bolt: 0..1, strongest just below the head."""
    out = np.zeros(f.n, np.float32)
    heads = np.asarray(fasteners, np.float32).reshape(-1, 7)
    heads = heads[np.abs(heads[:, 5]) < 0.5]
    upright = np.flatnonzero(np.abs(f.N[:, 2]) < 0.45)
    if not len(heads) or not len(upright):
        return out
    rng = np.random.default_rng(seed)
    run = (rng.uniform(0.025, 0.17, len(heads)) * (rng.random(len(heads)) < 0.72)).astype(np.float32)  # some stay clean
    distance, index = cKDTree(heads[:, :2]).query(f.P[upright, :2], k=min(6, len(heads)), distance_upper_bound=0.03, workers=-1)
    if distance.ndim == 1:
        distance, index = distance[:, None], index[:, None]
    best = np.zeros(len(upright), np.float32)
    for k in range(distance.shape[1]):
        near = np.isfinite(distance[:, k])
        i = np.where(near, index[:, k], 0)
        drop = heads[i, 2] - f.P[upright, 2]
        facing = (f.N[upright] * heads[i, 3:6]).sum(1) > 0.7
        length = np.maximum(run[i], 1e-4)
        t = np.clip(drop / length, 0, 1)
        width = heads[i, 6] * (0.50 + 0.60 * t)
        lateral = np.where(near, distance[:, k], 1.0)
        best = np.maximum(best, np.exp(-((lateral / width) ** 2)) * (1 - t) ** 1.3 * near * facing * (drop > -heads[i, 6] * 0.2) * (drop < length))
    out[upright] = best
    return out


def bronze(f, L, seed):
    big = f.fbm(0.3, seed)
    mid = f.fbm(0.05, seed + 1)
    pit = f.band(0.0030, seed + 2)
    L.C[:] = f.pal.bronze * (1 + 0.05 * mid[:, None])
    L.R[:] = 0.30 + 0.06 * mid
    L.M[:] = 1.0
    L.H[:] = pit * 6e-6
    tarnish = sm(-0.9, 0.5, 0.7 * big + 0.6 * mid + 1.6 * f.cav - 2.2 * f.edge - 1.2 * f.dtop + 0.2)
    L.lay(tarnish * 0.9, color=f.pal.bronze_tarnish * (1 + 0.10 * mid[:, None]), rough=0.50 + 0.05 * pit, metal=0.9, lift=1.5e-5 + pit * 1.0e-5)
    green = sm(0.35, 1.1, 2.4 * f.cav + 0.9 * (1 - f.mid) + 0.45 * mid + 0.35 * big - 0.25 * f.up - 0.2)
    L.lay(green * 0.92, color=f.pal.verdigris * (1 + 0.12 * mid[:, None]), rough=0.86, metal=0.0, lift=4e-5 + pit * 3e-5)


def lozenges(x, y):
    """Raised-lozenge tread, heights 0..1: 26 mm cells on the diagonal, alternate bars turned ninety degrees."""
    pitch = 0.026
    u = (x + y) / math.sqrt(2) / pitch
    v = (x - y) / math.sqrt(2) / pitch
    i = np.floor(u)
    j = np.floor(v)
    a = (u - i - 0.5) * pitch
    b = (v - j - 0.5) * pitch
    turn = ((i + j) % 2) > 0.5
    a, b = np.where(turn, b, a), np.where(turn, a, b)
    return np.clip(1 - (np.abs(a) / 0.0108) ** 2 - (np.abs(b) / 0.0032) ** 2, 0, 1) ** 0.7


def plain_plate(f, L, seed):
    """Smooth rolled plate that is walked on: bridge treads, the hatch leaf, the doorstep."""
    bare_iron(f, L, seed)
    top = (f.up > 0.5).astype(np.float32)
    big = f.fbm(0.6, seed + 3)
    mid = f.fbm(0.11, seed + 4)
    fine = f.fbm(0.02, seed + 5)
    # Feet polish a broad, soft path; the sheen changes long before the colour does.
    scuff = top * sm(-1.0, 1.4, f.fbm(2.6, seed + 2)) * sm(0.02, 0.14, f.rim) * 0.75
    polish = sm(0.18, 0.95, scuff + 0.04 * mid) * top
    keep = np.clip(1 - 0.50 * polish - f.dtop * 0.6, 0, 1)
    patina(f, L, seed + 7, warmth=-0.35, amount=keep)
    L.R -= polish * keep * 0.16
    L.lay(sm(0.10, 0.7, scuff) * keep * top * 0.30, color=f.pal.burnished, metal=0.92)
    score = f.band(0.0012, seed + 10, stretch=16) * sm(-0.6, 0.8, f.fbm(0.08, seed + 15))
    L.R += polish * (0.06 * score + 0.04 * mid)
    L.H += polish * score * 8e-6
    edge_in = sm(0.04, 0.004, f.rim + 0.012 * mid) * (1 - f.rnd) * top + 0.30 * (1 - top)
    amount = sm(
        0.80, 1.18, 0.9 * edge_in + 1.7 * f.cav + 0.30 * big + 0.30 * mid + 0.20 * fine + 0.55 * sm(0.2, -0.6, f.up) - 1.2 * scuff - 0.9 * f.dtop
    )
    rust(f, L, amount, seed + 12)
    bloom = (1 - amount) * (1 - scuff) * sm(-0.2, 1.6, f.fbm(2.4, seed + 13) + 0.8 * edge_in) * 0.07
    L.lay(bloom, color=f.pal.rust_mid, rough=0.66, metal=0.3)
    return scuff, amount


def palm_rail(f, L, seed):
    """The rail a hand rests on: browned iron, burnished bright along the crown where palms have rubbed it."""
    bare_iron(f, L, seed)
    big = f.fbm(0.7, seed + 3)
    mid = f.fbm(0.08, seed + 4)
    smear = f.fbm(0.045, seed + 5)
    reach = f.fbm(1.3, seed + 6, stretch=5)
    zones = sm(-1.2, 0.7, f.fbm(0.55, seed + 14, stretch=2.5))  # hands and boots favour some stretches
    crown = sm(0.28, 0.98, f.N[:, 2]) * (0.80 + 0.20 * sm(-1.5, 1.5, reach)) * (0.38 + 0.62 * zones) * sm(0.35, 0.9, f.mid + 0.1)
    pits = sm(1.1, 2.0, f.band(0.0042, seed + 8))
    keep = np.clip(1 - sm(0.22, 0.95, crown) * 0.93 + pits * 0.55 * sm(0.95, 0.35, crown), 0, 1)
    patina(f, L, seed + 7, warmth=0.75, amount=keep)
    # Where the polish gives out the iron is a warm russet, not yet dark.
    L.lay(sm(0.10, 0.55, crown) * keep * 0.6, color=f.pal.russet, rough=0.38, metal=0.92)
    hand = f.band(0.0011, seed + 9, stretch=16) * sm(-0.6, 0.8, f.fbm(0.09, seed + 15))
    L.R += (1 - keep) * (-0.11 + 0.05 * hand + 0.07 * smear)
    L.H += (1 - keep) * hand * 5e-6
    # Below the hand line: rust freckles and the dried marks of rain that beaded and sat.
    wall, ident = f.cell(0.011, seed + 10)
    bead = sm(0.50, 0.60, wall) * sm(0.74, 0.62, wall) * (ident > 0.70) * keep * sm(-0.4, 0.5, f.N[:, 2])
    L.lay(bead * 0.10, color=f.pal.scale, rough=0.70, metal=0.5, lift=4e-6)
    L.R -= sm(0.74, 0.86, wall) * (ident > 0.70) * keep * sm(-0.4, 0.5, f.N[:, 2]) * 0.10
    amount = sm(0.92, 1.25, 1.7 * f.cav + 0.55 * sm(0.1, -0.8, f.N[:, 2]) + 0.30 * big + 0.40 * mid + 0.34 * f.fbm(0.014, seed + 11) - 1.5 * crown)
    rust(f, L, amount, seed + 12)
    return crown, amount


def worn_iron(f, L, seed):
    """Unpainted iron fittings: strakes, flanges, grate bars, collars. Dark, rust in the lee, bright where struck."""
    bare_iron(f, L, seed)
    big = f.fbm(0.5, seed + 3)
    mid = f.fbm(0.09, seed + 4)
    fine = f.fbm(0.016, seed + 5)
    # Edges and rivet crowns are struck bright. Upward faces that feet and cargo reach are
    # burnished instead: an even, dull polish that changes the sheen more than the colour.
    struck = np.clip(1.5 * f.edge * (1 - f.rnd * 0.6) + 0.85 * f.dtop * sm(-0.6, 1.2, f.fbm(0.05, seed + 8)), 0, 1)
    burnish = sm(0.5, 0.95, f.up) * sm(0.55, 0.95, f.mid) * (1 - f.rnd) * (0.55 + 0.45 * sm(-1.2, 1.2, f.fbm(1.1, seed + 9)))
    keep = np.clip(1 - sm(0.42, 0.92, struck) - 0.40 * burnish, 0, 1)
    patina(f, L, seed + 7, warmth=0.15, amount=keep)
    L.R -= burnish * keep * 0.14
    score = f.band(0.0012, seed + 10, stretch=14) * sm(-0.6, 0.8, f.fbm(0.08, seed + 15))
    L.R += (1 - keep) * (-0.05 + 0.07 * score)
    L.H += (1 - keep) * score * 8e-6
    worn = np.clip(struck + 0.6 * burnish, 0, 1)
    amount = sm(0.72, 1.15, 1.8 * f.cav + 0.55 * sm(0.2, -0.7, f.up) + 0.40 * big + 0.38 * mid + 0.25 * fine + 0.35 * (1 - f.ao) - 1.3 * worn)
    rust(f, L, amount, seed + 12)
    L.lay((1 - amount) * keep * (1 - burnish) * sm(0.3, 1.2, 0.6 * big + 0.7 * mid) * 0.35, color=f.pal.rust_mid, rough=0.66, metal=0.25)
    return worn, amount


def coated(f, L, seed, coat, faded, level):
    """A painted member: teal on the plates and webs, slate on the structural sections."""
    bare_iron(f, L, seed)
    paint, primer, bare = painted(f, L, seed + 20, coat, faded, level)
    fresh = sm(0.55, 0.95, 1.3 * f.edge + 1.1 * f.dtop) * sm(0.6, 0.95, f.mid)
    rusting = weather_bare(f, L, bare, seed + 30, fresh)
    L.R += bare * fresh * -0.04
    rust_wash(f, L, rusting, seed + 40, strength=0.42)
    return fresh, rusting


def stamp(x, y, origin, text, height=0.034):
    """A foundry die struck into the plate. 1 inside the letters and border, read with +Y up."""
    scale = 4000  # pixels per metre of die
    font = None
    for name in ("georgiab.ttf", "DejaVuSerif-Bold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, int(height * scale * 0.62))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(int(height * scale * 0.62))
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    pad = int(height * scale * 0.30)
    w = right - left + 2 * pad
    h = int(height * scale)
    die = Image.new("L", (w, h))
    pen = ImageDraw.Draw(die)
    pen.rounded_rectangle((3, 3, w - 4, h - 4), radius=int(h * 0.16), outline=255, width=max(3, int(h * 0.06)))
    pen.text((pad - left, (h - (bottom - top)) // 2 - top), text, font=font, fill=255)
    die = ndi.gaussian_filter(np.asarray(die, np.float32) / 255, 1.2)
    px = (x - origin[0]) * scale
    py = (h - 1) - (y - origin[1]) * scale
    inside = (px >= 0) & (px < w - 1) & (py >= 0) & (py < h - 1)
    out = np.zeros_like(x, dtype=np.float32)
    out[inside] = ndi.map_coordinates(die, [py[inside], px[inside]], order=1)
    return out, (w / scale, h / scale)


def tread_plate(f, L, seed, options, bounds):
    """A plate that is walked and driven on: rolled tread, wheel lines worn to a sheen, rust creeping in from the edges.

    `options` may give `pattern` ("lozenge" or "none"), `wheel_lines_y_m` (where wheels run, along +X) and `stamp`
    ({"text", "origin_m"}: a foundry die struck into a plain panel). `bounds` is the part's (low, high) in metres.
    """
    x, y, top = f.P[:, 0], f.P[:, 1], f.up > 0.5
    bare_iron(f, L, seed)
    L.C *= 0.80  # iron tyres leave a dull grey polish, not chrome
    big = f.fbm(0.6, seed + 3)
    mid = f.fbm(0.11, seed + 4)
    fine = f.fbm(0.02, seed + 5)
    span = max(float(bounds[1][0] - bounds[0][0]), 1e-3)  # the bay's length: wear repeats in whole fractions of it
    patterned = options.get("pattern", "lozenge") == "lozenge"
    relief = np.zeros(f.n, np.float32)
    die = np.zeros(f.n, np.float32)
    if patterned:
        relief = lozenges(x, y) * sm(0.074, 0.092, f.rim) * top  # a plain margin for the rivet line
    if options.get("stamp"):
        origin = options["stamp"]["origin_m"]
        die, extent = stamp(x, y, origin, options["stamp"].get("text", ""))
        cartouche = (x > origin[0] - 0.015) & (x < origin[0] + 0.015 + extent[0]) & (y > origin[1] - 0.015) & (y < origin[1] + 0.015 + extent[1])
        relief = relief * (1 - cartouche.astype(np.float32))  # the die sits in a plain panel
        die = die * top
    # Wheel lines wander a centimetre and their strength breathes along the bay in whole fractions of its
    # length, so the same plate laid end to end joins up.
    turn = 2 * math.pi * x / span
    wander = 0.012 * np.sin(2 * turn)
    rng = np.random.default_rng(seed + 6)
    track = np.zeros(f.n, np.float32)
    for line in (0.47, 1.53) if options.get("wheel_lines_y_m") is None else options["wheel_lines_y_m"]:
        phase = rng.uniform(0, 2 * math.pi, 3)
        if bounds[0][1] <= line <= bounds[1][1]:
            d = y - line - wander
            breathe = 0.70 + 0.15 * np.sin(turn + phase[0]) + 0.09 * np.sin(2 * turn + phase[1]) + 0.06 * np.sin(3 * turn + phase[2])
            track = np.maximum(track, (np.exp(-((d / 0.042) ** 2)) + 0.40 * np.exp(-((d / 0.125) ** 2))) / 1.4 * breathe)
    track = (track * top).astype(np.float32)
    foot = top * sm(-1.0, 1.4, f.fbm(3.2, seed + 2)) * 0.18  # where people walk between the wheel lines: broad, soft
    wear = np.clip(track + foot, 0, 1)
    relief = relief * (1 - 0.80 * sm(0.12, 0.80, track)) * (1 - 0.25 * foot)
    L.H += relief * 1.35e-3 - die * 5.5e-4
    # The dark skin everywhere it is not being polished: valleys keep it, lozenge crowns lose it first.
    crown = relief * sm(0.3, 0.9, relief)
    polish = sm(0.15, 0.90, wear + 0.45 * crown * (0.25 + wear) + 0.04 * mid) * top
    keep = (1 - 0.46 * polish).astype(np.float32)
    patina(f, L, seed + 7, warmth=-0.45, amount=keep)
    # Traffic burnishes long before it bares the metal: the sheen changes first.
    L.R += (0.27 - L.R) * polish * 0.8
    L.lay(sm(0.10, 0.7, wear) * keep * top * 0.30, color=f.pal.burnished, metal=0.92)
    # Bright metal in the tracks is scored along the direction of travel.
    score = f.band(0.0011, seed + 10, stretch=60, axis=(1, 0, 0))
    gouge = sm(1.5, 2.3, f.band(0.0022, seed + 11, stretch=90, axis=(1, 0, 0)))
    bright = polish
    L.R += bright * (0.06 * score + 0.04 * mid)
    L.H += bright * (score * 9e-6 - gouge * 6e-5)
    L.lay(bright * gouge * 0.6, color=f.pal.iron_bright, rough=0.24)
    # Rust: in from the edges, around every rivet, in the valleys off the wheel line, under the plate.
    edge_in = sm(0.045, 0.004, f.rim + 0.012 * mid) * (1 - f.rnd) * top + 0.30 * (1 - top)
    under = sm(0.2, -0.6, f.up)
    valley = (1 - sm(0.05, 0.5, relief)) * sm(0.074, 0.1, f.rim) * top if patterned else np.zeros(f.n, np.float32)
    amount = sm(
        0.80,
        1.18,
        0.90 * edge_in + 1.7 * f.cav + 0.30 * big + 0.30 * mid + 0.20 * fine + 0.55 * under + 0.20 * valley + 0.5 * die - 1.3 * wear - 0.9 * f.dtop,
    )
    rust(f, L, amount, seed + 12)
    # A brown bloom ahead of the rust proper, mostly down in the valleys where water sits longest.
    bloom = (1 - amount) * (1 - wear) * sm(-0.2, 1.6, f.fbm(2.4, seed + 13) + 0.5 * valley + 0.8 * edge_in) * (0.02 + 0.10 * valley)
    L.lay(bloom, color=f.pal.rust_mid, rough=0.66, metal=0.3)
    return wear, amount


# ---------------------------------------------------------------------------------------------
# From maps to textures
# ---------------------------------------------------------------------------------------------
REQUIRED_MAPS = ("valid", "pos", "nrm", "ao", "bev", "cls")


def _islands(valid, pos):
    """Label the UV islands and measure each one's real texel size from the positions themselves."""
    labels, count = ndi.label(valid)
    step = np.zeros(valid.shape, np.float32)
    pairs = np.zeros(valid.shape, np.float32)
    for shift in (0, 1):
        a = [slice(None), slice(None)]
        b = [slice(None), slice(None)]
        a[shift] = slice(0, -1)
        b[shift] = slice(1, None)
        a, b = tuple(a), tuple(b)
        same = (labels[a] == labels[b]) & valid[a]
        d = np.linalg.norm(pos[b] - pos[a], axis=-1) * same
        d[d > 0.02] = 0  # a jump, not a neighbour: a seam inside one island
        step[a] += d
        pairs[a] += same & (d > 0)
    texel = np.bincount(labels.ravel(), step.ravel(), count + 1) / np.maximum(np.bincount(labels.ravel(), pairs.ravel(), count + 1), 1)
    measured = texel[1:][texel[1:] > 0]
    typical = float(np.median(measured)) if len(measured) else 1e-3
    texel[texel <= 0] = typical
    return labels, count, texel[labels].astype(np.float32), typical


def derive_attributes(labels, count, valid, pos, normal):
    """What a mesh that carries no annotations still says about itself, per UV island.

    Returns (round, grain axis, dome) for the valid texels. An island whose normals disagree is a tube or a
    dome, so it has no rim to wear. Its longest direction in space is the way the member runs, which is the
    way a rolled section's grain runs. A small round island is a rivet or bolt head, and how squarely a texel
    faces along the island's mean normal says how near the crown it is.
    """
    index = labels[valid]
    n = np.maximum(np.bincount(index, minlength=count + 1), 1).astype(np.float64)
    points = pos[valid].astype(np.float64)

    def per_island(values):
        return np.stack([np.bincount(index, values[:, k], count + 1) for k in range(values.shape[1])], 1) / n[:, None]

    mean_normal = per_island(normal.astype(np.float64))
    facing = np.linalg.norm(mean_normal, axis=1)
    curved = facing < 0.985
    centred = points - per_island(points)[index]
    covariance = np.zeros((count + 1, 3, 3))
    for i in range(3):
        for j in range(i, 3):
            covariance[:, i, j] = covariance[:, j, i] = np.bincount(index, centred[:, i] * centred[:, j], count + 1) / n
    spread, vectors = np.linalg.eigh(covariance)
    along = vectors[:, :, 2][index]  # the direction each island is longest in
    along = along - normal * (along * normal).sum(1, keepdims=True)  # laid into the surface
    short = np.linalg.norm(along, axis=1) < 1e-3
    along[short] = np.cross(normal[short], (0.0, 0.0, 1.0)) + 1e-6
    along /= np.maximum(np.linalg.norm(along, axis=1, keepdims=True), 1e-9)
    lead = np.argmax(np.abs(along), axis=1)
    flip = along[np.arange(len(along)), lead] < 0
    along[flip] *= -1  # one sign per direction, so parallel faces agree
    small = np.sqrt(np.maximum(spread.sum(1), 0)) < 0.016  # an island a couple of centimetres across
    head = (curved & small)[index]
    crown = (normal * (mean_normal / np.maximum(facing, 1e-9)[:, None])[index]).sum(1)
    dome = np.where(head, np.clip((crown - 0.55) / 0.45, 0, 1), 0)
    return curved[index], along.astype(np.float32), dome.astype(np.float32)


def paint(maps, recipe, palette, classes, noise):
    """Paint one part. `maps` is what bake_surface_maps wrote; returns the three images and what was measured."""
    for key in REQUIRED_MAPS:
        if key not in maps:
            raise HardSurfaceError(f"the maps lack {key!r}; bake them with bake_surface_maps")
    valid = np.asarray(maps["valid"], bool)
    H, W = valid.shape
    if not valid.any():
        raise HardSurfaceError("the maps cover no texel: is UV0 inside 0..1?")
    pos = np.asarray(maps["pos"], np.float32)
    nrm = np.asarray(maps["nrm"], np.float32)
    ao = np.asarray(maps["ao"], np.float32)
    bev = np.asarray(maps["bev"], np.float32)
    cls = np.asarray(maps["cls"])
    names = [str(n) for n in maps.get("class_names", [])] or [str(i) for i in range(int(cls.max()) + 1)]
    low, high = np.asarray(maps["bounds"], np.float32) if "bounds" in maps else np.stack([pos[valid].min(0), pos[valid].max(0)])
    weight = ndi.gaussian_filter(valid.astype(np.float32), 0.9) + 1e-6

    def soften(image):
        """Average sampling noise out of a bake without bleeding across island borders."""
        if image.ndim == 3:
            return np.stack([soften(image[..., i]) for i in range(image.shape[2])], -1)
        return ndi.gaussian_filter(image * valid, 0.9) / weight

    ao = soften(ao)
    bev = soften(bev)
    labels, count, texel_m, typical = _islands(valid, pos)
    rim = (ndi.distance_transform_edt(valid) * texel_m).astype(np.float32)

    v = valid
    normal = nrm[v]
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-6)
    curved, grain, dome = derive_attributes(labels, count, valid, pos, normal)
    if "axis" in maps:  # an annotated mesh knows better than a guess
        grain = np.asarray(maps["axis"], np.float32)[v]
        grain /= np.maximum(np.linalg.norm(grain, axis=1, keepdims=True), 1e-6)
    if "rnd" in maps:
        curved = np.asarray(maps["rnd"], bool)[v]
    if "dome" in maps:
        dome = np.asarray(maps["dome"], np.float32)[v]
    edge_raw = np.clip((1 - bev[..., 3][v]) / 0.15, 0, 1)
    mid = np.clip(ao[..., 2][v], 0, 1)
    f = Field(
        noise,
        palette,
        P=pos[v],
        N=normal,
        axis=grain,
        cls=cls[v].astype(np.int16),
        ao=np.clip(ao[..., 0][v], 0, 1),
        cav=np.clip(1 - ao[..., 1][v], 0, 1),
        mid=mid,
        edge=(edge_raw * sm(0.72, 0.95, mid)).astype(np.float32),
        up=normal[:, 2].copy(),
        dtop=sm(0.30, 0.95, dome),
        rnd=curved.astype(np.float32),
        texel=texel_m[v].astype(np.float32),
        rim=np.where(curved, 1.0, rim[v]).astype(np.float32),
    )
    n = f.n
    C = np.zeros((n, 3), np.float32)
    R = np.zeros(n, np.float32)
    M = np.zeros(n, np.float32)
    Hh = np.zeros(n, np.float32)
    polished = np.zeros(n, np.float32)
    rusted = np.zeros(n, np.float32)
    walked = np.zeros(n, np.float32)
    seed = int(recipe.get("seed", 1083))
    assigned = recipe.get("classes", {})
    shares = {}
    for index in np.unique(f.cls):
        label = names[index] if index < len(names) else str(index)
        if label not in assigned:
            raise HardSurfaceError(f"the recipe gives no class for {label!r}; the maps hold {', '.join(names)}")
        if assigned[label] not in classes:
            raise HardSurfaceError(f"{label!r} is assigned {assigned[label]!r}, which the profile does not define")
        entry = classes[assigned[label]]
        kind = entry["kind"]
        pick = f.cls == index
        g = f.take(pick)
        L = Layers(g.n)
        s = seed + int(index) * 1000
        if kind == "tread_plate":
            worn, red = tread_plate(g, L, s, {**entry, **recipe.get("tread", {})}, (low, high))
            walked[pick] = g.up > 0.5
        elif kind == "plain_plate":
            worn, red = plain_plate(g, L, s)
            walked[pick] = g.up > 0.5
        elif kind == "palm_rail":
            worn, red = palm_rail(g, L, s)
        elif kind == "worn_iron":
            worn, red = worn_iron(g, L, s)
        elif kind == "bronze":
            bronze(g, L, s)
            worn = g.edge
            red = np.zeros(g.n, np.float32)
        else:
            worn, red = coated(g, L, s, getattr(palette, entry["coat"]), getattr(palette, entry["faded"]), float(entry.get("level", 1.1)))
        C[pick], R[pick], M[pick], Hh[pick] = L.C, L.R, L.M, L.H
        polished[pick] = worn
        rusted[pick] = red
        shares[label] = {"class": assigned[label], "kind": kind, "share": round(float(pick.mean()), 4)}
    L = Layers(n)
    L.C, L.R, L.M, L.H = C, R, M, Hh

    # -- the years, over everything -------------------------------------------------------------
    big = f.fbm(0.8, seed + 71)
    mid = f.fbm(0.12, seed + 72)
    fine = f.fbm(0.018, seed + 73)
    clean = np.clip(polished, 0, 1)
    # Rain picks rust up at every fastener and lays it down the face below.
    heads = recipe["fasteners"] if "fasteners" in recipe else maps.get("fasteners", [])
    run = drips(f, heads, seed + 80) * sm(-1.2, 0.6, f.fbm(0.03, seed + 81, stretch=14, axis=(0, 0, 1)))
    L.lay(run * 0.62 * (1 - clean), color=palette.rust_mid * 0.9, rough=0.74, metal=0.0, lift=4e-6)
    # Soot and oily dirt settle where nothing rubs and rain cannot reach.
    grime = sm(0.30, 1.0, 1.8 * f.cav + 0.55 * (1 - f.ao) + 0.40 * (1 - f.mid) + 0.18 * mid + 0.12 * fine) * (1 - 0.8 * clean)
    L.lay(grime * 0.62, color=palette.grime, rough=0.84, metal=0.0, lift=2e-5)
    # Dust and dried salt on sheltered upward faces; the lines a puddle leaves as it dries.
    ledge = sm(0.55, 0.95, f.up) * (1 - clean) * (1 - 0.72 * walked)
    level = f.fbm(0.33, seed + 74)
    tide = np.exp(-(((level - 0.35) / 0.045) ** 2)) + 0.7 * np.exp(-(((level + 0.55) / 0.04) ** 2))
    L.lay(ledge * tide * 0.14 * sm(-0.5, 0.5, big), color=palette.scale, rough=0.80, metal=0.0, lift=6e-6)
    L.lay(ledge * sm(0.3, 1.6, big + 0.25 * mid) * 0.09, color=palette.dust, rough=0.82, metal=0.0)
    pooled = ledge * sm(0.35, 0.8, level) * (1 - grime)
    L.R -= pooled * 0.07
    L.C *= (1 - 0.06 * pooled)[:, None]
    # Handling marks. A real scratch is a few centimetres long, goes whichever way the thing
    # that made it was moving, and keeps company: they gather where the part gets knocked.
    across = np.cross(f.N, f.axis)
    across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-6)
    marks = np.zeros(n, np.float32)
    for angle, stretch, size, threshold, k in (
        (17, 15, 0.0016, 2.2, 75),
        (-41, 10, 0.0018, 2.3, 76),
        (74, 7, 0.0020, 2.4, 77),
        (-8, 22, 0.0014, 2.5, 78),
    ):
        way = math.cos(math.radians(angle)) * f.axis + math.sin(math.radians(angle)) * across
        marks += sm(threshold, threshold + 0.6, f.band(size, seed + k, stretch=stretch, axis=way))
    knocked = sm(-0.1, 1.2, f.fbm(0.24, seed + 79))
    scratch = np.clip(marks, 0, 1) * knocked * sm(0.5, 0.9, f.mid) * (1 - grime)
    L.C += (np.float32(0.045) * scratch * (1 - L.M))[:, None]
    L.R += scratch * (0.10 * (1 - L.M) - 0.08 * L.M)
    L.H -= scratch * 2.2e-5
    # Micro-variation in gloss is what a moving light finds first.
    L.R += 0.030 * fine + 0.022 * mid * (1 - L.M * 0.3)

    # -- to maps -------------------------------------------------------------------------------
    height = np.zeros((H, W), np.float32)
    height[v] = L.H
    nearest = ndi.distance_transform_edt(~valid, return_distances=False, return_indices=True)

    def fill(image):
        """Carry every island's edge outward, so a mip never samples the void between islands."""
        return image[nearest[0], nearest[1]]

    height = fill(height)
    gy, gx = np.gradient(height)
    slope = 1.25 / fill(texel_m)  # metres of height per metre, mildly dramatised
    detail = np.stack([-gx * slope, gy * slope, np.ones_like(gx)], -1)
    detail /= np.linalg.norm(detail, axis=-1, keepdims=True)
    base = bev[..., :3].copy()
    base[~valid] = (0, 0, 1)
    base /= np.maximum(np.linalg.norm(base, axis=-1, keepdims=True), 1e-6)
    base = fill(base)
    tangent = np.stack([base[..., 0] + detail[..., 0], base[..., 1] + detail[..., 1], base[..., 2] * detail[..., 2]], -1)
    tangent /= np.linalg.norm(tangent, axis=-1, keepdims=True)
    # Occlusion: the part's own shadowing, plus the pits and seams the height field carries.
    hollow = np.clip((ndi.gaussian_filter(height, 2.5) - height) / 2.0e-4, 0, 1)
    occlusion = np.clip(f.ao**0.9 * (0.55 + 0.45 * (1 - f.cav) ** 0.8), 0, 1) * (1 - 0.35 * hollow[v])

    def image8(channels):
        arr = np.zeros((H, W, 3), np.float32)
        arr[v] = channels
        return np.uint8(np.clip(np.rint(fill(arr) * 255), 0, 255))

    base_color = image8(to_srgb(np.clip(L.C, 0.012, 0.92)))
    orm = image8(np.stack([occlusion, np.clip(L.R, 0.08, 1), np.clip(L.M, 0, 1)], -1))
    normal_map = np.uint8(np.clip(np.rint((tangent * 0.5 + 0.5) * 255), 0, 255))
    stats = {
        "resolution": [int(W), int(H)],
        "atlas_fill": round(float(valid.mean()), 3),
        "texel_mm_median": round(typical * 1000, 3),
        "islands": int(count),
        "classes": shares,
        "fasteners": int(len(np.asarray(heads).reshape(-1, 7))) if len(heads) else 0,
        "basecolor_srgb_mean": [int(c) for c in base_color[v].mean(0)],
        "roughness_p5_p95": [round(float(x), 2) for x in np.percentile(L.R, [5, 95])],
        "metal_share": round(float((L.M > 0.5).mean()), 3),
        "rust_share": round(float((rusted > 0.5).mean()), 3),
        "normal_tilt_deg_p95": round(float(np.degrees(np.arccos(np.clip(np.percentile(tangent[v][:, 2], 5), -1, 1)))), 1),
        "annotated": sorted(key for key in ("axis", "rnd", "dome") if key in maps),
        "sampler": "torch" if torch is not None else "scipy",
    }
    return {"base_color": base_color, "normal": normal_map, "orm": orm, "stats": stats}
