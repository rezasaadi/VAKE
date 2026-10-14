from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean-dir", required=True, type=Path)
    parser.add_argument("--proof-module", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--lake", default="lake")
    args = parser.parse_args()
    if not re.fullmatch(r"VAKE\.Generated\.B[0-9a-f]{64}", args.proof_module):
        parser.error("Expected concrete VAKE.Generated.B<sha256> certificate module")
    if args.out.exists():
        parser.error("Negative-control destination must be fresh")
    args.out.mkdir(parents=True)
    digest = args.proof_module.removeprefix("VAKE.Generated.B")
    generated = Path("VAKE") / "Generated" / ("M" + digest + ".lean")
    certificate = Path("VAKE") / "Generated" / ("B" + digest + ".lean")
    mutations = [
        ("target_erase_changed", '(.clear "nonceA")', '(.clear "packetA")', "binding"),
        ("target_phase_changed", '"stuck_unexpected"', '"reject_unexpected_preserve_completed"', "profile_binding"),
    ]
    results = []
    env = os.environ.copy()
    env["PATH"] = str(Path(args.lake).resolve().parent) + os.pathsep + env.get("PATH", "")
    for name, before, after, theorem in mutations:
        isolated = args.out / name
        shutil.copytree(args.lean_dir, isolated, ignore=shutil.ignore_patterns(".lake", "validation", "Debug.lean"))
        target = isolated / generated
        source_text = target.read_text(encoding="utf-8")
        if source_text.count(before) != 1:
            raise ValueError(f"Negative control must change exactly one occurrence: {name}")
        target.write_text(source_text.replace(before, after), encoding="utf-8")
        declaration_line = next(i for i, line in enumerate((isolated / certificate).read_text(encoding="utf-8").splitlines(), 1)
                                if line.startswith("theorem " + theorem + " :"))
        command = [args.lake, "build", args.proof_module]
        result = subprocess.run(command, cwd=isolated, env=env, encoding="utf-8", errors="replace", text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = args.out / (name + ".log")
        log.write_text(result.stdout, encoding="utf-8")
        expected_diagnostic = certificate.name + ":" + str(declaration_line) + ":"
        rejected = result.returncode != 0 and expected_diagnostic in result.stdout and "Tactic `rfl` failed" in result.stdout
        row = {"control": name, "changed": str(generated), "before": before, "after": after,
               "expected_failure": args.proof_module + "." + theorem, "exit_code": result.returncode,
               "rejected_at_expected_binding": rejected, "log": str(log),
               "mutated_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        results.append(row)
        (args.out / "negative-binding-results.json").write_text(json.dumps({"status": "PASSED" if all(r["rejected_at_expected_binding"] for r in results) else "FAILED",
                                                                           "controls": results}, indent=2) + "\n", encoding="utf-8")
        if not rejected:
            raise RuntimeError(f"Control did not reject at expected binding: {name}; see {log}")
    print(json.dumps({"status": "PASSED", "controls": len(results), "output_dir": str(args.out)}))
    return 0

if __name__ == "__main__":
    sys.exit(main())