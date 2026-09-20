"""Check the actual browser GLBs and record their generation-to-runtime lineage."""
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree


root = Path(__file__).resolve().parents[2]
app = root / 'apps/lakeside-village'
ids = ['timber-cabin','round-cottage','pine-tree','wooden-dock','rowboat','mossy-rock','barrel-crates']


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


rows = []
for asset in ids:
    workspace = root / 'work' / ('lakeside-' + asset)
    revision = 'v2' if asset == 'pine-tree' else 'v1'
    uv_path = workspace / ('uv-' + revision) / 'mesh.glb'
    paint_dir = workspace / ('paint-' + revision)
    public = app / 'public/assets' / (asset + '.glb')
    source = trimesh.load(uv_path, force='mesh', process=False)
    runtime = trimesh.load(public, force='mesh', process=False)
    assert sha(public) == sha(paint_dir / 'painted.glb'), asset + ': served GLB differs from reviewed paint'
    assert len(source.faces) == len(runtime.faces), asset + ': triangle count changed'
    assert np.isfinite(runtime.vertices).all() and np.isfinite(runtime.visual.uv).all()
    assert len(runtime.visual.uv) == len(runtime.vertices)
    distances = cKDTree(source.triangles_center).query(runtime.triangles_center)[0]
    reverse = cKDTree(runtime.triangles_center).query(source.triangles_center)[0]
    delta = float(max(distances.max(),reverse.max()))
    assert delta < 1e-6, asset + ': runtime GLB geometry drift'
    material = runtime.visual.material
    image = getattr(material,'baseColorTexture',None)
    assert image is not None, asset + ': base color image missing'
    validation = json.loads((paint_dir / 'painted.validation.json').read_text())
    execution = json.loads((paint_dir / 'painted.execution.json').read_text())
    assert validation['faces_equal'] and validation['geometry_delta'] <= 1e-6 and validation['uv_delta'] <= 1e-6
    assert execution['status'] != 'running', asset + ': painter still running'
    tree_components = None
    if asset == 'pine-tree':
        connected = runtime.copy()
        connected.merge_vertices(merge_tex=True,merge_norm=True)
        tree_components = len(connected.split(only_watertight=False))
        assert tree_components == 1, 'Detached tree fragments returned after painting'
    generation_dir = workspace / 'candidates/hy3d-single-seed42-attempt001'
    rows.append({'id':asset,'file':'assets/'+asset+'.glb','sha256':sha(public),'bytes':public.stat().st_size,'triangles':len(runtime.faces),'vertices':len(runtime.vertices),'base_color_size':list(image.size),'runtime_geometry_delta':delta,'paint_geometry_delta':validation['geometry_delta'],'paint_uv_delta':validation['uv_delta'],'paint_faces_equal':validation['faces_equal'],'clean_painter_exit':execution['clean_process_exit'],'painter_exit_code':execution['exit_code'],'tree_connected_components':tree_components,'source_reference_sha256':sha(workspace/'references/primary.png'),'ai_candidate_sha256':sha(generation_dir/'candidate.glb'),'uv_authority_sha256':sha(uv_path),'paint_validation_sha256':sha(paint_dir/'painted.validation.json'),'texture_review_sha256':sha(workspace/'demo-reviews/texture_approval.json')})
report = {'schema':'stillwater.browser-assets.v1','date':'2026-09-15','scope':'Three.js demo; no UE production certification','source_scene_sha256':sha(root/'work/lakeside-village/references/scene-original.png'),'ground_texture_sha256':sha(app/'public/assets/forest-ground.png'),'assets':rows,'ok':True}
(app/'asset-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(root/'work/lakeside-village/evidence/runtime-asset-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'ok':True,'assets':len(rows),'triangles':sum(row['triangles'] for row in rows),'max_runtime_geometry_delta':max(row['runtime_geometry_delta'] for row in rows),'tree_components':next(row['tree_connected_components'] for row in rows if row['id']=='pine-tree')},indent=2))
