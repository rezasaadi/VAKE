import importlib.util
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("differential_test", ROOT / "scripts" / "differential_test.py")
DT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DT)

TARGET = '''import VAKE.Target.Global
namespace VAKE.Generated.Mx
def program : Target.Program :=
⟨"P", [⟨"a", [("x", (.input "v")), ("y", (.clear "w"))], (.halt "done")⟩, ⟨"b", [], (.goto "a")⟩]⟩
def environment : Environment :=
⟨"restricted_symbolic_v1", "stuck_unexpected", [], ["Alice", "Bob"], [], "ideal", []⟩
end VAKE.Generated.Mx
'''


class DifferentialTests(unittest.TestCase):
    def test_variants_are_deterministic_and_change_the_seed(self):
        seed = json.loads((ROOT / "examples/nonce_exchange.json").read_text(encoding="utf-8"))
        a = DT.encode(DT.variant(seed, random.Random(5)), random.Random(5))
        b = DT.encode(DT.variant(seed, random.Random(5)), random.Random(5))
        self.assertEqual(a, b)
        self.assertNotEqual(json.loads(a), seed)

    def test_list_elements_respect_nesting_and_strings(self):
        text = '[⟨"a,]", [1, 2]⟩, (f "x"), "y"]'
        elems = DT.list_elements(text, 0)
        self.assertEqual([text[s:e].strip() for s, e in elems], ['⟨"a,]", [1, 2]⟩', '(f "x")', '"y"'])

    def test_every_mutation_changes_only_the_expected_definition(self):
        for seed in range(40):
            mutated, operator, expected = DT.mutate(TARGET, random.Random(seed))
            self.assertNotEqual(mutated, TARGET, operator)
            program_changed = mutated.split("def environment")[0] != TARGET.split("def environment")[0]
            self.assertEqual(expected, "binding" if program_changed else "profile_binding", operator)
            self.assertEqual(mutated.count("⟨") - mutated.count("⟩"), 0, operator)

    def test_error_locations_accept_posix_and_windows_paths(self):
        log = "\n".join(["error: VAKE/Generated/Babc.lean:8:217: rfl failed",
                         "error: VAKE\\Generated\\Mdef.lean:3:1: elaboration",
                         "error: C:\\run\\ws\\VAKE\\Generated\\Bghi.lean:9:2: rfl failed",
                         "warning: VAKE/Generated/Bjkl.lean:1:1: not an error"])
        self.assertEqual(DT.error_locations(log), [("VAKE/Generated/Babc.lean", 8), ("VAKE/Generated/Mdef.lean", 3),
                                                   ("VAKE/Generated/Bghi.lean", 9)])

    def test_mixed_batch_rechecks_modules_without_generated_diagnostics(self):
        for code in (0, 1):
            with self.subTest(confirmation_exit_code=code), tempfile.TemporaryDirectory() as temporary:
                workspace = Path(temporary)
                proof = workspace / "VAKE/Generated/Bknown.lean"
                proof.parent.mkdir(parents=True)
                proof.write_text("namespace Review\ntheorem binding : False := by rfl\n", encoding="utf-8")
                batch = subprocess.CompletedProcess([], 1,
                    "error: VAKE/Generated/Bknown.lean:2:1: rfl failed\n"
                    "error: VAKE/Imported/Mother.lean:3:1: elaboration failed\nerror: build failed\n")
                confirmation = subprocess.CompletedProcess([], code, "dependency build result\n")
                with patch.object(DT, "run", side_effect=[batch, confirmation]) as run:
                    failures = DT.build(workspace, "lake", ["VAKE.Generated.Bknown", "VAKE.Generated.Bother"],
                                        workspace / "build.log")
                self.assertEqual(failures["VAKE.Generated.Bknown"], ["binding"])
                self.assertEqual("VAKE.Generated.Bother" in failures, code != 0)
                run.assert_called_with(["lake", "build", "VAKE.Generated.Bother"], workspace)

    def test_frontend_errors_and_empty_coverage_cannot_pass(self):
        cases = [(1, '{"status":"INTERNAL_ERROR"}', 2),
                 (1, 'frontend crashed', 2), (0, '[]', 2),
                 (0, '{"status":"UNKNOWN"}', 2),
                 (1, '{"status":"CHECKED"}', 2),
                 (0, '{"status":"TYPE_ERROR"}', 2),
                 (1, '{"status":"TYPE_ERROR"}', 0)]
        for code, stdout, expected_failures in cases:
            with self.subTest(code=code, stdout=stdout), tempfile.TemporaryDirectory() as temporary:
                out = Path(temporary) / "run"
                argv = ["differential_test.py", "--count", "2", "--mutants", "2", "--out", str(out)]
                with patch.object(sys, "argv", argv), \
                     patch.object(DT, "configured", side_effect=lambda name: sys.executable if name == "VAKE" else "lake"), \
                     patch.object(DT.lean_workspace, "prepare", return_value={}), \
                     patch.object(DT, "run", return_value=subprocess.CompletedProcess([], code, stdout)), \
                     redirect_stdout(io.StringIO()):
                    result = DT.main()
                summary = json.loads((out / "differential-result.json").read_text(encoding="utf-8"))
                self.assertEqual(result, 1)
                self.assertEqual(summary["status"], "FAILED")
                self.assertEqual(summary["frontend_failures"], expected_failures)
                self.assertEqual(summary["agreeing_exports"], 0)
                if expected_failures:
                    self.assertEqual((out / "variants/00000/check.log").read_text(encoding="utf-8"), stdout)

    def test_invalid_workload_is_rejected_before_creating_output(self):
        for flag, value in (("--count", "0"), ("--count", "-1"), ("--batch", "0"), ("--mutants", "-1")):
            with self.subTest(flag=flag, value=value), patch.object(sys, "argv", ["differential_test.py", flag, value]), \
                 patch.object(DT.lean_workspace, "prepare") as prepare, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    DT.main()
                self.assertEqual(error.exception.code, 2)
                prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
