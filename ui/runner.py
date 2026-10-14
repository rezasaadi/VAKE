from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from scripts.runtime_env import configured

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 2 * 1024 * 1024
EXAMPLES = {"nonce_exchange": "nonce_exchange.json", "type_mismatch": "negative/type_mismatch.json", "signature_check": "signature_check.json"}
PROFILE = "restricted_symbolic_v1.profile.json"
ID_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}")
SUCCESS = {"check": "CHECKED", "export": "EXPORTED", "verify": "PROVED_UNDER_ASSUMPTIONS", "trace": "PROVED_UNDER_ASSUMPTIONS", "controls": "PASSED"}
AUDIT = "export/lean-check/validation/proof-audit.json"

def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def dump(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(dump(value))
    temp.replace(path)

def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def safe(root, relative):
    parts = Path(relative)
    if parts.is_absolute() or ".." in parts.parts or ":" in relative or "\\" in relative:
        raise ValueError("Unsafe relative path")
    if root.is_symlink():
        raise ValueError("Symlink run root")
    path = root
    for part in parts.parts:
        path = path / part
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Symlink/junction artifacts are not served")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Artifact is outside its run")
    return path

def stop_tree(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=15)

class Store:
    def __init__(self, root=ROOT, runs=None, timeout=600, binary=None, environment=None):
        self.root = Path(root).resolve()
        self.runs = Path(runs or self.root / "reports/ui-runs")
        if self.runs.is_symlink():
            raise ValueError("Run storage must not be a symlink")
        self.runs.mkdir(parents=True, exist_ok=True)
        self.runs = self.runs.resolve()
        self._lock_file = (self.runs / ".server.lock").open("a+b")
        try:
            self._lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                if self._lock_file.read(1) == b"":
                    self._lock_file.write(b"0")
                    self._lock_file.flush()
                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock_file.close()
            raise ValueError("Run storage is already in use by another UI server")
        self.timeout = timeout
        self.binary = str(binary or self.root / "target/debug" / ("vake.exe" if os.name == "nt" else "vake"))
        self.env = dict(os.environ if environment is None else environment)
        self.env["VAKE_ROOT"] = str(self.root)
        self.env["VAKE_PYTHON"] = sys.executable
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vake-ui")
        self.processes = set()
        self.stopping = False
        for path in self.runs.iterdir():
            if ID_RE.fullmatch(path.name) and not path.is_symlink():
                state = read_json(path / "state.json")
                if state and state.get("job", {}).get("state") in ("queued", "running"):
                    name = state["job"]["stage"]
                    record = {"name": name, "status": "INCONCLUSIVE", "exit_code": None,
                              "message": "Server stopped before completion; create a new run to retry.",
                              "finished_at_utc": now()}
                    stage = safe(path, "stages/" + name)
                    stage.mkdir(parents=True, exist_ok=True)
                    if not (stage / "result.json").exists():
                        write_json(stage / "result.json", record)
                    state["job"] = {"stage": name, "state": "failed"}
                    write_json(path / "state.json", state)
                    self.refresh(path.name)

    def directory(self, run_id):
        if not ID_RE.fullmatch(run_id):
            raise ValueError("Invalid run ID")
        path = safe(self.runs, run_id)
        if not path.is_dir():
            raise FileNotFoundError("Unknown run")
        return path

    def examples(self):
        return [{"id": key, "filename": rel,
                 "model": (self.root / "examples" / rel).read_text(encoding="utf-8"),
                 "profile": (self.root / "examples" / PROFILE).read_text(encoding="utf-8")}
                for key, rel in EXAMPLES.items()]

    def create(self, body):
        example = body.get("example")
        if example is not None:
            if example not in EXAMPLES:
                raise ValueError("Unknown bundled example")
            model = (self.root / "examples" / EXAMPLES[example]).read_bytes()
        else:
            if not isinstance(body.get("model"), str):
                raise ValueError("Supply UTF-8 model text or a bundled example ID")
            model = body["model"].encode("utf-8")
        profile = body.get("profile")
        if profile is not None and not isinstance(profile, str):
            raise ValueError("Profile must be UTF-8 JSON text")
        profile = (self.root / "examples" / PROFILE).read_bytes() if profile is None else profile.encode("utf-8")
        if not model or len(model) > MAX_INPUT or not profile or len(profile) > MAX_INPUT:
            raise ValueError("Model and profile must each be between 1 byte and 2 MiB")

        try:
            parsed = json.loads(model)
            if not isinstance(parsed, dict): parsed = {}
        except (ValueError, RecursionError):
            parsed = {}
        protocol = parsed.get("protocol", {})
        protocol = protocol if isinstance(protocol, dict) else {}
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        path = self.runs / run_id
        path.mkdir()
        (path / "model.json").write_bytes(model)
        (path / "profile.json").write_bytes(profile)
        terminal = (model == (self.root / "examples/nonce_exchange.json").read_bytes()
                    and profile == (self.root / "examples" / PROFILE).read_bytes())
        state = {"run_id": run_id, "created_at_utc": now(), "model_name": protocol.get("id", "Unparsed input"),
                 "schema": parsed.get("format_version"), "source_sha256": sha(model), "profile_sha256": sha(profile),
                 "example": example, "terminal_demo_eligible": terminal, "job": {"state": "idle"},
                 "expected_check": {"status": "TYPE_ERROR", "exit_code": 1} if example == "type_mismatch" else None}
        write_json(path / "state.json", state)
        return self.refresh(run_id)

    def records(self, path):
        return [read_json(path / "stages" / name / "result.json")
                for name in SUCCESS if (path / "stages" / name / "result.json").is_file()]

    def start(self, run_id, name):
        if name not in SUCCESS:
            raise ValueError("Unknown action")
        with self.lock:
            path = self.directory(run_id)
            state = read_json(path / "state.json")
            if self.stopping:
                raise ValueError("Server is stopping")
            if (path / "stages" / name / "result.json").exists():
                return self.refresh(run_id)
            if state["job"]["state"] in ("queued", "running"):
                raise ValueError("This run already has a queued or running action")
            records = {r["name"]: r for r in self.records(path)}
            if name in ("export", "verify"):
                checked = records.get("check", {})
                if checked.get("status") not in ("CHECKED", "OPEN_OBLIGATION") or checked.get("exit_code") not in (0, 2):
                    raise ValueError("Complete input validation before export")
            if name == "verify":
                if records["check"]["status"] != "CHECKED":
                    raise ValueError("This input has open obligations; closed input is required for certificates")
                if records.get("export", {}).get("status") != "EXPORTED" or records["export"].get("exit_code") != 0:
                    raise ValueError("Complete export before Lean verification")
            if name in ("trace", "controls"):
                if records.get("verify", {}).get("status") != "PROVED_UNDER_ASSUMPTIONS" or records["verify"].get("exit_code") != 0:
                    raise ValueError("Complete Lean verification before demonstration checks")
                if not state["terminal_demo_eligible"]:
                    raise ValueError("Demonstration checks require the exact bundled nonce model and profile")
            stage = path / "stages" / name
            stage.mkdir(parents=True, exist_ok=False)
            (stage / "stdout.log").touch()
            (stage / "stderr.log").touch()
            state["job"] = {"stage": name, "state": "queued", "queued_at_utc": now()}
            write_json(path / "state.json", state)
            self.executor.submit(self.execute, run_id, name)
            return self.refresh(run_id)

    def command(self, path, name, state):
        if name == "check":
            return [self.binary, "check", str(path / "model.json")]
        if name == "export":
            return [self.binary, "export", str(path / "model.json"), "--profile", str(path / "profile.json"),
                    "--out", str(path / "export")]
        if name == "trace":
            return [sys.executable, str(self.root / "scripts/trace_demo.py"), "--export-dir", str(path / "export"), "--out", str(path / "traces")]
        if name == "controls":
            verified = read_json(path / "export/verification-result.json", {})
            return [sys.executable, str(self.root / "scripts/test_negative_bindings.py"),
                    "--lean-dir", str(path / "export/lean-check"), "--proof-module", verified["proof_module"],
                    "--out", str(path / "controls"), "--lake", self.env.get("VAKE_LAKE") or "lake"]
        command = [sys.executable, str(self.root / "scripts/verify.py"), "--export-dir", str(path / "export")]
        if (state["terminal_demo_eligible"]
                and (path / "model.json").read_bytes() == (self.root / "examples/nonce_exchange.json").read_bytes()
                and (path / "profile.json").read_bytes() == (self.root / "examples" / PROFILE).read_bytes()):
            command.append("--terminal-demo")
        if ((path / "model.json").read_bytes() == (self.root / "examples/signature_check.json").read_bytes()
                and (path / "profile.json").read_bytes() == (self.root / "examples" / PROFILE).read_bytes()):
            command.append("--signature-demo")
        return command

    def invoke(self, command, cwd, out, err, timeout):
        with out.open("wb") as stdout, err.open("wb") as stderr:
            process = subprocess.Popen(command, cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, shell=False,
                                       start_new_session=os.name != "nt")
            with self.lock:
                self.processes.add(process)
                stopping = self.stopping
            try:
                if stopping:
                    stop_tree(process)
                    return process.returncode, True
                try:
                    return process.wait(timeout=timeout), False
                except subprocess.TimeoutExpired:
                    stop_tree(process)
                    return process.returncode, True
            finally:
                with self.lock:
                    self.processes.discard(process)

    def execute(self, run_id, name):
        path = self.directory(run_id)
        stage = path / "stages" / name
        start = time.monotonic()
        state = read_json(path / "state.json")
        record = {"name": name, "cwd": str(self.root),
                  "started_at_utc": now(), "status": "INCONCLUSIVE", "exit_code": None,
                  "stdout_file": "stages/" + name + "/stdout.log", "stderr_file": "stages/" + name + "/stderr.log"}
        try:
            command = self.command(path, name, state)
            record["command"] = command
            with self.lock:
                state["job"].update(state="running", started_at_utc=record["started_at_utc"])
                write_json(path / "state.json", state)
            if sha((path / "model.json").read_bytes()) != state["source_sha256"] or sha((path / "profile.json").read_bytes()) != state["profile_sha256"]:
                raise ValueError("Saved input identity changed; refusing execution")
            if name == "check":
                versions = {"python": sys.version.splitlines()[0]}
                for tool, argv in (("vake", [self.binary, "--version"]), ("rust", [self.env.get("VAKE_RUSTC") or "rustc", "--version"])):
                    try:
                        code, timed = self.invoke(argv, self.root, stage / (tool + "-version.stdout.log"),
                                                  stage / (tool + "-version.stderr.log"), min(self.timeout, 15))
                        versions[tool] = {"command": argv, "exit_code": code, "timed_out": timed,
                                          "output": (stage / (tool + "-version.stdout.log")).read_text(encoding="utf-8", errors="replace").strip()}
                    except OSError as error:
                        versions[tool] = {"error": str(error), "command": argv}
                write_json(path / "tool-versions.json", versions)
            code, timed = self.invoke(command, self.root, stage / "stdout.log", stage / "stderr.log", self.timeout)
            record["exit_code"] = code
            try:
                payload = json.loads((stage / "stdout.log").read_text(encoding="utf-8"))
                if not isinstance(payload, dict): raise ValueError("Expected JSON object")
            except ValueError:
                payload = {"status": "INTERNAL_ERROR", "message": "No JSON result; inspect stdout and stderr"}
            record["output"] = payload
            record["status"] = "INCONCLUSIVE" if timed else payload.get("status", "INTERNAL_ERROR")
            if timed:
                record["message"] = "Timeout or server shutdown; process tree stopped. No security conclusion."
            expected = state.get("expected_check") if name == "check" else None
            record["expected"] = expected or {"status": SUCCESS[name], "exit_code": 0}
            record["meets_expected"] = not timed and code == record["expected"]["exit_code"] and record["status"] == record["expected"]["status"]
            if name == "verify":
                versions = read_json(path / "tool-versions.json", {})
                versions["lean"] = payload.get("theorem_audit", {}).get("lean_version", "Unavailable; inspect verification logs")
                write_json(path / "tool-versions.json", versions)
        except Exception as error:
            record.update(status="INTERNAL_ERROR", message=str(error), meets_expected=False)
        record["finished_at_utc"] = now()
        record["elapsed_ms"] = round((time.monotonic() - start) * 1000)
        with self.lock:
            write_json(stage / "result.json", record)
            state = read_json(path / "state.json")
            state["job"].update(state="completed" if record.get("meets_expected") else "failed",
                                finished_at_utc=record["finished_at_utc"])
            write_json(path / "state.json", state)
            self.refresh(run_id)

    def refresh(self, run_id):
        with self.lock:
            path = self.directory(run_id)
            state = read_json(path / "state.json")
            records = self.records(path)
            stages = {r["name"]: r for r in records}
            check, export, verify = (stages.get(name, {}) for name in ("check", "export", "verify"))
            result = {"run_id": run_id, "frontend_status": check.get("status", "NOT_CHECKED"),
                      "export_status": export.get("status", "NOT_EXPORTED"),
                      "export_proof_status": export.get("output", {}).get("proof_status", "NOT_CHECKED"),
                      "certificate_status": verify.get("status", "NOT_CHECKED"),
                      "compilation_status": verify.get("output", {}).get("compilation_status", "NOT_CHECKED"),
                      "security_status": "OPEN_OBLIGATION", "security_conclusion": "none",
                      "proof_scope": verify.get("output", {}).get("proof_scope", "No certificate checked"),
                      "terminal_demo": verify.get("output", {}).get("terminal_demo", False),
                      "negative_binding_controls": stages.get("controls", {}).get("status", "NOT_RUN"),
                      "trace_status": stages.get("trace", {}).get("status", "NOT_RUN"),
                      "trust_boundary": ["Rust parser/type checker/exporter", "Independent Python source importer",
                                         "Selected symbolic profile and semantics", "Lean kernel and audited logical axioms"]}
            audit = read_json(safe(path, AUDIT)) if verify.get("status") == "PROVED_UNDER_ASSUMPTIONS" and verify.get("exit_code") == 0 else None
            result["theorem_count"] = len(audit["theorems"]) if audit else None
            result["axioms_used"] = audit.get("axioms_used") if audit else None
            write_json(path / "ui-result.json", result)
            (path / "results.md").write_text("# VAKE run " + run_id + "\n\n" +
                "\n".join("- " + key + ": " + str(value) for key, value in result.items()) +
                "\n\nAuthentication, secrecy, replay resistance, active-attacker search, secure erasure and computational security are not proved.\n",
                encoding="utf-8")
            missing = []
            if verify:
                for rel in ("export/verification-result.json", "export/verification-logs/lean-version.log",
                            "export/verification-logs/independent-import.log", "export/verification-logs/lean-build.log",
                            "export/verification-logs/axiom-validation.log", AUDIT, "export/lean-check/validation/axioms.log"):
                    if not safe(path, rel).is_file():
                        missing.append({"path": rel, "status": "MISSING", "reason": "Stage failed, was interrupted, or did not produce this evidence"})
            artifacts = []
            for directory, dirs, names in os.walk(path, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in (".lake", "__pycache__") and not Path(directory, d).is_symlink())
                for filename in sorted(names):
                    p = Path(directory, filename)
                    rel = p.relative_to(path).as_posix()
                    if rel == "run-manifest.json" or p.suffix not in (".json", ".lean", ".log", ".md", ".toml") and filename != "lean-toolchain":
                        continue
                    try: data = safe(path, rel).read_bytes()
                    except (ValueError, OSError): continue
                    artifacts.append({"id": sha(rel.encode())[:24], "path": rel, "sha256": sha(data), "bytes": len(data)})
            artifacts.sort(key=lambda a: a["path"])
            manifest = {**state, "tool_versions": read_json(path / "tool-versions.json", {}),
                        "stages": records, "result": result, "missing_evidence": missing,
                        "artifacts": artifacts, "security_status": "OPEN_OBLIGATION", "security_conclusion": "none"}
            write_json(path / "run-manifest.json", manifest)
            trace = read_json(path / "traces/trace-result.json") if stages.get("trace", {}).get("status") == "PROVED_UNDER_ASSUMPTIONS" and stages["trace"].get("exit_code") == 0 else None
            return {**manifest, "audit": audit, "trace": trace,
                    "trace_audit": read_json(path / "traces/lean-check/validation/proof-audit.json") if trace else None,
                    "controls": read_json(path / "controls/negative-binding-results.json") if "controls" in stages else None}

    def history(self):
        with self.lock:
            return [read_json(p / "state.json") for p in sorted(self.runs.iterdir(), reverse=True)
                    if ID_RE.fullmatch(p.name) and not p.is_symlink() and (p / "state.json").is_file()]

    def artifact(self, run_id, file_id):
        manifest = self.refresh(run_id)
        row = next((a for a in manifest["artifacts"] if a["id"] == file_id), None)
        if not row: raise FileNotFoundError("Artifact is not in this run's manifest")
        return safe(self.directory(run_id), row["path"]), row

    def normalized(self, value, path):

        replacements = [(str(path), "reports/ui-runs/" + path.name),
                        (str(self.root), "."), (str(Path(sys.executable)), "<PYTHON>"),
                        (str(self.env.get("VAKE_LAKE", "")), "<LAKE>"),
                        (str(Path.home()), "<HOME>")]
        if isinstance(value, dict): return {k: self.normalized(v, path) for k, v in value.items()}
        if isinstance(value, list): return [self.normalized(v, path) for v in value]
        if not isinstance(value, str): return value
        for original, replacement in replacements:
            if not original: continue
            if not os.path.isabs(original) and "/" not in original and "\\" not in original:
                if value == original:
                    return replacement
                continue
            for form in (original, original.replace("\\", "/")):
                value = value.replace("\\\\?\\" + form, replacement).replace(form, replacement)
                value = value.replace(json.dumps(form)[1:-1], replacement)
        value = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+", "<HOME>", value)
        value = re.sub(r"/(?:home|Users)/[^/\s\"']+", "<HOME>", value)
        return value

    def bundle(self, run_id):
        with self.lock:
            manifest = self.refresh(run_id)
            if manifest["job"]["state"] in ("queued", "running"):
                raise ValueError("Wait for the active stage to finish before downloading evidence")
            path = self.directory(run_id)
            output = io.BytesIO()
            rows = []
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for row in manifest["artifacts"]:
                    original = safe(path, row["path"]).read_bytes()
                    data = original
                    immutable = row["path"] in ("model.json", "profile.json", "export/model.json", "export/operational-profile.json", "export/operational-ast.json") or row["path"].endswith(".lean")
                    if not immutable:
                        try: data = dump(self.normalized(json.loads(data), path))
                        except (ValueError, UnicodeError): data = self.normalized(data.decode("utf-8"), path).encode("utf-8")
                    if re.search(rb"[A-Za-z]:[\\/]+Users[\\/]", data) or re.search(rb"/(?:home|Users)/", data):
                        raise ValueError("A semantic artifact contains a home path; bundle withheld to preserve both privacy and exact input bytes")
                    rows.append({**row, "original_sha256": row["sha256"], "sha256": sha(data),
                                 "bytes": len(data), "path_normalized": data != original})
                    info = zipfile.ZipInfo(row["path"], date_time=(2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, data)
                shared_manifest = self.normalized(manifest, path)
                shared_manifest["artifacts"] = rows
                shared_manifest["bundle_note"] = "Metadata/log paths normalized in copies. original_sha256 identifies unchanged local originals; sha256 identifies bundle bytes. Semantic inputs and Lean sources are byte-preserved. Manifest excludes itself."
                info = zipfile.ZipInfo("run-manifest.json", date_time=(2026, 1, 1, 0, 0, 0))
                archive.writestr(info, dump(shared_manifest))
            return output.getvalue()

    def close(self):
        with self.lock:
            self.stopping = True
            processes = list(self.processes)
        for process in processes:
            stop_tree(process)
        self.executor.shutdown(wait=True)
        self._lock_file.close()
