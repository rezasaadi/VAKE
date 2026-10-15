from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
CORE_PROOFS = ["Local", "Global", "NoCommit", "Commitment", "KeyInjective"]

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def theorem_names(path: Path) -> list[str]:

    namespace = ""
    result = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        start = re.match(r"\s*namespace\s+([A-Za-z0-9_.]+)\s*$", line)
        if start:
            namespace = start.group(1)
        match = re.match(r"\s*(?:@\[[^\]]*\]\s*)?theorem\s+([A-Za-z0-9_]+)\b", line)
        if match:
            if not namespace:
                raise ValueError(f"Missing explicit namespace in {path}")
            result.append(namespace + "." + match.group(1))
    if not result:
        raise ValueError(f"No named theorems found in {path}")
    return result

def run(command: list[str], cwd: Path, log: Path) -> str:
    env = os.environ.copy()
    env["PATH"] = str(Path(command[0]).resolve().parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(command, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"Command exited {proc.returncode}: {command!r}; see {log}")
    return proc.stdout

def parse_audits(output: str, names: list[str]) -> list[dict]:
    records = []
    for name in names:
        pat = "'" + re.escape(name) + r"' (?:depends on axioms: \[([^\]]*)\]|does not depend on any axioms)"
        matches = list(re.finditer(pat, output))
        if len(matches) != 1:
            raise ValueError(f"Missing/duplicate axiom audit for {name}")
        match = matches[0]
        axioms = [] if match.group(1) is None else re.findall(r"[A-Za-z][\w.]*", match.group(1))
        if set(axioms) - ALLOWED_AXIOMS:
            raise ValueError(f"Forbidden axiom dependencies for {name}: {axioms}")
        starts = list(re.finditer(r"^" + re.escape(name) + r"(?=\s|:)", output[:match.start()], re.MULTILINE))
        if not starts:
            raise ValueError(f"Missing printed statement for {name}")
        statement = output[starts[-1].start():match.start()].strip()
        records.append({"name": name, "kernel_checked": True, "axioms": axioms,
                        "statement": statement, "statement_sha256": sha(statement.encode())})
    return records

def generate_demo(lean_dir: Path, proof_module: str) -> Path:
    digest = proof_module.removeprefix("VAKE.Generated.B")
    template = Path(__file__).with_name("terminal_demo.lean.in").read_text(encoding="utf-8")
    path = lean_dir / "VAKE" / "Demo" / "Terminal.lean"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.replace("@DIGEST@", digest), encoding="utf-8")
    return path

def validate(lean_dir: Path, proof_module: str | None, lake: str, terminal_demo: bool = False, scenarios: Path | None = None, signature_demo: bool = False, binding: tuple[str, str] | None = None) -> dict:
    global_demo = scenarios is not None
    lean_dir = lean_dir.resolve()
    out = lean_dir / "validation"
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("proof-audit.json", "proof-audit-failure.json"):
        (out / stale).unlink(missing_ok=True)
    files = [lean_dir / "VAKE" / "Proofs" / (name + ".lean") for name in CORE_PROOFS]
    modules = ["VAKE.Proofs." + name for name in CORE_PROOFS]
    if proof_module:
        if not re.fullmatch(r"VAKE\.Generated\.B[0-9a-f]{64}", proof_module):
            raise ValueError("Proof module must be VAKE.Generated.B followed by a lowercase SHA-256 digest")
        files.append(lean_dir.joinpath(*proof_module.split(".")).with_suffix(".lean"))
        modules.append(proof_module)
    if terminal_demo:
        if not proof_module:
            raise ValueError("Terminal demo requires a concrete proof module")
        files.append(generate_demo(lean_dir, proof_module))
        modules.append("VAKE.Demo.Terminal")
    if global_demo:
        if not proof_module:
            raise ValueError("Global demo requires a concrete proof module")
        if not binding:
            raise ValueError("Scenario traces require the model and profile SHA-256 binding")
        from scenario_traces import generate
        files.append(generate(lean_dir, proof_module, lake, scenarios, *binding))
        modules.append("VAKE.Demo.Global")
    if signature_demo:
        if not proof_module: raise ValueError("Signature demo requires a proof module")
        template = Path(__file__).with_name("signature_demo.lean.in").read_text(encoding="utf-8")
        file = lean_dir / "VAKE/Demo/Signature.lean"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(template.replace("@DIGEST@", proof_module.removeprefix("VAKE.Generated.B")), encoding="utf-8")
        files.append(file)
        modules.append("VAKE.Demo.Signature")
    expected = json.loads(Path(__file__).with_name("proof-declarations.json").read_text(encoding="utf-8"))
    for core in CORE_PROOFS:
        actual = theorem_names(lean_dir / "VAKE" / "Proofs" / (core + ".lean"))
        if actual != expected[core]:
            raise ValueError(f"Preserved theorem inventory changed: {core}")
    if proof_module:
        wanted = [proof_module + "." + name for name in
                  ("binding", "profile_binding", "step_preservation", "trace_preservation", "trace_reflection")]
        if theorem_names(lean_dir.joinpath(*proof_module.split(".")).with_suffix(".lean")) != wanted:
            raise ValueError("Concrete certificate declaration inventory changed")
    names = [name for file in files for name in theorem_names(file)]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate declaration in audit inventory")
    audit = lean_dir / "VAKE" / "Audit.lean"
    audit.write_text("\n".join("import " + module for module in modules)
                     + "\n"
                     + "\n".join(f"#check {name}\n#print axioms {name}" for name in names) + "\n", encoding="utf-8")
    version = run([lake, "env", "lean", "--version"], lean_dir, out / "lean-version.log").strip()
    run([lake, "build", *modules], lean_dir, out / "build.log")
    if signature_demo:
        observer = lean_dir / "SignatureObservations.lean"
        observer.write_text('import VAKE.Demo.Signature\ndef main : IO Unit := IO.println VAKE.Demo.Signature.observations.compress\n', encoding="utf-8")
        run([lake, "env", "lean", "--run", observer.name], lean_dir, out / "signature-observations.json")
    output = run([lake, "env", "lean", "VAKE/Audit.lean"], lean_dir, out / "axioms.log")
    records = parse_audits(output, names)
    result = {"status": "PROVED_UNDER_ASSUMPTIONS", "lean_version": version,
              "scope": "Symbolic operational semantics and translation correspondence only",
              "proof_module": proof_module, "terminal_demo": terminal_demo, "global_demo": global_demo, "scenario_file": scenarios.name if scenarios else None, "signature_demo": signature_demo,
              "theorem_count": len(records), "allowed_axioms": sorted(ALLOWED_AXIOMS),
              "axioms_used": sorted({a for r in records for a in r["axioms"]}),
              "source_files": [{"path": str(p.relative_to(lean_dir)), "sha256": sha(p.read_bytes())} for p in files],
              "theorems": records, "audit_log_sha256": sha(output.encode()), "output_dir": str(out)}
    (out / "proof-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean-dir", required=True, type=Path)
    parser.add_argument("--proof-module")
    parser.add_argument("--lake", default="lake")
    parser.add_argument("--terminal-demo", action="store_true")
    parser.add_argument("--scenarios", type=Path, help="scenario file for concrete trace certificates")
    parser.add_argument("--model-sha256")
    parser.add_argument("--profile-sha256")
    parser.add_argument("--signature-demo", action="store_true")
    args = parser.parse_args()
    try:
        binding = (args.model_sha256, args.profile_sha256) if args.model_sha256 and args.profile_sha256 else None
        result = validate(args.lean_dir, args.proof_module, args.lake, args.terminal_demo, args.scenarios, args.signature_demo, binding)
        print(json.dumps({key: result[key] for key in ("status", "lean_version", "proof_module", "terminal_demo", "theorem_count", "axioms_used", "output_dir")}))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        result = {"status": "FAILED", "error": str(error)}
        out = args.lean_dir / "validation"
        out.mkdir(parents=True, exist_ok=True)
        (out / "proof-audit-failure.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        return 1

if __name__ == "__main__":
    sys.exit(main())