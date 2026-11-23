"""Append lash cards and an eye-occlusion shell to a finished character GLB.

Append-only: every existing node, mesh, accessor, material and image byte is kept.
The new geometry is derived from the acquired head's own eyelid apertures and its
eyeball helpers
nothing is reconstructed from a reference picture. Lashes and the
shell inherit the head/eye morph targets so blinks and expressions carry them.

Proven on Remora (2026-11-06, eyes73). See docs/EYE_DETAIL.md.
"""
from __future__ import annotations

import copy
import hashlib
import io
from collections import defaultdict

import numpy as np

from .polish_glb import accessor, append_accessor, faces, read_glb, write_glb

SCHEMA = 'reference-asset-compiler.eye-detail-recipe.v1'
RECEIPT = 'reference-asset-compiler.eye-detail.v1'

_UPPER = dict(columns=24, rows=4, max_length_m=0.0042, inner_fraction=0.35, peak=0.72, spread=0.35,
              outer_drop=0.25, end_taper=0.08, angle_root_deg=20, angle_tip_deg=85, outer_flare=0.35,
              root_forward_m=5e-05, root_out_m=-0.0002, u_repeat=1.0, strands=190, min_length=0.6,
              root_width_px=11, opacity=1.0, clump=0.35, lean=0.02, margin_search_m=0.0025,
              margin_lateral_m=0.0012, margin_smooth=1, margin_facing=0.3, root_line=0.16,
              root_line_opacity=0.95)
_LOWER = dict(columns=20, rows=3, max_length_m=0.0013, inner_fraction=0.2, peak=0.7, spread=0.3,
              outer_drop=0.2, end_taper=0.15, angle_root_deg=15, angle_tip_deg=45, outer_flare=0.15,
              root_forward_m=5e-05, root_out_m=-0.0002, u_repeat=1.0, strands=40, min_length=0.5,
              root_width_px=4, opacity=0.55, clump=0.2, lean=0.015, margin_search_m=0.0025,
              margin_lateral_m=0.0012, margin_smooth=1, margin_facing=0.3, root_line=0.25,
              root_line_opacity=0.5)
LASH_PRESETS = {
    # Remora's approved look: a defined lash line with visible upper strands.
    'pronounced': dict(texture_size=[1024, 256], color_linear=[0.012, 0.009, 0.008], roughness=0.6,
                       specular=0.12, upper=_UPPER, lower=_LOWER),
    # Shorter, sparser and lighter: lid definition without a "made-up" read.
    'subtle': dict(texture_size=[1024, 256], color_linear=[0.016, 0.012, 0.010], roughness=0.6,
                   specular=0.1,
                   upper=dict(_UPPER, max_length_m=0.0027, strands=110, root_width_px=7, opacity=0.75,
                              min_length=0.5, root_line=0.12, root_line_opacity=0.6, angle_tip_deg=70),
                   lower=dict(_LOWER, max_length_m=0.0009, strands=20, opacity=0.35, root_line=0.15,
                              root_line_opacity=0.3)),
}
OCCLUSION_PRESETS = {
    'default': dict(color_linear=[0.03, 0.012, 0.01], offset_m=0.00015, dilate_m=0.001,
                    upper_strength=0.78, upper_falloff_m=0.0016, corner_strength=0.45,
                    corner_falloff_m=0.0016, lower_strength=0.18, lower_falloff_m=0.0006, max_alpha=0.8),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _preset(value, presets, label):
    """Resolve 'name' | {'preset': name, ...overrides} | full dict | None/'none'."""
    if value is None or value == 'none':
        return None
    if isinstance(value, str):
        value = {'preset': value}
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be a preset name, an object or "none"')
    value = copy.deepcopy(value)
    name = value.pop('preset', None)
    if name is None:
        return value
    if name not in presets:
        raise ValueError(f'Unknown {label} preset {name!r}; choose from {sorted(presets)}')
    merged = copy.deepcopy(presets[name])
    for key, item in value.items():
        if isinstance(item, dict) and isinstance(merged.get(key), dict):
            merged[key].update(item)
        else:
            merged[key] = item
    return merged


def resolve(config):
    """Return the fully expanded recipe the builder uses (also recorded in the receipt)."""
    if config.get('schema') != SCHEMA:
        raise ValueError(f'Eye detail needs schema {SCHEMA}')
    cfg = copy.deepcopy(config)
    cfg['lashes'] = _preset(cfg.get('lashes', 'pronounced'), LASH_PRESETS, 'lashes')
    cfg['occlusion'] = _preset(cfg.get('occlusion', 'default'), OCCLUSION_PRESETS, 'occlusion')
    if cfg['lashes'] is None and cfg['occlusion'] is None:
        raise ValueError('Nothing to add: lashes and occlusion are both "none"')
    return cfg


# ---------------------------------------------------------------- geometry helpers
def weld(points, decimals=6):
    keys, inverse = np.unique(np.round(points, decimals), axis=0, return_inverse=True)
    inverse = inverse.ravel()
    rep = np.zeros(len(keys), dtype=int)
    rep[inverse[::-1]] = np.arange(len(points))[::-1]          # first original vertex per weld
    return keys, inverse, rep


def boundary_loops(points, tri):
    """Closed boundary loops, found on unwelded indices then welded by position.

    Template heads can carry coincident duplicate lid layers
    welding first would
    close the aperture, so boundaries are detected per vertex stream first."""
    keys, inv, rep = weld(points)
    count = defaultdict(int)
    for f in tri:
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            count[(min(a, b), max(a, b))] += 1
    welded = {tuple(sorted((inv[a], inv[b]))) for (a, b), n in count.items() if n == 1 and inv[a] != inv[b]}
    adj = defaultdict(list)
    for a, b in welded:
        adj[a].append(b)
        adj[b].append(a)
    seen, loops = set(), []
    for start in adj:
        if start in seen or len(adj[start]) != 2:
            continue
        loop, prev, cur = [start], None, start
        while True:
            seen.add(cur)
            nxt = [n for n in adj[cur] if n != prev]
            if not nxt or len(adj[cur]) != 2:
                loop = None
                break
            prev, cur = cur, nxt[0]
            if cur == start:
                break
            loop.append(cur)
        if loop:
            loops.append(loop)
    return keys, rep, loops


def resample(poly, n):
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)]) / max(seg.sum(), 1e-12)
    t = np.linspace(0, 1, n)
    idx = np.clip(np.searchsorted(s, t, side='right') - 1, 0, len(poly) - 2)
    f = ((t - s[idx]) / np.maximum(s[idx + 1] - s[idx], 1e-12))[:, None]
    return idx, f, t


def seg_distance_2d(pts, poly):
    a, b = poly[:-1], poly[1:]
    ab = b - a
    ap = pts[:, None, :] - a[None]
    t = np.clip((ap * ab[None]).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-18)[None], 0, 1)
    closest = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(pts[:, None, :] - closest, axis=-1).min(1)


def point_in_poly(pts, poly):
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi, xj, yj = poly[i, 0], poly[i, 1], poly[j, 0], poly[j, 1]
        inside ^= ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-18) + xi)
        j = i
    return inside


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _trapezoid(y, x, axis=0):
    fn = getattr(np, 'trapezoid', None) or np.trapz
    return fn(y, x, axis=axis)


# ---------------------------------------------------------------- textures
def lash_texture(cfg, seed):
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)
    W, H = cfg['texture_size']
    img = Image.new('RGBA', (W * 2, H * 2), (0, 0, 0, 0))     # supersampled
    draw = ImageDraw.Draw(img)
    rgb = tuple(int(round(255 * c ** (1 / 2.2))) for c in cfg['color_linear'])
    # Top half: upper lashes (root at the middle row going up). Bottom half: lower lashes.
    for half, spec in (('upper', cfg['upper']), ('lower', cfg['lower'])):
        y0, y1 = (H * 2 // 2, 0) if half == 'upper' else (H * 2 // 2, H * 2)
        n = spec['strands']
        clumps = rng.uniform(0, 1, max(3, n // 5))
        for i in range(n):
            u = (i + rng.uniform(-0.4, 0.4)) / n
            c = clumps[np.argmin(np.abs(clumps - u))]
            u = u + (c - u) * spec.get('clump', 0.3)
            length = rng.uniform(spec['min_length'], 1.0)
            lean = rng.normal(0, spec.get('lean', 0.012))
            width = spec['root_width_px'] * 2 * rng.uniform(0.75, 1.15)
            steps = 12
            prev = None
            for k in range(steps + 1):
                t = k / steps * length
                x = (u + lean * t * t) * W * 2
                y = y0 + (y1 - y0) * t * 0.98
                if prev is not None:
                    w = max(1, int(round(width * (1 - t) ** 1.2)))
                    alpha = int(255 * spec['opacity'] * (1 - 0.55 * t))
                    draw.line([prev, (x, y)], fill=rgb + (alpha,), width=w)
                prev = (x, y)
    img = img.filter(ImageFilter.GaussianBlur(0.6)).resize((W, H), Image.LANCZOS)
    a = np.asarray(img).copy()
    rows = np.arange(H)
    for half, spec in (('upper', cfg['upper']), ('lower', cfg['lower'])):
        depth = spec.get('root_line', 0.0)
        if depth <= 0:
            continue
        t = (H / 2 - 1 - rows) / (H / 2) if half == 'upper' else (rows - H / 2) / (H / 2)
        ramp = np.where((t >= 0) & (t <= 1), np.clip(1 - t / depth, 0, 1) ** 1.5, 0)
        line = (255 * spec.get('root_line_opacity', 1.0) * ramp).astype(np.uint8)
        a[..., 3] = np.maximum(a[..., 3], line[:, None])
    a[..., :3] = rgb                                            # colour under alpha
    return Image.fromarray(a, 'RGBA')


def gradient_texture(color_linear, height=256):
    from PIL import Image
    rgb = [int(round(255 * c ** (1 / 2.2))) for c in color_linear]
    a = np.zeros((height, 4, 4), np.uint8)
    a[..., :3] = rgb
    a[..., 3] = np.linspace(0, 255, height).round().astype(np.uint8)[:, None]   # v=0 top row
    return Image.fromarray(a, 'RGBA')


def png(img):
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- builder
def build(raw, config):
    """Return (glb_bytes, receipt, {image_name: png_bytes})."""
    cfg = resolve(config)
    if cfg.get('source_sha256') != sha(raw):
        raise ValueError('Eye detail config must bind the exact source GLB (source_sha256)')
    doc, binary = read_glb(raw)
    buffer = bytearray(binary)
    meshes = {m.get('name'): i for i, m in enumerate(doc['meshes'])}
    for key in ('head_mesh', 'eye_mesh'):
        if cfg.get(key) not in meshes:
            raise ValueError(f'{key} {cfg.get(key)!r} is not a mesh in the source')
    head_i, eye_i = meshes[cfg['head_mesh']], meshes[cfg['eye_mesh']]
    head_node = next(n for n in doc['nodes'] if n.get('mesh') == head_i)
    eye_node = next(n for n in doc['nodes'] if n.get('mesh') == eye_i)
    if head_node.get('skin') is not None or eye_node.get('skin') is not None:
        raise ValueError('Skinned heads need a bone-bound route; this stage handles node-transformed heads')
    for k in ('translation', 'rotation', 'scale', 'matrix'):
        if head_node.get(k) != eye_node.get(k):
            raise ValueError('head and eye helpers must share a node transform')
    prefix = cfg.get('name_prefix', 'RAC')
    names_added = [f'{prefix}_eye_lashes', f'{prefix}_eye_occlusion']
    if any(n in meshes for n in names_added):
        raise ValueError('Eye detail is already present; start from the authority without it')
    head_mesh = doc['meshes'][head_i]
    skins = [p for p in head_mesh['primitives'] if doc['materials'][p['material']].get('name') == cfg['skin_material']]
    if len(skins) != 1:
        raise ValueError('skin_material must select exactly one head primitive')
    skin = skins[0]
    hp = accessor(doc, binary, skin['attributes']['POSITION'])
    htri = faces(doc, binary, skin)
    htargets = [accessor(doc, binary, t['POSITION']) for t in skin.get('targets', [])]
    eye_prim = doc['meshes'][eye_i]['primitives'][0]
    ep = accessor(doc, binary, eye_prim['attributes']['POSITION'])
    en = accessor(doc, binary, eye_prim['attributes']['NORMAL'])
    etri = faces(doc, binary, eye_prim)
    etargets = [accessor(doc, binary, t['POSITION']) for t in eye_prim.get('targets', [])]
    weights = head_mesh.get('weights', [0.0] * len(htargets))
    names = head_mesh.get('extras', {}).get('targetNames', [])
    if len(htargets) != len(weights) or len(etargets) != len(weights):
        raise ValueError('head/eye morph target counts must match')
    fwd = np.array(cfg.get('forward', [0, 0, 1]), float)
    up = np.array(cfg.get('up', [0, 1, 0]), float)
    side = np.cross(up, fwd)
    S = cfg.get('scale_to_local') or 1.0 / float(np.mean(head_node.get('scale', [1, 1, 1])))
    lc, oc = cfg['lashes'], cfg['occlusion']
    min_forward = cfg.get('margin_min_forward_m', 0.001)

    keys, rep, loops = boundary_loops(hp, htri)
    _, hinv, _ = weld(hp)
    hn = accessor(doc, binary, skin['attributes']['NORMAL'])
    wnormal = np.zeros((len(keys), 3))
    np.add.at(wnormal, hinv, hn)
    wnormal = unit(wnormal)
    report = dict(schema=RECEIPT, source_sha256=sha(raw), eyes=[])
    lash_pos, lash_uv, lash_idx, lash_tg = [], [], [], [[] for _ in weights]
    occ_pos, occ_uv, occ_nrm, occ_idx, occ_tg = [], [], [], [], [[] for _ in weights]

    for sign in (-1, 1):
        sel = np.where(np.sign(ep @ side) == sign)[0]
        if not len(sel):
            raise ValueError('Expected one eyeball helper on each side of the head')
        centre = ep[sel].mean(0)
        def flat(v):
            return v - np.outer(v @ fwd, fwd) if v.ndim > 1 else v - (v @ fwd) * fwd
        cand = [L for L in loops if 10 <= len(L) <= 80 and (keys[L].mean(0) - centre) @ fwd > 0]
        if not cand:
            raise ValueError('No eyelid aperture (closed boundary loop) in front of an eyeball helper')
        best = min(cand, key=lambda L: np.linalg.norm(flat(keys[L].mean(0) - centre)))
        loop = np.array(best)
        P = keys[loop]
        if np.linalg.norm(flat(P.mean(0) - centre)) > cfg.get('max_aperture_offset', 0.012):
            raise ValueError('eye aperture loop not found near eyeball helper')
        lat = P @ side
        inner = int(np.argmin(np.abs(lat)))
        outer = int(np.argmax(np.abs(lat)))
        order1 = [(inner + k) % len(loop) for k in range((outer - inner) % len(loop) + 1)]
        order2 = [(inner - k) % len(loop) for k in range((inner - outer) % len(loop) + 1)]
        c1, c2 = P[order1], P[order2]
        upper_o, lower_o = (order1, order2) if (c1 @ up).mean() > (c2 @ up).mean() else (order2, order1)
        apc = P.mean(0)
        eye_rec = dict(side='anatomical_' + ('left' if sign > 0 else 'right') + '_by_+side',
                       aperture_vertices=len(loop), aperture_centre=apc.tolist(),
                       eyeball_centre=centre.tolist(),
                       aperture_width=float(np.ptp(lat)), aperture_height=float(np.ptp(P @ up)))

        for which, chain_o, spec in ((('upper', upper_o, lc['upper']), ('lower', lower_o, lc['lower']))
                                     if lc else ()):
            chain = P[chain_o]
            n = spec['columns']
            idx, f, s = resample(chain, n)
            root = chain[idx] * (1 - f) + chain[np.minimum(idx + 1, len(chain) - 1)] * f
            radial = root - apc
            radial -= np.outer(radial @ fwd, fwd)
            radial = unit(radial)
            vdir = up if which == 'upper' else -up
            radial = unit(radial * 0.6 + vdir * 0.4)
            flare = (np.sign(root @ side - apc @ side))[:, None] * side[None] * (s ** 2)[:, None] * spec['outer_flare']
            prof = spec['inner_fraction'] + (1 - spec['inner_fraction']) * np.exp(-((s - spec['peak']) / spec['spread']) ** 2)
            prof *= np.where(s > spec['peak'], 1 - spec['outer_drop'] * (s - spec['peak']) / (1 - spec['peak']), 1)
            prof *= np.clip(np.minimum(s, 1 - s) / spec['end_taper'], 0.25, 1)
            L = spec['max_length_m'] * S * prof
            # The lid is a deep tube on many acquired heads: root each lash on the nearest
            # vertex (radially) whose surface has turned to face forward, in front of the
            # aperture edge. Roots on the edge itself are hidden inside the lid.
            margin_vid = np.empty(n, int)
            for c in range(n):
                rel = keys - root[c]
                along = rel @ radial[c]
                lateral = np.abs(rel @ unit(np.cross(radial[c], fwd)))
                for widen in (1, 2, 3, 4):
                    band = ((along > -0.0003 * S) & (along < spec['margin_search_m'] * S)
                            & (lateral < spec['margin_lateral_m'] * S * widen)
                            & (wnormal @ fwd >= spec['margin_facing']) & (rel @ fwd > min_forward * S))
                    cand_ids = np.where(band)[0]
                    if len(cand_ids):
                        break
                else:
                    raise ValueError('no lid margin found beyond aperture')
                margin_vid[c] = cand_ids[np.argmin(along[cand_ids])]
            margin = keys[margin_vid]
            k = max(1, int(spec.get('margin_smooth', 1)))
            pad = np.pad(margin, ((k, k), (0, 0)), mode='edge')
            root = np.stack([pad[i:i + 2 * k + 1].mean(0) for i in range(n)])
            base = root + fwd * spec['root_forward_m'] * S + radial * spec['root_out_m'] * S
            rows = spec['rows']
            start = len(lash_pos)
            for r in range(rows + 1):
                t = r / rows
                ts = np.linspace(0, t, 8)
                ang = np.radians(spec['angle_root_deg'] + (spec['angle_tip_deg'] - spec['angle_root_deg']) * ts)
                step = (np.cos(ang)[:, None, None] * fwd[None, None] + np.sin(ang)[:, None, None] * radial[None]
                        + flare[None] * ts[:, None, None])
                off = _trapezoid(step, ts, axis=0) if t > 0 else np.zeros_like(root)
                pos = base + off * L[:, None]
                for c in range(n):
                    lash_pos.append(pos[c])
                    v = 0.5 - 0.5 * t if which == 'upper' else 0.5 + 0.5 * t
                    lash_uv.append((s[c] * spec['u_repeat'] + (0.37 if sign > 0 else 0.0), v))
                    for kk, tg in enumerate(htargets):      # follow the rooted lid vertex
                        lash_tg[kk].append(tg[rep[margin_vid[c]]])
            for r in range(rows):
                for c in range(n - 1):
                    a = start + r * n + c
                    b = a + 1
                    d = a + n
                    e = d + 1
                    lash_idx += [a, b, e, a, e, d]
            eye_rec[f'{which}_lash_columns'] = n
        if oc:
            upper2 = np.stack([P[upper_o] @ side, P[upper_o] @ up], 1)
            lower2 = np.stack([P[lower_o] @ side, P[lower_o] @ up], 1)
            poly2 = np.stack([P @ side, P @ up], 1)
            e2 = np.stack([ep[sel] @ side, ep[sel] @ up], 1)
            frontish = (ep[sel] - centre) @ fwd > 0
            near = point_in_poly(e2, poly2) | (seg_distance_2d(e2, np.vstack([poly2, poly2[:1]])) < oc['dilate_m'] * S)
            keep = sel[frontish & near]
            keepset = {int(v): i for i, v in enumerate(keep)}
            k2 = np.stack([ep[keep] @ side, ep[keep] @ up], 1)
            du, dl = seg_distance_2d(k2, upper2), seg_distance_2d(k2, lower2)
            corners = np.stack([upper2[0], upper2[-1]])
            dc = np.linalg.norm(k2[:, None] - corners[None], axis=-1).min(1)
            alpha = (oc['upper_strength'] * np.exp(-du / (oc['upper_falloff_m'] * S))
                     + oc['corner_strength'] * np.exp(-dc / (oc['corner_falloff_m'] * S))
                     + oc['lower_strength'] * np.exp(-dl / (oc['lower_falloff_m'] * S)))
            alpha = np.clip(alpha, 0, oc['max_alpha'])
            start = len(occ_pos)
            for j, v in enumerate(keep):
                occ_pos.append(ep[v] + en[v] * oc['offset_m'] * S)
                occ_nrm.append(en[v])
                occ_uv.append((0.5, 0.5 / 256 + alpha[j] * 255 / 256))
                for kk, tg in enumerate(etargets):
                    occ_tg[kk].append(tg[v])
            tri_keep = [t for t in etri if all(int(x) in keepset for x in t)]
            for t in tri_keep:
                occ_idx += [start + keepset[int(x)] for x in t]
            if not tri_keep:
                raise ValueError('No eyeball triangles inside the aperture for the occlusion shell')
            eye_rec.update(occlusion_vertices=len(keep), occlusion_triangles=len(tri_keep),
                           occlusion_max_alpha=float(alpha.max()))
        report['eyes'].append(eye_rec)

    images = doc.setdefault('images', [])
    textures = doc.setdefault('textures', [])
    samplers = doc.setdefault('samplers', [])
    mats = doc['materials']
    pngs = {}

    def add_image(name, img, sampler):
        data = png(img)
        pngs[name] = data
        buffer.extend(b'\0' * (-len(buffer) % 4))
        doc['bufferViews'].append(dict(buffer=0, byteOffset=len(buffer), byteLength=len(data)))
        buffer.extend(data)
        images.append(dict(name=name, mimeType='image/png', bufferView=len(doc['bufferViews']) - 1))
        textures.append(dict(source=len(images) - 1, sampler=sampler))
        return len(textures) - 1

    def add_mesh(name, pos, nrm, uv, idx, tgs, mat):
        prim = dict(attributes=dict(POSITION=append_accessor(doc, buffer, pos, 'VEC3'),
                                    NORMAL=append_accessor(doc, buffer, nrm, 'VEC3'),
                                    TEXCOORD_0=append_accessor(doc, buffer, uv, 'VEC2')),
                    indices=append_accessor(doc, buffer, np.asarray(idx, np.uint32), 'SCALAR', 5125, 34963),
                    material=mat, mode=4)
        if tgs:
            prim['targets'] = [dict(POSITION=append_accessor(doc, buffer, np.asarray(t, np.float32), 'VEC3'))
                               for t in tgs]
        mesh = dict(name=name, primitives=[prim])
        if tgs:
            mesh.update(weights=list(weights), extras=dict(targetNames=list(names)))
        doc['meshes'].append(mesh)
        node = {k: head_node[k] for k in ('translation', 'rotation', 'scale', 'matrix') if k in head_node}
        node.update(name=name, mesh=len(doc['meshes']) - 1)
        doc['nodes'].append(node)
        doc['scenes'][doc.get('scene', 0)]['nodes'].append(len(doc['nodes']) - 1)

    clamp = next((i for i, s in enumerate(samplers) if s.get('wrapS') == 33071 and s.get('wrapT') == 33071), None)
    if clamp is None:
        samplers.append(dict(magFilter=9729, minFilter=9987, wrapS=33071, wrapT=33071))
        clamp = len(samplers) - 1
    if lc:
        LP = np.array(lash_pos, float)
        LI = np.array(lash_idx).reshape(-1, 3)
        fn = np.cross(LP[LI[:, 1]] - LP[LI[:, 0]], LP[LI[:, 2]] - LP[LI[:, 0]])
        LN = np.zeros_like(LP)
        for k in range(3):
            np.add.at(LN, LI[:, k], fn)
        LN = unit(LN)
        LN[(LN @ fwd) < 0] *= -1
        samplers.append(dict(magFilter=9729, minFilter=9987, wrapS=10497, wrapT=33071))
        repeat_u = len(samplers) - 1
        lash_tex = add_image('RAC_eye_lashes', lash_texture(lc, cfg.get('seed', 73)), repeat_u)
    if oc:
        occ_tex = add_image('RAC_eye_occlusion', gradient_texture(oc['color_linear']), clamp)
    if lc:
        mats.append(dict(name='RAC_Eye_Lashes', doubleSided=True, alphaMode='BLEND',
                         pbrMetallicRoughness=dict(baseColorTexture=dict(index=lash_tex), baseColorFactor=[1, 1, 1, 1],
                                                   metallicFactor=0, roughnessFactor=lc['roughness']),
                         extensions=dict(KHR_materials_specular=dict(specularFactor=lc['specular']))))
        lash_mat = len(mats) - 1
    if oc:
        mats.append(dict(name='RAC_Eye_Occlusion', doubleSided=False, alphaMode='BLEND',
                         pbrMetallicRoughness=dict(baseColorTexture=dict(index=occ_tex), baseColorFactor=[1, 1, 1, 1],
                                                   metallicFactor=0, roughnessFactor=1),
                         extensions=dict(KHR_materials_specular=dict(specularFactor=0))))
        occ_mat = len(mats) - 1
    used = set(doc.get('extensionsUsed', []))
    if 'KHR_materials_specular' not in used:
        doc['extensionsUsed'] = sorted(used | {'KHR_materials_specular'})
    if lc:
        add_mesh(names_added[0], LP, LN, lash_uv, lash_idx, lash_tg, lash_mat)
    if oc:
        add_mesh(names_added[1], np.array(occ_pos), np.array(occ_nrm), occ_uv, occ_idx, occ_tg, occ_mat)
    doc['buffers'][0]['byteLength'] = len(buffer)
    result = write_glb(doc, buffer)
    report.update(output_sha256=sha(result), resolved_config=cfg,
                  lash_vertices=len(lash_pos), occlusion_vertices=len(occ_pos),
                  added_meshes=[n for n, on in zip(names_added, (lc, oc)) if on],
                  image_sha256={k: sha(v) for k, v in pngs.items()},
                  original_binary_prefix_retained=bytes(buffer[:len(binary)]) == binary,
                  visual_acceptance='pending', production_ready=False)
    verify_append_only(raw, result)
    report['original_json_entries_identical'] = True
    return result, report, pngs


def verify_append_only(source_raw, result_raw):
    """Raise unless every original JSON entry and binary byte survives unchanged."""
    d, b = read_glb(source_raw)
    dn, bn = read_glb(result_raw)
    if bn[:len(b)] != b:
        raise ValueError('Original binary is not an exact prefix of the result')
    for key in ('accessors', 'bufferViews', 'meshes', 'materials', 'nodes', 'images', 'textures', 'samplers',
                'skins', 'animations'):
        old = d.get(key, [])
        if dn.get(key, [])[:len(old)] != old:
            raise ValueError(f'Original {key} changed')
    old_nodes = d['scenes'][d.get('scene', 0)]['nodes']
    if dn['scenes'][dn.get('scene', 0)]['nodes'][:len(old_nodes)] != old_nodes:
        raise ValueError('Original scene roots changed')
