"""Fresh per-run Lean workspaces backed by a content-addressed library cache.

Every verification run still gets its own copy of the Lean sources, so generated
modules, audits and logs never leak between runs. What is reused is the compiled
reusable library (`lake build VAKE`): it is built once per distinct library
fingerprint and its `.lake` directory is copied into each new workspace. Lake then
re-validates every module against its source hash, so an edited library file is
rebuilt in the workspace rather than served stale from the cache.

The fingerprint covers the Lean version, the Lake configuration and every library
source file (generated, imported, demo and audit files are excluded). Set
VAKE_LEAN_CACHE=0 for a clean-room run that rebuilds the library from source, and
VAKE_CACHE_DIR to relocate the cache (default: <repository>/.vake-cache).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUN_LOCAL = ("Imported", "Generated", "Demo", "validation")
RUN_LOCAL_FILES = ("Audit.lean", "SignatureObservations.lean", "Debug.lean")
CONFIG_FILES = ("lakefile.toml", "lean-toolchain", "lake-manifest.json")


def ignore_run_local(directory: str, names: list[str]) -> set[str]:
    return {n for n in names if n == ".lake" or n in RUN_LOCAL or n in RUN_LOCAL_FILES}


def library_files(lean_dir: Path) -> list[Path]:
    files = [lean_dir / name for name in CONFIG_FILES if (lean_dir / name).is_file()]
    for path in sorted(lean_dir.rglob("*.lean")):
        parts = path.relative_to(lean_dir).parts
        if ".lake" in parts or any(p in RUN_LOCAL for p in parts) or path.name in RUN_LOCAL_FILES:
            continue
        files.append(path)
    return files


def fingerprint(lean_dir: Path, lean_version: str) -> str:
    digest = hashlib.sha256()
    digest.update(b"vake-lean-library-cache-v1\0" + lean_version.strip().encode() + b"\0")
    for path in library_files(lean_dir):
        data = path.read_bytes()
        digest.update(path.relative_to(lean_dir).as_posix().encode() + b"\0")
        digest.update(str(len(data)).encode() + b"\0" + data)
    return digest.hexdigest()


def cache_enabled() -> bool:
    return os.environ.get("VAKE_LEAN_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def cache_root() -> Path:
    configured = os.environ.get("VAKE_CACHE_DIR")
    return (Path(configured) if configured else ROOT / ".vake-cache") / "lean"


def _run(command: list[str], cwd: Path, log: Path | None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = str(Path(command[0]).resolve().parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run([str(c) for c in command], cwd=cwd, env=env, text=True, encoding="utf-8",
                          errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(proc.stdout, encoding="utf-8")
    return proc


def _ensure_cache_entry(isolated: Path, lake: str, key: str, log: Path | None) -> tuple[str, Path | None, str | None]:
    root = cache_root()
    entry = root / key
    if (entry / ".lake").is_dir() and (entry / "cache-entry.json").is_file():
        return "hit", entry, None
    try:
        root.mkdir(parents=True, exist_ok=True)
        staging = root / f"{key}.tmp-{os.getpid()}-{time.time_ns()}"
        shutil.copytree(isolated, staging, ignore=ignore_run_local)
    except OSError as exc:
        return "unavailable", None, f"cache directory not writable: {exc}"
    proc = _run([lake, "build", "VAKE"], staging, log)
    if proc.returncode:
        shutil.rmtree(staging, ignore_errors=True)
        return "build_failed", None, "library build failed; see log"
    (staging / "cache-entry.json").write_text(json.dumps({
        "fingerprint": key, "created_unix": int(time.time()),
        "files": [p.relative_to(isolated).as_posix() for p in library_files(isolated)],
    }, indent=2) + "\n", encoding="utf-8")
    try:
        os.replace(staging, entry)
    except OSError:
        # Another run populated the same entry first; both copies are equivalent.
        shutil.rmtree(staging, ignore_errors=True)
        if not (entry / ".lake").is_dir():
            return "unavailable", None, "cache entry could not be installed"
    return "built", entry, None


def seed_library(isolated: Path, lake: str, log: Path | None = None) -> dict:
    """Copy the cached library build into an existing fresh workspace without `.lake`."""
    if not cache_enabled():
        return {"library_cache": "disabled"}
    if (isolated / ".lake").exists():
        raise RuntimeError("Workspace already has a .lake directory")
    version = _run([lake, "env", "lean", "--version"], isolated, None)
    if version.returncode:
        return {"library_cache": "unavailable", "reason": "lean --version failed"}
    key = fingerprint(isolated, version.stdout)
    status, entry, reason = _ensure_cache_entry(isolated, lake, key, log)
    record = {"library_cache": status, "library_fingerprint": key}
    if reason:
        record["reason"] = reason
    if entry is not None:
        shutil.copytree(entry / ".lake", isolated / ".lake", symlinks=True)
        record["cache_entry"] = str(entry)
    return record


def prepare(source_lean: Path, isolated: Path, lake: str, log: Path | None = None) -> dict:
    """Create a fresh workspace at `isolated`; seed its library build from the cache."""
    if isolated.exists():
        raise RuntimeError("Lean work directory already exists; use a fresh output directory")
    shutil.copytree(source_lean, isolated, ignore=ignore_run_local)
    return seed_library(isolated, lake, log)
