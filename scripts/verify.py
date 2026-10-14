from __future__ import annotations
from runtime_env import configured
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def run(command, cwd, log):
    result = subprocess.run([str(x) for x in command], cwd=cwd, text=True, encoding='utf-8', errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout, encoding='utf-8')
    return {'command': [str(x) for x in command], 'cwd': str(cwd), 'exit_code': result.returncode, 'log': str(log)}, result.stdout

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-dir', type=Path, required=True)
    parser.add_argument('--terminal-demo', action='store_true')
    parser.add_argument("--signature-demo", action="store_true")
    args = parser.parse_args()
    export = args.export_dir.resolve()
    logs = export / 'verification-logs'
    logs.mkdir(parents=True, exist_ok=True)
    commands = []
    result = {'status': 'INCONCLUSIVE', 'security_status': 'OPEN_OBLIGATION', 'security_conclusion': 'none', 'export_directory': str(export), 'commands': commands}
    try:
        lake = configured('LAKE') or shutil.which('lake')
        if not lake:
            raise RuntimeError('Lean/Lake 4.34.1 is required; place lake on PATH or set VAKE_LAKE')
        source_lean = ROOT / 'lean'
        isolated = export / 'lean-check'
        if isolated.exists():
            raise RuntimeError('Verification work directory already exists; use a fresh export directory')
        shutil.copytree(source_lean, isolated, ignore=shutil.ignore_patterns('.lake', 'Imported', 'Generated', 'Demo', 'Audit.lean', 'SignatureObservations.lean', 'validation'))
        record, output = run([lake, 'env', 'lean', '--version'], isolated, logs / 'lean-version.log')
        commands.append(record)
        if record['exit_code'] or 'version 4.34.1,' not in output:
            raise RuntimeError('The required Lean version is 4.34.1; see lean-version.log')
        record, output = run([sys.executable, ROOT / 'scripts/import_model.py', export, '--lean-dir', isolated], ROOT, logs / 'independent-import.log')
        commands.append(record)
        if record['exit_code']:
            result['status'] = 'TRANSLATION_ERROR'
            raise RuntimeError('Independent source import or operational projection comparison failed')
        imported = json.loads(output)
        record, output = run([lake, 'build', imported['proof']], isolated, logs / 'lean-build.log')
        commands.append(record)
        if record['exit_code']:
            result['status'] = 'CERTIFICATE_FAILED'
            raise RuntimeError('Lean rejected the generated model or its binding/correspondence certificates')
        result['compilation_status'] = 'LEAN_COMPILED'
        command = [sys.executable, ROOT / 'scripts/validate_lean.py', '--lean-dir', isolated, '--proof-module', imported['proof'], '--lake', lake]
        if args.signature_demo:
            if (export/"model.json").read_bytes() != (ROOT/"examples/signature_check.json").read_bytes() or (export/"operational-profile.json").read_bytes() != (ROOT/"examples/restricted_symbolic_v1.profile.json").read_bytes():
                raise ValueError("Signature demo requires exact bundled model/profile")
            command.append("--signature-demo")
        if args.terminal_demo:
            command.append('--terminal-demo')
        record, output = run(command, ROOT, logs / 'axiom-validation.log')
        commands.append(record)
        if record['exit_code']:
            result['status'] = 'CERTIFICATE_FAILED'
            raise RuntimeError('Independent theorem or axiom validation failed')
        audit = json.loads(output)
        result.update(status='PROVED_UNDER_ASSUMPTIONS', proof_module=imported['proof'], import_status=imported,
                      proof_scope='Concrete source/target AST binding and preserved operational correspondence',
                      theorem_audit=audit, assumptions=['Lean kernel and standard logical axioms reported in audit',
                      'Independent JSON source importer and Rust frontend are trusted programs',
                      'Preserved symbolic semantics and explicit operational profile model the intended system'],
                      unsupported_properties=['authentication', 'secrecy', 'computational security', 'attack search'],
                      terminal_demo=args.terminal_demo, signature_demo=args.signature_demo)
        if args.signature_demo:
            result["signature_behavior_scope"] = "Kernel-checked sign construction only; valid/changed-message verification outcomes are separate executable observations. No authentication proof."
        code = 0
    except Exception as exc:
        result['message'] = str(exc)
        code = 1
    (export / 'verification-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return code

if __name__ == '__main__':
    raise SystemExit(main())
