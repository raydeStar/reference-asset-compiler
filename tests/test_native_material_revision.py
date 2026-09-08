"""Material repair must not become a side door around geometry or provenance gates."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from reference_asset_compiler.io import sha256_file
from reference_asset_compiler.native_revision import validate_native_revision

class NativeMaterialRevisionTests(unittest.TestCase):
    def fixture(self, root, mutate=None):
        evidence=[]
        def artifact(name, value):
            p=root/name
            p.write_text(json.dumps(value))
            evidence.append(p)
            return {'path':str(p),'sha256':sha256_file(p)}
        sha='a'*64
        old=artifact('previous.json',{'schema':'reference-asset-compiler.ue5-import-evidence.v1',
            'ok':True,'asset_id':'plant','manifest_sha256':sha,'result':{'mesh':'old'}})
        lod={'lod':0,'sha256':'b'*64,'vertices':12,'triangles':8}
        rows=[{'mesh':key,'lods':[copy.deepcopy(lod)],'material':key+'mat','parent':key+'master',
               'textures':{'BaseColor':'same','ORM':'sameorm'}} for key in ['old','new']]
        probe={'assets':rows,'geometry_identical':True,'read_only':True}
        result={'mesh':'new','ok':True,'lod_count':1,'native_lods':[{'lod':0,'vertices':12,'triangles':8}],
                'checks':[{'check':n,'ok':True} for n in ['import_scale','materials_assigned',
                    'materials_textured','lods','native_runtime_budget','texture_settings','normal_fallback_policy']]}
        derivative={'operation':'native_material_rebind','source_manifest_sha256':sha,
            'source_mesh':'old','candidate_mesh':'new',
            'native_files':[dict(mesh=n,**artifact(n+'.uasset',n)) for n in ['old','new']],
            'material_files':[dict(asset=n,**artifact(n+'.uasset',n)) for n in ['oldmat','newmat','newmaster']]}
        if mutate:
            mutate(probe,result,derivative)
        derivative['artifacts']=[artifact('probe.json',probe)]
        batch=artifact('batch.json',{'native_derivative':derivative,'assets':[result]})
        payload={'asset_id':'plant','manifest_sha256':sha,'result':result,
                 'batch_report':batch['path'],'batch_report_sha256':batch['sha256'],
                 'native_revision':{'previous_import':old,'derivative':derivative}}
        return payload,evidence

    def run_case(self,mutate=None,valid=False):
        with tempfile.TemporaryDirectory() as tmp:
            payload,evidence=self.fixture(Path(tmp),mutate)
            if valid:
                validate_native_revision(payload,evidence,15000,20000)
            else:
                with self.assertRaises(ValueError):
                    validate_native_revision(payload,evidence,15000,20000)

    def test_valid_material_only_change(self): self.run_case(valid=True)
    def test_geometry_change_refused(self):
        self.run_case(lambda p,r,d:p['assets'][1]['lods'][0].update(sha256='c'*64))
    def test_texture_swap_refused(self):
        self.run_case(lambda p,r,d:p['assets'][1]['textures'].update(BaseColor='other'))
    def test_missing_normal_check_refused(self):
        self.run_case(lambda p,r,d:r['checks'].pop())
    def test_missing_material_file_refused(self):
        self.run_case(lambda p,r,d:d['material_files'].pop())
    def test_geometry_counts_mismatch_refused(self):
        self.run_case(lambda p,r,d:r['native_lods'][0].update(vertices=13))
    def test_missing_lod_refused(self):
        self.run_case(lambda p,r,d:r.update(lod_count=2))
    def test_changed_bound_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload,evidence=self.fixture(Path(tmp))
            evidence[1].write_text('changed')
            with self.assertRaises(ValueError):
                validate_native_revision(payload,evidence,15000,20000)
