"""Model-revision demonstration.

The edited model examples/revisions/signed_dh_unchecked_signature.json differs from
examples/signed_dh_exchange.json in one line: after signature verification, the
responder's `invalid` branch continues to `validate` instead of rejecting.

The demonstration checks that
  1. the edited model is admitted, re-exported and its translation certificates
     regenerate and verify without any manual Lean change;
  2. the original scenario file is refused because its SHA-256 binding no longer
     matches (SCENARIO_ERROR);
  3. the rebound scenario file fails with CERTIFICATE_FAILED, and Lean rejects
     exactly the certificates that encoded the signature check: the step-20
     rejection event and the two rejection claims in both attack scenarios,
     while every honest-scenario certificate still holds.

It prints a JSON summary whose status is PASSED only if all three hold.
"""
from __future__ import annotations
from runtime_env import configured
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SCENARIOS = ROOT / "examples/scenarios/signed_dh_exchange.scenarios.json"
EDITED_MODEL = ROOT / "examples/revisions/signed_dh_unchecked_signature.json"
EDITED_SCENARIOS = ROOT / "examples/revisions/signed_dh_unchecked_signature.scenarios.json"
PROFILE = ROOT / "examples/restricted_symbolic_v1.profile.json"
EXPECTED_FAILURES = sorted(
    f"{scenario}_{claim}"
    for scenario in ("forged_share", "spliced_signature")
    for claim in ("event_20", "responder_rejected", "responder_target_rejected")
)


ERROR_LINE = re.compile(r"^error: .*?VAKE[\\/]Demo[\\/]Global\.lean:(\d+):\d+", re.MULTILINE)


def error_lines(log: str) -> list[str]:
    """Line numbers of Lean errors in the scenario module (POSIX or Windows paths)."""
    return ERROR_LINE.findall(log)


def failing_theorems(lean_dir: Path) -> list[str]:
    """Map Lean error positions in the scenario module to theorem names."""
    log = (lean_dir / "validation" / "build.log").read_text(encoding="utf-8", errors="replace")
    source = (lean_dir / "VAKE" / "Demo" / "Global.lean").read_text(encoding="utf-8").splitlines()
    names = set()
    for line in error_lines(log):
        text = source[int(line) - 1]
        match = re.match(r"\s*theorem\s+([A-Za-z0-9_]+)", text)
        names.add(match.group(1) if match else f"<line {line}>")
    return sorted(names)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="fresh output directory (default: reports/runs/revision-<time>)")
    args = parser.parse_args()
    out = (args.out or ROOT / "reports/runs" / ("revision-" + str(time.time_ns()))).resolve()
    if out.exists():
        parser.error("Output directory must be fresh")
    out.mkdir(parents=True)
    binary = Path(configured("VAKE") or ROOT / "target/debug" / ("vake.exe" if os.name == "nt" else "vake"))
    stages = []

    def invoke(name, argv, expected_status):
        proc = subprocess.run([str(a) for a in argv], cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out / (name + ".stdout.log")).write_text(proc.stdout, encoding="utf-8")
        (out / (name + ".stderr.log")).write_text(proc.stderr, encoding="utf-8")
        try:
            status = json.loads(proc.stdout).get("status")
        except ValueError:
            status = "INTERNAL_ERROR"
        passed = status == expected_status
        stages.append({"stage": name, "expected": expected_status, "status": status, "passed": passed,
                       "command": [str(a) for a in argv]})
        return passed

    ok = invoke("check", [binary, "check", EDITED_MODEL], "CHECKED")
    ok = ok and invoke("export", [binary, "export", EDITED_MODEL, "--profile", PROFILE, "--out", out / "export"], "EXPORTED")
    ok = ok and invoke("verify", [sys.executable, ROOT / "scripts/verify.py", "--export-dir", out / "export"],
                       "PROVED_UNDER_ASSUMPTIONS")
    ok = ok and invoke("stale-scenario-binding", [sys.executable, ROOT / "scripts/trace_demo.py", "--export-dir", out / "export",
                                                  "--out", out / "stale-traces", "--scenarios", ORIGINAL_SCENARIOS], "SCENARIO_ERROR")
    ok = ok and invoke("rebound-traces", [sys.executable, ROOT / "scripts/trace_demo.py", "--export-dir", out / "export",
                                          "--out", out / "traces", "--scenarios", EDITED_SCENARIOS], "CERTIFICATE_FAILED")
    failures: list[str] = []
    if ok:
        failures = failing_theorems(out / "traces" / "lean-check")
        ok = failures == EXPECTED_FAILURES
    result = {"status": "PASSED" if ok else "FAILED", "edited_model": str(EDITED_MODEL.relative_to(ROOT)),
              "change": "Responder.checkSignature: invalid branch continues to validate instead of fail",
              "rejected_certificates": failures, "expected_rejected_certificates": EXPECTED_FAILURES,
              "stages": stages, "output": str(out), "security_conclusion": "none"}
    (out / "revision-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
