"""Isolated-host integration check; inputs and output are explicit environment paths.

Only run in check_unreal_animation_plugin.py's generated RACAnimationHost project.
RAC_PLUGIN_SMOKE_FBX, RAC_PLUGIN_SMOKE_PROBE, RAC_PLUGIN_SMOKE_OUTPUT are required.
RAC_PLUGIN_SMOKE_RELOAD=1 performs a read-only fresh-process saved graph check.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

import unreal

sys.path.insert(0,str(Path(__file__).resolve().parent))
from configure_rac_contact import install  # noqa: E402


def main():
    project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
    if not (project/'RACAnimationHost.uproject').is_file():
        raise ValueError('this fixture runs only in the isolated RACAnimationHost')
    out=Path(os.environ['RAC_PLUGIN_SMOKE_OUTPUT'])
    out.mkdir(parents=True,exist_ok=True)
    folder='/Game/RACFixture_'+''.join(c if c.isalnum() else '_' for c in out.name)
    asset_path=folder+'/ABP_Contact'
    if os.environ.get('RAC_PLUGIN_SMOKE_RELOAD')!='1':
        task=unreal.AssetImportTask()
        task.filename=os.environ['RAC_PLUGIN_SMOKE_FBX']
        task.destination_path=folder
        task.destination_name='FixtureCharacter'
        task.automated=True
        task.save=True
        options=unreal.FbxImportUI()
        options.import_mesh=True
        options.import_as_skeletal=True
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_SKELETAL_MESH
        options.automated_import_should_detect_type=False
        options.import_animations=False
        options.import_materials=False
        options.import_textures=False
        options.create_physics_asset=False
        task.options=options
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        meshes=[unreal.load_asset(p) for p in task.imported_object_paths]
        meshes=[m for m in meshes if isinstance(m,unreal.SkeletalMesh)]
        if len(meshes)!=1:
            raise ValueError('one imported fixture skeletal mesh required')
        factory=unreal.AnimBlueprintFactory()
        factory.set_editor_property('target_skeleton',meshes[0].get_editor_property('skeleton'))
        abp=unreal.AssetToolsHelpers.get_asset_tools().create_asset('ABP_Contact',folder,unreal.AnimBlueprint,factory)
        ed=unreal.BlueprintGraphEditor.get_graph_editor_by_name(abp,'AnimGraph')
        names=[str(n) for n in ed.list_available_nodes([])]
        reference=[n for n in names if 'localspacerefpose' in n.replace(' ','').lower()]
        if len(reference)!=1:
            (out/'node-catalog.json').write_text(json.dumps(names,indent=2))
            raise ValueError('could not resolve reference pose from the node catalog')
        pose=ed.create_node_from_name(reference[0],unreal.Vector2D(-300,0),[])
        root=next(n for n in ed.list_all_nodes() if n.get_class().get_name()=='AnimGraphNode_Root')
        assert pose.list_output_pins()[0].try_create_connection(root.list_input_pins()[0])
        assert unreal.BlueprintEditorLibrary.compile_blueprint(abp)
        assert unreal.EditorAssetLibrary.save_loaded_asset(abp,False)
        probe=Path(os.environ['RAC_PLUGIN_SMOKE_PROBE']).resolve()
        data=json.loads(probe.read_text())
        spec={'schema':'rac.unreal-contact-profile.v1','anim_blueprint':asset_path,
            'native_character_sha256':data['source_sha256'],
            'probe':{'path':str(probe),'sha256':hashlib.sha256(probe.read_bytes()).hexdigest()},
            'chains':{'l':['thigh_l','calf_l','foot_l','ik_foot_l'],'r':['thigh_r','calf_r','foot_r','ik_foot_r']},
            'plant_curves':{'l':'SolePlantL','r':'SolePlantR'},'clearance_cm':.65,
            'max_correction_cm':10.,'combat_max_correction_cm':3.,'release_time_s':.06}
        (out/'spec.json').write_text(json.dumps(spec,indent=2))
        install(out/'spec.json',out/'first-install')
        install(out/'spec.json',out/'repeat-install')
    abp=unreal.load_asset(asset_path)
    ed=unreal.BlueprintGraphEditor.get_graph_editor_by_name(abp,'AnimGraph')
    nodes=[n for n in ed.list_all_nodes() if n.get_class().get_name()=='AnimGraphNode_RACSoleContact']
    assert len(nodes)==1 and not ed.list_nodes_with_errors()
    node=nodes[0].get_editor_property('node')
    probe=json.loads(Path(os.environ['RAC_PLUGIN_SMOKE_PROBE']).read_text())
    assert len(node.get_editor_property('samples'))==sum(len(v) for v in probe['sides'].values())
    assert node.get_editor_property('max_correction')==10
    assert node.get_editor_property('max_combat_correction')==3
    assert str(node.get_editor_property('left_chain')[0])=='thigh_l'
    mode='reload' if os.environ.get('RAC_PLUGIN_SMOKE_RELOAD')=='1' else 'install'
    (out/(mode+'.json')).write_text(json.dumps({'passed':True,'mode':mode,'samples':len(node.get_editor_property('samples')),
        'asset':asset_path,'duplicate_nodes':False,'game_project_modified':False,'gameplay_tested':False},indent=2))
    unreal.log_warning('RAC_PLUGIN_SMOKE_PASS -- the independent workshop keeps its receipts.')


main()
