from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime_env import configured
from ui.runner import Store

def load_script(name):
    spec = importlib.util.spec_from_file_location("source_test_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class SourceConsistencyTests(unittest.TestCase):
    def test_environment_configuration_and_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(configured("LAKE", "fallback"), "fallback")
            with patch.dict("os.environ", {"VAKE_LAKE": "selected-lake"}):
                self.assertEqual(configured("LAKE"), "selected-lake")

    def test_archive_preflight_and_tampered_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            clean = Path(temporary) / "VAKE"
            proc = subprocess.run([sys.executable, str(ROOT / "scripts/package.py"), "--clean-dir", str(clean)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            command = [sys.executable, str(clean / "scripts/repository_preflight.py")]
            proc = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(result["status"], "PASS")
            self.assertIn("Source archive", result["source_selection"])
            path = clean / "src/lib.rs"
            path.write_text(path.read_text() + "\n// changed after packaging\n")
            proc = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertTrue(any(row["issue"] == "manifest fingerprint mismatch" for row in json.loads(proc.stdout)["findings"]))

    def test_preflight_rejects_broken_local_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            clean = Path(temporary)
            scripts = clean / "scripts"
            scripts.mkdir()
            for name in ("repository_preflight.py", "package.py"):
                shutil.copy2(ROOT / "scripts" / name, scripts / name)
            (clean / "README.md").write_text("[Missing guide](docs/absent.md)\n")
            proc = subprocess.run([sys.executable, str(scripts / "repository_preflight.py")], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            findings = json.loads(proc.stdout)["findings"]
            self.assertTrue(any(row["issue"] == "broken local Markdown link" for row in findings))

    def test_bare_lake_normalization_preserves_filenames(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(runs=Path(temporary) / "runs", environment={"VAKE_LAKE": "lake"})
            try:
                rid = store.create({"example": "nonce_exchange"})["run_id"]
                normalized = store.normalized({"command": ["lake", "build"], "file": "lean/lake-manifest.json"}, store.directory(rid))
                self.assertEqual(normalized["command"], ["<LAKE>", "build"])
                self.assertEqual(normalized["file"], "lean/lake-manifest.json")
            finally:
                store.close()

    def test_ui_wrapper_works_outside_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = subprocess.run(["bash", str(ROOT / "scripts/run-ui.sh"), "--help"], cwd=temporary,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("--port", proc.stdout)

    def measurement(self, output=None, launch_error=None):
        module = load_script("measure")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "examples").mkdir()
            (root / "examples/nonce_exchange.json").write_bytes(b"{}")
            outcome = subprocess.CompletedProcess([], 0, output or "{}", "")
            with patch.object(module, "ROOT", root), patch.object(sys, "argv", ["measure.py", "--repetitions", "1"]), \
                 patch.object(module.subprocess, "run", side_effect=launch_error, return_value=outcome), redirect_stdout(io.StringIO()):
                code = module.main()
            return code, json.loads((root / "reports/timings.json").read_text())

    def test_measurement_rejects_success_exit_with_wrong_status(self):
        code, result = self.measurement('{"status":"INTERNAL_ERROR"}')
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["rows"][0]["passed"])
        self.assertEqual(result["summary"], [])

    def test_measurement_retains_launch_failure(self):
        code, result = self.measurement(launch_error=FileNotFoundError("missing CLI"))
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing CLI", result["error"])

    def test_measurement_retains_non_object_failure(self):
        code, result = self.measurement('[]')
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Invalid measurement result", result["error"])

if __name__ == "__main__":
    unittest.main()
