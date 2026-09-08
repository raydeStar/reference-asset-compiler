"""Run the actual material builder against a small graph-recording UE double."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

class Node:
    def __init__(self, kind):
        self.kind, self.props = kind, {}
    def set_editor_property(self, key, value):
        self.props[key] = value
    def get_editor_property(self, key):
        return self.props.get(key, True)
    def get_name(self):
        return self.kind

class NormalFallbackTests(unittest.TestCase):
    def build(self, with_normal=False):
        nodes, links, properties, scalars, textures = [], [], {}, {}, {}
        master, instance = Node('Master'), Node('Instance')
        def create_node(material, kind, *args):
            node = Node(kind)
            nodes.append(node)
            return node
        lib = NS(create_material_expression=create_node,
            connect_material_expressions=lambda a, s, b, p: links.append((a,s,b,p)) or True,
            connect_material_property=lambda a, s, p: properties.update({p:a}) or True,
            recompile_material=lambda m: None,
            get_texture_parameter_names=lambda m: ['BaseColor','ORM','Normal'],
            get_statistics=lambda m: NS(num_pixel_shader_instructions=20),
            set_material_instance_parent=lambda i,m: None,
            set_material_instance_texture_parameter_value=lambda i,k,t: textures.update({k:t}),
            set_material_instance_scalar_parameter_value=lambda i,k,v: scalars.update({k:v}),
            get_material_instance_texture_parameter_value=lambda i,k: textures.get(k),
            update_material_instance=lambda i: None)
        engine = NS(MaterialEditingLibrary=lib,
            EditorAssetLibrary=NS(load_asset=lambda p: None if p.endswith('Master_v002') else Node(p),
                save_asset=lambda p: True, does_asset_exist=lambda p: False),
            AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=lambda name, root, cls, factory:
                master if cls == 'Material' else instance)),
            Material='Material', MaterialInstanceConstant='Instance',
            MaterialFactoryNew=lambda: None, MaterialInstanceConstantFactoryNew=lambda: None,
            LinearColor=lambda *values: values,
            MaterialProperty=NS(**{n:n for n in ['MP_BASE_COLOR','MP_NORMAL','MP_AMBIENT_OCCLUSION','MP_ROUGHNESS','MP_METALLIC']}),
            MaterialSamplerType=NS(SAMPLERTYPE_NORMAL='normal',SAMPLERTYPE_MASKS='masks'),
            log=lambda m: None, log_warning=lambda m: None, log_error=lambda m: self.fail(m))
        for name in ['TextureSampleParameter2D','Constant3Vector','ScalarParameter','LinearInterpolate','Constant']:
            setattr(engine,'MaterialExpression'+name,name)
        path = Path(__file__).resolve().parents[1]/'scripts/ue5/import_asset.py'
        tree = ast.parse(path.read_text())
        selected = [n for n in tree.body if
            isinstance(n,ast.FunctionDef) and n.name in {'ensure_master_material','build_material'} or
            isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'MASTER_NAME','MASTER_PATH','TEXTURE_PARAMETERS'} for t in n.targets)]
        scope = {'unreal':engine}
        exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),scope)
        slots = {'BaseColor':Node('base'),'ORM':Node('orm')}
        if with_normal:
            slots['Normal'] = Node('authored-normal')
        self.assertIs(instance,scope['build_material']('/Game/Test','M_Test',slots))
        return nodes, links, properties, scalars, textures, scope

    def test_missing_normal_uses_neutral_vector_not_engine_brick_texture(self):
        nodes, links, properties, scalars, _, scope = self.build()
        blend = properties['MP_NORMAL']
        self.assertEqual('LinearInterpolate',blend.kind)
        incoming = {pin:source for source,output,target,pin in links if target is blend}
        self.assertEqual((0.,0.,1.,1.),incoming['A'].props['constant'])
        self.assertEqual('Normal',incoming['B'].props['parameter_name'])
        self.assertEqual('HasNormal',incoming['Alpha'].props['parameter_name'])
        self.assertEqual(0.,incoming['Alpha'].props['default_value'])
        self.assertEqual(0.,scalars['HasNormal'])
        self.assertEqual('M_RAC_CharacterMaster_v002',scope['MASTER_NAME'])

    def test_authored_normal_enables_the_supplied_texture(self):
        _, _, _, scalars, textures, _ = self.build(with_normal=True)
        self.assertEqual(1.,scalars['HasNormal'])
        self.assertEqual('authored-normal',textures['Normal'].get_name())
        self.assertEqual(1.,scalars['HasORM'])
