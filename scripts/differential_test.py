"""Randomized differential testing of the Rust exporter against the Python importer.

For each trial the script derives a random variant of a bundled model, keeps it only
if the Rust frontend admits it, exports it (Rust: target definitions) and imports it
independently (Python: source definitions), and then asks Lean to check the per-export
`binding` and `profile_binding` certificates. Variants are built by composing:

  * consistent renaming of value, block and role identifiers to random legal names;
  * replacing literal values with adversarial ones (quotes, backslashes, control and
    C1 characters, non-BMP and combining characters, U+2028, BOM, u64 edge values);
  * inserting well-typed literal assignments (and erasures) into random blocks;
  * splitting blocks with an explicit jump;
  * shuffling declaration, role and block order;
  * re-encoding the JSON text (key order, indentation, \\uXXXX escapes).

Seeded bugs: for a sample of the agreeing exports, one type-correct mutation is applied
to the exporter's output (changed string, swapped constructor of the same shape,
reordered or dropped list element, changed environment field). Each mutant must be
rejected by Lean at `binding` or `profile_binding`.

Usage: python3 scripts/differential_test.py --count 200 --mutants 100 --seed 1
"""
from __future__ import annotations
from runtime_env import configured
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

import lean_workspace

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ["nonce_exchange.json", "public_message.json", "dh_exchange.json",
         "signed_dh_exchange.json", "signature_check.json"]
PROFILE = ROOT / "examples/restricted_symbolic_v1.profile.json"
BASE_TYPES = ["Bytes", "Bool", "Nat", "Principal", "RoleId", "SessionId", "SuiteId", "CredentialId", "Label"]
NAT_EDGES = [0, 1, 9, 10, 255, 256, 2**31 - 1, 2**32, 2**53 + 1, 2**63, 2**64 - 1]
TRICKY = (['"', "\\", "/", "'", "`", "\n", "\r", "\t", "\x00", "\x01", "\x1f", "\x7f", "\x80", "\x9f",
           "é", "ß", "λ", "中", "́", "‏", " ", "﻿", "￿",
           "\U0001f511", "\U0001d54a", " ", "{", "}", "[", "]", ":", ","]
          + list("abcXYZ019_.-"))


def random_id(rng: random.Random, taken: set[str]) -> str:
    while True:
        head = rng.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        tail = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789_.:/-") for _ in range(rng.randint(0, 24)))
        name = head + tail
        if name not in taken:
            taken.add(name)
            return name


def random_text(rng: random.Random) -> str:
    return "".join(rng.choice(TRICKY) for _ in range(rng.randint(0, 20)))


def random_literal(rng: random.Random, type_id: str):
    if type_id == "Bool":
        return rng.choice([True, False])
    if type_id == "Nat":
        return rng.choice(NAT_EDGES + [rng.randint(0, 2**64 - 1)])
    return random_text(rng)


def walk(node, visit, key=None):
    visit(node, key)
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, visit, k)
    elif isinstance(node, list):
        for v in node:
            walk(v, visit, key)


def rename(model: dict, ids: set[str], rng: random.Random, taken: set[str]) -> dict:
    """Consistently rename `ids` wherever a non-`kind` string field equals one of them."""
    mapping = {old: random_id(rng, taken) for old in sorted(ids) if rng.random() < 0.7}

    def fix(node):
        if isinstance(node, dict):
            return {k: (v if k in {"kind", "law_ids", "type_id", "family", "mode", "tag", "storage_kind"}
                        else fix(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [fix(v) for v in node]
        if isinstance(node, str):
            return mapping.get(node, node)
        return node
    return fix(model)


def literal_terms(model: dict) -> list[dict]:
    found = []
    walk(model, lambda n, k: found.append(n) if isinstance(n, dict) and n.get("kind") == "literal" else None)
    return found


def variant(seed: dict, rng: random.Random) -> dict:
    m = copy.deepcopy(seed)
    taken: set[str] = set()
    walk(m, lambda n, k: taken.add(n) if isinstance(n, str) else None)
    # 1. adversarial literal values
    for t in literal_terms(m):
        if rng.random() < 0.8:
            t["value"] = random_literal(rng, t["type_id"])
    # 2. inserted literal assignments
    declared = {t["id"] for t in m["types"]}
    for _ in range(rng.randint(0, 4)):
        type_id = rng.choice(BASE_TYPES)
        if type_id not in declared:
            m["types"].append({"id": type_id, "kind": "base", "parameters": [], "fields": [], "primitive_ref": None})
            declared.add(type_id)
        role = rng.choice(m["roles"])
        block = rng.choice(role["blocks"])
        value_id = random_id(rng, taken)
        m["values"].append({"id": value_id, "type_id": type_id, "owner_role": role["id"], "storage_kind": "local"})
        at = rng.randint(0, len(block["steps"]))
        steps = [{"kind": "assign", "output_value_id": value_id,
                  "term": {"kind": "literal", "type_id": type_id, "value": random_literal(rng, type_id)}}]
        if rng.random() < 0.5:
            steps.append({"kind": "erase", "object_id": value_id})
        block["steps"][at:at] = steps
    # 3. block splitting
    for _ in range(rng.randint(0, 2)):
        role = rng.choice(m["roles"])
        block = rng.choice(role["blocks"])
        if not block["steps"]:
            continue
        at = rng.randint(1, len(block["steps"]))
        new_id = random_id(rng, taken)
        role["blocks"].append({"id": new_id, "steps": block["steps"][at:], "terminator": block["terminator"]})
        block["steps"] = block["steps"][:at]
        block["terminator"] = {"kind": "jump", "target_block": new_id}
    # 4. renaming
    ids = {v["id"] for v in m["values"]} | {b["id"] for r in m["roles"] for b in r["blocks"]}
    if rng.random() < 0.5:
        ids |= {r["id"] for r in m["roles"]}
    m = rename(m, ids, rng, taken)
    # 5. order
    for key in ("types", "values", "primitives", "constructors", "encodings", "messages", "roles", "targets"):
        if isinstance(m.get(key), list) and rng.random() < 0.5:
            rng.shuffle(m[key])
    for role in m["roles"]:
        if rng.random() < 0.5:
            rng.shuffle(role["blocks"])
    return m


def encode(model: dict, rng: random.Random) -> bytes:
    def shuffle_keys(node):
        if isinstance(node, dict):
            items = [(k, shuffle_keys(v)) for k, v in node.items()]
            rng.shuffle(items)
            return dict(items)
        if isinstance(node, list):
            return [shuffle_keys(v) for v in node]
        return node
    if rng.random() < 0.5:
        model = shuffle_keys(model)
    text = json.dumps(model, ensure_ascii=rng.random() < 0.5, indent=rng.choice([None, 1, 2, 4]),
                      separators=rng.choice([(",", ":"), (", ", ": ")]) if rng.random() < 0.3 else None)
    return text.encode("utf-8")


# ---- seeded bugs in the exporter's output -------------------------------------------------

STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def regions(text: str) -> dict[str, tuple[int, int]]:
    program = text.index("def program")
    environment = text.index("def environment")
    end = text.index("\nend ", environment)
    return {"program": (program, environment), "environment": (environment, end)}


def list_elements(text: str, start: int) -> list[tuple[int, int]]:
    """Top-level elements of the list literal whose '[' is at `start`."""
    depth, i, elems, begin = 0, start + 1, [], start + 1
    while i < len(text):
        c = text[i]
        if c == '"':
            i = STRING.match(text, i).end()
            continue
        if c in "[(⟨":
            depth += 1
        elif c in "])⟩":
            if depth == 0:
                if text[begin:i].strip():
                    elems.append((begin, i))
                return elems
            depth -= 1
        elif c == "," and depth == 0:
            elems.append((begin, i))
            begin = i + 1
        i += 1
    return elems


def mutate(text: str, rng: random.Random) -> tuple[str, str, str]:
    """Return (mutated text, operator, expected failing theorem)."""
    span = regions(text)
    operators = ["program-string", "environment-string", "constructor-swap", "list-swap", "list-drop"]
    rng.shuffle(operators)
    for op in operators:
        lo, hi = span["environment" if op == "environment-string" else "program"]
        expected = "profile_binding" if op == "environment-string" else "binding"
        if op.endswith("string"):
            spots = [m for m in STRING.finditer(text, lo, hi)]
            if spots:
                m = rng.choice(spots)
                return text[:m.end() - 1] + "~" + text[m.end() - 1:], op, expected
        elif op == "constructor-swap":
            pairs = [("(.input ", "(.clear "), ("(.clear ", "(.input "), ("(.halt ", "(.goto "),
                     ("(.goto ", "(.halt "), ("(.generate ", "(.fetch "), ("(.fetch ", "(.generate ")]
            spots = [(m.start(), a, b) for a, b in pairs for m in re.finditer(re.escape(a), text[lo:hi])]
            if spots:
                at, a, b = rng.choice(spots)
                at += lo
                return text[:at] + b + text[at + len(a):], op + ":" + a.strip("( ") + "->" + b.strip("( "), expected
        else:
            lists = []
            for m in re.finditer(r"\[", text[lo:hi]):
                start = lo + m.start()
                if text[start - 1] == "\\" or STRING_inside(text, lo, start):
                    continue
                elems = list_elements(text, start)
                if op == "list-swap":
                    pairs = [(a, b) for a, b in zip(elems, elems[1:])
                             if text[a[0]:a[1]].strip() != text[b[0]:b[1]].strip()]
                    if pairs:
                        lists.append(pairs)
                elif len(elems) >= 2:
                    lists.append(elems)
            if lists:
                chosen = rng.choice(lists)
                if op == "list-swap":
                    (a0, a1), (b0, b1) = rng.choice(chosen)
                    first, second = text[a0:a1], text[b0:b1]
                    return text[:a0] + second + text[a1:b0] + first + text[b1:], op, expected
                i = rng.randrange(len(chosen))
                s0, s1 = chosen[i]
                if i + 1 < len(chosen):
                    return text[:s0] + text[chosen[i + 1][0]:], op, expected
                return text[:chosen[i - 1][1]] + text[s1:], op, expected
    raise ValueError("no applicable mutation")


def STRING_inside(text: str, lo: int, pos: int) -> bool:
    for m in STRING.finditer(text, lo, pos + 1):
        if m.start() < pos < m.end():
            return True
    return False


# ---- pipeline ----------------------------------------------------------------------------

def run(argv, cwd=ROOT):
    return subprocess.run([str(a) for a in argv], cwd=cwd, text=True, encoding="utf-8", errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def theorem_at(path: Path, line: int) -> str:
    text = path.read_text(encoding="utf-8").splitlines()
    for i in range(line - 1, -1, -1):
        m = re.match(r"\s*theorem\s+([A-Za-z0-9_]+)", text[i])
        if m:
            return m.group(1)
    return "<outside a theorem>"


ERROR_LINE = re.compile(r"^error: .*?(VAKE[\\/]Generated[\\/][^:\\/\s]+\.lean):(\d+):\d+", re.MULTILINE)


def error_locations(log: str) -> list[tuple[str, int]]:
    """(POSIX relative path, line) of Lean errors in generated modules, for POSIX or Windows logs."""
    return [(path.replace("\\", "/"), int(line)) for path, line in ERROR_LINE.findall(log)]


def build(workspace: Path, lake: str, modules: list[str], log: Path) -> dict[str, list[str]]:
    """Build modules; return {module: [failing theorem or file-level error]}."""
    proc = run([lake, "build", *modules], workspace)
    log.write_text(proc.stdout, encoding="utf-8")
    failures: dict[str, list[str]] = {}
    for path, line in error_locations(proc.stdout):
        module = path[:-5].replace("/", ".")
        where = theorem_at(workspace / path, line) if "/B" in path else "target-elaboration"
        failures.setdefault(module, []).append(where)
    if proc.returncode and not failures:
        failures["<build>"] = ["unparsed failure; see log"]
    elif proc.returncode:
        # A failed dependency may prevent a binding module from running at all.
        # Absence from the generated-file diagnostics is not evidence of success.
        for module in modules:
            if module in failures or module.replace(".B", ".M") in failures:
                continue
            confirmed = run([lake, "build", module], workspace)
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"\nConfirming {module}:\n{confirmed.stdout}")
            if confirmed.returncode:
                failures[module] = ["dependency-or-build-failure"]
    return failures


def response_status(proc) -> str:
    try:
        value = json.loads(proc.stdout)
    except ValueError:
        return "INTERNAL_ERROR"
    return value.get("status", "INTERNAL_ERROR") if isinstance(value, dict) else "INTERNAL_ERROR"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=200, help="random variants to generate")
    parser.add_argument("--mutants", type=int, default=100, help="seeded bugs (at most one per agreeing export)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--batch", type=int, default=50, help="variants per Lean build")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.count <= 0 or args.batch <= 0 or args.mutants < 0:
        parser.error("--count and --batch must be positive; --mutants must be nonnegative")
    out = (args.out or ROOT / "reports/runs" / ("differential-" + str(time.time_ns()))).resolve()
    if out.exists():
        parser.error("Output directory must be fresh")
    out.mkdir(parents=True)
    rng = random.Random(args.seed)
    binary = Path(configured("VAKE") or ROOT / "target/debug" / ("vake.exe" if os.name == "nt" else "vake"))
    lake = configured("LAKE") or shutil.which("lake")
    if not lake or not binary.exists():
        parser.error("Requires a built CLI and Lean/Lake 4.34.1")
    started = time.monotonic()
    seeds = {name: json.loads((ROOT / "examples" / name).read_text(encoding="utf-8")) for name in SEEDS}
    workspace = out / "workspace"
    cache = lean_workspace.prepare(ROOT / "lean", workspace, lake, out / "library-cache-build.log")
    mutant_space = out / "mutants"
    lean_workspace.prepare(ROOT / "lean", mutant_space, lake, out / "library-cache-build-mutants.log")

    rejected_by_frontend: dict[str, int] = {}
    trials, accepted, digests = [], [], set()
    for n in range(args.count):
        seed_name = rng.choice(SEEDS)
        model_bytes = encode(variant(seeds[seed_name], rng), rng)
        directory = out / "variants" / f"{n:05d}"
        directory.mkdir(parents=True)
        (directory / "model.json").write_bytes(model_bytes)
        row = {"trial": n, "seed": seed_name, "sha256": hashlib.sha256(model_bytes).hexdigest()}
        checked = run([binary, "check", directory / "model.json"])
        status = response_status(checked)
        expected_codes = {"CHECKED": 0, "OPEN_OBLIGATION": 2, "PARSE_ERROR": 1, "TYPE_ERROR": 1, "UNSUPPORTED": 1}
        if status not in expected_codes or checked.returncode != expected_codes[status]:
            row.update(result="frontend_failure", status=status, exit_code=checked.returncode)
            (directory / "check.log").write_text(checked.stdout, encoding="utf-8")
            trials.append(row)
            continue
        if status not in ("CHECKED", "OPEN_OBLIGATION"):
            reason = status
            rejected_by_frontend[reason] = rejected_by_frontend.get(reason, 0) + 1
            row["result"] = "rejected_by_frontend:" + reason
            trials.append(row)
            shutil.rmtree(directory)
            continue
        exported = run([binary, "export", directory / "model.json", "--profile", PROFILE, "--out", directory / "export"])
        if exported.returncode or response_status(exported) != "EXPORTED":
            row["result"] = "export_failed"
            trials.append(row)
            continue
        imported = run([sys.executable, ROOT / "scripts/import_model.py", directory / "export", "--lean-dir", workspace])
        if imported.returncode:
            row["result"] = "importer_disagreement"
            row["detail"] = imported.stdout[-2000:]
            trials.append(row)
            continue
        row["proof"] = json.loads(imported.stdout)["proof"]
        row["export"] = str(directory / "export")
        digests.add(row["sha256"])
        accepted.append(row)
        trials.append(row)

    disagreements = []
    for i in range(0, len(accepted), args.batch):
        batch = accepted[i:i + args.batch]
        failures = build(workspace, lake, [r["proof"] for r in batch], out / f"build-{i // args.batch:03d}.log")
        if "<build>" in failures:
            raise RuntimeError("Lean build failed without diagnostics; see logs")
        for r in batch:
            module_failures = failures.get(r["proof"], []) + failures.get(r["proof"].replace(".B", ".M"), [])
            r["result"] = "agree" if not module_failures else "lean_disagreement"
            if module_failures:
                r["failing"] = module_failures
                disagreements.append(r)

    agreeing = [r for r in accepted if r["result"] == "agree"]
    mutants = []
    for r in rng.sample(agreeing, min(args.mutants, len(agreeing))):
        identity = r["proof"].split(".B", 1)[1]
        target_rel = f"VAKE/Generated/M{identity}.lean"
        text = (workspace / target_rel).read_text(encoding="utf-8")
        mutated, op, expected = mutate(text, rng)
        for rel in (target_rel, f"VAKE/Generated/B{identity}.lean", f"VAKE/Imported/M{identity}.lean"):
            dest = mutant_space / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(workspace / rel, dest)
        (mutant_space / target_rel).write_text(mutated, encoding="utf-8")
        mutants.append({"trial": r["trial"], "seed": r["seed"], "operator": op, "expected": expected, "proof": r["proof"]})
    for i in range(0, len(mutants), args.batch):
        batch = mutants[i:i + args.batch]
        failures = build(mutant_space, lake, [m["proof"] for m in batch], out / f"mutant-build-{i // args.batch:03d}.log")
        for m in batch:
            got = failures.get(m["proof"], []) + failures.get(m["proof"].replace(".B", ".M"), [])
            m["failing"] = got
            m["result"] = ("rejected_at_expected_certificate" if got and set(got) == {m["expected"]}
                           else "rejected_elsewhere" if got else "NOT_REJECTED")

    def tally(rows, key):
        counts: dict[str, int] = {}
        for row in rows:
            counts[row[key]] = counts.get(row[key], 0) + 1
        return dict(sorted(counts.items()))

    operators: dict[str, dict[str, int]] = {}
    for m in mutants:
        family = m["operator"].split(":")[0]
        operators.setdefault(family, {}).setdefault(m["result"], 0)
        operators[family][m["result"]] += 1
    summary = {
        "status": "PASSED" if agreeing and not disagreements
                  and len(mutants) == min(args.mutants, args.count)
                  and all(m["result"] == "rejected_at_expected_certificate" for m in mutants)
                  and not any(t.get("result") in ("frontend_failure", "export_failed", "importer_disagreement") for t in trials) else "FAILED",
        "seed": args.seed, "trials": args.count,
        "admitted_variants": len(accepted), "distinct_admitted_models": len(digests),
        "rejected_by_frontend": rejected_by_frontend,
        "per_seed_admitted": tally(accepted, "seed"),
        "agreeing_exports": len(agreeing), "disagreements": len(disagreements),
        "export_failures": sum(t.get("result") == "export_failed" for t in trials),
        "frontend_failures": sum(t.get("result") == "frontend_failure" for t in trials),
        "importer_disagreements": sum(t.get("result") == "importer_disagreement" for t in trials),
        "seeded_bugs": len(mutants), "seeded_bug_results": tally(mutants, "result") if mutants else {},
        "seeded_bug_operators": operators, "library_cache": cache.get("library_cache"),
        "elapsed_s": round(time.monotonic() - started, 1), "output": str(out),
    }
    (out / "trials.json").write_text(json.dumps(trials, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "mutants.json").write_text(json.dumps(mutants, indent=2) + "\n", encoding="utf-8")
    (out / "differential-result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
