import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("lean_workspace", SCRIPTS / "lean_workspace.py")
WS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WS)


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class LibraryCacheTests(unittest.TestCase):
    base = {"lakefile.toml": "name = \"vake\"\n", "VAKE.lean": "import VAKE.Common\n",
            "VAKE/Common.lean": "def x := 1\n"}

    def test_fingerprint_ignores_run_local_files(self):
        with tempfile.TemporaryDirectory() as a:
            root = tree(Path(a), self.base)
            before = WS.fingerprint(root, "Lean 4.34.1")
            tree(root, {"VAKE/Generated/B0.lean": "theorem t : True := trivial\n",
                        "VAKE/Imported/S0.lean": "def y := 2\n", "VAKE/Audit.lean": "#check x\n",
                        ".lake/build/junk": "x"})
            self.assertEqual(before, WS.fingerprint(root, "Lean 4.34.1"))

    def test_fingerprint_tracks_library_sources_and_lean_version(self):
        with tempfile.TemporaryDirectory() as a:
            root = tree(Path(a), self.base)
            before = WS.fingerprint(root, "Lean 4.34.1")
            self.assertNotEqual(before, WS.fingerprint(root, "Lean 4.35.0"))
            tree(root, {"VAKE/Common.lean": "def x := 2\n"})
            self.assertNotEqual(before, WS.fingerprint(root, "Lean 4.34.1"))

    def test_disabled_cache_copies_sources_without_build_products(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            source = tree(Path(a), {**self.base, ".lake/build/x": "x", "VAKE/Generated/B0.lean": "-"})
            previous = os.environ.get("VAKE_LEAN_CACHE")
            os.environ["VAKE_LEAN_CACHE"] = "0"
            try:
                record = WS.prepare(source, Path(b) / "ws", "lake")
            finally:
                if previous is None:
                    os.environ.pop("VAKE_LEAN_CACHE")
                else:
                    os.environ["VAKE_LEAN_CACHE"] = previous
            self.assertEqual(record, {"library_cache": "disabled"})
            self.assertTrue((Path(b) / "ws/VAKE/Common.lean").is_file())
            self.assertFalse((Path(b) / "ws/.lake").exists())
            self.assertFalse((Path(b) / "ws/VAKE/Generated").exists())

    def test_existing_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as a:
            with self.assertRaisesRegex(RuntimeError, "fresh"):
                WS.prepare(Path(a), Path(a), "lake")


if __name__ == "__main__":
    unittest.main()
