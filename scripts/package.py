from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED_PREFIXES=('reports/runs/','reports/ui-runs/','reports/ci-evidence/','reports/demo-proof-export/','reports/negative-binding-controls/','lean/validation/','lean/VAKE/Generated/','lean/VAKE/Imported/','lean/VAKE/Demo/','vake-reports-export/','dist/')

def included(path, root=None):
    root=ROOT if root is None else Path(root)
    rel=path.relative_to(root)
    if any(p in {'.git','target','.lake','.vake-cache','__pycache__','node_modules'} for p in rel.parts):return False
    name=rel.as_posix()
    if not path.is_file() or name in {'source-manifest.json','lean/VAKE/Audit.lean','lean/SignatureObservations.lean'}:return False
    if path.name.startswith('.env') or path.suffix in {'.pem','.key','.pyc'}:return False
    if name.startswith(EXCLUDED_PREFIXES):return False
    if name.startswith('reports/') and len(rel.parts)==2 and path.suffix=='.log':return False
    return True

def source_files(root=None):
    root=ROOT if root is None else Path(root)
    files=sorted(p for p in root.rglob('*') if included(p, root))
    if any(p.is_symlink() for p in files):raise RuntimeError('Source package must not depend on symlinks')
    return files

def source_manifest(files, root=None):
    root=ROOT if root is None else Path(root)
    return {'version':'0.2.0','identity':'Content-addressed VAKE source snapshot','files':[{'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in files]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path)
    parser.add_argument('--clean-dir',type=Path)
    args=parser.parse_args()
    if not args.out and not args.clean_dir:parser.error('supply --out or --clean-dir')
    files=source_files()
    if args.out and args.out.resolve().is_relative_to(ROOT):raise RuntimeError('Archive destination must be outside source tree')
    if args.clean_dir and args.clean_dir.resolve().exists():raise RuntimeError('Clean destination must not exist')
    manifest=source_manifest(files)
    manifest_bytes=(json.dumps(manifest,indent=2)+'\n').encode('utf-8')
    if args.clean_dir:
        destination=args.clean_dir.resolve()
        for p in files:
            out=destination/p.relative_to(ROOT)
            out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,out)
        (destination/'source-manifest.json').write_bytes(manifest_bytes)
    if args.out:
        output=args.out.resolve()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            payload=[(p.relative_to(ROOT).as_posix(),p.read_bytes()) for p in files]+[('source-manifest.json',manifest_bytes)]
            for name,data in payload:
                info=zipfile.ZipInfo('VAKE/'+name)
                info.date_time=(2026,10,14,0,0,0)
                info.external_attr=((0o100755 if name.endswith('.sh') else 0o100644)<<16)
                info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,data)
        print(json.dumps({'archive':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'source_files':len(files)},indent=2))
    if args.clean_dir:print(json.dumps({'clean_directory':str(args.clean_dir.resolve()),'source_files':len(files)}))

if __name__=='__main__':main()
