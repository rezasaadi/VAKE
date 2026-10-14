from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scenario_traces import matching

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error("Use 1..10 repetitions")
    out = ROOT / "reports/runs" / ("measure-" + str(time.time_ns()))
    out.mkdir(parents=True)
    binary = ROOT / "target/debug" / ("vake.exe" if os.name == "nt" else "vake")
    profile = ROOT / "examples/restricted_symbolic_v1.profile.json"
    rows = []
    error = None
    try:
        for model in ("nonce_exchange", "dh_exchange", "signed_dh_exchange", "signature_check", "negative/type_mismatch"):
            for i in range(args.repetitions):
                directory = out / (model.replace("/", "-") + "-" + str(i + 1))
                directory.mkdir()
                file = ROOT / "examples" / (model + ".json")
                negative = model.startswith("negative/")
                commands = [("check", [binary, "check", file], 1 if negative else 0,
                             "TYPE_ERROR" if negative else "CHECKED")]
                if not negative:
                    flags = {"nonce_exchange": ["--terminal-demo"], "signature_check": ["--signature-demo"]}.get(model, [])
                    commands += [
                        ("export", [binary, "export", file, "--profile", profile,
                                    "--out", directory / "export"], 0, "EXPORTED"),
                        ("verify", [sys.executable, ROOT / "scripts/verify.py", "--export-dir",
                                    directory / "export", *flags], 0, "PROVED_UNDER_ASSUMPTIONS"),
                    ]
                    if profile.is_file() and matching(ROOT, file.read_bytes(), profile.read_bytes()):
                        commands.append(("traces", [sys.executable, ROOT / "scripts/trace_demo.py", "--export-dir",
                                                    directory / "export", "--out", directory / "traces"], 0,
                                         "PROVED_UNDER_ASSUMPTIONS"))
                for stage, argv, expected_code, expected_status in commands:
                    started = time.perf_counter()
                    proc = subprocess.run([str(a) for a in argv], cwd=ROOT, capture_output=True,
                                          encoding="utf-8", errors="replace")
                    elapsed = (time.perf_counter() - started) * 1000
                    (directory / (stage + ".stdout.log")).write_text(proc.stdout, encoding="utf-8")
                    (directory / (stage + ".stderr.log")).write_text(proc.stderr, encoding="utf-8")
                    try:
                        payload = json.loads(proc.stdout)
                        if not isinstance(payload, dict):
                            raise ValueError("Expected a JSON result object")
                    except ValueError as exc:
                        raise RuntimeError("Invalid measurement result; see " + str(directory)) from exc
                    passed = proc.returncode == expected_code and payload.get("status") == expected_status
                    rows.append({"model": model, "repetition": i + 1, "stage": stage,
                                 "elapsed_ms": round(elapsed, 3), "exit_code": proc.returncode,
                                 "status": payload.get("status"), "expected_status": expected_status,
                                 "passed": passed, "model_sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                 "command": [str(a) for a in argv], "evidence": str(directory.relative_to(ROOT))})
                    if not passed:
                        raise RuntimeError("Unexpected exit code or status; see " + str(directory))
    except (OSError, ValueError, RuntimeError) as exc:
        error = str(exc)
    summary = []
    for model, stage in sorted({(r["model"], r["stage"]) for r in rows if r["passed"]}):
        times = [r["elapsed_ms"] for r in rows if r["passed"] and r["model"] == model and r["stage"] == stage]
        summary.append({"model": model, "stage": stage, "n": len(times),
                        "median_ms": statistics.median(times), "min_ms": min(times), "max_ms": max(times)})
    status = "FAIL" if error else "PASS"
    result = {"status": status, "error": error, "platform": platform.platform(),
              "processor": platform.processor(), "logical_cpus": os.cpu_count(), "python": sys.version,
              "methodology": "Serial wall-clock subprocess timings. Prebuilt CLI; each proof run has a fresh Lean directory and no shared .lake cache. Excludes toolchain installation. OS caching uncontrolled. Failed workflows retain partial evidence; their summaries are incomplete.",
              "peak_memory": "Not measured: portable per-process-tree peak collection is not implemented.",
              "repetitions": args.repetitions, "rows": rows, "summary": summary, "evidence_directory": str(out)}
    data = json.dumps(result, indent=2) + "\n"
    (out / "timings.json").write_text(data, encoding="utf-8")
    (ROOT / "reports/timings.json").write_text(data, encoding="utf-8")
    print(json.dumps({"status": status, "error": error, "output": str(out), "summary": summary}, indent=2))
    return 1 if error else 0

if __name__ == "__main__":
    raise SystemExit(main())
