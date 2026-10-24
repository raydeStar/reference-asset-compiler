# SPDX-License-Identifier: MIT
"""Read an installed mesh's actual bind frames and export its geometry without saving assets.

Set RAC_ANIMATION_BINDING_CONFIG to JSON containing mesh, reference_clip and a
fresh output directory. RAC_OWNED_EDITOR_PROCESS=1 quits only an owned editor.
Skeleton asset reference poses are deliberately not used as mesh bind poses.
"""
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal


def main():
    config_path = Path(os.environ['RAC_ANIMATION_BINDING_CONFIG'])
    config = json.loads(config_path.read_text())
    out = Path(config['output'])
    out.mkdir(parents=True, exist_ok=False)
    result = {'error': None, 'assets_saved': False, 'bones': {},
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest()}
    try:
        mesh = unreal.load_asset(config['mesh'])
        clip = unreal.load_asset(config['reference_clip'])
        assert isinstance(mesh, unreal.SkeletalMesh) and isinstance(clip, unreal.AnimSequence)
        assert mesh.get_editor_property('skeleton') == clip.get_editor_property('skeleton')
        result['mesh'] = mesh.get_path_name()
        options = unreal.AnimPoseEvaluationOptions()
        options.optional_skeletal_mesh = mesh
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(clip, 0, options)
        for name in unreal.AnimPoseExtensions.get_bone_names(pose):
            transform = unreal.AnimPoseExtensions.get_ref_bone_pose(pose, name, unreal.AnimPoseSpaces.WORLD)
            p, q = transform.translation, transform.rotation
            result['bones'][str(name)] = [p.x, p.y, p.z, q.x, q.y, q.z, q.w]
        path = out/'installed-mesh.fbx'
        task = unreal.AssetExportTask()
        task.object = mesh
        task.filename = str(path)
        task.automated = True
        task.prompt = False
        task.replace_identical = False
        task.options = unreal.FbxExportOption()
        task.exporter = unreal.SkeletalMeshExporterFBX()
        assert unreal.Exporter.run_asset_export_task(task)
        result['mesh_export'] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        (out/'engine-mesh-bind.json').write_text(json.dumps(result, indent=2))
        unreal.log_warning('MESH_BIND_EXPORTED -- the mesh, sir, is the witness. '+str(result['error'] or out))
        if os.environ.get('RAC_OWNED_EDITOR_PROCESS') == '1':
            unreal.SystemLibrary.quit_editor()


if __name__ == '__main__':
    main()
