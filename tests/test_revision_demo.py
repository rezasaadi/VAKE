import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "examples/signed_dh_exchange.json"
EDITED = ROOT / "examples/revisions/signed_dh_unchecked_signature.json"
SCENARIOS = ROOT / "examples/revisions/signed_dh_unchecked_signature.scenarios.json"
PROFILE = ROOT / "examples/restricted_symbolic_v1.profile.json"


def responder_arms(model):
    role = next(r for r in model["roles"] if r["id"] == "Responder")
    block = next(b for b in role["blocks"] if b["id"] == "checkSignature")
    return {arm["tag"]: arm["target_block"] for arm in block["terminator"]["arms"]}


class RevisionDemoTests(unittest.TestCase):
    def test_edited_model_changes_only_the_failed_signature_branch(self):
        original = json.loads(ORIGINAL.read_text(encoding="utf-8"))
        edited = json.loads(EDITED.read_text(encoding="utf-8"))
        self.assertEqual(responder_arms(original), {"ok": "validate", "invalid": "fail"})
        self.assertEqual(responder_arms(edited), {"ok": "validate", "invalid": "validate"})
        changed = [a for a, b in zip(ORIGINAL.read_text(encoding="utf-8").splitlines(),
                                     EDITED.read_text(encoding="utf-8").splitlines()) if a != b]
        self.assertEqual(len(changed), 1)

    def test_rebound_scenarios_match_the_edited_model_and_original_schedules(self):
        spec = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        self.assertEqual(spec["model_sha256"], hashlib.sha256(EDITED.read_bytes()).hexdigest())
        self.assertEqual(spec["profile_sha256"], hashlib.sha256(PROFILE.read_bytes()).hexdigest())
        original = json.loads((ROOT / "examples/scenarios/signed_dh_exchange.scenarios.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["scenarios"], original["scenarios"])

    def test_error_lines_accept_posix_and_windows_paths(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location("revision_demo", ROOT / "scripts" / "revision_demo.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        log = "\n".join(["error: VAKE/Demo/Global.lean:557:1107: rfl failed",
                         "error: VAKE\\Demo\\Global.lean:567:3: rfl failed",
                         "error: C:\\run\\lean-check\\VAKE\\Demo\\Global.lean:730:9: rfl failed",
                         "warning: VAKE/Demo/Global.lean:1:1: not an error"])
        self.assertEqual(module.error_lines(log), ["557", "567", "730"])


if __name__ == "__main__":
    unittest.main()
