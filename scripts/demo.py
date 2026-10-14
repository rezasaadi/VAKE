from __future__ import annotations
from runtime_env import configured
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
ROOT = Path(__file__).resolve().parents[1]

def main():
    executable = ROOT / 'target' / 'debug' / ('vake.exe' if os.name == 'nt' else 'vake')
    if not executable.exists():
        print(json.dumps({'status':'INTERNAL_ERROR', 'message':'Run the build script before demo'}))
        return 1
    run = ROOT / 'reports/runs' / ('demo-' + str(time.time_ns()))
    run.mkdir(parents=True)
    model = ROOT / 'examples/nonce_exchange.json'
    profile = ROOT / 'examples/restricted_symbolic_v1.profile.json'
    stages = []
    def invoke(name, command, expected_code=0, expected_status=None):
        result = subprocess.run([str(x) for x in command], cwd=ROOT, text=True, encoding='utf-8', errors='replace', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (run / (name + '.stdout.log')).write_text(result.stdout, encoding='utf-8')
        (run / (name + '.stderr.log')).write_text(result.stderr, encoding='utf-8')
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = {'status':'INTERNAL_ERROR', 'message':'Non-JSON output; inspect saved logs'}
        passed = result.returncode == expected_code and (expected_status is None or payload.get('status') == expected_status)
        stages.append({'stage':name, 'passed':passed, 'exit_code':result.returncode, 'status':payload.get('status'), 'command':[str(x) for x in command]})
        return passed
    ok = invoke('check', [executable, 'check', model], expected_status='CHECKED')
    if ok:
        ok = invoke('export', [executable, 'export', model, '--profile', profile, '--out', run / 'export'], expected_status='EXPORTED')
    if ok:
        ok = invoke('verify', [sys.executable, ROOT/'scripts/verify.py', '--export-dir', run/'export', '--terminal-demo'], expected_status='PROVED_UNDER_ASSUMPTIONS')
    if ok:
        proof = json.loads((run/'export/verification-result.json').read_text(encoding='utf-8'))['proof_module']
        lake = configured('LAKE') or shutil.which('lake')
        ok = invoke('negative-bindings', [sys.executable, ROOT/'scripts/test_negative_bindings.py', '--lean-dir', run/'export/lean-check', '--proof-module', proof, '--out', run/'negative-binding-controls', '--lake', lake], expected_status='PASSED')
    if ok:
        ok = invoke('global-traces', [sys.executable, ROOT/'scripts/trace_demo.py', '--export-dir', run/'export', '--out', run/'traces'], expected_status='PROVED_UNDER_ASSUMPTIONS')
    if ok:
        signature_model = ROOT/'examples/signature_check.json'
        ok = invoke('signature-check', [executable, 'check', signature_model], expected_status='CHECKED')
        if ok:
            ok = invoke('signature-export', [executable, 'export', signature_model, '--profile', profile, '--out', run/'signature-export'], expected_status='EXPORTED')
        if ok:
            ok = invoke('signature-verify', [sys.executable, ROOT/'scripts/verify.py', '--export-dir', run/'signature-export', '--signature-demo'], expected_status='PROVED_UNDER_ASSUMPTIONS')
    if ok:
        dh_model = ROOT/'examples/dh_exchange.json'
        ok = invoke('dh-check', [executable, 'check', dh_model], expected_status='CHECKED')
        if ok:
            ok = invoke('dh-export', [executable, 'export', dh_model, '--profile', profile, '--out', run/'dh-export'], expected_status='EXPORTED')
        if ok:
            ok = invoke('dh-verify', [sys.executable, ROOT/'scripts/verify.py', '--export-dir', run/'dh-export'], expected_status='PROVED_UNDER_ASSUMPTIONS')
        if ok:
            ok = invoke('dh-traces', [sys.executable, ROOT/'scripts/trace_demo.py', '--export-dir', run/'dh-export', '--out', run/'dh-traces'], expected_status='PROVED_UNDER_ASSUMPTIONS')
    if ok:
        signed_model = ROOT/'examples/signed_dh_exchange.json'
        ok = invoke('signed-dh-check', [executable, 'check', signed_model], expected_status='CHECKED')
        if ok:
            ok = invoke('signed-dh-export', [executable, 'export', signed_model, '--profile', profile, '--out', run/'signed-dh-export'], expected_status='EXPORTED')
        if ok:
            ok = invoke('signed-dh-verify', [sys.executable, ROOT/'scripts/verify.py', '--export-dir', run/'signed-dh-export'], expected_status='PROVED_UNDER_ASSUMPTIONS')
        if ok:
            ok = invoke('signed-dh-traces', [sys.executable, ROOT/'scripts/trace_demo.py', '--export-dir', run/'signed-dh-export', '--out', run/'signed-dh-traces'], expected_status='PROVED_UNDER_ASSUMPTIONS')
    negative = ROOT / 'examples/negative/type_mismatch.json'
    if negative.exists():
        ok = invoke('negative-type', [executable, 'check', negative], 1, 'TYPE_ERROR') and ok
    else:
        stages.append({'stage':'negative-type','passed':False,'message':'Missing required type mismatch example'})
        ok = False
    summary = {'status':'PASS' if ok else 'FAIL', 'stages':stages, 'evidence_directory':str(run), 'security_conclusion':'none'}
    (run/'demo-result.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1
if __name__ == '__main__':
    raise SystemExit(main())

