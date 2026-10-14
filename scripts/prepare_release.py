from pathlib import Path
import argparse
import json
import subprocess
import sys

from component_manifest import refresh
from package import source_files, source_manifest

ROOT=Path(__file__).resolve().parents[1]

def refresh_manifests(root=ROOT):
    root=Path(root)
    refresh(root)
    manifest=source_manifest(source_files(root),root)
    (root/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    return manifest

def pending_source_changes(root=ROOT):
    root=Path(root)
    changed=subprocess.check_output(['git','-C',str(root),'diff','--name-only','HEAD','-z'])
    untracked=subprocess.check_output(['git','-C',str(root),'ls-files','--others','--exclude-standard','-z'])
    return sorted({n.decode('utf-8') for n in (changed+untracked).split(b'\0') if n})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check-publication',action='store_true',help='also require the complete source update to be committed before a push')
    args=parser.parse_args()
    manifest=refresh_manifests()
    command=[sys.executable,str(ROOT/'scripts/repository_preflight.py'),'--working-tree','--json',str(ROOT/'reports/runs/preparation/preflight-result.json')]
    result=subprocess.run(command)
    if result.returncode:return result.returncode
    if args.check_publication:
        if not (ROOT/'.git').exists():
            print(json.dumps({'status':'NOT_READY_TO_PUSH','message':'A Git checkout is required for publication checks.'}))
            return 1
        pending=pending_source_changes()
        if pending:
            print(json.dumps({'status':'NOT_READY_TO_PUSH','message':'Commit the complete source update, including both manifests and every new file, before pushing.','pending_files':pending},indent=2))
            return 1
    print(json.dumps({'status':'PREPARED','source_files':len(manifest['files']),'git_changes':'No staging, commits or pushes performed'}))
    return 0

if __name__=='__main__':raise SystemExit(main())
