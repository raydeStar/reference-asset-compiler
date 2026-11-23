"""Exercise real bytes, missing faces and texture frames, not just command construction."""
from __future__ import annotations

import copy
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from reference_asset_compiler.io import sha256_file
from reference_asset_compiler.polish_glb import accessor, append_accessor, faces, read_glb, write_glb
from reference_asset_compiler.reference_guides import capture_guides
from reference_asset_compiler.surface_finish import inspect_surface, repair_bounds, restore_surface

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from repack_surface import repack
from surface_atlas import read_image
from project_reference_patch import sample
from test_material_sweep import swatch


def named_swatch(root):
    source, _ = swatch(root)
    doc, binary = read_glb(source.read_bytes())
    doc['meshes'][0]['name'] = 'Coat'
    source.write_bytes(write_glb(doc, binary))
    return source


def hole_fixture(root):
    source = named_swatch(root)
    doc, binary = read_glb(source.read_bytes())
    buffer = bytearray(binary)
    pr = doc['meshes'][0]['primitives'][0]
    p = np.array([[0,0,0], [1,0,0], [1,1,0], [0,1,0], [.5,.5,1]], 'f4')
    uv = p[:, :2]
    tri = np.array([[0,2,1], [0,3,2], [0,1,4], [1,2,4], [2,3,4], [3,0,4]])
    pr['attributes'] = dict(POSITION=append_accessor(doc, buffer, p, 'VEC3'),
        NORMAL=append_accessor(doc, buffer, np.tile([0,0,-1], (5,1)), 'VEC3'),
        TEXCOORD_0=append_accessor(doc, buffer, uv, 'VEC2'),
        JOINTS_0=append_accessor(doc, buffer, np.zeros((5,4)), 'VEC4', 5123),
        WEIGHTS_0=append_accessor(doc, buffer, np.tile([1,0,0,0], (5,1)), 'VEC4'))
    delta = np.tile([.01,.02,.03], (5,1))
    pr['targets'] = [dict(POSITION=append_accessor(doc, buffer, delta, 'VEC3'))]
    pr['indices'] = append_accessor(doc, buffer, tri.ravel(), 'SCALAR', 5125, 34963)
    doc['buffers'][0]['byteLength'] = len(buffer)
    donor = root/'donor.glb'
    donor.write_bytes(write_glb(doc, buffer))
    pr['indices'] = append_accessor(doc, buffer, tri[1:].ravel(), 'SCALAR', 5125, 34963)
    doc['buffers'][0]['byteLength'] = len(buffer)
    source.write_bytes(write_glb(doc, buffer))
    cfg = dict(schema='reference-asset-compiler.restore-surface-recipe.v1',
        source_sha256=sha256_file(source), acquisition_provenance='Synthetic acquired-surface test only',
        donor=donor.name, donor_sha256=sha256_file(donor), mesh='Coat', material='Hand-painted',
        donor_faces=[0], bounds=[[-.01,-.01,-.01], [1.01,1.01,.01]], expected_boundary_edges=3,
        patch_material='Restored cloth')
    recipe = root/'restore.json'
    recipe.write_text(json.dumps(cfg))
    return source, recipe


def test_bounds_repair_keeps_binary_and_rejects_nan(tmp_path):
    source = named_swatch(tmp_path)
    original, binary = read_glb(source.read_bytes())
    output, receipt = repair_bounds(source)
    doc, new = read_glb(output)
    assert new == binary and receipt['binary_byte_identical']
    assert doc['accessors'][0]['min'] == [0,0,0]
    stripped = copy.deepcopy(doc)
    for change in receipt['changes']:
        stripped['accessors'][change['accessor']].pop('min')
        stripped['accessors'][change['accessor']].pop('max')
    assert stripped == original
    damaged = bytearray(binary)
    damaged[:4] = np.array([np.nan], '<f4').tobytes()
    source.write_bytes(write_glb(original, damaged))
    with pytest.raises(ValueError, match='Nonfinite'):
        repair_bounds(source)


def test_accessor_handles_stride_sparse_and_checks_view_limits():
    data = bytearray(np.array([[1,2,3,99], [4,5,6,99]], '<f4').tobytes())
    data.extend(np.array([1], '<u4').tobytes())
    data.extend(np.array([7,8,9], '<f4').tobytes())
    doc = dict(buffers=[dict(byteLength=len(data))], bufferViews=[
        dict(buffer=0,byteOffset=0,byteLength=32,byteStride=16),
        dict(buffer=0,byteOffset=32,byteLength=4), dict(buffer=0,byteOffset=36,byteLength=12)],
        accessors=[dict(bufferView=0,componentType=5126,type='VEC3',count=2,
            sparse=dict(count=1,indices=dict(bufferView=1,componentType=5125),values=dict(bufferView=2)))])
    np.testing.assert_array_equal(accessor(doc, data, 0), [[1,2,3],[7,8,9]])
    doc['bufferViews'][0]['byteLength'] = 24
    with pytest.raises(ValueError, match='buffer view'):
        accessor(doc, data, 0)


def test_restore_closes_hole_and_inherits_weights_and_morphs(tmp_path):
    source, recipe = hole_fixture(tmp_path)
    before, binary = read_glb(source.read_bytes())
    assert inspect_surface(source)['primitives'][0]['topology']['boundary_edges'] == 3
    raw, receipt = restore_surface(source, recipe)
    assert raw == restore_surface(source, recipe)[0]
    doc, new = read_glb(raw)
    assert new.startswith(binary) and receipt['closed_boundary_edges'] == 3
    assert before['meshes'][0]['primitives'][0] == doc['meshes'][0]['primitives'][0]
    patch = doc['meshes'][0]['primitives'][1]
    np.testing.assert_array_equal(accessor(doc, new, patch['attributes']['WEIGHTS_0']), [[1,0,0,0]]*3)
    np.testing.assert_allclose(accessor(doc, new, patch['targets'][0]['POSITION']), [[.01,.02,.03]]*3)
    assert doc['nodes'] == before['nodes'] and doc['materials'][:2] == before['materials']


@pytest.mark.parametrize('fault', ['source', 'donor', 'faces', 'bounds', 'border', 'duplicate_material'])
def test_restore_refuses_unbound_or_overbroad_repair(tmp_path, fault):
    source, recipe = hole_fixture(tmp_path)
    cfg = json.loads(recipe.read_text())
    if fault in ('source', 'donor'):
        cfg[fault+'_sha256'] = '0'*64
    elif fault == 'faces':
        cfg['donor_faces'] = [0,1]
    elif fault == 'bounds':
        cfg['bounds'][1][0] = .1
    elif fault == 'border':
        cfg['expected_boundary_edges'] = 4
    else:
        cfg['patch_material'] = 'Hand-painted'
    recipe.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        restore_surface(source, recipe)


def test_guides_are_deterministic_and_pixel_center_registered(tmp_path):
    source = named_swatch(tmp_path)
    cfg = dict(schema='reference-asset-compiler.reference-guides-recipe.v1',
        source_sha256=sha256_file(source), acquisition_provenance='Synthetic mapping registration test',
        mesh='Coat',resolution=64, views=[dict(name='front', center=[.006,.006,0],axis=[0,0,1],width=.012)])
    recipe = tmp_path/'guide.json'
    recipe.write_text(json.dumps(cfg))
    a = capture_guides(source, tmp_path/'a', recipe)
    b = capture_guides(source, tmp_path/'b', recipe)
    assert a == b
    assert (tmp_path/'a/front.npz').read_bytes() == (tmp_path/'b/front.npz').read_bytes()
    guide = np.load(tmp_path/'a/front.npz')
    assert (guide['hit'] >= 0).all()
    assert np.max(abs(guide['depth'])) == 0
    np.testing.assert_allclose(guide['bary'].sum(2), 1)
    image = np.asarray(Image.open(tmp_path/'a/front.png'))
    assert image.min() > 100 and image.max() < 190


def test_repack_transports_triangle_data_and_isolates_material(tmp_path):
    pytest.importorskip('xatlas')
    source = named_swatch(tmp_path)
    doc, binary = read_glb(source.read_bytes())
    buffer = bytearray(binary)
    pr = doc['meshes'][0]['primitives'][0]
    pr['attributes']['WEIGHTS_0'] = append_accessor(doc, buffer, [[1,0,0,0]]*4, 'VEC4')
    pr['targets'] = [dict(POSITION=append_accessor(doc, buffer, [[0,0,.01]]*4, 'VEC3'))]
    doc['buffers'][0]['byteLength'] = len(buffer)
    source.write_bytes(write_glb(doc, buffer))
    recipe = tmp_path/'repack.json'
    recipe.write_text(json.dumps(dict(schema='reference-asset-compiler.repack-surface-recipe.v1',
        source_sha256=sha256_file(source),acquisition_provenance='Synthetic transport test',
        mesh='Coat',material='Hand-painted',new_material='Dense cloth',resolution=64,padding=2)))
    raw, report = repack(source, recipe)
    out, binary_out = read_glb(raw)
    after = out['meshes'][0]['primitives'][0]
    oldtri, newtri = faces(doc, buffer, pr), faces(out, binary_out, after)
    for key in ('POSITION','NORMAL','WEIGHTS_0'):
        np.testing.assert_array_equal(accessor(doc, buffer, pr['attributes'][key])[oldtri],
                                      accessor(out, binary_out, after['attributes'][key])[newtri])
    np.testing.assert_array_equal(accessor(doc, buffer, pr['targets'][0]['POSITION'])[oldtri],
                                  accessor(out, binary_out, after['targets'][0]['POSITION'])[newtri])
    assert out['materials'][:2] == doc['materials'] and report['normal_frames_transported']
    assert 'min' in out['accessors'][after['attributes']['POSITION']]


def test_guides_allow_explicit_opaque_subset_but_never_silently_skip_transparency(tmp_path):
    source=named_swatch(tmp_path)
    doc,binary=read_glb(source.read_bytes())
    copy_pr=copy.deepcopy(doc['meshes'][0]['primitives'][0])
    copy_pr['material']=len(doc['materials'])
    doc['materials'].append(dict(name='Glass',alphaMode='BLEND'))
    doc['meshes'][0]['primitives'].append(copy_pr)
    source.write_bytes(write_glb(doc,binary))
    cfg=dict(schema='reference-asset-compiler.reference-guides-recipe.v1',source_sha256=sha256_file(source),
        acquisition_provenance='Synthetic explicit guide scope test',mesh='Coat',resolution=32,
        views=[dict(name='front',center=[.006,.006,0],axis=[0,0,1],width=.012)])
    recipe=tmp_path/'guide.json'
    recipe.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='Transparent'):
        capture_guides(source,tmp_path/'refused',recipe)
    cfg['materials']=['Hand-painted']
    recipe.write_text(json.dumps(cfg))
    receipt=capture_guides(source,tmp_path/'scoped',recipe)
    assert receipt['selected_materials']==['Hand-painted'] and 'Glass' in receipt['omitted_materials']
    assert (np.load(tmp_path/'scoped/front.npz')['hit']>=0).all()
    cfg['materials']=['Misspelled']
    recipe.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='subset'):
        capture_guides(source,tmp_path/'wrong',recipe)


def test_repack_normal_map_keeps_its_object_space_direction(tmp_path):
    pytest.importorskip('xatlas')
    source = named_swatch(tmp_path)
    doc, binary = read_glb(source.read_bytes())
    buffer = bytearray(binary)
    pr = doc['meshes'][0]['primitives'][0]
    pr['attributes']['TANGENT'] = append_accessor(doc, buffer, [[1,0,0,-1]]*4, 'VEC4')
    pixel = np.rint((np.array([.4,.2,np.sqrt(.8)])*.5+.5)*255).astype('u1')
    stream = io.BytesIO()
    Image.fromarray(np.tile(pixel,(16,16,1))).save(stream,format='PNG')
    encoded=stream.getvalue()
    buffer.extend(b'\0'*(-len(buffer)%4))
    doc['bufferViews'].append(dict(buffer=0,byteOffset=len(buffer),byteLength=len(encoded)))
    buffer.extend(encoded)
    doc['images']=[dict(bufferView=len(doc['bufferViews'])-1,mimeType='image/png')]
    doc['textures']=[dict(source=0)]
    doc['materials'][0]['normalTexture']=dict(index=0)
    doc['buffers'][0]['byteLength']=len(buffer)
    source.write_bytes(write_glb(doc,buffer))
    recipe=tmp_path/'normal-repack.json'
    recipe.write_text(json.dumps(dict(schema='reference-asset-compiler.repack-surface-recipe.v1',
        source_sha256=sha256_file(source),acquisition_provenance='Synthetic normal-frame test',
        mesh='Coat',material='Hand-painted',new_material='Repacked',resolution=128,padding=4)))
    raw,_=repack(source,recipe)
    out,new=read_glb(raw)
    p=out['meshes'][0]['primitives'][0]
    tri=faces(out,new,p)
    a=p['attributes']
    uv=accessor(out,new,a['TEXCOORD_0'])[tri].mean(1)
    t=accessor(out,new,a['TANGENT'])[tri].mean(1)
    n=accessor(out,new,a['NORMAL'])[tri].mean(1)
    tex=np.asarray(read_image(out,new,out['materials'][p['material']]['normalTexture']))
    mapped=sample(tex,uv)[:,:3]/127.5-1
    mapped/=np.linalg.norm(mapped,axis=1,keepdims=True)
    world=t[:,:3]*mapped[:,:1]+np.cross(n,t[:,:3])*t[:,3:]*mapped[:,1:2]+n*mapped[:,2:3]
    expected=pixel.astype(float)/127.5-1
    expected[1]*=-1
    expected/=np.linalg.norm(expected)
    assert np.min(world@expected)>.9999


@pytest.mark.parametrize('tiny',[True,False])
def test_collapsed_uvs_are_isolated_only_for_tiny_surface_area(tmp_path,monkeypatch,tiny):
    xatlas=pytest.importorskip('xatlas')
    source=named_swatch(tmp_path)
    doc,binary=read_glb(source.read_bytes())
    buf=bytearray(binary)
    pr=doc['meshes'][0]['primitives'][0]
    scale=1e-6 if tiny else .01
    p=np.array([[0,0,0],[.012,0,0],[.012,.012,0],[0,.012,0],[.02,0,0],[.02+scale,0,0],[.02,scale,0]],'f4')
    tri=np.array([[0,1,2],[0,2,3],[4,5,6]],'u4')
    uv=np.array([[0,0],[.5,0],[.5,.5],[0,.5],[.6,.6],[.7,.6],[.6,.7]],'f4')
    pr['attributes']=dict(POSITION=append_accessor(doc,buf,p,'VEC3'),
        NORMAL=append_accessor(doc,buf,[[0,0,1]]*7,'VEC3'),
        TEXCOORD_0=append_accessor(doc,buf,uv,'VEC2'),
        TANGENT=append_accessor(doc,buf,[[1,0,0,1]]*7,'VEC4'))
    pr['indices']=append_accessor(doc,buf,tri.ravel(),'SCALAR',5125,34963)
    doc['buffers'][0]['byteLength']=len(buf)
    source.write_bytes(write_glb(doc,buf))
    class CollapsedAtlas:
        def add_mesh(self,*args):
            pass
        def generate(self,**kwargs):
            pass
        def __getitem__(self,index):
            collapsed=uv.copy()
            collapsed[4:]=[.6,.6]
            return np.arange(7,dtype='u4'),tri.copy(),collapsed
    monkeypatch.setattr(xatlas,'Atlas',CollapsedAtlas)
    recipe=tmp_path/'small.json'
    recipe.write_text(json.dumps(dict(schema='reference-asset-compiler.repack-surface-recipe.v1',
        source_sha256=sha256_file(source),acquisition_provenance='Synthetic collapsed chart test',
        mesh='Coat',material='Hand-painted',new_material='Repacked',resolution=128,padding=2)))
    if not tiny:
        with pytest.raises(ValueError,match='substantial'):
            repack(source,recipe)
    else:
        raw,receipt=repack(source,recipe)
        out,new=read_glb(raw)
        after=out['meshes'][0]['primitives'][0]
        actual=accessor(out,new,after['attributes']['POSITION'])[faces(out,new,after)]
        np.testing.assert_array_equal(actual,p[tri])
        assert receipt['isolated_subpixel_triangles']==[2]


def test_restore_refuses_reversed_donor_winding(tmp_path):
    source,recipe=hole_fixture(tmp_path)
    cfg=json.loads(recipe.read_text())
    path=tmp_path/cfg['donor']
    d,b=read_glb(path.read_bytes())
    p=d['meshes'][0]['primitives'][0]
    tri=faces(d,b,p).copy()
    tri[0]=tri[0,::-1]
    buf=bytearray(b)
    p['indices']=append_accessor(d,buf,tri.ravel(),'SCALAR',5125,34963)
    d['buffers'][0]['byteLength']=len(buf)
    path.write_bytes(write_glb(d,buf))
    cfg['donor_sha256']=sha256_file(path)
    recipe.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='winding'):
        restore_surface(source,recipe)


def test_repack_refuses_to_silently_discard_tangent_morphs(tmp_path):
    pytest.importorskip('xatlas')
    source,_=hole_fixture(tmp_path)
    doc,binary=read_glb(source.read_bytes())
    pr=doc['meshes'][0]['primitives'][0]
    pr['targets'][0]['TANGENT']=pr['targets'][0]['POSITION']
    source.write_bytes(write_glb(doc,binary))
    recipe=tmp_path/'tangents.json'
    recipe.write_text(json.dumps(dict(schema='reference-asset-compiler.repack-surface-recipe.v1',
        source_sha256=sha256_file(source),acquisition_provenance='Synthetic refusal test',
        mesh='Coat',material='Hand-painted',new_material='Repacked',resolution=64,padding=4)))
    with pytest.raises(ValueError,match='Tangent morphs'):
        repack(source,recipe)
