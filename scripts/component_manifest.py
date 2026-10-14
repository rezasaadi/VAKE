"""Refresh hashes for the checked-in VAKE implementation components."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def refresh(root=ROOT):
    root = Path(root)
    paths = [root / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml",
              "lean/lakefile.toml", "lean/lake-manifest.json", "lean/lean-toolchain")]
    for folder, suffix in (("src", ".rs"), ("lean", ".lean"), ("scripts", ".py"), ("scripts", ".in")):
        for path in (root / folder).rglob("*" + suffix):
            if any(part in {".lake", "Generated", "Imported", "Demo", "validation", "__pycache__"}
                   for part in path.relative_to(root).parts):
                continue
            if path.name in {"Audit.lean", "SignatureObservations.lean"}:
                continue
            paths.append(path)
    rows = []
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Components must be regular files: " + str(path))
        data = path.read_bytes()
        rows.append({"path": path.relative_to(root).as_posix(), "bytes": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()})
    result = {"schema_version": "1.0", "project": "VAKE", "package_version": "0.2.0",
              "scope": "Current checked-in Rust, Lean, workflow and toolchain components. File hashes are not execution or proof evidence.",
              "files": rows}
    destination = root / "docs/components.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    result = refresh()
    print(json.dumps({"status": "UPDATED", "component_count": len(result["files"]),
                      "manifest": "docs/components.json"}))
