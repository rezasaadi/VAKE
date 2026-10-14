from __future__ import annotations
from runtime_env import configured
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['build','test','demo','all'], default='all')
    parser.add_argument('--offline', action='store_true')
    args=parser.parse_args()
    output=ROOT/'reports/runs'/('reproduce-'+str(time.time_ns()))
    output.mkdir(parents=True)
    commands=[]
    def invoke(name, command, cwd=ROOT):
        result=subprocess.run([str(x) for x in command],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        (output/(name+'.log')).write_text(result.stdout,encoding='utf-8')
        commands.append({'name':name,'command':[str(x) for x in command],'exit_code':result.returncode,'log':str(output/(name+'.log'))})
        print(name+': '+('PASS' if result.returncode==0 else 'FAIL'),flush=True)
        if result.returncode: raise RuntimeError(name+' failed; see saved log')
        return result.stdout
    try:
        cargo=configured('CARGO') or shutil.which('cargo')
        lake=configured('LAKE') or shutil.which('lake')
        if not lake or (args.stage != 'demo' and not cargo):
            raise RuntimeError('Required tools missing; set VAKE_CARGO/VAKE_LAKE or PATH (demo needs Lake and a prebuilt CLI)')
        if cargo: os.environ['VAKE_CARGO'] = str(cargo)
        os.environ['VAKE_LAKE'] = str(lake)
        if configured('RUSTC'): os.environ['RUSTC'] = configured('RUSTC')
        cargo_opts=['--locked']+(['--offline'] if args.offline else [])
        if args.stage in ['build','all']:
            rustc=configured('RUSTC') or shutil.which('rustc')
            if not rustc: raise RuntimeError('rustc required; set VAKE_RUSTC or PATH')
            rust=invoke('rust-version',[rustc,'--version'])
            if not rust.startswith('rustc 1.97.1 '): raise RuntimeError('Rust 1.97.1 is required by rust-toolchain.toml')
            lean=invoke('lean-version',[lake,'env','lean','--version'],ROOT/'lean')
            if 'version 4.34.1,' not in lean: raise RuntimeError('Lean 4.34.1 is required')
            invoke('cargo-build',[cargo,'build',*cargo_opts])
            invoke('lean-build',[lake,'build'],ROOT/'lean')
        if args.stage in ['test','all']:
            invoke('cargo-test',[cargo,'test',*cargo_opts])
            invoke('proof-auditor-tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'])
            invoke('lean-axioms',[sys.executable,ROOT/'scripts/validate_lean.py','--lean-dir',ROOT/'lean','--lake',lake])
        if args.stage in ['demo','all']:
            invoke('demo',[sys.executable,ROOT/'scripts/demo.py'])
        status='PASS'
        code=0
        error=None
    except Exception as exc:
        status='FAIL';code=1;error=str(exc)
    result={'status':status,'stage':args.stage,'platform':platform.platform(),'python':sys.version,'commands':commands,'error':error}
    (output/'reproduction-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'evidence_directory':str(output),'error':error},indent=2))
    return code
if __name__=='__main__': raise SystemExit(main())

