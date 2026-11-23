"""Eye detail appends lashes/occlusion that follow the head's morphs and change nothing else."""

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler import eye_detail  # noqa: E402
from reference_asset_compiler.polish_glb import accessor, append_accessor, read_glb, write_glb  # noqa: E402
from reference_asset_compiler.polish_workflow import ALLOWED, MUTATES  # noqa: E402
from reference_asset_compiler.stages import STAGES  # noqa: E402

EYE_Y, EYE_Z, EYE_X, RADIUS = 1.374, 0.099, 0.03, 0.011
LID_RAISE = 0.001


def _head():
    xs, ys = np.arange(-0.06, 0.0601, 0.002), np.arange(1.34, 1.4101, 0.002)
    grid = np.array([(x, y, EYE_Z + RADIUS) for y in ys for x in xs])
    nx = len(xs)
    tris = []
    for j in range(len(ys) - 1):
        for i in range(nx - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(((cx - s * EYE_X) / 0.011) ** 2 + ((cy - EYE_Y) / 0.004) ** 2 < 1 for s in (-1, 1)):
                continue                                             # eyelid aperture
            a = j * nx + i
            tris += [(a, a + 1, a + nx + 1), (a, a + nx + 1, a + nx)]
    normals = np.tile([0.0, 0.0, 1.0], (len(grid), 1))
    morph = np.zeros_like(grid)
    morph[grid[:, 1] > EYE_Y, 1] = LID_RAISE                         # "blink" lifts the upper face
    return grid, normals, np.array(tris), morph


def _eyes():
    pts, tris = [], []
    rings, segs = 12, 16
    for s in (-1, 1):
        base = len(pts)
        for r in range(rings + 1):
            th = np.pi * r / rings
            for k in range(segs):
                ph = 2 * np.pi * k / segs
                d = np.array([np.sin(th) * np.cos(ph), np.cos(th), np.sin(th) * np.sin(ph)])
                pts.append(np.array([s * EYE_X, EYE_Y, EYE_Z]) + RADIUS * d)
        for r in range(rings):
            for k in range(segs):
                a, b = base + r * segs + k, base + r * segs + (k + 1) % segs
                tris += [(a, b, b + segs), (a, b + segs, a + segs)]
    pts = np.array(pts)
    centres = np.where(pts[:, :1] > 0, [[EYE_X, EYE_Y, EYE_Z]], [[-EYE_X, EYE_Y, EYE_Z]])
    return pts, (pts - centres) / RADIUS, np.array(tris)


def fixture():
    doc = dict(asset={'version': '2.0'}, buffers=[{'byteLength': 0}], bufferViews=[], accessors=[],
               materials=[dict(name='skin'), dict(name='eyes')], meshes=[], nodes=[], scenes=[{'nodes': []}],
               extensionsUsed=['KHR_materials_specular'])
    buf = bytearray()
    hp, hn, ht, hm = _head()
    ep, en, et = _eyes()
    for name, (p, n, t, m), mat in (('head', (hp, hn, ht, hm), 0), ('eyes', (ep, en, et, np.zeros_like(ep)), 1)):
        prim = dict(attributes=dict(POSITION=append_accessor(doc, buf, p, 'VEC3'),
                                    NORMAL=append_accessor(doc, buf, n, 'VEC3')),
                    indices=append_accessor(doc, buf, t.astype(np.uint32), 'SCALAR', 5125, 34963),
                    material=mat, targets=[dict(POSITION=append_accessor(doc, buf, m, 'VEC3'))])
        doc['meshes'].append(dict(name=name, primitives=[prim], weights=[0.0], extras=dict(targetNames=['blink'])))
        doc['nodes'].append(dict(name=name, mesh=len(doc['meshes']) - 1))
        doc['scenes'][0]['nodes'].append(len(doc['nodes']) - 1)
    doc['buffers'][0]['byteLength'] = len(buf)
    return write_glb(doc, buf)


def config(raw, **extra):
    cfg = dict(schema=eye_detail.SCHEMA, source_sha256=hashlib.sha256(raw).hexdigest(), head_mesh='head',
               eye_mesh='eyes', skin_material='skin', margin_min_forward_m=-0.001, max_aperture_offset=0.006)
    cfg.update(extra)
    return cfg


def lash_mesh(doc, binary, name='RAC_eye_lashes'):
    mesh = next(m for m in doc['meshes'] if m['name'] == name)
    prim = mesh['primitives'][0]
    return accessor(doc, binary, prim['attributes']['POSITION']), accessor(doc, binary, prim['targets'][0]['POSITION'])


def test_append_only_lashes_and_occlusion_follow_morphs():
    raw = fixture()
    out, receipt, images = eye_detail.build(raw, config(raw))
    eye_detail.verify_append_only(raw, out)
    doc, binary = read_glb(out)
    assert [m['name'] for m in doc['meshes']] == ['head', 'eyes', 'RAC_eye_lashes', 'RAC_eye_occlusion']
    assert receipt['original_binary_prefix_retained'] and receipt['output_sha256'] == hashlib.sha256(out).hexdigest()
    assert set(images) == {'RAC_eye_lashes', 'RAC_eye_occlusion'}
    assert all(m['weights'] == [0.0] and m['extras']['targetNames'] == ['blink'] for m in doc['meshes'][2:])
    pos, morph = lash_mesh(doc, binary)
    upper = pos[:, 1] > EYE_Y + 0.003
    assert upper.any() and np.allclose(morph[upper], [0, LID_RAISE, 0])   # upper lashes ride the lid
    assert np.allclose(morph[pos[:, 1] < EYE_Y - 0.004], 0)              # lower lashes do not
    assert (pos[:, 2] > EYE_Z + RADIUS).all()                             # lashes sit in front of the lid
    assert len(receipt['eyes']) == 2 and all(e['occlusion_triangles'] > 0 for e in receipt['eyes'])


def test_presets_scale_the_look_and_none_keeps_only_occlusion():
    raw = fixture()
    reach = {}
    for preset in ('pronounced', 'subtle'):
        doc, binary = read_glb(eye_detail.build(raw, config(raw, lashes=preset))[0])
        reach[preset] = np.ptp(lash_mesh(doc, binary)[0][:, 2])
    assert reach['subtle'] < reach['pronounced']
    out, receipt, images = eye_detail.build(raw, config(raw, lashes='none'))
    doc, _ = read_glb(out)
    assert [m['name'] for m in doc['meshes']][2:] == ['RAC_eye_occlusion'] and set(images) == {'RAC_eye_occlusion'}
    out, _, _ = eye_detail.build(raw, config(raw, lashes={'preset': 'subtle', 'upper': {'max_length_m': 0.001}}))
    doc, binary = read_glb(out)
    assert np.ptp(lash_mesh(doc, binary)[0][:, 2]) < reach['subtle']


def test_deterministic_and_named_by_prefix():
    raw = fixture()
    a = eye_detail.build(raw, config(raw, name_prefix='Hero'))[0]
    assert a == eye_detail.build(raw, config(raw, name_prefix='Hero'))[0]
    assert {'Hero_eye_lashes', 'Hero_eye_occlusion'} <= {m['name'] for m in read_glb(a)[0]['meshes']}


@pytest.mark.parametrize('change, message', [
    (dict(source_sha256='0' * 64), 'bind the exact source'),
    (dict(lashes='glam'), 'Unknown lashes preset'),
    (dict(lashes='none', occlusion='none'), 'Nothing to add'),
    (dict(schema='other'), 'schema'),
    (dict(head_mesh='missing'), 'not a mesh'),
])
def test_refuses_unbound_or_unknown_requests(change, message):
    raw = fixture()
    with pytest.raises(ValueError, match=message):
        eye_detail.build(raw, config(raw, **change))


def test_refuses_to_stack_on_itself():
    raw = fixture()
    out = eye_detail.build(raw, config(raw))[0]
    with pytest.raises(ValueError, match='already present'):
        eye_detail.build(out, config(out))


def test_registered_as_a_mutating_polish_stage():
    assert STAGES['eye-detail']['script'] == 'scripts/eye_detail.py'
    assert 'eye-detail' in ALLOWED and 'eye-detail' in MUTATES
