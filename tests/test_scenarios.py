import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scenario_traces as st
from runtime_env import configured

BINARY = ROOT / "target/debug" / ("vake.exe" if os.name == "nt" else "vake")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

class ScenarioTests(unittest.TestCase):
    PROFILE = ROOT / "examples/restricted_symbolic_v1.profile.json"

    def test_bundled_scenarios_are_bound_to_bundled_examples(self):
        for model in ("nonce_exchange", "dh_exchange", "signed_dh_exchange"):
            found = st.matching(ROOT, (ROOT / "examples" / (model + ".json")).read_bytes(), self.PROFILE.read_bytes())
            self.assertEqual(found, ROOT / "examples/scenarios" / (model + ".scenarios.json"))
        self.assertIsNone(st.matching(ROOT, (ROOT / "examples/signature_check.json").read_bytes(), self.PROFILE.read_bytes()))

    def test_edited_model_is_not_matched(self):
        edited = (ROOT / "examples/nonce_exchange.json").read_bytes() + b"\n"
        self.assertIsNone(st.matching(ROOT, edited, self.PROFILE.read_bytes()))
        path = ROOT / "examples/scenarios/nonce_exchange.scenarios.json"
        with self.assertRaisesRegex(ValueError, "different model/profile"):
            st.load(path, hashlib.sha256(edited).hexdigest(), sha(self.PROFILE))

    def test_recipe_translation(self):
        recipe = {"encode": {"encoding": "c", "record": {"record": {"constructor": "Mk", "fields": [
            ["pub", {"field": {"of": {"call": {"primitive": "kg", "args": []}}, "name": "public"}}],
            ["n", {"atom": {"type": "Nonce", "name": "x\"y", "length": 1}}]]}}}}
        self.assertEqual(st.recipe(recipe),
            '(.encode "c" (.record "Mk" (.cons "pub" (.field (.call "kg" .nil) "public") '
            '(.cons "n" (.atom "Nonce" "x\\"y" (some 1)) .nil))))')
        self.assertEqual(st.recipe({"decode": {"sent": 2}}), "(.decode (.sent 2))")

    def test_unsupported_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported recipe kind"):
            st.recipe({"known": "v"})
        with self.assertRaisesRegex(ValueError, "natural number"):
            st.recipe({"sent": -1})
        with self.assertRaisesRegex(ValueError, "expected events"):
            st.actions({"actions": [{"advance": "A1", "events": []}]})
        with self.assertRaisesRegex(ValueError, "exactly one kind"):
            st.claim("p", "w", {"name": "c", "sent_count": 1, "no_resume": "A1"})

    def test_scenario_file_rejects_unknown_fields(self):
        spec = json.loads((ROOT / "examples/scenarios/dh_exchange.scenarios.json").read_text())
        spec["scenarios"][0]["extra"] = True
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.scenarios.json"
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "unknown field"):
                st.load(path, spec["model_sha256"], spec["profile_sha256"])

@unittest.skipUnless(configured("UI_TEST_LEAN") == "1", "Set VAKE_UI_TEST_LEAN=1 for real Lean integration")
class FalseClaimTests(unittest.TestCase):

    def check(self, model: str, scenario_name: str, claim: dict) -> dict:
        source = json.loads((ROOT / "examples/scenarios" / (model + ".scenarios.json")).read_text())
        scenario = next(s for s in source["scenarios"] if s["name"] == scenario_name)
        scenario["claims"] = [claim]
        source["scenarios"] = [scenario]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.scenarios.json").write_text(json.dumps(source))
            export = subprocess.run([str(BINARY), "export", str(ROOT / "examples" / (model + ".json")), "--profile",
                                     str(ROOT / "examples/restricted_symbolic_v1.profile.json"), "--out", str(d / "export")],
                                    capture_output=True, text=True)
            self.assertEqual(export.returncode, 0, export.stdout + export.stderr)
            proc = subprocess.run([sys.executable, str(ROOT / "scripts/trace_demo.py"), "--export-dir", str(d / "export"),
                                   "--out", str(d / "traces"), "--scenarios", str(d / "s.scenarios.json")],
                                  capture_output=True, text=True, timeout=900)
            self.assertNotEqual(proc.returncode, 0)
            return json.loads((d / "traces/trace-result.json").read_text())

    def test_false_key_agreement_in_mitm_is_rejected(self):
        result = self.check("dh_exchange", "mitm", {"name": "false_agreement", "same_key": [["I1", "iKey"], ["R1", "rKey"]]})
        self.assertEqual(result["status"], "CERTIFICATE_FAILED", result.get("message"))

    def test_nonexistent_message_indices_are_rejected(self):
        result = self.check("nonce_exchange", "malformed", {"name": "absent_messages", "sent_equal": [99, 100]})
        self.assertEqual(result["status"], "CERTIFICATE_FAILED", result.get("message"))

if __name__ == "__main__":
    unittest.main()
