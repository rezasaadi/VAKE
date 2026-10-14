import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_lean.py"
SPEC = importlib.util.spec_from_file_location("validate_lean", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

class ProofAuditTests(unittest.TestCase):
    name = "VAKE.Demo.test"

    def test_forbidden_axiom_is_rejected(self):
        log = f"{self.name} : True\n'{self.name}' depends on axioms: [sorryAx]"
        with self.assertRaisesRegex(ValueError, "Forbidden axiom"):
            AUDIT.parse_audits(log, [self.name])

    def test_missing_axiom_record_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing/duplicate axiom audit"):
            AUDIT.parse_audits(f"{self.name} : True", [self.name])

    def test_duplicate_axiom_record_is_rejected(self):
        entry = f"'{self.name}' does not depend on any axioms\n"
        with self.assertRaisesRegex(ValueError, "Missing/duplicate axiom audit"):
            AUDIT.parse_audits(f"{self.name} : True\n" + entry * 2, [self.name])

    def test_line_wrapped_statement_is_retained(self):
        statement = f"{self.name}\n  (p : Prop) : p -> p"
        result = AUDIT.parse_audits(statement + f"\n'{self.name}' does not depend on any axioms", [self.name])
        self.assertEqual(result[0]["statement"], statement)

    def test_valid_axiom_free_statement_is_retained(self):
        statement = f"{self.name} : True"
        result = AUDIT.parse_audits(statement + f"\n'{self.name}' does not depend on any axioms", [self.name])
        self.assertEqual(result[0]["statement"], statement)
        self.assertEqual(result[0]["axioms"], [])
        self.assertTrue(result[0]["kernel_checked"])

if __name__ == "__main__":
    unittest.main()