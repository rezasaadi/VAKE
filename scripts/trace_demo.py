from runtime_env import configured
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    output=args.out.resolve()
    if output.exists(): parser.error("Trace destination must be fresh")
    output.mkdir(parents=True)
    result={"status":"INCONCLUSIVE","security_status":"OPEN_OBLIGATION","security_conclusion":"none","commands":[]}
    started=time.monotonic()

    def run(name,argv,cwd):
        proc=subprocess.run([str(a) for a in argv],cwd=cwd,encoding="utf-8",errors="replace",capture_output=True)
        (output/(name+".stdout.log")).write_text(proc.stdout,encoding="utf-8")
        (output/(name+".stderr.log")).write_text(proc.stderr,encoding="utf-8")
        result["commands"].append({"command":[str(a) for a in argv],"cwd":str(cwd),"exit_code":proc.returncode,"stdout":name+".stdout.log","stderr":name+".stderr.log"})
        if proc.returncode: raise RuntimeError(name+" failed; see raw logs")
        return proc.stdout
    try:
        export=args.export_dir.resolve()
        for original,exported in (("nonce_exchange.json","model.json"),("restricted_symbolic_v1.profile.json","operational-profile.json")):
            if (ROOT/"examples"/original).read_bytes() != (export/exported).read_bytes():
                raise ValueError("Global demonstration requires the exact bundled nonce model and profile")
        lake=configured('LAKE') or shutil.which("lake")
        if not lake: raise RuntimeError("Lean/Lake 4.34.1 is required")
        isolated=output/"lean-check"
        shutil.copytree(ROOT/"lean",isolated,ignore=shutil.ignore_patterns(".lake","Imported","Generated","Demo","validation","Audit.lean"))
        version=run("lean-version",[lake,"env","lean","--version"],isolated).strip()
        if "version 4.34.1," not in version: raise RuntimeError("Lean 4.34.1 required")
        imported=json.loads(run("independent-import",[sys.executable,ROOT/"scripts/import_model.py",export,"--lean-dir",isolated],ROOT))
        run("binding-build",[lake,"build",imported["proof"]],isolated)
        run("trace-audit",[sys.executable,ROOT/"scripts/validate_lean.py","--lean-dir",isolated,"--proof-module",imported["proof"],"--lake",lake,"--global-demo"],ROOT)
        audit=json.loads((isolated/"validation/proof-audit.json").read_text())
        candidate=json.loads((isolated/"trace-candidate.json").read_text())
        names={r["name"] for r in audit["theorems"]}
        for scenario in candidate["scenarios"]:
            prefix="VAKE.Demo.Global."+scenario["name"]
            scenario.update(theorem_prefix=prefix,source_theorem=prefix+"_source_trace",target_theorem=prefix+"_target_trace",
                            outcome="Both sessions stopped; echo equals announcement; NonceObserved emitted." if scenario["name"]=="honest" else "Echoer rejected the envelope with a nonce of invalid length; no send.")
            required=[prefix+"_initial",prefix+"_source_trace",prefix+"_target_trace",prefix+"_echoer_outcome",prefix+"_send_count",prefix+"_echoer_no_resume"]
            required += [prefix+suffix+str(i+1) for i in range(len(scenario["events"])) for suffix in ("_execution_","_commit_","_event_","_knowledge_","_step_")]
            if not set(required)<=names: raise ValueError("Missing required concrete trace declarations")
        result.update(status="PROVED_UNDER_ASSUMPTIONS",scope="Concrete global source and generated-target reachability; malformed-delivery rejection",
                      rendering_boundary="Timeline serialized by compiled evaluation of the same definitions whose steps, event kinds, outcomes and traces are kernel-checked. Serialization is trusted display code.",
                      scenarios=candidate["scenarios"],theorem_count=len(audit["theorems"]),axioms_used=audit["axioms_used"],lean_version=version,
                      model_sha256=hashlib.sha256((export/"model.json").read_bytes()).hexdigest(),
                      profile_sha256=hashlib.sha256((export/"operational-profile.json").read_bytes()).hexdigest(),
                      certificate_sha256=hashlib.sha256((isolated/"VAKE/Demo/Global.lean").read_bytes()).hexdigest(),
                      proof_audit_sha256=hashlib.sha256((isolated/"validation/proof-audit.json").read_bytes()).hexdigest())
        code=0
    except Exception as error:
        result["message"]=str(error);code=1
    result["elapsed_ms"]=round((time.monotonic()-started)*1000)
    (output/"trace-result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    return code
if __name__=="__main__": raise SystemExit(main())

