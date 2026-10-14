from runtime_env import configured
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess, sys, time
from scenario_traces import matching, required_theorems
ROOT = Path(__file__).resolve().parents[1]

class StageFailure(RuntimeError):
    def __init__(self, name, stdout):
        super().__init__(name + " failed; see raw logs")
        self.name, self.stdout = name, stdout

def classify(error) -> str:

    if isinstance(error, StageFailure):
        if error.name == "binding-build":
            return "CERTIFICATE_FAILED"
        if error.name == "trace-audit":
            try:
                message = json.loads(error.stdout).get("error", "")
            except ValueError:
                message = ""
            if "Candidate evaluation failed" in message or "scenario" in message.lower():
                return "SCENARIO_ERROR"
            if "'build'" in message or "axiom" in message or "inventory" in message:
                return "CERTIFICATE_FAILED"
        return "INCONCLUSIVE"
    if isinstance(error, ValueError) and "scenario" in str(error).lower():
        return "SCENARIO_ERROR"
    if isinstance(error, ValueError) and "Missing required concrete trace declarations" in str(error):
        return "CERTIFICATE_FAILED"
    return "INCONCLUSIVE"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, help="scenario file (default: bundled file matching the export)")
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        parser.error("Trace destination must be fresh")
    output.mkdir(parents=True)
    result = {"status": "INCONCLUSIVE", "security_status": "OPEN_OBLIGATION", "security_conclusion": "none", "commands": []}
    started = time.monotonic()

    def run(name, argv, cwd):
        proc = subprocess.run([str(a) for a in argv], cwd=cwd, encoding="utf-8", errors="replace", capture_output=True)
        (output / (name + ".stdout.log")).write_text(proc.stdout, encoding="utf-8")
        (output / (name + ".stderr.log")).write_text(proc.stderr, encoding="utf-8")
        result["commands"].append({"command": [str(a) for a in argv], "cwd": str(cwd), "exit_code": proc.returncode,
                                   "stdout": name + ".stdout.log", "stderr": name + ".stderr.log"})
        if proc.returncode:
            raise StageFailure(name, proc.stdout)
        return proc.stdout
    try:
        export = args.export_dir.resolve()
        model, profile = (export / "model.json").read_bytes(), (export / "operational-profile.json").read_bytes()
        model_sha, profile_sha = hashlib.sha256(model).hexdigest(), hashlib.sha256(profile).hexdigest()
        scenarios = args.scenarios.resolve() if args.scenarios else matching(ROOT, model, profile)
        if scenarios is None:
            raise ValueError("No scenario file is bound to this model/profile; pass --scenarios with a file whose hashes match")
        result["scenario_file"] = str(scenarios.relative_to(ROOT)) if scenarios.is_relative_to(ROOT) else str(scenarios)
        lake = configured('LAKE') or shutil.which("lake")
        if not lake:
            raise RuntimeError("Lean/Lake 4.34.1 is required")
        isolated = output / "lean-check"
        shutil.copytree(ROOT / "lean", isolated, ignore=shutil.ignore_patterns(".lake", "Imported", "Generated", "Demo", "validation", "Audit.lean"))
        version = run("lean-version", [lake, "env", "lean", "--version"], isolated).strip()
        if "version 4.34.1," not in version:
            raise RuntimeError("Lean 4.34.1 required")
        imported = json.loads(run("independent-import", [sys.executable, ROOT / "scripts/import_model.py", export, "--lean-dir", isolated], ROOT))
        run("binding-build", [lake, "build", imported["proof"]], isolated)
        run("trace-audit", [sys.executable, ROOT / "scripts/validate_lean.py", "--lean-dir", isolated, "--proof-module", imported["proof"],
                            "--lake", lake, "--scenarios", scenarios, "--model-sha256", model_sha, "--profile-sha256", profile_sha], ROOT)
        audit = json.loads((isolated / "validation/proof-audit.json").read_text())
        candidate = json.loads((isolated / "trace-candidate.json").read_text())
        names = {r["name"] for r in audit["theorems"]}
        missing = sorted(set(required_theorems(scenarios, candidate)) - names)
        if missing:
            raise ValueError("Missing required concrete trace declarations: " + ", ".join(missing[:5]))
        for scenario in candidate["scenarios"]:
            prefix = "VAKE.Demo.Global." + scenario["name"]
            scenario.update(theorem_prefix=prefix, source_theorem=prefix + "_source_trace", target_theorem=prefix + "_target_trace",
                            outcome=scenario.get("description", ""))
        result.update(status="PROVED_UNDER_ASSUMPTIONS",
                      scope="Concrete global source and generated-target reachability and the listed final-state claims for the scenarios in the scenario file",
                      rendering_boundary="Timeline serialized by compiled evaluation of the same definitions whose steps, event kinds, outcomes and traces are kernel-checked. Serialization is trusted display code.",
                      scenarios=candidate["scenarios"], theorem_count=len(audit["theorems"]), axioms_used=audit["axioms_used"], lean_version=version,
                      model_sha256=model_sha, profile_sha256=profile_sha,
                      certificate_sha256=hashlib.sha256((isolated / "VAKE/Demo/Global.lean").read_bytes()).hexdigest(),
                      proof_audit_sha256=hashlib.sha256((isolated / "validation/proof-audit.json").read_bytes()).hexdigest())
        code = 0
    except Exception as error:
        result["status"] = classify(error)
        result["message"] = str(error)
        code = 1
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    (output / "trace-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return code

if __name__ == "__main__":
    raise SystemExit(main())
