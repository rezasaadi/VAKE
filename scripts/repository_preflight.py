from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote
import zipfile

from package import source_files

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {".git", "target", ".lake", ".vake-cache", "__pycache__", "node_modules"}
FORBIDDEN_PREFIXES = ("reports/", "artifact/validation-", "vake-reports-export/", "paper/build/", "paper/output/")
PATTERNS = {
    "obsolete project identity": re.compile(r"(?:ae(?:gi|ig)s|veri[\s_.-]*ake)", re.I),
    "private user path": re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+|/(?:home|Users)/)[A-Za-z0-9_.-]+", re.I),
    "GitHub credential": re.compile(r"(?:gh[pousr]_" + r"[A-Za-z0-9]{30,}|github_pat_" + r"[A-Za-z0-9_]{40,})"),
    "AWS access key": re.compile(r"(?:AKIA|ASIA)" + r"[A-Z0-9]{16}"),
    "private key": re.compile(r"-----BEGIN " + r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the result outside the tracked source snapshot")
    parser.add_argument("--working-tree", action="store_true", help="check current source files, including updates not yet added to Git")
    args = parser.parse_args()
    tracked_selection = (ROOT / ".git").exists() and not args.working_tree
    if tracked_selection:
        raw = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"])
        names = sorted(n.decode("utf-8") for n in raw.split(b"\0") if n)
        source_selection = "Git tracked files"
    else:
        names = sorted(p.relative_to(ROOT).as_posix() for p in source_files(ROOT))
        if (ROOT / "source-manifest.json").is_file():
            names.append("source-manifest.json")
        source_selection = "Working tree source files" if args.working_tree else "Source archive files, excluding build and run output"
    if not names:
        raise SystemExit("No source files found.")
    findings = []
    largest = 0
    hashes = []
    archive_members = 0

    def scan_text(label, data):
        if b"\0" in data:
            return
        try:
            body = data.decode("utf-8")
        except UnicodeDecodeError:
            return
        for kind, pattern in PATTERNS.items():
            if pattern.search(body):
                findings.append({"path": label, "issue": kind})
        return body

    for name in names:
        path = ROOT / name
        if PATTERNS["obsolete project identity"].search(name):
            findings.append({"path": name, "issue": "obsolete project identity in path"})
        if path.is_symlink() or not path.is_file():
            findings.append({"path": name, "issue": "missing file or symlink"})
            continue
        if FORBIDDEN_PARTS.intersection(Path(name).parts) or name.startswith(FORBIDDEN_PREFIXES) or path.name.startswith(".env") or path.suffix in {".pem", ".key", ".pyc"}:
            findings.append({"path": name, "issue": "generated/private file tracked"})
        data = path.read_bytes()
        largest = max(largest, len(data))
        if len(data) >= 100 * 1024 * 1024:
            findings.append({"path": name, "issue": "file reaches GitHub 100 MiB limit"})
        hashes.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        body = scan_text(name, data)
        if name.endswith(".md") and body:
            for target in re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", body):
                target = target.strip().split(' "', 1)[0].strip("<>")
                if not target or target.startswith("#") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                    continue
                target = unquote(target.split("#", 1)[0].split("?", 1)[0])
                candidate = ROOT / target.lstrip("/") if target.startswith("/") else path.parent / target
                if not candidate.exists():
                    findings.append({"path": name, "issue": "broken local Markdown link", "target": target})
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    archive_members += 1
                    if member.file_size > 100 * 1024 * 1024:
                        findings.append({"path": name, "issue": "oversized archive member"})
                        continue
                    if ".." in Path(member.filename).parts or member.filename.startswith(("/", "\\")):
                        findings.append({"path": name, "issue": "unsafe archive member path"})
                    if PATTERNS["obsolete project identity"].search(member.filename):
                        findings.append({"path": name, "issue": "obsolete project identity in archive path"})
                    scan_text(name + ":" + member.filename, archive.read(member))
    for manifest_name in ("docs/components.json", "source-manifest.json"):
        manifest_path = ROOT / manifest_name
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            seen = set()
            for row in manifest["files"]:
                relative = Path(row["path"])
                if relative.is_absolute() or ".." in relative.parts or ":" in row["path"] or "\\" in row["path"]:
                    raise ValueError("unsafe manifest path")
                if row["path"] in seen:
                    raise ValueError("duplicate manifest path")
                seen.add(row["path"])
                candidate = ROOT / relative
                if candidate.is_symlink() or not candidate.resolve().is_relative_to(ROOT.resolve()):
                    raise ValueError("manifest entry outside source tree")
                if not candidate.is_file():
                    findings.append({"path": manifest_name, "issue": "manifest references missing file", "target": row["path"]})
                    continue
                if tracked_selection and row["path"] not in names:
                    findings.append({"path": manifest_name, "issue": "manifest references untracked file", "target": row["path"]})
                data = candidate.read_bytes()
                if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                    findings.append({"path": manifest_name, "issue": "manifest fingerprint mismatch", "target": row["path"]})
            if manifest_name == "source-manifest.json":
                for missing in sorted(set(names) - {manifest_name} - seen):
                    findings.append({"path": manifest_name, "issue": "source file absent from manifest", "target": missing})
        except (OSError, ValueError, KeyError, TypeError) as error:
            findings.append({"path": manifest_name, "issue": "invalid source manifest", "message": str(error)})
    result = {
        "status": "PASS" if not findings else "FAIL",
        "scope": "Source hygiene, project identity, local Markdown links and manifest fingerprints; does not validate protocol security",
        "source_selection": source_selection,
        "source_files": len(names),
        "archive_members_scanned": archive_members,
        "largest_file_bytes": largest,
        "findings": findings,
        "files": hashes,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))
    return 0 if not findings else 1

if __name__ == "__main__":
    raise SystemExit(main())
