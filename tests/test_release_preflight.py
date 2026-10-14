from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

def load(name):
    spec=importlib.util.spec_from_file_location('release_test_'+name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def row(name,data):
    return {'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

class ReleasePreflightTests(unittest.TestCase):
    def preflight(self,root,tracked=None,working=False):
        module=load('repository_preflight')
        args=['repository_preflight.py']+(['--working-tree'] if working else [])
        raw=b'\0'.join(n.encode() for n in (tracked or []))+b'\0'
        with patch.object(module,'ROOT',root),patch.object(sys,'argv',args),patch.object(module.subprocess,'check_output',return_value=raw),redirect_stdout(io.StringIO()) as output:
            code=module.main()
        return code,json.loads(output.getvalue())

    def test_missing_file_does_not_hide_other_fingerprint_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'README.md').write_bytes(b'changed\n')
            rows=[row('scripts/scenario_traces.py',b'missing'),row('README.md',b'old\n')]
            (root/'source-manifest.json').write_text(json.dumps({'files':rows}))
            code,result=self.preflight(root)
            self.assertEqual(code,1)
            issues={(x['issue'],x.get('target')) for x in result['findings']}
            self.assertIn(('manifest references missing file','scripts/scenario_traces.py'),issues)
            self.assertIn(('manifest fingerprint mismatch','README.md'),issues)

    def test_tracked_snapshot_rejects_untracked_required_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'.git').mkdir()
            (root/'README.md').write_bytes(b'guide\n')
            (root/'scenario.py').write_bytes(b'x=1\n')
            rows=[row('README.md',b'guide\n'),row('scenario.py',b'x=1\n')]
            (root/'source-manifest.json').write_text(json.dumps({'files':rows}))
            code,result=self.preflight(root,['README.md','source-manifest.json'])
            self.assertEqual(code,1)
            self.assertTrue(any(x['issue']=='manifest references untracked file' and x['target']=='scenario.py' for x in result['findings']))
            code,result=self.preflight(root,working=True)
            self.assertEqual(code,0,result)
            code,result=self.preflight(root,['README.md','scenario.py','source-manifest.json'])
            self.assertEqual(code,0,result)

    def test_manifest_must_cover_all_selected_source_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'README.md').write_bytes(b'guide\n')
            (root/'new.py').write_bytes(b'x=1\n')
            (root/'source-manifest.json').write_text(json.dumps({'files':[row('README.md',b'guide\n')]}))
            code,result=self.preflight(root)
            self.assertEqual(code,1)
            self.assertTrue(any(x['issue']=='source file absent from manifest' and x['target']=='new.py' for x in result['findings']))

    def test_refresh_updates_both_manifests_in_order(self):
        module=load('prepare_release')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ['Cargo.toml','Cargo.lock','rust-toolchain.toml','lean/lakefile.toml','lean/lake-manifest.json','lean/lean-toolchain','scripts/scenario_traces.py']:
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'fixture\n')
            (root/'README.md').write_bytes(b'guide\n')
            manifest=module.refresh_manifests(root)
            component=next(x for x in manifest['files'] if x['path']=='docs/components.json')
            self.assertEqual(component['sha256'],hashlib.sha256((root/'docs/components.json').read_bytes()).hexdigest())
            self.assertNotIn(b'\r',(root/'docs/components.json').read_bytes())
            self.assertNotIn(b'\r',(root/'source-manifest.json').read_bytes())
            self.assertNotIn('source-manifest.json',{x['path'] for x in manifest['files']})
            code,result=self.preflight(root)
            self.assertEqual(code,0,result)

    def test_collector_preserves_early_preflight_failure(self):
        module=load('collect_ci_evidence')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            source=root/'reports/runs/preflight/preflight-result.json'
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({'status':'FAIL','findings':[{'issue':'manifest references missing file'}]}))
            with patch.object(module,'ROOT',root):module.main()
            target=root/'reports/ci-evidence/preflight/preflight-result.json'
            self.assertEqual(json.loads(target.read_text())['status'],'FAIL')
            manifest=json.loads((root/'reports/ci-evidence/manifest.json').read_text())
            self.assertEqual(manifest['files'][0]['sha256'],hashlib.sha256(target.read_bytes()).hexdigest())

    def test_publication_check_reports_all_pending_paths(self):
        module=load('prepare_release')
        with patch.object(module.subprocess,'check_output',side_effect=[b'scripts/demo.py\0',b'scripts/scenario_traces.py\0']):
            self.assertEqual(module.pending_source_changes(),['scripts/demo.py','scripts/scenario_traces.py'])

if __name__=='__main__':unittest.main()
